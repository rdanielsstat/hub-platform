# Database bootstrap Lambda for this environment.
#
# SECURITY BOUNDARY: this is a SEPARATE function from the app Lambda, with its
# OWN IAM role. Only THIS role can read the shared Aurora MASTER credentials
# (/dnls-shared/aurora-master). The app Lambda's role (lambda.tf) cannot — it
# reads only its own per-env app DB + JWT params. So master/superuser access is
# confined to this short-lived, invoke-only bootstrap, never the running app.
#
# It runs the SAME container image as the app, but overrides the image CMD to
# run `python -m app.bootstrap_db` instead of the app handler. It's invoked
# once per deploy (idempotent) by the pipeline, before the app goes live.
# It is NOT fronted by API Gateway — nothing can reach it over the network; it
# only runs when explicitly invoked.

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

resource "aws_iam_role_policy_attachment" "bootstrap_vpc" {
  role       = aws_iam_role.bootstrap.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole"
}

# The bootstrap needs BOTH the master credentials (to connect as superuser) and
# this env's app DB param (to read the role name + password it should create,
# matching what the app will connect with). It does NOT need the JWT param.
data "aws_iam_policy_document" "bootstrap_ssm" {
  statement {
    actions = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = [
      local.aurora_master_param_arn, # shared master creds — ONLY the bootstrap role gets this
      aws_ssm_parameter.app_db.arn,  # this env's app DB creds
    ]
  }
}

resource "aws_iam_role_policy" "bootstrap_ssm" {
  name   = "${local.name}-bootstrap-ssm"
  role   = aws_iam_role.bootstrap.id
  policy = data.aws_iam_policy_document.bootstrap_ssm.json
}

resource "aws_lambda_function" "bootstrap" {
  function_name = "${local.name}-bootstrap"
  role          = aws_iam_role.bootstrap.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.backend.repository_url}:${var.lambda_image_tag}"

  # Override the image's default CMD so this function runs the bootstrap module
  # instead of the app handler. Same image, different entrypoint.
  image_config {
    command = ["app.bootstrap_db.lambda_handler"]
  }

  timeout     = 60
  memory_size = 512

  vpc_config {
    subnet_ids         = local.private_subnet_ids
    security_group_ids = [local.lambda_security_group_id]
  }

  environment {
    variables = {
      APP_NAME    = "hub"
      ENVIRONMENT = local.environment
      USE_SSM     = "true"

      # Master creds (superuser) — read from SSM by the bootstrap ONLY.
      MASTER_DB_PARAM_NAME = local.aurora_master_param_name

      # The app's own DB param, so the bootstrap creates the role/password the
      # app will actually use.
      DB_PARAM_NAME = aws_ssm_parameter.app_db.name
    }
  }
}

output "bootstrap_function_name" {
  description = "Invoke this once per deploy (idempotent) before the app goes live."
  value       = aws_lambda_function.bootstrap.function_name
}
