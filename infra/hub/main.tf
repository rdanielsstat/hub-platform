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
