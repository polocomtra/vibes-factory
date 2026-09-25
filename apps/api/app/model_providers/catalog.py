"""Active provider/model capabilities exposed by the platform catalog.

Provider adapters remain available in the registry even when a model is not
currently exposed here. Re-enabling a model should be a catalog/configuration
change, not a runtime architecture change.
"""

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
        "gpt-6-luna",
        "GPT-6 Luna",
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
