output "environment" {
  value = local.environment
}

output "subdomain" {
  value = local.subdomain
}

output "site_url" {
  description = "What a reviewer opens."
  value       = "https://${local.subdomain}"
}

output "cloudfront_domain" {
  description = "CloudFront domain the subdomain CNAME points at."
  value       = aws_cloudfront_distribution.frontend.domain_name
}

output "cloudfront_distribution_id" {
  description = "Needed by CI to invalidate after a frontend deploy."
  value       = aws_cloudfront_distribution.frontend.id
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
  description = "Direct API Gateway URL. Normal traffic goes via CloudFront /api/*."
  value       = aws_apigatewayv2_api.backend.api_endpoint
}

# The deployment record: read from the API Lambda itself, not from the
# variable, so a targeted apply (rollback-dev.yml) updates it too.
# promote.yml reads it from dev; rollback-dev.yml rolls back from it.
output "deployed_image_tag" {
  description = "The image tag the API Lambda runs. promote.yml promotes it; rollback-dev.yml rolls back from it."
  value       = element(split(":", aws_lambda_function.backend.image_uri), 1)
}
