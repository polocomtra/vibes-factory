"""Agent resource authorization dependencies."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import Agent, User
from ..workspaces.authorization import require_workspace_access


async def require_agent_access(
    agent_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Agent:
    agent = await session.scalar(select(Agent).where(Agent.id == agent_id))
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "RESOURCE_NOT_FOUND",
                "message": "Agent was not found.",
                "details": {},
            },
        )
    await require_workspace_access(session, user.id, agent.workspace_id)
    return agent
