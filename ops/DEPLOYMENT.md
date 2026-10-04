# Deployment

How code gets to dev and prod, what each workflow does, and what to
check before and after. Infrastructure setup from scratch (OIDC trust,
state bucket, first apply) is in `infra/BOOTSTRAP.md`; this file assumes
it's done.

| Environment | URL | Deployed by | When |
|---|---|---|---|
| dev | https://hub-dev.dnls.dev | `.github/workflows/ci.yml` (`deploy-dev`) | Every push to `main`, after the unit tests and the gitleaks scan pass |
| prod | https://hub.dnls.dev | `.github/workflows/promote.yml` | By hand, with a typed confirmation and a reviewer's approval |

Nobody deploys from a laptop, and agents never deploy (`AGENTS.md`).

## Dev: every push to main

`ci.yml` runs on every pull request and push. On a push to `main`,
`deploy-dev` runs once `test` (backend and frontend unit tests) and
`secrets-scan` (gitleaks over the full history) pass:

1. Computes an image tag, `<UTC timestamp>-<short sha>`, unique per
   build, and `SERVICE_VERSION` from the nearest `vX.Y.Z` tag
   (`.github/scripts/service-version.sh`).
2. Creates the ECR repository if needed, builds the backend image
   (`docker build --target prod`) and pushes it.
3. Targeted `tofu apply -target=aws_lambda_function.bootstrap`: points
   only the bootstrap function at the new image (creating it, and what it
   depends on, on a first deploy).
4. Invokes the bootstrap Lambda, which applies any pending Alembic
   migrations to the dev Neon database (and creates the demo account if
   that environment has one and it doesn't exist). A migration failure
   fails the job here, before the API code or the frontend changes.
5. Full `tofu apply` on the `dev` workspace with the new image tag: the
   API Lambda switches to the new code, plus API Gateway, CloudFront, SSM
   parameters, DNS.
6. Builds the frontend with `VITE_API_BASE_URL=/api`, syncs it to the S3
   bucket, and invalidates CloudFront.
7. Smoke test: `GET /api/health` through the site URL until it returns
   200 (5 tries, 10 s apart).

`deploy-dev` waits for every check: `test`, `dependency-scan` (pip-audit
and pnpm audit; fails on HIGH and CRITICAL), `secrets-scan`, `integration`
(Postgres) and `e2e` (Playwright against Docker Compose).
Any failure means no deploy.

## Prod: promote.yml

Started from GitHub: **Actions > Promote to production > Run workflow**,
typing `promote` to confirm. The job runs in the `prod` GitHub
environment, so it then waits for a required reviewer's approval and a
wait timer. Once approved it:

1. Reads the image tag currently deployed in dev
   (`tofu output deployed_image_tag` in the dev workspace). Refuses if
   dev is on `latest`.
2. Derives `SERVICE_VERSION` from the commit that image was built from
   (the sha at the end of the tag), not from `main`'s current HEAD.
3. Copies that exact image from the dev ECR repository to the prod one.
   Same bytes, no rebuild.
4. Targeted apply of the prod bootstrap function with that tag.
5. Invokes it: migrations run against prod Neon, from the scripts baked
   into the promoted image. A failure stops here, with prod still on the
   old image.
6. Full `tofu apply` on the `prod` workspace with that tag: the API
   Lambda switches to the new code.
7. Builds the frontend **from the current `main` checkout** and deploys
   it to the prod bucket and distribution.
8. Smoke-tests `https://hub.dnls.dev/api/health`.

Note step 7: the backend is the image tested in dev, but the frontend is
rebuilt from `main` at promote time. If `main` has moved on since dev was
deployed, prod gets a newer frontend than the dev deploy you tested.
Promote right after a dev deploy, or check that `main` hasn't changed
since.

## Pre-deploy checklist (prod)

Before running `promote.yml`:

- [ ] The dev deploy for the commit you mean to ship succeeded, smoke
      test included.
- [ ] `main` hasn't moved since that dev deploy (see the frontend note
      above), or the extra commits are frontend-safe.
- [ ] You've used dev by hand: sign in, create a project, add a note,
      reload.
- [ ] If the release has a migration: the dev bootstrap log shows it
      applied (`Schema migrated from revision X to Y`), and the release
      tolerates the deploy order (below).
- [ ] Every CI check is green for that commit (they gate the dev
      deploy, so a successful dev deploy implies it): unit, dependency
      scan, gitleaks, integration, E2E.
- [ ] If the release adds a limit or constraint: the existing-data
      check below returns zeros on prod.
- [ ] For a tagged release, the tag is pushed (`release` skill), so
      `SERVICE_VERSION` is a clean `X.Y.Z`.

## Deploy order and migrations

Both workflows migrate **before** the API code switches:

1. `tofu apply -target=aws_lambda_function.bootstrap` with the new image
   tag. Only the bootstrap function (and anything it depends on) changes;
   the API Lambda keeps serving the old image.
2. Invoke the bootstrap: the migrations run. If one fails, the job stops
   here, nothing else is deployed, and the old API keeps running against
   the unchanged schema (on Postgres a failed migration rolls back).
3. Full `tofu apply`: the API Lambda switches to the new image, which
   finds the schema it expects already in place.

(Before 2026-10-02 the order was the reverse: the full apply, then the
bootstrap, so new code briefly ran against the old schema.)

What that means for writing migrations: for the seconds to a minute
between steps 2 and 3, the **old** code runs against the **new** schema.
So migrations must stay compatible with the code that's still running:

- Additive changes (new tables, nullable or defaulted columns, new
  indexes) are safe.
- New constraints are safe as long as the old code can't write values
  that break them. `0002`'s length limits qualify: the old code had no
  limits, but a write that long in that window would just fail.
- Renames and drops need the old code gone first: ship the code that no
  longer uses the column, then drop it in a later release.

The targeted apply prints OpenTofu's usual warning about `-target`
being for exceptional use; it's expected here. The full apply right
after brings everything else in line.

## Migrations that add limits: check existing data first

A migration that adds a limit (`0002`, `0003`) refuses to run over rows
that already exceed it, rather than truncating anyone's data, and the
deploy stops at the bootstrap with the counts, before any code changes
(`ops/TROUBLESHOOTING.md`). Before promoting one, run the matching check
in the Neon SQL editor. For the current limits:

```
SELECT
  (SELECT count(*) FROM projects WHERE length(name) > 256)            AS names,
  (SELECT count(*) FROM projects WHERE length(pitch) > 2000)          AS pitches,
  (SELECT count(*) FROM projects WHERE length(description) > 5000)    AS descriptions,
  (SELECT count(*) FROM projects WHERE length(next_action) > 1000)    AS next_actions,
  (SELECT count(*) FROM notes    WHERE length(body) > 10000)          AS notes,
  (SELECT count(*) FROM users    WHERE length(display_name) > 100)    AS display_names,
  (SELECT count(*) FROM projects WHERE json_array_length(tags) > 50)  AS tag_lists,
  (SELECT count(*) FROM projects WHERE json_array_length(links) > 50) AS link_lists;
```

All zeros: deploy.

## Security headers

CloudFront adds CSP, HSTS (one year, includeSubDomains, preload),
`X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff` and
`Referrer-Policy` to every response (`infra/hub/frontend.tf`). Check
after a deploy:

```
curl -sI https://hub-dev.dnls.dev/ | grep -iE "content-security|strict-transport|x-frame|x-content-type|referrer"
```

The CSP allows scripts from the site itself only (no inline scripts),
plus Cloudflare's Web Analytics beacon, which Cloudflare's proxy injects;
styles and fonts from the site and Google Fonts; and API calls to the
same origin, plus the beacon's report endpoint. A change that loads anything from another origin must add
it to `local.content_security_policy`, or browsers block it.

## Trusted proxies: Cloudflare's IP ranges

Cloudflare proxies the site, so the per-IP rate limits need to know
Cloudflare's addresses to find the real client
(`security/RATE_LIMITING.md`). The app reads them from
`TRUSTED_PROXY_IPS`, which comes from the OpenTofu variable
`trusted_proxy_ips`, which both workflows fill from a **GitHub
environment variable** named `TRUSTED_PROXY_IPS` (on the `dev` and
`prod` environments). Unset or empty means trust no proxy: the
behaviour before this setting existed.

Get the current ranges (Cloudflare publishes them as plain text, one
CIDR per line) as one comma-separated line:

```
{ curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6; } \
  | grep -v '^$' | paste -sd, -
```

(The same lists are at https://www.cloudflare.com/ips/ and, as JSON,
from `https://api.cloudflare.com/client/v4/ips`.) Then set the variable
on each environment, with the GitHub UI (**Settings > Environments >
dev / prod > Environment variables**) or the CLI:

```
RANGES=$({ curl -fsS https://www.cloudflare.com/ips-v4; echo; curl -fsS https://www.cloudflare.com/ips-v6; } | grep -v '^$' | paste -sd, -)
gh variable set TRUSTED_PROXY_IPS --env dev  --body "$RANGES"
gh variable set TRUSTED_PROXY_IPS --env prod --body "$RANGES"
```

It takes effect on the next deploy (a push to `main` for dev, a promote
for prod). A malformed entry stops the Lambda from starting (the app
validates the list at import), so the deploy's smoke test fails rather
than the limit silently doing the wrong thing.

Verify after the dev deploy, from two different networks (for example
home Wi-Fi and a phone hotspot): six failed logins on dev from the
first get `429` on the sixth; one failed login from the second right
after should get `401`, not `429`. If the second also gets `429`, the
user's address isn't arriving in `X-Forwarded-For`; check the request
headers the Lambda receives (CloudFront normally appends the viewer to
`X-Forwarded-For` on its own, but if not, it has to be added to the
`/api/*` origin request policy in `infra/hub/frontend.tf`).

Status: set on the `dev` and `prod` environments (2026-10-03), deployed
to both, and verified from two networks (2026-10-04): the second network
got `401`, not `429`.

Cloudflare changes these ranges rarely and announces it in advance.
Re-run the command when it does, or every few months, and update both
variables.

## After deploying

- `curl -s https://hub.dnls.dev/api/health` returns `{"status":"ok"}`.
- Sign in on the site and load the dashboard (exercises the database).
- Check the bootstrap output in the job log. Every deploy prints either
  `Schema already at head (revision N).` or
  `Schema migrated from revision X to Y.`
- Watch error rates in Grafana for a few minutes (`ops/MONITORING.md`).

## Migration history

| Revision | What | Dev | Prod |
|---|---|---|---|
| `0001` | Baseline: the old `create_all()` schema. Existing databases were stamped, not recreated (`Pre-Alembic schema found: stamped at baseline revision 0001.`) | 2026-10-03 | 2026-10-03 |
| `0002` | CHECK constraints: project text lengths, note body length | 2026-10-03 | 2026-10-03 |
| `0003` | CHECK constraints: display name length, tag and link counts | 2026-10-03 | 2026-10-03 |

Both databases are at `0003`. Every deploy's bootstrap log says
`Schema already at head (revision N).` or
`Schema migrated from revision X to Y.`

## Backup Testing

Backups are Neon's point-in-time restore (PITR): Neon keeps the write-ahead
log for the project's history window and can create a new branch showing
the database exactly as it was at any moment inside it. There are no
separate dump files.

**History window: 6 hours** on the current Neon free plan
(`history_retention_seconds = 21600` on both `hub-dev` and `hub-prod`).
A restore further back than that isn't possible; a longer window needs a
paid Neon plan.

### Test on 2026-10-04 (prod): pass

Restored prod (`hub-prod`, project `soft-frost-13927168`, branch
`production`) to **2026-10-03 23:30:00 UTC**, four minutes before the
prod bootstrap ran migration `0003` (23:34:03 UTC). A point-in-time
restore must therefore show the schema at `0002`, which current prod no
longer is: a check a plain copy of prod would fail.

| | Prod (now) | Restored to 23:30 UTC |
|---|---|---|
| users | 2 | 2 |
| projects | 10 | 10 |
| notes | 19 | 19 |
| Alembic revision | `0003` | **`0002`** |
| `0003` constraints | 3 | **0** |
| `0002` constraints | 5 | 5 |
| Newest user update / note | 2026-10-02 01:42 / 2026-10-01 05:39 | same |

Result: the restore reproduced the database as of the requested moment,
schema included. Row counts match because nothing was written to prod
between the restore point and the test (the newest rows are from
2026-10-01 and 2026-10-02). Neon reported the branch's point as
15:00:41 UTC: it resolves the requested time to the log position at that
moment and reports the last commit before it; nothing was written in
between. The test branch (read-only endpoint) was deleted afterwards;
only `production` remains.

### How to repeat it

With a Neon API key (`NEON_API_KEY`) and `jq`:

```
N=https://console.neon.tech/api/v2; A="Authorization: Bearer $NEON_API_KEY"
P=<project id>; B=<production branch id>; T=2026-10-03T23:30:00Z   # inside the history window
# 1. Branch from the point in time, with a read-only compute
curl -s -X POST -H "$A" -H 'Content-Type: application/json' "$N/projects/$P/branches" \
  -d "{\"branch\":{\"parent_id\":\"$B\",\"parent_timestamp\":\"$T\",\"name\":\"restore-test\"},\"endpoints\":[{\"type\":\"read_only\"}]}"
# 2. Connection URI for the new branch (contains a password: don't log it)
curl -s -H "$A" "$N/projects/$P/connection_uri?branch_id=<new branch id>&database_name=neondb&role_name=neondb_owner&pooled=false" | jq -r .uri
# 3. Compare with prod: counts of users, projects, notes; SELECT version_num FROM alembic_version
# 4. Delete the test branch (never the production branch)
curl -s -X DELETE -H "$A" "$N/projects/$P/branches/<new branch id>"
```

Pick a restore point just before a known change (a deploy's migration,
from the bootstrap log), so the result proves it's point-in-time and not
a copy of the current state. To actually restore after an incident,
restore the `production` branch itself from the Neon console (Branches,
Restore), which keeps a backup of the pre-restore state, or point the
SSM database URLs at a restored branch; either is a manual,
maintainer-only operation.

Run this test after any change to the Neon plan or project, and at least
before each prod promotion that includes a migration.

## Rolling back

There's no rollback workflow. Options, fastest first:

- **Backend only, prod**: re-run `tofu apply` on the prod workspace
  with the previous image tag (`-var=lambda_image_tag=<old tag>`). The
  previous tags stay in ECR (`aws_ecr_lifecycle_policy` keeps the 10
  newest images; tags are immutable, so a tag always names the same
  image). Older code runs fine on the newer schema as long as migrations
  stay additive (see "Deploy order and migrations").
- **Frontend**: rebuild from the older commit and sync it to the bucket,
  then invalidate.
- **Revert on main**: `git revert`, push, let CI deploy dev, then
  promote.

Migrations don't roll back on their own. Alembic can downgrade
(`uv run alembic downgrade -1` against the database), but do that only
deliberately, after checking the migration's `downgrade()` won't drop
data you need.
