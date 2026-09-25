"""Provider-independent runtime contracts."""

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

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
    content: str = ""
    tool_calls: tuple[dict[str, object], ...] = ()
    tool_call_id: str | None = None
    name: str | None = None


class RuntimeTool(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_id: UUID | None = None
    tool_version_id: UUID | None = None
    kind: Literal["tool", "child_agent"] = "tool"
    child_agent_id: UUID | None = None
    child_agent_version_id: UUID | None = None
    name: str
    description: str | None = None
    parameters: dict[str, object] = Field(default_factory=dict)


class RuntimeKnowledgeBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_base_id: UUID
    name: str
    mode: Literal["auto", "always"] = "auto"
    top_k: int = Field(default=5, ge=1, le=20)
    score_threshold: float | None = None
    filters: dict[str, object] = Field(default_factory=dict)


class RuntimeMemoryBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    memory_store_id: UUID
    top_k: int = Field(default=5, ge=1, le=20)
    write_enabled: bool = True
    write_types: tuple[str, ...] = ("PROFILE", "SEMANTIC")


class RuntimeMemoryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    item_id: UUID
    content: str
    score: float
    scope: str


class RuntimeGuardrail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version_id: UUID | None = None
    source: Literal["CUSTOM", "PLATFORM_DEFAULT"] = "CUSTOM"
    configuration: dict[str, object] = Field(default_factory=dict)
    hooks: tuple[str, ...] = ()
    priority: int = Field(default=100, ge=0, le=1000)


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    marker: str
    chunk_id: UUID
    document_id: UUID
    knowledge_base_id: UUID
    source_name: str
    page: int | None = None
    section: str | None = None
    score: float
    generation: int
    excerpt: str = Field(max_length=500)


class AgentVersionRuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    agent_id: UUID
    workspace_id: UUID
    instructions: str
    model_provider: str
    model_name: str
    model_options: dict[str, object] = Field(default_factory=dict)
    tools: tuple[RuntimeTool, ...] = ()
    knowledge_bases: tuple[RuntimeKnowledgeBinding, ...] = ()
    memory: RuntimeMemoryBinding | None = None
    guardrails_enabled: bool = False
    guardrails: tuple[RuntimeGuardrail, ...] = ()


class RuntimeSession(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    agent_id: UUID
    workspace_id: UUID
    user_id: UUID = Field(default_factory=uuid4)
    messages: tuple[SessionMessage, ...] = ()


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workspace_id: UUID
    agent_version: AgentVersionRuntimeConfig
    session: RuntimeSession
    input: TextInput
    execution_budget: ExecutionBudget
    knowledge_context: str | None = None
    citations: tuple[Citation, ...] = ()
    memory_context: str | None = None
    memory_results: tuple[RuntimeMemoryResult, ...] = ()
    resume_run_id: UUID | None = None
    resume_approval_id: UUID | None = None


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    trace_id: UUID
    agent_version_id: UUID
    session_id: UUID
    status: Literal["COMPLETED", "WAITING_APPROVAL"]
    output: TextInput | None = None
    citations: tuple[Citation, ...] = ()
    usage: TokenUsage
    estimated_cost: float | None = None
    started_at: datetime
    completed_at: datetime | None


class RuntimeStreamEvent(BaseModel):
    """The small event envelope shared by the runtime and SSE transport."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    event: Literal[
        "run.started",
        "message.delta",
        "message.completed",
        "tool.started",
        "tool.completed",
        "tool.failed",
        "child_agent.started",
        "child_agent.completed",
        "child_agent.failed",
        "retrieval.started",
        "retrieval.completed",
        "retrieval.failed",
        "memory.retrieved",
        "guardrail.triggered",
        "approval.required",
        "run.completed",
        "run.failed",
    ]
    data: dict[str, object]
