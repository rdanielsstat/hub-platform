# PR audit

Security review of the most recent change set to reach production. Add a
new section per audit, newest first.

## 2026-10-04: PR #5, and the direct commits ec830d6 and f34d327

| | |
|---|---|
| PR | [rdanielsstat/hub-platform#5](https://github.com/rdanielsstat/hub-platform/pull/5) "chore: update GitHub actions to Node.js 24-compatible versions" |
| PR commits | `b308f5f` (head), merged as `333e7f1` on 2026-10-03 03:01 UTC by rdanielsstat |
| Also audited | `ec830d6` (security headers, image and IaC fixes, SHA-pinned actions, OTLP logs, list limits, CI gating) and `f34d327` (Cloudflare Web Analytics in the CSP). Both were pushed directly to `main`, not through a PR, and are the latest changes live in prod. |
| CI | PR #5: test, integration, e2e, secrets-scan passed (run 37091593775); deploy-dev skipped, as on any PR. `ec830d6`: run 37159927021. `f34d327`: run 37160435822. All jobs passed. |
| Reviewed by | Claude Code (AI agent), 2026-10-04. The same agent wrote PR #5 and both commits, so this is a self-review; see "Sign-off". |

### PR #5: actions on Node.js 24 (3 workflow files, +23/-23)

What changed: every action in `ci.yml`, `promote.yml` and
`observability-alert-handler.yml` moved to its current major release
(checkout v7.0.1, setup-node v7.0.0, setup-python v7.0.0, setup-uv v10.2.0,
pnpm action-setup v6.1.0, configure-aws-credentials v6.3.0, setup-opentofu
v2.0.2, upload-artifact v7.0.1).

Security implications:

- **Positive: off a deprecated runtime.** Node.js 20 actions were being
  force-run on Node 24 with deprecation warnings; every action now targets
  Node 24.
- **Verified: inputs and permissions unchanged.** Each new version was
  checked to accept every input the workflows pass. No `permissions:`
  block changed: `ci.yml` and `promote.yml` keep `contents: read` and
  `id-token: write` (OIDC to AWS), the alert handler keeps `contents: read`.
- **Verified: checkout's credential handling.** checkout v7 keeps the
  GitHub token in a separate config file it removes at job end (visible in
  the post-job log: "Removing credentials config"), rather than in
  `.git/config`. No change to what later steps can read during the job.
- **Finding (fixed later): tags, not SHAs.** The PR pinned exact version
  tags (`@v7.0.1`), which a compromised upstream could move. Fixed in
  `ec830d6`: every action is now pinned to its commit SHA.

Result: **approve**.

### ec830d6: remaining hardening (39 files, +1245/-190)

| Change | Security implications | Verdict |
|---|---|---|
| CloudFront response headers policy: CSP, HSTS, X-Frame-Options, nosniff, Referrer-Policy | Blocks injected and third-party scripts, clickjacking and MIME sniffing; HSTS pins HTTPS for a year. `style-src 'unsafe-inline'` remains (React and Base UI set inline styles); it permits inline styles, not code. Verified on dev and prod: headers present, no CSP violations. | Approve |
| Theme script moved from inline to `public/theme-init.js` | Needed for `script-src 'self'` without hashes. Same code; still loads before paint. | Approve |
| Dockerfile: `dnf upgrade --releasever=latest`; pip removed from the image | Clears all 8 HIGH OS findings and every pip finding. Trade-off: builds are less reproducible (each build takes the latest AL2023 security updates); accepted, since images are scanned on push and tested in dev before promotion. | Approve |
| S3 SSE explicit; ECR tags immutable; `promote.yml` skips an already-present tag | Immutability guarantees dev and prod run the same bytes for a tag. The skip check compares only the tag; safe because a tag can no longer be repointed. Tag value comes from OpenTofu output, not user input, so no shell injection path. | Approve |
| Actions pinned to commit SHAs | Closes the moved-tag supply-chain risk for the OIDC-holding deploy job. | Approve |
| `deploy-dev` needs `integration` and `e2e` | A failing Postgres or browser test can no longer deploy. Verified: deploy started 2 s after e2e finished. | Approve |
| OTLP log export of `app.client_errors`, `app.db`, `app.security` | New data flow to Grafana Cloud: user id, user agent, page path, error text and stack, and source IPs of rejected direct calls. Disclosed in `security/DATA_POLICY.md`. Export uses the existing token; failures are logged and back off; nothing secret is logged. | Approve |
| New dependency `opentelemetry-instrumentation-logging` | Official OpenTelemetry package, same version line as the existing instrumentation; pip-audit clean. | Approve |
| Limits on tags, links and display name (API and migration `0003`) | Bounds storage per account; the migration refuses rather than truncates existing data. Verified on dev and prod: 0002 to 0003 applied. | Approve |
| `Store.create_user` only reports a real email clash as a duplicate | Fixes a misleading 409 for unrelated integrity errors. Doesn't widen any information leak: duplicate detection already existed. | Approve |

### f34d327: Cloudflare Web Analytics allowed in the CSP (4 files, +19/-8)

Cloudflare's proxy injects its analytics beacon into every page; the strict
CSP blocked it. Allowed: `script-src https://static.cloudflareinsights.com`,
`connect-src https://cloudflareinsights.com`.

Security implications: this trusts one more script origin, operated by
Cloudflare. Cloudflare already terminates TLS for the site, so it could
alter any page anyway; allowing its beacon adds no new party that can run
code in the page. The injected tag carries a Subresource Integrity hash.
The data collected is disclosed in `security/DATA_POLICY.md`. Verified on
dev and prod: the beacon loads (200) and the console has no CSP errors.

Result: **approve**.

### Findings from this audit

1. **`main` has no branch protection or ruleset** (checked 2026-10-04:
   `GET /branches/main/protection` returns 404, 0 rulesets). On a public
   repo this allows force-pushes (which could rewrite the history the
   gitleaks scan checks), branch deletion, and pushes that skip CI. PR #5
   was also merged with no review, and the two later commits bypassed PRs.
   Recommended minimum, which keeps the current direct-push workflow:
   block force-pushes and deletion of `main`. Stronger, if the workflow
   moves to PRs: require the CI checks to pass before merge. **Resolved
   2026-10-04:** the maintainer approved, and ruleset `protect-main`
   (id 24435773) now blocks force-pushes and deletion of `main`.
2. **Self-review.** The agent that wrote these changes also audited them.
   Every claim above links to CI runs or checks that were performed, but an
   independent reviewer would catch what the author can't. The QA subagent
   (`.claude/agents/qa-engineer.md`) or a human review is the remedy for
   future PRs.

### Sign-off

- Automated review: Claude Code, 2026-10-04. All three change sets
  approved; one repository-settings finding (branch protection).
- Maintainer sign-off: __________ (date) __________
