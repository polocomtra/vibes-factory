from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from apps.api.app.knowledge.embedding import FakeEmbeddingProvider
from apps.api.app.knowledge.parsing import (
    DocumentParseError,
    chunk_segments,
    parse_document,
)
from apps.api.app.knowledge.schemas import RetrievalFilters
from apps.api.worker import finish_stale_ingestion


def test_utf8_markdown_preserves_heading_provenance_and_chunks() -> None:
    segments = parse_document(
        "guide.md",
        "text/markdown",
        b"# Setup\n\nInstall the agent.\n\n# Run\n\nStart it.",
    )
    assert segments[0].section == "Setup"
    chunks = chunk_segments(segments, target_tokens=2, overlap=1)
    assert chunks
    assert chunks[0].section == "Setup"


def test_scanned_pdf_returns_recovery_error() -> None:
    with pytest.raises(DocumentParseError, match="signature"):
        parse_document("scan.pdf", "application/pdf", b"not a pdf")


@pytest.mark.asyncio
async def test_fake_embedding_is_normalized_and_dimensioned() -> None:
    response = await FakeEmbeddingProvider().embed(["xin chào"], "query")
    assert response.dimensions == 384
    assert len(response.embeddings[0]) == 384
    assert sum(value * value for value in response.embeddings[0]) == pytest.approx(
        1, abs=1e-5
    )


def test_retrieval_filter_limits_document_ids_and_metadata() -> None:
    document_id = uuid4()
    filters = RetrievalFilters(document_ids=[document_id], metadata={"language": "vi"})
    assert filters.document_ids == [document_id]


@pytest.mark.asyncio
async def test_stale_ingestion_job_is_completed_without_overwriting_document() -> None:
    job_id = uuid4()
    job = SimpleNamespace(id=job_id)
    stored_job = SimpleNamespace(
        id=job_id,
        resource_id=uuid4(),
        generation=1,
        status=None,
        result=None,
        error={"code": "old"},
        lease_owner="worker",
        lease_expires_at="lease",
    )
    session = SimpleNamespace(
        get=AsyncMock(return_value=stored_job),
        commit=AsyncMock(),
    )

    await finish_stale_ingestion(session, job)

    assert stored_job.status.value == "COMPLETED"
    assert stored_job.result == {"skipped": "stale_generation"}
    assert stored_job.error is None
    assert stored_job.lease_owner is None
    assert stored_job.lease_expires_at is None
    session.commit.assert_awaited_once()
