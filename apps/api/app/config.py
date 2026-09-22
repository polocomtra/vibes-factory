"""Application configuration loaded from environment variables."""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the VibesFactory API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="VF_",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "VibesFactory API"
    environment: str = "local"
    log_level: str = "INFO"
    database_url: str = (
        "postgresql+asyncpg://vibesfactory:vibesfactory@127.0.0.1:15432/vibesfactory"
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]
    otel_service_name: str = "vibesfactory-api"
    otel_console_exporter: bool = False
    supabase_url: str | None = None
    supabase_publishable_key: str | None = None
    supabase_jwt_jwks_url: str | None = None
    supabase_auth_timeout_seconds: float = 5.0
    model_provider_timeout_seconds: float = 60.0
    gemini_api_key: SecretStr | None = None
    exa_api_key: SecretStr | None = None
    encryption_master_key: SecretStr | None = None
    enable_mcp: bool = True
    mcp_allow_http: bool = True
    mcp_allowed_private_hosts: Annotated[list[str], NoDecode] = []
    mcp_connect_timeout_seconds: float = 10.0
    mcp_operation_timeout_seconds: float = 30.0
    mcp_max_discovered_tools: int = 200
    mcp_max_output_bytes: int = 256_000
    # Host-local worker default. Docker Compose overrides this with the
    # service DNS name `http://embedding:8100`.
    embedding_service_url: str = "http://127.0.0.1:8100"
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_revision: str = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    embedding_timeout_seconds: float = Field(default=90.0, gt=0, le=900)
    embedding_batch_size: int = Field(default=8, ge=1, le=32)
    # Keep host-local development writable without requiring sudo. Docker
    # Compose overrides this with its mounted /var/lib/vibesfactory volume.
    blob_storage_path: str = "~/.vibesfactory/blobs"
    blob_storage_bucket: str | None = None
    max_document_bytes: int = 20 * 1024 * 1024
    ingestion_poll_seconds: float = 1.0
    workflow_poll_seconds: float = 1.0
    workflow_lease_seconds: int = Field(default=120, ge=30, le=900)
    workflow_heartbeat_seconds: int = Field(default=30, ge=5, le=300)
    workflow_event_heartbeat_seconds: int = Field(default=15, ge=5, le=120)
    workflow_default_timeout_seconds: int = Field(default=900, ge=1, le=3_600)
    azure_openai_api_key: SecretStr | None = None
    azure_openai_base_url: str | None = None
    azure_openai_deployment_name: str = "gpt-5.6-luna"
    # These are estimates for the configured Azure deployment, not provider
    # billing data. Override them with the rates from the Azure pricing plan.
    azure_openai_input_price_per_million: Decimal | None = Decimal("1.25")
    azure_openai_output_price_per_million: Decimal | None = Decimal("10")
    azure_openai_cached_input_price_per_million: Decimal | None = Decimal("0.125")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("mcp_allowed_private_hosts", mode="before")
    @classmethod
    def parse_mcp_allowed_private_hosts(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [host.strip().lower() for host in value.split(",") if host.strip()]
        return [host.strip().lower() for host in value]


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""

    return Settings()
