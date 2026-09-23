resource "aws_s3_bucket" "raw" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.raw_retention_days
    }
  }
}

data "aws_iam_policy_document" "pipeline" {
  statement {
    sid     = "ListRawBucket"
    actions = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.raw.arn]
  }
  statement {
    sid     = "ReadWriteRawObjects"
    actions = ["s3:GetObject", "s3:PutObject", "s3:GetObjectVersion"]
    resources = ["${aws_s3_bucket.raw.arn}/${var.raw_prefix}/*"]
  }
}

resource "aws_iam_policy" "pipeline" {
  name        = "chargeforward-s3-pipeline"
  description = "Least-privilege access to the ChargeForward raw-data prefix."
  policy      = data.aws_iam_policy_document.pipeline.json
}

data "aws_iam_policy_document" "assume_pipeline" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "pipeline" {
  count              = var.create_pipeline_role ? 1 : 0
  name               = "chargeforward-prefect-pipeline"
  assume_role_policy = data.aws_iam_policy_document.assume_pipeline.json
}

resource "aws_iam_role_policy_attachment" "pipeline" {
  count      = var.create_pipeline_role ? 1 : 0
  role       = aws_iam_role.pipeline[0].name
  policy_arn = aws_iam_policy.pipeline.arn
}
