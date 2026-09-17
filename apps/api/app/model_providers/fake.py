"""Deterministic provider for unit tests and local contract checks."""

from collections.abc import AsyncIterator, Callable

from .contracts import ModelRequest, ModelResponse, ModelStreamEvent
from .errors import ProviderError


class FakeModelProvider:
    """A no-network provider that exercises the same platform contract."""

    provider_id = "fake"

    def __init__(
        self,
        response_factory: Callable[[ModelRequest], ModelResponse] | None = None,
        stream_chunk_size: int = 4,
    ) -> None:
        self.response_factory = response_factory
        self.stream_chunk_size = max(1, stream_chunk_size)
        self.requests: list[ModelRequest] = []
        self.stream_requests: list[ModelRequest] = []

    async def generate(self, request: ModelRequest, api_key: str) -> ModelResponse:
        del api_key
        self.requests.append(request)
        if self.response_factory:
            return self.response_factory(request)
        return ModelResponse(
            content="OK",
            finish_reason="STOP",
            provider_metadata={"model": request.model},
        )

    async def stream(
        self, request: ModelRequest, api_key: str
    ) -> AsyncIterator[ModelStreamEvent]:
        del api_key
        if not request.stream:
            raise ProviderError(
                "MODEL_REQUEST_INVALID",
                "A streaming provider request must set stream=true.",
            )
        self.stream_requests.append(request)
        response = (
            self.response_factory(request)
            if self.response_factory
            else ModelResponse(
                content="OK",
                finish_reason="STOP",
                provider_metadata={"model": request.model},
            )
        )
        for start in range(0, len(response.content), self.stream_chunk_size):
            yield ModelStreamEvent(
                type="text_delta",
                text=response.content[start : start + self.stream_chunk_size],
            )
        yield ModelStreamEvent(type="completed", response=response)
