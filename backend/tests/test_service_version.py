"""SERVICE_VERSION derivation (.github/scripts/service-version.sh), run
against throwaway git repos.

    no vX.Y.Z tag reachable      0.0.0+<sha>
    HEAD is tagged v1.2.0        1.2.0
    2 commits after v1.2.0       1.2.0+2.g<sha>
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "service-version.sh"

# Same pattern as infra/hub/main.tf's service_version validation.
SEMVER = re.compile(r"^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?$")

# Keep the developer's own git config (signing, hooks, default branch)
# out of these repos.
_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


class Repo:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.git("init", "-q")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", *args],
            cwd=self.path,
            env=_GIT_ENV,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def commit(self) -> None:
        self.git("commit", "-q", "--allow-empty", "-m", "change")

    def tag(self, name: str) -> None:
        self.git("tag", "-a", name, "-m", name)

    def sha(self) -> str:
        return self.git("rev-parse", "--short", "HEAD")

    def version(self) -> str:
        result = subprocess.run(
            ["bash", str(SCRIPT)],
            cwd=self.path,
            env=_GIT_ENV,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Repo:
    repo = Repo(tmp_path)
    repo.commit()
    return repo


def test_no_tags_reports_zero_version_with_sha(repo: Repo) -> None:
    assert repo.version() == f"0.0.0+{repo.sha()}"


def test_tagged_commit_reports_exact_version(repo: Repo) -> None:
    repo.tag("v1.2.0")
    assert repo.version() == "1.2.0"


def test_commits_after_tag_report_build_metadata(repo: Repo) -> None:
    repo.tag("v1.2.0")
    repo.commit()
    repo.commit()
    assert repo.version() == f"1.2.0+2.g{repo.sha()}"


def test_nearest_tag_wins(repo: Repo) -> None:
    repo.tag("v1.2.0")
    repo.commit()
    repo.tag("v1.3.0")
    repo.commit()
    assert repo.version() == f"1.3.0+1.g{repo.sha()}"


def test_ignores_tags_that_are_not_plain_vX_Y_Z(repo: Repo) -> None:
    repo.tag("v1.2.0")
    repo.commit()
    for name in ("release-2", "2.0.0", "v2.0.0-rc.1", "v2.0"):
        repo.tag(name)
    assert repo.version() == f"1.2.0+1.g{repo.sha()}"


@pytest.mark.parametrize("tags", [(), ("v1.2.0",), ("v1.2.0", "+1")])
def test_output_is_valid_semver(repo: Repo, tags: tuple[str, ...]) -> None:
    for tag in tags:
        if tag == "+1":
            repo.commit()
        else:
            repo.tag(tag)
    assert SEMVER.match(repo.version())
