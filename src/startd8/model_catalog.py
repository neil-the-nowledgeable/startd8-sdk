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

    # Mythos-class flagship — highest capability tier (above Opus).
    CLAUDE_FABLE_LATEST = "anthropic:claude-fable-5"

    # Flagship - Best quality Opus-tier, highest cost among Opus models
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

    # Flagship - most capable model callable via Chat Completions.
    # NOTE: gpt-5.5-pro is the nominal top model but is Responses-API-only (404 "not a chat model"
    # on v1/chat/completions), so the latest-flagship default points at gpt-5.5 until Responses-API
    # support lands. See docs/design/OPENAI_GPT_CONFIGURATION_QUESTIONS.md (Q3).
    GPT_FLAGSHIP_LATEST = "openai:gpt-5.5"

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
    # DeepSeek Models
    # ==========================================================================

    # General chat/code (DeepSeek-V3 class) — strong cost position
    DEEPSEEK_CHAT = "deepseek:deepseek-chat"

    # Reasoning (DeepSeek-R1 class)
    DEEPSEEK_REASONER = "deepseek:deepseek-reasoner"

    # ==========================================================================
    # Jetson Edge Cluster (self-hosted; opt-in, LAN; see docs/design/jetson-cluster-benchmark/)
    # ==========================================================================

    # Clean general baseline ("$500 edge box" contestant)
    JETSON_MISTRAL_BASE = "jetson:mistral-7b-base"

    # In-domain fine-tuned adapter — fenced track only, never a general-leaderboard peer
    JETSON_ITER_002 = "jetson:iter-002"

    # ==========================================================================
    # Recommended Defaults by Use Case
    # ==========================================================================

    # Primary Contractor pattern: flagship lead/reviewer + cheap drafter.
    # REQ-PCMR-100: lead/reviewer run on the Anthropic flagship (Opus 4.8) for
    # max spec/review/integration quality; the reviewer role defaults to the
    # lead (prime_contractor.py), so it inherits this with no separate edit.
    # REQ-PCMR-101: drafter stays the cheapest stable tier (Gemini Flash Lite).
    # To opt down to the balanced lead, set lead_agent=Models.CLAUDE_SONNET_LATEST.
    PRIMARY_CONTRACTOR_LEAD = CLAUDE_OPUS_LATEST
    PRIMARY_CONTRACTOR_DRAFTER = GEMINI_FLASH_LITE

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

    # Local-lane contestants (clean general code models on the localhost Ollama; FR-LO-4)
    OLLAMA_QWEN_CODER_14B = "ollama:qwen2.5-coder:14b"
    OLLAMA_QWEN_CODER_7B = "ollama:qwen2.5-coder:7b"
    OLLAMA_CODELLAMA = "ollama:codellama:latest"


# Model registry with full metadata
_MODEL_REGISTRY: Dict[str, ModelInfo] = {
    # Anthropic — Mythos-class (above Opus)
    "claude-fable-5": ModelInfo(
        provider="anthropic",
        model_id="claude-fable-5",
        tier="flagship",
        capabilities={"text", "vision", "code", "reasoning"},
    ),
    # Anthropic — Opus tier
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
    # DeepSeek
    "deepseek-chat": ModelInfo(
        provider="deepseek",
        model_id="deepseek-chat",
        tier="balanced",
        capabilities={"text", "code", "reasoning"},
    ),
    "deepseek-reasoner": ModelInfo(
        provider="deepseek",
        model_id="deepseek-reasoner",
        tier="balanced",
        capabilities={"text", "code", "reasoning"},
    ),
    # Jetson edge cluster (aliases; served on a self-hosted LAN endpoint)
    "mistral-7b-base": ModelInfo(
        provider="jetson",
        model_id="mistral-7b-base",
        tier="fast",
        capabilities={"text", "code"},
    ),
    "iter-002": ModelInfo(
        provider="jetson",
        model_id="iter-002",
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
    # Ollama local-lane contestants (clean general code models; FR-LO-4)
    "qwen2.5-coder:14b": ModelInfo(
        provider="ollama",
        model_id="qwen2.5-coder:14b",
        tier="fast",
        capabilities={"text", "code"},
    ),
    "qwen2.5-coder:7b": ModelInfo(
        provider="ollama",
        model_id="qwen2.5-coder:7b",
        tier="fast",
        capabilities={"text", "code"},
    ),
    "codellama:latest": ModelInfo(
        provider="ollama",
        model_id="codellama:latest",
        tier="fast",
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
        "deepseek": {
            "flagship": Models.DEEPSEEK_CHAT,
            "balanced": Models.DEEPSEEK_CHAT,
            "fast": Models.DEEPSEEK_CHAT,
            "mini": Models.DEEPSEEK_CHAT,
            "reasoning": Models.DEEPSEEK_REASONER,
        },
        "jetson": {
            "flagship": Models.JETSON_MISTRAL_BASE,
            "balanced": Models.JETSON_MISTRAL_BASE,
            "fast": Models.JETSON_MISTRAL_BASE,
            "mini": Models.JETSON_MISTRAL_BASE,
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


# ---------------------------------------------------------------------------
# Flagship single source of truth — "what loads for a vendor, and why"
# ---------------------------------------------------------------------------
#
# A "flagship" is a vendor's designated default model: the **newest STABLE**
# (GA) model of that vendor. Previews/experimental builds are NEVER the
# flagship, even when they are the highest-capability entry. The flagship is
# curated by hand here (not computed) so it is explicit and reviewable:
#
#   vendor      flagship                 why
#   --------    ---------------------    ---------------------------------------
#   anthropic   claude-opus-4-8          newest stable Opus. NOTE: Fable-5 is a
#                                        distinct higher "Mythos" class and is
#                                        NOT the default flagship — reach it only
#                                        by explicit override.
#   openai      gpt-5.5                  newest stable flagship.
#   gemini      gemini-2.5-pro           newest STABLE pro (NOT 3.x-*-preview).
#   mistral     mistral-large-latest     newest stable large.
#   deepseek    deepseek-chat            sole stable chat flagship.
#   ollama      startd8-coder            local-only; exempt from the cloud
#                                        flagship guarantee (callers treat the
#                                        local default separately).
#
# Do NOT resolve a vendor default via `provider.supported_models[0]` — that is
# list-ordering, not a flagship designation, and is preview/stale for several
# vendors. Resolve via get_flagship() instead.

# Agent/preset aliases that callers use which are NOT provider names.
_PROVIDER_ALIASES = {
    "claude": "anthropic",
    "gpt": "openai",
    "gpt4": "openai",
    "gpt-4": "openai",
    "gpt5": "openai",
    "googleai": "gemini",
    "google": "gemini",
}

# Known canonical provider names (those resolvable by the catalog tier map).
_KNOWN_PROVIDERS = {
    "anthropic", "openai", "gemini", "mistral",
    "deepseek", "jetson", "ollama", "nim",
}


def canonical_provider(name: str) -> Optional[str]:
    """Normalize an agent/preset name to a canonical provider name.

    The MCP server and other callers accept agent aliases like ``claude`` or
    ``gpt4`` that are NOT provider names; the provider registry and the catalog
    only understand canonical names (``anthropic``, ``openai``, ``gemini`` …).
    Without this mapping the *default* agent ``claude`` resolves to no provider
    and no flagship at all.

    Returns the canonical provider name, or ``None`` if unrecognized (callers
    MUST handle ``None`` explicitly rather than guessing).
    """
    if not name:
        return None
    key = name.strip().lower()
    if key in _KNOWN_PROVIDERS:
        return key
    return _PROVIDER_ALIASES.get(key)


def get_flagship(provider: str) -> Optional[str]:
    """Return a vendor's flagship ``"provider:model"`` spec (newest STABLE model).

    This is the canonical single source of truth for default-agent model
    selection. It is a thin, explicitly-named wrapper over
    ``get_latest_model(provider, tier="flagship")`` so callers express intent
    ("give me the flagship") rather than a tier string.

    The ``provider`` argument may be a provider name or an agent alias
    (``claude``/``gpt4`` …); it is normalized via :func:`canonical_provider`.
    Returns ``None`` for an unknown provider — callers MUST handle ``None``
    explicitly and MUST NOT fall back to ``supported_models[0]``.
    """
    canon = canonical_provider(provider)
    if canon is None:
        return None
    return get_latest_model(canon, tier="flagship")


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
