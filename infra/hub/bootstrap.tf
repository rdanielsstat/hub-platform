# Schema bootstrap Lambda for this environment.
#
# Neon creates the project, role and database. What remains is creating the
# TABLES, which used to happen at app import time on every cold start inside a
# try/except that hid failures. It happens here instead: once per deploy,
# explicitly, and it fails loudly.
#
# SECURITY BOUNDARY: this is a separate function with its own role. Only this
# role can read the DIRECT connection string. The app role reads the pooled
# one. It is not fronted by any API, so nothing can reach it over the network;
# it runs only when CI invokes it.
#
# It runs the SAME image as the app, with the CMD overridden.

data "aws_iam_policy_document" "bootstrap_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "bootstrap" {
  name               = "${local.name}-bootstrap"
  assume_role_policy = data.aws_iam_policy_document.bootstrap_assume.json
}

resource "aws_iam_role_policy_attachment" "bootstrap_basic" {
  role       = aws_iam_role.bootstrap.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "bootstrap_ssm" {
  statement {
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [aws_ssm_parameter.db_url_direct.arn]
  }
}

resource "aws_iam_role_policy" "bootstrap_ssm" {
  name   = "${local.name}-bootstrap-ssm"
  role   = aws_iam_role.bootstrap.id
  policy = data.aws_iam_policy_document.bootstrap_ssm.json
}

resource "aws_cloudwatch_log_group" "bootstrap" {
  name              = "/aws/lambda/${local.name}-bootstrap"
  retention_in_days = 14
}

resource "aws_lambda_function" "bootstrap" {
  function_name = "${local.name}-bootstrap"
  role          = aws_iam_role.bootstrap.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.lambda_image_tag}"

  image_config {
    command = ["app.bootstrap_db.lambda_handler"]
  }

  timeout     = 60
  memory_size = 512

  depends_on = [aws_cloudwatch_log_group.bootstrap]

  environment {
    variables = {
      APP_NAME    = "hub"
      ENVIRONMENT = local.environment
      USE_SSM     = "true"

      # Direct (non-pooled) URL: PgBouncer transaction mode is a poor fit for
      # DDL, so schema work uses the plain endpoint.
      DB_URL_PARAM_NAME = aws_ssm_parameter.db_url_direct.name
    }
  }
}

output "bootstrap_function_name" {
  description = "Invoke this once per deploy (idempotent) before the app goes live."
  value       = aws_lambda_function.bootstrap.function_name
}
