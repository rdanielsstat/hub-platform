variable "aws_region" {
  description = "Region for shared infrastructure."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "CIDR for the shared VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "db_master_username" {
  description = "Master username for the shared Aurora cluster."
  type        = string
  default     = "dnsadmin"
}
