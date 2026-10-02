# Frontend for this environment: private S3 bucket served by CloudFront at
# <subdomain>, PLUS an /api/* behaviour pointing at API Gateway.
#
# Two origins on one distribution is the key change. The browser loads the app
# and calls /api/... on the same origin, so:
#   - no CORS, at all
#   - the frontend build is environment-independent (VITE_API_BASE_URL is
#     always "/api"), so one built artifact promotes from dev to prod
#   - one certificate and one DNS record instead of two

resource "aws_s3_bucket" "frontend" {
  bucket = "dnls-${local.name}-frontend" # dnls-hub-prod-frontend / dnls-hub-dev-frontend
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  bucket                  = aws_s3_bucket.frontend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  name                              = "${local.name}-frontend-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# SPA routing without custom_error_response.
#
# custom_error_response applies to the WHOLE distribution, so mapping 403/404
# to index.html would also swallow real API 401s, 403s and 404s and return an
# HTML page with status 200. This function is attached to the static behaviour
# only, so /api/* error codes pass through untouched.
#
# CloudFront Functions bill per million invocations and are effectively free
# at this volume.
resource "aws_cloudfront_function" "spa_router" {
  name    = "${local.name}-spa-router"
  runtime = "cloudfront-js-2.0"
  comment = "Rewrite extensionless paths to /index.html for SPA routing"
  publish = true
  code    = <<-JS
    function handler(event) {
      var request = event.request;
      // Anything without a file extension is a client-side route.
      if (request.uri.indexOf('.') === -1) {
        request.uri = '/index.html';
      }
      return request;
    }
  JS
}

# Origin request policy for /api/*: which viewer headers reach API Gateway.
#
# Replaces the managed AllViewerExceptHostHeader policy, which does not
# forward CloudFront-Viewer-Address. The backend's per-IP login rate limit
# (backend/app/auth/rate_limit.py, CLIENT_IP_HEADER in lambda.tf) needs that
# header: API Gateway only sees CloudFront's address, so without it every
# user behind the same CloudFront edge shares one rate-limit bucket, and five
# attempts from any of them lock the rest out for a minute.
#
# An allowlist because no header behaviour both drops Host and adds
# CloudFront headers: "allViewerAndWhitelistCloudFront" forwards the viewer's
# Host, and API Gateway answers a foreign Host with 403. Listed here are the
# request headers the API reads. Cookies (the hub_token session) and query
# strings are forwarded in full; the body and its length always are.
# A header the API starts depending on must be added here, or it is dropped.
#
# Names are account-wide and dev and prod share an account, so the name
# carries the environment.
resource "aws_cloudfront_origin_request_policy" "api" {
  name    = "${local.name}-forward-viewer-address"
  comment = "API origin: allowlisted viewer headers plus CloudFront-Viewer-Address for per-IP rate limiting"

  headers_config {
    header_behavior = "whitelist"
    headers {
      items = [
        "Accept",
        "Authorization",
        "CloudFront-Viewer-Address",
        "Content-Type",
        "Origin",
        "User-Agent",
      ]
    }
  }

  cookies_config {
    cookie_behavior = "all"
  }

  query_strings_config {
    query_string_behavior = "all"
  }
}

resource "aws_cloudfront_distribution" "frontend" {
  enabled             = true
  default_root_object = "index.html"
  aliases             = [local.subdomain]

  origin {
    domain_name              = aws_s3_bucket.frontend.bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend.id
  }

  origin {
    domain_name = replace(aws_apigatewayv2_api.backend.api_endpoint, "https://", "")
    origin_id   = "apigw-backend"

    # Proves a request came through CloudFront: the backend rejects anything
    # without this header (see aws_ssm_parameter.origin_verify, database.tf).
    # Set here on the origin, not in the origin request policy, which can only
    # pick viewer headers to forward, never add a fixed one. CloudFront
    # overwrites any X-Origin-Verify a viewer sends.
    custom_header {
      name  = "X-Origin-Verify"
      value = random_password.origin_verify.result
    }

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = "658327ea-f89d-4fab-a63d-7e88639e58f6" # CachingOptimized

    function_association {
      event_type   = "viewer-request"
      function_arn = aws_cloudfront_function.spa_router.arn
    }
  }

  ordered_cache_behavior {
    path_pattern           = "/api/*"
    target_origin_id       = "apigw-backend"
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods         = ["GET", "HEAD"]

    # CachingDisabled: API responses are per-user and must never be cached.
    cache_policy_id = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"

    # Allowlisted headers plus CloudFront-Viewer-Address, and never the
    # viewer's Host: CloudFront sends API Gateway its own host name, since
    # forwarding the CloudFront alias as Host makes API Gateway answer 403.
    # See aws_cloudfront_origin_request_policy.api above.
    origin_request_policy_id = aws_cloudfront_origin_request_policy.api.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.frontend.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }

  price_class = "PriceClass_100"
}

data "aws_iam_policy_document" "frontend_bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.frontend.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.frontend.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  bucket = aws_s3_bucket.frontend.id
  policy = data.aws_iam_policy_document.frontend_bucket.json
}
