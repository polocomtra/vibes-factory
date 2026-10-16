"""Workspace-scoped persistence for run artifacts and provenance links."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..knowledge.storage import BlobStore, blob_store_for_settings
from ..models import AgentPlan, AgentPlanTask, Artifact, ArtifactReference, Run

INLINE_ARTIFACT_LIMIT = 64 * 1024
ARTIFACT_READ_LIMIT = 64 * 1024
ARTIFACT_MODEL_READ_LIMIT = 12_000


@dataclass(frozen=True, slots=True)
class ArtifactContent:
    artifact: Artifact
    content: bytes


class ArtifactService:
    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        blob_store: BlobStore | None = None,
    ) -> None:
        self.session = session
        self.blob_store = blob_store or blob_store_for_settings(settings)

    async def create(
        self,
        run: Run,
        *,
        artifact_type: str,
        mime_type: str,
        title: str,
        content: str | bytes,
        producer_key: str,
        task_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Artifact:
        if not producer_key or len(producer_key) > 255:
            raise ValueError("Artifact producer key is invalid")
        if task_id is not None:
            task = await self.session.scalar(
                select(AgentPlanTask).where(
                    AgentPlanTask.id == task_id,
                    AgentPlanTask.workspace_id == run.workspace_id,
                    AgentPlanTask.plan_id.in_(
                        select(AgentPlan.id).where(
                            AgentPlan.run_id == run.id,
                            AgentPlan.workspace_id == run.workspace_id,
                        )
                    ),
                )
            )
            if task is None:
                raise ValueError("Artifact task must belong to the same run")

        data = content.encode("utf-8") if isinstance(content, str) else content
        content_hash = hashlib.sha256(data).hexdigest()

        existing = await self.session.scalar(
            select(Artifact).where(
                Artifact.run_id == run.id,
                Artifact.workspace_id == run.workspace_id,
                Artifact.producer_key == producer_key,
            )
        )
        if existing is not None:
            if (
                existing.content_hash != content_hash
                or existing.artifact_type != artifact_type
                or existing.mime_type != mime_type
            ):
                raise ValueError("Artifact producer key was reused for new content")
            return existing

        inline_data: str | None = None
        blob_uri: str | None = None
        if len(data) <= INLINE_ARTIFACT_LIMIT:
            inline_data = data.decode("utf-8")
        else:
            # Deterministic keys make retries after an upload-before-commit safe.
            blob_uri = await self.blob_store.put(
                f"runs/{run.id}/artifacts/{content_hash}", data
            )
        artifact = Artifact(
            id=uuid4(),
            workspace_id=run.workspace_id,
            run_id=run.id,
            task_id=task_id,
            artifact_type=artifact_type,
            mime_type=mime_type,
            title=title[:512],
            inline_data=inline_data,
            blob_key=blob_uri,
            content_hash=content_hash,
            producer_key=producer_key,
            metadata_json=metadata or {},
        )
        self.session.add(artifact)
        await self.session.flush()
        return artifact

    async def reference(
        self,
        run: Run,
        source: Artifact,
        target: Artifact,
        *,
        relation: str,
    ) -> ArtifactReference:
        if (
            source.workspace_id != run.workspace_id
            or target.workspace_id != run.workspace_id
            or source.run_id != run.id
            or target.run_id != run.id
            or source.id == target.id
        ):
            raise ValueError("Artifact references must stay within the same run")
        existing = await self.session.scalar(
            select(ArtifactReference).where(
                ArtifactReference.source_artifact_id == source.id,
                ArtifactReference.target_artifact_id == target.id,
                ArtifactReference.relation == relation,
                ArtifactReference.workspace_id == run.workspace_id,
            )
        )
        if existing is not None:
            return existing
        reference = ArtifactReference(
            id=uuid4(),
            workspace_id=run.workspace_id,
            source_artifact_id=source.id,
            target_artifact_id=target.id,
            relation=relation,
        )
        self.session.add(reference)
        await self.session.flush()
        return reference

    async def read(self, artifact: Artifact, *, offset: int, limit: int) -> bytes:
        if offset < 0 or not 1 <= limit <= ARTIFACT_READ_LIMIT:
            raise ValueError("Artifact range is invalid")
        full = (
            artifact.inline_data.encode("utf-8")
            if artifact.inline_data is not None
            else await self.blob_store.get(artifact.blob_key or "")
        )
        return full[offset : offset + limit]

    async def read_all(self, artifact: Artifact) -> bytes:
        if artifact.inline_data is not None:
            return artifact.inline_data.encode("utf-8")
        return await self.blob_store.get(artifact.blob_key or "")

    async def read_text_range(
        self, artifact: Artifact, *, offset: int, limit: int = 4_000
    ) -> dict[str, Any]:
        if offset < 0 or not 1 <= limit <= ARTIFACT_MODEL_READ_LIMIT:
            raise ValueError("Artifact range is invalid")
        content = (await self.read_all(artifact)).decode("utf-8")
        chunk = content[offset : offset + limit]
        next_offset = offset + len(chunk)
        return {
            "artifact_id": str(artifact.id),
            "title": artifact.title,
            "offset": offset,
            "next_offset": next_offset if next_offset < len(content) else None,
            "has_more": next_offset < len(content),
            "content": chunk,
        }

    @staticmethod
    def record_inspected_range(artifact: Artifact, *, offset: int, text: str) -> None:
        """Record the exact source range returned to the model, bounded per source."""
        metadata = dict(artifact.metadata_json)
        current = metadata.get("inspected_ranges", [])
        ranges = [item for item in current if isinstance(item, dict)]
        if not any(
            item.get("start") == offset and item.get("text") == text for item in ranges
        ):
            ranges.append({"start": offset, "end": offset + len(text), "text": text})
        metadata["inspected_ranges"] = ranges[-12:]
        artifact.metadata_json = metadata
