<overview>
GitHub Actions CI/CD workflows for AWS deployment. Created on demand only. Includes testing, Terraform deployment, and Lambda updates.
</overview>

<basic_ci>
## Basic CI Workflow

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      localstack:
        image: localstack/localstack:latest
        ports:
          - 4566:4566
        env:
          SERVICES: s3,sns,sqs,secretsmanager

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install Poetry
        uses: snok/install-poetry@v1
        with:
          virtualenvs-create: true
          virtualenvs-in-project: true

      - name: Load cached venv
        uses: actions/cache@v4
        with:
          path: .venv
          key: venv-${{ runner.os }}-${{ hashFiles('**/poetry.lock') }}

      - name: Install dependencies
        run: poetry install --no-interaction

      - name: Run linter
        run: poetry run ruff check .

      - name: Run type checker
        run: poetry run mypy src/

      - name: Run tests
        env:
          DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
          AWS_ENDPOINT_URL: http://localhost:4566
          USE_LOCALSTACK: "true"
        run: poetry run pytest --cov --cov-fail-under=90
```
</basic_ci>

<deploy_workflow>
## Deploy to AWS Workflow

```yaml
# .github/workflows/deploy.yml
name: Deploy to AWS

on:
  push:
    branches: [main]
  workflow_dispatch:  # Manual trigger

env:
  AWS_REGION: us-east-1
  TF_VERSION: "1.7.0"

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production

    permissions:
      id-token: write  # For OIDC
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: ${{ env.TF_VERSION }}

      - name: Terraform Init
        working-directory: terraform/environments/prod
        run: terraform init

      - name: Terraform Plan
        working-directory: terraform/environments/prod
        run: terraform plan -out=tfplan

      - name: Terraform Apply
        working-directory: terraform/environments/prod
        run: terraform apply -auto-approve tfplan
```
</deploy_workflow>

<lambda_deploy>
## Lambda-Only Deploy

```yaml
# .github/workflows/deploy-lambda.yml
name: Deploy Lambda

on:
  push:
    branches: [main]
    paths:
      - "app/lambda/**"
  workflow_dispatch:

env:
  AWS_REGION: us-east-1

jobs:
  deploy-lambda:
    runs-on: ubuntu-latest
    environment: production

    permissions:
      id-token: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ env.AWS_REGION }}

      - name: Package Lambda
        run: |
          cd app/lambda
          pip install -r requirements.txt -t package/
          cp *.py package/
          cd package && zip -r ../lambda.zip .

      - name: Deploy Trading Lambda
        run: |
          aws lambda update-function-code \
            --function-name myapp-prod-trading-lambda \
            --zip-file fileb://app/lambda/lambda.zip

      - name: Deploy Execution Lambda
        run: |
          aws lambda update-function-code \
            --function-name myapp-prod-execution-lambda \
            --zip-file fileb://app/lambda/lambda.zip

      - name: Wait for update
        run: |
          aws lambda wait function-updated \
            --function-name myapp-prod-trading-lambda
          aws lambda wait function-updated \
            --function-name myapp-prod-execution-lambda
```
</lambda_deploy>

<oidc_setup>
## OIDC Setup for Secure AWS Access

No long-lived credentials. GitHub Actions assumes IAM role via OIDC.

**1. Create OIDC Provider in AWS:**
```hcl
# terraform/modules/github-oidc/main.tf

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_actions" {
  name = "${var.project_name}-github-actions"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          }
          StringLike = {
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_org}/${var.github_repo}:*"
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "github_actions" {
  role       = aws_iam_role.github_actions.name
  policy_arn = aws_iam_policy.github_actions.arn
}

resource "aws_iam_policy" "github_actions" {
  name = "${var.project_name}-github-actions-policy"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:UpdateFunctionCode",
          "lambda:GetFunction",
          "lambda:UpdateFunctionConfiguration"
        ]
        Resource = "arn:aws:lambda:${var.aws_region}:${data.aws_caller_identity.current.account_id}:function:${var.project_name}-*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket"
        ]
        Resource = [
          "arn:aws:s3:::${var.project_name}-terraform-state",
          "arn:aws:s3:::${var.project_name}-terraform-state/*"
        ]
      }
    ]
  })
}

output "role_arn" {
  value = aws_iam_role.github_actions.arn
}
```

**2. Add secret to GitHub:**
- Repository Settings → Secrets → Actions
- Add `AWS_ROLE_ARN` with the role ARN from Terraform output
</oidc_setup>

<pr_workflow>
## Pull Request Workflow

```yaml
# .github/workflows/pr.yml
name: Pull Request

on:
  pull_request:
    branches: [main]

jobs:
  test:
    uses: ./.github/workflows/ci.yml

  terraform-plan:
    runs-on: ubuntu-latest
    needs: test

    permissions:
      id-token: write
      contents: read
      pull-requests: write

    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: us-east-1

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        working-directory: terraform/environments/prod
        run: terraform init

      - name: Terraform Plan
        id: plan
        working-directory: terraform/environments/prod
        run: terraform plan -no-color
        continue-on-error: true

      - name: Comment Plan on PR
        uses: actions/github-script@v7
        with:
          script: |
            const output = `#### Terraform Plan 📖
            \`\`\`
            ${{ steps.plan.outputs.stdout }}
            \`\`\`
            `;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: output
            })
```
</pr_workflow>

<secrets_in_actions>
## GitHub Secrets Setup

**Required secrets:**
| Secret | Description |
|--------|-------------|
| `AWS_ROLE_ARN` | IAM role ARN for OIDC |

**Optional secrets (if not using OIDC):**
| Secret | Description |
|--------|-------------|
| `AWS_ACCESS_KEY_ID` | IAM access key |
| `AWS_SECRET_ACCESS_KEY` | IAM secret key |

**Configure in GitHub:**
1. Repository → Settings → Secrets and variables → Actions
2. Add repository secrets
</secrets_in_actions>
