<overview>
Terraform project structure for AWS deployment. Environments-based organization with reusable modules. Supports local (LocalStack) and prod (AWS) environments.
</overview>

<directory_structure>
## Project Structure

```
terraform/
├── environments/
│   ├── local/                    # LocalStack configuration
│   │   ├── main.tf               # Root module
│   │   ├── variables.tf          # Variable definitions
│   │   ├── outputs.tf            # Output values
│   │   ├── terraform.tfvars      # Variable values
│   │   ├── providers.tf          # Provider configuration
│   │   └── backend.tf            # State backend (local)
│   │
│   └── prod/                     # Production AWS
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       ├── terraform.tfvars
│       ├── providers.tf
│       └── backend.tf            # State backend (S3)
│
└── modules/                      # Reusable modules
    ├── lambda/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── s3/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    ├── sns-sqs/
    │   ├── main.tf
    │   ├── variables.tf
    │   └── outputs.tf
    └── secrets/
        ├── main.tf
        ├── variables.tf
        └── outputs.tf
```
</directory_structure>

<local_environment>
## Local Environment (LocalStack)

```hcl
# terraform/environments/local/providers.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region                      = "us-east-1"
  access_key                  = "test"
  secret_key                  = "test"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    s3             = "http://localhost:4566"
    sns            = "http://localhost:4566"
    sqs            = "http://localhost:4566"
    secretsmanager = "http://localhost:4566"
    lambda         = "http://localhost:4566"
    iam            = "http://localhost:4566"
  }
}
```

```hcl
# terraform/environments/local/backend.tf
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
```

```hcl
# terraform/environments/local/variables.tf
variable "project_name" {
  description = "Project name"
  type        = string
  default     = "myapp"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "local"
}
```

```hcl
# terraform/environments/local/main.tf
module "s3" {
  source = "../../modules/s3"

  bucket_name = "${var.project_name}-${var.environment}-state"
  environment = var.environment
}

module "sns_sqs" {
  source = "../../modules/sns-sqs"

  project_name = var.project_name
  environment  = var.environment
  topic_name   = "order-events"
  queue_name   = "order-queue"
}
```
</local_environment>

<prod_environment>
## Production Environment (AWS)

```hcl
# terraform/environments/prod/providers.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
```

```hcl
# terraform/environments/prod/backend.tf
terraform {
  backend "s3" {
    bucket         = "myapp-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-locks"
  }
}
```

```hcl
# terraform/environments/prod/variables.tf
variable "project_name" {
  description = "Project name"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}
```

```hcl
# terraform/environments/prod/terraform.tfvars
project_name = "myapp"
environment  = "prod"
aws_region   = "us-east-1"
```

```hcl
# terraform/environments/prod/main.tf
module "s3" {
  source = "../../modules/s3"

  bucket_name = "${var.project_name}-${var.environment}-state"
  environment = var.environment
}

module "secrets" {
  source = "../../modules/secrets"

  project_name = var.project_name
  environment  = var.environment
}

module "sns_sqs" {
  source = "../../modules/sns-sqs"

  project_name = var.project_name
  environment  = var.environment
  topic_name   = "order-events"
  queue_name   = "order-queue"
}

module "lambda" {
  source = "../../modules/lambda"

  project_name     = var.project_name
  environment      = var.environment
  function_name    = "trading-lambda"
  handler          = "tradingLambda.lambdaHandler"
  runtime          = "python3.13"
  source_path      = "../../../app/lambda"
  s3_bucket        = module.s3.bucket_name
  sns_topic_arn    = module.sns_sqs.topic_arn
  secrets_arn      = module.secrets.secret_arn
}
```
</prod_environment>

<commands>
## Terraform Commands

```bash
# Initialize (first time or after provider changes)
cd terraform/environments/local  # or prod
terraform init

# Format code
terraform fmt -recursive

# Validate configuration
terraform validate

# Plan changes (dry run)
terraform plan

# Apply changes
terraform apply

# Apply with auto-approve (CI/CD)
terraform apply -auto-approve

# Destroy all resources
terraform destroy

# Show current state
terraform show

# List resources
terraform state list

# Import existing resource
terraform import aws_s3_bucket.bucket bucket-name
```
</commands>

<naming_conventions>
## Naming Conventions

**Resources:**
```hcl
# Pattern: {project}-{environment}-{resource}
resource "aws_s3_bucket" "state" {
  bucket = "${var.project_name}-${var.environment}-state"
}

# Examples:
# myapp-local-state
# myapp-prod-state
# myapp-prod-order-events (SNS topic)
# myapp-prod-order-queue (SQS queue)
```

**Variables:**
```hcl
# snake_case for variables
variable "project_name" {}
variable "environment" {}
variable "aws_region" {}
```

**Outputs:**
```hcl
# snake_case for outputs
output "bucket_name" {
  value = aws_s3_bucket.state.bucket
}

output "topic_arn" {
  value = aws_sns_topic.events.arn
}
```
</naming_conventions>
