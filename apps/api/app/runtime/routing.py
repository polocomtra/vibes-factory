"""Deterministic runtime routing for optional knowledge retrieval."""

import re

from .contracts import AgentRunRequest

_KNOWLEDGE_REQUEST_MARKERS = (
    "knowledge base",
    "knowledge bases",
    "knowledge",
    "knowledge document",
    "knowledge documents",
    "uploaded file",
    "uploaded files",
    "uploaded document",
    "uploaded documents",
    "attached file",
    "attached files",
    "attached document",
    "attached documents",
    "attached docs",
    "attached knowledge",
    "provided file",
    "provided files",
    "provided document",
    "provided documents",
    "provided docs",
    "uploaded docs",
    "according to the document",
    "according to the documents",
    "according to document",
    "according to the docs",
    "in the document",
    "in the documents",
    "in document",
    "in the docs",
    "in docs",
    "from the document",
    "from the documents",
    "from the docs",
    "based on the document",
    "based on the documents",
    "based on the docs",
    "use the attached",
    "use attached",
    "tài liệu",
    "tài liệu đính kèm",
    "file đính kèm",
    "cơ sở tri thức",
)

_NO_EXTERNAL_SEARCH_MARKERS = (
    "don't use web search",
    "do not use web search",
    "without web search",
    "no web search",
)

_EXTERNAL_RESEARCH_MARKERS = (
    "search the web",
    "web search",
    "on the web",
    "on the internet",
    "internet search",
    "look it up",
    "look up online",
    "latest news",
    "latest information",
    "current news",
    "real time",
    "research",
)


def _normalize_prompt(prompt: str) -> str:
    """Make natural punctuation such as ``knowledge/ documents`` searchable."""

    return " ".join(
        token
        for token in re.split(r"[^\w]+", prompt.casefold(), flags=re.UNICODE)
        if token
    )


def _contains_marker(prompt: str, markers: tuple[str, ...]) -> bool:
    return any(_normalize_prompt(marker) in prompt for marker in markers)


def should_retrieve_knowledge(request: AgentRunRequest) -> bool:
    """Return whether this request should spend retrieval budget.

    Knowledge bindings default to ``auto`` so requests handled by an attached
    web-search tool are not mixed with unrelated KB chunks. Explicit document
    prompts still retrieve, and ``always`` remains available for agents that
    intentionally require retrieval for every request.
    """

    bindings = request.agent_version.knowledge_bases
    if not bindings:
        return False
    if any(binding.mode == "always" for binding in bindings):
        return True

    prompt = _normalize_prompt(request.input.text)
    if _contains_marker(prompt, _KNOWLEDGE_REQUEST_MARKERS):
        return True
    has_web_search = any(
        tool.name.strip().lower() == "web_search"
        for tool in request.agent_version.tools
    )
    if not has_web_search:
        return True
    if _contains_marker(prompt, _NO_EXTERNAL_SEARCH_MARKERS):
        return True
    # ``auto`` should skip only an explicitly external/web-research request.
    # Merely having the web_search tool available must not hide an attached KB
    # from ordinary questions such as the phase-9 retrieval fixtures.
    return not _contains_marker(prompt, _EXTERNAL_RESEARCH_MARKERS)
