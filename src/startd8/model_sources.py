"""Four-source model-id reconciliation (PL-TMM-3).

Ties together the four model-list sources that exist in the SDK:

  #1 ``model_catalog._MODEL_REGISTRY``  — curated tier/capability metadata
  #2 ``<Provider>.HARDCODED_MODELS``    — provider baseline
  #3 ``discovered_models.json``         — API discovery cache
  #4 ``user_models.json``               — manual user overlay

``classify_model_id`` is the single shared spine (R1-S2) consumed by the TUI
picker grouping, the Manage-Models list annotation, and add/entry validation
(REQ-TMM-120). Sources #2 and #3 are read together via
``provider.supported_models`` (which already merges baseline ∪ discovered).
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .logging_config import get_logger

logger = get_logger(__name__)

# Providers that expose a HARDCODED_MODELS baseline + API discovery.
RECONCILED_PROVIDERS = ("anthropic", "openai", "gemini")


def _default_catalog_lookup(model_id: str) -> bool:
    """Source #1: is the id in the model_catalog registry (overlay-aware)?"""
    try:
        from .model_catalog import get_model_info

        return get_model_info(model_id) is not None
    except Exception:  # pragma: no cover - catalog import/lookup must never crash classify
        logger.debug("catalog lookup failed for %r", model_id, exc_info=True)
        return False


def _get_provider(provider: str):
    """Resolve a provider instance via the registry (sources #2 + #3)."""
    try:
        from .providers.registry import ProviderRegistry

        ProviderRegistry.discover()
        return ProviderRegistry.get_provider(provider.lower())
    except Exception:
        logger.debug("provider resolution failed for %r", provider, exc_info=True)
        return None


def classify_model_id(
    provider: str,
    model_id: str,
    *,
    store: Optional[Any] = None,
    provider_obj: Optional[Any] = None,
    catalog_lookup: Optional[Callable[[str], bool]] = None,
) -> str:
    """Classify a model id against all four sources (REQ-TMM-120).

    Returns one of:
      * ``"user"``         — present in the user overlay (#4). Checked first, so
                             a user-added id that also collides with a baseline
                             id is reported as ``user`` (precedence per REQ-TMM-131).
      * ``"known"``        — present in the catalog (#1) or the provider's
                             ``supported_models`` (#2 ∪ #3).
      * ``"unrecognized"`` — absent from all four sources.

    The ``store`` / ``provider_obj`` / ``catalog_lookup`` parameters are
    injectable for testing; defaults read the real sources.
    """
    provider_l = provider.lower()

    if store is None:
        from .user_models import UserModelStore

        store = UserModelStore()
    if any(r.get("model_id") == model_id for r in store.list(provider_l)):
        return "user"

    lookup = catalog_lookup or _default_catalog_lookup
    if lookup(model_id):
        return "known"

    prov = provider_obj if provider_obj is not None else _get_provider(provider_l)
    if prov is not None and model_id in (getattr(prov, "supported_models", None) or []):
        return "known"

    return "unrecognized"


__all__ = ["classify_model_id", "RECONCILED_PROVIDERS"]
