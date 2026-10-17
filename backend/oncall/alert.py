"""On-call triage: decide what to do with a Grafana alert that reached
.github/workflows/observability-alert-handler.yml through GitHub's
repository_dispatch (event_type "grafana-alert"). Run there as
`python -m oncall.alert` from backend/.

The Grafana contact point (infra/hub/grafana.tf) sends a custom
payload (infra/hub/grafana/dispatch-payload.tmpl), which GitHub hands
the workflow as github.event.client_payload. The workflow passes it in
ALERT_PAYLOAD as JSON. This script never trusts it: a payload that
isn't JSON, isn't an object, misses a field, or isn't a firing alert
for a rule labeled hub_oncall="true" leads to "ignore", and the
workflow exits without touching dev.

Decisions:

    rollback   firing, hub_oncall="true", hub_environment="dev":
               diagnose, then roll dev back to the previous image
    diagnose   firing, hub_oncall="true", hub_environment="prod":
               diagnose and record it only. Prod is never rolled back
               by an agent; a human promotes the fix.
    resolved   resolved, hub_oncall="true": record the resolution
    ignore     anything else

Standard library only, like oncall/diagnose.py. Writes the decision to
GITHUB_OUTPUT (action, reason, environment, alertname, summary, title)
and the step summary.
"""

import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

ENVIRONMENTS = ("dev", "prod")
_MAX_FIELD = 200
# Labels and annotations go into issue titles and step outputs: keep
# them to one short line of plain text.
_UNSAFE = re.compile(r"[^\w .,:;()%<>=/+-]")


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str
    environment: str = ""
    alertname: str = ""
    summary: str = ""

    @property
    def title(self) -> str:
        """The tracking issue's title, the same for every notification of
        one incident so the workflow finds the open issue again."""
        if not self.alertname:
            return ""
        return f"On-call: {self.alertname}"


def _clean(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _UNSAFE.sub("", value.replace("\n", " ")).strip()[:_MAX_FIELD]


def parse_payload(raw: str | None) -> Mapping[str, Any] | None:
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def decide(payload: Mapping[str, Any] | None) -> Decision:
    if payload is None:
        return Decision("ignore", "payload missing or not a JSON object")

    status = payload.get("status")
    if status not in ("firing", "resolved"):
        return Decision(
            "ignore", f"status is {_clean(status) or 'missing'}, not firing"
        )
    if payload.get("hub_oncall") != "true":
        return Decision("ignore", "alert is not labeled hub_oncall=true")

    environment = payload.get("hub_environment")
    if environment not in ENVIRONMENTS:
        return Decision(
            "ignore", f"hub_environment is {_clean(environment) or 'missing'}"
        )
    alertname = _clean(payload.get("alertname"))
    if not alertname:
        return Decision("ignore", "alertname missing")
    summary = _clean(payload.get("summary")) or alertname
    found = {"environment": environment, "alertname": alertname, "summary": summary}

    if status == "resolved":
        return Decision("resolved", "alert resolved", **found)

    firing = payload.get("firing")
    if not isinstance(firing, int) or isinstance(firing, bool) or firing < 1:
        return Decision("ignore", "no firing alerts in the notification", **found)

    if environment == "dev":
        return Decision("rollback", "firing on dev", **found)
    return Decision(
        "diagnose", "firing on prod: diagnose only, never roll back", **found
    )


def _write_outputs(env: Mapping[str, str], decision: Decision) -> None:
    lines = {
        "action": decision.action,
        "reason": decision.reason,
        "environment": decision.environment,
        "alertname": decision.alertname,
        "summary": decision.summary,
        "title": decision.title,
    }
    path = env.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a") as f:
            for key, value in lines.items():
                f.write(f"{key}={value}\n")
    summary = env.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(
                f"## On-call triage\n\n**Action:** {decision.action}\n\n"
                f"**Why:** {decision.reason}\n"
            )


def main(env: Mapping[str, str] = os.environ) -> int:
    decision = decide(parse_payload(env.get("ALERT_PAYLOAD")))
    print(f"action={decision.action} reason={decision.reason}")
    _write_outputs(env, decision)
    return 0


if __name__ == "__main__":
    sys.exit(main())
