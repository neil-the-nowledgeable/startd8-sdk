# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Declarative onboarding-persona resolution (A1 — de-hardcodes portal_spec_builder personas).

The portal's personas were two hardcoded dicts (`_PERSONA_SECTIONS` + `_PERSONA_VALUE`). This loader
makes a persona's **section set + value prop** data: a persona declared in a ContextManifest's
``personas[]`` (with ``sections`` / ``value``) overrides; otherwise the hardcoded dicts are the
built-in default. This is the polish ``DEFAULT_THEME`` precedence idiom — except polish has no data
path; here the manifest IS the data path.

Manifest persona entry (in ``.contextcore.yaml`` ``spec.personas`` or top-level ``personas``)::

    - id: analyst                 # render id (portal_persona may alias to a built-in)
      portal_persona: analyst
      sections: [overview, scoring-methodology, leaderboard, ...]   # membership; order is build_portal_spec's
      value: {title: "...", pain: "...", headline: "...", content: "..."}

A pure-alias entry (only ``id``/``portal_persona``, no ``sections``/``value``) does NOT override the
built-in default for that render id (no regression).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional


@dataclass(frozen=True)
class PersonaProfile:
    """A render persona's section membership + value prop (resolved from manifest or hardcoded default)."""

    sections: FrozenSet[str]
    value: Dict[str, str]  # title, pain, headline, content (may be empty)


def load_personas(manifest_personas: Optional[List[Dict[str, Any]]] = None) -> Dict[str, PersonaProfile]:
    """Resolve render personas: hardcoded defaults overlaid by manifest-declared personas[].

    ``manifest_personas`` is the raw ``personas[]`` list (each: id/portal_persona + optional
    sections/value). Returns ``{render_id: PersonaProfile}``.
    """
    # Built-in defaults (the hardcoded dicts are now the fallback, not the only source).
    from .portal_spec_builder import _PERSONA_SECTIONS, _PERSONA_VALUE

    profiles: Dict[str, PersonaProfile] = {
        pid: PersonaProfile(frozenset(sections), dict(_PERSONA_VALUE.get(pid, {})))
        for pid, sections in _PERSONA_SECTIONS.items()
    }

    for p in (manifest_personas or []):
        render_id = p.get("portal_persona") or p.get("id")
        if not render_id:
            continue
        sections = p.get("sections")
        value = p.get("value")
        if sections is None and value is None:
            continue  # pure alias — keep the built-in default for this render id
        base = profiles.get(render_id)
        profiles[render_id] = PersonaProfile(
            sections=frozenset(sections) if sections is not None else (base.sections if base else frozenset()),
            value=dict(value) if value is not None else (base.value if base else {}),
        )
    return profiles
