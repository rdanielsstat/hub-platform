# One-time setup

Three things have to exist before anything else works. Do them in this order,
once. Everything after that is `git push`.

## 1. State bucket (already done)

The S3 bucket holding OpenTofu state must exist BEFORE `tofu init`, because
the backend config points at it. This is the one standard exception to
"everything in code": you create the state store by hand, once, then
OpenTofu manages the rest.

Already created as `dnls-hub-tofu-state`. Recorded here for reproducibility:

```bash
export STATE_BUCKET="dnls-hub-tofu-state"
export AWS_REGION="us-east-1"

aws s3api create-bucket --bucket "$STATE_BUCKET" --region "$AWS_REGION"

aws s3api put-bucket-versioning --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api put-public-access-block --bucket "$STATE_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

All three roots (`ci/`, `hub/` dev, `hub/` prod) share this bucket under
different keys. Native S3 locking is on via `use_lockfile = true`, so there is
no DynamoDB table and no charge for one.

## 2. Neon projects (done by hand, on purpose)

Two projects in the Neon console, both **AWS US East 1 (N. Virginia)** to match
the Lambda, both **Postgres 17**, Postgres service only:

- `hub-dev`
- `hub-prod`

For each, click **Connect** in the left sidebar and copy two strings: one with
the Connection pooling toggle ON (hostname contains `-pooler`), one with it
OFF. Four strings total. They go in `infra/hub/terraform.tfvars` under
`neon_urls`, and into the `NEON_URLS` GitHub secret as JSON.

Free tier: 0.5 GB storage and 100 compute-hours per project per month, compute
scales to zero after 5 minutes idle and resumes in a few hundred milliseconds.

## 3. CI trust role

```bash
cd infra/bootstrap
tofu init
tofu apply          # prints ci_role_arn
```

Creates the GitHub OIDC provider and a role that jobs of this repository
running in the `dev` or `prod` deployment environment can assume (forks
and pull requests from forks get no OIDC token). No AWS access keys are
ever stored in GitHub. Limiting the environments to `main` (below) is
what keeps other branches from deploying.

Then configure the repo (no console clicking):

```bash
gh variable set AWS_ROLE_ARN --body "<ci_role_arn from above>"
gh secret set CLOUDFLARE_ZONE_ID   --body "bd3b8490fd5303e7f6996b70bdbfebd1"
gh secret set CLOUDFLARE_API_TOKEN --body "<token from infra/.env>"
gh secret set NEON_URLS --body '{"dev":{"pooled":"...","direct":"..."},"prod":{"pooled":"...","direct":"..."}}'
```

The workflows reference `environment: dev` and `environment: prod`, so create
both in the repository's Settings, Environments (or via `gh api`), and limit
each to the `main` branch (Deployment branches: "Selected branches", rule
`main`), since the AWS role trusts any job in those environments:

```bash
for env in dev prod; do
  gh api -X PUT repos/<owner>/<repo>/environments/$env \
    -F 'deployment_branch_policy[protected_branches]=false' \
    -F 'deployment_branch_policy[custom_branch_policies]=true'
  gh api -X POST repos/<owner>/<repo>/environments/$env/deployment-branch-policies \
    -f name=main -f type=branch
done
```

For `prod`, also add yourself as a required reviewer and a wait timer
(the PUT replaces the environment's settings, so include them in the same
call; `ops/DEPLOYMENT.md`, "Prod: promote.yml").

The rest of the repository configuration the workflows read, by name
(values never go in the repo):

| Name | Kind | Where | Used by |
|---|---|---|---|
| `AWS_ROLE_ARN` | variable | repo | every job that assumes the AWS role |
| `CLOUDFLARE_ZONE_ID`, `CLOUDFLARE_API_TOKEN`, `NEON_URLS`, `DEMO_PASSWORDS` | secrets | repo | OpenTofu (`ci.yml`, `promote.yml`, `rollback-dev.yml`) |
| `OTEL_EXPORTER_OTLP_ENDPOINT_DEV`, `OTEL_EXPORTER_OTLP_HEADERS_DEV` | secrets | `dev` environment | dev Lambda telemetry |
| `TF_VAR_OTEL_EXPORTER_OTLP_ENDPOINT_PROD`, `TF_VAR_OTEL_EXPORTER_OTLP_HEADERS_PROD` | secrets | `prod` environment | prod Lambda telemetry |
| `TRUSTED_PROXY_IPS` | variable | `dev` and `prod` environments | Cloudflare's ranges (`ops/DEPLOYMENT.md`); required, OpenTofu refuses an empty value |
| `GRAFANA_URL` | variable | repo | the Grafana provider (`infra/hub/grafana.tf`) |
| `GRAFANA_AUTH` | secret | repo | the Grafana provider's service account token |
| `GH_DISPATCH_TOKEN` | secret | repo | the alert contact point's call to GitHub's `repository_dispatch` API: a fine-grained token for this repository only, Contents read and write |
| `OPENAI_API_KEY` | secret | repo | the on-call agent's diagnosis |
| `FAULT_INJECT_5XX` | variable | `dev` environment only, unset normally | the on-call drill (`security/OPERATIONAL_DIAGNOSIS.md`) |

## Where OpenTofu runs: CI only

`infra/hub` is planned and applied only by GitHub Actions: `ci.yml`
(every push to `main`: dev), `promote.yml` (manual, approved: prod) and
`rollback-dev.yml` (the on-call agent, or by hand: dev). Don't run
`tofu plan` or `tofu apply` against the `dev` or `prod` workspace from a
laptop. A local run doesn't have the values CI passes, and with the
values missing, a plan describes a downgrade rather than the live
system.

What CI passes, and why:

- `lambda_image_tag`: the image tag CI just built and pushed (ci.yml),
  the tag dev runs (promote.yml) or the dev tag before it
  (rollback-dev.yml). Required, no default, and it must look like a CI
  build tag (`<yyyymmdd>-<hhmmss>-<sha>`): a run without it fails instead
  of pointing the Lambdas at an image nobody tested.
- `service_version`: SemVer from the nearest `vX.Y.Z` tag for the
  image's commit (`.github/scripts/service-version.sh`), reported on
  every trace and metric. Required, no default.
- `trusted_proxy_ips`: Cloudflare's IP ranges, from the
  `TRUSTED_PROXY_IPS` variable on the `dev` and `prod` GitHub
  environments. Required, and an empty value is refused: without it the
  login and sign-up limits would count per Cloudflare edge, not per user
  (`security/RATE_LIMITING.md`).
- `grafana_url` and `github_dispatch_token` (plus `GRAFANA_AUTH` for the
  provider): the alerting as code in `infra/hub/grafana.tf`.
- `fault_inject_5xx`: dev only, for the drill; false unless the dev
  environment's `FAULT_INJECT_5XX` variable says otherwise, and refused
  outside dev.
- The secrets and per-environment settings in the table above.

To see what a change will do: `tofu fmt` and `tofu validate` run on
every pull request (the `infra-check` job), and the dev deploy's apply
prints the plan it applies, in the run log. Changing infrastructure
means a pull request, like any other change.

## First deploy

Also CI. Once the steps above are done and the table's secrets and
variables are set, push to `main`: `deploy-dev` creates the dev ECR
repository first (a targeted apply), pushes the image into it, then
applies everything else, so a brand-new environment needs no local
apply. Production is created the same way by its first run of
`promote.yml` in the Actions tab: a typed confirmation plus a reviewer's
approval in the `prod` environment (`ops/DEPLOYMENT.md`).
