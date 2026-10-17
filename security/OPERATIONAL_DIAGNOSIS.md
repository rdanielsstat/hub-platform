# Operational diagnosis

What the on-call agent did on each alert or drill, with a human review.
Since 2026-10-17 the agent wakes on its own: a Grafana alert reaches
`.github/workflows/observability-alert-handler.yml` through GitHub's
`repository_dispatch` API, `backend/oncall/alert.py` triages it,
`backend/oncall/diagnose.py` asks OpenAI for a diagnosis, and on dev
`.github/workflows/rollback-dev.yml` rolls back to the previous image. Add
a new section per run, newest first, below the runbook. The run sections
are a log and stay as written.

## Drill runbook: from alert to rollback, no human in the loop

A reusable check of the whole path on dev: the project creation alert
fires, the dispatch starts the agent, the agent rolls dev back to an
image from a different commit, the create-project probe passes and the
alert resolves. Dev only. Prod is never part of it: `FAULT_INJECT_5XX`
is ignored in prod by the app, refused outside dev by OpenTofu
(`guard_fault_inject`) and never passed by `promote.yml`.

The last drill passed on 2026-10-17: see
["2026-10-17: drill closed, automatic rollback proven on dev"](#2026-10-17-drill-closed-automatic-rollback-proven-on-dev).

### Prerequisites

- The alerting is in place (`infra/hub/grafana.tf`, applied by CI): the
  folder "Hub alerts", the rule groups "Project creation (dev)" and
  "Project creation (prod)", the contact point `hub-oncall-github-dispatch`
  and the notification policy.
- Dev has run at least two builds from different commits, so ECR holds an
  older image for the rollback to go back to (`rollback-dev.yml` picks the
  newest older image built from a different commit).
- Optional dispatch check with no fault: Alerting > Contact points >
  `hub-oncall-github-dispatch` > Test. GitHub should start an
  "Observability alert handler" run (event `repository_dispatch`) whose
  triage says `action=ignore` and which touches nothing. If no run
  appears, the contact point's last delivery error in Grafana says why: a
  `401` is the token, a `422` is the payload.

### Run it

1. Turn the fault on for dev only:

   ```bash
   gh variable set FAULT_INJECT_5XX --env dev --body true
   ```

2. Deploy dev with it: `gh workflow run ci.yml --ref main` (or re-run the
   `deploy-dev` job of the last CI run on `main`). Dev then runs a new tag
   with `FAULT_INJECT_5XX=true`.
3. Send project creation requests until the alert fires. With an account
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
   requests, so expect the alert to fire 2 to 4 minutes in.
4. Watch, without touching anything:
   - GitHub Actions starts "Observability alert handler" from
     `repository_dispatch`.
   - `triage` says `action=rollback`; `record` opens or reuses the issue
     "On-call: Project creation 5xx rate above 2% (dev)"; `diagnose`
     comments the OpenAI diagnosis on it.
   - `rollback` runs "Roll back dev": it picks the newest older image from
     a different commit, points the dev Lambdas at it, checks GET
     `/api/health`, and runs the create-project probe (sign-in as the demo
     account, create, delete). It comments the outcome on the issue; only
     a success counts toward the one rollback per incident.
   - The loop starts printing `201`: the rollback deployed without
     `FAULT_INJECT_5XX`.
   - About 5 minutes later Grafana sends a resolved notification, and a
     second run comments it on the issue with the `oncall:resolved`
     marker, which ends the incident.

### After the drill

5. Turn the fault off, so the next deploy doesn't bring it back:

   ```bash
   gh variable delete FAULT_INJECT_5XX --env dev
   gh variable list --env dev
   ```

   The list must show only `TRUSTED_PROXY_IPS`.
6. Close the tracking issue, and delete the drill projects from your
   account.
7. Record the run below, newest first: copy the table and fill in every
   row. Grafana's own firing time isn't in any GitHub log; write "not
   recorded" unless you took a screenshot.

### Record template

| Step | Time (UTC) | Evidence |
|---|---|---|
| Fault deployed to dev | | run URL, new tag |
| First `500` from POST /projects | | loop output |
| Alert firing in Grafana | not recorded | screenshot, if taken |
| Handler run started by `repository_dispatch` | | run URL |
| Tracking issue opened or reused, diagnosis posted | | issue URL |
| Rollback run: target tag (different commit) | | run URL, tags |
| Health 200 and probe passed | | rollback run log |
| First `201` after the rollback | | loop output |
| Alert resolved, `oncall:resolved` comment | | run URL |
| `FAULT_INJECT_5XX` removed from dev | | `gh variable list --env dev` |

## 2026-10-17: drill closed, automatic rollback proven on dev

| | |
|---|---|
| Type | **Drill.** `FAULT_INJECT_5XX` on dev made `POST /projects` answer 500; no real incident. |
| Tracking issue | [#23](https://github.com/rdanielsstat/hub-platform/issues/23) |
| Outcome | **Passed.** The alert woke the agent with no human action, the agent rolled dev back to an image built from a different commit, the create-project probe passed, and the alert resolved. |

### Timeline (UTC)

| Time | What happened | Evidence |
|---|---|---|
| 20:59:52 to 21:04:57 | Fault deploy: CI run by hand at `c70ef57` deployed dev as image `20261017-210226-c70ef57`, with `FAULT_INJECT_5XX` on | [CI run 39069048554](https://github.com/rdanielsstat/hub-platform/actions/runs/39069048554) |
| 21:07:33 | The alert's dispatch started the handler (`repository_dispatch`). Grafana's own firing time was not recorded separately | [handler run 39069607931](https://github.com/rdanielsstat/hub-platform/actions/runs/39069607931) |
| 21:07:57 | Diagnosis posted on #23 | issue #23 |
| 21:08:22 | Rollback target chosen: from `20261017-210226-c70ef57` to `20261017-205138-e18ee99`, an image built from a different commit (`e18ee99`) | run 39069607931, job `rollback / rollback` |
| 21:09:03 | GET /api/health returned 200 | same job |
| 21:09:17 | Probe passed: `POST /auth/login 200`, `POST /projects 201`, and the probe project deleted (`DELETE /projects/<probe> 204`) | same job |
| 21:09:18 | Rollback recorded on #23 as `outcome=success` | issue #23 |
| 21:09:21 | Handler run finished: success | run 39069607931 |
| 21:10:08 | `FAULT_INJECT_5XX` set to `false` on the dev environment (the variable was kept, not deleted) | dev environment variable |
| 21:12:57 | Grafana reported the alert resolved (back to Normal); recorded on #23 at 21:12:58 with the `oncall:resolved` marker | [handler run 39069963693](https://github.com/rdanielsstat/hub-platform/actions/runs/39069963693) |

### What the drills found, and the fix for each

| Failure | Fixed in |
|---|---|
| The rollback's apply failed: `rollback-dev.yml` didn't pass `grafana_default_contact_point` | [#24](https://github.com/rdanielsstat/hub-platform/pull/24) |
| A failed rollback counted toward the one rollback per incident, so the retries were refused | [#25](https://github.com/rdanielsstat/hub-platform/pull/25) |
| The rollback picked a rebuild of the same commit, and its health check couldn't see the fault; the create-project probe was added | [#26](https://github.com/rdanielsstat/hub-platform/pull/26) |
| The probe's sign-in got Cloudflare's 403 (error code 1010) because of Python's default User-Agent | [#28](https://github.com/rdanielsstat/hub-platform/pull/28) |

## 2026-10-17: drill, automatic path on dev (rollback did not complete)

| | |
|---|---|
| Type | **Drill.** `FAULT_INJECT_5XX` on dev made `POST /projects` answer 500; no real incident. |
| Tracking issue | [#23](https://github.com/rdanielsstat/hub-platform/issues/23), "On-call: Project creation 5xx rate above 2% (dev)" |
| Outcome | The alert fired and woke the agent with no human action, and the agent opened the issue and posted diagnoses. **The rollback never changed dev**: the first attempt failed, and a counter bug then blocked every retry. Dev recovered when the fault was turned off and dev was redeployed at `d869a39`. |
| Fixes | PR [#24](https://github.com/rdanielsstat/hub-platform/pull/24) (the missing variable); this change (the counter) |

### Timeline (UTC)

| Time | What happened | Evidence |
|---|---|---|
| 18:35 | CI run by hand (`workflow_dispatch`) at `1b3daad` deployed dev with `FAULT_INJECT_5XX` on, as image `20261017-183848-1b3daad` | [CI run 39058787616](https://github.com/rdanielsstat/hub-platform/actions/runs/39058787616) |
| 18:45:32 | The dev alert fired; Grafana's dispatch started the handler (`repository_dispatch`) with no human action. Triage: `action=rollback` | [handler run 39059505242](https://github.com/rdanielsstat/hub-platform/actions/runs/39059505242), attempt 1 |
| 18:45:46 | Issue #23 opened; diagnosis posted at 18:45:57 | issue #23 |
| 18:46:26 | **Rollback failed**: the targeted apply in `rollback-dev.yml` stopped with "No value for required variable" for `grafana_default_contact_point`, which the workflow didn't pass. Dev stayed on `20261017-183848-1b3daad` | attempt 1, job `rollback / rollback` |
| 18:46:27 | The failure was recorded on #23 with the same `<!-- oncall:rollback -->` marker a success would carry | issue #23 |
| 18:50:48 | Grafana reported the alert resolved; the handler recorded it | [handler run 39059872492](https://github.com/rdanielsstat/hub-platform/actions/runs/39059872492) |
| 18:52:55 | PR #24 merged (`d869a39`): `rollback-dev.yml` passes `TF_VAR_grafana_default_contact_point`. CI deployed dev at `d869a39` | [CI run 39060043473](https://github.com/rdanielsstat/hub-platform/actions/runs/39060043473) |
| 18:54:32 | Handler rerun (attempt 2). **Counter bug**: it counted the failed attempt's marker as a rollback and refused ("Still firing after a rollback ...", 18:54:49). The diagnosis it then posted still said "Next: rolling dev back" | [handler run 39059505242](https://github.com/rdanielsstat/hub-platform/actions/runs/39059505242), attempt 2 |
| 18:59:33 | The alert fired again; the handler refused again for the same reason (18:59:51) | [handler run 39060495270](https://github.com/rdanielsstat/hub-platform/actions/runs/39060495270) |
| before 19:01 | `FAULT_INJECT_5XX` turned off on the dev environment, by hand | |
| 19:01:34 | CI run by hand at `d869a39` redeployed dev with the fault off | [CI run 39060654192](https://github.com/rdanielsstat/hub-platform/actions/runs/39060654192) |
| 19:04:48 | Grafana reported the alert resolved; recorded on #23 | [handler run 39060867122](https://github.com/rdanielsstat/hub-platform/actions/runs/39060867122) |

### Human review

- **Worked:** the alert on user impact fired within minutes of the
  fault; the contact point's dispatch started the handler with no human
  action; triage picked `rollback` for dev; the issue, the diagnoses and
  both resolutions were recorded on #23.
- **Failed - missing variable:** `rollback-dev.yml` didn't pass
  `TF_VAR_grafana_default_contact_point`, a required `infra/hub` input
  added after the rollback workflow was written. Fixed in PR #24, after a
  check that it was the only required input missing.
- **Failed - counter bug:** `rollback-dev.yml` posted the
  `<!-- oncall:rollback -->` marker whatever the outcome, and the handler
  counted every comment with it. A failed attempt therefore used up the
  one rollback per incident, and the retries after PR #24 were refused.
  Fixed now: the outcome comment carries `outcome=success` or
  `outcome=failure`, only successes count (`backend/oncall/rollback_record.py`,
  with tests that a failure doesn't increment the count and a success
  does), and the diagnosis no longer promises a rollback the handler will
  skip. The bare marker on #23's failed attempt doesn't count either, so
  the thread needs no edit.
- **Not shown yet:** a successful automatic rollback. Dev recovered
  because a human turned the fault off and redeployed, not because of the
  agent. Run the drill again with both fixes merged and record it here.

**Note, added later:** the rerun's 19:35 rollback (run 39062983586)
reported success but chose `20261017-192115-98370fc`, a rebuild of the
same commit as the running `20261017-192835-98370fc`, so the fault
stayed on; its health check didn't send POST /projects, so it couldn't
tell. PR "fix(oncall): rollback target, fault probe and per-incident
allowance" fixes both: the rollback goes back to a different commit and
must create a project before it counts.

**Note, added later:** run 39067154127 rolled dev back to `1843165`, but
its probe failed on login with a 403: Cloudflare refused Python's
default User-Agent (error code 1010) before the request reached the app.
Run 39068305687 of probe-dev on main reproduced it. PR "fix(oncall):
named User-Agent for the rollback probe" fixes it.

### Data sent to OpenAI

The rule's summary annotation and the fixed system prompt, three times
(18:45, 18:54, 18:59). No logs, user data, credentials or database
contents.

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
