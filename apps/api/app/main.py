"""VibesFactory FastAPI application entrypoint."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette import status

from .agents.routes import router as agent_router
from .config import get_settings
from .db import check_database, dispose_engine
from .errors import error_response, register_exception_handlers
from .logging import configure_logging
from .middleware import request_id_middleware
from .model_providers.routes import router as model_provider_router
from .runs.routes import router as run_router
from .sessions.routes import router as session_router
from .telemetry import initialize_telemetry
from .tools.routes import router as tool_router
from .traces.routes import router as trace_router
from .workspaces.routes import router as workspace_router

settings = get_settings()
configure_logging(settings)
logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_telemetry(settings)
    logger.info("application_started", environment=settings.environment)
    yield
    await dispose_engine()
    logger.info("application_stopped")


app = FastAPI(
    title="VibesFactory API",
    version="0.1.0",
    description="Production-inspired Agentic AI Platform API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.middleware("http")(request_id_middleware)
register_exception_handlers(app)
app.include_router(workspace_router)
app.include_router(agent_router)
app.include_router(model_provider_router)
app.include_router(session_router)
app.include_router(run_router)
app.include_router(trace_router)
app.include_router(tool_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Return process health without requiring external dependencies."""

    return {"status": "ok", "service": "vibesfactory-api"}


@app.get("/ready", tags=["system"], response_model=None)
async def readiness(request: Request) -> dict[str, object] | JSONResponse:
    """Return readiness only when PostgreSQL is reachable."""

    try:
        await check_database()
    except (SQLAlchemyError, OSError):
        logger.exception("readiness_database_check_failed")
        return error_response(
            request,
            code="SERVICE_NOT_READY",
            message="The database is not ready.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={"database": "unavailable"},
        )

    return {"status": "ready", "checks": {"database": "ok"}}
