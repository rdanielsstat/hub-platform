terraform {
  required_version = ">= 1.10"

  backend "s3" {
    bucket       = "dnls-hub-tofu-state"
    key          = "hub/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true
    # With workspaces, OpenTofu automatically stores each workspace's state
    # under env:/<workspace>/hub/terraform.tfstate in this bucket, so prod and
    # dev states never collide. The "default" workspace is unused here.
  }
}
