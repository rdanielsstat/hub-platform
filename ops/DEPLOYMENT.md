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

The `integration` and `e2e` jobs also run on every push and PR, but don't
gate the deploy yet (see the comment in `ci.yml`). Once they've been
green on `main` for a while, add them to `deploy-dev`'s `needs`.

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
- [ ] Integration and E2E jobs are green for that commit.
- [ ] No open HIGH or CRITICAL dependency findings
      (`security/DEPENDENCIES.md`).
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

## The first deploy after the move to Alembic

Dev and prod Neon were created by `create_all()` and have no
`alembic_version` table. The first bootstrap that runs the new image
detects that, stamps the database at baseline revision `0001` (no
tables are created, altered or dropped, no rows are touched), and
prints `Pre-Alembic schema found: stamped at baseline revision 0001.`
The same run then applies `0002` (text length limits). Nothing to do by
hand, with one caveat: `0002` refuses to run if any existing row is
already longer than the new limits (it never truncates user data). The
API never limited these before, so on dev and prod check first, in the
Neon SQL editor:

```
SELECT
  (SELECT count(*) FROM projects WHERE length(name) > 256)          AS names,
  (SELECT count(*) FROM projects WHERE length(pitch) > 2000)        AS pitches,
  (SELECT count(*) FROM projects WHERE length(description) > 5000)  AS descriptions,
  (SELECT count(*) FROM projects WHERE length(next_action) > 1000)  AS next_actions,
  (SELECT count(*) FROM notes    WHERE length(body) > 10000)        AS notes;
```

All zeros: deploy. Otherwise the bootstrap fails with the same counts,
the job stops, and the old API keeps serving until the rows are dealt
with (`ops/TROUBLESHOOTING.md`). The same goes for a stamp refused over
a partial schema.

## Rolling back

There's no rollback workflow. Options, fastest first:

- **Backend only, prod**: re-run `tofu apply` on the prod workspace
  with the previous image tag (`-var=lambda_image_tag=<old tag>`). The
  previous tags stay in ECR (`aws_ecr_lifecycle_policy` keeps recent
  ones).
- **Frontend**: rebuild from the older commit and sync it to the bucket,
  then invalidate.
- **Revert on main**: `git revert`, push, let CI deploy dev, then
  promote.

Migrations don't roll back on their own. Alembic can downgrade
(`uv run alembic downgrade -1` against the database), but do that only
deliberately, after checking the migration's `downgrade()` won't drop
data you need.
