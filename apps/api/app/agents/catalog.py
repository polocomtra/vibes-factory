"""Backward-compatible import surface for the Phase 3 model catalog."""

from ..model_providers.catalog import (
    ModelDefinition,
    find_model,
    get_default_model,
    list_models,
)

__all__ = ["ModelDefinition", "find_model", "get_default_model", "list_models"]
