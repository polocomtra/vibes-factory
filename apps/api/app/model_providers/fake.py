"""Deterministic provider for unit tests and local contract checks."""

from collections.abc import Callable

from .contracts import ModelRequest, ModelResponse


class FakeModelProvider:
    """A no-network provider that exercises the same platform contract."""

    provider_id = "fake"

    def __init__(
        self,
        response_factory: Callable[[ModelRequest], ModelResponse] | None = None,
    ) -> None:
        self.response_factory = response_factory
        self.requests: list[ModelRequest] = []

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
