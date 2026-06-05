"""Strict parse of ``views.yaml`` — the composite-view manifest (REQ-VIEW-1/2).

Class-3 determinism: multi-entity views (dashboards, boards, polymorphic workspaces) are pure
relational logic — joins, counts, group-by, polymorphic resolution — derivable from the contract +
a declared manifest. ``views.yaml`` declares each view over a **closed archetype vocabulary**; the
manifest supplies only entities/fields, never logic. Unknown keys / unknown ``kind`` fail loud.

v1 archetypes: ``dashboard`` (aggregates + signal), ``board`` (group-by an ordered allow-list),
``workspace`` (polymorphic resolution + gap-flag). ``detail-compose`` / ``export-package`` are a
fast-follow (VIEW_GENERATOR_REQUIREMENTS.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import yaml

_KINDS = {"dashboard", "board", "workspace"}
_VIEW_KEYS = {
    "name", "kind", "route", "root", "aggregates", "signal", "group_by", "order", "polymorphic",
}
_AGG_KEYS = {"name", "of", "fk"}
_POLY_KEYS = {"of", "fk", "type_field", "id_field", "type_map"}


@dataclass(frozen=True)
class Aggregate:
    name: str
    of: str   # the related entity
    fk: str   # the FK field on *of* pointing at root.id


@dataclass(frozen=True)
class Polymorphic:
    of: str
    fk: str
    type_field: str
    id_field: str
    type_map: Tuple[Tuple[str, str], ...]  # (subjectType value -> entity name), declaration order


@dataclass(frozen=True)
class ViewSpec:
    name: str
    kind: str
    route: str
    root: str
    aggregates: Tuple[Aggregate, ...] = ()
    signal: str = ""                      # "<aggname> >= <int>"
    group_by: str = ""
    order: Tuple[str, ...] = ()
    polymorphic: Polymorphic | None = None

    @property
    def module(self) -> str:
        return self.name


def _signal_parts(expr: str) -> Tuple[str, int]:
    """Parse a ``<aggname> >= <int>`` signal into ``(aggname, threshold)``. Loud on anything else."""
    toks = expr.split()
    if len(toks) != 3 or toks[1] != ">=":
        raise ValueError(f"views.yaml: signal must be '<aggregate> >= <int>', got {expr!r}")
    try:
        return toks[0], int(toks[2])
    except ValueError:
        raise ValueError(f"views.yaml: signal threshold must be an int, got {toks[2]!r}")


def parse_views(text: str, *, known_entities: frozenset = frozenset()) -> Tuple[ViewSpec, ...]:
    """Parse + strictly validate ``views.yaml``. ``known_entities`` (if given) gates entity refs."""
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict) or "views" not in data:
        raise ValueError("views.yaml must be a mapping with a top-level `views:` list")

    def _check_entity(ent: str, where: str) -> None:
        if known_entities and ent not in known_entities:
            raise ValueError(f"views.yaml: {where} references unknown entity {ent!r}")

    out: List[ViewSpec] = []
    for i, entry in enumerate(data["views"] or []):
        if not isinstance(entry, dict):
            raise ValueError(f"views.yaml: view #{i} must be a mapping")
        unknown = set(entry) - _VIEW_KEYS
        if unknown:
            raise ValueError(f"views.yaml: view #{i} has unknown keys {sorted(unknown)}")
        for req in ("name", "kind", "route", "root"):
            if not entry.get(req):
                raise ValueError(f"views.yaml: view #{i} missing required `{req}`")
        kind = str(entry["kind"])
        if kind not in _KINDS:
            raise ValueError(f"views.yaml: view #{i} unknown kind {kind!r} (allowed: {sorted(_KINDS)})")
        root = str(entry["root"])
        _check_entity(root, f"view {entry['name']!r} root")

        aggregates: List[Aggregate] = []
        for a in entry.get("aggregates") or []:
            bad = set(a) - _AGG_KEYS
            if bad:
                raise ValueError(f"views.yaml: aggregate in {entry['name']!r} unknown keys {sorted(bad)}")
            _check_entity(str(a["of"]), f"aggregate {a.get('name')!r}")
            aggregates.append(Aggregate(name=str(a["name"]), of=str(a["of"]), fk=str(a["fk"])))

        poly = None
        if "polymorphic" in entry:
            p = entry["polymorphic"]
            bad = set(p) - _POLY_KEYS
            if bad:
                raise ValueError(f"views.yaml: polymorphic in {entry['name']!r} unknown keys {sorted(bad)}")
            tmap = tuple((str(k), str(v)) for k, v in (p.get("type_map") or {}).items())
            for _, ent in tmap:
                _check_entity(ent, f"polymorphic type_map in {entry['name']!r}")
            _check_entity(str(p["of"]), f"polymorphic source in {entry['name']!r}")
            poly = Polymorphic(
                of=str(p["of"]), fk=str(p["fk"]),
                type_field=str(p["type_field"]), id_field=str(p["id_field"]), type_map=tmap,
            )

        if entry.get("signal"):
            agg_names = {a.name for a in aggregates}
            sig_name, _ = _signal_parts(str(entry["signal"]))
            if sig_name not in agg_names:
                raise ValueError(
                    f"views.yaml: {entry['name']!r} signal references unknown aggregate {sig_name!r}"
                )

        out.append(ViewSpec(
            name=str(entry["name"]), kind=kind, route=str(entry["route"]), root=root,
            aggregates=tuple(aggregates), signal=str(entry.get("signal", "")),
            group_by=str(entry.get("group_by", "")),
            order=tuple(str(s) for s in (entry.get("order") or ())),
            polymorphic=poly,
        ))
    if not out:
        raise ValueError("views.yaml declares no views")
    names = [v.name for v in out]
    if len(set(names)) != len(names):
        raise ValueError(f"views.yaml has duplicate view names: {names}")
    return tuple(out)
