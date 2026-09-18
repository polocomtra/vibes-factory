from typing import Self

import pytest
from fastapi import HTTPException

from apps.api.app.auth.service import verify_supabase_token
from apps.api.app.config import Settings


class FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict[str, str]:
        return self._payload


class FakeClient:
    response = FakeResponse(401)

    def __init__(self, **_: object) -> None:
        pass

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def get(self, *_: object, **__: object) -> FakeResponse:
        return self.response


def auth_settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_publishable_key="sb_publishable_test",
    )


@pytest.mark.asyncio
async def test_invalid_jwt_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.api.app.auth.service.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(HTTPException) as error:
        await verify_supabase_token("invalid-token", auth_settings())

    assert error.value.status_code == 401
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_expired_jwt_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "apps.api.app.auth.service.httpx.AsyncClient",
        FakeClient,
    )

    with pytest.raises(HTTPException) as error:
        await verify_supabase_token("expired-token", auth_settings())

    assert error.value.status_code == 401
    assert isinstance(error.value.detail, dict)
    assert error.value.detail["code"] == "INVALID_TOKEN"


@pytest.mark.asyncio
async def test_valid_jwt_resolves_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClient.response = FakeResponse(
        200,
        {"id": "supabase-user-id", "email": "user@example.com"},
    )
    monkeypatch.setattr(
        "apps.api.app.auth.service.httpx.AsyncClient",
        FakeClient,
    )

    principal = await verify_supabase_token("valid-token", auth_settings())

    assert principal.user_id == "supabase-user-id"
    assert principal.email == "user@example.com"
    FakeClient.response = FakeResponse(401)
