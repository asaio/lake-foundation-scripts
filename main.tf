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

data "template_file" "iam_policy_template" {
  template = file("${path.module}/iam_policy.tpl")  # Adjust the path as needed
}

resource "aws_iam_policy" "lambda_policy" {
  name        = "lambda_policy"
  description = "Policy for Lambda function"
  policy      = data.template_file.iam_policy_template.rendered
}

resource "aws_lambda_permission" "eventbridge_permission" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.example_lambda.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_eventbridge_rule.example_rule.arn
}
