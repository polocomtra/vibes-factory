from collections.abc import Callable
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from openai import AsyncOpenAI

from apps.api.app.model_providers.contracts import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
)
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


class FakeGeminiClient:
    def __init__(self, response: object) -> None:
        self.aio = SimpleNamespace(
            interactions=SimpleNamespace(create=AsyncMock(return_value=response)),
            aclose=AsyncMock(),
        )


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

    azure_request = request("azure_openai", "gpt-5.6-luna").model_copy(
        update={"temperature": 0.2}
    )
    result = await provider.generate(azure_request, "temporary-key")

    assert result.content == "OK"
    assert result.usage is not None and result.usage.total_tokens == 3
    client.responses.create.assert_awaited_once()
    kwargs = client.responses.create.await_args.kwargs
    assert kwargs["model"] == "gpt-5.6-luna"
    assert kwargs["store"] is False
    assert kwargs["input"] == "hello"
    assert "temperature" not in kwargs
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_azure_stream_normalizes_text_deltas_and_completed_response() -> None:
    completed = SimpleNamespace(
        output_text="Hello world",
        output=[],
        usage=SimpleNamespace(input_tokens=2, output_tokens=2, total_tokens=4),
        status="completed",
        model="gpt-5.6-luna",
    )

    async def events():
        yield SimpleNamespace(type="response.output_text.delta", delta="Hello ")
        yield SimpleNamespace(type="response.output_text.delta", delta="world")
        yield SimpleNamespace(type="response.completed", response=completed)

    client = FakeOpenAIClient(events())
    factory = cast(Callable[..., AsyncOpenAI], lambda **kwargs: client)
    provider = AzureOpenAIProvider(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        client_factory=factory,
    )
    stream_request = request("azure_openai", "gpt-5.6-luna").model_copy(
        update={"stream": True}
    )

    normalized = [
        event async for event in provider.stream(stream_request, "temporary-key")
    ]

    assert [event.type for event in normalized] == [
        "text_delta",
        "text_delta",
        "completed",
    ]
    assert [event.text for event in normalized[:2]] == ["Hello ", "world"]
    assert normalized[-1].response is not None
    assert normalized[-1].response.content == "Hello world"
    kwargs = client.responses.create.await_args.kwargs
    assert kwargs["stream"] is True
    client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_azure_stream_keeps_usable_incomplete_text_response() -> None:
    incomplete = SimpleNamespace(
        output_text="A useful partial answer",
        output=[],
        usage=SimpleNamespace(input_tokens=12, output_tokens=8, total_tokens=20),
        status="incomplete",
        incomplete_details=SimpleNamespace(reason="max_output_tokens"),
    )

    async def events():
        yield SimpleNamespace(type="response.output_text.delta", delta="A useful ")
        yield SimpleNamespace(type="response.output_text.delta", delta="partial answer")
        yield SimpleNamespace(type="response.incomplete", response=incomplete)

    client = FakeOpenAIClient(events())
    provider = AzureOpenAIProvider(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        client_factory=cast(Callable[..., AsyncOpenAI], lambda **kwargs: client),
    )
    stream_request = request("azure_openai", "gpt-5.6-luna").model_copy(
        update={"stream": True}
    )

    normalized = [
        event async for event in provider.stream(stream_request, "temporary-key")
    ]

    assert normalized[-1].type == "completed"
    assert normalized[-1].response is not None
    assert normalized[-1].response.content == "A useful partial answer"
    assert normalized[-1].response.finish_reason == "LENGTH"


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
    response = SimpleNamespace(
        output_text="OK",
        id="interaction_1",
        model="gemini-2.5-flash",
        status="completed",
        usage=SimpleNamespace(
            total_input_tokens=2,
            total_output_tokens=1,
            total_tokens=3,
        ),
    )
    client = FakeGeminiClient(response)
    provider = GeminiProvider(client_factory=lambda **kwargs: client)
    result = await provider.generate(
        request("google", "gemini-2.5-flash"), "temporary-key"
    )

    assert result.content == "OK"
    assert result.finish_reason is None
    assert result.provider_metadata["interactionId"] == "interaction_1"
    assert result.usage is not None and result.usage.total_tokens == 3
    client.aio.interactions.create.assert_awaited_once()
    kwargs = client.aio.interactions.create.await_args.kwargs
    assert kwargs["model"] == "gemini-2.5-flash"
    assert kwargs["input"][0] == {
        "type": "user_input",
        "content": [{"type": "text", "text": "hello"}],
    }
    assert kwargs["generation_config"]["max_output_tokens"] == 8
    assert kwargs["store"] is False
    assert kwargs["stream"] is False
    client.aio.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_3_8_omits_legacy_temperature_parameter() -> None:
    response = SimpleNamespace(
        output_text="OK",
    )
    client = FakeGeminiClient(response)
    provider = GeminiProvider(client_factory=lambda **kwargs: client)
    gemini_request = request("google", "gemini-3.8-flash").model_copy(
        update={"temperature": 0.2}
    )

    await provider.generate(gemini_request, "temporary-key")

    kwargs = client.aio.interactions.create.await_args.kwargs
    assert "temperature" not in kwargs
    assert "temperature" not in kwargs["generation_config"]


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

    from apps.api.app.model_providers.catalog import find_model, list_models

    default = next(model for model in list_models() if model.is_default)
    registry = ModelProviderRegistry(
        gemini_api_key=SecretStr("gemini-environment-key"),
        azure_openai_api_key=SecretStr("environment-key"),
        azure_openai_base_url="https://resource.services.ai.azure.com/openai/v1",
    )

    assert (default.provider, default.name) == ("azure_openai", "gpt-5.6-luna")
    assert [(model.provider, model.name) for model in list_models()] == [
        ("azure_openai", "gpt-5.6-luna")
    ]
    assert find_model("google", "gemini-3.8-flash") is None
    assert registry.builtin_api_key("azure_openai") == "environment-key"
    assert registry.builtin_api_key("google") == "gemini-environment-key"
    assert registry.resolve("azure_openai").provider_id == "azure_openai"
    assert registry.resolve("google").provider_id == "google"


@pytest.mark.asyncio
async def test_fake_provider_uses_platform_contract_without_network() -> None:
    provider = FakeModelProvider()
    result = await provider.generate(request("fake"), "ignored")
    assert result.content == "OK"
    assert provider.requests == [request("fake")]


@pytest.mark.asyncio
async def test_fake_provider_stream_is_deterministic() -> None:
    provider = FakeModelProvider(
        response_factory=lambda _: ModelResponse(
            content="stream me", finish_reason="STOP"
        ),
        stream_chunk_size=3,
    )
    stream_request = request("fake").model_copy(update={"stream": True})

    events = [event async for event in provider.stream(stream_request, "ignored")]

    assert [event.text for event in events[:-1]] == ["str", "eam", " me"]
    assert events[-1].type == "completed"
    assert events[-1].response is not None
    assert events[-1].response.content == "stream me"
    assert provider.stream_requests == [stream_request]
