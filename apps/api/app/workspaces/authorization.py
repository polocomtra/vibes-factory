"""Reusable workspace membership and role authorization checks."""

from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import User, WorkspaceMember, WorkspaceRole


async def require_workspace_access(
    session: AsyncSession,
    user_id: UUID,
    workspace_id: UUID,
) -> WorkspaceMember:
    """Require that a local user belongs to the requested workspace."""

    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "WORKSPACE_ACCESS_DENIED",
                "message": "You do not have access to this workspace.",
                "details": {},
            },
        )
    return member


async def require_workspace_membership(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMember:
    """FastAPI dependency for any member-level workspace operation."""

    return await require_workspace_access(session, user.id, workspace_id)


async def require_workspace_owner(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMember:
    """FastAPI dependency for owner-only workspace operations."""

    member = await require_workspace_access(session, user.id, workspace_id)
    if member.role != WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "WORKSPACE_OWNER_REQUIRED",
                "message": "Only the workspace owner can perform this action.",
                "details": {},
            },
        )
    return member
