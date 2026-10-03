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

# Explicit SSE-S3. AWS already encrypts new objects this way by default; this
# makes it part of the configuration (tfsec AVD-AWS-0088) rather than an
# account default. A customer-managed KMS key (AVD-AWS-0132) is deliberately
# not used: the bucket holds only the public build, see security/IAC_SCANS.md.
resource "aws_s3_bucket_server_side_encryption_configuration" "frontend" {
  bucket = aws_s3_bucket.frontend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = true
  }
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

# Security headers on every response, the SPA's and the API's. CloudFront
# adds them (override = true replaces any the origin sent), so S3 objects
# and the Lambda need no changes.
#
# Content-Security-Policy, kept as strict as the app allows:
#   - script-src 'self': no inline scripts and no third-party scripts. The
#     pre-paint theme script is a file (frontend/public/theme-init.js) for
#     this reason; the Vite build emits only <script src>.
#   - style-src 'unsafe-inline': React style props and Base UI's popup
#     positioning set inline style attributes, which CSP governs as styles.
#     Script injection stays blocked; inline styles can't run code.
#   - Google Fonts: the stylesheet (fonts.googleapis.com) and the font
#     files (fonts.gstatic.com), loaded by index.html.
#   - connect-src 'self': the API is same-origin (/api/*).
#   - Cloudflare Web Analytics: Cloudflare's proxy (dns.tf, proxied) injects
#     its beacon script (static.cloudflareinsights.com, with an integrity
#     hash) into every HTML page, and the beacon reports to
#     cloudflareinsights.com. Allowed so the zone's analytics keep working.
#     To drop analytics, turn off Web Analytics for the hostname in
#     Cloudflare and remove both entries. security/DATA_POLICY.md.
#   - frame-ancestors 'none' (with X-Frame-Options DENY): no clickjacking.
# A change that loads anything from a new origin must be added here, or
# the browser blocks it (the console shows the CSP violation).
#
# HSTS: one year, includeSubDomains, preload. Covers this hostname and
# anything under it; dnls.dev itself is unaffected. "preload" only takes
# effect if the apex domain is submitted to the preload list, which this
# stack doesn't do; harmless here.
locals {
  content_security_policy = join("; ", [
    "default-src 'self'",
    "script-src 'self' https://static.cloudflareinsights.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    "img-src 'self' data:",
    "connect-src 'self' https://cloudflareinsights.com",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "upgrade-insecure-requests",
  ])
}

resource "aws_cloudfront_response_headers_policy" "security" {
  name    = "${local.name}-security-headers"
  comment = "CSP, HSTS and related security headers for the SPA and the API"

  security_headers_config {
    content_security_policy {
      content_security_policy = local.content_security_policy
      override                = true
    }

    strict_transport_security {
      access_control_max_age_sec = 31536000
      include_subdomains         = true
      preload                    = true
      override                   = true
    }

    content_type_options {
      override = true
    }

    frame_options {
      frame_option = "DENY"
      override     = true
    }

    referrer_policy {
      referrer_policy = "strict-origin-when-cross-origin"
      override        = true
    }
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

    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id

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

    response_headers_policy_id = aws_cloudfront_response_headers_policy.security.id
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
