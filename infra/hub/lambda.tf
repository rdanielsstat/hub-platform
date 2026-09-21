# Backend Lambda for this environment, attached to the shared VPC.

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

resource "aws_iam_role_policy_attachment" "lambda_vpc" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# Allow reading ONLY this environment's own SSM parameters (db creds + jwt).
# SSM SecureString values are encrypted with the AWS-managed key by default,
# which the SSM service decrypts on GetParameter without a separate KMS grant.
data "aws_iam_policy_document" "lambda_ssm" {
  statement {
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      aws_ssm_parameter.app_db.arn,
      aws_ssm_parameter.jwt.arn,
    ]
  }
}

resource "aws_iam_role_policy" "lambda_ssm" {
  name   = "${local.name}-lambda-ssm"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda_ssm.json
}

resource "aws_lambda_function" "backend" {
  function_name = "${local.name}-backend"
  role          = aws_iam_role.lambda.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.lambda_image_tag}"

  timeout     = 30
  memory_size = 512

  vpc_config {
    subnet_ids         = local.private_subnet_ids
    security_group_ids = [local.lambda_security_group_id]
  }

  environment {
    variables = {
      APP_NAME    = "hub"
      ENVIRONMENT = local.environment

      # Turn on SSM-backed secret loading. This flag (not ENVIRONMENT) is what
      # makes config.py fetch DATABASE_URL + JWT secret from SSM at runtime.
      USE_SSM = "true"

      # The app fetches secret VALUES from SSM at runtime using these names;
      # values themselves are never placed in the Lambda environment.
      DB_PARAM_NAME  = aws_ssm_parameter.app_db.name
      JWT_PARAM_NAME = aws_ssm_parameter.jwt.name
    }
  }
}
