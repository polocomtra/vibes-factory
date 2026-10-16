"""Application service for one-shot provider connection tests."""

import json
import time

from pydantic import SecretStr

from .contracts import ModelMessage, ModelRequest, ModelTool
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
    *,
    pinned_addresses: tuple[str, ...] | None = None,
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
        provider = registry.resolve(
            payload.provider,
            base_url=payload.base_url,
            pinned_addresses=pinned_addresses,
        )
        started = time.perf_counter()
        await provider.generate(request, payload.api_key.get_secret_value())
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        capabilities: dict[str, bool] | None = None
        if payload.probe_planning:
            strict_request = ModelRequest(
                provider=payload.provider,
                model=model,
                messages=(
                    ModelMessage(role="user", content='Return {"supported": true}.'),
                ),
                response_schema={
                    "type": "object",
                    "properties": {"supported": {"type": "boolean"}},
                    "required": ["supported"],
                    "additionalProperties": False,
                },
                max_output_tokens=128,
            )
            registry.validate_request(strict_request)
            strict_response = await provider.generate(
                strict_request, payload.api_key.get_secret_value()
            )
            try:
                strict_payload = json.loads(strict_response.content)
            except json.JSONDecodeError:
                raise ProviderError(
                    "PROVIDER_INVALID_RESPONSE",
                    "The provider did not return a valid structured "
                    "capability response.",
                ) from None
            if (
                not isinstance(strict_payload, dict)
                or strict_payload.get("supported") is not True
            ):
                raise ProviderError(
                    "PROVIDER_INVALID_RESPONSE",
                    "The provider did not return a valid structured "
                    "capability response.",
                )
            tool_request = ModelRequest(
                provider=payload.provider,
                model=model,
                messages=(
                    ModelMessage(role="user", content="Call the probe function."),
                ),
                tools=(
                    ModelTool(
                        name="capability_probe",
                        description="Return a capability probe result.",
                        parameters={
                            "type": "object",
                            "properties": {"ok": {"type": "boolean"}},
                            "required": ["ok"],
                            "additionalProperties": False,
                        },
                    ),
                ),
                max_output_tokens=128,
            )
            registry.validate_request(tool_request)
            tool_response = await provider.generate(
                tool_request, payload.api_key.get_secret_value()
            )
            capabilities = {
                "structured_output": True,
                "tool_calling": bool(
                    tool_response.tool_calls
                    and tool_response.tool_calls[0].name == "capability_probe"
                    and tool_response.tool_calls[0].arguments.get("ok") is True
                ),
            }
        return ModelConnectionTestResponse(
            status="SUCCESS",
            provider=payload.provider,
            model_name=payload.model_name,
            latency_ms=latency_ms,
            capabilities=capabilities,
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
