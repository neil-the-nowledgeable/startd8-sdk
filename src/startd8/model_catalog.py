"""
Model Catalog - Centralized model constants and discovery.

This module provides:
- Constants for latest/recommended models per provider
- Helper functions to get models by capability
- Validation functions to check model availability

Usage:
    from startd8.model_catalog import Models, get_latest_model

    # Use constants directly
    config = WorkflowConfig(lead_agent=Models.CLAUDE_SONNET_LATEST)

    # Or get by capability
    fast_model = get_latest_model("gemini", tier="fast")
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class ModelInfo:
    """Information about a model."""

    provider: str
    model_id: str
    tier: str  # "flagship", "balanced", "fast", "mini"
    capabilities: Set[str]  # "text", "vision", "code", "reasoning"

    @property
    def full_id(self) -> str:
        """Return provider:model format."""
        return f"{self.provider}:{self.model_id}"


class Models:
    """
    Centralized model constants.

    These are the recommended models for various use cases.
    Update these when new models are released.
    """

    # ==========================================================================
    # Anthropic Claude Models
    # ==========================================================================

    # Flagship - Best quality, highest cost
    CLAUDE_OPUS_LATEST = "anthropic:claude-opus-4-5-20251101"

    # Balanced - Good quality/cost tradeoff (recommended for most use cases)
    CLAUDE_SONNET_LATEST = "anthropic:claude-sonnet-4-5-20250927"

    # Fast - Quick responses, lower cost
    CLAUDE_HAIKU_LATEST = "anthropic:claude-haiku-4-5-20251008"

    # Legacy (for backwards compatibility)
    CLAUDE_SONNET_4 = "anthropic:claude-sonnet-4-20250514"
    CLAUDE_SONNET_35 = "anthropic:claude-3-5-sonnet-20241022"

    # ==========================================================================
    # Google Gemini Models
    # ==========================================================================

    # Flagship
    GEMINI_PRO_LATEST = "gemini:gemini-2.5-pro"

    # Balanced
    GEMINI_FLASH_LATEST = "gemini:gemini-2.5-flash"

    # Fast/Mini - Cheapest, fastest
    GEMINI_FLASH_LITE = "gemini:gemini-2.5-flash-lite"

    # Preview models (may change)
    GEMINI_3_PRO_PREVIEW = "gemini:gemini-3-pro-preview"
    GEMINI_3_FLASH_PREVIEW = "gemini:gemini-3-flash-preview"

    # ==========================================================================
    # OpenAI Models
    # ==========================================================================

    # Flagship (Reasoning)
    O3_LATEST = "openai:o3"

    # Balanced
    GPT4_1_LATEST = "openai:gpt-4.1"

    # Fast
    GPT4_LATEST = "openai:gpt-4o"

    # Mini - Fast, cheap
    GPT4_MINI = "openai:gpt-4o-mini"

    # Legacy aliases
    GPT5_2_CODEX_LATEST = O3_LATEST

    # ==========================================================================
    # Recommended Defaults by Use Case
    # ==========================================================================

    # Lead Contractor pattern: balanced lead + cheap drafter
    LEAD_CONTRACTOR_LEAD = CLAUDE_SONNET_LATEST
    LEAD_CONTRACTOR_DRAFTER = GEMINI_FLASH_LITE

    # Code review: needs good reasoning
    CODE_REVIEW = CLAUDE_SONNET_LATEST

    # Document enhancement: balanced
    DOC_ENHANCEMENT = CLAUDE_SONNET_LATEST

    # Quick validation: fast and cheap
    QUICK_VALIDATION = CLAUDE_HAIKU_LATEST

    # Semantic validation (Haiku pattern from lessons learned)
    SEMANTIC_VALIDATOR = CLAUDE_HAIKU_LATEST


# Model registry with full metadata
_MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # Anthropic
    "claude-opus-4-5-20251101": ModelInfo(
        provider="anthropic",
        model_id="claude-opus-4-5-20251101",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-sonnet-4-5-20250927": ModelInfo(
        provider="anthropic",
        model_id="claude-sonnet-4-5-20250927",
        tier="balanced",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-haiku-4-5-20251008": ModelInfo(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251008",
        tier="fast",
        capabilities={"text", "code"},
    ),
    "claude-sonnet-4-20250514": ModelInfo(
        provider="anthropic",
        model_id="claude-sonnet-4-20250514",
        tier="balanced",
        capabilities={"text", "vision", "code", "reasoning"},
    ),

    # Gemini
    "gemini-2.5-pro": ModelInfo(
        provider="gemini",
        model_id="gemini-2.5-pro",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "gemini-2.5-flash": ModelInfo(
        provider="gemini",
        model_id="gemini-2.5-flash",
        tier="balanced",
        capabilities={"text", "vision", "code"},
    ),
    "gemini-2.5-flash-lite": ModelInfo(
        provider="gemini",
        model_id="gemini-2.5-flash-lite",
        tier="mini",
        capabilities={"text", "code"},
    ),

    # OpenAI
    "o3": ModelInfo(
        provider="openai",
        model_id="o3",
        tier="flagship",
        capabilities={"text", "code", "reasoning"},
    ),
    "gpt-4.1": ModelInfo(
        provider="openai",
        model_id="gpt-4.1",
        tier="balanced",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "gpt-4o": ModelInfo(
        provider="openai",
        model_id="gpt-4o",
        tier="fast",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "gpt-4o-mini": ModelInfo(
        provider="openai",
        model_id="gpt-4o-mini",
        tier="mini",
        capabilities={"text", "code"},
    ),
}


def get_model_info(model_id: str) -> Optional[ModelInfo]:
    """
    Get information about a model.

    Args:
        model_id: Model ID (with or without provider prefix)

    Returns:
        ModelInfo if found, None otherwise
    """
    # Strip provider prefix if present
    if ":" in model_id:
        model_id = model_id.split(":", 1)[1]
    return _MODEL_REGISTRY.get(model_id)


def is_known_model(model_id: str) -> bool:
    """
    Check if a model is in the known catalog.

    Args:
        model_id: Model ID (with or without provider prefix)

    Returns:
        True if model is known
    """
    return get_model_info(model_id) is not None


def get_latest_model(
    provider: str,
    tier: str = "balanced",
) -> Optional[str]:
    """
    Get the latest model for a provider and tier.

    Args:
        provider: Provider name ("anthropic", "gemini", "openai")
        tier: Model tier ("flagship", "balanced", "fast", "mini")

    Returns:
        Full model ID (provider:model) or None
    """
    tier_map = {
        "anthropic": {
            "flagship": Models.CLAUDE_OPUS_LATEST,
            "balanced": Models.CLAUDE_SONNET_LATEST,
            "fast": Models.CLAUDE_HAIKU_LATEST,
            "mini": Models.CLAUDE_HAIKU_LATEST,
        },
        "gemini": {
            "flagship": Models.GEMINI_PRO_LATEST,
            "balanced": Models.GEMINI_FLASH_LATEST,
            "fast": Models.GEMINI_FLASH_LITE,
            "mini": Models.GEMINI_FLASH_LITE,
        },
        "openai": {
            "flagship": Models.O3_LATEST,
            "balanced": Models.GPT4_1_LATEST,
            "fast": Models.GPT4_LATEST,
            "mini": Models.GPT4_MINI,
        },
    }

    provider_map = tier_map.get(provider.lower())
    if not provider_map:
        return None
    return provider_map.get(tier)


def list_models_by_tier(tier: str) -> List[str]:
    """
    List all models of a given tier.

    Args:
        tier: Model tier ("flagship", "balanced", "fast", "mini")

    Returns:
        List of full model IDs
    """
    return [
        info.full_id
        for info in _MODEL_REGISTRY.values()
        if info.tier == tier
    ]


def list_models_by_capability(capability: str) -> List[str]:
    """
    List all models with a given capability.

    Args:
        capability: Capability name ("text", "vision", "code", "reasoning")

    Returns:
        List of full model IDs
    """
    return [
        info.full_id
        for info in _MODEL_REGISTRY.values()
        if capability in info.capabilities
    ]


__all__ = [
    "Models",
    "ModelInfo",
    "get_model_info",
    "is_known_model",
    "get_latest_model",
    "list_models_by_tier",
    "list_models_by_capability",
]
