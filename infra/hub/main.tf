variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "cloudflare_zone_id" {
  type = string
}

variable "lambda_image_tag" {
  description = "ECR image tag to deploy (set by CI, or 'latest' locally)."
  type        = string
  default     = "latest"
}

# Neon connection strings, one entry per workspace. Copied from the Neon
# console (Connect button, Connection pooling toggle on for pooled, off for
# direct). Lives in terraform.tfvars, which is gitignored; CI supplies it as
# the TF_VAR_neon_urls environment variable holding JSON.
#
# pooled: PgBouncer endpoint (hostname has -pooler). Used by the app Lambda,
#         which is connection-per-request and needs the pooler.
# direct: plain endpoint. Used by the bootstrap Lambda, because the pooler
#         runs PgBouncer in transaction mode and schema DDL wants a session.
variable "neon_urls" {
  description = "Per-environment Neon connection strings."
  type = map(object({
    pooled = string
    direct = string
  }))
  sensitive = true
}

# Password for the seeded demo account, per workspace. Leave an entry out (or
# set it to "") and that environment gets NO demo user at all.
#
# The password lives in terraform.tfvars (gitignored) and reaches the bootstrap
# through SSM. It is never in the repo, never in app/db/seed.py, and never the
# same value as the local demo1234.
#
# This is a real, writable, publicly advertised account. Treat its data as
# disposable: anyone with the credentials can edit or delete it. That is what
# the "Reset demo data" workflow is for.
variable "demo_passwords" {
  description = "Per-environment demo account password. Omit an environment to skip seeding it."
  type        = map(string)
  default     = {}
  sensitive   = true
}

# Grafana Cloud OTLP settings for the dev Lambda (lambda.tf), exactly as
# Grafana's OTLP setup page gives them. Dev only for now: prod gets no
# OTel variables at all. CI supplies them as TF_VAR_otel_endpoint_dev /
# TF_VAR_otel_headers_dev from the dev environment's secrets; locally,
# terraform.tfvars (gitignored). The "" defaults exist only so prod
# applies (promote.yml) don't need them: guard_otel_dev below fails any
# dev plan where either is missing.
variable "otel_endpoint_dev" {
  description = "OTEL_EXPORTER_OTLP_ENDPOINT for the dev Lambda."
  type        = string
  default     = ""
}

variable "otel_headers_dev" {
  description = "OTEL_EXPORTER_OTLP_HEADERS for the dev Lambda (carries the Grafana token)."
  type        = string
  default     = ""
  sensitive   = true
}

# The workspace name IS the environment: `prod` or `dev`.
# Everything below derives from it, so switching workspace switches all names
# and the subdomain with no other edits.
locals {
  environment = terraform.workspace

  # Guard against applying in the unnamed default workspace by accident.
  is_valid_env = contains(["prod", "dev"], local.environment)

  name = "hub-${local.environment}" # hub-prod / hub-dev

  # prod serves the bare hub.dnls.dev; dev serves hub-dev.dnls.dev
  subdomain = local.environment == "prod" ? "hub.dnls.dev" : "hub-${local.environment}.dnls.dev"

  # This environment's Neon strings, selected by workspace.
  neon = lookup(var.neon_urls, local.environment, { pooled = "", direct = "" })

  # Empty string means "no demo account in this environment".
  demo_password = lookup(var.demo_passwords, local.environment, "")

  # OpenTelemetry export to Grafana Cloud: dev only. Empty in prod, so
  # the prod Lambda's environment is unchanged and OTEL_ENABLED stays off.
  otel_env = {
    for k, v in {
      OTEL_ENABLED                = "true"
      OTEL_EXPORTER_OTLP_ENDPOINT = var.otel_endpoint_dev
      OTEL_EXPORTER_OTLP_HEADERS  = var.otel_headers_dev
      # The deployed image tag (CI's -var lambda_image_tag), reported as
      # the service.version resource attribute on all telemetry.
      SERVICE_VERSION = var.lambda_image_tag
    } : k => v if local.environment == "dev"
  }
}

resource "terraform_data" "guard_env" {
  count = local.is_valid_env ? 0 : 1

  lifecycle {
    precondition {
      condition     = local.is_valid_env
      error_message = "Select a workspace first: `tofu workspace select prod` or `dev`. Current workspace is not allowed."
    }
  }
}

# Fail early and clearly if the Neon strings for this workspace are missing,
# rather than deploying a Lambda that cannot reach a database.
resource "terraform_data" "guard_neon" {
  lifecycle {
    precondition {
      condition     = local.neon.pooled != "" && local.neon.direct != ""
      error_message = "No neon_urls entry for this workspace. Add it to terraform.tfvars (or TF_VAR_neon_urls in CI)."
    }
  }
}

# Fail the dev plan loudly if the Grafana settings are missing, rather
# than deploying a dev Lambda that exports nowhere.
resource "terraform_data" "guard_otel_dev" {
  count = local.environment == "dev" ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.otel_endpoint_dev != "" && var.otel_headers_dev != ""
      error_message = "otel_endpoint_dev and otel_headers_dev must be set for dev. Add them to terraform.tfvars (or TF_VAR_otel_endpoint_dev / TF_VAR_otel_headers_dev in CI)."
    }
  }
}
