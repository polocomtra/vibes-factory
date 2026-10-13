"""Sanitize model and provider data before traces or persistence."""

from ..model_providers.contracts import ModelRequest
from ..model_providers.errors import ProviderError

_SECRET_METADATA_KEYS = frozenset(
    {"api_key", "apikey", "authorization", "credential", "password", "secret", "token"}
)


def _provider_status(error: ProviderError) -> int:
    if error.code == "PROVIDER_TIMEOUT":
        return 504
    if error.code in {"MODEL_REQUEST_INVALID", "MODEL_CAPABILITY_UNSUPPORTED"}:
        return 422
    return 502


def _safe_model_input(model_request: ModelRequest) -> dict[str, object]:
    return {
        "provider": model_request.provider,
        "model": model_request.model,
        "system_instruction": model_request.system_instruction,
        "messages": [message.model_dump() for message in model_request.messages],
        "temperature": model_request.temperature,
        "max_output_tokens": model_request.max_output_tokens,
        "stream": model_request.stream,
        "tools": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            }
            for tool in model_request.tools
        ],
    }


def _safe_provider_metadata(value: object) -> object:
    """Keep useful provider metadata while dropping secret-shaped fields."""

    if isinstance(value, dict):
        return {
            str(key): _safe_provider_metadata(item)
            for key, item in value.items()
            if str(key).lower() not in _SECRET_METADATA_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_safe_provider_metadata(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
