terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "= 5.100.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "= 4.52.9"
    }
    random = {
      source  = "hashicorp/random"
      version = "= 3.9.1"
    }
    grafana = {
      source  = "grafana/grafana"
      version = "= 4.46.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      App         = "hub"
      Environment = terraform.workspace
      ManagedBy   = "opentofu"
    }
  }
}

# us-east-1 alias for the CloudFront cert (must live in us-east-1).
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      App         = "hub"
      Environment = terraform.workspace
      ManagedBy   = "opentofu"
    }
  }
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# Grafana Cloud alerting (grafana.tf). The stack URL comes from
# var.grafana_url (the GRAFANA_URL repo variable in CI); the service
# account token from the GRAFANA_AUTH environment variable, which the
# provider reads itself, mapped from the GRAFANA_AUTH secret in the
# workflow jobs that run OpenTofu. It never goes through a variable, so
# it can't land in a plan file.
provider "grafana" {
  url = var.grafana_url
}
