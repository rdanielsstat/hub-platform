# Operational diagnosis

What the on-call agent did on each alert or drill, with a human review.
Since 2026-10-17 the agent wakes on its own: a Grafana alert reaches
`.github/workflows/observability-alert-handler.yml` through GitHub's
`repository_dispatch` API, `backend/oncall/alert.py` triages it,
`backend/oncall/diagnose.py` asks OpenAI for a diagnosis, and on dev
`.github/workflows/rollback-dev.yml` rolls back to the previous image. Add
a new section per run, newest first, below the runbook.

## Drill runbook: from alert to rollback, no human in the loop

Proves the whole path on dev: the project creation alert fires, the
dispatch starts the agent, the agent rolls dev back, the health check
returns 200 and the alert resolves. Dev only. Prod is never part of it:
`FAULT_INJECT_5XX` is ignored in prod by the app, refused outside dev by
OpenTofu (`guard_fault_inject`) and never passed by `promote.yml`.

### Before the drill (once)

1. Merge the change that adds the alerting as code and wait for the
   `deploy-dev` job of CI to pass. It creates, in the Grafana stack: the
   folder "Hub alerts", the rule group "Project creation" (one rule for
   dev, one for prod), the contact point `hub-oncall-github-dispatch` and
   the notification policy.
2. In Grafana (Alerting > Alert rules), delete the old hand-made rule
   "Registration Error Rate > 10%" (rule ID `cfzugswaau0hsf`). It counted
   409 and 422 answers as errors, and the new policy would now send it to
   the dispatch contact point. The agent would ignore it (no
   `hub_oncall` label), but each firing would still start a run.
3. Test the dispatch with no fault: Alerting > Contact points >
   `hub-oncall-github-dispatch` > Test. GitHub should start an
   "Observability alert handler" run (event `repository_dispatch`) whose
   triage says `action=ignore` (a test alert has no `hub_oncall` label) and
   which touches nothing. That proves the URL, the token and the payload
   format. If no run appears, check the contact point's last delivery error
   in Grafana: a `401` is the token, a `422` is the payload.
4. Note the tag dev runs now (the good image): the last `deploy-dev` run's
   "Compute image tag and version" step prints it.

### The drill

5. Turn the fault on for dev only:

   ```bash
   gh variable set FAULT_INJECT_5XX --env dev --body true
   ```

6. Deploy dev with it. Re-run the `deploy-dev` job of the last successful
   CI run on `main` (Actions > CI > the run > Re-run jobs > `deploy-dev`).
   That builds a new image from the same commit, so dev now runs a new
   tag with `FAULT_INJECT_5XX=true`, and the good image is the one just
   before it in ECR.
7. Send project creation requests until the alert fires. With an account
   of your own on dev (not the shared demo account), from a shell:

   ```bash
   DEV=https://hub-dev.dnls.dev
   JAR=$(mktemp)
   read -rp "Dev account email: " EMAIL
   read -rsp "Password: " PASS; echo
   curl -s -c "$JAR" -H "Origin: $DEV" -o /dev/null -w 'login %{http_code}\n' \
     --data-urlencode "username=$EMAIL" --data-urlencode "password=$PASS" \
     "$DEV/api/auth/login"
   for i in $(seq 1 30); do
     curl -s -b "$JAR" -H "Origin: $DEV" -H 'Content-Type: application/json' \
       -o /dev/null -w "$(date -u +%H:%M:%S) POST /projects %{http_code}\n" \
       -d "{\"name\": \"drill $i\"}" "$DEV/api/projects"
     sleep 10
   done
   ```

   Every request should print `500`. The rule needs at least 10 requests
   in 5 minutes, and metrics reach Grafana about a minute after the
   requests, so expect the alert to fire 2 to 4 minutes in (Alerting >
   Alert rules > "Project creation 5xx rate above 2% (dev)" turns Firing).
8. Watch, without touching anything:
   - GitHub Actions starts "Observability alert handler" from
     `repository_dispatch`.
   - `triage` says `action=rollback`; `record` opens the issue "On-call:
     Project creation 5xx rate above 2% (dev)"; `diagnose` comments the
     OpenAI diagnosis on it.
   - `rollback` runs "Roll back dev": it finds the previous tag (the good
     image from step 4), points the dev Lambdas at it, and GET
     `/api/health` returns 200. It comments the outcome on the issue.
   - The loop above starts printing `201`: the previous image runs, and the
     rollback deployed without `FAULT_INJECT_5XX`.
   - About 5 minutes later the 5xx share drops below 2%, Grafana sends a
     resolved notification, and a second run comments "Resolved" on the
     issue.

### After the drill

9. Turn the fault off, so the next deploy doesn't bring it back:

   ```bash
   gh variable delete FAULT_INJECT_5XX --env dev
   gh variable list --env dev
   ```

   The list must show only `TRUSTED_PROXY_IPS`. The dev Lambda is already
   free of it (the rollback deployed without it); the next push to `main`
   deploys normally.
10. Confirm a project can be created on dev (the app, or one `201` from
    the loop), close the tracking issue, and delete the drill projects.
11. Record the run below: copy the table, fill in every row, and add the
    issue link and screenshots of the firing alert and the issue thread.

### Record template

| Step | Time (UTC) | Evidence |
|---|---|---|
| Fault deployed to dev (`deploy-dev` re-run) | | run URL, new tag |
| First `500` from POST /projects | | loop output |
| Alert firing in Grafana | | screenshot |
| Handler run started by `repository_dispatch` | | run URL |
| Tracking issue opened, diagnosis posted | | issue URL |
| Rollback run: previous tag deployed | | run URL, tag |
| GET /api/health returned 200 | | rollback run log |
| First `201` after the rollback | | loop output |
| Alert resolved, "Resolved" comment | | run URL, screenshot |
| `FAULT_INJECT_5XX` removed from dev | | `gh variable list --env dev` |

## 2026-10-04: drill, client error spike from database outages on dev

| | |
|---|---|
| Run | [Actions run 37164038288](https://github.com/rdanielsstat/hub-platform/actions/runs/37164038288), 2026-10-04 00:09 UTC, `success` |
| Approval | `observability-oncall` environment, approved via the API on the repo owner's explicit pre-approval of this paid run |
| Model | `gpt-4o-mini` (repository default) |
| Cost | Estimated $0.000210 per run ($0.0063/month at 30 runs); actual $0.000095 (208 input, 106 output tokens). Budget guard: $5.00/month |
| Type | **Drill.** The alert below was written to exercise the diagnostic against the failure mode added this week; no real incident occurred. |

### Alert given to the diagnostic

> DRILL (2026-10-04, recorded for security/OPERATIONAL_DIAGNOSIS.md): on
> hub-dev, client_errors_post_total rose from ~0 to 40 per minute for 10
> minutes. Loki shows the reports are kind=http, status=503, endpoint GET
> /api/auth/me and GET /api/projects. The backend logs app.db
> 'database_unavailable error=OperationalError' warnings at the same time,
> and auth_me_get_latency_ms p95 rose to 9 seconds. Neon is the database
> (scale-to-zero after 5 minutes idle); the Lambda pool uses
> pool_pre_ping.

### Diagnosis returned (verbatim)

> The spike in `client_errors_post_total` to 40 per minute, coupled with
> `database_unavailable error=OperationalError` logs and increased latency
> for auth requests, suggests the database (Neon) is not available, likely
> due to it being scaled to zero after a period of inactivity. To resolve
> this, first check if the database has indeed transitioned to a "sleep"
> state and confirm any settings for connectionl handling in the
> application. Consider adjusting the scaling policy to ensure the
> database remains active during periods of anticipated demand.

### Human review of the diagnosis

- **Right:** it correlated the three signals (client error spike, `app.db`
  warnings, latency) to a single cause, the database, and pointed at the
  Neon compute state first. That's the correct first check
  (`ops/TROUBLESHOOTING.md`, "First request after idle is slow").
- **Incomplete:** a scale-to-zero resume normally adds well under a second
  and then succeeds; it doesn't produce ten minutes of `OperationalError`.
  Sustained 503s with a 9-second p95 point more to Neon being unreachable
  or failing to resume (a Neon incident, compute quota exhausted on the
  free plan, or wrong connection settings after a change) than to ordinary
  cold starts. The diagnostic didn't distinguish the two.
- **Missing next steps** a responder would want: the Neon console's
  compute state and project quota; the Neon status page; whether the
  outage started with a deploy (bootstrap logs, `ops/DEPLOYMENT.md`); and
  confirming in Loki that users saw "Can't reach the server" and were not
  signed out (the expected behaviour since 2026-10-02).
- **Remediation advice:** "adjust the scaling policy" (raise the suspend
  timeout or disable scale-to-zero) is valid for slow first requests, at a
  cost, and is listed in `ops/TROUBLESHOOTING.md`. It wouldn't fix an
  outage.
- One typo in the model output ("connectionl"), kept verbatim above.

### What this run shows about the tool

- The workflow works end to end: manual start, environment approval gate,
  spend estimate before the call, one call, output in the job log and
  summary.
- Useful as a first-pass triage note; not a substitute for the runbook.
  The diagnosis quality is bounded by the alert text: it sees only what the
  alert says, by design (no access to logs or data; see
  `security/AGENT_SECURITY.md`).
- Cost is negligible ($0.0001 a run), so it can run on every alert.

### Data sent to OpenAI

The alert text above and the fixed system prompt describing the stack. No
logs, user data, credentials or database contents
(`security/DATA_POLICY.md`).
