"""Gemini adapter using Google's official GenerateContent API."""

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any, cast

from google import genai
from google.genai import types

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
        client_factory: Callable[..., Any] = genai.Client,
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
                cast(Any, client.aio.models).generate_content(
                    model=request.model,
                    contents=cast(Any, _generate_contents(request)),
                    config=cast(Any, _generate_config(request)),
                ),
                timeout=self.timeout,
            )
            return _parse_generate_content(response)
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

    async def stream(
        self, request: ModelRequest, api_key: str
    ) -> AsyncIterator[ModelStreamEvent]:
        if not request.stream:
            raise ProviderError(
                "MODEL_REQUEST_INVALID", "A streaming request must set stream=true."
            )
        client: genai.Client | None = None
        content: list[str] = []
        calls: list[ModelToolCall] = []
        final_usage: ModelUsage | None = None
        try:
            client = self.client_factory(
                api_key=api_key,
                http_options=types.HttpOptions(
                    base_url=self.base_url, timeout=int(self.timeout * 1000)
                ),
            )
            stream = cast(Any, client.aio.models).generate_content_stream(
                model=request.model,
                contents=cast(Any, _generate_contents(request)),
                config=cast(Any, _generate_config(request)),
            )
            async for chunk in stream:
                final_usage = _parse_generate_usage(chunk) or final_usage
                try:
                    parsed = _parse_generate_content(chunk)
                except ProviderError:
                    # The final Gemini stream chunk can contain usage metadata
                    # without candidates. Preserve usage and finish normally.
                    continue
                if parsed.content:
                    content.append(parsed.content)
                    yield ModelStreamEvent(type="text_delta", text=parsed.content)
                if parsed.tool_calls:
                    calls = list(parsed.tool_calls)
            yield ModelStreamEvent(
                type="completed",
                response=ModelResponse(
                    content="".join(content),
                    tool_calls=tuple(calls),
                    usage=final_usage,
                    finish_reason="TOOL_CALLS" if calls else "STOP",
                ),
            )
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


def _generate_contents(request: ModelRequest) -> list[dict[str, Any]]:
    contents: list[dict[str, Any]] = []
    for message in request.messages:
        if message.role == "tool":
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": message.name or "tool",
                                "response": {"result": message.content},
                            }
                        }
                    ],
                }
            )
            continue
        role = "model" if message.role == "assistant" else "user"
        parts: list[dict[str, Any]] = []
        if message.content:
            parts.append({"text": message.content})
        parts.extend(
            {"function_call": {"name": call.name, "args": call.arguments}}
            for call in message.tool_calls
        )
        contents.append({"role": role, "parts": parts or [{"text": ""}]})
    return contents


def _generate_config(request: ModelRequest) -> dict[str, Any]:
    config: dict[str, Any] = {
        "system_instruction": request.system_instruction,
        "max_output_tokens": request.max_output_tokens,
    }
    if request.temperature is not None and request.model != "gemini-3.8-flash":
        config["temperature"] = request.temperature
    if request.tools:
        config["tools"] = [
            {
                "function_declarations": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }
                    for tool in request.tools
                ]
            }
        ]
    if request.response_schema:
        config["response_mime_type"] = "application/json"
        config["response_schema"] = request.response_schema
    return config


def _parse_generate_content(response: object) -> ModelResponse:
    content = ""
    calls: list[ModelToolCall] = []
    for candidate in _value(response, "candidates", []) or []:
        for index, part in enumerate(
            _value(_value(candidate, "content"), "parts", []) or []
        ):
            text = _value(part, "text")
            if isinstance(text, str):
                content += text
            function = _value(part, "function_call")
            if function is not None:
                arguments = _value(function, "args", {})
                calls.append(
                    ModelToolCall(
                        id=f"gemini_call_{index}",
                        name=_value(function, "name", "unknown"),
                        arguments=arguments if isinstance(arguments, dict) else {},
                    )
                )
    usage = _parse_generate_usage(response)
    if not content and not calls:
        raise ProviderError(
            "PROVIDER_INVALID_RESPONSE", "The provider returned no usable content."
        )
    return ModelResponse(
        content=content,
        tool_calls=tuple(calls),
        usage=usage,
        finish_reason="TOOL_CALLS" if calls else "STOP",
    )


def _parse_generate_usage(response: object) -> ModelUsage | None:
    usage_data = _value(response, "usage_metadata")
    if usage_data is None:
        return None
    return ModelUsage(
        input_tokens=_value(usage_data, "prompt_token_count"),
        output_tokens=_value(usage_data, "candidates_token_count"),
        total_tokens=_value(usage_data, "total_token_count"),
        cached_input_tokens=_value(usage_data, "cached_content_token_count"),
    )
