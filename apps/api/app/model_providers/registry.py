"""Provider registry and request validation."""

from urllib.parse import urlparse

from pydantic import SecretStr

from ..config import Settings
from .catalog import find_model
from .contracts import ModelProvider, ModelRequest
from .errors import ProviderError
from .providers.deepseek import DeepSeekProvider
from .providers.gemini import GeminiProvider
from .providers.openai import AzureOpenAIProvider, OpenAIProvider


class ModelProviderRegistry:
    def __init__(
        self,
        *,
        timeout: float = 60.0,
        azure_openai_api_key: SecretStr | None = None,
        azure_openai_base_url: str | None = None,
    ) -> None:
        self.timeout = timeout
        self.azure_openai_api_key = azure_openai_api_key
        self.azure_openai_base_url = azure_openai_base_url

    @classmethod
    def from_settings(cls, settings: Settings) -> "ModelProviderRegistry":
        return cls(
            timeout=settings.model_provider_timeout_seconds,
            azure_openai_api_key=settings.azure_openai_api_key,
            azure_openai_base_url=settings.azure_openai_base_url,
        )

    def resolve(self, provider: str, *, base_url: str | None = None) -> ModelProvider:
        provider = provider.strip().lower()
        if provider == "google":
            return GeminiProvider(base_url=base_url, timeout=self.timeout)
        if provider == "openai":
            return OpenAIProvider(base_url=base_url, timeout=self.timeout)
        if provider == "azure_openai":
            configured_base_url = base_url or self.azure_openai_base_url
            self.validate_azure_base_url(configured_base_url)
            return AzureOpenAIProvider(
                base_url=configured_base_url, timeout=self.timeout
            )
        if provider == "deepseek":
            return DeepSeekProvider(base_url=base_url, timeout=self.timeout)
        raise ProviderError(
            "MODEL_REQUEST_INVALID", "The requested provider is not supported."
        )

    def builtin_api_key(self, provider: str) -> str:
        """Resolve an environment credential without exposing it to API callers."""

        if provider.strip().lower() == "azure_openai" and self.azure_openai_api_key:
            value = self.azure_openai_api_key.get_secret_value()
            if value.strip():
                return value
        raise ProviderError(
            "PROVIDER_CREDENTIAL_MISSING",
            "The configured provider credential is missing.",
        )

    @staticmethod
    def validate_azure_base_url(base_url: str | None) -> None:
        if not base_url:
            raise ProviderError(
                "MODEL_REQUEST_INVALID", "Azure OpenAI base URL is required."
            )
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or not parsed.path.rstrip("/").endswith("/openai/v1")
        ):
            raise ProviderError(
                "MODEL_REQUEST_INVALID",
                "Azure OpenAI base URL must end with /openai/v1.",
            )

    @staticmethod
    def validate_request(request: ModelRequest) -> None:
        if request.stream:
            raise ProviderError(
                "MODEL_CAPABILITY_UNSUPPORTED",
                "Streaming is not supported until Phase 5.",
            )
        definition = find_model(request.provider, request.model)
        if definition is None:
            # Custom models are deliberately accepted by test connection only.
            return
        capabilities = definition.capabilities
        if request.tools and not capabilities.get("tool_calling", False):
            raise ProviderError(
                "MODEL_CAPABILITY_UNSUPPORTED",
                "This model does not support tool calling.",
            )
        if request.response_schema and not capabilities.get("structured_output", False):
            raise ProviderError(
                "MODEL_CAPABILITY_UNSUPPORTED",
                "This model does not support structured output.",
            )
        if (
            definition.max_output_tokens
            and request.max_output_tokens > definition.max_output_tokens
        ):
            raise ProviderError(
                "MODEL_REQUEST_INVALID",
                "The requested output token limit is too high for this model.",
            )
