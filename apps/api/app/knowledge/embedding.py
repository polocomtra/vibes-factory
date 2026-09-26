"""HTTP embedding provider contract; the API never loads model weights."""

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any, Literal

import httpx
import structlog

from ..config import Settings


class EmbeddingUnavailable(Exception):
    """The internal embedding service could not fulfil a request."""


logger = structlog.get_logger(__name__)


def _fetch_cloud_run_identity_token(audience: str) -> str:
    """Fetch an ID token from the Cloud Run service identity metadata server."""

    from google.auth.transport.requests import Request
    from google.oauth2.id_token import fetch_id_token

    return fetch_id_token(Request(), audience)


@dataclass(frozen=True)
class EmbeddingResponse:
    model: str
    revision: str
    dimensions: int
    token_counts: list[int]
    embeddings: list[list[float]]


class EmbeddingProvider:
    async def embed(
        self, texts: list[str], input_type: Literal["query", "passage"]
    ) -> EmbeddingResponse:
        raise NotImplementedError


class HttpEmbeddingProvider(EmbeddingProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def embed(
        self, texts: list[str], input_type: Literal["query", "passage"]
    ) -> EmbeddingResponse:
        if not texts or len(texts) > 32:
            raise EmbeddingUnavailable("Embedding batch must contain 1 to 32 texts.")
        started = monotonic()
        fields = {
            "service_url": self._settings.embedding_service_url,
            "batch_size": len(texts),
            "input_type": input_type,
        }
        logger.info("embedding_request_started", **fields)
        try:
            headers = None
            if self._settings.embedding_service_audience:
                token = await asyncio.to_thread(
                    _fetch_cloud_run_identity_token,
                    self._settings.embedding_service_audience,
                )
                headers = {"Authorization": f"Bearer {token}"}
            async with httpx.AsyncClient(
                base_url=self._settings.embedding_service_url,
                timeout=httpx.Timeout(
                    self._settings.embedding_timeout_seconds, connect=5.0
                ),
            ) as client:
                response = await client.post(
                    "/internal/v1/embeddings",
                    json={"texts": texts, "input_type": input_type},
                    headers=headers,
                )
                response.raise_for_status()
                payload: dict[str, Any] = response.json()
        except Exception as exc:
            status_code = (
                exc.response.status_code
                if isinstance(exc, httpx.HTTPStatusError)
                else None
            )
            logger.warning(
                "embedding_request_failed",
                **fields,
                error_type=type(exc).__name__,
                error_detail=str(exc)[:500] or type(exc).__name__,
                status_code=status_code,
                duration_ms=max(0, int((monotonic() - started) * 1000)),
            )
            raise EmbeddingUnavailable("The embedding service is unavailable.") from exc
        if payload.get("dimensions") != 384 or len(
            payload.get("embeddings", [])
        ) != len(texts):
            logger.warning(
                "embedding_response_invalid",
                **fields,
                response_dimensions=payload.get("dimensions"),
                response_batch_size=len(payload.get("embeddings", [])),
                duration_ms=max(0, int((monotonic() - started) * 1000)),
            )
            raise EmbeddingUnavailable(
                "The embedding service returned an invalid vector shape."
            )
        logger.info(
            "embedding_request_completed",
            **fields,
            dimensions=payload["dimensions"],
            duration_ms=max(0, int((monotonic() - started) * 1000)),
        )
        return EmbeddingResponse(
            model=str(payload["model"]),
            revision=str(payload["revision"]),
            dimensions=int(payload["dimensions"]),
            token_counts=[int(value) for value in payload["token_counts"]],
            embeddings=[
                [float(value) for value in row] for row in payload["embeddings"]
            ],
        )


class FakeEmbeddingProvider(EmbeddingProvider):
    """Deterministic provider used by unit and API tests."""

    def __init__(self, dimensions: int = 384) -> None:
        self.dimensions = dimensions

    async def embed(
        self, texts: list[str], input_type: Literal["query", "passage"]
    ) -> EmbeddingResponse:
        import hashlib
        import math

        vectors: list[list[float]] = []
        for text in texts:
            seed = hashlib.sha256(f"{input_type}:{text}".encode()).digest()
            vector = [
                ((seed[index % len(seed)] / 255) * 2) - 1
                for index in range(self.dimensions)
            ]
            norm = math.sqrt(sum(value * value for value in vector)) or 1
            vectors.append([value / norm for value in vector])
        return EmbeddingResponse(
            model="fake/multilingual-e5-small",
            revision="test",
            dimensions=self.dimensions,
            token_counts=[len(text.split()) for text in texts],
            embeddings=vectors,
        )
