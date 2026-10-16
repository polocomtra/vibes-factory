"""DeepSeek's OpenAI-compatible Chat Completions adapter."""

import json
from collections.abc import AsyncIterator, Callable
from inspect import isawaitable
from typing import Any

from openai import AsyncOpenAI

from ..contracts import (
    ModelRequest,
    ModelResponse,
    ModelStreamEvent,
    ModelToolCall,
    ModelUsage,
)
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
                api_key=api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
            messages = self._messages(request)
            kwargs: dict[str, object] = {
                "model": request.model,
                "messages": messages,
                "max_tokens": request.max_output_tokens,
                "stream": False,
            }
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            if request.tools:
                kwargs["tools"] = self._tools(request)
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

    @staticmethod
    def _messages(request: ModelRequest) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})
        for item in request.messages:
            message: dict[str, Any] = {"role": item.role, "content": item.content}
            if item.tool_call_id:
                message["tool_call_id"] = item.tool_call_id
            if item.name:
                message["name"] = item.name
            if item.tool_calls:
                message["tool_calls"] = [
                    {
                        "id": call.id or f"call_{index}",
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": json.dumps(call.arguments),
                        },
                    }
                    for index, call in enumerate(item.tool_calls)
                ]
            messages.append(message)
        return messages

    @staticmethod
    def _tools(request: ModelRequest) -> list[dict[str, object]]:
        return [
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

    async def stream(
        self, request: ModelRequest, api_key: str
    ) -> AsyncIterator[ModelStreamEvent]:
        """Normalize Chat Completions SSE and join fragmented tool arguments."""
        if not request.stream:
            raise ProviderError(
                "MODEL_REQUEST_INVALID", "A streaming request must set stream=true."
            )
        client: AsyncOpenAI | None = None
        try:
            client = self.client_factory(
                api_key=api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
            kwargs: dict[str, object] = {
                "model": request.model,
                "messages": self._messages(request),
                "max_tokens": request.max_output_tokens,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if request.temperature is not None:
                kwargs["temperature"] = request.temperature
            if request.tools:
                kwargs["tools"] = self._tools(request)
            if request.response_schema:
                kwargs["response_format"] = {"type": "json_object"}
            stream = await client.chat.completions.create(**kwargs)  # type: ignore[call-overload]
            content: list[str] = []
            calls: dict[int, dict[str, str]] = {}
            usage: ModelUsage | None = None
            finish_reason: str | None = None
            async for chunk in stream:
                choices = _value(chunk, "choices", []) or []
                if not choices:
                    raw_usage = _value(chunk, "usage")
                    if raw_usage is not None:
                        usage = ModelUsage(
                            input_tokens=_value(raw_usage, "prompt_tokens"),
                            output_tokens=_value(raw_usage, "completion_tokens"),
                            total_tokens=_value(raw_usage, "total_tokens"),
                        )
                    continue
                choice = choices[0]
                delta = _value(choice, "delta")
                text = _value(delta, "content")
                if isinstance(text, str) and text:
                    content.append(text)
                    yield ModelStreamEvent(type="text_delta", text=text)
                for part in _value(delta, "tool_calls", []) or []:
                    index = int(_value(part, "index", 0))
                    target = calls.setdefault(
                        index, {"id": "", "name": "", "arguments": ""}
                    )
                    target["id"] += _value(part, "id", "") or ""
                    function = _value(part, "function")
                    target["name"] += _value(function, "name", "") or ""
                    target["arguments"] += _value(function, "arguments", "") or ""
                finish_reason = _value(choice, "finish_reason") or finish_reason
            parsed_calls = tuple(
                ModelToolCall(
                    id=part["id"] or None,
                    name=part["name"] or "unknown",
                    arguments=_arguments(part["arguments"] or "{}"),
                )
                for _, part in sorted(calls.items())
            )
            response = ModelResponse(
                content="".join(content),
                tool_calls=parsed_calls,
                usage=usage,
                finish_reason="TOOL_CALLS" if parsed_calls else finish_reason,
            )
            yield ModelStreamEvent(type="completed", response=response)
        except ProviderError:
            raise
        except Exception as error:
            raise normalize_sdk_exception(error) from None
        finally:
            await _close_client(client)
