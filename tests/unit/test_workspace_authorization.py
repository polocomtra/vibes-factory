from typing import cast
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.app.models import WorkspaceMember, WorkspaceRole
from apps.api.app.workspaces.authorization import require_workspace_access


class FakeSession:
    def __init__(self, member: WorkspaceMember | None) -> None:
        self.member = member

    async def scalar(self, _statement: object) -> WorkspaceMember | None:
        return self.member


@pytest.mark.asyncio
async def test_member_can_access_workspace() -> None:
    user_id = uuid4()
    workspace_id = uuid4()
    member = WorkspaceMember(
        workspace_id=workspace_id,
        user_id=user_id,
        role=WorkspaceRole.MEMBER,
    )

    result = await require_workspace_access(
        cast(AsyncSession, FakeSession(member)), user_id, workspace_id
    )

    assert result.role == WorkspaceRole.MEMBER


@pytest.mark.asyncio
async def test_non_member_cannot_access_workspace() -> None:
    with pytest.raises(HTTPException) as error:
        await require_workspace_access(
            cast(AsyncSession, FakeSession(None)), uuid4(), uuid4()
        )

    assert error.value.status_code == 403
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["code"] == "WORKSPACE_ACCESS_DENIED"
