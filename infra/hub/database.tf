# Each environment gets its OWN database (inside the shared Aurora cluster) and
# its OWN credentials. prod and dev share cluster hardware but never a database.
#
# Design seam, stated plainly: the AWS provider can't run CREATE DATABASE /
# CREATE ROLE inside Postgres — that's a data-plane action on a private cluster
# reachable only from in-VPC Lambda. So the app's own migrations create/own its
# schema in a database named per-environment (hub_prod / hub_dev). This file
# provisions the per-env SSM parameters the app reads at runtime; creating the
# DB/role is a bootstrap step the app runs, not a Terraform resource.
#
# Secrets are SSM Parameter Store SecureString (free tier), not Secrets Manager.

locals {
  db_name = "hub_${local.environment}" # hub_prod / hub_dev
}

resource "random_password" "app_db" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}"
}

# This environment's DB credentials (JSON), read by the app at runtime.
resource "aws_ssm_parameter" "app_db" {
  name        = "/${local.name}/db-credentials"
  description = "DB credentials for ${local.name}"
  type        = "SecureString"
  value = jsonencode({
    username = "${local.db_name}_user"
    password = random_password.app_db.result
    host     = local.aurora_cluster_endpoint
    port     = 5432
    dbname   = local.db_name
  })
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
