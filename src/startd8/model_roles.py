"""First-class per-role model resolution (MODEL_CONFIG_FIRST_CLASS).

One **backend-agnostic** resolver every LLM-calling site uses, so a role's model is
chosen by a single documented precedence and one provider/override flips every unset
role. The resolver returns a **spec string** (e.g. ``"gemini:gemini-2.5-pro"``); callers
create the agent via ``resolve_agent_spec`` with their own max_tokens/timeout. It never
special-cases a provider — a resolved spec may name anthropic / gemini / openai / ollama
/ a future ``edge`` backend identically (see MICRO_PRIME_BACKEND_ABSTRACTION_REQUIREMENTS).

Precedence (highest first), per role:
  1. explicit ``override`` (per-call / CLI flag)
  2. ``run_config[role]``  (also accepts the legacy ``"{role}_agent"`` key)
  3. ``~/.startd8/config.json``  ``models.<role>.default``
  4. inheritance — the **parent** role's *explicit* spec (steps 1-3 only):
       reviewer / ingestion_assessor / ingestion_transformer  ← lead
       micro_prime_cloud_retry                                 ← drafter
  5. provider default — ``get_latest_model(provider, <role tier>)`` where
     ``provider`` = ``provider`` arg | ``run_config["default_provider"|"provider"]``
  6. catalog default (role-pinned; intentional quality tuning — REQ-PCMR)

Steps 1-3 are the role's "explicit" sources; inheritance (4) deliberately copies only a
parent's *explicit* choice (not the parent's provider/catalog default), so a bare
``--provider`` lets each role use its own tier rather than all cloning the lead.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from .model_catalog import Models, get_latest_model


class Role(str, Enum):
    """Canonical LLM roles across the pipeline (the single authoritative list)."""

    LEAD = "lead"
    DRAFTER = "drafter"
    TIER3 = "tier3"
    REVIEWER = "reviewer"
    INGESTION_ASSESSOR = "ingestion_assessor"
    INGESTION_TRANSFORMER = "ingestion_transformer"
    MICRO_PRIME_CLOUD_RETRY = "micro_prime_cloud_retry"
    MICRO_PRIME_LOCAL = "micro_prime_local"


# Tier used for the provider-default path (step 5): get_latest_model(provider, tier).
_ROLE_TIER: Dict[str, str] = {
    "lead": "flagship",
    "tier3": "flagship",
    "reviewer": "flagship",
    "ingestion_assessor": "balanced",
    "ingestion_transformer": "balanced",
    "drafter": "balanced",
    "micro_prime_cloud_retry": "fast",
    "micro_prime_local": "fast",
}

# Inheritance graph (step 4): an unset role copies the parent's *explicit* spec.
_INHERITS: Dict[str, str] = {
    "reviewer": "lead",
    "ingestion_assessor": "lead",
    "ingestion_transformer": "lead",
    "micro_prime_cloud_retry": "drafter",
}

# Catalog last-resort default (step 6). Provider-pinned defaults are intentional,
# quality-tuned (REQ-PCMR); a global override (step 5) flips them when desired.
_CATALOG_DEFAULT: Dict[str, str] = {
    "lead": Models.PRIMARY_CONTRACTOR_LEAD,
    "drafter": Models.PRIMARY_CONTRACTOR_DRAFTER,
    "tier3": Models.CLAUDE_OPUS_LATEST,
    "reviewer": Models.PRIMARY_CONTRACTOR_LEAD,  # reviewer tracks the lead by default
    "ingestion_assessor": Models.CLAUDE_SONNET_LATEST,
    "ingestion_transformer": Models.CLAUDE_SONNET_LATEST,
    "micro_prime_cloud_retry": Models.CLAUDE_HAIKU_LATEST,
    "micro_prime_local": "ollama:startd8-coder",
}

_FALLBACK_DEFAULT = Models.CLAUDE_SONNET_LATEST


def _role_str(role: "Role | str") -> str:
    return role.value if isinstance(role, Role) else str(role)


def _explicit_spec(
    role: str,
    override: Optional[str],
    run_config: Dict[str, Any],
    config_manager: Any,
) -> Optional[str]:
    """Steps 1-3 only: the role's *explicitly* chosen spec, or ``None``."""
    if override:
        return str(override)
    rc = run_config.get(role) or run_config.get(f"{role}_agent")
    if rc:
        return str(rc)
    if config_manager is not None:
        try:
            mc = config_manager.get_model_config(role) or {}
        except Exception:
            mc = {}
        if mc.get("default"):
            return str(mc["default"])
    return None


def resolve_role_spec(
    role: "Role | str",
    *,
    override: Optional[str] = None,
    run_config: Optional[Dict[str, Any]] = None,
    config_manager: Any = None,
    provider: Optional[str] = None,
) -> str:
    """Resolve a role to a model spec string by the documented precedence.

    Backend-agnostic and side-effect-free. See the module docstring for precedence.
    """
    role = _role_str(role)
    run_config = run_config or {}

    # 1-3: this role's explicit choice.
    explicit = _explicit_spec(role, override, run_config, config_manager)
    if explicit:
        return explicit

    # 4: inherit the parent's *explicit* choice (override applies only to this role).
    parent = _INHERITS.get(role)
    if parent:
        inherited = _explicit_spec(parent, None, run_config, config_manager)
        if inherited:
            return inherited

    # 5: global provider default at this role's tier.
    prov = provider or run_config.get("default_provider") or run_config.get("provider")
    if prov:
        spec = get_latest_model(str(prov), tier=_ROLE_TIER.get(role, "balanced"))
        if spec:
            return spec

    # 6: catalog default (role-pinned).
    return _CATALOG_DEFAULT.get(role, _FALLBACK_DEFAULT)


def resolve_role_agent(
    role: "Role | str",
    *,
    override: Optional[str] = None,
    run_config: Optional[Dict[str, Any]] = None,
    config_manager: Any = None,
    provider: Optional[str] = None,
    **agent_config: Any,
):
    """Convenience: resolve the spec (``resolve_role_spec``) then build the agent.

    Thin wrapper over ``resolve_agent_spec`` — most call sites want the spec string
    (they pass their own max_tokens/timeout), so prefer ``resolve_role_spec`` there.
    """
    from .utils.agent_resolution import resolve_agent_spec

    spec = resolve_role_spec(
        role, override=override, run_config=run_config,
        config_manager=config_manager, provider=provider,
    )
    return resolve_agent_spec(spec, **agent_config)


__all__ = ["Role", "resolve_role_spec", "resolve_role_agent"]
