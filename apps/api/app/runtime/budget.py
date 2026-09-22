"""Cumulative execution-budget tracking for every runtime transport."""

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from time import monotonic
from typing import Any
from uuid import UUID

from ..model_providers.contracts import ModelRequest, ModelResponse
from .contracts import AgentRunRequest, ExecutionBudget, TokenUsage
from .errors import RuntimeExecutionError

_MAX_ESTIMATED_TOKENS = 10_000_000
_TOKENS_PER_MILLION = Decimal(1_000_000)
_COST_QUANTUM = Decimal("0.00000001")


_COUNTERS = (
    "node_executions",
    "total_steps",
    "model_calls",
    "tool_calls",
    "child_runs",
    "agent_runs",
    "input_tokens",
    "output_tokens",
    "total_tokens",
)


@dataclass(slots=True)
class ExecutionContext:
    """Shared execution state for a workflow and its complete agent tree.

    The context is intentionally transport-agnostic.  ``fork`` only changes
    lineage fields; the counters and absolute deadline remain shared.
    """

    budget: dict[str, int]
    trace_id: UUID
    workflow_run_id: UUID | None = None
    root_run_id: UUID | None = None
    parent_run_id: UUID | None = None
    parent_span_id: UUID | None = None
    agent_depth: int = 0
    deadline: float | None = None
    counters: dict[str, int] = field(default_factory=dict)
    cancel_check: Any = None

    def __post_init__(self) -> None:
        self.counters.update(
            {name: int(self.counters.get(name, 0)) for name in _COUNTERS}
        )
        if self.deadline is None:
            self.deadline = monotonic() + max(
                1, self.budget.get("timeout_seconds", 120)
            )

    def fork(
        self,
        *,
        parent_run_id: UUID | None,
        parent_span_id: UUID,
        agent_depth: int,
    ) -> "ExecutionContext":
        return ExecutionContext(
            budget=self.budget,
            trace_id=self.trace_id,
            workflow_run_id=self.workflow_run_id,
            root_run_id=self.root_run_id,
            parent_run_id=parent_run_id,
            parent_span_id=parent_span_id,
            agent_depth=agent_depth,
            deadline=self.deadline,
            counters=self.counters,
            cancel_check=self.cancel_check,
        )

    def snapshot(self) -> dict[str, int]:
        return {name: int(self.counters.get(name, 0)) for name in _COUNTERS}

    def remaining_seconds(self) -> float:
        if self.cancel_check is not None and self.cancel_check():
            raise RuntimeExecutionError(
                "RUN_CANCELLED",
                "The execution was cancelled.",
                status_code=409,
                details={"reason": "cancel_requested"},
            )
        remaining = (self.deadline or monotonic()) - monotonic()
        if remaining <= 0:
            self.limit("timeout_seconds", "timeout_seconds")
        return remaining

    def limit(self, budget_name: str, limit_name: str | None = None) -> None:
        name = limit_name or budget_name
        raise RuntimeExecutionError(
            "RUN_LIMIT_EXCEEDED",
            "Agent execution exceeded its configured budget.",
            status_code=422,
            details={
                "budget": name,
                "used": int(self.counters.get(budget_name, 0)),
                "limit": int(self.budget.get(name, 0)),
            },
        )

    def increment(self, counter: str, *, limit_name: str | None = None) -> int:
        self.counters[counter] = int(self.counters.get(counter, 0)) + 1
        limit_key = limit_name or counter
        if limit_key in self.budget and self.counters[counter] > self.budget[limit_key]:
            self.limit(counter, limit_key)
        self.remaining_seconds()
        return self.counters[counter]


def estimate_model_request(request: ModelRequest) -> int:
    """Bounded fallback estimate used when a provider omits usage metadata."""
    text = request.system_instruction or ""
    text += "\n" + "\n".join(message.content for message in request.messages)
    text += "\n" + "\n".join(
        tool.name + (tool.description or "") for tool in request.tools
    )
    return min(_MAX_ESTIMATED_TOKENS, max(1, (len(text) + 3) // 4))


def estimate_model_cost(
    usage: TokenUsage,
    *,
    input_price_per_million: Decimal | None,
    output_price_per_million: Decimal | None,
    cached_input_price_per_million: Decimal | None = None,
) -> Decimal | None:
    """Estimate USD cost from normalized usage and configured token rates."""
    if input_price_per_million is None or output_price_per_million is None:
        return None
    input_tokens = max(0, usage.input_tokens or 0)
    cached_input_tokens = min(input_tokens, max(0, usage.cached_input_tokens or 0))
    uncached_input_tokens = input_tokens - cached_input_tokens
    output_tokens = max(0, usage.output_tokens or 0)
    cached_rate = (
        cached_input_price_per_million
        if cached_input_price_per_million is not None
        else input_price_per_million
    )
    cost = (
        Decimal(uncached_input_tokens) * input_price_per_million
        + Decimal(cached_input_tokens) * cached_rate
        + Decimal(output_tokens) * output_price_per_million
    ) / _TOKENS_PER_MILLION
    return cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)


class ExecutionBudgetTracker:
    """Track cumulative calls, steps, tokens and one absolute deadline."""

    def __init__(
        self,
        request: AgentRunRequest,
        context: ExecutionContext | None = None,
    ) -> None:
        self.budget: ExecutionBudget = request.execution_budget
        self.context = context or ExecutionContext(
            budget=self.budget.model_dump(),
            trace_id=UUID(int=0),
        )

    def _limit(self, name: str) -> None:
        self.context.limit(name, name)

    @property
    def steps(self) -> int:
        return self.context.counters["total_steps"]

    @property
    def model_calls(self) -> int:
        return self.context.counters["model_calls"]

    @property
    def tool_calls(self) -> int:
        return self.context.counters["tool_calls"]

    @property
    def input_tokens(self) -> int:
        return self.context.counters["input_tokens"]

    @property
    def output_tokens(self) -> int:
        return self.context.counters["output_tokens"]

    @property
    def total_tokens(self) -> int:
        return self.context.counters["total_tokens"]

    @property
    def cached_input_tokens(self) -> int:
        return self.context.counters.get("cached_input_tokens", 0)

    def remaining_seconds(self) -> float:
        return self.context.remaining_seconds()

    def begin_model_call(self) -> float:
        self.context.increment("total_steps", limit_name="max_steps")
        self.context.increment("model_calls", limit_name="max_model_calls")
        return self.remaining_seconds()

    def record_tool_calls(self, count: int) -> float:
        for _ in range(count):
            self.context.increment("total_steps", limit_name="max_steps")
            self.context.increment("tool_calls", limit_name="max_tool_calls")
        return self.remaining_seconds()

    def record_response(self, response: ModelResponse, request: ModelRequest) -> None:
        provider_usage = response.usage
        input_tokens = (
            provider_usage.input_tokens
            if provider_usage and provider_usage.input_tokens is not None
            else estimate_model_request(request)
        )
        output_tokens = (
            provider_usage.output_tokens
            if provider_usage and provider_usage.output_tokens is not None
            else min(_MAX_ESTIMATED_TOKENS, max(1, (len(response.content) + 3) // 4))
        )
        cached = (
            provider_usage.cached_input_tokens
            if provider_usage and provider_usage.cached_input_tokens is not None
            else 0
        )
        self.context.counters["input_tokens"] += input_tokens
        self.context.counters["output_tokens"] += output_tokens
        self.context.counters["total_tokens"] += input_tokens + output_tokens
        self.context.counters["cached_input_tokens"] = (
            self.context.counters.get("cached_input_tokens", 0) + cached
        )
        if self.context.counters["total_tokens"] > self.context.budget.get(
            "max_total_tokens", self.budget.max_total_tokens
        ):
            self._limit("max_total_tokens")

    def usage(self) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.context.counters["input_tokens"],
            output_tokens=self.context.counters["output_tokens"],
            total_tokens=self.context.counters["total_tokens"],
            cached_input_tokens=self.context.counters.get("cached_input_tokens")
            or None,
        )
