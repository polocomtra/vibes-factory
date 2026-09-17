"""Platform-owned model catalog used by the Phase 2 control plane.

This deliberately contains no vendor SDK imports. Phase 3 can replace the
implementation behind the same small catalog interface when providers land.
"""

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, slots=True)
class ModelDefinition:
    provider: str
    name: str
    display_name: str
    capabilities: dict[str, bool]


MODEL_CATALOG: Final[tuple[ModelDefinition, ...]] = (
    ModelDefinition(
        provider="google",
        name="gemini-2.5-flash",
        display_name="Gemini 2.5 Flash",
        capabilities={
            "tool_calling": True,
            "streaming": True,
            "structured_output": True,
            "vision": True,
            "reasoning": False,
        },
    ),
    ModelDefinition(
        provider="openai",
        name="gpt-4.1-mini",
        display_name="GPT-4.1 Mini",
        capabilities={
            "tool_calling": True,
            "streaming": True,
            "structured_output": True,
            "vision": True,
            "reasoning": False,
        },
    ),
)


def list_models() -> tuple[ModelDefinition, ...]:
    return MODEL_CATALOG


def find_model(provider: str, name: str) -> ModelDefinition | None:
    return next(
        (
            definition
            for definition in MODEL_CATALOG
            if definition.provider == provider and definition.name == name
        ),
        None,
    )
