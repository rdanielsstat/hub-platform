# Operational diagnosis

Output of the on-call diagnostic (`backend/oncall/diagnose.py`, run by
`.github/workflows/observability-alert-handler.yml`), with a human review of
each diagnosis. Add a new section per run, newest first.

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
