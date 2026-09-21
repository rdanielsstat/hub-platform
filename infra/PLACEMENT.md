# Where each file goes

Two independent OpenTofu roots. Files with the SAME NAME appear in both
folders but are DIFFERENT files — do not swap them.

## infra/shared/   (6 files)
aurora.tf
backend.tf      <- key = "shared/terraform.tfstate"
outputs.tf      <- outputs vpc_id, private_subnet_ids, aurora_* 
providers.tf    <- NO cloudflare, NO us_east_1 alias (short)
variables.tf
vpc.tf

## infra/hub/   (13 files)
apigateway.tf
backend.tf      <- key = "hub/terraform.tfstate"
certs.tf
database.tf
dns.tf
ecr.tf
frontend.tf
lambda.tf
main.tf
outputs.tf      <- outputs cloudfront_domain, frontend_bucket, ecr_repository_url
providers.tf    <- HAS cloudflare + us_east_1 alias (long)
shared.tf
terraform.tfvars.example   (+ your real terraform.tfvars)

## infra/   (root)
BOOTSTRAP.md
PLACEMENT.md  (this file)

## Same-name pairs — how to tell them apart
backend.tf   : shared has key="shared/..."  | hub has key="hub/..."
providers.tf : shared has NO cloudflare     | hub HAS cloudflare + us_east_1
outputs.tf   : shared outputs vpc/subnet/aurora | hub outputs cloudfront/bucket/ecr
