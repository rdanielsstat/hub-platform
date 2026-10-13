# Image and infrastructure scans

Results of the container image scans (trivy) and the infrastructure-as-code
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
trivy config backend/Dockerfile

# The local Compose frontend image (nginx), and its Dockerfile
docker compose build frontend
trivy image --scanners vuln hub-platform-frontend:latest
trivy config frontend/Dockerfile

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
CRITICAL, 0 HIGH, 0 MEDIUM, 0 LOW. One UNKNOWN remained in
`/usr/local/bin/aws-lambda-rie` (`golang.org/x/sys` v0.21.0,
CVE-2026-39824). It was accepted on 2026-10-03; that acceptance is
superseded by the 2026-10-13 rescan below, which removed the binary.

**Confirmed on prod (2026-10-04):** the image prod runs,
`hub-prod-backend:20261003-230501-f34d327` (built by CI from the patched
Dockerfile), scanned by digest: no findings in the OS packages or Python
packages; the same single UNKNOWN in `aws-lambda-rie`.

## trivy: backend image, rescan (2026-10-13)

A local build of the prod stage (`linux/amd64`, trivy 0.75.0), in the
security sweep of 2026-10-13: 14 findings, every one in
`/usr/local/bin/aws-lambda-rie`, the AWS Lambda Runtime Interface
Emulator that the base image ships. Its Go standard library is v1.26.7
(fixed in 1.26.9 and 1.27.2):

| Severity | Count | Findings |
|---|---|---|
| CRITICAL | 0 | |
| HIGH | 3 | CVE-2026-78667 (`net/http` Range header DoS), CVE-2026-78669 (`net/http` HTTP/2), CVE-2026-97031 (`crypto/tls` ECH DoS) |
| MEDIUM | 5 | CVE-2026-56866 (`net/http` response desync), CVE-2026-78663 and CVE-2026-97032 (HTTP/2), CVE-2026-94439 (request smuggling), CVE-2026-94448 (`html/template` XSS) |
| LOW | 1 | CVE-2026-56857 (`os`, Windows junctions) |
| UNKNOWN | 5 | `golang.org/x/sys` CVE-2026-39824 and Go standard library items, including CVE-2026-78659 |

None was reachable in Lambda: the base image's `/lambda-entrypoint.sh`
runs the emulator only when `AWS_LAMBDA_RUNTIME_API` is unset, that is,
outside Lambda; in Lambda it runs `/var/runtime/bootstrap` directly.

**Action taken** (`backend/Dockerfile`, prod stage):
`RUN rm -f /usr/local/bin/aws-lambda-rie`. Local runs use the `dev`
stage (Docker Compose), never this one, so nothing here needs the
emulator; to run the prod image locally, mount one in, as below.

**Result after the fix:** `trivy image --scanners vuln`: 0 findings at
any severity. Verified the image still serves the handler: built for
`linux/amd64` (as deployed) and `linux/arm64`, then run with AWS's own
emulator mounted from the official base image
(`-v .../aws-lambda-rie:/aws-lambda-rie --entrypoint /aws-lambda-rie
... /var/runtime/bootstrap app.lambda_handler.handler`) and invoked with
an API Gateway v2 event for `GET /api/health`: `200 {"status":"ok"}` on
both, through the real `/var/runtime/bootstrap`. A regression test
(`backend/tests/test_dockerfile.py`) checks the prod stage keeps
removing it. `security/REMEDIATION_LOG.md` M3.

**Scope of the evidence.** The 0-findings trivy result, which inspects
Go binaries, is for a local build from this Dockerfile. The image CI
built and deployed to dev (`20261013-175345-83da391`) was checked by its
build log (the `rm` step ran) and ECR's scan on push, which covers OS
packages only and doesn't inspect Go binaries; no full Go binary scan
was run on that image itself. To scan it, use the "Image" commands
under "How to run" against the dev repository. Absence confirmed on the
deployed prod image (digest `sha256:9bcd0e4c...6cec1b42`, `ls` exit 2,
run by the owner, 2026-10-13). No Go binary scan of that image has been
run.

**`trivy config backend/Dockerfile`:** DS-0002 (HIGH, no non-root
`USER`) and DS-0026 (LOW, no `HEALTHCHECK`). Neither applies to the prod
stage, since Lambda runs the function as its own unprivileged user and
has its own health handling. The `dev` stage, though, ran the local Compose
backend as root; it now runs as a non-root `app` user (uid 10001) with
a healthcheck on `/health` (`security/REMEDIATION_LOG.md` N2). After:
0 misconfigurations.

## trivy: Compose frontend image (2026-10-13)

`frontend/Dockerfile`: the production build served by
`nginxinc/nginx-unprivileged:1.30-alpine` (Alpine 3.24.2), for the local
Docker Compose stack only; deployments serve the build from S3.

| Finding | Severity | Decision |
|---|---|---|
| CVE-2026-85091, zlib 1.3.2-r0 (heap buffer overflow), fixed in 1.3.2-r1 | MEDIUM | **Fixed**: the Dockerfile runs `apk upgrade --no-cache` as root, then switches back to the image's `nginx` user (uid 101), the same approach as the backend's `dnf upgrade` |
| DS-0026, no `HEALTHCHECK` (`trivy config`) | LOW | **Fixed**: a healthcheck fetches the page every 10 seconds; `docker compose ps` shows `(healthy)` |

**Result after the fixes**: `trivy image`: 0 vulnerabilities at any
severity. `trivy config frontend/Dockerfile`: 0 misconfigurations. The
container runs as uid 101, not root.

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
