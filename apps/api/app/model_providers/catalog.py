"""Static provider/model capabilities for the Phase 3 catalog."""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    provider: str
    name: str
    display_name: str
    # Keep the Phase 2 dictionary shape stable for existing agent-editor code.
    capabilities: dict[str, bool]
    context_window: int | None = None
    max_output_tokens: int | None = None
    is_default: bool = False


MODEL_CATALOG: Final[tuple[ModelDefinition, ...]] = (
    ModelDefinition(
        "azure_openai",
        "gpt-5.6-luna",
        "GPT-5.6 Luna",
        {
            "tool_calling": True,
            "streaming": True,
            "structured_output": True,
            "vision": True,
            "reasoning": True,
        },
        1_050_000,
        128_000,
        True,
    ),
    ModelDefinition(
        "google",
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
        {
            "tool_calling": True,
            "streaming": True,
            "structured_output": True,
            "vision": True,
            "reasoning": False,
        },
        1_048_576,
        65_536,
    ),
    ModelDefinition(
        "openai",
        "gpt-4.1-mini",
        "GPT-4.1 Mini",
        {
            "tool_calling": True,
            "streaming": True,
            "structured_output": True,
            "vision": True,
            "reasoning": False,
        },
        1_047_576,
        32_768,
    ),
    ModelDefinition(
        "deepseek",
        "deepseek-flash",
        "DeepSeek Flash",
        {
            "tool_calling": True,
            "streaming": True,
            "structured_output": True,
            "vision": False,
            "reasoning": True,
        },
    ),
    ModelDefinition(
        "deepseek",
        "deepseek-v4-pro",
        "DeepSeek V4 Pro",
        {
            "tool_calling": True,
            "streaming": True,
            "structured_output": True,
            "vision": False,
            "reasoning": True,
        },
    ),
)


def list_models() -> tuple[ModelDefinition, ...]:
    return MODEL_CATALOG


def get_default_model() -> ModelDefinition:
    return next(
        (model for model in MODEL_CATALOG if model.is_default), MODEL_CATALOG[0]
    )


def find_model(provider: str, name: str) -> ModelDefinition | None:
    provider = provider.strip().lower()
    name = name.strip().lower()
    return next(
        (
            item
            for item in MODEL_CATALOG
            if item.provider == provider and item.name == name
        ),
        None,
    )
