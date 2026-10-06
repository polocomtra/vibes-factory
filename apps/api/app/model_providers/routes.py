"""Ephemeral model connection test endpoint."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_settings
from ..model_connections.service import (
    ModelConnectionError,
    resolve_connection_endpoint,
)
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
    pinned_addresses = None
    if payload.provider == "azure_openai":
        try:
            payload.base_url, pinned_addresses = await resolve_connection_endpoint(
                payload.provider, payload.base_url
            )
        except ModelConnectionError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail={
                    "code": error.code,
                    "message": error.message,
                    "details": {},
                },
            ) from error
    return await test_connection(payload, registry, pinned_addresses=pinned_addresses)
