"""Stable, safe errors exposed by provider adapters."""

from typing import Final

PROVIDER_ERROR_CODES: Final[frozenset[str]] = frozenset(
    {
        "PROVIDER_CREDENTIAL_MISSING",
        "PROVIDER_AUTHENTICATION_FAILED",
        "PROVIDER_RATE_LIMITED",
        "PROVIDER_TIMEOUT",
        "PROVIDER_BAD_REQUEST",
        "PROVIDER_INVALID_RESPONSE",
        "PROVIDER_UNAVAILABLE",
        "MODEL_NOT_FOUND",
        "MODEL_CAPABILITY_UNSUPPORTED",
        "MODEL_REQUEST_INVALID",
    }
)


class ProviderError(Exception):
    """An adapter error with a stable code and no vendor exception text."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message
        self.retryable = retryable
        self.status_code = status_code
        self.request_id = request_id


def normalize_sdk_exception(error: Exception) -> ProviderError:
    """Map OpenAI/httpx exceptions without copying their potentially secret text."""

    name = type(error).__name__.lower()
    status_code = getattr(error, "status_code", None)
    request_id = getattr(error, "request_id", None)
    if "authentication" in name or "permission" in name:
        return ProviderError(
            "PROVIDER_AUTHENTICATION_FAILED",
            "The provider credentials were rejected.",
            status_code=status_code,
            request_id=request_id,
        )
    if "ratelimit" in name or status_code == 429:
        return ProviderError(
            "PROVIDER_RATE_LIMITED",
            "The provider rate limit was reached.",
            retryable=True,
            status_code=status_code,
            request_id=request_id,
        )
    if "timeout" in name:
        return ProviderError(
            "PROVIDER_TIMEOUT",
            "The provider request timed out.",
            retryable=True,
            status_code=status_code,
            request_id=request_id,
        )
    if "badrequest" in name or status_code in (400, 422):
        return ProviderError(
            "PROVIDER_BAD_REQUEST",
            "The provider rejected the request.",
            status_code=status_code,
            request_id=request_id,
        )
    if status_code is not None and status_code == 404:
        return ProviderError(
            "MODEL_NOT_FOUND",
            "The requested model was not found.",
            status_code=status_code,
            request_id=request_id,
        )
    if status_code is not None and status_code >= 500:
        return ProviderError(
            "PROVIDER_UNAVAILABLE",
            "The provider is temporarily unavailable.",
            retryable=True,
            status_code=status_code,
            request_id=request_id,
        )
    if "connection" in name or "connect" in name or "network" in name:
        return ProviderError(
            "PROVIDER_UNAVAILABLE",
            "The provider is unavailable.",
            retryable=True,
            request_id=request_id,
        )
    return ProviderError(
        "PROVIDER_INVALID_RESPONSE",
        "The provider returned an invalid response.",
        status_code=status_code,
        request_id=request_id,
    )
