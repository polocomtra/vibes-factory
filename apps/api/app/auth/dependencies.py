"""FastAPI dependencies for authenticated requests."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings, get_settings
from ..db import get_session
from ..models import User
from .service import AuthenticatedPrincipal, verify_supabase_token

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedPrincipal:
    """Validate the bearer token before any protected API handler runs."""

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "AUTHENTICATION_REQUIRED",
                "message": "A valid bearer token is required.",
                "details": {},
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await verify_supabase_token(credentials.credentials, settings)


async def get_current_user(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve external Auth identity to the local application user."""

    user = await session.scalar(
        select(User).where(User.external_auth_id == principal.user_id)
    )
    if user is None:
        user = User(external_auth_id=principal.user_id, email=principal.email)
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    if user.email != principal.email:
        user.email = principal.email
        await session.commit()
        await session.refresh(user)
    return user
