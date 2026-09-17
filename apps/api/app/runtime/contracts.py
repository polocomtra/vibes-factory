"""Provider-independent runtime contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TextInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["text"] = "text"
    text: str = Field(min_length=1, max_length=100_000)


class ExecutionBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    max_steps: int = Field(default=20, ge=1, le=1_000)
    max_model_calls: int = Field(default=10, ge=1, le=1_000)
    max_tool_calls: int = Field(default=10, ge=0, le=1_000)
    max_child_runs: int = Field(default=5, ge=0, le=1_000)
    max_agent_depth: int = Field(default=3, ge=0, le=100)
    max_total_tokens: int = Field(default=100_000, ge=1, le=10_000_000)
    timeout_seconds: int = Field(default=120, ge=1, le=3_600)


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)


class SessionMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Literal["USER", "ASSISTANT", "SYSTEM", "TOOL"]
    content: str = Field(min_length=1)


class AgentVersionRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    agent_id: UUID
    workspace_id: UUID
    instructions: str
    model_provider: str
    model_name: str
    model_options: dict[str, object] = Field(default_factory=dict)


class RuntimeSession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    agent_id: UUID
    workspace_id: UUID
    messages: tuple[SessionMessage, ...] = ()


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    agent_version: AgentVersionRuntimeConfig
    session: RuntimeSession
    input: TextInput
    execution_budget: ExecutionBudget


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    trace_id: UUID
    agent_version_id: UUID
    session_id: UUID
    status: Literal["COMPLETED"]
    output: TextInput
    usage: TokenUsage
    estimated_cost: float | None = None
    started_at: datetime
    completed_at: datetime
