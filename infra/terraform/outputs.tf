output "raw_bucket_name" {
  value       = aws_s3_bucket.raw.bucket
  description = "S3 bucket for immutable raw source objects."
}

output "raw_prefix_uri" {
  value       = "s3://${aws_s3_bucket.raw.bucket}/${var.raw_prefix}/"
  description = "Configured raw-data landing prefix."
}

output "pipeline_policy_arn" {
  value       = aws_iam_policy.pipeline.arn
  description = "IAM policy for the ingestion/orchestration runtime."
}

output "pipeline_role_arn" {
  value       = var.create_pipeline_role ? aws_iam_role.pipeline[0].arn : null
  description = "Optional ECS-compatible Prefect pipeline role."
}
