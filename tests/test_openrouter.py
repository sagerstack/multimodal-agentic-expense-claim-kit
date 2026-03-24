"""Unit tests for OpenRouter client."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentic_claims.core.config import Settings
from agentic_claims.infrastructure.openrouter.client import OpenRouterClient


@pytest.fixture
def testSettings():
    """Create test settings with mock values."""
    return Settings(
        postgres_host="localhost",
        postgres_port=5432,
        postgres_db="test_db",
        postgres_user="test_user",
        postgres_password="test_pass",
        chainlit_host="localhost",
        chainlit_port=8000,
        app_env="test",
        openrouter_api_key="test-key",
        openrouter_model_llm="test-llm",
        openrouter_model_vlm="test-vlm",
        openrouter_base_url="https://test.openrouter.ai/api/v1",
        openrouter_max_retries=3,
        openrouter_retry_delay=0.1,
        qdrant_host="localhost",
        qdrant_port=6333,
    )


@pytest.fixture
def client(testSettings):
    """Create OpenRouterClient with test settings."""
    return OpenRouterClient(testSettings)


@pytest.mark.asyncio
async def testClientInstantiation(testSettings):
    """Test that OpenRouterClient can be instantiated."""
    client = OpenRouterClient(testSettings)
    assert client.settings == testSettings
    assert client.client is not None


@pytest.mark.asyncio
async def testCallLlmConstructsCorrectApiCall(client):
    """Test that callLlm constructs correct API call."""
    messages = [{"role": "user", "content": "test message"}]
    expected_response = "test response"

    # Mock the AsyncOpenAI client
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = expected_response

    with patch.object(client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
        result = await client.callLlm(messages)

        # Verify call was made with correct parameters
        client.client.chat.completions.create.assert_called_once_with(
            model="test-llm", messages=messages
        )
        assert result == expected_response


@pytest.mark.asyncio
async def testCallLlmRetryLogic(client):
    """Test that callLlm retries on failure."""
    messages = [{"role": "user", "content": "test"}]
    expected_response = "success"

    # Mock response for successful call
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = expected_response

    # Mock to fail twice then succeed on third attempt
    mock_create = AsyncMock(
        side_effect=[
            Exception("First failure"),
            Exception("Second failure"),
            mock_response,
        ]
    )

    with patch.object(client.client.chat.completions, "create", mock_create):
        with patch("asyncio.sleep", new=AsyncMock()):  # Skip actual delays
            result = await client.callLlm(messages)

            assert result == expected_response
            assert mock_create.call_count == 3


@pytest.mark.asyncio
async def testCallLlmRetryExhaustion(client):
    """Test that callLlm raises exception after max retries."""
    messages = [{"role": "user", "content": "test"}]

    # Mock to always fail
    mock_create = AsyncMock(side_effect=Exception("Always fails"))

    with patch.object(client.client.chat.completions, "create", mock_create):
        with patch("asyncio.sleep", new=AsyncMock()):  # Skip actual delays
            with pytest.raises(Exception, match="Always fails"):
                await client.callLlm(messages)

            # Should have tried max_retries times
            assert mock_create.call_count == 3


@pytest.mark.asyncio
async def testCallVlmBuildsCorrectMultimodalMessage(client):
    """Test that callVlm builds correct multimodal message format."""
    text = "What's in this image?"
    image_url = "https://example.com/image.jpg"
    expected_response = "VLM response"

    # Mock response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = expected_response

    with patch.object(client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
        result = await client.callVlm(text, image_url)

        # Verify the message structure passed to callLlm
        call_args = client.client.chat.completions.create.call_args
        messages = call_args.kwargs["messages"]

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][0] == {"type": "text", "text": text}
        assert messages[0]["content"][1] == {
            "type": "image_url",
            "image_url": {"url": image_url},
        }

        assert result == expected_response


@pytest.mark.asyncio
async def testCallLlmUsesCustomModel(client):
    """Test that callLlm accepts custom model override."""
    messages = [{"role": "user", "content": "test"}]
    custom_model = "custom-model-name"

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "response"

    with patch.object(client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
        await client.callLlm(messages, model=custom_model)

        # Verify custom model was used
        call_args = client.client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == custom_model


@pytest.mark.asyncio
async def testCallVlmUsesCustomModel(client):
    """Test that callVlm accepts custom model override."""
    custom_model = "custom-vlm"

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "response"

    with patch.object(client.client.chat.completions, "create", new=AsyncMock(return_value=mock_response)):
        await client.callVlm("test", "http://img.jpg", model=custom_model)

        # Verify custom model was used
        call_args = client.client.chat.completions.create.call_args
        assert call_args.kwargs["model"] == custom_model
