"""Application service for one-shot provider connection tests."""

import time

from pydantic import SecretStr

from .contracts import ModelMessage, ModelRequest
from .errors import ProviderError
from .registry import ModelProviderRegistry
from .schemas import (
    ModelConnectionTestError,
    ModelConnectionTestRequest,
    ModelConnectionTestResponse,
)

CONNECTION_TEST_MAX_OUTPUT_TOKENS = 64


async def test_connection(
    payload: ModelConnectionTestRequest,
    registry: ModelProviderRegistry,
) -> ModelConnectionTestResponse:
    model = (
        payload.deployment_name
        if payload.provider == "azure_openai"
        else payload.model_name
    )
    if model is None:
        raise ValueError("model name is required")
    request = ModelRequest(
        provider=payload.provider,
        model=model,
        messages=(ModelMessage(role="user", content="Reply with exactly OK."),),
        # Azure Responses rejects values below 16; reasoning models also spend
        # part of this budget on internal reasoning before emitting "OK".
        max_output_tokens=CONNECTION_TEST_MAX_OUTPUT_TOKENS,
        stream=False,
    )
    try:
        registry.validate_request(request)
        provider = registry.resolve(payload.provider, base_url=payload.base_url)
        started = time.perf_counter()
        await provider.generate(request, payload.api_key.get_secret_value())
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        return ModelConnectionTestResponse(
            status="SUCCESS",
            provider=payload.provider,
            model_name=payload.model_name,
            latency_ms=latency_ms,
        )
    except ProviderError as error:
        return ModelConnectionTestResponse(
            status="FAILED",
            provider=payload.provider,
            model_name=payload.model_name,
            error=ModelConnectionTestError(code=error.code, message=error.safe_message),
        )
    finally:
        # Clear the mutable request model too, so callers cannot reuse this key.
        payload.api_key = SecretStr("")
