# Image and infrastructure scans

Results of the container image scan (trivy) and the infrastructure-as-code
scans (tfsec, checkov), with the decision taken for every finding. Re-run
before each release and update the dates.

## How to run

```
# Image: scan what prod actually runs (needs Docker and AWS read access)
IMG=$(aws lambda get-function --function-name hub-prod-backend --query Code.ResolvedImageUri --output text)
aws ecr get-login-password | docker login --username AWS --password-stdin "${IMG%%/*}"
docker pull --platform linux/amd64 "$IMG"
trivy image --scanners vuln "$IMG"

# Or a local build of the current Dockerfile
docker build --platform linux/amd64 --target prod -t hub-backend:scan backend
trivy image --scanners vuln hub-backend:scan

# Infrastructure (from the repo root). Keep terraform.tfvars out of the
# scan: it holds real secrets, and scanners print code snippets.
tfsec infra/hub --exclude-path terraform.tfvars --minimum-severity HIGH
uvx checkov -d infra/hub --framework terraform --skip-path terraform.tfvars --compact
```

ECR also scans every pushed image (`scan_on_push = true`, `infra/hub/ecr.tf`);
results are in the ECR console per image.

## trivy: backend image (2026-10-03)

Scanned the image prod was running (`hub-prod-backend@sha256:002023d8...`,
tag `20261003-030302-333e7f1`), trivy 0.75.0.

| Severity | Count | Where |
|---|---|---|
| CRITICAL | 0 | |
| HIGH | 8 | Base image OS packages: `curl-minimal`, `libcurl-minimal` (CVE-2026-80230), `pcre2`, `pcre2-syntax` (CVE-2026-89161), `rpm`, `rpm-libs` (CVE-2026-78367, CVE-2026-84233). Fixed versions released. |
| MEDIUM | 12 | `libxml2` (7 CVEs, OS package), `pip` 25.0.1 from the base image (5 CVEs) |
| LOW | 1 | `pip` |
| UNKNOWN | 1 | `golang.org/x/sys` in `aws-lambda-rie` |

None was in the app's own dependencies (those are covered by pip-audit,
`security/DEPENDENCIES.md`).

**Action taken** (`backend/Dockerfile`, prod stage):

- `dnf upgrade -y --releasever=latest` on the AWS Lambda base image.
  Amazon Linux 2023 locks dnf to the image's release snapshot, so the
  `--releasever=latest` is what reaches fixes AWS has published since the
  base image was built. Fixes every OS finding.
- `pip uninstall -y pip` after the app's dependencies are installed. The
  function never runs pip. Upgrading it instead was tried first and
  traded the old pip's CVEs for HIGH findings in the copies of `urllib3`,
  `msgpack` and setuptools' `pkg_resources` that pip bundles in
  `pip/_vendor/` (newer pip publishes an SBOM listing them, which trivy
  reads). Removing pip removes all of it. The app's own `urllib3` is
  2.8.0, patched, and unaffected.

**Result after the fix** (local build of the updated Dockerfile): 0
CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. One UNKNOWN remains, accepted:
`golang.org/x/sys` v0.21.0 in `/usr/local/bin/aws-lambda-rie`
(CVE-2026-39824, an integer overflow in `NewNTUnicodeString`). That
binary is AWS's Runtime Interface Emulator, used only when the image is
run outside Lambda, and the affected function is Windows-only code; this
is a Linux image. It goes away when AWS rebuilds the emulator.

## tfsec: infra/hub (2026-10-03, HIGH and CRITICAL)

tfsec 1.28 (now maintained as part of trivy). No CRITICAL findings.

| Rule | Resource | Decision |
|---|---|---|
| AVD-AWS-0088 S3 bucket has no encryption configured | `aws_s3_bucket.frontend` | **Fixed**: explicit SSE-S3 (`aws_s3_bucket_server_side_encryption_configuration.frontend`). AWS already applied it by default; now it's in code. |
| AVD-AWS-0031 ECR tags are mutable | `aws_ecr_repository.backend` | **Fixed**: `image_tag_mutability = "IMMUTABLE"`. CI pushes a unique tag per build; `promote.yml` now skips the copy when prod already has the tag, since re-pushing an existing tag is refused. |
| AVD-AWS-0011 CloudFront has no WAF | `aws_cloudfront_distribution.frontend` | **Accepted**: Cloudflare proxies every request to the site (`proxied = true`, `infra/hub/dns.tf`) and provides WAF and DDoS mitigation at its edge; origin verification refuses anything that skips CloudFront; per-IP and per-account limits sit in the app (`security/RATE_LIMITING.md`). An AWS WAF would duplicate Cloudflare's at roughly $5 to $10 a month. Revisit if Cloudflare proxying is ever turned off. |
| AVD-AWS-0132 S3 not encrypted with a customer-managed KMS key | `aws_s3_bucket.frontend` | **Accepted**: the bucket holds only the public frontend build, served to anyone. A CMK adds cost and key-policy complexity and protects nothing here. |

## checkov: infra/hub (2026-10-03)

checkov 3.3, Terraform framework: 113 passed, 36 failed. checkov reports
no severities without a Prisma Cloud key, so each failure was triaged by
hand. Two overlap with tfsec and are fixed above (CKV_AWS_51 ECR tags; the
S3 encryption family partly). The rest:

| Checks | Resources | Decision |
|---|---|---|
| CKV_AWS_68, CKV2_AWS_47 CloudFront WAF / WAF Log4j rule | distribution | **Accepted**: see AVD-AWS-0011 above. Not a Java app. |
| CKV_AWS_145, CKV_AWS_136, CKV_AWS_158, CKV_AWS_337, CKV_AWS_173 KMS CMKs for S3, ECR, log groups, SSM parameters, Lambda environment | several | **Accepted**: all are encrypted at rest with AWS-managed keys already. SSM SecureStrings use the AWS-managed `aws/ssm` key, readable only by the roles that need them. Lambda environment variables hold parameter *names*, never secret values. CMKs ($1 a month each, plus key policies) would change who could decrypt only for principals inside this one-person account. |
| CKV_AWS_86, CKV_AWS_18, CKV_AWS_76 access logging (CloudFront, S3, API Gateway) | distribution, bucket, stage | **Accepted**: off on purpose. Request logs would store every visitor's IP address (`security/DATA_POLICY.md`); the app's own logs and traces cover incidents. |
| CKV_AWS_338 log retention at least 1 year | both log groups | **Accepted**: 14 days on purpose (cost, and data minimisation). |
| CKV_AWS_117 Lambda in a VPC | both functions | **Accepted**: nothing private to reach. Neon is reached over TLS on the public internet; a VPC would add a NAT gateway (~$30 a month) for no isolation gain. |
| CKV_AWS_116 Lambda dead-letter queue | both functions | **Not applicable**: both are invoked synchronously (API Gateway, the CI bootstrap call); a DLQ only applies to asynchronous invocations. |
| CKV_AWS_50 X-Ray tracing | both functions | **Accepted**: tracing is OpenTelemetry to Grafana Cloud (`ops/MONITORING.md`). |
| CKV_AWS_272 code signing | both functions | **Accepted**: images come only from this repo's ECR, pushed only by CI's OIDC role; tags are now immutable. |
| CKV_AWS_115 reserved concurrency | both functions | **Accepted**: discussed in `security/RATE_LIMITING.md` (would also cap legitimate traffic). API Gateway's stage throttle bounds load. |
| CKV_AWS_309 API Gateway routes without an authorizer | route | **Accepted**: authentication is in the app (JWT, `app/auth/`), and public routes (`/health`, `/auth/*`) must stay public. |
| CKV_AWS_21, CKV_AWS_144, CKV2_AWS_61, CKV2_AWS_62 S3 versioning, replication, lifecycle, event notifications | bucket | **Accepted**: the bucket is a build artifact, rebuilt from git on every deploy. |
| CKV_AWS_310 CloudFront origin failover | distribution | **Accepted**: single-region app by design. |
| CKV_AWS_374 CloudFront geo restriction | distribution | **Accepted**: the app is meant to be reachable everywhere. |

## Not scanned here

- `infra/bootstrap/` (the one-time GitHub OIDC trust root): small and
  applied by hand; scan it with the same commands when it changes.
- The frontend bundle: covered by `pnpm audit` (`security/DEPENDENCIES.md`).
