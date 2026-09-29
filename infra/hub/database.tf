# Per-environment configuration, stored in SSM Parameter Store.
#
# Parameter Store standard parameters are free. There is no Secrets Manager
# anywhere in this stack, and no VPC, because Neon is reached over the public
# internet with TLS and the Lambda has ordinary outbound access.
#
# The app Lambda reads the pooled URL. The bootstrap Lambda reads the direct
# URL. Neither value is ever placed in a Lambda environment variable; only the
# parameter NAMES are, and the values are fetched at runtime.

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
