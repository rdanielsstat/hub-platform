# Operational diagnosis

Output of the on-call diagnostic (`backend/oncall/diagnose.py`, run by
`.github/workflows/observability-alert-handler.yml`), with a human review of
each diagnosis. Add a new section per run, newest first.

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
