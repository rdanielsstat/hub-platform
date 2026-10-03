# Backend Lambda for this environment. NOT in a VPC: it reaches Neon over
# public TLS and SSM over the public AWS endpoint, so there are no interface
# endpoints and no NAT gateway. That is the whole reason this stack costs
# cents instead of tens of dollars.

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${local.name}-lambda"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Read ONLY this environment's own parameters, and NOT the direct URL, which
# belongs to the bootstrap role alone.
data "aws_iam_policy_document" "lambda_ssm" {
  statement {
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      aws_ssm_parameter.db_url.arn,
      aws_ssm_parameter.jwt.arn,
      aws_ssm_parameter.origin_verify.arn,
    ]
  }
}

resource "aws_iam_role_policy" "lambda_ssm" {
  name   = "${local.name}-lambda-ssm"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_ssm.json
}

# Declared explicitly so retention is 14 days. Left to Lambda, the group is
# auto-created with retention set to never expire, and you pay $0.03/GB-month
# on those logs forever.
resource "aws_cloudwatch_log_group" "backend" {
  name              = "/aws/lambda/${local.name}-backend"
  retention_in_days = 14
}

resource "aws_lambda_function" "backend" {
  function_name = "${local.name}-backend"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.lambda_image_tag}"

  timeout     = 30
  memory_size = 512

  # The distribution first: the app rejects requests without X-Origin-Verify,
  # so CloudFront must already be sending it before a Lambda that checks for
  # it goes live. The AWS provider waits for the distribution to finish
  # deploying, so this ordering closes that window on a rotation or the
  # first rollout.
  depends_on = [
    aws_cloudwatch_log_group.backend,
    aws_cloudfront_distribution.frontend,
  ]

  environment {
    # local.otel_env (main.tf) adds the OTel settings in dev and prod.
    variables = merge({
      APP_NAME    = "hub"
      ENVIRONMENT = local.environment

      # Turn on SSM-backed secret loading.
      USE_SSM = "true"

      # Parameter NAMES only. Values are fetched at runtime.
      DB_URL_PARAM_NAME = aws_ssm_parameter.db_url.name
      JWT_PARAM_NAME    = aws_ssm_parameter.jwt.name

      # Origin verification: the app loads the secret CloudFront sends as
      # X-Origin-Verify (database.tf, frontend.tf) from this SSM parameter at
      # startup, and answers 403 to any request without it, i.e. anything
      # sent straight to the public execute-api URL instead of via CloudFront.
      ORIGIN_VERIFY_PARAM_NAME = aws_ssm_parameter.origin_verify.name
      # Not read by the app. Changes when the secret is rotated, which
      # updates the function and so replaces warm containers still holding
      # the old value (it's cached per process), after CloudFront (see
      # depends_on below) has switched to the new one.
      ORIGIN_VERIFY_VERSION = tostring(aws_ssm_parameter.origin_verify.version)

      # CloudFront serves the API at <subdomain>/api/*, so Mangum strips this
      # prefix before FastAPI sees the path. Routes stay at /projects etc.
      API_BASE_PATH = "/api"

      # Same-origin in AWS, so this is belt-and-braces rather than required.
      CORS_ORIGINS = "https://${local.subdomain}"

      # The real viewer IP for the per-IP login rate limit. API Gateway only
      # sees CloudFront's address; CloudFront adds the viewer's in this header
      # ("ip:port"), forwarded by aws_cloudfront_origin_request_policy.api
      # (frontend.tf). Without it the app falls back to the peer address,
      # which would make the limit per CloudFront edge, not per user.
      CLIENT_IP_HEADER = "CloudFront-Viewer-Address"

      # Behind Cloudflare, that viewer is a Cloudflare edge, not the user.
      # When it's in these ranges the app reads the user's address from
      # X-Forwarded-For instead (security/RATE_LIMITING.md). Empty: off.
      TRUSTED_PROXY_IPS = var.trusted_proxy_ips
    }, local.otel_env)
  }
}
