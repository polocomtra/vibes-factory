"""OpenAI Responses API adapters, including Azure custom endpoints."""

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


def _messages(request: ModelRequest) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
            continue
        if message.role == "assistant" and message.tool_calls:
            for call in message.tool_calls:
                items.append(
                    {
                        "type": "function_call",
                        "call_id": call.id,
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    }
                )
            if message.content:
                items.append({"role": "assistant", "content": message.content})
            continue
        items.append({"role": message.role, "content": message.content})
    return items


def _response_input(request: ModelRequest) -> str | list[dict[str, Any]]:
    if len(request.messages) == 1 and request.messages[0].role == "user":
        return request.messages[0].content
    return _messages(request)


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


def _parse_arguments(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return {str(key): value for key, value in raw.items()}
    if not isinstance(raw, str):
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned invalid tool arguments."
        )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned invalid tool arguments."
        ) from error
    if not isinstance(parsed, dict):
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned invalid tool arguments."
        )
    return {str(key): value for key, value in parsed.items()}


def _parse_responses_output(response: object) -> ModelResponse:
    output_text = _value(response, "output_text")
    content = output_text or ""
    tool_calls: list[ModelToolCall] = []
    output = _value(response, "output", []) or []
    if not isinstance(output, list) or (not output_text and not output):
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned an invalid response."
        )
    for item in output:
        item_type = _value(item, "type")
        if item_type == "message" and not output_text:
            for part in _value(item, "content", []) or []:
                if _value(part, "type") in ("output_text", "text"):
                    content += _value(part, "text", "") or ""
        elif item_type == "function_call":
            tool_calls.append(
                ModelToolCall(
                    id=_value(item, "call_id") or _value(item, "id"),
                    name=_value(item, "name", "") or "unknown",
                    arguments=_parse_arguments(_value(item, "arguments", {})),
                )
            )

    usage_object = _value(response, "usage")
    usage = None
    if usage_object is not None:
        input_details = _value(usage_object, "input_tokens_details")
        usage = ModelUsage(
            input_tokens=_value(usage_object, "input_tokens"),
            output_tokens=_value(usage_object, "output_tokens"),
            total_tokens=_value(usage_object, "total_tokens"),
            cached_input_tokens=_value(input_details, "cached_tokens")
            if input_details
            else None,
        )

    status = _value(response, "status")
    incomplete = _value(response, "incomplete_details")
    reason = _value(incomplete, "reason") if incomplete else None
    finish_reason = (
        "TOOL_CALLS"
        if tool_calls
        else (
            "LENGTH"
            if reason in {"max_output_tokens", "max_tokens"} or status == "incomplete"
            else "STOP"
            if status == "completed"
            else status
        )
    )
    metadata: dict[str, object] = {}
    for key, value in {
        "request_id": _value(response, "_request_id") or _value(response, "request_id"),
        "model": _value(response, "model"),
    }.items():
        if isinstance(value, (str, int, float, bool)):
            metadata[key] = value
    return ModelResponse(
        content=content,
        tool_calls=tuple(tool_calls),
        usage=usage,
        finish_reason=finish_reason,
        provider_metadata=metadata,
    )


class OpenAIProvider:
    provider_id = "openai"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        client_factory: Callable[..., AsyncOpenAI] = AsyncOpenAI,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.client_factory = client_factory

    def _client(self, api_key: str) -> AsyncOpenAI:
        if not api_key.strip():
            raise ProviderError(
                "PROVIDER_CREDENTIAL_MISSING", "Provider credentials are required."
            )
        kwargs: dict[str, object] = {"api_key": api_key, "timeout": self.timeout}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return self.client_factory(**kwargs)

    @staticmethod
    def _response_kwargs(request: ModelRequest) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "model": request.model,
            "input": _response_input(request),
            "store": False,
            "stream": request.stream,
        }
        if request.system_instruction:
            kwargs["instructions"] = request.system_instruction
        if request.temperature is not None and request.provider != "azure_openai":
            kwargs["temperature"] = request.temperature
        if request.max_output_tokens:
            kwargs["max_output_tokens"] = request.max_output_tokens
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
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "response",
                    "strict": True,
                    "schema": request.response_schema,
                }
            }
        return kwargs

    async def generate(self, request: ModelRequest, api_key: str) -> ModelResponse:
        client: AsyncOpenAI | None = None
        try:
            client = self._client(api_key)
            response = await client.responses.create(**self._response_kwargs(request))  # type: ignore[call-overload]
            return _parse_responses_output(response)
        except ProviderError:
            raise
        except Exception as error:
            raise normalize_sdk_exception(error) from None
        finally:
            await _close_client(client)

    async def stream(
        self, request: ModelRequest, api_key: str
    ) -> AsyncIterator[ModelStreamEvent]:
        """Stream Responses API text deltas through the platform contract."""

        if not request.stream:
            raise ProviderError(
                "MODEL_REQUEST_INVALID",
                "A streaming provider request must set stream=true.",
            )
        client: AsyncOpenAI | None = None
        completed = False
        try:
            client = self._client(api_key)
            stream = await client.responses.create(**self._response_kwargs(request))  # type: ignore[call-overload]
            async for event in stream:
                event_type = _value(event, "type")
                if event_type == "response.output_text.delta":
                    delta = _value(event, "delta")
                    if isinstance(delta, str) and delta:
                        yield ModelStreamEvent(type="text_delta", text=delta)
                elif event_type == "response.completed":
                    response = _value(event, "response")
                    if response is None:
                        raise ProviderError(
                            "PROVIDER_INVALID_RESPONSE",
                            "The provider returned no completed response.",
                        )
                    completed = True
                    yield ModelStreamEvent(
                        type="completed", response=_parse_responses_output(response)
                    )
                elif event_type == "response.incomplete":
                    # Azure/OpenAI can terminate a response at the output limit
                    # while still returning usable text. Preserve that text as
                    # a bounded partial answer so the runtime can persist it
                    # instead of dropping the whole run after tool execution.
                    response = _value(event, "response")
                    if response is None:
                        raise ProviderError(
                            "PROVIDER_INVALID_RESPONSE",
                            "The provider returned an incomplete response.",
                        )
                    try:
                        parsed = _parse_responses_output(response)
                    except ProviderError:
                        raise ProviderError(
                            "PROVIDER_INVALID_RESPONSE",
                            "The provider returned an incomplete response "
                            "without usable output.",
                        ) from None
                    completed = True
                    yield ModelStreamEvent(type="completed", response=parsed)
                elif event_type in {"response.failed", "error"}:
                    raise ProviderError(
                        "PROVIDER_INVALID_RESPONSE",
                        "The provider failed before completing the response.",
                    )
            if not completed:
                raise ProviderError(
                    "PROVIDER_INVALID_RESPONSE",
                    "The provider stream ended without a completed response.",
                )
        except ProviderError:
            raise
        except Exception as error:
            raise normalize_sdk_exception(error) from None
        finally:
            await _close_client(client)


class AzureOpenAIProvider(OpenAIProvider):
    provider_id = "azure_openai"

    def __init__(
        self,
        *,
        base_url: str | None,
        timeout: float = 60.0,
        client_factory: Callable[..., AsyncOpenAI] = AsyncOpenAI,
    ) -> None:
        if not base_url:
            raise ProviderError(
                "MODEL_REQUEST_INVALID", "Azure OpenAI base URL is required."
            )
        super().__init__(
            base_url=base_url, timeout=timeout, client_factory=client_factory
        )
