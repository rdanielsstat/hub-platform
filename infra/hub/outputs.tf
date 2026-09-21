output "environment" {
  value = local.environment
}

output "subdomain" {
  value = local.subdomain
}

output "cloudfront_domain" {
  description = "CloudFront domain the subdomain CNAME points at."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "frontend_bucket" {
  description = "S3 bucket to sync the built frontend into."
  value       = aws_s3_bucket.frontend.id
}

output "ecr_repository_url" {
  description = "Push the backend image here."
  value       = aws_ecr_repository.backend.repository_url
}

output "api_endpoint" {
  value = aws_apigatewayv2_api.backend.api_endpoint
}
