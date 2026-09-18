"""Cumulative execution-budget tracking for every runtime transport."""

from decimal import ROUND_HALF_UP, Decimal
from time import monotonic

from ..model_providers.contracts import ModelRequest, ModelResponse
from .contracts import AgentRunRequest, ExecutionBudget, TokenUsage
from .errors import RuntimeExecutionError

_MAX_ESTIMATED_TOKENS = 10_000_000
_TOKENS_PER_MILLION = Decimal(1_000_000)
_COST_QUANTUM = Decimal("0.00000001")


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

    def __init__(self, request: AgentRunRequest) -> None:
        self.budget: ExecutionBudget = request.execution_budget
        self.started_at = monotonic()
        self.deadline = self.started_at + self.budget.timeout_seconds
        self.steps = 0
        self.model_calls = 0
        self.tool_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.cached_input_tokens = 0

    def _limit(self, name: str) -> None:
        raise RuntimeExecutionError(
            "RUN_LIMIT_EXCEEDED",
            "Agent execution exceeded its configured budget.",
            status_code=422,
            details={"budget": name},
        )

    def remaining_seconds(self) -> float:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            self._limit("timeout_seconds")
        return remaining

    def begin_model_call(self) -> float:
        self.steps += 1
        self.model_calls += 1
        if self.steps > self.budget.max_steps:
            self._limit("max_steps")
        if self.model_calls > self.budget.max_model_calls:
            self._limit("max_model_calls")
        return self.remaining_seconds()

    def record_tool_calls(self, count: int) -> float:
        self.steps += 1
        self.tool_calls += count
        if self.steps > self.budget.max_steps:
            self._limit("max_steps")
        if self.tool_calls > self.budget.max_tool_calls:
            self._limit("max_tool_calls")
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
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.cached_input_tokens += cached
        self.total_tokens += input_tokens + output_tokens
        if self.total_tokens > self.budget.max_total_tokens:
            self._limit("max_total_tokens")

    def usage(self) -> TokenUsage:
        return TokenUsage(
            input_tokens=self.input_tokens,
            output_tokens=self.output_tokens,
            total_tokens=self.total_tokens,
            cached_input_tokens=self.cached_input_tokens or None,
        )
