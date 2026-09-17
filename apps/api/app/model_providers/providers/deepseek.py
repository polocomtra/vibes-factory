"""DeepSeek's OpenAI-compatible Chat Completions adapter."""

import json
from collections.abc import Callable
from inspect import isawaitable
from typing import Any

from openai import AsyncOpenAI

from ..contracts import ModelRequest, ModelResponse, ModelToolCall, ModelUsage
from ..errors import ProviderError, normalize_sdk_exception


def _value(item: object, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _arguments(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    try:
        parsed = json.loads(raw if isinstance(raw, str) else "")
    except json.JSONDecodeError as error:
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned invalid tool arguments."
        ) from error
    if not isinstance(parsed, dict):
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned invalid tool arguments."
        )
    return {str(key): value for key, value in parsed.items()}


async def _close_client(client: object | None) -> None:
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if isawaitable(result):
            await result
    except Exception:
        return


def _parse_chat_response(response: object) -> ModelResponse:
    choices = _value(response, "choices", []) or []
    if not choices:
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned no response choices."
        )
    choice = choices[0]
    message = _value(choice, "message")
    if message is None:
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned no response message."
        )
    calls: list[ModelToolCall] = []
    for call in _value(message, "tool_calls", []) or []:
        function = _value(call, "function")
        calls.append(
            ModelToolCall(
                id=_value(call, "id"),
                name=_value(function, "name", "") or "unknown",
                arguments=_arguments(_value(function, "arguments", "{}")),
            )
        )
    usage_object = _value(response, "usage")
    prompt_details = (
        _value(usage_object, "prompt_tokens_details") if usage_object else None
    )
    usage = (
        ModelUsage(
            input_tokens=_value(usage_object, "prompt_tokens")
            if usage_object
            else None,
            output_tokens=_value(usage_object, "completion_tokens")
            if usage_object
            else None,
            total_tokens=_value(usage_object, "total_tokens") if usage_object else None,
            cached_input_tokens=_value(prompt_details, "cached_tokens")
            if prompt_details
            else None,
        )
        if usage_object
        else None
    )
    metadata: dict[str, object] = {}
    for key, value in {
        "request_id": _value(response, "_request_id") or _value(response, "request_id"),
        "model": _value(response, "model"),
    }.items():
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
    raw_finish_reason = _value(choice, "finish_reason")
    finish_reason = {
        "stop": "STOP",
        "length": "LENGTH",
        "tool_calls": "TOOL_CALLS",
    }.get(raw_finish_reason, raw_finish_reason)
    return ModelResponse(
        content=_value(message, "content", "") or "",
        tool_calls=tuple(calls),
        usage=usage,
        finish_reason="TOOL_CALLS" if calls else finish_reason,
        provider_metadata=metadata,
    )


class DeepSeekProvider:
    provider_id = "deepseek"
    default_base_url = "https://api.deepseek.com"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        client_factory: Callable[..., AsyncOpenAI] = AsyncOpenAI,
    ) -> None:
        self.base_url = base_url or self.default_base_url
        self.timeout = timeout
        self.client_factory = client_factory

    async def generate(self, request: ModelRequest, api_key: str) -> ModelResponse:
        if not api_key.strip():
            raise ProviderError(
                "PROVIDER_CREDENTIAL_MISSING", "Provider credentials are required."
            )
        client: AsyncOpenAI | None = None
        try:
            client = self.client_factory(
                api_key=api_key, base_url=self.base_url, timeout=self.timeout
            )
            messages: list[dict[str, str]] = []
            if request.system_instruction:
                messages.append(
                    {"role": "system", "content": request.system_instruction}
                )
            messages.extend(
                {"role": item.role, "content": item.content}
                for item in request.messages
            )
            kwargs: dict[str, object] = {
                "model": request.model,
                "messages": messages,
                "max_tokens": request.max_output_tokens,
                "stream": False,
            }
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            if request.tools:
                kwargs["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        },
                    }
                    for tool in request.tools
                ]
            if request.response_schema:
                kwargs["response_format"] = {"type": "json_object"}
            response = await client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
            return _parse_chat_response(response)
        except ProviderError:
            raise
        except Exception as error:
            raise normalize_sdk_exception(error) from None
        finally:
            await _close_client(client)
