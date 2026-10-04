# On-Call Diagnostic

A small, read-only helper that asks an AI model for a quick first diagnosis of an alert. The on-call person starts it after a Grafana alert, and it runs once a reviewer approves.

## What it does

Given a plain-text description of an alert, it makes one OpenAI API call (GPT-4o-mini by default) and returns a 2-3 sentence diagnosis: the most likely causes and the first thing to check or fix.

The model only sees the alert text you provide, plus a fixed note that Hub-Platform is a FastAPI backend on AWS Lambda with Postgres and OpenTelemetry.

## When it runs

The diagnostic is the GitHub Actions workflow `.github/workflows/observability-alert-handler.yml`. The on-call person starts it after a Grafana alert, and a reviewer approves each run before it does anything.

### Alert rule

A Grafana-managed alert rule in the project's Grafana Cloud stack watches the registration error rate in the dev environment, which is the environment that sends metrics to Grafana Cloud.

- **Rule:** Registration Error Rate > 10% (rule ID `cfzugswaau0hsf`)
- **Query:** `(rate(auth_register_post_errors_total[5m]) / rate(auth_register_post_total[5m])) * 100`, the percentage of `POST /auth/register` requests that returned an error (4xx or 5xx) over the last 5 minutes. That includes 409 (email already registered) and 422 (invalid input), not only server errors.
- **Condition:** above 10
- **Evaluated:** every minute
- **Pending period:** 5 minutes, so it fires once the error rate has stayed above 10% for 5 minutes
- **No data:** treated as normal
- **Contact point:** `github-workflow`
- **Summary:** "Registration error rate exceeded 10% for 5 minutes"

The alert links to a dashboard panel showing the error-rate trend.

### From alert to diagnosis

1. The rule fires in Grafana.
2. The `github-workflow` contact point's webhook notifies the on-call person.
3. They start the workflow by hand in GitHub Actions, pasting in the alert summary. The run waits for approval in the `observability-oncall` environment.
4. A reviewer approves the run in GitHub Actions.
5. The diagnostic runs and writes its diagnosis to the run log and job summary.

## Run it by hand

To diagnose an alert yourself, or to test the workflow:

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

## Example run

A recorded drill (2026-10-04, run 37164038288): the alert text, the
diagnosis verbatim, the cost ($0.000095), and a human review of what the
diagnosis got right and missed, in `security/OPERATIONAL_DIAGNOSIS.md`.

## Cost guard

Before calling OpenAI, the script estimates the cost of one call and multiplies it by the expected runs per month. If that's over $5/month, it skips the call and posts a warning in the run instead. This is an estimate from a rough token count; it doesn't check real billing.

## Code

- `backend/oncall/diagnose.py`: the script (run as `python -m oncall.diagnose` from `backend/`)
- `backend/tests/test_oncall.py`: its tests
- `.github/workflows/observability-alert-handler.yml`: the workflow
