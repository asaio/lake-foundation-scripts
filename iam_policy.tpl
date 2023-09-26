policy {
  Version = "2012-10-17"
  Statement = [
    {
      Action   = "ssm:GetParameter",
      Effect   = "Allow",
      Resource = "${aws_ssm_parameter.example_parameter.arn}"
    },
    {
      Action   = ["s3:PutLifecycleConfiguration", "s3:PutBucketVersioning"],
      Effect   = "Allow",
      Resource = "${aws_s3_bucket.example_bucket.arn}"
    },
    {
      Action   = ["kms:Encrypt", "kms:Decrypt"],
      Effect   = "Allow",
      Resource = "${aws_kms_key.example_key.arn}"
    },
    {
      Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"],
      Effect   = "Allow",
      Resource = "${aws_cloudwatch_log_group.lambda_log_group.arn}"
    }
  ]
}
