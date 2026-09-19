"""Dispatch boundary for local PostgreSQL and future Cloud Tasks adapters."""

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Job, JobStatus, JobType


class JobDispatcher(Protocol):
    async def dispatch(
        self,
        session: AsyncSession,
        job_type: JobType,
        resource_id: UUID,
        workspace_id: UUID | None,
        generation: int,
        payload: Mapping[str, object],
    ) -> Job: ...


class PostgresJobDispatcher:
    async def dispatch(
        self,
        session: AsyncSession,
        job_type: JobType,
        resource_id: UUID,
        workspace_id: UUID | None,
        generation: int,
        payload: Mapping[str, object],
    ) -> Job:
        job = Job(
            workspace_id=workspace_id,
            job_type=job_type,
            status=JobStatus.QUEUED,
            resource_type="document",
            resource_id=resource_id,
            generation=generation,
            payload=dict(payload),
        )
        session.add(job)
        return job
