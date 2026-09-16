"""Workspace and current-user HTTP routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.dependencies import get_current_user
from ..db import get_session
from ..models import User, Workspace, WorkspaceMember, WorkspaceRole
from .authorization import (
    require_workspace_access,
    require_workspace_membership,
    require_workspace_owner,
)
from .schemas import (
    UserResponse,
    WorkspaceCollection,
    WorkspaceCreate,
    WorkspaceMemberCollection,
    WorkspaceMemberCreate,
    WorkspaceMemberResponse,
    WorkspaceResponse,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/v1", tags=["identity"])


def _workspace_response(workspace: Workspace, role: WorkspaceRole) -> WorkspaceResponse:
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        role=role,
        created_at=workspace.created_at,
    )


@router.get("/me", response_model=UserResponse)
async def current_user(user: User = Depends(get_current_user)) -> User:
    return user


@router.post(
    "/workspaces", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED
)
async def create_workspace(
    payload: WorkspaceCreate,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    workspace = Workspace(name=payload.name, slug=payload.slug, owner_user_id=user.id)
    session.add(workspace)
    try:
        await session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id, user_id=user.id, role=WorkspaceRole.OWNER
            )
        )
        await session.commit()
        await session.refresh(workspace)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORKSPACE_SLUG_CONFLICT",
                "message": "You already have a workspace with this slug.",
                "details": {},
            },
        ) from exc
    return _workspace_response(workspace, WorkspaceRole.OWNER)


@router.get("/workspaces", response_model=WorkspaceCollection)
async def list_workspaces(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceCollection:
    rows = await session.execute(
        select(Workspace, WorkspaceMember.role)
        .join(WorkspaceMember, WorkspaceMember.workspace_id == Workspace.id)
        .where(WorkspaceMember.user_id == user.id)
        .order_by(Workspace.created_at.desc())
    )
    data = [_workspace_response(workspace, role) for workspace, role in rows.all()]
    return WorkspaceCollection(
        data=data,
        pagination={"next_cursor": None, "has_more": False},
    )


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    member = await require_workspace_access(session, user.id, workspace_id)
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WORKSPACE_NOT_FOUND",
                "message": "Workspace was not found.",
                "details": {},
            },
        )
    return _workspace_response(workspace, member.role)


@router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    payload: WorkspaceUpdate,
    _: WorkspaceMember = Depends(require_workspace_owner),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WORKSPACE_NOT_FOUND",
                "message": "Workspace was not found.",
                "details": {},
            },
        )
    workspace.name = payload.name
    await session.commit()
    await session.refresh(workspace)
    return _workspace_response(workspace, WorkspaceRole.OWNER)


@router.get(
    "/workspaces/{workspace_id}/members", response_model=WorkspaceMemberCollection
)
async def list_workspace_members(
    workspace_id: UUID,
    _: WorkspaceMember = Depends(require_workspace_membership),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMemberCollection:
    rows = await session.execute(
        select(WorkspaceMember, User)
        .join(User, User.id == WorkspaceMember.user_id)
        .where(WorkspaceMember.workspace_id == workspace_id)
        .order_by(
            (WorkspaceMember.role == WorkspaceRole.OWNER).desc(),
            WorkspaceMember.created_at.asc(),
        )
    )
    data = [
        WorkspaceMemberResponse(
            user_id=member.user_id,
            email=user.email,
            role=member.role,
            created_at=member.created_at,
        )
        for member, user in rows.all()
    ]
    return WorkspaceMemberCollection(
        data=data,
        pagination={"next_cursor": None, "has_more": False},
    )


@router.post(
    "/workspaces/{workspace_id}/members",
    response_model=WorkspaceMemberResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_workspace_member(
    workspace_id: UUID,
    payload: WorkspaceMemberCreate,
    _: WorkspaceMember = Depends(require_workspace_owner),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceMemberResponse:
    user = await session.scalar(
        select(User).where(func.lower(User.email) == payload.email)
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "USER_NOT_FOUND_FOR_MEMBERSHIP",
                "message": "The user must sign in to VibesFactory before being added.",
                "details": {},
            },
        )

    existing = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORKSPACE_MEMBER_ALREADY_EXISTS",
                "message": "This user is already a member of the workspace.",
                "details": {},
            },
        )

    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user.id,
        role=WorkspaceRole.MEMBER,
    )
    session.add(member)
    try:
        await session.commit()
        await session.refresh(member)
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORKSPACE_MEMBER_ALREADY_EXISTS",
                "message": "This user is already a member of the workspace.",
                "details": {},
            },
        ) from exc
    return WorkspaceMemberResponse(
        user_id=user.id,
        email=user.email,
        role=member.role,
        created_at=member.created_at,
    )


@router.delete(
    "/workspaces/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_workspace_member(
    workspace_id: UUID,
    user_id: UUID,
    _: WorkspaceMember = Depends(require_workspace_owner),
    session: AsyncSession = Depends(get_session),
) -> Response:
    member = await session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id,
            WorkspaceMember.user_id == user_id,
        )
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "WORKSPACE_MEMBER_NOT_FOUND",
                "message": "Workspace member was not found.",
                "details": {},
            },
        )
    if member.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORKSPACE_OWNER_CANNOT_BE_REMOVED",
                "message": "The workspace owner cannot be removed.",
                "details": {},
            },
        )
    await session.delete(member)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
