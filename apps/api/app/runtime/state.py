"""Mutable state owned by exactly one runtime invocation."""

from dataclasses import dataclass, field
from typing import Any

from ..models import Run, Span, Trace
from .budget import ExecutionBudgetTracker, ExecutionContext
from .context import ContextBuildResult
from .contracts import AgentRunRequest


@dataclass(slots=True)
class RunState:
    request: AgentRunRequest
    execution_context: ExecutionContext
    tracker: ExecutionBudgetTracker | None = None
    context: ContextBuildResult | None = None
    run: Run | None = None
    trace: Trace | None = None
    root_span: Span | None = None
    context_span: Span | None = None
    model_span: Span | None = None
    guardrail_events: list[dict[str, Any]] = field(default_factory=list)
