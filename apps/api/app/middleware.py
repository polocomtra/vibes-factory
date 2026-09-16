"""HTTP middleware shared by the API."""

from uuid import uuid4

import structlog
from fastapi import Request

logger = structlog.get_logger(__name__)


async def request_id_middleware(request: Request, call_next):
    """Attach a request ID to every request and response."""

    request_id = request.headers.get("X-Request-ID") or f"req_{uuid4().hex}"
    request.state.request_id = request_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    logger.info("request_completed", method=request.method, path=request.url.path)
    return response
