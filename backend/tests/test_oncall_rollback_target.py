"""The dev rollback's target (oncall/rollback_target.py): the newest older
image built from a different commit."""

import io

import pytest

from oncall.rollback_target import choose_previous, commit_sha, main

# The 2026-10-17 pair: two builds of the same commit, 98370fc.
DRILL_CURRENT = "20261017-192835-98370fc"
DRILL_SAME_COMMIT = "20261017-192115-98370fc"
# Fixture only: a made-up SHA standing for "some other, older commit".
FIXTURE_OTHER_COMMIT = "20261017-183848-f1c7ab1"


def test_skips_tags_from_the_same_commit() -> None:
    tags = ["new-98370fc", "mid-98370fc", "old-abc1234"]
    assert choose_previous(tags, "new-98370fc") == "old-abc1234"


def test_only_the_same_commit_is_an_error() -> None:
    with pytest.raises(ValueError, match="other than 98370fc"):
        choose_previous(["new-98370fc", "mid-98370fc"], "new-98370fc")


def test_current_not_in_the_list_is_an_error() -> None:
    with pytest.raises(ValueError, match="not in the list"):
        choose_previous(["a-abc1234", "b-def5678"], "c-98370fc")


def test_the_2026_10_17_pair_goes_back_to_a_different_commit() -> None:
    tags = [DRILL_CURRENT, DRILL_SAME_COMMIT, FIXTURE_OTHER_COMMIT]
    assert choose_previous(tags, DRILL_CURRENT) == FIXTURE_OTHER_COMMIT


def test_an_older_build_of_the_same_commit_further_down_is_skipped_too() -> None:
    tags = ["t3-aaaaaaa", "t2-bbbbbbb", "t1-aaaaaaa"]
    assert choose_previous(tags, "t3-aaaaaaa") == "t2-bbbbbbb"


def test_commit_sha_is_the_text_after_the_last_dash() -> None:
    assert commit_sha(DRILL_CURRENT) == "98370fc"


def test_main_prints_the_previous_tag(capsys: pytest.CaptureFixture[str]) -> None:
    stdin = io.StringIO(
        f"{DRILL_CURRENT}\n{DRILL_SAME_COMMIT}\n{FIXTURE_OTHER_COMMIT}\n"
    )
    assert main(["--current", DRILL_CURRENT], stdin) == 0
    assert capsys.readouterr().out.strip() == FIXTURE_OTHER_COMMIT


def test_main_fails_with_a_message_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    stdin = io.StringIO(f"{DRILL_CURRENT}\n{DRILL_SAME_COMMIT}\n")
    assert main(["--current", DRILL_CURRENT], stdin) == 1
    out = capsys.readouterr()
    assert out.out == ""
    assert "other than 98370fc" in out.err
