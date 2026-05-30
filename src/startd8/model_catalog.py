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
    CLAUDE_OPUS_LATEST = "anthropic:claude-opus-4-8"

    # Previous flagships
    CLAUDE_OPUS_47 = "anthropic:claude-opus-4-7"
    CLAUDE_OPUS_46 = "anthropic:claude-opus-4-6"
    CLAUDE_OPUS_45 = "anthropic:claude-opus-4-5-20251101"

    # Balanced - Good quality/cost tradeoff (recommended for most use cases)
    CLAUDE_SONNET_LATEST = "anthropic:claude-sonnet-4-6"

    # Previous balanced
    CLAUDE_SONNET_45 = "anthropic:claude-sonnet-4-5-20250929"

    # Fast - Quick responses, lower cost
    CLAUDE_HAIKU_LATEST = "anthropic:claude-haiku-4-5-20251001"

    # Legacy (for backwards compatibility)
    CLAUDE_SONNET_4 = "anthropic:claude-sonnet-4-20250514"
    CLAUDE_SONNET_35 = "anthropic:claude-3-5-sonnet-20241022"

    # ==========================================================================
    # Google Gemini Models
    # ==========================================================================

    # Flagship (newest stable; 3.x are preview-only, see below)
    GEMINI_PRO_LATEST = "gemini:gemini-2.5-pro"

    # Balanced
    GEMINI_FLASH_LATEST = "gemini:gemini-2.5-flash"

    # Fast/Mini - Cheapest, fastest
    GEMINI_FLASH_LITE = "gemini:gemini-2.5-flash-lite"

    # Preview models (may change/deprecate without notice — not used as stable defaults)
    GEMINI_3_PRO_PREVIEW = "gemini:gemini-3.1-pro-preview"
    GEMINI_3_FLASH_PREVIEW = "gemini:gemini-3-flash-preview"

    # ==========================================================================
    # OpenAI Models
    # ==========================================================================

    # Flagship - most capable
    GPT_FLAGSHIP_LATEST = "openai:gpt-5.5-pro"

    # Balanced - standard quality/cost
    GPT_STANDARD_LATEST = "openai:gpt-5.5"

    # Fast - smaller, quicker
    GPT_MINI_LATEST = "openai:gpt-5.4-mini"

    # Mini - cheapest, fastest
    GPT_NANO_LATEST = "openai:gpt-5.4-nano"

    # Coding-optimized
    GPT_CODEX_LATEST = "openai:gpt-5.3-codex"

    # Legacy aliases (kept for backward compatibility; values refreshed to current GA)
    O3_LATEST = GPT_FLAGSHIP_LATEST
    GPT4_1_LATEST = GPT_STANDARD_LATEST
    GPT4_LATEST = GPT_MINI_LATEST
    GPT4_MINI = GPT_NANO_LATEST
    GPT5_2_CODEX_LATEST = GPT_CODEX_LATEST

    # ==========================================================================
    # Mistral AI Models
    # ==========================================================================

    # Flagship
    MISTRAL_LARGE_LATEST = "mistral:mistral-large-latest"

    # Balanced
    MISTRAL_MEDIUM_LATEST = "mistral:mistral-medium-latest"

    # Fast
    MISTRAL_SMALL_LATEST = "mistral:mistral-small-latest"

    # ==========================================================================
    # Recommended Defaults by Use Case
    # ==========================================================================

    # Primary Contractor pattern: balanced lead + cheap drafter
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

    # ==========================================================================
    # NVIDIA NIM Models
    # ==========================================================================

    NEMOTRON_NANO = "nim:nvidia/nemotron-3-nano-30b-a3b"

    # ==========================================================================
    # Ollama Local Models
    # ==========================================================================

    # Micro Prime local code generation (REQ-MP-104)
    STARTD8_CODER = "ollama:startd8-coder"

    # Micro Prime: local model for SIMPLE element body generation
    MICRO_PRIME_LOCAL = STARTD8_CODER


# Model registry with full metadata
_MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # Anthropic
    "claude-opus-4-8": ModelInfo(
        provider="anthropic",
        model_id="claude-opus-4-8",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-opus-4-7": ModelInfo(
        provider="anthropic",
        model_id="claude-opus-4-7",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-opus-4-6": ModelInfo(
        provider="anthropic",
        model_id="claude-opus-4-6",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-opus-4-5-20251101": ModelInfo(
        provider="anthropic",
        model_id="claude-opus-4-5-20251101",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-sonnet-4-6": ModelInfo(
        provider="anthropic",
        model_id="claude-sonnet-4-6",
        tier="balanced",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-sonnet-4-5-20250929": ModelInfo(
        provider="anthropic",
        model_id="claude-sonnet-4-5-20250929",
        tier="balanced",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "claude-haiku-4-5-20251008": ModelInfo(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251008",
        tier="fast",
        capabilities={"text", "code"},
    ),
    "claude-haiku-4-5-20251001": ModelInfo(
        provider="anthropic",
        model_id="claude-haiku-4-5-20251001",
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
    "gemini-3.1-pro-preview": ModelInfo(
        provider="gemini",
        model_id="gemini-3.1-pro-preview",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "gemini-3-flash-preview": ModelInfo(
        provider="gemini",
        model_id="gemini-3-flash-preview",
        tier="balanced",
        capabilities={"text", "vision", "code"},
    ),
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
    "gpt-5.5-pro": ModelInfo(
        provider="openai",
        model_id="gpt-5.5-pro",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "gpt-5.5": ModelInfo(
        provider="openai",
        model_id="gpt-5.5",
        tier="balanced",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    "gpt-5.4-mini": ModelInfo(
        provider="openai",
        model_id="gpt-5.4-mini",
        tier="fast",
        capabilities={"text", "code", "reasoning"},
    ),
    "gpt-5.4-nano": ModelInfo(
        provider="openai",
        model_id="gpt-5.4-nano",
        tier="mini",
        capabilities={"text", "code"},
    ),
    "gpt-5.3-codex": ModelInfo(
        provider="openai",
        model_id="gpt-5.3-codex",
        tier="balanced",
        capabilities={"text", "code", "reasoning"},
    ),
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

    # Mistral AI
    "mistral-large-latest": ModelInfo(
        provider="mistral",
        model_id="mistral-large-latest",
        tier="flagship",
        capabilities={"text", "code", "reasoning"},
    ),
    "mistral-medium-latest": ModelInfo(
        provider="mistral",
        model_id="mistral-medium-latest",
        tier="balanced",
        capabilities={"text", "code", "reasoning"},
    ),
    "mistral-small-latest": ModelInfo(
        provider="mistral",
        model_id="mistral-small-latest",
        tier="fast",
        capabilities={"text", "code"},
    ),
    # Ollama local models
    "startd8-coder": ModelInfo(
        provider="ollama",
        model_id="startd8-coder",
        tier="mini",
        capabilities={"text", "code"},
    ),
    # NVIDIA NIM
    "nvidia/nemotron-3-nano-30b-a3b": ModelInfo(
        provider="nim",
        model_id="nvidia/nemotron-3-nano-30b-a3b",
        tier="reasoning",
        capabilities={"text", "reasoning", "code"},
    ),
}


def _load_user_overlay() -> Dict[str, ModelInfo]:
    """User overlay over ``_MODEL_REGISTRY`` (REQ-TMM-130/131).

    Reads ``user_models.json`` via ``UserModelStore``; records with an invalid
    tier are already dropped by ``as_catalog_overlay`` (R1-S3). User-added
    entries take precedence over the baseline registry on id collision. Returns
    an empty overlay on any failure (REQ-TMM-106) so the catalog never crashes.

    Note: ``get_latest_model`` intentionally does NOT consult this overlay — its
    tier→constant mapping is unchanged, so overlay models are *resolvable* but
    never *auto-selected* as a tier default (NR-6).
    """
    try:
        from .user_models import UserModelStore

        overlay_raw = UserModelStore().as_catalog_overlay()
    except Exception:  # pragma: no cover - overlay must never break the catalog
        return {}

    result: Dict[str, ModelInfo] = {}
    for model_id, meta in overlay_raw.items():
        result[model_id] = ModelInfo(
            provider=meta["provider"],
            model_id=model_id,
            tier=meta["tier"],
            capabilities=set(meta.get("capabilities") or set()),
        )
    return result


def _registry_with_overlay() -> Dict[str, ModelInfo]:
    """Baseline registry merged with the user overlay (user wins on collision)."""
    merged = dict(_MODEL_REGISTRY)
    merged.update(_load_user_overlay())
    return merged


def get_model_info(model_id: str) -> Optional[ModelInfo]:
    """
    Get information about a model.

    Consults the user overlay (REQ-TMM-130) before the curated registry, so a
    user-added model with a valid tier resolves here and takes precedence over
    a colliding baseline id (REQ-TMM-131).

    Args:
        model_id: Model ID (with or without provider prefix)

    Returns:
        ModelInfo if found, None otherwise
    """
    # Strip provider prefix if present
    if ":" in model_id:
        model_id = model_id.split(":", 1)[1]
    overlay = _load_user_overlay()
    if model_id in overlay:
        return overlay[model_id]
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
            "flagship": Models.GPT_FLAGSHIP_LATEST,
            "balanced": Models.GPT_STANDARD_LATEST,
            "fast": Models.GPT_MINI_LATEST,
            "mini": Models.GPT_NANO_LATEST,
        },
        "mistral": {
            "flagship": Models.MISTRAL_LARGE_LATEST,
            "balanced": Models.MISTRAL_MEDIUM_LATEST,
            "fast": Models.MISTRAL_SMALL_LATEST,
            "mini": Models.MISTRAL_SMALL_LATEST,
        },
        "ollama": {
            "flagship": Models.STARTD8_CODER,
            "balanced": Models.STARTD8_CODER,
            "fast": Models.STARTD8_CODER,
            "mini": Models.STARTD8_CODER,
        },
        "nim": {
            "flagship": Models.NEMOTRON_NANO,
            "balanced": Models.NEMOTRON_NANO,
            "reasoning": Models.NEMOTRON_NANO,
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
        for info in _registry_with_overlay().values()
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
        for info in _registry_with_overlay().values()
        if capability in info.capabilities
    ]


# Tier escalation order: mini → fast → balanced → flagship
_TIER_ESCALATION = ["mini", "fast", "balanced", "flagship"]


def get_escalation_target(agent_spec: str) -> Optional[str]:
    """Return the next-tier-up agent spec for escalation, or None if already flagship.

    Args:
        agent_spec: Current agent spec (e.g. "anthropic:claude-sonnet-4-6").

    Returns:
        Escalated agent spec, or None if no escalation is possible.
    """
    if ":" not in agent_spec:
        return None
    provider, model_id = agent_spec.split(":", 1)
    info = get_model_info(model_id)  # overlay-aware (REQ-TMM-130)
    if info is None:
        return None
    try:
        current_idx = _TIER_ESCALATION.index(info.tier)
    except ValueError:
        return None
    if current_idx >= len(_TIER_ESCALATION) - 1:
        return None  # Already flagship
    next_tier = _TIER_ESCALATION[current_idx + 1]
    return get_latest_model(provider, tier=next_tier)


__all__ = [
    "Models",
    "ModelInfo",
    "get_model_info",
    "is_known_model",
    "get_latest_model",
    "get_escalation_target",
    "list_models_by_tier",
    "list_models_by_capability",
]
