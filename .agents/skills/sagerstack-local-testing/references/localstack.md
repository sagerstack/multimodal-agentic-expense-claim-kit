<overview>
LocalStack setup for local AWS development. Provides S3, SNS, SQS, Lambda, Secrets Manager, and other AWS services locally via Docker.
</overview>

<docker_compose>
## Docker Compose Setup

```yaml
# docker-compose.yml
version: "3.8"

services:
  localstack:
    image: localstack/localstack:latest
    container_name: localstack
    ports:
      - "4566:4566"           # LocalStack Gateway
      - "4510-4559:4510-4559" # External services port range
    environment:
      - SERVICES=s3,sns,sqs,secretsmanager,events,lambda
      - DEBUG=1
      - DATA_DIR=/var/lib/localstack/data
      - LAMBDA_EXECUTOR=docker
      - DOCKER_HOST=unix:///var/run/docker.sock
    volumes:
      - "./localstack-data:/var/lib/localstack"
      - "/var/run/docker.sock:/var/run/docker.sock"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:4566/_localstack/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  postgres:
    image: postgres:15
    container_name: postgres
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=devuser
      - POSTGRES_PASSWORD=devpass
      - POSTGRES_DB=mydb_dev
    volumes:
      - postgres-data:/var/lib/postgresql/data

volumes:
  postgres-data:
```

**Start services:**
```bash
docker-compose up -d

# Wait for LocalStack to be ready
until curl -s http://localhost:4566/_localstack/health | grep -q '"s3": "running"'; do
  echo "Waiting for LocalStack..."
  sleep 2
done
echo "LocalStack ready!"
```
</docker_compose>

<aws_configuration>
## AWS Client Configuration

```python
# src/shared/infrastructure/aws.py
import boto3
import os
from functools import lru_cache

def getAwsClient(serviceName: str):
    """Get AWS client, using LocalStack endpoint if configured."""
    endpointUrl = os.environ.get("AWS_ENDPOINT_URL")
    useLocalstack = os.environ.get("USE_LOCALSTACK", "false").lower() == "true"

    if useLocalstack or endpointUrl:
        return boto3.client(
            serviceName,
            endpoint_url=endpointUrl or "http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
            region_name=os.environ.get("AWS_REGION", "us-east-1")
        )

    return boto3.client(serviceName)

@lru_cache
def getS3Client():
    return getAwsClient("s3")

@lru_cache
def getSnsClient():
    return getAwsClient("sns")

@lru_cache
def getSqsClient():
    return getAwsClient("sqs")

@lru_cache
def getSecretsClient():
    return getAwsClient("secretsmanager")
```

**.env.local:**
```bash
USE_LOCALSTACK=true
AWS_ENDPOINT_URL=http://localhost:4566
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
```
</aws_configuration>

<s3_operations>
## S3 Operations

```python
# src/shared/infrastructure/s3Repository.py
import json
from .aws import getS3Client

class S3StateRepository:
    def __init__(self, bucket: str, key: str, client=None):
        self._bucket = bucket
        self._key = key
        self._client = client or getS3Client()

    def save(self, state: dict) -> None:
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._key,
            Body=json.dumps(state),
            ContentType="application/json"
        )

    def load(self) -> dict | None:
        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=self._key
            )
            return json.loads(response["Body"].read().decode("utf-8"))
        except self._client.exceptions.NoSuchKey:
            return None
```

**Create bucket (LocalStack):**
```bash
aws --endpoint-url=http://localhost:4566 s3 mb s3://my-bucket
aws --endpoint-url=http://localhost:4566 s3 ls
```
</s3_operations>

<sns_sqs_operations>
## SNS/SQS Operations

```python
# src/shared/infrastructure/messaging.py
import json
from .aws import getSnsClient, getSqsClient

class SnsPublisher:
    def __init__(self, topicArn: str, client=None):
        self._topicArn = topicArn
        self._client = client or getSnsClient()

    def publish(self, message: dict) -> str:
        response = self._client.publish(
            TopicArn=self._topicArn,
            Message=json.dumps(message),
            MessageAttributes={
                "messageType": {
                    "DataType": "String",
                    "StringValue": message.get("type", "unknown")
                }
            }
        )
        return response["MessageId"]

class SqsConsumer:
    def __init__(self, queueUrl: str, client=None):
        self._queueUrl = queueUrl
        self._client = client or getSqsClient()

    def receiveMessages(self, maxMessages: int = 10) -> list[dict]:
        response = self._client.receive_message(
            QueueUrl=self._queueUrl,
            MaxNumberOfMessages=maxMessages,
            WaitTimeSeconds=5
        )
        return response.get("Messages", [])

    def deleteMessage(self, receiptHandle: str) -> None:
        self._client.delete_message(
            QueueUrl=self._queueUrl,
            ReceiptHandle=receiptHandle
        )
```

**Setup SNS/SQS (LocalStack):**
```bash
# Create topic
aws --endpoint-url=http://localhost:4566 sns create-topic --name my-topic

# Create queue
aws --endpoint-url=http://localhost:4566 sqs create-queue --queue-name my-queue

# Subscribe queue to topic
aws --endpoint-url=http://localhost:4566 sns subscribe \
  --topic-arn arn:aws:sns:us-east-1:000000000000:my-topic \
  --protocol sqs \
  --notification-endpoint arn:aws:sqs:us-east-1:000000000000:my-queue
```
</sns_sqs_operations>

<secrets_manager>
## Secrets Manager

```python
# src/shared/infrastructure/secrets.py
import json
from .aws import getSecretsClient

class SecretsManager:
    def __init__(self, client=None):
        self._client = client or getSecretsClient()

    def getSecret(self, secretName: str) -> dict:
        response = self._client.get_secret_value(SecretId=secretName)
        return json.loads(response["SecretString"])

    def createSecret(self, secretName: str, secretValue: dict) -> None:
        self._client.create_secret(
            Name=secretName,
            SecretString=json.dumps(secretValue)
        )
```

**Setup secrets (LocalStack):**
```bash
aws --endpoint-url=http://localhost:4566 secretsmanager create-secret \
  --name myapp/database \
  --secret-string '{"url":"postgresql://user:pass@localhost:5432/db"}'

aws --endpoint-url=http://localhost:4566 secretsmanager get-secret-value \
  --secret-id myapp/database
```
</secrets_manager>

<testing_with_localstack>
## Testing with LocalStack

```python
# tests/integration/conftest.py
import pytest
import boto3
import os

@pytest.fixture(scope="module")
def localstackEndpoint():
    return os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")

@pytest.fixture(scope="module")
def s3Client(localstackEndpoint):
    return boto3.client(
        "s3",
        endpoint_url=localstackEndpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1"
    )

@pytest.fixture(scope="module")
def testBucket(s3Client):
    bucketName = "test-bucket"
    s3Client.create_bucket(Bucket=bucketName)
    yield bucketName

    # Cleanup
    response = s3Client.list_objects_v2(Bucket=bucketName)
    for obj in response.get("Contents", []):
        s3Client.delete_object(Bucket=bucketName, Key=obj["Key"])
    s3Client.delete_bucket(Bucket=bucketName)

@pytest.fixture(scope="module")
def snsClient(localstackEndpoint):
    return boto3.client(
        "sns",
        endpoint_url=localstackEndpoint,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name="us-east-1"
    )

@pytest.fixture(scope="module")
def testTopic(snsClient):
    response = snsClient.create_topic(Name="test-topic")
    topicArn = response["TopicArn"]
    yield topicArn
    snsClient.delete_topic(TopicArn=topicArn)
```

```python
# tests/integration/localstack/testS3Repository.py
import pytest
from src.shared.infrastructure.s3Repository import S3StateRepository

@pytest.mark.integration
@pytest.mark.localstack
class TestS3StateRepository:
    def testSaveAndLoad(self, s3Client, testBucket):
        repo = S3StateRepository(
            bucket=testBucket,
            key="state.json",
            client=s3Client
        )
        state = {"version": 1, "data": "test"}

        repo.save(state)
        loaded = repo.load()

        assert loaded == state

    def testLoadNonExistent(self, s3Client, testBucket):
        repo = S3StateRepository(
            bucket=testBucket,
            key="nonexistent.json",
            client=s3Client
        )

        result = repo.load()

        assert result is None
```
</testing_with_localstack>

<verification>
## Verifying LocalStack

```bash
# Check health
curl http://localhost:4566/_localstack/health

# List S3 buckets
aws --endpoint-url=http://localhost:4566 s3 ls

# List SNS topics
aws --endpoint-url=http://localhost:4566 sns list-topics

# List SQS queues
aws --endpoint-url=http://localhost:4566 sqs list-queues

# List secrets
aws --endpoint-url=http://localhost:4566 secretsmanager list-secrets
```
</verification>
