variable "aws_region" {
  description = "AWS region for ChargeForward resources."
  type        = string
  default     = "us-east-1"
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for raw ChargeForward sources."
  type        = string
}

variable "raw_prefix" {
  description = "S3 key prefix reserved for ChargeForward raw sources."
  type        = string
  default     = "chargeforward/raw"
}

variable "raw_retention_days" {
  description = "Days before noncurrent raw object versions expire."
  type        = number
  default     = 90
}

variable "create_pipeline_role" {
  description = "Create an ECS-compatible role for a containerized Prefect worker."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Tags applied to managed resources."
  type        = map(string)
  default = {
    Project   = "ChargeForward"
    ManagedBy = "Terraform"
  }
}
