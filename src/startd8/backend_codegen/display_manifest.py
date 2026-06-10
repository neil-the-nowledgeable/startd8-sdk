"""``display.yaml`` — the presentation **structure** layer (FR-DM-1): per-entity list columns/labels/
order, detail sections, row ``label_field``, and composite-view field bindings.

Carries *bindings*, not copy (view words live in #7 / ``views.yaml prose:``). Strict-parsed against the
contract: unknown keys / entities / field refs / formats fail loud. The generators consume an
``EntityDisplay`` to stop leaking system ids as labels; absence ⇒ today's behavior (opt-in).
"""

from __future__ import annotations

from dataclasses import dataclass, field as _f
from typing import Dict, Optional, Tuple

import yaml

from ..languages.prisma_parser import PrismaSchema

_FORMATS = {"", "badge", "date", "link"}        # + "truncate:N" (prefix-checked)
_COL_KEYS = {"field", "label", "format"}
_SECTION_KEYS = {"title", "fields"}
_ENTITY_KEYS = {"title", "subtitle", "label_field", "columns", "sections", "hidden_fields", "default_sort"}
_REL_KEYS = {"name", "via_fk", "label_field"}
_VIEW_KEYS = {"root_label_field", "relations"}


@dataclass(frozen=True)
class ColumnDisplay:
    field: str
    label: str = ""
    format: str = ""


@dataclass(frozen=True)
class DetailSection:
    title: str
    fields: Tuple[str, ...]


@dataclass(frozen=True)
class EntityDisplay:
    entity: str
    title: str = ""
    subtitle: str = ""
    label_field: str = ""
    columns: Tuple[ColumnDisplay, ...] = ()
    sections: Tuple[DetailSection, ...] = ()
    hidden_fields: Tuple[str, ...] = ()
    default_sort: Optional[Tuple[str, str]] = None


@dataclass(frozen=True)
class RelationDisplay:
    name: str
    via_fk: str = ""
    label_field: str = ""


@dataclass(frozen=True)
class ViewDisplay:
    view: str
    root_label_field: str = ""
    relations: Tuple[RelationDisplay, ...] = ()


def _check_format(entity: str, fmt: str) -> None:
    if fmt in _FORMATS or fmt.startswith("truncate:"):
        return
    raise ValueError(f"display.yaml: {entity} column format {fmt!r} not in {sorted(_FORMATS)} | truncate:N")


def parse_display(
    text: Optional[str], schema: PrismaSchema
) -> Tuple[Dict[str, EntityDisplay], Dict[str, ViewDisplay]]:
    """Parse ``display.yaml`` → ({entity: EntityDisplay}, {view: ViewDisplay}). Tolerant of absence."""
    data = yaml.safe_load(text or "") or {}
    if not data:
        return {}, {}
    if not isinstance(data, dict) or set(data) - {"entities", "views"}:
        raise ValueError("display.yaml must be a mapping with `entities:` and/or `views:`")

    entities: Dict[str, EntityDisplay] = {}
    for name, spec in (data.get("entities") or {}).items():
        model = schema.model(name)
        if model is None:
            raise ValueError(f"display.yaml: unknown entity {name!r}")
        cols = {f.name for f in model.fields}
        if not isinstance(spec, dict) or set(spec) - _ENTITY_KEYS:
            raise ValueError(f"display.yaml: entities[{name}] has unknown keys {sorted(set(spec) - _ENTITY_KEYS)}")

        def _field(fname: str) -> str:
            if fname not in cols:
                raise ValueError(f"display.yaml: entities[{name}] references unknown field {fname!r}")
            return fname

        columns = []
        for c in spec.get("columns", ()) or ():
            if not isinstance(c, dict) or set(c) - _COL_KEYS or "field" not in c:
                raise ValueError(f"display.yaml: entities[{name}] column must be a mapping with `field`")
            _check_format(name, str(c.get("format", "")))
            columns.append(ColumnDisplay(_field(str(c["field"])), str(c.get("label", "")), str(c.get("format", ""))))
        sections = []
        for s in spec.get("sections", ()) or ():
            if not isinstance(s, dict) or set(s) - _SECTION_KEYS or "title" not in s:
                raise ValueError(f"display.yaml: entities[{name}] section must be a mapping with `title`")
            sections.append(DetailSection(str(s["title"]), tuple(_field(str(x)) for x in s.get("fields", ()) or ())))
        ds = spec.get("default_sort")
        entities[name] = EntityDisplay(
            entity=name, title=str(spec.get("title", "")), subtitle=str(spec.get("subtitle", "")),
            label_field=_field(str(spec["label_field"])) if spec.get("label_field") else "",
            columns=tuple(columns), sections=tuple(sections),
            hidden_fields=tuple(_field(str(x)) for x in spec.get("hidden_fields", ()) or ()),
            default_sort=(str(ds[0]), str(ds[1])) if isinstance(ds, (list, tuple)) and len(ds) == 2 else None,
        )

    views: Dict[str, ViewDisplay] = {}
    for vname, spec in (data.get("views") or {}).items():
        if not isinstance(spec, dict) or set(spec) - _VIEW_KEYS:
            raise ValueError(f"display.yaml: views[{vname}] has unknown keys")
        rels = []
        for r in spec.get("relations", ()) or ():
            if not isinstance(r, dict) or set(r) - _REL_KEYS or "name" not in r:
                raise ValueError(f"display.yaml: views[{vname}] relation must be a mapping with `name`")
            rels.append(RelationDisplay(str(r["name"]), str(r.get("via_fk", "")), str(r.get("label_field", ""))))
        views[vname] = ViewDisplay(vname, str(spec.get("root_label_field", "")), tuple(rels))

    return entities, views


def display_hash_payload(entities: Dict[str, EntityDisplay]) -> str:
    """OQ-A: a stable hash payload of the BINDING structure with inline copy strings stripped
    (title/subtitle/column label), so a copy-only edit doesn't trip drift `--check`."""
    import json
    norm = {
        name: {
            "label_field": ed.label_field,
            "columns": [(c.field, c.format) for c in ed.columns],      # label (copy) excluded
            "sections": [list(s.fields) for s in ed.sections],         # title (copy) excluded
            "hidden_fields": list(ed.hidden_fields),
            "default_sort": list(ed.default_sort) if ed.default_sort else None,
        }
        for name, ed in sorted(entities.items())
    }
    return json.dumps(norm, sort_keys=True)
