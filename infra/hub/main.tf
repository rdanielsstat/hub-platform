variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "cloudflare_zone_id" {
  type = string
}

# Required, with no default: CI passes the tag it built (ci.yml), the tag
# dev runs (promote.yml) or the previous dev tag (rollback-dev.yml). A
# run without one fails instead of planning a switch to some other image.
variable "lambda_image_tag" {
  description = "ECR image tag to deploy, e.g. 20261013-211021-8df32f0. Set by CI."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9]{8}-[0-9]{6}-[0-9a-f]{7,40}$", var.lambda_image_tag))
    error_message = "lambda_image_tag must be a CI build tag (<yyyymmdd>-<hhmmss>-<sha>), not latest or a hand-picked name."
  }
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
# Required, with no default, for the same reason as lambda_image_tag.
variable "service_version" {
  description = "SemVer for SERVICE_VERSION, e.g. 1.2.0 or 1.2.0+3.gabc1234. Set by CI."
  type        = string
  nullable    = false

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
# TRUSTED_PROXY_IPS (on the dev and prod environments). Required, with no
# default, and guard_trusted_proxies below refuses an empty value: an
# empty list would quietly make the login and sign-up limits per
# Cloudflare edge instead of per user (security/RATE_LIMITING.md).
variable "trusted_proxy_ips" {
  description = "Comma-separated proxy IPs/CIDRs trusted for X-Forwarded-For (Cloudflare's ranges). Set by CI."
  type        = string
  nullable    = false
}

# Drill only (security/OPERATIONAL_DIAGNOSIS.md): true makes the dev
# Lambda's POST /projects answer 500 (FAULT_INJECT_5XX), so the project
# creation alert fires and the on-call agent rolls dev back. ci.yml's
# deploy-dev passes the dev GitHub environment variable FAULT_INJECT_5XX;
# nothing else passes it, so rollback-dev.yml always deploys it off.
# guard_fault_inject refuses it anywhere but dev.
variable "fault_inject_5xx" {
  description = "Dev only: force POST /projects to answer 500, for the on-call drill."
  type        = bool
  default     = false
  nullable    = false
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

  # Set on the dev Lambda only, and only while a drill is running.
  fault_env = local.environment == "dev" && var.fault_inject_5xx ? {
    FAULT_INJECT_5XX = "true"
  } : {}
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

# Cloudflare proxies both environments, so an empty list is always a
# mistake (the GitHub environment variable missing), never a choice.
resource "terraform_data" "guard_trusted_proxies" {
  lifecycle {
    precondition {
      condition     = trimspace(var.trusted_proxy_ips) != ""
      error_message = "trusted_proxy_ips is empty. CI passes it from the TRUSTED_PROXY_IPS variable on the dev and prod GitHub environments (ops/DEPLOYMENT.md)."
    }
  }
}

# The drill's fault flag never reaches prod.
resource "terraform_data" "guard_fault_inject" {
  lifecycle {
    precondition {
      condition     = !var.fault_inject_5xx || local.environment == "dev"
      error_message = "fault_inject_5xx is for the dev drill only and must stay false outside the dev workspace."
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
