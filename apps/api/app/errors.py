"""Stable API error envelope and exception handlers."""

from typing import Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

logger = structlog.get_logger(__name__)


def error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "request_id": getattr(request.state, "request_id", None),
                "details": details or {},
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register consistent validation and internal error responses."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            code="VALIDATION_ERROR",
            message="The request could not be validated.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"issues": exc.errors()},
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        detail: dict[str, Any] = exc.detail if isinstance(exc.detail, dict) else {}
        code = detail.get("code", "HTTP_ERROR")
        message = detail.get("message", "The request could not be completed.")
        details = detail.get("details", {})
        response = error_response(
            request,
            code=code,
            message=message,
            status_code=exc.status_code,
            details=details,
        )
        if exc.headers:
            for key, value in exc.headers.items():
                response.headers[key] = value
        return response

    @app.exception_handler(Exception)
    async def internal_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("unhandled_exception", exc_info=exc)
        return error_response(
            request,
            code="INTERNAL_ERROR",
            message="An unexpected error occurred.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )
