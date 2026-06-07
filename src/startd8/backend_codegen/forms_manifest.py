"""Strict parse of the ``forms:`` section of ``views.yaml`` — per-entity post-submit behavior.

``views.yaml`` is the composite-view manifest (``view_codegen.manifest.parse_views``); its parser
ignores unknown **top-level** keys, so the per-entity form-behavior knob rides in a sibling
top-level ``forms:`` section (FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md FR-4) — two strict parsers over
disjoint sections of one file, mirroring how ``pages.yaml`` is shared by the pages generator and
the base-nav. This parser reads **only** ``forms:`` and tolerates a missing/empty ``views:`` list
(``parse_views`` requires ≥1 view; a forms-only manifest must still parse here).

.. code-block:: yaml

    views: [...]                        # view_codegen's section — untouched
    forms:                              # this parser's section
      Profile:  { on_create: detail }   # default — redirect to the new record's detail page
      Activity: { on_create: form }     # rapid sequential entry — back to a fresh form

Closed vocabulary, fail-loud (manifest house rules): unknown entity keys are deferred to render
time (the schema is not in scope here — callers pass ``known_entities``), unknown per-entity keys
and unknown ``on_create`` values raise immediately.
"""

from __future__ import annotations

from typing import Dict, Optional

import yaml

# The closed on_create vocabulary (FR-4). detail is the default everywhere a value is omitted.
ON_CREATE_VALUES = frozenset({"detail", "list", "form", "confirmation"})
ON_CREATE_DEFAULT = "detail"

_ENTRY_KEYS = {"on_create"}


def parse_forms(
    text: Optional[str], *, known_entities: frozenset = frozenset()
) -> Dict[str, str]:
    """Parse the ``forms:`` section of *text* (a full ``views.yaml``) → ``{entity: on_create}``.

    ``None``/empty text or an absent ``forms:`` section ⇒ ``{}`` (every entity gets
    :data:`ON_CREATE_DEFAULT`). ``known_entities`` (when given) gates entity refs, exactly like
    ``parse_views``. Anything malformed fails loud.
    """
    if text is None:
        return {}
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict):
        raise ValueError("views.yaml must be a YAML mapping")
    forms = data.get("forms") or {}
    if not isinstance(forms, dict):
        raise ValueError("views.yaml: `forms:` must be a mapping of entity -> settings")

    out: Dict[str, str] = {}
    for entity, cfg in forms.items():
        name = str(entity)
        if known_entities and name not in known_entities:
            raise ValueError(f"views.yaml: forms references unknown entity {name!r}")
        if not isinstance(cfg, dict):
            raise ValueError(f"views.yaml: forms entry {name!r} must be a mapping")
        unknown = set(cfg) - _ENTRY_KEYS
        if unknown:
            raise ValueError(
                f"views.yaml: forms entry {name!r} has unknown keys {sorted(unknown)}"
            )
        value = str(cfg.get("on_create", ON_CREATE_DEFAULT))
        if value not in ON_CREATE_VALUES:
            raise ValueError(
                f"views.yaml: forms entry {name!r} unknown on_create {value!r} "
                f"(allowed: {sorted(ON_CREATE_VALUES)})"
            )
        out[name] = value
    return out
