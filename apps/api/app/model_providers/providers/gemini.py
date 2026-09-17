"""Gemini REST adapter using HTTPX, isolated from the platform contract."""

from typing import Any

import httpx

from ..contracts import ModelRequest, ModelResponse, ModelToolCall, ModelUsage
from ..errors import ProviderError


class GeminiProvider:
    provider_id = "google"
    default_base_url = "https://generativelanguage.googleapis.com"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or self.default_base_url).rstrip("/")
        self.timeout = timeout
        self.http_client = http_client

    async def generate(self, request: ModelRequest, api_key: str) -> ModelResponse:
        if not api_key.strip():
            raise ProviderError(
                "PROVIDER_CREDENTIAL_MISSING", "Provider credentials are required."
            )
        contents = [
            {
                "role": "model" if message.role == "assistant" else "user",
                "parts": [{"text": message.content}],
            }
            for message in request.messages
            if message.role != "system"
        ]
        payload: dict[str, Any] = {"contents": contents}
        if request.system_instruction:
            payload["systemInstruction"] = {
                "parts": [{"text": request.system_instruction}]
            }
        generation: dict[str, Any] = {"maxOutputTokens": request.max_output_tokens}
        if request.temperature is not None:
            generation["temperature"] = request.temperature
        if request.response_schema:
            generation["responseMimeType"] = "application/json"
            generation["responseSchema"] = request.response_schema
        if generation:
            payload["generationConfig"] = generation
        if request.tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.parameters,
                        }
                        for tool in request.tools
                    ]
                }
            ]
        url = f"{self.base_url}/v1beta/models/{request.model}:generateContent"
        try:
            if self.http_client is not None:
                response = await self.http_client.post(
                    url, headers={"x-goog-api-key": api_key}, json=payload
                )
            else:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        url, headers={"x-goog-api-key": api_key}, json=payload
                    )
        except httpx.TimeoutException:
            raise ProviderError(
                "PROVIDER_TIMEOUT", "The provider request timed out.", retryable=True
            ) from None
        except httpx.HTTPError:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE", "The provider is unavailable.", retryable=True
            ) from None
        if response.status_code in (401, 403):
            raise ProviderError(
                "PROVIDER_AUTHENTICATION_FAILED",
                "The provider credentials were rejected.",
                status_code=response.status_code,
            )
        if response.status_code == 404:
            raise ProviderError(
                "MODEL_NOT_FOUND", "The requested model was not found.", status_code=404
            )
        if response.status_code == 429:
            raise ProviderError(
                "PROVIDER_RATE_LIMITED",
                "The provider rate limit was reached.",
                retryable=True,
                status_code=429,
            )
        if response.status_code >= 500:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                "The provider is temporarily unavailable.",
                retryable=True,
                status_code=response.status_code,
            )
        if response.status_code >= 400:
            raise ProviderError(
                "PROVIDER_BAD_REQUEST",
                "The provider rejected the request.",
                status_code=response.status_code,
            )
        try:
            body = response.json()
            candidate = body["candidates"][0]
            parts = candidate["content"]["parts"]
        except (ValueError, KeyError, IndexError, TypeError):
            raise ProviderError(
                "PROVIDER_INVALID_RESPONSE",
                "The provider returned an invalid response.",
            ) from None
        content = ""
        calls: list[ModelToolCall] = []
        for part in parts:
            if not isinstance(part, dict):
                raise ProviderError(
                    "PROVIDER_INVALID_RESPONSE",
                    "The provider returned an invalid response.",
                )
            if isinstance(part.get("text"), str):
                content += part["text"]
            function_call = part.get("functionCall")
            if isinstance(function_call, dict) and isinstance(
                function_call.get("name"), str
            ):
                args = function_call.get("args", {})
                if not isinstance(args, dict):
                    raise ProviderError(
                        "PROVIDER_INVALID_RESPONSE",
                        "The provider returned invalid tool arguments.",
                    )
                calls.append(ModelToolCall(name=function_call["name"], arguments=args))
        usage_data = body.get("usageMetadata", {})
        usage = (
            ModelUsage(
                input_tokens=usage_data.get("promptTokenCount"),
                output_tokens=usage_data.get("candidatesTokenCount"),
                total_tokens=usage_data.get("totalTokenCount"),
                cached_input_tokens=usage_data.get("cachedContentTokenCount"),
            )
            if usage_data
            else None
        )
        return ModelResponse(
            content=content,
            tool_calls=tuple(calls),
            usage=usage,
            finish_reason="TOOL_CALLS" if calls else candidate.get("finishReason"),
            provider_metadata={
                key: body[key]
                for key in ("responseId", "modelVersion")
                if isinstance(body.get(key), (str, int, float, bool))
            },
        )
