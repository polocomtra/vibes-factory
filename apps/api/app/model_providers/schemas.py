"""API schemas for non-persistent model connection probes."""

from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)


class ModelConnectionTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["google", "openai", "azure_openai", "deepseek"]
    model_name: str = Field(min_length=1, max_length=255)
    deployment_name: str | None = Field(default=None, max_length=255)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: SecretStr = Field(min_length=1, repr=False)

    @field_validator("provider", "model_name", "deployment_name", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_provider_fields(self) -> "ModelConnectionTestRequest":
        if self.provider == "azure_openai" and not self.deployment_name:
            raise ValueError("deployment_name is required for Azure OpenAI")
        if self.provider == "azure_openai" and not self.base_url:
            raise ValueError("base_url is required for Azure OpenAI")
        if self.provider != "azure_openai" and self.deployment_name:
            raise ValueError("deployment_name is only valid for Azure OpenAI")
        return self


class ModelConnectionTestError(BaseModel):
    code: str
    message: str


class ModelConnectionTestResponse(BaseModel):
    status: Literal["SUCCESS", "FAILED"]
    provider: str
    model_name: str
    latency_ms: int | None = None
    error: ModelConnectionTestError | None = None
