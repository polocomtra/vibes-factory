"""Public approval request API contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..models import ApprovalKind, ApprovalStatus


class ApprovalRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    kind: ApprovalKind
    run_id: UUID | None
    workflow_run_id: UUID | None
    workflow_node_run_id: UUID | None
    tool_version_id: UUID | None
    tool_call_id: str | None
    status: ApprovalStatus
    requested_action: str
    arguments: dict[str, Any]
    risk_reason: str
    expires_at: datetime
    requested_at: datetime
    resolved_at: datetime | None
    resolved_by: UUID | None


class ApprovalRequestCollectionResponse(BaseModel):
    data: list[ApprovalRequestResponse]
    pagination: dict[str, Any]


class ApprovalResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2_000)


ApprovalStatusFilter = Literal["PENDING", "APPROVED", "REJECTED", "EXPIRED"]
