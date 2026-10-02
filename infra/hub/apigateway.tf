# HTTP API fronting this environment's Lambda.
#
# CHANGED: there is no custom domain and no api.<subdomain> record any more.
# CloudFront forwards <subdomain>/api/* to this API's default endpoint, so the
# browser only ever talks to one origin. That removes a certificate, two DNS
# records, an API Gateway domain name, a base path mapping, and all CORS.

resource "aws_apigatewayv2_api" "backend" {
  name          = "${local.name}-backend"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "backend" {
  api_id                 = aws_apigatewayv2_api.backend.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.backend.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "backend" {
  api_id    = aws_apigatewayv2_api.backend.id
  route_key = "$default"
  target    = "integrations/${aws_apigatewayv2_integration.backend.id}"
}

resource "aws_apigatewayv2_stage" "backend" {
  api_id      = aws_apigatewayv2_api.backend.id
  name        = "$default"
  auto_deploy = true

  # Stage-wide throttle across all clients and routes: a steady 50 requests
  # per second with bursts up to 100; over it, API Gateway answers 429
  # without invoking the Lambda. The global backstop for the per-IP login
  # limit in the app (app/auth/rate_limit.py), which each Lambda container
  # counts on its own. Thresholds are documented in backend/README.md.
  default_route_settings {
    throttling_burst_limit = 100
    throttling_rate_limit  = 50
  }
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.backend.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.backend.execution_arn}/*/*"
}
