"""Pydantic contracts for identity and workspace APIs."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..models import WorkspaceRole


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    display_name: str | None = None
    avatar_url: str | None = None


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(
        min_length=1, max_length=100, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
    )

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class WorkspaceUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    role: WorkspaceRole
    created_at: datetime


class WorkspaceCollection(BaseModel):
    data: list[WorkspaceResponse]
    pagination: dict[str, str | bool | None]


class WorkspaceMemberCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if (
            "@" not in normalized
            or normalized.startswith("@")
            or normalized.endswith("@")
        ):
            raise ValueError("email must be valid")
        return normalized


class WorkspaceMemberResponse(BaseModel):
    user_id: UUID
    email: str
    role: WorkspaceRole
    created_at: datetime


class WorkspaceMemberCollection(BaseModel):
    data: list[WorkspaceMemberResponse]
    pagination: dict[str, str | bool | None]
