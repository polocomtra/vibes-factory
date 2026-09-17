"""Gemini adapter using Google's official GenAI Interactions SDK."""

import asyncio
from collections.abc import Callable
from typing import Any, cast

from google import genai
from google.genai import types

from ..contracts import ModelRequest, ModelResponse, ModelToolCall, ModelUsage
from ..errors import ProviderError, normalize_sdk_exception


def _value(item: object, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _interaction_input(request: ModelRequest) -> list[dict[str, Any]]:
    """Map platform messages to Interactions user/model input steps."""

    interaction_input: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role == "system":
            continue
        if message.role == "tool":
            raise ProviderError(
                "MODEL_CAPABILITY_UNSUPPORTED",
                "Tool messages are not supported by the Gemini text adapter yet.",
            )
        interaction_input.append(
            {
                "type": (
                    "model_output" if message.role == "assistant" else "user_input"
                ),
                "content": [{"type": "text", "text": message.content}],
            }
        )
    if not interaction_input:
        raise ProviderError(
            "MODEL_REQUEST_INVALID", "The Gemini request must contain text content."
        )
    return interaction_input


def _interaction_kwargs(request: ModelRequest) -> dict[str, Any]:
    """Build an Interactions request without leaking SDK types upstream."""

    kwargs: dict[str, Any] = {
        "model": request.model,
        "input": _interaction_input(request),
        "system_instruction": request.system_instruction,
        "generation_config": {"max_output_tokens": request.max_output_tokens},
        # Session history is owned and persisted by VibesFactory, not Google.
        "store": False,
        "stream": False,
    }
    if request.tools:
        kwargs["tools"] = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in request.tools
        ]
    if request.response_schema:
        kwargs["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": cast(dict[str, Any], request.response_schema),
        }
    return kwargs


def _parse_response(response: object) -> ModelResponse:
    """Normalize an Interactions response into the platform contract."""

    content = _value(response, "output_text", "")
    if not isinstance(content, str):
        content = ""
    calls: list[ModelToolCall] = []

    # output_text is supplied by the SDK. The step fallback keeps parsing
    # resilient when a response is constructed by a test double or a future
    # SDK version does not populate the convenience property.
    for step in _value(response, "steps", []) or []:
        step_type = _enum_value(_value(step, "type"))
        if step_type == "function_call":
            name = _value(step, "name")
            arguments = _value(step, "arguments", {})
            call_id = _value(step, "id")
            if not isinstance(name, str) or not isinstance(arguments, dict):
                raise ProviderError(
                    "PROVIDER_INVALID_RESPONSE",
                    "The provider returned invalid tool arguments.",
                )
            calls.append(
                ModelToolCall(
                    id=call_id if isinstance(call_id, str) else None,
                    name=name,
                    arguments=arguments,
                )
            )
        elif not content and step_type == "model_output":
            for block in _value(step, "content", []) or []:
                block_text = _value(block, "text")
                if isinstance(block_text, str):
                    content += block_text

    if not content and not calls:
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned no text content."
        )

    usage_data = _value(response, "usage")
    if usage_data is None:
        usage_data = _value(response, "usage_metadata")
    usage = (
        ModelUsage(
            input_tokens=_value(
                usage_data,
                "total_input_tokens",
                _value(usage_data, "prompt_token_count"),
            ),
            output_tokens=_value(
                usage_data,
                "total_output_tokens",
                _value(usage_data, "candidates_token_count"),
            ),
            total_tokens=_value(
                usage_data,
                "total_tokens",
                _value(usage_data, "total_token_count"),
            ),
            cached_input_tokens=_value(
                usage_data,
                "total_cached_tokens",
                _value(usage_data, "cached_content_token_count"),
            ),
        )
        if usage_data is not None
        else None
    )
    metadata: dict[str, object] = {}
    for source_key, output_key in (("id", "interactionId"), ("model", "model")):
        value = _enum_value(_value(response, source_key))
        if isinstance(value, (str, int, float, bool)):
            metadata[output_key] = value
    status = _enum_value(_value(response, "status"))
    if isinstance(status, str):
        metadata["status"] = status

    return ModelResponse(
        content=content,
        tool_calls=tuple(calls),
        usage=usage,
        finish_reason="TOOL_CALLS" if calls else None,
        provider_metadata=metadata,
    )


async def _close_client(client: object | None) -> None:
    if client is None:
        return
    async_client = getattr(client, "aio", None)
    close = getattr(async_client, "aclose", None)
    if not callable(close):
        return
    try:
        result = close()
        if hasattr(result, "__await__"):
            await result
    except Exception:
        return


class GeminiProvider:
    provider_id = "google"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        client_factory: Callable[..., genai.Client] = genai.Client,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.client_factory = client_factory

    async def generate(self, request: ModelRequest, api_key: str) -> ModelResponse:
        if not api_key.strip():
            raise ProviderError(
                "PROVIDER_CREDENTIAL_MISSING", "Provider credentials are required."
            )
        client: genai.Client | None = None
        try:
            client = self.client_factory(
                api_key=api_key,
                http_options=types.HttpOptions(
                    base_url=self.base_url,
                    timeout=int(self.timeout * 1000),
                ),
            )
            response = await asyncio.wait_for(
                client.aio.interactions.create(**_interaction_kwargs(request)),
                timeout=self.timeout,
            )
            return _parse_response(response)
        except ProviderError:
            raise
        except TimeoutError:
            raise ProviderError(
                "PROVIDER_TIMEOUT", "The provider request timed out.", retryable=True
            ) from None
        except Exception as error:
            raise normalize_sdk_exception(error) from None
        finally:
            await _close_client(client)
