"""The rollback record (oncall/rollback_record.py): only a rollback that
succeeded counts toward the one rollback per incident."""

import json
from pathlib import Path

import pytest

from oncall.rollback_record import (
    FAILURE_MARKER,
    SUCCESS_MARKER,
    count_successful_rollbacks,
    main,
    outcome_comment,
)

CURRENT = "20261017-183848-1b3daad"
PREVIOUS = "20261017-182910-1b3daad"
RUN = "https://github.com/rdanielsstat/hub-platform/actions/runs/1"

DIAGNOSIS = "**Diagnosis** (OpenAI, gpt-4o-mini)\n\nCheck the logs."
RESOLVED = "**Resolved:** Grafana reports the alert resolved."

# What rollback-dev.yml posted before this fix, for a failed attempt
# (issue #23, 2026-10-17): the bare marker, with a failure.
LEGACY_FAILED = (
    "<!-- oncall:rollback -->\n**Rollback** (on-call agent, no human approval, "
    "dev only)\n\nRollback of dev **failed** (failure); dev may still be on "
    f"`{CURRENT}`. A human needs to look.\n\nReason: x\n\nRun: {RUN}"
)
LEGACY_SUCCEEDED = (
    "<!-- oncall:rollback -->\n**Rollback** (on-call agent, no human approval, "
    f"dev only)\n\nRolled dev back from `{CURRENT}` to `{PREVIOUS}`. GET "
    f"/api/health returned 200.\n\nReason: x\n\nRun: {RUN}"
)


def _comment(status: str) -> str:
    return outcome_comment(status, CURRENT, PREVIOUS, "5xx above 2%", RUN)


def test_a_failed_rollback_does_not_increment_the_count() -> None:
    before = [DIAGNOSIS]
    after = [DIAGNOSIS, _comment("failure")]
    assert count_successful_rollbacks(before) == 0
    assert count_successful_rollbacks(after) == 0


def test_a_successful_rollback_increments_the_count() -> None:
    before = [DIAGNOSIS, _comment("failure")]
    after = [*before, _comment("success")]
    assert count_successful_rollbacks(before) == 0
    assert count_successful_rollbacks(after) == 1


@pytest.mark.parametrize("status", ["failure", "cancelled", ""])
def test_anything_but_success_is_recorded_as_a_failure(status: str) -> None:
    body = _comment(status)
    assert body.startswith(FAILURE_MARKER)
    assert SUCCESS_MARKER not in body
    assert "**failed**" in body


def test_failure_before_the_apply_says_dev_is_unchanged() -> None:
    body = outcome_comment("failure", CURRENT, PREVIOUS, "r", RUN, "failure")
    assert f"still on `{CURRENT}`" in body
    assert count_successful_rollbacks([body]) == 0


def test_failed_health_check_after_the_apply_says_dev_changed() -> None:
    body = outcome_comment("failure", CURRENT, PREVIOUS, "r", RUN, "success")
    assert f"dev now runs `{PREVIOUS}`" in body
    assert "didn't return 200" in body
    assert count_successful_rollbacks([body]) == 0


def test_success_comment_names_both_tags() -> None:
    body = _comment("success")
    assert body.startswith(SUCCESS_MARKER)
    assert f"`{CURRENT}` to `{PREVIOUS}`" in body


def test_legacy_markers_count_only_completed_rollbacks() -> None:
    """Issue #23's failed attempt, posted with the old bare marker, must not
    block a retry; an old successful one still counts."""
    assert count_successful_rollbacks([LEGACY_FAILED]) == 0
    assert count_successful_rollbacks([LEGACY_SUCCEEDED]) == 1


def test_issue_23_thread_counts_zero() -> None:
    """The thread as it stood after the drill: one failed attempt, two
    diagnoses, two resolutions, two refusals."""
    refusal = "Still firing after a rollback. The agent rolls back once per incident"
    thread = [
        DIAGNOSIS,
        LEGACY_FAILED,
        RESOLVED,
        refusal,
        DIAGNOSIS,
        refusal,
        DIAGNOSIS,
    ]
    assert count_successful_rollbacks(thread) == 0


def _issue_json(*bodies: str) -> str:
    return json.dumps(
        {"comments": [{"body": b, "author": {"login": "x"}} for b in bodies]}
    )


def test_count_command_writes_outputs(tmp_path: Path) -> None:
    comments = tmp_path / "comments.json"
    out = tmp_path / "out"
    comments.write_text(_issue_json(DIAGNOSIS, _comment("failure")))
    assert main(["count", str(comments)], {"GITHUB_OUTPUT": str(out)}) == 0
    assert out.read_text().splitlines() == ["rollbacks=0", "rolled_back=false"]

    comments.write_text(
        _issue_json(DIAGNOSIS, _comment("failure"), _comment("success"))
    )
    out.unlink()
    assert main(["count", str(comments)], {"GITHUB_OUTPUT": str(out)}) == 0
    assert out.read_text().splitlines() == ["rollbacks=1", "rolled_back=true"]


def test_count_command_tolerates_an_issue_without_comments(tmp_path: Path) -> None:
    comments = tmp_path / "comments.json"
    out = tmp_path / "out"
    comments.write_text("{}")
    assert main(["count", str(comments)], {"GITHUB_OUTPUT": str(out)}) == 0
    assert "rolled_back=false" in out.read_text()


def test_comment_command_writes_the_body(tmp_path: Path) -> None:
    out = tmp_path / "body.md"
    env = {
        "ROLLBACK_STATUS": "success",
        "CURRENT": CURRENT,
        "PREVIOUS": PREVIOUS,
        "REASON": "5xx above 2%",
        "RUN_URL": RUN,
    }
    assert main(["comment", str(out)], env) == 0
    assert out.read_text().startswith(SUCCESS_MARKER)


def test_bad_arguments() -> None:
    assert main([]) == 2
    assert main(["delete", "x"]) == 2
