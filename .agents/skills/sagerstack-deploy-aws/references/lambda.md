<overview>
Lambda function deployment with Terraform. Includes IAM roles, environment variables, layers, and SNS/SQS triggers.
</overview>

<module_structure>
## Lambda Module

```hcl
# terraform/modules/lambda/main.tf

# IAM role for Lambda
resource "aws_iam_role" "lambda" {
  name = "${var.project_name}-${var.environment}-${var.function_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Basic Lambda execution policy
resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Custom policy for S3, SNS, SQS, Secrets Manager
resource "aws_iam_role_policy" "lambda_permissions" {
  name = "${var.function_name}-permissions"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject"
        ]
        Resource = "${var.s3_bucket_arn}/*"
      },
      {
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = var.sns_topic_arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.sqs_queue_arn
      },
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.secrets_arn
      }
    ]
  })
}

# Lambda function
resource "aws_lambda_function" "function" {
  function_name = "${var.project_name}-${var.environment}-${var.function_name}"
  role          = aws_iam_role.lambda.arn
  handler       = var.handler
  runtime       = var.runtime
  timeout       = var.timeout
  memory_size   = var.memory_size

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  layers = var.layer_arns

  environment {
    variables = merge(
      {
        ENVIRONMENT     = var.environment
        S3_BUCKET       = var.s3_bucket
        SNS_TOPIC_ARN   = var.sns_topic_arn
        SECRETS_NAME    = var.secrets_name
      },
      var.extra_env_vars
    )
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic,
    aws_iam_role_policy.lambda_permissions
  ]
}

# Package Lambda code
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = var.source_path
  output_path = "${path.module}/lambda.zip"
  excludes    = ["__pycache__", "*.pyc", ".pytest_cache", "tests"]
}

# CloudWatch Log Group
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${aws_lambda_function.function.function_name}"
  retention_in_days = var.log_retention_days
}
```

```hcl
# terraform/modules/lambda/variables.tf
variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "function_name" {
  type = string
}

variable "handler" {
  type    = string
  default = "handler.lambdaHandler"
}

variable "runtime" {
  type    = string
  default = "python3.13"
}

variable "timeout" {
  type    = number
  default = 30
}

variable "memory_size" {
  type    = number
  default = 256
}

variable "source_path" {
  type = string
}

variable "s3_bucket" {
  type = string
}

variable "s3_bucket_arn" {
  type = string
}

variable "sns_topic_arn" {
  type    = string
  default = ""
}

variable "sqs_queue_arn" {
  type    = string
  default = ""
}

variable "secrets_arn" {
  type    = string
  default = ""
}

variable "secrets_name" {
  type    = string
  default = ""
}

variable "layer_arns" {
  type    = list(string)
  default = []
}

variable "extra_env_vars" {
  type    = map(string)
  default = {}
}

variable "log_retention_days" {
  type    = number
  default = 14
}
```

```hcl
# terraform/modules/lambda/outputs.tf
output "function_name" {
  value = aws_lambda_function.function.function_name
}

output "function_arn" {
  value = aws_lambda_function.function.arn
}

output "invoke_arn" {
  value = aws_lambda_function.function.invoke_arn
}

output "role_arn" {
  value = aws_iam_role.lambda.arn
}
```
</module_structure>

<sqs_trigger>
## SQS Trigger

```hcl
# terraform/modules/lambda/sqs_trigger.tf

resource "aws_lambda_event_source_mapping" "sqs" {
  count = var.sqs_queue_arn != "" ? 1 : 0

  event_source_arn = var.sqs_queue_arn
  function_name    = aws_lambda_function.function.arn
  batch_size       = var.sqs_batch_size
  enabled          = true

  # For partial batch failure handling
  function_response_types = ["ReportBatchItemFailures"]
}
```
</sqs_trigger>

<eventbridge_schedule>
## EventBridge Schedule

```hcl
# terraform/modules/lambda/schedule.tf

resource "aws_cloudwatch_event_rule" "schedule" {
  count = var.schedule_expression != "" ? 1 : 0

  name                = "${var.function_name}-schedule"
  description         = "Schedule for ${var.function_name}"
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda" {
  count = var.schedule_expression != "" ? 1 : 0

  rule      = aws_cloudwatch_event_rule.schedule[0].name
  target_id = "lambda"
  arn       = aws_lambda_function.function.arn
}

resource "aws_lambda_permission" "eventbridge" {
  count = var.schedule_expression != "" ? 1 : 0

  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.function.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule[0].arn
}
```

```hcl
# In variables.tf
variable "schedule_expression" {
  type    = string
  default = ""  # e.g., "rate(5 minutes)" or "cron(0 12 * * ? *)"
}
```
</eventbridge_schedule>

<lambda_layer>
## Lambda Layer for Dependencies

```hcl
# terraform/modules/lambda-layer/main.tf

resource "aws_lambda_layer_version" "dependencies" {
  layer_name          = "${var.project_name}-${var.environment}-dependencies"
  description         = "Python dependencies layer"
  compatible_runtimes = ["python3.13"]

  filename         = data.archive_file.layer_zip.output_path
  source_code_hash = data.archive_file.layer_zip.output_base64sha256
}

data "archive_file" "layer_zip" {
  type        = "zip"
  source_dir  = var.layer_source_path
  output_path = "${path.module}/layer.zip"
}

output "layer_arn" {
  value = aws_lambda_layer_version.dependencies.arn
}
```

**Layer structure:**
```
layer/
└── python/
    └── lib/
        └── python3.13/
            └── site-packages/
                ├── pandas/
                ├── numpy/
                └── ccxt/
```
</lambda_layer>

<usage_example>
## Usage Example

```hcl
# terraform/environments/prod/main.tf

module "trading_lambda" {
  source = "../../modules/lambda"

  project_name  = var.project_name
  environment   = var.environment
  function_name = "trading-lambda"
  handler       = "tradingLambda.lambdaHandler"
  runtime       = "python3.13"
  timeout       = 60
  memory_size   = 512
  source_path   = "../../../app/lambda"

  s3_bucket     = module.s3.bucket_name
  s3_bucket_arn = module.s3.bucket_arn
  sns_topic_arn = module.sns_sqs.topic_arn
  secrets_arn   = module.secrets.secret_arn
  secrets_name  = module.secrets.secret_name

  layer_arns = [module.dependencies_layer.layer_arn]

  schedule_expression = "rate(5 minutes)"

  extra_env_vars = {
    LOG_LEVEL = "INFO"
  }
}

module "execution_lambda" {
  source = "../../modules/lambda"

  project_name  = var.project_name
  environment   = var.environment
  function_name = "execution-lambda"
  handler       = "executionLambda.lambdaHandler"
  runtime       = "python3.13"
  timeout       = 30
  memory_size   = 256
  source_path   = "../../../app/lambda"

  s3_bucket     = module.s3.bucket_name
  s3_bucket_arn = module.s3.bucket_arn
  sqs_queue_arn = module.sns_sqs.queue_arn
  secrets_arn   = module.secrets.secret_arn
  secrets_name  = module.secrets.secret_name

  layer_arns = [module.dependencies_layer.layer_arn]
}
```
</usage_example>
