"""Per-call provider accounting and per-run cost aggregation."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..model_providers.contracts import ModelRequest, ModelResponse
from ..models import Run, Span, SpanStatus, SpanType
from ..monitoring.pricing import pricing_for_call
from .budget import estimate_model_cost, estimate_model_request
from .contracts import TokenUsage


class RuntimeAccounting:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_model_accounting(
        self,
        run: Run,
        span: Span,
        response: ModelResponse,
        request: ModelRequest,
    ) -> None:
        provider_usage = response.usage
        input_estimated = provider_usage is None or provider_usage.input_tokens is None
        output_estimated = (
            provider_usage is None or provider_usage.output_tokens is None
        )
        input_tokens = (
            provider_usage.input_tokens
            if provider_usage and provider_usage.input_tokens is not None
            else estimate_model_request(request)
        )
        output_tokens = (
            provider_usage.output_tokens
            if provider_usage and provider_usage.output_tokens is not None
            else min(10_000_000, max(1, (len(response.content) + 3) // 4))
        )
        cached_tokens = (
            min(input_tokens, provider_usage.cached_input_tokens)
            if provider_usage and provider_usage.cached_input_tokens is not None
            else None
        )
        usage = {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": input_tokens + output_tokens,
            "input_tokens_estimated": input_estimated,
            "output_tokens_estimated": output_estimated,
        }
        if cached_tokens is not None:
            usage["cached_input_tokens"] = cached_tokens
        span.usage = usage
        span.status = SpanStatus.COMPLETED
        span.completed_at = datetime.now(UTC)
        # Persist provider usage and call duration before the pricing lookup or
        # later guardrail/tool work can fail or pause the run.
        await self.session.commit()
        pricing = await pricing_for_call(
            self.session,
            request.provider,
            request.model,
            span.started_at,
        )
        if pricing is not None:
            price = estimate_model_cost(
                TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    cached_input_tokens=cached_tokens,
                ),
                input_price_per_million=pricing.input_price_per_million,
                output_price_per_million=pricing.output_price_per_million,
                cached_input_price_per_million=pricing.cached_input_price_per_million,
            )
            span.attributes = {
                **span.attributes,
                "pricing_id": str(pricing.id),
                "currency": "USD",
                "pricing_snapshot": {
                    "input_price_per_million": str(pricing.input_price_per_million),
                    "output_price_per_million": str(pricing.output_price_per_million),
                    "cached_input_price_per_million": (
                        str(pricing.cached_input_price_per_million)
                        if pricing.cached_input_price_per_million is not None
                        else None
                    ),
                    "effective_from": pricing.effective_from.isoformat(),
                    "source": pricing.metadata_json.get("source"),
                },
                "estimated_cost": str(price),
                "cost_status": "ESTIMATED",
            }
        else:
            span.attributes = {
                **span.attributes,
                "cost_status": "PRICING_MISSING",
                "currency": "USD",
            }
        await self.refresh_run_accounting(run)
        await self.session.commit()

    async def refresh_run_accounting(self, run: Run) -> None:
        spans = list(
            (
                await self.session.scalars(
                    select(Span).where(
                        Span.run_id == run.id,
                        Span.span_type == SpanType.MODEL,
                        Span.attributes["model_call"].as_boolean().is_(True),
                        Span.attributes["accounting_version"].as_integer() == 1,
                    )
                )
            ).all()
        )
        totals = {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cached_input_tokens": 0,
        }
        usage_complete = True
        cost_complete = True
        known_cost = Decimal(0)
        for span in spans:
            if span.status != SpanStatus.COMPLETED or not span.usage:
                usage_complete = False
                cost_complete = False
                continue
            for key in totals:
                value = span.usage.get(key)
                if isinstance(value, int):
                    totals[key] += value
            if span.attributes.get("estimated_cost") is None:
                cost_complete = False
            else:
                known_cost += Decimal(str(span.attributes["estimated_cost"]))
        run.usage = {
            **totals,
            "accounting_version": 1,
            "complete": usage_complete,
            "estimated": any(
                item.usage.get("input_tokens_estimated")
                or item.usage.get("output_tokens_estimated")
                for item in spans
            ),
        }
        run.metadata_json = {
            **run.metadata_json,
            "accounting": {
                "version": 1,
                "model_calls": len(spans),
                "usage_complete": usage_complete,
                "cost_complete": cost_complete,
                "known_cost_subtotal": str(known_cost),
                "currency": "USD",
                "evaluation_mode": run.metadata_json.get("evaluation_mode", False),
            },
        }
        run.estimated_cost = known_cost if cost_complete else None
