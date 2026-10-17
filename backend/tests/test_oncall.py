"""The on-call diagnostic (oncall/diagnose.py) and the workflow that runs
it (.github/workflows/observability-alert-handler.yml).

No test here calls OpenAI: the HTTP call goes through an injectable
urlopen.
"""

import io
import json
import urllib.error
from pathlib import Path

import pytest
import yaml

from oncall import diagnose

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "observability-alert-handler.yml"

FAKE_KEY = "sk-test-not-a-real-key"


def _env(**overrides: str) -> dict[str, str]:
    env = {
        "OPENAI_API_KEY": FAKE_KEY,
        "ONCALL_MODEL": "test-model",
        "ONCALL_INPUT_PRICE_PER_M": "0.15",
        "ONCALL_OUTPUT_PRICE_PER_M": "0.60",
        "ONCALL_RUNS_PER_MONTH": "30",
        "ALERT_SUMMARY": "auth_register_post error rate 25% over 15m",
    }
    env.update(overrides)
    return env


class _FakeResponse(io.BytesIO):
    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _ok_urlopen(calls: list):
    def urlopen(request, timeout=None):
        calls.append(request)
        body = {
            "choices": [{"message": {"content": "Likely a DB constraint issue."}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 40},
        }
        return _FakeResponse(json.dumps(body).encode())

    return urlopen


def _no_call_urlopen(_request, timeout=None):
    raise AssertionError("OpenAI must not be called")


# ---- cost estimate -------------------------------------------------


def test_estimate_call_cost() -> None:
    pricing = diagnose.Pricing(input_per_million=1.0, output_per_million=2.0)
    # 400 chars ~ 100 input tokens; 200 output tokens max.
    cost = diagnose.estimate_call_cost("x" * 400, 200, pricing)
    assert cost == pytest.approx((100 * 1.0 + 200 * 2.0) / 1_000_000)


def test_actual_cost_from_usage() -> None:
    pricing = diagnose.Pricing(input_per_million=1.0, output_per_million=2.0)
    usage = {"prompt_tokens": 1000, "completion_tokens": 500}
    assert diagnose.actual_cost(usage, pricing) == pytest.approx(0.002)


# ---- main ----------------------------------------------------------


def test_under_budget_calls_openai_and_prints_diagnostic(capsys) -> None:
    calls: list = []
    code = diagnose.main(_env(), urlopen=_ok_urlopen(calls))
    out = capsys.readouterr().out

    assert code == 0
    assert len(calls) == 1
    assert "Likely a DB constraint issue." in out
    assert "Estimated cost" in out and "/month" in out and "$5.00" in out
    assert "Actual cost" in out
    assert FAKE_KEY not in out


def test_request_shape(capsys) -> None:
    calls: list = []
    diagnose.main(_env(), urlopen=_ok_urlopen(calls))
    request = calls[0]
    assert request.full_url == "https://api.openai.com/v1/chat/completions"
    assert request.get_header("Authorization") == f"Bearer {FAKE_KEY}"
    payload = json.loads(request.data)
    assert payload["model"] == "test-model"
    assert payload["max_completion_tokens"] == diagnose.MAX_OUTPUT_TOKENS
    prompt = " ".join(m["content"] for m in payload["messages"])
    assert "auth_register_post error rate 25% over 15m" in prompt
    assert "2-3 sentence" in prompt


def test_over_budget_refuses_with_warning_and_no_call(capsys) -> None:
    code = diagnose.main(
        _env(ONCALL_RUNS_PER_MONTH="100000000"), urlopen=_no_call_urlopen
    )
    out = capsys.readouterr().out
    # A warning for now, not a failed run.
    assert code == 0
    assert "::warning" in out
    assert "$5.00" in out
    assert "skipping" in out.lower()


def test_missing_api_key_fails(capsys) -> None:
    code = diagnose.main(_env(OPENAI_API_KEY=""), urlopen=_no_call_urlopen)
    assert code == 1
    assert "::error" in capsys.readouterr().out


def test_openai_http_error_fails_without_leaking_key(capsys) -> None:
    def urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"error": {"message": "Incorrect API key provided"}}'),
        )

    code = diagnose.main(_env(), urlopen=urlopen)
    out = capsys.readouterr().out
    assert code == 1
    assert "::error" in out and "401" in out
    assert "Incorrect API key provided" in out
    assert FAKE_KEY not in out


def test_writes_step_summary(tmp_path, capsys) -> None:
    summary = tmp_path / "summary.md"
    diagnose.main(_env(GITHUB_STEP_SUMMARY=str(summary)), urlopen=_ok_urlopen([]))
    text = summary.read_text()
    assert "Likely a DB constraint issue." in text
    assert "$5.00" in text


# ---- workflow ------------------------------------------------------


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text())


def test_workflow_wakes_on_grafana_alerts_and_keeps_manual_runs(workflow: dict) -> None:
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = workflow[True]
    assert set(triggers) == {"repository_dispatch", "workflow_dispatch"}
    assert triggers["repository_dispatch"] == {"types": ["grafana-alert"]}


def test_manual_run_still_requires_oncall_environment(workflow: dict) -> None:
    job = workflow["jobs"]["diagnose-manual"]
    assert job["if"] == "github.event_name == 'workflow_dispatch'"
    assert job["environment"] == "observability-oncall"


def test_automatic_jobs_need_no_approval(workflow: dict) -> None:
    """The dispatch path runs without a human: no job waits on the
    observability-oncall reviewers, and the rollback runs in dev, whose
    environment has no reviewers."""
    for name, job in workflow["jobs"].items():
        if name == "diagnose-manual":
            continue
        assert job.get("environment") is None, name


def test_triage_gates_every_automatic_job(workflow: dict) -> None:
    jobs = workflow["jobs"]
    assert jobs["triage"]["if"] == "github.event_name == 'repository_dispatch'"
    assert jobs["record"]["if"] == "needs.triage.outputs.action != 'ignore'"
    rollback = jobs["rollback"]
    assert "needs.triage.outputs.action == 'rollback'" in rollback["if"]
    assert "needs.triage.outputs.environment == 'dev'" in rollback["if"]
    assert "needs.record.outputs.rolled_back == 'false'" in rollback["if"]
    assert rollback["uses"] == "./.github/workflows/rollback-dev.yml"


def test_payload_reaches_triage_via_env_only(workflow: dict) -> None:
    (step,) = [
        s
        for s in workflow["jobs"]["triage"]["steps"]
        if "oncall.alert" in s.get("run", "")
    ]
    assert step["env"]["ALERT_PAYLOAD"] == "${{ toJSON(github.event.client_payload) }}"
    assert "${{" not in step["run"]


def test_workflow_permissions_are_read_only(workflow: dict) -> None:
    assert workflow["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("job_name", ["diagnose-manual", "diagnose"])
def test_workflow_passes_key_and_inputs_via_env_only(
    workflow: dict, job_name: str
) -> None:
    job = workflow["jobs"][job_name]
    (step,) = [s for s in job["steps"] if "oncall.diagnose" in s.get("run", "")]
    assert step["env"]["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    assert "ALERT_SUMMARY" in step["env"]
    assert "ONCALL_RUNS_PER_MONTH" in step["env"]
    # No expression interpolated into the shell script itself.
    assert "${{" not in step["run"]
    assert step["working-directory"] == "backend"


def test_no_expression_is_interpolated_into_any_shell_script(workflow: dict) -> None:
    """Alert fields are attacker-reachable text: every run script reads
    them from env, never from a ${{ }} expression."""
    for name, job in workflow["jobs"].items():
        for step in job.get("steps", []):
            assert "${{" not in step.get("run", ""), (name, step.get("name"))


def test_rollbacks_are_counted_by_the_tested_module(workflow: dict) -> None:
    """The once-per-incident check counts only successful rollbacks
    (oncall/rollback_record.py), not every comment with a marker."""
    steps = workflow["jobs"]["record"]["steps"]
    (count,) = [s for s in steps if s.get("id") == "count"]
    assert "python -m oncall.rollback_record count" in count["run"]
    assert workflow["jobs"]["record"]["outputs"]["rolled_back"] == (
        "${{ steps.count.outputs.rolled_back }}"
    )
    assert not any("oncall:rollback" in s.get("run", "") for s in steps)


def test_rollback_outcome_comment_comes_from_the_module() -> None:
    rollback = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "rollback-dev.yml").read_text()
    )
    (job,) = rollback["jobs"].values()
    (step,) = [
        s
        for s in job["steps"]
        if s.get("name") == "Comment the outcome on the tracking issue"
    ]
    assert "python -m oncall.rollback_record comment" in step["run"]
    assert "oncall:rollback" not in step["run"]
    assert step["env"]["APPLY_OUTCOME"] == "${{ steps.apply.outcome }}"
