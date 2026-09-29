terraform {
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.60"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      App       = "hub"
      Scope     = "bootstrap"
      ManagedBy = "opentofu"
    }
  }
}
