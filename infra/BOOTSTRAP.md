# One-time bootstrap: state bucket

The S3 bucket that holds OpenTofu state must exist BEFORE `tofu init`,
because the backend config points at it. This is the one standard
exception to "everything in code" — you create the state store manually,
once, then everything else is managed by OpenTofu.

Run these once (pick a globally-unique bucket name and set it in backend.tf):

```bash
export STATE_BUCKET="dnls-hub-tofu-state"   # must be globally unique
export AWS_REGION="us-east-1"

# create the bucket
aws s3api create-bucket \
  --bucket "$STATE_BUCKET" \
  --region "$AWS_REGION"

# enable versioning (recommended for state recovery + lock file reliability)
aws s3api put-bucket-versioning \
  --bucket "$STATE_BUCKET" \
  --versioning-configuration Status=Enabled

# block all public access
aws s3api put-public-access-block \
  --bucket "$STATE_BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# default encryption
aws s3api put-bucket-encryption \
  --bucket "$STATE_BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Then set the same bucket name in `backend.tf` and run `tofu init`.
