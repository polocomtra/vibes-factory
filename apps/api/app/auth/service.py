"""Supabase Auth token verification and platform identity contracts."""

from dataclasses import dataclass

import httpx
from fastapi import HTTPException, status

from ..config import Settings


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Identity extracted from a verified Supabase access token."""

    user_id: str
    email: str


def _auth_exception(
    code: str,
    message: str,
    status_code: int,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "details": {}},
        headers=(
            {"WWW-Authenticate": "Bearer"}
            if status_code == status.HTTP_401_UNAUTHORIZED
            else None
        ),
    )


async def verify_supabase_token(
    token: str, settings: Settings
) -> AuthenticatedPrincipal:
    """Ask Supabase Auth to validate a bearer token and return platform identity."""

    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise _auth_exception(
            "AUTH_NOT_CONFIGURED",
            "Supabase authentication is not configured.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    endpoint = f"{settings.supabase_url.rstrip('/')}/auth/v1/user"
    headers = {
        "apikey": settings.supabase_publishable_key,
        "Authorization": f"Bearer {token}",
    }

    try:
        async with httpx.AsyncClient(
            timeout=settings.supabase_auth_timeout_seconds
        ) as client:
            response = await client.get(endpoint, headers=headers)
    except httpx.HTTPError as exc:
        raise _auth_exception(
            "AUTH_PROVIDER_UNAVAILABLE",
            "The authentication provider is temporarily unavailable.",
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ) from exc

    if response.status_code != status.HTTP_200_OK:
        if response.status_code >= status.HTTP_500_INTERNAL_SERVER_ERROR:
            raise _auth_exception(
                "AUTH_PROVIDER_UNAVAILABLE",
                "The authentication provider is temporarily unavailable.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        raise _auth_exception(
            "INVALID_TOKEN",
            "The access token is invalid or expired.",
            status.HTTP_401_UNAUTHORIZED,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise _auth_exception(
            "INVALID_TOKEN",
            "The authentication provider returned an invalid identity.",
            status.HTTP_401_UNAUTHORIZED,
        ) from exc

    user_id = payload.get("id")
    email = payload.get("email")
    if (
        not isinstance(user_id, str)
        or not user_id
        or not isinstance(email, str)
        or not email
    ):
        raise _auth_exception(
            "INVALID_TOKEN",
            "The access token does not contain a usable identity.",
            status.HTTP_401_UNAUTHORIZED,
        )

    return AuthenticatedPrincipal(user_id=user_id, email=email)
