# Per-environment configuration, stored in SSM Parameter Store.
#
# Parameter Store standard parameters are free. There is no Secrets Manager
# anywhere in this stack, and no VPC, because Neon is reached over the public
# internet with TLS and the Lambda has ordinary outbound access.
#
# The app Lambda reads the pooled URL. The bootstrap Lambda reads the direct
# URL and the demo password. Neither value is ever placed in a Lambda
# environment variable; only the parameter NAMES are, and the values are
# fetched at runtime.

resource "aws_ssm_parameter" "db_url" {
  name        = "/${local.name}/db-url"
  description = "Neon pooled connection string for ${local.name}"
  type        = "SecureString"
  value       = local.neon.pooled
}

resource "aws_ssm_parameter" "db_url_direct" {
  name        = "/${local.name}/db-url-direct"
  description = "Neon direct connection string for ${local.name} (schema bootstrap only)"
  type        = "SecureString"
  value       = local.neon.direct
}

# This environment's JWT signing secret, generated and stored (not hard-coded).
resource "random_password" "jwt" {
  length  = 64
  special = false # keep JWT secret alphanumeric to avoid any encoding surprises
}

resource "aws_ssm_parameter" "jwt" {
  name        = "/${local.name}/jwt-secret"
  description = "JWT signing secret for ${local.name}"
  type        = "SecureString"
  value       = random_password.jwt.result
}

# Shared secret CloudFront sends to API Gateway as X-Origin-Verify on every
# /api/* request (custom_header on the apigw-backend origin, frontend.tf).
# The backend rejects any request without it (app/auth/origin_verify.py), so
# the public execute-api URL can't be used to bypass CloudFront, and with it
# the trustworthy CloudFront-Viewer-Address the login rate limit keys on.
# Not a credential for anything else; rotate with
# `tofu apply -replace=random_password.origin_verify`.
resource "random_password" "origin_verify" {
  length  = 48
  special = false # header-safe
}

resource "aws_ssm_parameter" "origin_verify" {
  name        = "/${local.name}/origin-verify-secret"
  description = "X-Origin-Verify value CloudFront sends to the ${local.name} API"
  type        = "SecureString"
  value       = random_password.origin_verify.result
}

# Demo account password, created only when this environment has one. When it
# is absent the bootstrap gets no DEMO_PASSWORD_PARAM_NAME at all and cannot
# seed a demo user even by accident.
resource "aws_ssm_parameter" "demo_password" {
  count       = local.demo_password != "" ? 1 : 0
  name        = "/${local.name}/demo-password"
  description = "Password for the seeded demo account in ${local.name}"
  type        = "SecureString"
  value       = local.demo_password
}
