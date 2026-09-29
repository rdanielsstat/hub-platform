# DNS for this environment. One record now, not two.

resource "cloudflare_record" "frontend" {
  zone_id = var.cloudflare_zone_id
  name    = local.subdomain
  type    = "CNAME"
  content = aws_cloudfront_distribution.frontend.domain_name
  ttl     = 1
  proxied = true
}
