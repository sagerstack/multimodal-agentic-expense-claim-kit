<overview>
AWS Secrets Manager configuration with Terraform. Secure storage for API keys, database credentials, and other sensitive configuration.
</overview>

<module_structure>
## Secrets Module

```hcl
# terraform/modules/secrets/main.tf

resource "aws_secretsmanager_secret" "app_secrets" {
  name        = "${var.project_name}/${var.environment}/config"
  description = "Application secrets for ${var.project_name} ${var.environment}"

  recovery_window_in_days = var.recovery_window

  tags = {
    Project     = var.project_name
    Environment = var.environment
  }
}

# Initial secret value (should be updated manually or via CI/CD)
resource "aws_secretsmanager_secret_version" "app_secrets" {
  secret_id = aws_secretsmanager_secret.app_secrets.id

  secret_string = jsonencode({
    binanceApiKey    = var.initial_binance_api_key
    binanceApiSecret = var.initial_binance_api_secret
    databaseUrl      = var.initial_database_url
  })

  lifecycle {
    ignore_changes = [secret_string]  # Don't overwrite manual updates
  }
}
```

```hcl
# terraform/modules/secrets/variables.tf
variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "recovery_window" {
  type    = number
  default = 7  # Days before permanent deletion
}

# Initial values (can be placeholder, updated manually)
variable "initial_binance_api_key" {
  type    = string
  default = "PLACEHOLDER"
}

variable "initial_binance_api_secret" {
  type    = string
  default = "PLACEHOLDER"
}

variable "initial_database_url" {
  type    = string
  default = "PLACEHOLDER"
}
```

```hcl
# terraform/modules/secrets/outputs.tf
output "secret_arn" {
  value = aws_secretsmanager_secret.app_secrets.arn
}

output "secret_name" {
  value = aws_secretsmanager_secret.app_secrets.name
}

output "secret_id" {
  value = aws_secretsmanager_secret.app_secrets.id
}
```
</module_structure>

<reading_secrets>
## Reading Secrets in Application

```python
# src/shared/infrastructure/secrets.py
import boto3
import json
import os
from functools import lru_cache

class SecretsManager:
    def __init__(self, region: str = None):
        self._region = region or os.environ.get("AWS_REGION", "us-east-1")
        endpointUrl = os.environ.get("AWS_ENDPOINT_URL")  # LocalStack

        if endpointUrl:
            self._client = boto3.client(
                "secretsmanager",
                endpoint_url=endpointUrl,
                region_name=self._region,
                aws_access_key_id="test",
                aws_secret_access_key="test"
            )
        else:
            self._client = boto3.client(
                "secretsmanager",
                region_name=self._region
            )

    def getSecret(self, secretName: str) -> dict:
        response = self._client.get_secret_value(SecretId=secretName)
        return json.loads(response["SecretString"])

@lru_cache
def getSecretsManager() -> SecretsManager:
    return SecretsManager()

# Usage in production
def getProductionConfig():
    environment = os.environ.get("ENVIRONMENT", "local")

    if environment == "prod":
        secretName = os.environ.get("SECRETS_NAME", "myapp/prod/config")
        secrets = getSecretsManager().getSecret(secretName)
        return {
            "binanceApiKey": secrets["binanceApiKey"],
            "binanceApiSecret": secrets["binanceApiSecret"],
            "databaseUrl": secrets["databaseUrl"]
        }
    else:
        # Local: use environment variables
        return {
            "binanceApiKey": os.environ["BINANCE_API_KEY"],
            "binanceApiSecret": os.environ["BINANCE_API_SECRET"],
            "databaseUrl": os.environ["DATABASE_URL"]
        }
```
</reading_secrets>

<lambda_integration>
## Lambda Integration

```hcl
# In Lambda module - grant access to secrets
resource "aws_iam_role_policy" "lambda_secrets" {
  name = "${var.function_name}-secrets"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
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
```

```python
# app/lambda/tradingLambda.py
import os
from src.shared.infrastructure.secrets import getProductionConfig

def lambdaHandler(event, context):
    config = getProductionConfig()

    apiKey = config["binanceApiKey"]
    apiSecret = config["binanceApiSecret"]

    # Use credentials...
```
</lambda_integration>

<updating_secrets>
## Updating Secrets

**Via AWS CLI:**
```bash
# Update secret value
aws secretsmanager put-secret-value \
  --secret-id myapp/prod/config \
  --secret-string '{
    "binanceApiKey": "new-key",
    "binanceApiSecret": "new-secret",
    "databaseUrl": "postgresql://..."
  }'

# Get current value
aws secretsmanager get-secret-value \
  --secret-id myapp/prod/config \
  --query SecretString \
  --output text | jq .
```

**Via GitHub Actions (secure):**
```yaml
# .github/workflows/update-secrets.yml
name: Update Secrets

on:
  workflow_dispatch:
    inputs:
      secret_key:
        description: "Secret key to update"
        required: true
        type: choice
        options:
          - binanceApiKey
          - binanceApiSecret
          - databaseUrl
      secret_value:
        description: "New secret value"
        required: true

jobs:
  update:
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Update secret
        run: |
          # Get current secret
          CURRENT=$(aws secretsmanager get-secret-value \
            --secret-id myapp/prod/config \
            --query SecretString \
            --output text)

          # Update specific key
          UPDATED=$(echo $CURRENT | jq --arg key "${{ inputs.secret_key }}" --arg val "${{ inputs.secret_value }}" '.[$key] = $val')

          # Put updated secret
          aws secretsmanager put-secret-value \
            --secret-id myapp/prod/config \
            --secret-string "$UPDATED"
```
</updating_secrets>

<rotation>
## Secret Rotation (Optional)

```hcl
# Enable automatic rotation (advanced)
resource "aws_secretsmanager_secret_rotation" "app_secrets" {
  secret_id           = aws_secretsmanager_secret.app_secrets.id
  rotation_lambda_arn = aws_lambda_function.rotation.arn

  rotation_rules {
    automatically_after_days = 30
  }
}
```
</rotation>

<localstack_testing>
## LocalStack Testing

```bash
# Create secret in LocalStack
aws --endpoint-url=http://localhost:4566 secretsmanager create-secret \
  --name myapp/local/config \
  --secret-string '{
    "binanceApiKey": "test-key",
    "binanceApiSecret": "test-secret",
    "databaseUrl": "postgresql://devuser:devpass@localhost:5432/mydb_dev"
  }'

# Get secret
aws --endpoint-url=http://localhost:4566 secretsmanager get-secret-value \
  --secret-id myapp/local/config
```
</localstack_testing>
