"""HTTP-only embedding boundary with readiness after a real model warm-up."""

import asyncio
import hashlib
import logging
import math
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path
from time import monotonic
from typing import Literal

import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from huggingface_hub import snapshot_download
from pydantic import BaseModel, Field
from transformers import AutoTokenizer

MODEL_ID = os.getenv("VF_EMBEDDING_MODEL", "intfloat/multilingual-e5-small")
MODEL_REVISION = os.getenv(
    "VF_EMBEDDING_REVISION", "614241f622f53c4eeff9890bdc4f31cfecc418b3"
)
MODEL_PATH = os.getenv(
    "VF_EMBEDDING_MODEL_PATH", "/opt/huggingface/models/intfloat/multilingual-e5-small"
)
ORT_PROVIDER = os.getenv("VF_EMBEDDING_ORT_PROVIDER", "CPUExecutionProvider")
MAX_TOKENS = 512
DIMENSIONS = 384
logger = logging.getLogger("vibesfactory.embedding")
_inference_lock = asyncio.Lock()
_model_ready = False


class EmbeddingRequest(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=32)
    input_type: Literal["query", "passage"]


class EmbeddingResponse(BaseModel):
    model: str
    revision: str
    dimensions: int
    token_counts: list[int]
    embeddings: list[list[float]]


class OnnxEmbedder:
    """Small ONNX-only model wrapper; it deliberately does not import torch."""

    def __init__(self, model_dir: Path) -> None:
        onnx_dir = model_dir / "onnx"
        tokenizer_dir = onnx_dir if onnx_dir.is_dir() else model_dir
        model_path = onnx_dir / "model.onnx"
        if not model_path.is_file():
            raise FileNotFoundError(f"ONNX model not found at {model_path}")
        self.tokenizer = AutoTokenizer.from_pretrained(
            tokenizer_dir,
            local_files_only=True,
        )
        self.session = ort.InferenceSession(
            str(model_path),
            providers=[ORT_PROVIDER],
        )

    def encode(self, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
        encoded = self.tokenizer(
            texts,
            padding=True,
            truncation=True,
            max_length=MAX_TOKENS,
            return_tensors="np",
        )
        model_inputs: dict[str, np.ndarray] = {}
        for input_def in self.session.get_inputs():
            if input_def.name in encoded:
                model_inputs[input_def.name] = encoded[input_def.name]
            elif input_def.name == "token_type_ids":
                model_inputs[input_def.name] = np.zeros_like(encoded["input_ids"])
            else:
                raise ValueError(f"Unsupported ONNX input: {input_def.name}")
        outputs = self.session.run(None, model_inputs)
        if not outputs or outputs[0].ndim != 3:
            raise ValueError("The ONNX model returned an invalid hidden-state shape")
        return outputs[0], encoded["attention_mask"]


@lru_cache(maxsize=1)
def _load_model() -> OnnxEmbedder:
    if os.path.isdir(MODEL_PATH):
        model_dir = Path(MODEL_PATH)
    else:
        model_dir = Path(
            snapshot_download(
                MODEL_ID,
                revision=MODEL_REVISION,
                local_files_only=True,
            )
        )
    return OnnxEmbedder(model_dir)


def _embed(request: EmbeddingRequest) -> EmbeddingResponse:
    texts = [f"{request.input_type}: {text}" for text in request.texts]
    try:
        model = _load_model()
        hidden_states, attention_mask = model.encode(texts)
        mask = attention_mask.astype(np.float32)[..., None]
        vectors = (hidden_states * mask).sum(axis=1) / np.clip(
            mask.sum(axis=1), 1e-9, None
        )
        vectors = vectors / np.clip(
            np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12, None
        )
        embeddings = [[float(value) for value in row] for row in vectors]
        counts = [min(MAX_TOKENS, len(text.split())) for text in request.texts]
    except Exception as exc:
        if os.getenv("VF_EMBEDDING_ALLOW_FAKE", "false").lower() != "true":
            raise HTTPException(
                503,
                detail={
                    "code": "EMBEDDING_UNAVAILABLE",
                    "message": "The embedding model is not ready.",
                },
            ) from exc
        embeddings = []
        counts = []
        for text in texts:
            seed = hashlib.sha256(text.encode()).digest()
            vector = [
                ((seed[index % len(seed)] / 255) * 2) - 1 for index in range(DIMENSIONS)
            ]
            norm = math.sqrt(sum(value * value for value in vector)) or 1
            embeddings.append([value / norm for value in vector])
            counts.append(min(MAX_TOKENS, len(text.split())))
    if any(len(row) != DIMENSIONS for row in embeddings):
        raise HTTPException(
            503,
            detail={
                "code": "EMBEDDING_UNAVAILABLE",
                "message": "The embedding model returned an invalid dimension.",
            },
        )
    return EmbeddingResponse(
        model=MODEL_ID,
        revision=MODEL_REVISION,
        dimensions=DIMENSIONS,
        token_counts=counts,
        embeddings=embeddings,
    )


def _warm_model() -> None:
    _embed(EmbeddingRequest(texts=["embedding service warmup"], input_type="passage"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    global _model_ready
    started = monotonic()
    try:
        await run_in_threadpool(_warm_model)
        _model_ready = True
        logger.info(
            "embedding_model_ready provider=%s duration_ms=%s",
            ORT_PROVIDER,
            int((monotonic() - started) * 1000),
        )
    except Exception:
        logger.exception(
            "embedding_model_not_ready provider=%s duration_ms=%s",
            ORT_PROVIDER,
            int((monotonic() - started) * 1000),
        )
    yield


app = FastAPI(
    title="VibesFactory Embedding Service", version="0.1.0", lifespan=lifespan
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "vibesfactory-embedding"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    if not _model_ready:
        raise HTTPException(
            503,
            detail={
                "code": "EMBEDDING_UNAVAILABLE",
                "message": "The embedding model inference is not ready.",
            },
        )
    return {"status": "ready", "provider": ORT_PROVIDER}


@app.post("/internal/v1/embeddings", response_model=EmbeddingResponse)
async def embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    started = monotonic()
    logger.info(
        "embedding_request_started batch_size=%s input_type=%s",
        len(request.texts),
        request.input_type,
    )
    try:
        # Keep CPU-bound ONNX inference off the event loop and serialize it so
        # concurrent ingestion workers do not oversubscribe local CPU memory.
        async with _inference_lock:
            response = await run_in_threadpool(_embed, request)
    except HTTPException as exc:
        logger.error(
            "embedding_request_failed status_code=%s batch_size=%s duration_ms=%s detail=%s",
            exc.status_code,
            len(request.texts),
            int((monotonic() - started) * 1000),
            str(exc.detail)[:500],
        )
        raise
    logger.info(
        "embedding_request_completed batch_size=%s duration_ms=%s",
        len(request.texts),
        int((monotonic() - started) * 1000),
    )
    return response
