<overview>
SNS and SQS configuration with Terraform. SNS topics for publishing events, SQS queues for reliable message delivery with dead-letter queues.
</overview>

<module_structure>
## SNS/SQS Module

```hcl
# terraform/modules/sns-sqs/main.tf

# SNS Topic
resource "aws_sns_topic" "events" {
  name = "${var.project_name}-${var.environment}-${var.topic_name}"
}

# SQS Queue
resource "aws_sqs_queue" "queue" {
  name                       = "${var.project_name}-${var.environment}-${var.queue_name}"
  visibility_timeout_seconds = var.visibility_timeout
  message_retention_seconds  = var.message_retention
  receive_wait_time_seconds  = var.receive_wait_time

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = var.max_receive_count
  })
}

# Dead Letter Queue
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project_name}-${var.environment}-${var.queue_name}-dlq"
  message_retention_seconds = 1209600  # 14 days
}

# SQS Queue Policy - Allow SNS to send messages
resource "aws_sqs_queue_policy" "queue_policy" {
  queue_url = aws_sqs_queue.queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Principal = "*"
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.events.arn
          }
        }
      }
    ]
  })
}

# SNS to SQS Subscription
resource "aws_sns_topic_subscription" "sqs" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.queue.arn

  # Enable raw message delivery (no SNS wrapper)
  raw_message_delivery = var.raw_message_delivery
}
```

```hcl
# terraform/modules/sns-sqs/variables.tf
variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "topic_name" {
  type = string
}

variable "queue_name" {
  type = string
}

variable "visibility_timeout" {
  type    = number
  default = 60  # Should be >= Lambda timeout
}

variable "message_retention" {
  type    = number
  default = 345600  # 4 days
}

variable "receive_wait_time" {
  type    = number
  default = 20  # Long polling
}

variable "max_receive_count" {
  type    = number
  default = 3  # Retries before DLQ
}

variable "raw_message_delivery" {
  type    = bool
  default = true
}
```

```hcl
# terraform/modules/sns-sqs/outputs.tf
output "topic_arn" {
  value = aws_sns_topic.events.arn
}

output "topic_name" {
  value = aws_sns_topic.events.name
}

output "queue_arn" {
  value = aws_sqs_queue.queue.arn
}

output "queue_url" {
  value = aws_sqs_queue.queue.url
}

output "queue_name" {
  value = aws_sqs_queue.queue.name
}

output "dlq_arn" {
  value = aws_sqs_queue.dlq.arn
}

output "dlq_url" {
  value = aws_sqs_queue.dlq.url
}
```
</module_structure>

<usage>
## Usage Example

```hcl
# terraform/environments/prod/main.tf

module "order_messaging" {
  source = "../../modules/sns-sqs"

  project_name = var.project_name
  environment  = var.environment
  topic_name   = "order-events"
  queue_name   = "order-queue"

  visibility_timeout = 120  # Match Lambda timeout + buffer
  max_receive_count  = 3    # Retry 3 times before DLQ
}

# Use outputs in Lambda module
module "execution_lambda" {
  source = "../../modules/lambda"

  # ...
  sqs_queue_arn = module.order_messaging.queue_arn
  sns_topic_arn = module.order_messaging.topic_arn
}
```
</usage>

<multiple_subscriptions>
## Multiple Queue Subscriptions

```hcl
# For different Lambda functions processing different message types

resource "aws_sqs_queue" "trading_queue" {
  name = "${var.project_name}-${var.environment}-trading-queue"
  # ...
}

resource "aws_sqs_queue" "notification_queue" {
  name = "${var.project_name}-${var.environment}-notification-queue"
  # ...
}

# Filter by message attributes
resource "aws_sns_topic_subscription" "trading" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.trading_queue.arn

  filter_policy = jsonencode({
    messageType = ["order.placed", "order.executed"]
  })
}

resource "aws_sns_topic_subscription" "notification" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.notification_queue.arn

  filter_policy = jsonencode({
    messageType = ["order.failed", "alert"]
  })
}
```
</multiple_subscriptions>

<dlq_alarm>
## CloudWatch Alarm for DLQ

```hcl
resource "aws_cloudwatch_metric_alarm" "dlq_alarm" {
  alarm_name          = "${var.project_name}-${var.environment}-dlq-messages"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  alarm_description   = "Messages in DLQ - requires investigation"
  treat_missing_data  = "notBreaching"

  dimensions = {
    QueueName = aws_sqs_queue.dlq.name
  }

  alarm_actions = [var.alert_sns_topic_arn]
}
```
</dlq_alarm>
