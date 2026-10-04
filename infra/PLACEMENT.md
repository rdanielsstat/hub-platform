# Where each file goes

Two OpenTofu roots, each with its own state file in the same S3 bucket.

Several file names appear in both folders and are DIFFERENT files. Check the
marker line before saving.

```
infra/
├── .env                       gitignored: export CLOUDFLARE_API_TOKEN=...
├── BOOTSTRAP.md
├── PLACEMENT.md               (this file)
├── bootstrap/                 GitHub OIDC trust. Applied once, by hand. No workspaces.
│   ├── backend.tf
│   ├── main.tf
│   └── providers.tf
└── hub/                       Everything else. Workspaces: dev | prod.
    ├── apigateway.tf
    ├── backend.tf
    ├── bootstrap.tf
    ├── certs.tf
    ├── database.tf
    ├── dns.tf
    ├── ecr.tf
    ├── frontend.tf
    ├── lambda.tf
    ├── main.tf
    ├── outputs.tf
    ├── providers.tf
    ├── terraform.tfvars        gitignored
    └── terraform.tfvars.example
```

`infra/shared/` is gone. There is no VPC and no Aurora. The database is Neon,
reached over the public internet with TLS.

## infra/bootstrap/   (3 files)

| File | Marker to identify it |
|---|---|
| `main.tf` | starts `# GitHub Actions OIDC trust`, contains `aws_iam_openid_connect_provider` |
| `providers.tf` | SHORT. aws only, no cloudflare, no us_east_1 alias, `Scope = "bootstrap"` |
| `backend.tf` | `key = "bootstrap/terraform.tfstate"` |

Nothing here is per-environment. Never run `tofu workspace` in this folder.

## infra/hub/   (14 files)

| File | Marker to identify it |
|---|---|
| `main.tf` | starts `variable "aws_region"`, contains `variable "neon_urls"` |
| `providers.tf` | LONG. aws + cloudflare + random, HAS the us_east_1 alias |
| `backend.tf` | `key = "hub/terraform.tfstate"` |
| `apigateway.tf` | no custom domain, no api mapping |
| `bootstrap.tf` | the schema bootstrap LAMBDA (runs the Alembic migrations), not the same thing as `infra/bootstrap/` |
| `certs.tf` | one certificate only (frontend) |
| `database.tf` | five SSM parameters (pooled and direct database URLs, JWT secret, origin-verify secret, demo password), no Secrets Manager |
| `dns.tf` | one Cloudflare record only |
| `ecr.tf` | `IMMUTABLE` tags, scan on push, two lifecycle rules |
| `frontend.tf` | two CloudFront origins, `aws_cloudfront_function`, the `/api/*` origin request policy, the security response headers policy (CSP, HSTS), S3 encryption |
| `lambda.tf` | no `vpc_config`, has `aws_cloudwatch_log_group`, sets `TRUSTED_PROXY_IPS` |
| `outputs.tf` | outputs `site_url`, `cloudfront_distribution_id`, `deployed_image_tag` |
| `terraform.tfvars.example` | has the `neon_urls` block |

## Same-name pairs, how to tell them apart

| Name | infra/bootstrap/ | infra/hub/ |
|---|---|---|
| `main.tf` | OIDC provider + CI role | variables + workspace locals |
| `providers.tf` | short, aws only | long, has cloudflare |
| `backend.tf` | `key = "bootstrap/..."` | `key = "hub/..."` |

The one that is not a pair: `infra/bootstrap/` is a DIRECTORY holding the
GitHub Actions trust role. `infra/hub/bootstrap.tf` is a FILE defining a
Lambda that applies the database migrations. They share no purpose.

## Outside infra/

```
.github/workflows/
├── ci.yml        push to main: test, build, push, deploy dev
└── promote.yml   manual: promote the dev image tag to prod
```
