"""``editors:`` — the bulk child-field editor declaration (FR-ED-1/2), a views.yaml section.

Coexists with ``views:`` / ``forms:`` / ``filters:`` / ``flows:`` in views.yaml; this reads only
``editors:``. Each editor edits ONE field across a parent's filtered, grouped children in one form/POST
(with reset-to-default). Mapping form (name → spec), mirroring the brief + the ``filters:`` precedent.
Strict: unknown keys / duplicate names / missing required keys → loud at parse. Field/entity existence is
validated at render (``editor_generator._validate_editor``), where the schema is available.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import yaml

# Required + optional keys. ``filter``/``group_by``/``order_by``/``default_value``/``label`` optional;
# ``reset_to_default`` defaults True (the reset behaviour is the point of the archetype).
_REQUIRED = ("parent", "child", "fk", "edit_field", "route")
_OPTIONAL = ("filter", "group_by", "order_by", "reset_to_default", "default_value", "label")
_KEYS = frozenset(_REQUIRED + _OPTIONAL)


@dataclass(frozen=True)
class EditorSpec:
    name: str
    parent: str
    child: str
    fk: str
    edit_field: str
    route: str
    filter: Tuple[Tuple[str, object], ...] = ()   # own-column equality map (col, value) pairs
    group_by: str = ""
    order_by: str = ""
    reset_to_default: bool = True
    default_value: str = ""                        # bare resolver fn name; "" = omitted (zero-seam) mode
    label: str = ""

    @property
    def filter_map(self) -> Dict[str, object]:
        return dict(self.filter)


def parse_editors(
    views_text: Optional[str], *, known_entities: frozenset = frozenset()
) -> Tuple[EditorSpec, ...]:
    """Parse the ``editors:`` section of views.yaml → EditorSpecs. Tolerant of absence."""
    data = yaml.safe_load(views_text or "") or {}
    if not isinstance(data, dict) or "editors" not in data:
        return ()
    raw = data["editors"] or {}
    if not isinstance(raw, dict):
        raise ValueError("views.yaml: `editors` must be a mapping of name -> spec")
    out = []
    seen = set()
    for name, spec in raw.items():
        name = str(name)
        if name in seen:
            raise ValueError(f"views.yaml: duplicate editor name {name!r}")
        seen.add(name)
        if not isinstance(spec, dict):
            raise ValueError(f"views.yaml: editor {name!r} must be a mapping")
        unknown = set(spec) - _KEYS
        if unknown:
            raise ValueError(f"views.yaml: editor {name!r} has unknown keys {sorted(unknown)}")
        for req in _REQUIRED:
            if not spec.get(req):
                raise ValueError(f"views.yaml: editor {name!r} missing required `{req}`")
        flt = spec.get("filter") or {}
        if not isinstance(flt, dict):
            raise ValueError(f"views.yaml: editor {name!r} `filter` must be a mapping of column -> value")
        if known_entities:
            for ent_key in ("parent", "child"):
                if spec[ent_key] not in known_entities:
                    raise ValueError(
                        f"views.yaml: editor {name!r} references unknown entity "
                        f"{spec[ent_key]!r} (in `{ent_key}`)"
                    )
        out.append(
            EditorSpec(
                name=name,
                parent=str(spec["parent"]),
                child=str(spec["child"]),
                fk=str(spec["fk"]),
                edit_field=str(spec["edit_field"]),
                route=str(spec["route"]),
                filter=tuple(sorted((str(k), v) for k, v in flt.items())),
                group_by=str(spec.get("group_by") or ""),
                order_by=str(spec.get("order_by") or ""),
                reset_to_default=bool(spec.get("reset_to_default", True)),
                default_value=str(spec.get("default_value") or ""),
                label=str(spec.get("label") or name),
            )
        )
    return tuple(out)
