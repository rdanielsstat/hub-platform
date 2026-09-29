# One cert per environment, for the CloudFront alias. CloudFront certs must
# live in us-east-1.
#
# CHANGED: the second, regional api.<subdomain> certificate is gone, because
# API Gateway no longer has a custom domain.

resource "aws_acm_certificate" "frontend" {
  provider          = aws.us_east_1
  domain_name       = local.subdomain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "cloudflare_record" "frontend_cert_validation" {
  for_each = {
    for dvo in aws_acm_certificate.frontend.domain_validation_options :
    dvo.domain_name => {
      name  = dvo.resource_record_name
      type  = dvo.resource_record_type
      value = dvo.resource_record_value
    }
  }

  zone_id = var.cloudflare_zone_id
  name    = each.value.name
  type    = each.value.type
  content = each.value.value
  ttl     = 60
  proxied = false
}

resource "aws_acm_certificate_validation" "frontend" {
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.frontend.arn
  validation_record_fqdns = [for r in cloudflare_record.frontend_cert_validation : r.hostname]
}
