"""Strict parse of ``views.yaml`` — the composite-view manifest (REQ-VIEW-1/2).

Class-3 determinism: multi-entity views (dashboards, boards, polymorphic workspaces) are pure
relational logic — joins, counts, group-by, polymorphic resolution — derivable from the contract +
a declared manifest. ``views.yaml`` declares each view over a **closed archetype vocabulary**; the
manifest supplies only entities/fields, never logic. Unknown keys / unknown ``kind`` fail loud.

v1 archetypes: ``dashboard`` (aggregates + signal), ``board`` (group-by an ordered allow-list),
``workspace`` (polymorphic resolution + gap-flag). ``detail-compose`` (root + resolved relations as
panels + conditional panels) and ``export-package`` (root + relations -> lossless package + named MD
layout) are the fast-follow (VIEW_GENERATOR_REQUIREMENTS.md).

``export-package`` additionally takes ``scope: row | model`` (default ``row`` — the existing per-row
package). ``scope: model`` (AR-3, FR-10 whole-model export) serves the WHOLE model through the
generated ``app/export.py`` serialization layer: ``route`` becomes the optional base path (default
``/export`` -> ``/export/markdown`` + ``/export/json``), and ``root``/``relations`` are forbidden.

``detail-compose`` takes the same ``scope`` grammar (AR-1, FR-8 whole-model compose — the Value
Map): ``scope: model`` iterates ALL roots (every root + resolved relations on ONE page, unlinked
roots flagged, never dropped), so the route takes no ``{id}`` — it derives ``/<kebab(view name)>``
per authoring contract §2.3 (optional explicit ``route:`` override; ``{id}`` in it fails loud).

``computed-panel`` (AR-2, FR-9 — the completeness page) binds a **generated compute function** to
a score+nudges panel at a declared route. ``compute`` names the binding from an OPEN, registrable
vocabulary (v1: ``completeness`` — ``app/completeness.py``'s ``compute_completeness``, fed live
per-entity row counts). The vocabulary's single source of truth is ``renderers._COMPUTE_RENDERERS``
(name -> renderer fn); adding a binding there (e.g. a ``funnel`` metrics binding) automatically
opens it here, with no duplicate allow-list to keep in sync.
Route derives ``/<kebab(view name)>``. Entity-shaped keys (``root``/``relations``/``aggregates``/…)
are wrong-kind on a computed-panel and fail loud.

``import-flow`` (AR-4, FR-10 restore — "local-only isn't a dead end") is the round-trip partner of
the model-scoped export-package, consuming its JSON payload (entity -> field-faithful row dicts):
GET ``<route>`` (upload form) -> POST ``<route>/validate`` (parse + check entity names and field
shapes against the contract; reports errors WITHOUT mutating) -> POST ``<route>/restore`` (the
destructive step — refused without an explicit ``confirm`` field; UPSERT by primary key with the
retired ``import_routes.py`` merge semantics: idempotent, never deletes). ``route`` is the optional
base path (default ``/import``). It takes no entity keys at all — those fail loud.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import yaml

_KINDS = {
    "dashboard", "board", "workspace", "detail-compose", "export-package", "computed-panel",
    "import-flow",
}
# `scope` is valid on export-package (AR-3: whole-model export) and detail-compose (AR-1:
# whole-model compose — the Value Map). `model` = iterate/serve the WHOLE model, not one row.
_SCOPES = {"row", "model"}
_SCOPED_KINDS = {"export-package", "detail-compose"}
# computed-panel compute bindings (AR-2): an OPEN, registrable vocabulary of GENERATED compute
# functions. The canonical registry is `renderers._COMPUTE_RENDERERS` (name -> renderer fn) — the
# single source of truth for BOTH what parses here and what renders. We read it via a deferred
# import (`renderers` depends on `manifest`, so a module-level import would cycle), guaranteeing the
# parse-time allow-list and the render dispatch can never drift. To add a binding, register one
# entry in that dict — no edit here. v1 ships only `completeness` (app/completeness.py).
# Keys a computed-panel may carry — entity-shaped keys are wrong-kind there and fail loud.
_COMPUTED_PANEL_KEYS = {"name", "kind", "route", "compute"}
# Keys an import-flow may carry — it is contract-driven (app/export.py), so no entity keys at all.
_IMPORT_FLOW_KEYS = {"name", "kind", "route"}
_VIEW_KEYS = {
    "name", "kind", "route", "root", "aggregates", "signal", "group_by", "order", "polymorphic",
    "relations", "panels", "gap", "scope", "compute",
}
_AGG_KEYS = {"name", "of", "fk"}
_POLY_KEYS = {"of", "fk", "type_field", "id_field", "type_map"}
_REL_KEYS = {"name", "from", "fk"}
_PANEL_KEYS = {"name", "fields", "show_when"}
_GAP_KEYS = {"needs_from"}
_SHOW_WHEN = {"any_set"}


@dataclass(frozen=True)
class Aggregate:
    name: str
    of: str   # the related entity
    fk: str   # the FK field on *of* pointing at root.id


@dataclass(frozen=True)
class Relation:
    name: str   # the key under which resolved rows are returned
    frm: str    # the related entity (manifest key: ``from``)
    fk: str     # the FK field on *frm* pointing at root.id


@dataclass(frozen=True)
class Panel:
    name: str
    fields: Tuple[str, ...]
    show_when: str  # currently only ``any_set``


@dataclass(frozen=True)
class Gap:
    needs_from: Tuple[str, ...]  # root text fields, newline-split into needs


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
    root: str   # "" for model-scoped export-packages / computed-panels (no single root row)
    scope: str = "row"                    # export-package/detail-compose: "row" | "model" (AR-3/AR-1)
    compute: str = ""                     # computed-panel only: the compute binding (AR-2)
    aggregates: Tuple[Aggregate, ...] = ()
    signal: str = ""                      # "<aggname> >= <int>"
    group_by: str = ""
    order: Tuple[str, ...] = ()
    polymorphic: Polymorphic | None = None
    relations: Tuple[Relation, ...] = ()
    panels: Tuple[Panel, ...] = ()
    gap: Gap | None = None

    @property
    def module(self) -> str:
        return self.name


def _compute_bindings() -> frozenset:
    """The registered compute-binding vocabulary, read from the canonical renderer registry.

    Deferred import (``renderers`` imports ``manifest``) so the allow-list this validator enforces
    is literally the set of renderers that exist — the single source of truth, never a duplicate.
    """
    from .renderers import compute_binding_names

    return compute_binding_names()


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
        for req in ("name", "kind"):
            if not entry.get(req):
                raise ValueError(f"views.yaml: view #{i} missing required `{req}`")
        kind = str(entry["kind"])
        if kind not in _KINDS:
            raise ValueError(f"views.yaml: view #{i} unknown kind {kind!r} (allowed: {sorted(_KINDS)})")

        scope = str(entry.get("scope", "row"))
        if scope not in _SCOPES:
            raise ValueError(
                f"views.yaml: view #{i} unknown scope {scope!r} (allowed: {sorted(_SCOPES)})"
            )
        if "scope" in entry and kind not in _SCOPED_KINDS:
            raise ValueError(
                f"views.yaml: view #{i} `scope` is only valid on kinds "
                f"{sorted(_SCOPED_KINDS)}, not {kind!r}"
            )
        if "compute" in entry and kind != "computed-panel":
            raise ValueError(
                f"views.yaml: view #{i} `compute` is only valid on kind 'computed-panel', not {kind!r}"
            )
        compute = ""
        model_export = kind == "export-package" and scope == "model"
        model_compose = kind == "detail-compose" and scope == "model"
        if kind == "import-flow":
            # AR-4 (FR-10 restore): contract-driven (app/export.py's ENTITY_ORDER/FIELDS), so it
            # declares no entities — route is the optional base path for form/validate/restore.
            wrong_kind = set(entry) - _IMPORT_FLOW_KEYS
            if wrong_kind:
                raise ValueError(
                    f"views.yaml: view #{i} keys {sorted(wrong_kind)} are not valid on kind "
                    "'import-flow' (the flow is driven by the export contract, not declared entities)"
                )
            root = ""
            route = str(entry.get("route") or "/import")
        elif kind == "computed-panel":
            # AR-2 (FR-9): a compute binding -> score+nudges panel. No entity keys at all —
            # the data shape is the compute function's contract, not a root + relations.
            wrong_kind = set(entry) - _COMPUTED_PANEL_KEYS
            if wrong_kind:
                raise ValueError(
                    f"views.yaml: view #{i} keys {sorted(wrong_kind)} are not valid on kind "
                    "'computed-panel' (it binds a compute function, not entities)"
                )
            compute = str(entry.get("compute") or "")
            if not compute:
                raise ValueError(f"views.yaml: view #{i} missing required `compute`")
            if compute not in _compute_bindings():
                raise ValueError(
                    f"views.yaml: view #{i} unknown compute binding {compute!r} "
                    f"(allowed: {sorted(_compute_bindings())})"
                )
            root = ""
            route = str(entry.get("route") or "/" + str(entry["name"]).replace("_", "-"))
        elif model_export:
            # Whole-model export (AR-3): no root row — root/relations are meaningless and forbidden;
            # route is the optional base path (authoring-contract default: /export).
            for forbidden in ("root", "relations"):
                if entry.get(forbidden):
                    raise ValueError(
                        f"views.yaml: view #{i} `{forbidden}` is not allowed with `scope: model` "
                        "(a model-scoped export-package serves the WHOLE model)"
                    )
            root = ""
            route = str(entry.get("route") or "/export")
        elif model_compose:
            # Whole-model compose (AR-1, FR-8): EVERY root + resolved relations on one page, so the
            # route takes no {id} — it derives /<kebab(view name)> (authoring contract §2.3), with
            # an optional explicit `route:` override. `root` (the iterated entity) stays required.
            if not entry.get("root"):
                raise ValueError(f"views.yaml: view #{i} missing required `root`")
            root = str(entry["root"])
            _check_entity(root, f"view {entry['name']!r} root")
            route = str(entry.get("route") or "/" + str(entry["name"]).replace("_", "-"))
            if "{" in route:
                raise ValueError(
                    f"views.yaml: view #{i} route {route!r} must not take path params with "
                    "`scope: model` (a model-scoped detail-compose iterates ALL roots)"
                )
        else:
            for req in ("route", "root"):
                if not entry.get(req):
                    raise ValueError(f"views.yaml: view #{i} missing required `{req}`")
            root = str(entry["root"])
            route = str(entry["route"])
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

        relations: List[Relation] = []
        for r in entry.get("relations") or []:
            bad = set(r) - _REL_KEYS
            if bad:
                raise ValueError(f"views.yaml: relation in {entry['name']!r} unknown keys {sorted(bad)}")
            for req in ("name", "from", "fk"):
                if not r.get(req):
                    raise ValueError(f"views.yaml: relation in {entry['name']!r} missing `{req}`")
            _check_entity(str(r["from"]), f"relation {r.get('name')!r} in {entry['name']!r}")
            relations.append(Relation(name=str(r["name"]), frm=str(r["from"]), fk=str(r["fk"])))

        panels: List[Panel] = []
        for pn in entry.get("panels") or []:
            bad = set(pn) - _PANEL_KEYS
            if bad:
                raise ValueError(f"views.yaml: panel in {entry['name']!r} unknown keys {sorted(bad)}")
            for req in ("name", "fields", "show_when"):
                if not pn.get(req):
                    raise ValueError(f"views.yaml: panel in {entry['name']!r} missing `{req}`")
            sw = str(pn["show_when"])
            if sw not in _SHOW_WHEN:
                raise ValueError(
                    f"views.yaml: panel {pn['name']!r} in {entry['name']!r} unknown show_when {sw!r} "
                    f"(allowed: {sorted(_SHOW_WHEN)})"
                )
            panels.append(Panel(
                name=str(pn["name"]), fields=tuple(str(f) for f in pn["fields"]), show_when=sw,
            ))

        gap = None
        if "gap" in entry:
            g = entry["gap"]
            bad = set(g) - _GAP_KEYS
            if bad:
                raise ValueError(f"views.yaml: gap in {entry['name']!r} unknown keys {sorted(bad)}")
            if not g.get("needs_from"):
                raise ValueError(f"views.yaml: gap in {entry['name']!r} missing `needs_from`")
            gap = Gap(needs_from=tuple(str(s) for s in g["needs_from"]))

        if entry.get("signal"):
            agg_names = {a.name for a in aggregates}
            sig_name, _ = _signal_parts(str(entry["signal"]))
            if sig_name not in agg_names:
                raise ValueError(
                    f"views.yaml: {entry['name']!r} signal references unknown aggregate {sig_name!r}"
                )

        out.append(ViewSpec(
            name=str(entry["name"]), kind=kind, route=route, root=root, scope=scope,
            compute=compute,
            aggregates=tuple(aggregates), signal=str(entry.get("signal", "")),
            group_by=str(entry.get("group_by", "")),
            order=tuple(str(s) for s in (entry.get("order") or ())),
            polymorphic=poly,
            relations=tuple(relations), panels=tuple(panels), gap=gap,
        ))
    if not out:
        raise ValueError("views.yaml declares no views")
    names = [v.name for v in out]
    if len(set(names)) != len(names):
        raise ValueError(f"views.yaml has duplicate view names: {names}")
    return tuple(out)
