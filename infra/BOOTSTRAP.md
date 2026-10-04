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
cd infra/ci
tofu init
tofu apply          # prints ci_role_arn
```

Creates the GitHub OIDC provider and a role that only workflows on the `main`
branch of this repository can assume. No AWS access keys are ever stored in
GitHub.

Then configure the repo (no console clicking):

```bash
gh variable set AWS_ROLE_ARN --body "<ci_role_arn from above>"
gh secret set CLOUDFLARE_ZONE_ID   --body "bd3b8490fd5303e7f6996b70bdbfebd1"
gh secret set CLOUDFLARE_API_TOKEN --body "<token from infra/.env>"
gh secret set NEON_URLS --body '{"dev":{"pooled":"...","direct":"..."},"prod":{"pooled":"...","direct":"..."}}'
```

The workflows reference `environment: dev` and `environment: prod`, so create
both in the repository's Settings, Environments (or via `gh api`).

## Local `tofu` runs

`infra/.env` (gitignored) holds the Cloudflare token:

```bash
source infra/.env
cd infra/hub
tofu workspace select dev
tofu plan
```

## First deploy

```bash
cd infra/hub
tofu init -upgrade
tofu workspace select dev || tofu workspace new dev
tofu plan
```

Read the plan, then apply. After the first dev apply succeeds, every push to
`main` deploys dev itself (once every CI check passes), and production is
the `promote.yml` workflow in the Actions tab: a typed confirmation plus
a reviewer's approval in the `prod` environment (`ops/DEPLOYMENT.md`).
