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
# disposable: anyone with the credentials can edit or delete it, and the
# changes persist (deploys never reset it).
variable "demo_passwords" {
  description = "Per-environment demo account password. Omit an environment to skip seeding it."
  type        = map(string)
  default     = {}
  sensitive   = true
}

# SemVer reported as SERVICE_VERSION (service.version on telemetry) by the
# dev and prod Lambdas. CI derives it from git tags (.github/scripts/service-version.sh):
# 1.2.0 on a release tag, 1.2.0+2.g<sha> after it, 0.0.0+<sha> before any.
# Separate from lambda_image_tag, which must stay unique per build.
variable "service_version" {
  description = "SemVer for SERVICE_VERSION, e.g. 1.2.0 or 1.2.0+3.gabc1234."
  type        = string
  default     = "0.0.0+local"

  validation {
    condition     = can(regex("^\\d+\\.\\d+\\.\\d+(-[0-9A-Za-z.-]+)?(\\+[0-9A-Za-z.-]+)?$", var.service_version))
    error_message = "service_version must be SemVer without a leading v, e.g. 1.2.0 or 1.2.0+3.gabc1234."
  }
}

# Grafana Cloud OTLP settings for the dev Lambda (lambda.tf), exactly as
# Grafana's OTLP setup page gives them. CI supplies them as TF_VAR_otel_endpoint_dev /
# TF_VAR_otel_headers_dev from the dev environment's secrets; locally,
# terraform.tfvars (gitignored). The "" defaults exist only so prod
# plans don't need them: guard_otel_dev below fails any dev plan where
# either is missing.
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

# Same settings for the prod Lambda. CI (promote.yml) supplies them as
# TF_VAR_otel_endpoint_prod / TF_VAR_otel_headers_prod from the prod
# environment's secrets. The "" defaults keep dev plans working without
# them; guard_otel_prod below fails any prod plan where either is missing.
variable "otel_endpoint_prod" {
  description = "OTEL_EXPORTER_OTLP_ENDPOINT for the prod Lambda."
  type        = string
  default     = ""
}

variable "otel_headers_prod" {
  description = "OTEL_EXPORTER_OTLP_HEADERS for the prod Lambda (carries the Grafana token)."
  type        = string
  default     = ""
  sensitive   = true
}

# Proxies the API trusts to report the client address in X-Forwarded-For
# (TRUSTED_PROXY_IPS, backend/app/core/config.py): comma-separated IPs or
# CIDR ranges. Cloudflare proxies the site, so set this to Cloudflare's
# published ranges (ops/DEPLOYMENT.md); CI passes it as
# TF_VAR_trusted_proxy_ips from the GitHub environment variable
# TRUSTED_PROXY_IPS. Empty (the default) trusts no proxy, which is the
# behaviour before this setting existed.
variable "trusted_proxy_ips" {
  description = "Comma-separated proxy IPs/CIDRs trusted for X-Forwarded-For (Cloudflare's ranges)."
  type        = string
  default     = ""
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token for DNS management."
  type        = string
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

  # OpenTelemetry export to Grafana Cloud, per workspace. Empty in any
  # other workspace, so OTEL_ENABLED stays off there.
  otel_env = lookup({
    dev = {
      OTEL_ENABLED                = "true"
      OTEL_EXPORTER_OTLP_ENDPOINT = var.otel_endpoint_dev
      OTEL_EXPORTER_OTLP_HEADERS  = var.otel_headers_dev
      # SemVer from git tags (CI's -var service_version), reported as the
      # service.version resource attribute on all telemetry.
      SERVICE_VERSION = var.service_version
    }
    prod = {
      OTEL_ENABLED                = "true"
      OTEL_EXPORTER_OTLP_ENDPOINT = var.otel_endpoint_prod
      OTEL_EXPORTER_OTLP_HEADERS  = var.otel_headers_prod
      # promote.yml derives it from the commit the promoted image was built
      # from, so prod reports the same version dev did for those bytes.
      SERVICE_VERSION = var.service_version
    }
  }, local.environment, {})
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

# Same for prod.
resource "terraform_data" "guard_otel_prod" {
  count = local.environment == "prod" ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.otel_endpoint_prod != "" && var.otel_headers_prod != ""
      error_message = "otel_endpoint_prod and otel_headers_prod must be set for prod. Add them to terraform.tfvars (or TF_VAR_otel_endpoint_prod / TF_VAR_otel_headers_prod in CI)."
    }
  }
}
