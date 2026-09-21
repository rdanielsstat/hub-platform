# DNS records for this environment.

# <subdomain> -> CloudFront
resource "cloudflare_record" "frontend" {
  zone_id = var.cloudflare_zone_id
  name    = local.subdomain
  type    = "CNAME"
  content = aws_cloudfront_distribution.frontend.domain_name
  ttl     = 1
  proxied = true
}

# api.<subdomain> -> API Gateway
resource "cloudflare_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = "api.${local.subdomain}"
  type    = "CNAME"
  content = aws_apigatewayv2_domain_name.backend.domain_name_configuration[0].target_domain_name
  ttl     = 1
  proxied = true
}
