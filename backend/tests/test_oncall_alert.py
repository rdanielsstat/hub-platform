"""On-call triage (oncall/alert.py): which grafana-alert payloads make
the agent act, and that everything else is ignored."""

import json
from pathlib import Path

import pytest

from oncall.alert import Decision, decide, main, parse_payload

FIRING_DEV = {
    "status": "firing",
    "alertname": "Project creation 5xx rate above 2% (dev)",
    "hub_environment": "dev",
    "hub_oncall": "true",
    "summary": "POST /projects 5xx rate above 2% over 5 minutes",
    "firing": 1,
    "resolved": 0,
    "group_key": "{}:{alertname=x}",
    "external_url": "https://blackpoplar56.grafana.net/",
}


def _with(**changes: object) -> dict:
    payload = dict(FIRING_DEV)
    for key, value in changes.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    return payload


def test_firing_on_dev_rolls_back() -> None:
    decision = decide(FIRING_DEV)
    assert decision.action == "rollback"
    assert decision.environment == "dev"
    assert decision.title == "On-call: Project creation 5xx rate above 2% (dev)"


def test_firing_on_prod_only_diagnoses() -> None:
    decision = decide(_with(hub_environment="prod"))
    assert decision.action == "diagnose"
    assert "never roll back" in decision.reason


def test_resolved_is_recorded_not_acted_on() -> None:
    decision = decide(_with(status="resolved", firing=0, resolved=1))
    assert decision.action == "resolved"
    assert decision.title == decide(FIRING_DEV).title


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        _with(status=None),
        _with(status="pending"),
        _with(status=["firing"]),
        _with(hub_oncall=None),
        _with(hub_oncall="false"),
        _with(hub_oncall=True),
        _with(hub_environment=None),
        _with(hub_environment="staging"),
        _with(alertname=None),
        _with(alertname=""),
        _with(firing=None),
        _with(firing=0),
        _with(firing="1"),
        _with(firing=True),
    ],
    ids=lambda p: json.dumps(p)[:60] if p is not None else "none",
)
def test_anything_else_is_ignored(payload: dict | None) -> None:
    assert decide(payload).action == "ignore"


@pytest.mark.parametrize("raw", [None, "", "not json", "[1, 2]", '"firing"', "null"])
def test_unparseable_payloads_are_none(raw: str | None) -> None:
    assert parse_payload(raw) is None


def test_fields_are_cleaned_for_titles_and_outputs() -> None:
    decision = decide(
        _with(alertname="Bad\nname`$(rm -rf /)`", summary="x" * 500 + "\nmore")
    )
    assert "\n" not in decision.alertname
    assert "`" not in decision.alertname and "$" not in decision.alertname
    assert len(decision.summary) <= 200


def test_ignored_decision_has_no_title() -> None:
    assert Decision("ignore", "x").title == ""


def test_main_writes_outputs(tmp_path: Path) -> None:
    output = tmp_path / "out"
    summary = tmp_path / "summary"
    env = {
        "ALERT_PAYLOAD": json.dumps(FIRING_DEV),
        "GITHUB_OUTPUT": str(output),
        "GITHUB_STEP_SUMMARY": str(summary),
    }
    assert main(env) == 0
    lines = dict(line.split("=", 1) for line in output.read_text().splitlines())
    assert lines["action"] == "rollback"
    assert lines["environment"] == "dev"
    assert "rollback" in summary.read_text()


def test_main_with_no_payload_ignores_and_succeeds(tmp_path: Path) -> None:
    """A grafana-alert dispatch with no client_payload: the run exits
    cleanly with action=ignore, so no later job touches dev."""
    output = tmp_path / "out"
    assert main({"ALERT_PAYLOAD": "{}", "GITHUB_OUTPUT": str(output)}) == 0
    assert "action=ignore" in output.read_text()
