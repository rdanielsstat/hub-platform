# On-Call Agent

An agent that wakes up on a Grafana alert, diagnoses it with OpenAI, and on
dev fixes it by rolling back to the previous image, with no human in the
loop. On prod it diagnoses and records only.

## What it does

1. **Wakes up.** A Grafana alert rule fires; its contact point calls
   GitHub's `repository_dispatch` API with event type `grafana-alert`;
   GitHub starts `.github/workflows/observability-alert-handler.yml` on
   `main`. Nobody clicks anything.
2. **Triages** (`backend/oncall/alert.py`). It acts only on a firing (or
   resolved) alert from a rule labeled `hub_oncall="true"` for `dev` or
   `prod`. A payload that isn't JSON, misses a field, is a test
   notification or comes from any other rule is ignored: the run ends and
   touches nothing.
3. **Records** the incident on a GitHub issue ("On-call: <rule name>"),
   opened on the first firing and reused while it stays open.
4. **Diagnoses** (`backend/oncall/diagnose.py`): one OpenAI call
   (GPT-4o-mini by default, the `OPENAI_API_KEY` secret) for a 2 to 3
   sentence diagnosis, posted on the issue. The model sees the alert's
   summary and a fixed description of the stack, nothing else.
5. **Fixes dev** (`.github/workflows/rollback-dev.yml`): redeploys the
   previous dev image, checks GET `/api/health` returns 200, and comments
   the outcome on the issue. Once per incident: if the alert is still
   firing after a rollback, it says so on the issue and stops, for a human.
6. **Records the resolution** when Grafana sends the resolved notification.

Prod alerts get steps 1 to 4 and 6. Nothing an agent does deploys to prod;
a human promotes the fix with `promote.yml`.

## The alert

Defined as code in `infra/hub/grafana.tf`, applied by CI with the dev
workspace (the dev and prod environments share one Grafana stack):

- **Rules:** "Project creation 5xx rate above 2% (dev)" and "(prod)", in
  the folder "Hub alerts", group "Project creation"
- **What it measures:** real user impact on the key journey: the share of
  `POST /projects` requests answering 5xx, over a 5 minute window, from
  `projects_create_errors_total{http_status_code=~"5.."}` and
  `projects_create_total`, filtered by `hub_environment`
- **Fires when:** at least 10 requests in the window and more than 2% of
  them 5xx. A 409 or 422 is the user's input, not an outage, and doesn't
  count.
- **Evaluated:** every minute; no data counts as normal
- **Labels:** `hub_oncall="true"`, `hub_environment`, `severity="page"`,
  `journey="project_create"`
- **Contact point:** `hub-oncall-github-dispatch`, a webhook to
  `https://api.github.com/repos/rdanielsstat/hub-platform/dispatches`
  with a custom payload (`infra/hub/grafana/dispatch-payload.tmpl`):
  `{"event_type": "grafana-alert", "client_payload": {...}}`
- **Notification policy:** routes `hub_oncall="true"` to the contact
  point, grouped by rule and environment, repeating every 4 hours while
  firing

## Where the exception to "agents never deploy" ends

`AGENTS.md` says agents never deploy, and the Claude Code guard hook
(`agent-hooks/guard.py`) blocks every deploy command in an interactive
session. Neither changes. The on-call agent is not Claude Code: it's a
GitHub Actions workflow, and its one deploy path is scoped as tightly as
it can be:

- Only `rollback-dev.yml`, and only the `rollback` job, in the `dev`
  GitHub environment (which allows `main` only and has no reviewers).
- Only the dev workspace, and a targeted apply of the two dev Lambdas.
- Only to the image pushed just before the one running, and never across a
  database migration.
- At most once per incident.

`backend/tests/test_workflow_permissions.py` checks the scope: the job's
environment, that the workflow never names prod or promote, that it
selects only the dev workspace and that it targets only the two Lambdas.

## Run it by hand

- **Diagnosis only:** Actions > "Observability alert handler" > Run
  workflow, with an alert summary. This path still waits for a reviewer
  in the `observability-oncall` environment before any OpenAI spend, and
  never rolls back.
- **Rollback only:** Actions > "Roll back dev" > Run workflow, with a
  reason.

## What it needs

- Secrets: `OPENAI_API_KEY` (diagnosis), `GH_DISPATCH_TOKEN` (Grafana's
  call to GitHub, set into the contact point by OpenTofu), `GRAFANA_AUTH`
  (OpenTofu's Grafana provider), plus the deploy secrets `rollback-dev.yml`
  shares with `ci.yml`.
- Variables: `GRAFANA_URL` (repo), `TRUSTED_PROXY_IPS` (dev environment).
- Optional repository variables to switch models: `ONCALL_OPENAI_MODEL`,
  `ONCALL_INPUT_PRICE_PER_M` and `ONCALL_OUTPUT_PRICE_PER_M` (USD per 1M
  tokens). The defaults are `gpt-4o-mini`, 0.15 and 0.60.

The Python steps use only the standard library, so the workflow installs
nothing.

## Cost guard

Before calling OpenAI, the diagnosis estimates the cost of one call times
the expected runs per month (30 on the automatic path). Over $5/month it
skips the call and posts a warning instead. The rollback runs either way.

## Drills and past runs

The drill runbook (fault injection on dev with `FAULT_INJECT_5XX`, the
alert, the rollback and the resolution) and every recorded run are in
`security/OPERATIONAL_DIAGNOSIS.md`.

## Code

- `backend/oncall/alert.py`: triage; tests in `backend/tests/test_oncall_alert.py`
- `backend/oncall/diagnose.py`: diagnosis; tests in `backend/tests/test_oncall.py`
- `.github/workflows/observability-alert-handler.yml`: the agent
- `.github/workflows/rollback-dev.yml`: the dev rollback
- `infra/hub/grafana.tf`: the alert, contact point and policy
