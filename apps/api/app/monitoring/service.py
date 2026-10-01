"""PostgreSQL-backed metrics aggregation over operational runs and spans."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Float,
    Numeric,
    and_,
    case,
    cast,
    func,
    not_,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    Agent,
    AgentVersion,
    EvaluationResult,
    Run,
    RunStatus,
    Session,
    Span,
    SpanStatus,
    SpanType,
)

MAX_RANGE = timedelta(days=90)
METRICS = frozenset(
    {
        "runs",
        "failures",
        "latency",
        "success_rate",
        "p95_latency",
        "model_latency",
        "tokens",
        "input_tokens",
        "output_tokens",
        "estimated_cost",
        "tool_failures",
    }
)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("from and to must include a timezone")
    return value.astimezone(UTC)


def _base_query(
    workspace_id: UUID, from_: datetime, to: datetime, filters: dict[str, Any]
):
    statement = (
        select(
            Run.id.label("run_id"),
            Run.status.label("status"),
            Run.started_at.label("started_at"),
            Run.completed_at.label("completed_at"),
            Run.created_at.label("created_at"),
            Run.agent_id.label("agent_id"),
            Run.agent_version_id.label("agent_version_id"),
            AgentVersion.model_provider.label("provider"),
            AgentVersion.model_name.label("model"),
            Run.metadata_json["accounting_version"]
            .as_integer()
            .label("accounting_version"),
            Run.metadata_json["accounting"]["usage_complete"]
            .as_boolean()
            .label("usage_complete"),
            Run.metadata_json["accounting"]["cost_complete"]
            .as_boolean()
            .label("cost_complete"),
        )
        .join(AgentVersion, AgentVersion.id == Run.agent_version_id)
        .outerjoin(Session, Session.id == Run.session_id)
        .where(
            Run.workspace_id == workspace_id,
            Run.created_at >= from_,
            Run.created_at < to,
            not_(Run.metadata_json["evaluation_mode"].as_boolean().is_(True)),
            or_(
                Session.id.is_(None),
                Session.metadata_json["source"].as_string() != "evaluation",
            ),
            not_(
                Run.root_run_id.in_(
                    select(EvaluationResult.run_id).where(
                        EvaluationResult.run_id.is_not(None)
                    )
                )
            ),
        )
    )
    if filters.get("agent_id"):
        statement = statement.where(Run.agent_id == filters["agent_id"])
    if filters.get("agent_version_id"):
        statement = statement.where(Run.agent_version_id == filters["agent_version_id"])
    if filters.get("provider"):
        statement = statement.where(
            AgentVersion.model_provider == filters["provider"].lower()
        )
    if filters.get("model"):
        statement = statement.where(AgentVersion.model_name == filters["model"].lower())
    if filters.get("status"):
        statement = statement.where(Run.status == filters["status"].upper())
    return statement


def _duration_expr(source):
    return cast(
        func.extract("epoch", source.c.completed_at - source.c.started_at) * 1000,
        Float,
    )


async def summary(
    session: AsyncSession,
    workspace_id: UUID,
    from_: datetime,
    to: datetime,
    filters: dict[str, Any],
) -> dict[str, Any]:
    from_, to = _utc(from_), _utc(to)
    if to <= from_ or to - from_ > MAX_RANGE:
        raise ValueError("Monitoring range must be positive and no longer than 90 days")
    runs = _base_query(workspace_id, from_, to, filters).subquery("monitoring_runs")
    latency = _duration_expr(runs)
    done = runs.c.status.in_(
        [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]
    )
    terminal_latency = and_(
        done, runs.c.started_at.is_not(None), runs.c.completed_at.is_not(None)
    )
    run_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count(case((runs.c.status == RunStatus.COMPLETED, 1))).label(
                    "completed"
                ),
                func.count(case((runs.c.status == RunStatus.FAILED, 1))).label(
                    "failed"
                ),
                func.count(case((runs.c.status == RunStatus.CANCELLED, 1))).label(
                    "cancelled"
                ),
                func.count(case((~done, 1))).label("in_progress"),
                func.count(case((terminal_latency, 1))).label("latency_count"),
                func.avg(case((terminal_latency, latency))).label("average_ms"),
                func.percentile_cont(0.95)
                .within_group(case((terminal_latency, latency)))
                .label("p95_ms"),
            ).select_from(runs)
        )
    ).one()

    model_filter = Span.span_type == SpanType.MODEL
    model_join = (
        select(Span)
        .join(runs, runs.c.run_id == Span.run_id)
        .where(
            model_filter,
            Span.attributes["model_call"].as_boolean().is_(True),
            Span.attributes["accounting_version"].as_integer() == 1,
        )
    )
    model_spans = model_join.subquery("monitoring_model_spans")
    input_tokens = cast(model_spans.c.usage["input_tokens"].as_integer(), BigInteger)
    output_tokens = cast(model_spans.c.usage["output_tokens"].as_integer(), BigInteger)
    cost = cast(model_spans.c.attributes["estimated_cost"].as_string(), Numeric(18, 8))
    missing_call = or_(
        model_spans.c.status != SpanStatus.COMPLETED,
        model_spans.c.attributes["estimated_cost"].as_string().is_(None),
    )
    model_row = (
        await session.execute(
            select(
                func.coalesce(func.sum(input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(output_tokens), 0).label("output_tokens"),
                func.coalesce(
                    func.sum(
                        func.extract(
                            "epoch",
                            model_spans.c.completed_at - model_spans.c.started_at,
                        )
                        * 1000
                    ),
                    0,
                ).label("duration_sum"),
                func.count(case((model_spans.c.completed_at.is_not(None), 1))).label(
                    "duration_count"
                ),
                func.coalesce(func.sum(cost), 0).label("known_cost"),
                func.count(case((missing_call, 1))).label("missing_cost_calls"),
                func.count().label("calls"),
                func.count(
                    case(
                        (
                            model_spans.c.usage["input_tokens_estimated"]
                            .as_boolean()
                            .is_(True),
                            1,
                        )
                    )
                ).label("estimated_input_calls"),
                func.count(
                    case(
                        (
                            model_spans.c.usage["output_tokens_estimated"]
                            .as_boolean()
                            .is_(True),
                            1,
                        )
                    )
                ).label("estimated_output_calls"),
            ).select_from(model_spans)
        )
    ).one()

    tool_spans = (
        select(Span.status)
        .join(runs, runs.c.run_id == Span.run_id)
        .where(
            Span.span_type == SpanType.TOOL,
            Span.attributes["child_agent_id"].as_string().is_(None),
        )
        .subquery()
    )
    tool_row = (
        await session.execute(
            select(
                func.count(case((tool_spans.c.status == SpanStatus.FAILED, 1))).label(
                    "failed"
                ),
                func.count(
                    case(
                        (
                            tool_spans.c.status.in_(
                                [SpanStatus.COMPLETED, SpanStatus.FAILED]
                            ),
                            1,
                        )
                    )
                ).label("terminal"),
            ).select_from(tool_spans)
        )
    ).one()
    denominator = run_row.completed + run_row.failed
    # Count only new-format runs inside the same filtered cohort.
    accounted = await session.scalar(
        select(func.count()).select_from(runs).where(runs.c.accounting_version == 1)
    )
    usage_complete_runs = await session.scalar(
        select(func.count())
        .select_from(runs)
        .where(runs.c.accounting_version == 1, runs.c.usage_complete.is_(True))
    )
    cost_complete_runs = await session.scalar(
        select(func.count())
        .select_from(runs)
        .where(runs.c.accounting_version == 1, runs.c.cost_complete.is_(True))
    )
    total = int(run_row.total)
    known_cost = Decimal(str(model_row.known_cost or 0))
    return {
        "period": {"from": from_, "to": to},
        "filters": filters,
        "runs": {
            "total": total,
            "completed": int(run_row.completed),
            "failed": int(run_row.failed),
            "cancelled": int(run_row.cancelled),
            "in_progress": int(run_row.in_progress),
            "success_rate": float(run_row.completed / denominator)
            if denominator
            else None,
            "failure_rate": float(run_row.failed / denominator)
            if denominator
            else None,
        },
        "latency": {
            "average_ms": float(run_row.average_ms)
            if run_row.average_ms is not None
            else None,
            "p95_ms": float(run_row.p95_ms) if run_row.p95_ms is not None else None,
        },
        "model_latency": {
            "average_ms": float(model_row.duration_sum / model_row.duration_count)
            if model_row.duration_count
            else None
        },
        "usage": {
            "input_tokens": int(model_row.input_tokens),
            "output_tokens": int(model_row.output_tokens),
        },
        "estimated_cost": (
            str(known_cost)
            if total == 0
            or (
                int(accounted or 0) == total
                and model_row.missing_cost_calls == 0
                and run_row.in_progress == 0
            )
            or model_row.calls > model_row.missing_cost_calls
            or known_cost
            else None
        ),
        "currency": "USD",
        "tool_failures": {
            "count": int(tool_row.failed),
            "rate": float(tool_row.failed / tool_row.terminal)
            if tool_row.terminal
            else None,
        },
        "data_quality": {
            "accounted_runs": int(accounted or 0),
            "legacy_runs": max(0, total - int(accounted or 0)),
            "usage_complete_runs": int(usage_complete_runs or 0),
            "cost_complete_runs": int(cost_complete_runs or 0),
            "missing_pricing_or_usage_calls": int(model_row.missing_cost_calls),
            "estimated_input_calls": int(model_row.estimated_input_calls),
            "estimated_output_calls": int(model_row.estimated_output_calls),
            "cost_complete": (
                int(accounted or 0) == total
                and model_row.missing_cost_calls == 0
                and run_row.in_progress == 0
            ),
        },
    }


async def timeseries(
    session: AsyncSession,
    workspace_id: UUID,
    metric: str,
    from_: datetime,
    to: datetime,
    interval: str,
    filters: dict[str, Any],
) -> dict[str, Any]:
    from_, to = _utc(from_), _utc(to)
    if metric not in METRICS:
        raise ValueError("Unsupported monitoring metric")
    if to <= from_ or to - from_ > MAX_RANGE:
        raise ValueError("Monitoring range must be positive and no longer than 90 days")
    if interval == "auto":
        interval = "1h" if to - from_ <= timedelta(hours=24) else "1d"
    if interval not in {"1h", "1d"}:
        raise ValueError("interval must be auto, 1h, or 1d")
    unit = "hour" if interval == "1h" else "day"
    run_query = _base_query(workspace_id, from_, to, filters).subquery("series_runs")
    bucket = func.date_trunc(unit, func.timezone("UTC", run_query.c.created_at)).label(
        "bucket"
    )
    values: dict[datetime, Any]
    if metric in {"runs", "failures", "success_rate"}:
        success = func.count(case((run_query.c.status == RunStatus.COMPLETED, 1)))
        failed = func.count(case((run_query.c.status == RunStatus.FAILED, 1)))
        eligible = success + failed
        value = (
            func.count()
            if metric == "runs"
            else failed
            if metric == "failures"
            else success / func.nullif(eligible, 0)
        )
        rows = (
            await session.execute(
                select(bucket, value.label("value")).group_by(bucket).order_by(bucket)
            )
        ).all()
        values = {
            row.bucket.replace(tzinfo=UTC): (
                float(row.value) if row.value is not None else None
            )
            for row in rows
        }
        complete = True
    elif metric in {"latency", "p95_latency"}:
        duration = cast(
            func.extract("epoch", run_query.c.completed_at - run_query.c.started_at)
            * 1000,
            Float,
        )
        terminal = and_(
            run_query.c.status.in_(
                [RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED]
            ),
            run_query.c.started_at.is_not(None),
            run_query.c.completed_at.is_not(None),
        )
        aggregate = (
            func.avg(case((terminal, duration)))
            if metric == "latency"
            else func.percentile_cont(0.95).within_group(case((terminal, duration)))
        )
        rows = (
            await session.execute(
                select(bucket, aggregate.label("value"))
                .where(terminal)
                .group_by(bucket)
                .order_by(bucket)
            )
        ).all()
        values = {row.bucket.replace(tzinfo=UTC): float(row.value) for row in rows}
        complete = True
    else:
        span_query = (
            select(Span)
            .join(run_query, run_query.c.run_id == Span.run_id)
            .where(
                Span.span_type
                == (SpanType.TOOL if metric == "tool_failures" else SpanType.MODEL)
            )
        )
        if metric != "tool_failures":
            span_query = span_query.where(
                Span.attributes["model_call"].as_boolean().is_(True),
                Span.attributes["accounting_version"].as_integer() == 1,
            )
        else:
            span_query = span_query.where(
                Span.attributes["child_agent_id"].as_string().is_(None)
            )
        spans = span_query.subquery("series_spans")
        span_bucket = func.date_trunc(
            unit, func.timezone("UTC", spans.c.started_at)
        ).label("bucket")
        if metric == "tool_failures":
            aggregate = func.count(case((spans.c.status == SpanStatus.FAILED, 1)))
            rows = (
                await session.execute(
                    select(span_bucket, aggregate.label("value")).group_by(span_bucket)
                )
            ).all()
            values = {row.bucket.replace(tzinfo=UTC): float(row.value) for row in rows}
            complete = True
        elif metric in {"input_tokens", "output_tokens", "tokens"}:
            in_count = cast(spans.c.usage["input_tokens"].as_integer(), BigInteger)
            out_count = cast(spans.c.usage["output_tokens"].as_integer(), BigInteger)
            span_aggregate = (
                in_count
                if metric == "input_tokens"
                else out_count
                if metric == "output_tokens"
                else in_count + out_count
            )
            rows = (
                await session.execute(
                    select(
                        span_bucket,
                        func.sum(span_aggregate).label("value"),
                        func.count(
                            case((spans.c.status != SpanStatus.COMPLETED, 1))
                        ).label("incomplete"),
                    ).group_by(span_bucket)
                )
            ).all()
            run_bucket = func.date_trunc(
                unit, func.timezone("UTC", run_query.c.created_at)
            ).label("bucket")
            usage_quality = await session.execute(
                select(
                    run_bucket,
                    func.count().label("total_runs"),
                    func.count(
                        case(
                            (
                                and_(
                                    run_query.c.status.in_(
                                        [
                                            RunStatus.COMPLETED,
                                            RunStatus.FAILED,
                                            RunStatus.CANCELLED,
                                        ]
                                    ),
                                    run_query.c.accounting_version == 1,
                                    run_query.c.usage_complete.is_(True),
                                ),
                                1,
                            )
                        )
                    ).label("complete_runs"),
                ).group_by(run_bucket)
            )
            run_quality = {
                row.bucket.replace(tzinfo=UTC): (row.total_runs, row.complete_runs)
                for row in usage_quality
            }
            values = {
                row.bucket.replace(tzinfo=UTC): (
                    float(row.value) if row.value is not None else None,
                    row.incomplete == 0,
                )
                for row in rows
            }
            complete = True
        else:
            cost = cast(spans.c.attributes["estimated_cost"].as_string(), Float)
            rows = (
                await session.execute(
                    select(
                        span_bucket,
                        func.sum(cost).label("value"),
                        func.count(
                            case(
                                (
                                    spans.c.attributes["estimated_cost"]
                                    .as_string()
                                    .is_(None),
                                    1,
                                )
                            )
                        ).label("incomplete"),
                    ).group_by(span_bucket)
                )
            ).all()
            run_bucket = func.date_trunc(
                unit, func.timezone("UTC", run_query.c.created_at)
            ).label("bucket")
            cost_quality = await session.execute(
                select(
                    run_bucket,
                    func.count().label("total_runs"),
                    func.count(
                        case(
                            (
                                and_(
                                    run_query.c.status.in_(
                                        [
                                            RunStatus.COMPLETED,
                                            RunStatus.FAILED,
                                            RunStatus.CANCELLED,
                                        ]
                                    ),
                                    run_query.c.accounting_version == 1,
                                    run_query.c.cost_complete.is_(True),
                                ),
                                1,
                            )
                        )
                    ).label("complete_runs"),
                ).group_by(run_bucket)
            )
            run_quality = {
                row.bucket.replace(tzinfo=UTC): (row.total_runs, row.complete_runs)
                for row in cost_quality
            }
            values = {
                row.bucket.replace(tzinfo=UTC): (
                    float(row.value) if row.value is not None else None,
                    row.incomplete == 0,
                )
                for row in rows
            }
            complete = True

    step = timedelta(hours=1) if interval == "1h" else timedelta(days=1)
    cursor = (
        from_.replace(minute=0, second=0, microsecond=0)
        if interval == "1h"
        else from_.replace(hour=0, minute=0, second=0, microsecond=0)
    )
    bucket_count = int((to - cursor + step - timedelta(microseconds=1)) // step)
    if bucket_count > 500:
        raise ValueError("The requested interval would return more than 500 points")
    points = []
    while cursor < to:
        raw = values.get(cursor)
        is_complete = complete
        point_value: float | int | None
        quality = (
            run_quality.get(cursor)
            if metric in {"tokens", "input_tokens", "output_tokens", "estimated_cost"}
            else None
        )
        if isinstance(raw, tuple):
            point_value, is_complete = raw
            if quality is not None:
                total_runs, complete_runs = quality
                is_complete = is_complete and total_runs == complete_runs
                if not is_complete and point_value == 0:
                    point_value = None
        elif raw is None:
            if quality is not None and quality[0] > quality[1]:
                point_value = None
                is_complete = False
            else:
                point_value = (
                    0
                    if metric
                    in {
                        "runs",
                        "failures",
                        "tokens",
                        "input_tokens",
                        "output_tokens",
                        "estimated_cost",
                        "tool_failures",
                    }
                    else None
                )
        else:
            point_value = raw
        points.append(
            {"timestamp": cursor, "value": point_value, "complete": is_complete}
        )
        cursor += step
    return {"metric": metric, "interval": interval, "points": points}


async def options(session: AsyncSession, workspace_id: UUID) -> dict[str, Any]:
    agent_rows = (
        await session.execute(
            select(Agent.id, Agent.name)
            .where(Agent.workspace_id == workspace_id)
            .order_by(Agent.name)
        )
    ).all()
    model_rows = (
        await session.execute(
            select(AgentVersion.model_provider, AgentVersion.model_name)
            .where(AgentVersion.workspace_id == workspace_id)
            .distinct()
            .order_by(AgentVersion.model_provider, AgentVersion.model_name)
        )
    ).all()
    return {
        "agents": [{"id": str(row.id), "name": row.name} for row in agent_rows],
        "models": [
            {"provider": row.model_provider, "model": row.model_name}
            for row in model_rows
        ],
    }
