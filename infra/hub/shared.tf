# Read the shared VPC + Aurora (built once in ../shared) so both hub
# environments attach to the same network and database cluster.
data "terraform_remote_state" "shared" {
  backend = "s3"
  config = {
    bucket = "dnls-hub-tofu-state"
    key    = "shared/terraform.tfstate"
    region = "us-east-1"
  }
}

locals {
  vpc_id                   = data.terraform_remote_state.shared.outputs.vpc_id
  private_subnet_ids       = data.terraform_remote_state.shared.outputs.private_subnet_ids
  lambda_security_group_id = data.terraform_remote_state.shared.outputs.lambda_security_group_id
  aurora_cluster_endpoint  = data.terraform_remote_state.shared.outputs.aurora_cluster_endpoint
}
