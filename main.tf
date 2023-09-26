data "aws_iam_policy_document" "lambda_assume_role_policy" {
  statement {
    actions   = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda_role" {
  name        = "lambda_role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role_policy.json
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "lambda_policy"
  description = "Policy for Lambda function"
  
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Action   = ["ssm:GetParameter"],
        Effect   = "Allow",
        Resource = aws_ssm_parameter.example_parameter.arn
      },
      {
        Action   = ["s3:PutLifecycleConfiguration", "s3:PutBucketVersioning"],
        Effect   = "Allow",
        Resource = aws_s3_bucket.example_bucket.arn
      },
      {
        Action   = ["kms:Encrypt", "kms:Decrypt"],
        Effect   = "Allow",
        Resource = aws_kms_key.example_key.arn  # Replace with your KMS key ARN
      },
      {
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
        Effect   = "Allow",
        Resource = aws_cloudwatch_log_group.lambda_log_group.arn
      }
    ]
  })
}

resource "aws_lambda_permission" "eventbridge_permission" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.example_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_eventbridge_rule.example_rule.arn
}
