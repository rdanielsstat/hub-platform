# Shared VPC + endpoints, created ONCE. Both hub environments attaches its Lambda to
# these subnets rather than making its own VPC. This is the "share only the
# safe plumbing" decision: networking is shared, DATA is not (each app gets its
# own database — see the app module).

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = "dnls-shared-vpc" }
}

resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.main.id
  cidr_block        = cidrsubnet(aws_vpc.main.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
  tags              = { Name = "dnls-shared-private-${count.index}" }
}

# One security group all app Lambdas share for egress.
resource "aws_security_group" "lambda" {
  name        = "dnls-shared-lambda-sg"
  description = "Shared Lambda egress"
  vpc_id      = aws_vpc.main.id

  egress {
    description = "All egress"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "dnls-shared-lambda-sg" }
}

# Aurora SG: allow Postgres from the shared Lambda SG.
resource "aws_security_group" "aurora" {
  name        = "dnls-shared-aurora-sg"
  description = "Aurora ingress from shared Lambda SG"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from Lambda"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "dnls-shared-aurora-sg" }
}

# VPC endpoints so in-VPC Lambdas reach AWS services without a NAT gateway.
# Shared across ALL apps/envs — created once, not per-app. This is the main
# cost saving of sharing the VPC: you pay for one set of endpoints, not one
# set per environment.
resource "aws_security_group" "vpc_endpoints" {
  name        = "dnls-shared-vpce-sg"
  description = "Allow HTTPS from Lambda to VPC endpoints"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "HTTPS from Lambda"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = [aws_security_group.lambda.id]
  }

  tags = { Name = "dnls-shared-vpce-sg" }
}

locals {
  interface_endpoints = [
    "ssm", # Lambda fetches secrets from SSM Parameter Store at runtime
    "ecr.api",
    "ecr.dkr",
    "logs",
  ]
}

resource "aws_vpc_endpoint" "interface" {
  for_each            = toset(local.interface_endpoints)
  vpc_id              = aws_vpc.main.id
  service_name        = "com.amazonaws.${var.aws_region}.${each.value}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.vpc_endpoints.id]
  private_dns_enabled = true
  tags                = { Name = "dnls-shared-vpce-${each.value}" }
}

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_vpc.main.default_route_table_id]
  tags              = { Name = "dnls-shared-vpce-s3" }
}
