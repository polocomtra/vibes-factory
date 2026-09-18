"""Provider-neutral tool execution contracts."""

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ToolExecutionContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    run_id: UUID | None = None
    trace_id: UUID | None = None
    timeout_seconds: float = Field(default=30, gt=0, le=3_600)


class ToolGuardrailHook(Protocol):
    async def validate(
        self, arguments: Mapping[str, Any], context: ToolExecutionContext
    ) -> None:
        """Validate a tool call before credentials or execution are reached."""


class NoopToolGuardrailHook:
    async def validate(
        self, arguments: Mapping[str, Any], context: ToolExecutionContext
    ) -> None:
        del arguments, context


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ok: bool
    output: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None


class CredentialResolver(Protocol):
    def resolve(self, reference: str) -> str:
        """Resolve a credential without exposing it to the model or storage."""


class UnavailableCredentialResolver:
    def resolve(self, reference: str) -> str:
        del reference
        raise ValueError("Credential Vault is not available until Phase 7.")


class ToolExecutor(Protocol):
    async def execute(
        self,
        arguments: Mapping[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        """Execute validated arguments and return sanitized platform output."""
