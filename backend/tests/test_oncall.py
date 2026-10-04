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


def test_workflow_is_manual_dispatch_only(workflow: dict) -> None:
    # PyYAML reads the bare key `on` as the boolean True.
    triggers = workflow[True]
    assert set(triggers) == {"workflow_dispatch"}


def test_workflow_job_requires_oncall_environment(workflow: dict) -> None:
    (job,) = workflow["jobs"].values()
    assert job["environment"] == "observability-oncall"


def test_workflow_permissions_are_read_only(workflow: dict) -> None:
    assert workflow["permissions"] == {"contents": "read"}


def test_workflow_passes_key_and_inputs_via_env_only(workflow: dict) -> None:
    (job,) = workflow["jobs"].values()
    (step,) = [s for s in job["steps"] if "oncall.diagnose" in s.get("run", "")]
    assert step["env"]["OPENAI_API_KEY"] == "${{ secrets.OPENAI_API_KEY }}"
    assert step["env"]["ALERT_SUMMARY"] == "${{ inputs.alert_summary }}"
    assert step["env"]["ONCALL_RUNS_PER_MONTH"] == "${{ inputs.runs_per_month }}"
    # No expression interpolated into the shell script itself.
    assert "${{" not in step["run"]
    assert step["working-directory"] == "backend"
