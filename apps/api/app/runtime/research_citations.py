"""Validation and rendering for citations backed by inspected source artifacts."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from ..models import Artifact

_MARKER = re.compile(r"\[(S\d+)\]")


def source_catalog(artifacts: list[Artifact]) -> list[dict[str, Any]]:
    """Build a bounded model-visible catalog from source excerpts actually read."""
    catalog: list[dict[str, Any]] = []
    for artifact in artifacts:
        if artifact.artifact_type != "SOURCE_DOCUMENT":
            continue
        raw_ranges = artifact.metadata_json.get("inspected_ranges")
        ranges = (
            [item for item in raw_ranges if isinstance(item, dict)]
            if isinstance(raw_ranges, list)
            else []
        )
        if not ranges:
            inspected = artifact.metadata_json.get("inspected_excerpt")
            if isinstance(inspected, str) and inspected.strip():
                ranges = [{"start": 0, "text": inspected}]
        source_url = artifact.metadata_json.get("source_url")
        if not ranges:
            continue
        ordered_ranges = sorted(
            ranges,
            key=lambda item: (
                int(item.get("start", 0))
                if isinstance(item.get("start", 0), int)
                else 0
            ),
        )
        prefix = next(
            (item for item in ordered_ranges if item.get("start", 0) == 0), None
        )
        selected: list[dict[str, Any]] = []
        remaining = 1_500
        if prefix is not None and isinstance(prefix.get("text"), str):
            prefix_text = prefix["text"][: min(750, remaining)]
            if prefix_text:
                selected.append({"start": 0, "text": prefix_text})
                remaining -= len(prefix_text)
        for item in reversed(ordered_ranges):
            if remaining <= 0:
                break
            if item is prefix or not isinstance(item.get("text"), str):
                continue
            excerpt = item["text"][:remaining]
            if excerpt:
                selected.append({"start": item.get("start", 0), "text": excerpt})
                remaining -= len(excerpt)
        if remaining and prefix is not None and isinstance(prefix.get("text"), str):
            already = len(selected[0]["text"]) if selected else 0
            extra = prefix["text"][already : already + remaining]
            if extra:
                if selected and selected[0].get("start") == 0:
                    selected[0]["text"] += extra
                else:
                    selected.append({"start": 0, "text": extra})
        inspected = "\n".join(str(item["text"]) for item in selected)
        catalog.append(
            {
                "source_id": f"S{len(catalog) + 1}",
                "artifact_id": str(artifact.id),
                "title": artifact.title,
                "url": str(source_url or ""),
                # Keep the synthesis source catalog bounded and validate against
                # exactly the prefix the model received.
                "inspected_excerpt": inspected[:1_500],
                "inspected_ranges": selected,
            }
        )
    return catalog


def validate_research_citations(
    proposed: object,
    catalog: list[dict[str, Any]],
    stored_content: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Keep only source IDs and excerpts that match text shown to the model."""
    if not isinstance(proposed, list):
        return [], ["The report did not include a valid citation list."]
    by_id = {item["source_id"]: item for item in catalog}
    valid: list[dict[str, Any]] = []
    gaps: list[str] = []
    seen: set[str] = set()
    for item in proposed:
        if not isinstance(item, dict):
            gaps.append("A malformed citation was omitted.")
            continue
        source_id = item.get("source_id")
        excerpt = item.get("excerpt")
        source = by_id.get(source_id) if isinstance(source_id, str) else None
        if not isinstance(source_id, str):
            gaps.append("A citation with an invalid source ID was omitted.")
            continue
        inspected_ranges = source.get("inspected_ranges", []) if source else []
        was_inspected = (
            excerpt in source["inspected_excerpt"]
            if source is not None and isinstance(excerpt, str)
            else False
        )
        if source is not None and isinstance(excerpt, str):
            was_inspected = any(
                isinstance(source_range, dict)
                and isinstance(source_range.get("text"), str)
                and excerpt in source_range["text"]
                for source_range in inspected_ranges
            )
        if (
            source is None
            or not isinstance(excerpt, str)
            or not excerpt.strip()
            or len(excerpt) > 500
            or not was_inspected
            or excerpt not in (stored_content or {}).get(source["artifact_id"], "")
        ):
            gaps.append(
                "A citation that did not match inspected source text was omitted."
            )
            continue
        if source_id in seen:
            continue
        seen.add(source_id)
        try:
            artifact_id = UUID(source["artifact_id"])
        except ValueError:
            gaps.append("A citation with an invalid source reference was omitted.")
            continue
        valid.append(
            {
                "marker": source_id,
                "artifact_id": str(artifact_id),
                "source_name": source["title"],
                "source_url": source["url"],
                "excerpt": excerpt,
                "chunk_id": None,
                "document_id": None,
                "knowledge_base_id": None,
                "page": None,
                "section": None,
                "score": None,
                "generation": None,
            }
        )
    return valid, gaps


def render_cited_report(
    report: str, citations: list[dict[str, Any]], gaps: list[str]
) -> str:
    """Append a readable source list and prevent dangling generated markers."""
    valid_markers = {str(item["marker"]) for item in citations}
    rendered = _MARKER.sub(
        lambda match: match.group(0) if match.group(1) in valid_markers else "",
        report,
    ).strip()
    if citations:
        rendered += "\n\n## Sources\n"
        rendered += "\n".join(
            "- ["
            + str(item["marker"])
            + "] "
            + _escape_markdown(str(item["source_name"]))
            + " — "
            + _escape_markdown(str(item["source_url"]))
            for item in citations
        )
    if gaps:
        rendered += "\n\n## Gaps\n" + "\n".join(
            f"- {gap}" for gap in dict.fromkeys(gaps)
        )
    return rendered


def _escape_markdown(value: str) -> str:
    flattened = re.sub(r"[\r\n]+", " ", value)
    return re.sub(r"([\\`*_{}\[\]<>()#+.!|])", r"\\\1", flattened)


def has_unresolved_citation_marker(
    report: str, citations: list[dict[str, Any]]
) -> bool:
    valid_markers = {str(item["marker"]) for item in citations}
    return any(
        match.group(1) not in valid_markers for match in _MARKER.finditer(report)
    )
