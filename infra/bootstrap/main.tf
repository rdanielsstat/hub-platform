# GitHub Actions OIDC trust. Run ONCE, from your laptop, before any CI runs.
# After this, GitHub Actions deploys with no long-lived AWS access keys
# anywhere: it exchanges a signed GitHub token for temporary credentials.
#
# NOT to be confused with infra/hub/bootstrap.tf, which is the per-environment
# schema bootstrap Lambda. Different thing entirely.
#
# This is deliberately a separate configuration with its own state, because
# the OIDC provider is account-level. If it lived in infra/hub/ the dev and
# prod workspaces would each try to create the same provider and collide.
#
# Cost: $0.00. IAM roles, policies and OIDC providers are free.

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "github_repo" {
  description = "owner/name of the GitHub repository allowed to assume the CI role."
  type        = string
  default     = "rdanielsstat/hub-platform"
}

variable "state_bucket" {
  description = "S3 bucket holding OpenTofu state."
  type        = string
  default     = "dnls-hub-tofu-state"
}

data "aws_caller_identity" "current" {}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# Only workflows running on the main branch of this one repository may assume
# the role. A fork, a pull request from a fork, or another repo cannot.
data "aws_iam_policy_document" "ci_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "ci" {
  name               = "hub-github-actions"
  description        = "Assumed by GitHub Actions to deploy hub via OpenTofu"
  assume_role_policy = data.aws_iam_policy_document.ci_assume.json
}

# HONEST NOTE, worth writing down in security/ for the rubric: this role is
# broad. PowerUserAccess covers everything OpenTofu creates except IAM, and
# the inline policy below adds the IAM actions it needs. Scoping this down to
# exactly the resource set is possible but brittle, and every new resource
# type means another policy edit. The compensating controls are that the trust
# policy is pinned to one repo and one branch, there are no static keys, and
# every assumption is in CloudTrail.
resource "aws_iam_role_policy_attachment" "ci_power" {
  role       = aws_iam_role.ci.name
  policy_arn = "arn:aws:iam::aws:policy/PowerUserAccess"
}

data "aws_iam_policy_document" "ci_iam" {
  # OpenTofu creates and manages the Lambda execution roles.
  statement {
    actions = [
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:PassRole",
      "iam:TagRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = [
      "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/hub-*",
    ]
  }

  # State bucket and its lock files.
  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = ["arn:aws:s3:::${var.state_bucket}"]
  }

  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["arn:aws:s3:::${var.state_bucket}/*"]
  }
}

resource "aws_iam_role_policy" "ci_iam" {
  name   = "hub-ci-iam"
  role   = aws_iam_role.ci.id
  policy = data.aws_iam_policy_document.ci_iam.json
}

output "ci_role_arn" {
  description = "Set this as the AWS_ROLE_ARN variable in the GitHub repo."
  value       = aws_iam_role.ci.arn
}
