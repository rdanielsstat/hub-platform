# These outputs are how each app+env config discovers the shared infra.
# Apps read them via a terraform_remote_state data source (see the env configs).

output "vpc_id" {
  value = aws_vpc.main.id
}

output "private_subnet_ids" {
  value = aws_subnet.private[*].id
}

output "lambda_security_group_id" {
  value = aws_security_group.lambda.id
}

output "aurora_cluster_endpoint" {
  value = aws_rds_cluster.aurora.endpoint
}

output "aurora_cluster_id" {
  value = aws_rds_cluster.aurora.id
}

output "aurora_master_param_arn" {
  value = aws_ssm_parameter.db_master.arn
}

output "aurora_master_param_name" {
  value = aws_ssm_parameter.db_master.name
}
