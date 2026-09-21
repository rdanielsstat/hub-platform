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

# The workspace name IS the environment: `prod` or `dev`.
# Everything below derives from it, so switching workspace switches all names
# and the subdomain with no other edits.
locals {
  environment = terraform.workspace

  # Guard against applying in the unnamed default workspace by accident.
  # (A plan in `default` would build resources named hub-default-* — not wanted.)
  is_valid_env = contains(["prod", "dev"], local.environment)

  name = "hub-${local.environment}" # hub-prod / hub-dev

  # prod serves the bare hub.dnls.dev; dev serves hub-dev.dnls.dev
  subdomain = local.environment == "prod" ? "hub.dnls.dev" : "hub-${local.environment}.dnls.dev"
}

# Fail early with a clear message if run in the default workspace.
resource "terraform_data" "guard_env" {
  count = local.is_valid_env ? 0 : 1

  lifecycle {
    precondition {
      condition     = local.is_valid_env
      error_message = "Select a workspace first: `tofu workspace select prod` or `dev`. Current workspace '${terraform.workspace}' is not allowed."
    }
  }
}
