"""``onboarding:`` — first-run orientation declaration (FR-1/2), a views.yaml section.

Coexists with ``views:`` / ``forms:`` / ``filters:`` / ``flows:`` / ``editors:``. Reads only
``onboarding:``. Flat mapping (not a list of named onboarding packs in v1). Strict unknown keys;
tolerant of absence (zero artifacts).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import yaml

_REQUIRED = ("route", "title")
_OPTIONAL = (
    "lead",
    "continue_href",
    "help_href",
    "tips",
    "empty_states",
    "storage_key",
    "nav_label",
    "redirect_root_if_empty",
)
_KEYS = frozenset(_REQUIRED + _OPTIONAL)


@dataclass(frozen=True)
class OnboardingSpec:
    route: str
    title: str
    lead: str = ""
    continue_href: str = "/"
    help_href: str = ""
    tips: Tuple[str, ...] = ()
    empty_states: Tuple[Tuple[str, str], ...] = ()  # (entity, copy)
    storage_key: str = "onboarding_tips_dismissed"
    nav_label: str = ""  # nav chrome; defaults to title when empty
    redirect_root_if_empty: bool = False

    @property
    def empty_state_map(self) -> dict:
        return dict(self.empty_states)

    @property
    def nav_text(self) -> str:
        return self.nav_label or self.title



def parse_onboarding(
    views_text: Optional[str], *, known_entities: frozenset = frozenset()
) -> Optional[OnboardingSpec]:
    """Parse ``onboarding:`` from views.yaml. ``None`` when section absent."""
    data = yaml.safe_load(views_text or "") or {}
    if not isinstance(data, dict) or "onboarding" not in data:
        return None
    raw = data["onboarding"]
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("views.yaml: `onboarding` must be a mapping")
    if not raw:
        raise ValueError("views.yaml: `onboarding` is empty — omit the section or set route/title")
    unknown = set(raw) - _KEYS
    if unknown:
        raise ValueError(f"views.yaml: onboarding has unknown keys {sorted(unknown)}")
    for req in _REQUIRED:
        if not raw.get(req):
            raise ValueError(f"views.yaml: onboarding missing required `{req}`")
    tips_raw = raw.get("tips") or []
    if not isinstance(tips_raw, list):
        raise ValueError("views.yaml: onboarding `tips` must be a list of strings")
    tips = tuple(str(t) for t in tips_raw)
    empty_raw = raw.get("empty_states") or {}
    if not isinstance(empty_raw, dict):
        raise ValueError("views.yaml: onboarding `empty_states` must be a mapping of Entity -> copy")
    if known_entities:
        for ent in empty_raw:
            if ent not in known_entities:
                raise ValueError(
                    f"views.yaml: onboarding empty_states references unknown entity {ent!r}"
                )
    empty_states = tuple(sorted((str(k), str(v)) for k, v in empty_raw.items()))
    redirect_raw = raw.get("redirect_root_if_empty", False)
    if not isinstance(redirect_raw, bool):
        raise ValueError("views.yaml: onboarding `redirect_root_if_empty` must be a boolean")
    return OnboardingSpec(
        route=str(raw["route"]),
        title=str(raw["title"]),
        lead=str(raw.get("lead") or ""),
        continue_href=str(raw.get("continue_href") or "/"),
        help_href=str(raw.get("help_href") or ""),
        tips=tips,
        empty_states=empty_states,
        storage_key=str(raw.get("storage_key") or "onboarding_tips_dismissed"),
        nav_label=str(raw.get("nav_label") or ""),
        redirect_root_if_empty=redirect_raw,
    )
