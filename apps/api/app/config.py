"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Annotated

from pydantic import SecretStr, field_validator
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
    azure_openai_api_key: SecretStr | None = None
    azure_openai_base_url: str | None = None
    azure_openai_deployment_name: str = "gpt-5.6-luna"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings object."""

    return Settings()
