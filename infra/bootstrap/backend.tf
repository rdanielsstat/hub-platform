terraform {
  backend "s3" {
    bucket       = "dnls-hub-tofu-state"
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
  }
}
