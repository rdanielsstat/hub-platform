# On-Call Diagnostic

A small, read-only helper that asks an AI model for a quick first diagnosis of an alert. It's started by hand and doesn't change anything.

## What it does

Given a plain-text description of an alert, it makes one OpenAI API call (GPT-4o-mini by default) and returns a 2-3 sentence diagnosis: the most likely causes and the first thing to check or fix.

The model only sees the alert text you provide, plus a fixed note that Hub-Platform is a FastAPI backend on AWS Lambda with Postgres and OpenTelemetry.

## When it runs

Only when someone starts it. It's the GitHub Actions workflow `.github/workflows/observability-alert-handler.yml`, triggered by hand (`workflow_dispatch`). No Grafana alert or webhook starts it automatically.

## How to run it

1. In GitHub, open **Actions**, select **Observability alert handler**, and click **Run workflow**.
2. Fill in the two inputs:
   - **Alert to diagnose** (`alert_summary`): a description of the alert, for example which metric is high, by how much, and for how long.
   - **Expected runs per month** (`runs_per_month`): used only for the cost check below. Defaults to 30.
3. A reviewer approves the run. It uses the `observability-oncall` environment, so it waits for approval before it starts, and so before any OpenAI spend.

## What it needs

- The `OPENAI_API_KEY` secret, available to the workflow.
- A reviewer configured on the `observability-oncall` environment.
- Optional repository variables, to switch models: `ONCALL_OPENAI_MODEL`, `ONCALL_INPUT_PRICE_PER_M`, and `ONCALL_OUTPUT_PRICE_PER_M` (USD per 1M tokens). The defaults are `gpt-4o-mini`, 0.15, and 0.60.

It uses only the Python standard library, so the workflow installs nothing.

## What it outputs

Everything goes to the workflow run log and the run's job summary:

- The alert text it was given
- An estimated cost per run and per month
- The diagnosis
- The actual cost of the call, from the tokens used

## Cost guard

Before calling OpenAI, the script estimates the cost of one call and multiplies it by the expected runs per month. If that's over $5/month, it skips the call and posts a warning in the run instead. This is an estimate from a rough token count; it doesn't check real billing.

## What it does not do

- It doesn't query CloudWatch, Grafana, GitHub, the database, or any other system. It doesn't read logs, metrics, or code.
- It doesn't make changes, open issues, send notifications, commit, or push.
- It doesn't run on its own.

It's a diagnostic aid for a person, not an automated responder or fixer.

## Code

- `backend/oncall/diagnose.py`: the script (run as `python -m oncall.diagnose` from `backend/`)
- `backend/tests/test_oncall.py`: its tests
- `.github/workflows/observability-alert-handler.yml`: the workflow
