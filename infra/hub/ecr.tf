# One ECR repo per environment (hub-prod-backend, hub-dev-backend), so prod and
# dev images never mix.
#
# Tags are immutable (tfsec AVD-AWS-0031): a tag, once pushed, always names
# the same image, so the tag dev tested is byte-for-byte the tag prod runs.
# CI pushes a fresh <timestamp>-<sha> tag per build; promote.yml skips the
# copy when prod already has the tag (re-promoting the same build).
resource "aws_ecr_repository" "backend" {
  name                 = "${local.name}-backend"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  encryption_configuration {
    encryption_type = "AES256"
  }
}

# ECR storage is $0.10/GB-month and a FastAPI image is a few hundred MB, so
# without this the repo grows by one image per deploy forever. Rule 2 is the
# one that actually caps the bill.
resource "aws_ecr_lifecycle_policy" "backend" {
  repository = aws_ecr_repository.backend.name
  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "Expire untagged images after 7 days"
        selection = {
          tagStatus   = "untagged"
          countType   = "sinceImagePushed"
          countUnit   = "days"
          countNumber = 7
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "Keep only the 10 most recent images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 10
        }
        action = { type = "expire" }
      },
    ]
  })
}
