"""Provider-safe names for model-facing function tools."""

import re


def model_tool_name(name: str) -> str:
    """Return a stable function name accepted by OpenAI/Gemini tool schemas."""
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_-").lower()
    return (normalized or "tool")[:64]
