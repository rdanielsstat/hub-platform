"""The on-call agent's rollback record on a tracking issue.

rollback-dev.yml comments the outcome of every rollback attempt on the
incident's tracking issue, with a hidden marker saying how it ended.
observability-alert-handler.yml then counts the successful ones to keep
to one rollback per incident. Only a rollback that actually changed dev
counts: a failed attempt (a missing variable, no older image, a
migration in between) is recorded, but the agent may try again on the
next firing.

Markers:

    <!-- oncall:rollback outcome=success -->  dev now runs the previous image
    <!-- oncall:rollback outcome=failure -->  the attempt failed; dev unchanged

Comments from before 2026-10-17 carry a bare <!-- oncall:rollback -->
for both outcomes; one counts only if it reports a completed rollback.

Run from backend/ as:

    python -m oncall.rollback_record count COMMENTS_JSON
        COMMENTS_JSON is `gh issue view N --json comments` output. Writes
        rollbacks=<n> and rolled_back=true|false to GITHUB_OUTPUT.
    python -m oncall.rollback_record comment OUT_FILE
        Writes the outcome comment to OUT_FILE, from ROLLBACK_STATUS (the
        job status), APPLY_OUTCOME (the apply step's outcome), CURRENT,
        PREVIOUS, REASON and RUN_URL.

Standard library only, like the rest of oncall/.
"""

import json
import os
import sys
from collections.abc import Iterable, Mapping

SUCCESS_MARKER = "<!-- oncall:rollback outcome=success -->"
FAILURE_MARKER = "<!-- oncall:rollback outcome=failure -->"
LEGACY_MARKER = "<!-- oncall:rollback -->"
# What a legacy comment said when the rollback had completed.
_LEGACY_SUCCESS_TEXT = "Rolled dev back from"


def is_successful_rollback(body: str) -> bool:
    if SUCCESS_MARKER in body:
        return True
    return LEGACY_MARKER in body and _LEGACY_SUCCESS_TEXT in body


def count_successful_rollbacks(bodies: Iterable[str]) -> int:
    return sum(1 for body in bodies if is_successful_rollback(body))


def comment_bodies(issue_json: str) -> list[str]:
    """The comment bodies from `gh issue view --json comments` output."""
    data = json.loads(issue_json or "{}")
    comments = data.get("comments", []) if isinstance(data, dict) else []
    return [
        c["body"]
        for c in comments
        if isinstance(c, dict) and isinstance(c.get("body"), str)
    ]


_NOT_COUNTED = (
    " This attempt doesn't count toward the one rollback per incident, so "
    "the agent tries again if the alert fires again. A human should look at "
    "the run."
)


def outcome_comment(
    status: str,
    current: str,
    previous: str,
    reason: str,
    run_url: str,
    apply_outcome: str = "",
) -> str:
    """The comment rollback-dev.yml posts. status is the job status: only
    "success" (the apply and the health check both passed) counts.
    apply_outcome says whether dev changed when the job failed."""
    if status == "success":
        marker = SUCCESS_MARKER
        result = (
            f"Rolled dev back from `{current}` to `{previous}`. "
            "GET /api/health returned 200."
        )
    elif apply_outcome == "success":
        marker = FAILURE_MARKER
        result = (
            f"Rollback of dev **failed** ({status or 'unknown'}): dev now runs "
            f"`{previous}`, but GET /api/health didn't return 200." + _NOT_COUNTED
        )
    else:
        marker = FAILURE_MARKER
        result = (
            f"Rollback of dev **failed** ({status or 'unknown'}) before it "
            f"changed anything; dev is still on `{current or 'unknown'}`."
            + _NOT_COUNTED
        )
    return (
        f"{marker}\n**Rollback** (on-call agent, no human approval, dev only)\n\n"
        f"{result}\n\nReason: {reason}\n\nRun: {run_url}"
    )


def _write_output(env: Mapping[str, str], values: Mapping[str, str]) -> None:
    path = env.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for key, value in values.items():
                f.write(f"{key}={value}\n")


def main(argv: list[str], env: Mapping[str, str] = os.environ) -> int:
    if len(argv) != 2 or argv[0] not in ("count", "comment"):
        print(__doc__, file=sys.stderr)
        return 2
    command, path = argv
    if command == "count":
        with open(path) as f:
            count = count_successful_rollbacks(comment_bodies(f.read()))
        _write_output(
            env,
            {"rollbacks": str(count), "rolled_back": "true" if count else "false"},
        )
        print(f"Successful rollbacks for this incident: {count}")
        return 0
    body = outcome_comment(
        env.get("ROLLBACK_STATUS", ""),
        env.get("CURRENT", ""),
        env.get("PREVIOUS", ""),
        env.get("REASON", ""),
        env.get("RUN_URL", ""),
        env.get("APPLY_OUTCOME", ""),
    )
    with open(path, "w") as f:
        f.write(body + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
