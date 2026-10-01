"""Authenticated workspace monitoring APIs."""

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import Agent, AgentVersion, User
from ..workspaces.authorization import require_workspace_access
from .schemas import MonitoringOptions, MonitoringSummary, MonitoringTimeseries
from .service import options, summary, timeseries

router = APIRouter(
    prefix="/v1/workspaces/{workspace_id}/monitoring", tags=["monitoring"]
)
RunStatusFilter = Literal[
    "QUEUED",
    "RUNNING",
    "WAITING_TOOL",
    "WAITING_APPROVAL",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]


async def _filters(
    workspace_id: UUID,
    user: User,
    session: AsyncSession,
    agent_id: UUID | None,
    agent_version_id: UUID | None,
    provider: str | None,
    model: str | None,
    status: RunStatusFilter | None,
) -> dict[str, object]:
    await require_workspace_access(session, user.id, workspace_id)
    if agent_version_id is not None:
        predicates = [
            AgentVersion.id == agent_version_id,
            AgentVersion.workspace_id == workspace_id,
        ]
        if agent_id is not None:
            predicates.append(AgentVersion.agent_id == agent_id)
        version = await session.scalar(select(AgentVersion).where(*predicates))
        if version is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "RESOURCE_NOT_FOUND",
                    "message": "The agent version was not found in this workspace.",
                    "details": {},
                },
            )
    if agent_id is not None:
        agent = await session.scalar(
            select(Agent.id).where(
                Agent.id == agent_id, Agent.workspace_id == workspace_id
            )
        )
        if agent is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "code": "RESOURCE_NOT_FOUND",
                    "message": "The agent was not found in this workspace.",
                    "details": {},
                },
            )
    return {
        "agent_id": agent_id,
        "agent_version_id": agent_version_id,
        "provider": provider,
        "model": model,
        "status": status,
    }


def _period(from_: datetime | None, to: datetime | None) -> tuple[datetime, datetime]:
    end = to or datetime.now(UTC)
    start = from_ or end - timedelta(days=7)
    if (
        start.tzinfo is None
        or end.tzinfo is None
        or end <= start
        or end - start > timedelta(days=90)
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "A timezone-aware positive period of at most "
                "90 days is required.",
                "details": {"fields": ["from", "to"]},
            },
        )
    return start, end


@router.get("/summary", response_model=MonitoringSummary)
async def get_summary(
    workspace_id: UUID,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    agent_id: UUID | None = None,
    agent_version_id: UUID | None = None,
    provider: str | None = Query(default=None, max_length=64),
    model: str | None = Query(default=None, max_length=255),
    status: RunStatusFilter | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MonitoringSummary:
    filters = await _filters(
        workspace_id, user, session, agent_id, agent_version_id, provider, model, status
    )
    start, end = _period(from_, to)
    return MonitoringSummary.model_validate(
        await summary(session, workspace_id, start, end, filters)
    )


@router.get("/timeseries", response_model=MonitoringTimeseries)
async def get_timeseries(
    workspace_id: UUID,
    metric: str = Query(..., max_length=32),
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    interval: str = Query(default="auto"),
    agent_id: UUID | None = None,
    agent_version_id: UUID | None = None,
    provider: str | None = Query(default=None, max_length=64),
    model: str | None = Query(default=None, max_length=255),
    status: RunStatusFilter | None = None,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MonitoringTimeseries:
    filters = await _filters(
        workspace_id, user, session, agent_id, agent_version_id, provider, model, status
    )
    start, end = _period(from_, to)
    try:
        data = await timeseries(
            session, workspace_id, metric, start, end, interval, filters
        )
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail={"code": "VALIDATION_ERROR", "message": str(error), "details": {}},
        ) from None
    return MonitoringTimeseries.model_validate(data)


@router.get("/options", response_model=MonitoringOptions)
async def get_options(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MonitoringOptions:
    await require_workspace_access(session, user.id, workspace_id)
    return MonitoringOptions.model_validate(await options(session, workspace_id))
