"""Provider-independent request and response contracts.

The contracts intentionally contain no credential fields. A key is supplied to
``generate`` for the lifetime of one call and is never part of a model request.
"""

from collections.abc import AsyncIterator
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ModelMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["system", "user", "assistant", "tool"]
    content: str = Field(min_length=1)


class ModelTool(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=10_000)
    parameters: dict[str, object] = Field(default_factory=dict)


class ModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1, max_length=64)
    model: str = Field(min_length=1, max_length=255)
    messages: tuple[ModelMessage, ...] = Field(min_length=1)
    system_instruction: str | None = None
    tools: tuple[ModelTool, ...] = ()
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int = Field(default=1024, ge=1, le=1_000_000)
    response_schema: dict[str, object] | None = None
    stream: bool = False
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("provider", "model", mode="before")
    @classmethod
    def normalize_identifier(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("system_instruction")
    @classmethod
    def normalize_instruction(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("response_schema")
    @classmethod
    def require_object_schema(
        cls, value: dict[str, object] | None
    ) -> dict[str, object] | None:
        if value is not None and value.get("type") not in (None, "object"):
            raise ValueError("response_schema must describe a JSON object")
        return value

class ModelToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str | None = None
    name: str = Field(min_length=1)
    arguments: dict[str, object]


class ModelUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)


class ModelResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    tool_calls: tuple[ModelToolCall, ...] = ()
    usage: ModelUsage | None = None
    finish_reason: str | None = None
    provider_metadata: dict[str, object] = Field(default_factory=dict)


class ModelStreamEvent(BaseModel):
    """Provider-neutral events emitted during one model stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text_delta", "completed"]
    text: str | None = None
    response: ModelResponse | None = None


class ModelProvider(Protocol):
    provider_id: str

    async def generate(self, request: ModelRequest, api_key: str) -> ModelResponse:
        """Generate one non-streaming response using an in-memory API key."""


class StreamingModelProvider(Protocol):
    """Optional streaming capability implemented by providers that support it."""

    provider_id: str

    def stream(
        self, request: ModelRequest, api_key: str
    ) -> AsyncIterator[ModelStreamEvent]:
        """Yield normalized text and terminal response events."""
