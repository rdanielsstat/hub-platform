# ONE Aurora Serverless v2 cluster, shared across hub prod + dev.
# Sharing the CLUSTER is not sharing a DATABASE: each environment creates its
# own database (and its own credentials) inside this cluster. prod and dev
# never share a database; they share only the (idle-cheap) cluster hardware.
#
# HONEST TRADEOFF: the strictest production pattern gives each environment its
# own cluster (or its own account). Here prod and dev share a cluster but have
# separate databases. Reasonable for a student project; for a real payments app
# you'd likely give prod its own cluster. The workspace structure makes that
# split straightforward later.
#
# Secrets live in SSM Parameter Store (SecureString), not Secrets Manager, to
# stay in the free tier — Secrets Manager bills ~$0.40/secret/month; standard
# SSM SecureString parameters are free.

resource "aws_db_subnet_group" "aurora" {
  name       = "dnls-shared-aurora-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags       = { Name = "dnls-shared-aurora-subnets" }
}

resource "aws_rds_cluster" "aurora" {
  cluster_identifier     = "dnls-shared-aurora"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned"
  engine_version         = "16.8"
  db_subnet_group_name   = aws_db_subnet_group.aurora.name
  vpc_security_group_ids = [aws_security_group.aurora.id]

  database_name   = "postgres"
  master_username = var.db_master_username
  master_password = random_password.db_master.result

  serverlessv2_scaling_configuration {
    min_capacity             = 0
    max_capacity             = 2
    seconds_until_auto_pause = 300
  }

  skip_final_snapshot = true
  storage_encrypted   = true
  apply_immediately   = true
}

resource "aws_rds_cluster_instance" "aurora" {
  identifier         = "dnls-shared-aurora-1"
  cluster_identifier = aws_rds_cluster.aurora.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.aurora.engine
  engine_version     = aws_rds_cluster.aurora.engine_version
}

resource "random_password" "db_master" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}"
}

# Master credentials in SSM Parameter Store (SecureString, encrypted, free tier).
resource "aws_ssm_parameter" "db_master" {
  name        = "/dnls-shared/aurora-master"
  description = "Master credentials for the shared Aurora cluster"
  type        = "SecureString"
  value = jsonencode({
    username = var.db_master_username
    password = random_password.db_master.result
    host     = aws_rds_cluster.aurora.endpoint
    port     = 5432
  })
}
