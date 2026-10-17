"""Which image the dev rollback goes back to.

CI tags every image <yyyymmdd>-<hhmmss>-<commit sha>, and a rerun of the
dev deploy builds a new tag from the same commit. Going back one tag can
therefore redeploy the same code (2026-10-17: 20261017-192835-98370fc
rolled back to 20261017-192115-98370fc, and the fault stayed). The
rollback goes back to the newest image built from a different commit.

Run from backend/ by .github/workflows/rollback-dev.yml as:

    python -m oncall.rollback_target --current TAG < TAGS

TAGS is every tagged image in the dev ECR repository, one per line,
newest push first. Prints the previous tag; on error prints why to
stderr and exits 1.

Standard library only, like the rest of oncall/.
"""

import argparse
import sys
from collections.abc import Sequence


def commit_sha(tag: str) -> str:
    """The commit a tag was built from: the text after the last dash."""
    return tag.rsplit("-", 1)[-1]


def choose_previous(tags_newest_first: Sequence[str], current: str) -> str:
    """The first tag after current whose commit differs from current's."""
    if current not in tags_newest_first:
        raise ValueError(f"current tag {current} is not in the list")
    sha = commit_sha(current)
    older = tags_newest_first[tags_newest_first.index(current) + 1 :]
    for tag in older:
        if commit_sha(tag) != sha:
            return tag
    raise ValueError(
        f"no image older than {current} was built from a commit other than {sha}"
    )


def main(argv: Sequence[str] | None = None, stdin=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--current", required=True)
    args = parser.parse_args(argv)
    lines = (stdin or sys.stdin).read().splitlines()
    tags = [line.strip() for line in lines if line.strip()]
    try:
        print(choose_previous(tags, args.current))
    except ValueError as exc:
        print(f"rollback target: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
