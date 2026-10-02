terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
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