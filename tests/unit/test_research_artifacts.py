"""Deterministic research trajectory and citation provenance fixtures."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from apps.api.app.artifacts.service import INLINE_ARTIFACT_LIMIT, ArtifactService
from apps.api.app.config import Settings
from apps.api.app.models import Artifact
from apps.api.app.runtime.planning import PlanProposal, ProposedTask
from apps.api.app.runtime.research_citations import (
    has_unresolved_citation_marker,
    render_cited_report,
    source_catalog,
    validate_research_citations,
)

FIXTURE = (
    Path(__file__).parents[1] / "fixtures" / "research" / "cloud_run_vs_fargate.json"
)


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_research_fixture_plans_follow_up_and_cites_inspected_sources() -> None:
    fixture = _fixture()
    initial_tasks = tuple(
        ProposedTask.model_validate(item) for item in fixture["initial_tasks"]
    )
    proposal = PlanProposal(tasks=initial_tasks)
    follow_up = ProposedTask.model_validate(fixture["follow_up_task"])
    assert follow_up.dependencies == ("compare",)
    assert "cost" in str(fixture["gap"]).lower()

    artifacts = [
        Artifact(
            id=source["id"],
            workspace_id="20000000-0000-4000-8000-000000000001",
            run_id="30000000-0000-4000-8000-000000000001",
            artifact_type="SOURCE_DOCUMENT",
            mime_type="text/plain; charset=utf-8",
            title=source["title"],
            inline_data=source["content"],
            blob_key=None,
            content_hash="0" * 64,
            producer_key=f"fixture:{source['id']}",
            metadata_json={
                "source_url": source["url"],
                "inspected_excerpt": source["inspected_excerpt"],
            },
        )
        for source in fixture["sources"]
    ]
    catalog = source_catalog(artifacts)
    proposed_citations = [
        {"source_id": "S1", "excerpt": fixture["sources"][0]["inspected_excerpt"]},
        {"source_id": "S2", "excerpt": fixture["sources"][1]["inspected_excerpt"]},
    ]
    stored = {str(item.id): item.inline_data for item in artifacts}
    citations, gaps = validate_research_citations(
        proposed_citations,
        catalog,
        stored,  # type: ignore[arg-type]
    )
    rendered = render_cited_report(
        str(fixture["report"]), citations, [str(fixture["gap"])]
    )

    assert [task.key for task in proposal.tasks] == ["cloud_run", "fargate", "compare"]
    assert [citation["marker"] for citation in citations] == ["S1", "S2"]
    assert gaps == []
    assert "## Sources" in rendered
    assert "[S1] Cloud Run autoscaling documentation" in rendered
    assert "## Gaps" in rendered
    assert not has_unresolved_citation_marker(str(fixture["report"]), citations)


def test_research_fixture_defines_offline_failure_and_recovery_cases() -> None:
    fixture = _fixture()
    scenarios = fixture["failure_scenarios"]

    assert set(scenarios) == {
        "inaccessible_source",
        "conflicting_sources",
        "invalid_citation",
        "timeout",
        "worker_restart",
        "partial_report",
    }
    assert scenarios["worker_restart"]["checkpoint"] == "TASK_READY"
    assert scenarios["inaccessible_source"]["expected"] == "continue_with_gap"

    fixture_sources = fixture["sources"]
    artifacts = [
        Artifact(
            id=source["id"],
            workspace_id="20000000-0000-4000-8000-000000000001",
            run_id="30000000-0000-4000-8000-000000000001",
            artifact_type="SOURCE_DOCUMENT",
            mime_type="text/plain",
            title=source["title"],
            inline_data=source["content"],
            blob_key=None,
            content_hash="0" * 64,
            producer_key=f"fixture:{source['id']}",
            metadata_json={
                "source_url": source["url"],
                "inspected_excerpt": source["inspected_excerpt"],
            },
        )
        for source in fixture_sources
    ]
    catalog = source_catalog(artifacts)
    invalid, gaps = validate_research_citations(
        [{"source_id": "S99", "excerpt": "Unsupported claim."}],
        catalog,
        {str(item.id): item.inline_data or "" for item in artifacts},
    )

    assert invalid == []
    assert gaps


def test_citation_requires_exact_inspected_excerpt_and_same_stored_source() -> None:
    fixture = _fixture()
    source = fixture["sources"][0]
    artifact = Artifact(
        id=source["id"],
        workspace_id="20000000-0000-4000-8000-000000000001",
        run_id="30000000-0000-4000-8000-000000000001",
        artifact_type="SOURCE_DOCUMENT",
        mime_type="text/plain",
        title=source["title"],
        inline_data=source["content"],
        blob_key=None,
        content_hash="0" * 64,
        producer_key="fixture:source",
        metadata_json={
            "source_url": source["url"],
            "inspected_excerpt": source["inspected_excerpt"],
        },
    )
    catalog = source_catalog([artifact])

    citations, gaps = validate_research_citations(
        [{"source_id": "S1", "excerpt": "This sentence was never inspected."}],
        catalog,
        {str(artifact.id): artifact.inline_data or ""},
    )

    assert citations == []
    assert gaps


@pytest.mark.parametrize("proposed", [None, {}, ["not an object"]])
def test_invalid_citation_payload_is_rejected_without_fabricating_sources(
    proposed: object,
) -> None:
    citations, gaps = validate_research_citations(proposed, [])
    assert citations == []
    assert gaps


@pytest.mark.asyncio
async def test_artifact_service_keeps_small_content_inline() -> None:
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None), add=Mock(), flush=AsyncMock()
    )
    service = ArtifactService(session, Settings(), blob_store=Mock())
    run = SimpleNamespace(id=uuid4(), workspace_id=uuid4())

    artifact = await service.create(
        run,  # type: ignore[arg-type]
        artifact_type="SOURCE_DOCUMENT",
        mime_type="text/plain",
        title="Primary source",
        content="verified excerpt",
        producer_key="fetch:call-1",
    )

    assert artifact.inline_data == "verified excerpt"
    assert artifact.blob_key is None
    session.add.assert_called_once_with(artifact)


@pytest.mark.asyncio
async def test_artifact_service_uses_private_blob_for_large_content() -> None:
    content = "x" * (INLINE_ARTIFACT_LIMIT + 1)

    class MemoryBlobStore:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        async def put(self, key: str, data: bytes) -> str:
            self.objects[key] = data
            return f"private://{key}"

        async def get(self, uri: str) -> bytes:
            return self.objects[uri.removeprefix("private://")]

        async def delete(self, _uri: str) -> None:
            return None

    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None), add=Mock(), flush=AsyncMock()
    )
    blobs = MemoryBlobStore()
    service = ArtifactService(
        session,
        Settings(),
        blob_store=blobs,  # type: ignore[arg-type]
    )
    run = SimpleNamespace(id=uuid4(), workspace_id=uuid4())

    artifact = await service.create(
        run,  # type: ignore[arg-type]
        artifact_type="SOURCE_DOCUMENT",
        mime_type="text/plain",
        title="Large source",
        content=content,
        producer_key="fetch:call-2",
    )

    assert artifact.inline_data is None
    assert artifact.blob_key is not None
    assert await service.read_all(artifact) == content.encode()


@pytest.mark.asyncio
async def test_artifact_range_reads_are_recorded_as_inspected_evidence() -> None:
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None), add=Mock(), flush=AsyncMock()
    )
    service = ArtifactService(session, Settings(), blob_store=Mock())
    artifact = Artifact(
        id=uuid4(),
        workspace_id=uuid4(),
        run_id=uuid4(),
        artifact_type="SOURCE_DOCUMENT",
        mime_type="text/plain",
        title="Source",
        inline_data="prefix text and later verified evidence",
        blob_key=None,
        content_hash="0" * 64,
        producer_key="source:range",
        metadata_json={
            "source_url": "https://example.test/source",
            "inspected_excerpt": "prefix text",
            "inspected_ranges": [{"start": 0, "end": 11, "text": "prefix text"}],
        },
    )

    result = await service.read_text_range(artifact, offset=22, limit=19)
    service.record_inspected_range(
        artifact, offset=result["offset"], text=result["content"]
    )
    catalog = source_catalog([artifact])
    citations, gaps = validate_research_citations(
        [{"source_id": "S1", "excerpt": result["content"]}],
        catalog,
        {str(artifact.id): artifact.inline_data or ""},
    )

    assert result["content"] == "verified evidence"
    assert result["has_more"] is False
    assert citations[0]["artifact_id"] == str(artifact.id)
    assert gaps == []
