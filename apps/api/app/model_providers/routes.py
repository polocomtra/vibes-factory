"""Ephemeral model connection test endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends

from ..config import get_settings
from ..workspaces.authorization import require_workspace_membership
from .registry import ModelProviderRegistry
from .schemas import ModelConnectionTestRequest, ModelConnectionTestResponse
from .service import test_connection

router = APIRouter(prefix="/v1", tags=["model-providers"])


@router.post(
    "/workspaces/{workspace_id}/model-connections:test",
    response_model=ModelConnectionTestResponse,
)
async def test_model_connection(
    workspace_id: UUID,
    payload: ModelConnectionTestRequest,
    _: object = Depends(require_workspace_membership),
) -> ModelConnectionTestResponse:
    registry = ModelProviderRegistry.from_settings(get_settings())
    return await test_connection(payload, registry)
