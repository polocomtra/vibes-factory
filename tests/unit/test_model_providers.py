from collections.abc import Callable
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest
from openai import AsyncOpenAI

from apps.api.app.model_providers.contracts import ModelMessage, ModelRequest
from apps.api.app.model_providers.errors import ProviderError
from apps.api.app.model_providers.fake import FakeModelProvider
from apps.api.app.model_providers.providers.deepseek import DeepSeekProvider
from apps.api.app.model_providers.providers.gemini import GeminiProvider
from apps.api.app.model_providers.providers.openai import (
    AzureOpenAIProvider,
    OpenAIProvider,
)
from apps.api.app.model_providers.registry import ModelProviderRegistry
from apps.api.app.model_providers.service import CONNECTION_TEST_MAX_OUTPUT_TOKENS


def request(provider: str, model: str = "custom-model") -> ModelRequest:
    return ModelRequest(
        provider=provider,
        model=model,
        messages=(ModelMessage(role="user", content="hello"),),
        max_output_tokens=8,
    )


class FakeOpenAIClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.responses = SimpleNamespace(create=AsyncMock(return_value=response))
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=response))
        )
        self.close = AsyncMock()


@pytest.mark.asyncio
async def test_azure_uses_custom_endpoint_deployment_and_responses_api() -> None:
    response = SimpleNamespace(
        output_text="OK",
        output=[],
        usage=SimpleNamespace(input_tokens=2, output_tokens=1, total_tokens=3),
        status="completed",
        model="gpt-5.6-luna",
    )
    client = FakeOpenAIClient(response)
    factory = cast(Callable[..., AsyncOpenAI], lambda **kwargs: client)
    provider = AzureOpenAIProvider(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        client_factory=factory,
    )

    result = await provider.generate(
        request("azure_openai", "gpt-5.6-luna"), "temporary-key"
    )

    assert result.content == "OK"
    assert result.usage is not None and result.usage.total_tokens == 3
    client.responses.create.assert_awaited_once()
    kwargs = client.responses.create.await_args.kwargs
    assert kwargs["model"] == "gpt-5.6-luna"
    assert kwargs["store"] is False
    assert kwargs["input"] == "hello"
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_openai_response_fallback_normalizes_tool_call() -> None:
    response = SimpleNamespace(
        output_text=None,
        output=[
            SimpleNamespace(
                type="message",
                content=[SimpleNamespace(type="output_text", text="done")],
            ),
            SimpleNamespace(
                type="function_call",
                call_id="call_1",
                name="lookup",
                arguments='{"city": "Paris"}',
            ),
        ],
        status="completed",
    )
    client = FakeOpenAIClient(response)
    provider = OpenAIProvider(
        client_factory=cast(Callable[..., AsyncOpenAI], lambda **kwargs: client)
    )

    result = await provider.generate(request("openai"), "temporary-key")

    assert result.content == "done"
    assert result.tool_calls[0].arguments == {"city": "Paris"}
    assert result.finish_reason == "TOOL_CALLS"


@pytest.mark.asyncio
async def test_deepseek_maps_chat_completion_and_forces_non_streaming() -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="OK", tool_calls=[]),
                finish_reason="stop",
            )
        ],
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=1, total_tokens=4),
        model="deepseek-flash",
    )
    client = FakeOpenAIClient(response)
    provider = DeepSeekProvider(
        client_factory=cast(Callable[..., AsyncOpenAI], lambda **kwargs: client)
    )

    result = await provider.generate(
        request("deepseek", "deepseek-flash"), "temporary-key"
    )

    assert result.content == "OK"
    assert result.usage is not None and result.usage.input_tokens == 3
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["stream"] is False
    assert kwargs["max_tokens"] == 8
    assert kwargs["messages"] == [{"role": "user", "content": "hello"}]


@pytest.mark.asyncio
async def test_gemini_normalizes_text_usage_and_model_finish_reason() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "responseId": "resp_1",
                "modelVersion": "gemini-2.5-flash",
                "candidates": [
                    {"content": {"parts": [{"text": "OK"}]}, "finishReason": "STOP"}
                ],
                "usageMetadata": {
                    "promptTokenCount": 2,
                    "candidatesTokenCount": 1,
                    "totalTokenCount": 3,
                },
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        result = await GeminiProvider(http_client=client).generate(
            request("google", "gemini-2.5-flash"), "temporary-key"
        )

    assert result.content == "OK"
    assert result.finish_reason == "STOP"
    assert result.provider_metadata["responseId"] == "resp_1"


def test_registry_rejects_invalid_azure_base_url() -> None:
    with pytest.raises(ProviderError) as error:
        ModelProviderRegistry().resolve(
            "azure_openai", base_url="http://localhost/openai/v1"
        )
    assert error.value.code == "MODEL_REQUEST_INVALID"


def test_provider_missing_key_is_stable_and_safe() -> None:
    with pytest.raises(ProviderError) as error:
        OpenAIProvider()._client(" ")
    assert error.value.code == "PROVIDER_CREDENTIAL_MISSING"
    assert "temporary-key" not in str(error.value)


def test_connection_probe_uses_azure_compatible_output_limit() -> None:
    assert CONNECTION_TEST_MAX_OUTPUT_TOKENS >= 16


def test_azure_model_is_backend_default_and_uses_configured_endpoint() -> None:
    from pydantic import SecretStr

    from apps.api.app.model_providers.catalog import list_models

    default = next(model for model in list_models() if model.is_default)
    registry = ModelProviderRegistry(
        azure_openai_api_key=SecretStr("environment-key"),
        azure_openai_base_url="https://resource.services.ai.azure.com/openai/v1",
    )

    assert (default.provider, default.name) == ("azure_openai", "gpt-5.6-luna")
    assert registry.builtin_api_key("azure_openai") == "environment-key"
    assert registry.resolve("azure_openai").provider_id == "azure_openai"


@pytest.mark.asyncio
async def test_fake_provider_uses_platform_contract_without_network() -> None:
    provider = FakeModelProvider()
    result = await provider.generate(request("fake"), "ignored")
    assert result.content == "OK"
    assert provider.requests == [request("fake")]
