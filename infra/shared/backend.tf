terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket       = "dnls-hub-tofu-state"
    key          = "shared/terraform.tfstate" # shared infra has its own state
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
