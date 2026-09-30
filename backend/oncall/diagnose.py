"""On-call diagnostic: ask OpenAI for a 2-3 sentence diagnosis of an
alert. Run by .github/workflows/observability-alert-handler.yml as
`python -m oncall.diagnose` from backend/.

Standard library only, so the workflow needs no dependency install.

Before calling OpenAI it estimates the monthly spend (cost of one call,
from a rough token count and the configured prices, times the expected
runs per month). Over MONTHLY_BUDGET_USD it skips the call with a
GitHub Actions warning instead; the run itself still succeeds. No
billing API is queried: this is an estimate.

Configuration, all from environment variables:

    OPENAI_API_KEY             required to call OpenAI
    ONCALL_MODEL               OpenAI model id
    ONCALL_INPUT_PRICE_PER_M   USD per 1M input tokens
    ONCALL_OUTPUT_PRICE_PER_M  USD per 1M output tokens
    ONCALL_RUNS_PER_MONTH      expected runs per month
    ALERT_SUMMARY              the alert to diagnose
    GITHUB_STEP_SUMMARY        set by Actions; the result is appended
"""

import json
import math
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

OPENAI_URL = "https://api.openai.com/v1/chat/completions"
MONTHLY_BUDGET_USD = 5.00
MAX_OUTPUT_TOKENS = 300
_CHARS_PER_TOKEN = 4
_TIMEOUT_S = 60

SYSTEM_PROMPT = (
    "You are the on-call engineer for hub-platform, a FastAPI backend on "
    "AWS Lambda with a Postgres database, instrumented with OpenTelemetry. "
    "Given an alert, write a 2-3 sentence diagnostic: the most likely "
    "causes, and the first thing to check or fix. Be specific and concise."
)


@dataclass(frozen=True)
class Pricing:
    input_per_million: float
    output_per_million: float


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / _CHARS_PER_TOKEN)


def estimate_call_cost(prompt: str, max_output_tokens: int, pricing: Pricing) -> float:
    """Upper-ish bound for one call: rough input tokens, full output budget."""
    return (
        estimate_tokens(prompt) * pricing.input_per_million
        + max_output_tokens * pricing.output_per_million
    ) / 1_000_000


def actual_cost(usage: Mapping[str, int], pricing: Pricing) -> float:
    return (
        usage.get("prompt_tokens", 0) * pricing.input_per_million
        + usage.get("completion_tokens", 0) * pricing.output_per_million
    ) / 1_000_000


def build_messages(alert_summary: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Alert: {alert_summary}\n\nWrite the 2-3 sentence diagnostic.",
        },
    ]


def call_openai(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    urlopen: Callable[..., Any],
) -> tuple[str, dict[str, int]]:
    request = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(
            {
                "model": model,
                "messages": messages,
                "max_completion_tokens": MAX_OUTPUT_TOKENS,
            }
        ).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=_TIMEOUT_S) as response:
        body = json.load(response)
    text = body["choices"][0]["message"]["content"].strip()
    return text, body.get("usage", {})


def _api_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        return json.load(exc)["error"]["message"]
    except Exception:  # noqa: BLE001
        return exc.reason


def _append_summary(env: Mapping[str, str], markdown: str) -> None:
    path = env.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a") as f:
            f.write(markdown + "\n")


def main(
    env: Mapping[str, str] = os.environ,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> int:
    model = env["ONCALL_MODEL"]
    pricing = Pricing(
        input_per_million=float(env["ONCALL_INPUT_PRICE_PER_M"]),
        output_per_million=float(env["ONCALL_OUTPUT_PRICE_PER_M"]),
    )
    runs_per_month = int(env["ONCALL_RUNS_PER_MONTH"])
    alert = env["ALERT_SUMMARY"]
    messages = build_messages(alert)

    prompt = " ".join(m["content"] for m in messages)
    per_call = estimate_call_cost(prompt, MAX_OUTPUT_TOKENS, pricing)
    monthly = per_call * runs_per_month
    estimate = (
        f"Estimated cost: ${per_call:.6f} per run, ${monthly:.4f}/month at "
        f"{runs_per_month} runs/month with {model} "
        f"(budget ${MONTHLY_BUDGET_USD:.2f}/month)"
    )
    print(estimate)
    _append_summary(env, f"## On-call diagnostic\n\n**Alert:** {alert}\n\n{estimate}\n")

    if monthly > MONTHLY_BUDGET_USD:
        message = (
            f"Estimated OpenAI spend ${monthly:.2f}/month exceeds the "
            f"${MONTHLY_BUDGET_USD:.2f}/month budget; skipping the diagnostic."
        )
        print(f"::warning title=On-call budget::{message}")
        _append_summary(env, f"> **Skipped:** {message}")
        return 0

    api_key = env.get("OPENAI_API_KEY", "")
    if not api_key:
        print("::error title=On-call::OPENAI_API_KEY is not set")
        return 1

    try:
        diagnostic, usage = call_openai(api_key, model, messages, urlopen)
    except urllib.error.HTTPError as exc:
        print(f"::error title=OpenAI API::HTTP {exc.code}: {_api_error_message(exc)}")
        return 1
    except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
        print(f"::error title=OpenAI API::{type(exc).__name__}: {exc}")
        return 1

    spent = f"Actual cost: ${actual_cost(usage, pricing):.6f} ({usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out tokens)"
    print(f"\nDiagnostic:\n{diagnostic}\n\n{spent}")
    _append_summary(env, f"### Diagnostic\n\n{diagnostic}\n\n{spent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
