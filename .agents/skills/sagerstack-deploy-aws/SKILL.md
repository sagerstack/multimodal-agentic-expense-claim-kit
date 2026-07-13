---
name: sagerstack:deploy-aws
description: AWS infrastructure deployment with Terraform. Use when deploying to AWS, writing Terraform configurations, setting up CI/CD with GitHub Actions, or managing AWS resources (EKS, Lambda, S3, SNS, SQS, Secrets Manager).
---

<essential_principles>

## How AWS Deployment Works

These principles ALWAYS apply when deploying to AWS.

### 1. Terraform for Infrastructure

All AWS infrastructure is defined in Terraform. No manual AWS console changes.

```
terraform/
├── environments/
│   ├── local/              # LocalStack configuration
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── terraform.tfvars
│   └── prod/               # Production AWS
│       ├── main.tf
│       ├── variables.tf
│       └── terraform.tfvars
└── modules/                # Reusable modules
    ├── lambda/
    ├── s3/
    ├── sns-sqs/
    └── secrets/
```

### 2. Environment Separation

| Environment | Infrastructure | Secrets |
|-------------|----------------|---------|
| local | LocalStack | `.env.local` |
| prod | AWS | Secrets Manager |

**Never mix environments.** Each has its own Terraform state.

### 3. Secrets in AWS Secrets Manager

Production secrets are NEVER in code or environment files.

```hcl
# terraform/modules/secrets/main.tf
resource "aws_secretsmanager_secret" "app_secrets" {
  name = "${var.project_name}/${var.environment}/config"
}
```

```python
# Application code
if environment == "prod":
    secrets = secretsManager.getSecret("myapp/prod/config")
    apiKey = secrets["binanceApiKey"]
```

### 4. GitHub Actions for CI/CD (On Demand)

CI/CD pipelines are created only when explicitly requested.

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy with Terraform
        run: |
          cd terraform/environments/prod
          terraform init
          terraform apply -auto-approve
```

### 5. Two Environments Only

| Name | Purpose | Tools |
|------|---------|-------|
| `local` | Development, testing | Docker, LocalStack, Minikube |
| `prod` | Production | AWS services |

No staging, dev, or other environments. Keep it simple.

### 6. Module-Based Terraform

```hcl
# terraform/environments/prod/main.tf
module "lambda" {
  source = "../../modules/lambda"

  functionName = "trading-lambda"
  runtime      = "python3.13"
  handler      = "tradingLambda.lambdaHandler"
  # ...
}

module "s3" {
  source = "../../modules/s3"

  bucketName = "myapp-state"
  # ...
}
```

</essential_principles>

<intake>
**What would you like to do?**

1. Set up Terraform project structure
2. Deploy Lambda functions
3. Configure S3, SNS, SQS
4. Set up Secrets Manager
5. Create GitHub Actions CI/CD
6. Deploy to EKS (Kubernetes)
7. Something else

**Wait for response, then read the matching workflow.**
</intake>

<routing>
| Response | Workflow |
|----------|----------|
| 1, "setup", "terraform", "structure" | `workflows/setup-terraform.md` |
| 2, "lambda", "function", "serverless" | `workflows/deploy-lambda.md` |
| 3, "s3", "sns", "sqs", "messaging" | `workflows/configure-messaging.md` |
| 4, "secrets", "credentials" | `workflows/setup-secrets.md` |
| 5, "github", "ci/cd", "actions", "pipeline" | `workflows/setup-github-actions.md` |
| 6, "eks", "kubernetes", "k8s" | `workflows/deploy-eks.md` |
| 7, other | Clarify, then select workflow or references |
</routing>

<reference_index>
## Domain Knowledge

All in `references/`:

**Terraform:**
- terraform-structure.md — Project organization
- terraform-modules.md — Reusable module patterns
- terraform-state.md — State management

**AWS Services:**
- lambda.md — Lambda function deployment
- s3.md — S3 bucket configuration
- sns-sqs.md — Messaging infrastructure
- secrets-manager.md — Secrets management
- eks.md — Kubernetes deployment

**CI/CD:**
- github-actions.md — GitHub Actions workflows
</reference_index>

<workflows_index>
## Workflows

All in `workflows/`:

| File | Purpose |
|------|---------|
| setup-terraform.md | Initialize Terraform project |
| deploy-lambda.md | Deploy Lambda functions |
| configure-messaging.md | Set up S3, SNS, SQS |
| setup-secrets.md | Configure Secrets Manager |
| setup-github-actions.md | Create CI/CD pipelines |
| deploy-eks.md | Deploy to Kubernetes |
</workflows_index>

<verification>
## After Every Deployment

```bash
# 1. Terraform plan (review changes)
cd terraform/environments/prod
terraform plan

# 2. Apply changes
terraform apply

# 3. Verify resources
aws lambda list-functions
aws s3 ls
aws sns list-topics
aws sqs list-queues

# 4. Test the deployment
# (depends on what was deployed)
```
</verification>
