"""Deterministic composite-view emitters (class-3 determinism — REQ-VIEW-3).

Pure, no-LLM projection of ``views.yaml`` + the contract into owned **multi-entity** views that
``backend_codegen`` (single-entity CRUD) does not emit: a data module per view (the resolver/
aggregator/grouper — pure SQLModel ``select`` + Python), a router, minimal templates over the owned
``base.html``, and the rung-4 view tests that prove resolution/aggregation/grouping correctness
(incl. the dangling-polymorphic-ref-flagged-not-crashed invariant — RUN-029/032).

Two-hash drift: a view file is stale if **either** the schema or ``views.yaml`` changed.
"""

from __future__ import annotations

from typing import List, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from .manifest import ViewSpec, _signal_parts, parse_views

_TEST_SHIM = (
    "import sys\n"
    "from pathlib import Path\n\n"
    "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
)


def _header(schema_sha: str, views_sha: str, kind: str) -> str:
    """Two-input (schema + views.yaml) ``#`` provenance header; stale if either hash changes."""
    return (
        "# GENERATED from prisma/schema.prisma (+ views.yaml) — do not edit by hand; "
        "regenerate via `startd8 generate views`.\n"
        f"# startd8-artifact: {kind}\n"
        "# Source of truth: the Prisma schema and the views manifest.\n"
        f"# schema-sha256: {schema_sha}\n"
        f"# views-sha256: {views_sha}"
    )


def _module_path(v: ViewSpec) -> str:
    return f"app/views/{v.module}.py"


# --------------------------------------------------------------------------- #
# Per-archetype data modules (the owned relational logic)
# --------------------------------------------------------------------------- #

def _render_dashboard(v: ViewSpec) -> str:
    agg_entities = sorted({a.of for a in v.aggregates})
    imports = ", ".join([v.root] + [e for e in agg_entities if e != v.root])
    lines = [
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {imports}", "", "",
        f"def {v.module}_data(session: Session) -> list[dict[str, Any]]:",
        f'    """Dashboard over {v.root}: per-row aggregate counts + readiness signal."""',
        "    out: list[dict[str, Any]] = []",
        f"    for root in session.exec(select({v.root})).all():",
        "        row: dict[str, Any] = {\"root\": root}",
    ]
    for a in v.aggregates:
        lines.append(
            f"        row[{a.name!r}] = len(session.exec("
            f"select({a.of}).where({a.of}.{a.fk} == root.id)).all())"
        )
    if v.signal:
        name, threshold = _signal_parts(v.signal)
        lines.append(f"        row['signal'] = (row[{name!r}] >= {threshold})")
    lines += [
        "        out.append(row)",
        "    return out", "",
        f"__all__ = [{(v.module + '_data')!r}]", "",
    ]
    return "\n".join(lines)


def _render_board(v: ViewSpec) -> str:
    order_lit = "[" + ", ".join(f'"{s}"' for s in v.order) + "]"
    return "\n".join([
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {v.root}", "",
        f"_ORDER = {order_lit}", "", "",
        f"def {v.module}_data(session: Session) -> list[tuple[str, list[Any]]]:",
        f'    """Board: group {v.root} by `{v.group_by}` in the owned order; '
        'unknown statuses kept (no row lost), appended last."""',
        "    cols: dict[str, list[Any]] = {}",
        f"    for root in session.exec(select({v.root})).all():",
        f"        cols.setdefault(getattr(root, {v.group_by!r}), []).append(root)",
        "    ordered = [(s, cols.pop(s, [])) for s in _ORDER]",
        "    ordered += [(s, rows) for s, rows in cols.items()]  # statuses outside the allow-list",
        "    return ordered", "",
        f"__all__ = [{(v.module + '_data')!r}]", "",
    ])


def _render_workspace(v: ViewSpec) -> str:
    p = v.polymorphic
    assert p is not None
    entities = sorted({v.root, p.of} | {ent for _, ent in p.type_map})
    imports = ", ".join(entities)
    map_lit = "{" + ", ".join(f'"{k}": {ent}' for k, ent in p.type_map) + "}"
    lines = [
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {imports}", "",
        f"_TYPE_MAP = {map_lit}", "", "",
        f"def {v.module}_data(session: Session, root_id: str) -> dict[str, Any]:",
        f'    """Workspace: resolve {p.of}\'s polymorphic ({p.type_field} -> entity, {p.id_field} -> row)'
        ' references for one {root}; a dangling ref is FLAGGED, not crashed (RUN-029)."""'.format(root=v.root),
        f"    root = session.get({v.root}, root_id)",
        "    resolved: list[dict[str, Any]] = []",
        f"    for m in session.exec(select({p.of}).where({p.of}.{p.fk} == root_id)).all():",
        f"        model = _TYPE_MAP.get(getattr(m, {p.type_field!r}))",
        f"        entity = session.get(model, getattr(m, {p.id_field!r})) if model is not None else None",
        '        resolved.append({"match": m, "entity": entity, "dangling": entity is None})',
    ]
    if v.gap is not None:
        needs_lit = "[" + ", ".join(repr(f) for f in v.gap.needs_from) + "]"
        lines += [
            "    needs: list[str] = []",
            f"    for _field in {needs_lit}:",
            "        _raw = getattr(root, _field, None) or \"\"",
            "        needs += [n.strip() for n in str(_raw).split(chr(10)) if n.strip()]",
            "    # union of declared needs MINUS covered (a need is covered when >=1 match resolved)",
            "    _covered = sum(1 for r in resolved if not r['dangling'])",
            "    _uniq: list[str] = []",
            "    for n in needs:",
            "        if n not in _uniq:",
            "            _uniq.append(n)",
            "    gaps = _uniq[_covered:] if _covered < len(_uniq) else []",
            '    return {"root": root, "resolved": resolved, "gaps": gaps}',
        ]
    else:
        lines.append('    return {"root": root, "resolved": resolved}')
    lines += ["", f"__all__ = [{(v.module + '_data')!r}]", ""]
    return "\n".join(lines)


def _render_detail_compose_model(v: ViewSpec) -> str:
    """Model-scoped detail-compose (AR-1 / FR-8): EVERY root + resolved relations on ONE page.

    The whole-model compose behind the Value Map: iterate ALL roots, resolve each declared
    relation per root, compute conditional panels per root, and flag a root with no resolved
    relation rows as unlinked (the "not yet linked" empty-ish state) — never drop it. The route
    takes no ``{id}``; bare GET serves 200 on empty AND populated DBs (empty -> empty list ->
    the template's meaningful empty state).
    """
    entities = sorted({v.root} | {r.frm for r in v.relations})
    imports = ", ".join(entities)
    lines = [
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {imports}", "", "",
        f"def {v.module}_data(session: Session) -> list[dict[str, Any]]:",
        f'    """Whole-model compose: every {v.root} + resolved relations; unlinked roots flagged,'
        ' never dropped."""',
        "    out: list[dict[str, Any]] = []",
        f"    for root in session.exec(select({v.root})).all():",
        '        item: dict[str, Any] = {"root": root}',
    ]
    for r in v.relations:
        lines.append(
            f"        item[{r.name!r}] = session.exec("
            f"select({r.frm}).where({r.frm}.{r.fk} == root.id)).all()"
        )
    if v.panels:
        lines.append("        panels: dict[str, bool] = {}")
        for pn in v.panels:
            fields_lit = "(" + ", ".join(repr(f) for f in pn.fields) + (",)" if len(pn.fields) == 1 else ")")
            lines.append(
                f"        panels[{pn.name!r}] = "
                f"any(getattr(root, _f, None) not in (None, \"\") for _f in {fields_lit})"
            )
        lines.append('        item["panels"] = panels')
    if v.relations:
        linked_expr = " or ".join(f"item[{r.name!r}]" for r in v.relations)
        lines.append(f'        item["linked"] = bool({linked_expr})  # FR-8: "not yet linked" flag')
    lines += [
        "        out.append(item)",
        "    return out", "",
        f"__all__ = [{(v.module + '_data')!r}]", "",
    ]
    return "\n".join(lines)


def _render_detail_compose(v: ViewSpec) -> str:
    if v.scope == "model":
        return _render_detail_compose_model(v)
    entities = sorted({v.root} | {r.frm for r in v.relations})
    imports = ", ".join(entities)
    lines = [
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {imports}", "", "",
        f"def {v.module}_data(session: Session, root_id: str) -> dict[str, Any]:",
        f'    """Detail-compose: one {v.root} root + resolved relations as panels + conditional panels'
        ' (any_set -> shown only when >=1 declared field is non-empty)."""',
        f"    root = session.get({v.root}, root_id)",
        '    out: dict[str, Any] = {"root": root}',
    ]
    for r in v.relations:
        lines.append(
            f"    out[{r.name!r}] = session.exec("
            f"select({r.frm}).where({r.frm}.{r.fk} == root_id)).all()"
        )
    lines.append("    panels: dict[str, bool] = {}")
    for pn in v.panels:
        fields_lit = "(" + ", ".join(repr(f) for f in pn.fields) + (",)" if len(pn.fields) == 1 else ")")
        # show_when == any_set: shown only if >=1 field is non-empty
        lines.append(
            f"    panels[{pn.name!r}] = "
            f"any(getattr(root, _f, None) not in (None, \"\") for _f in {fields_lit})"
        )
    lines += [
        '    out["panels"] = panels',
        "    return out",
        "", "",
        f"def {v.module}_roots(session: Session) -> list[Any]:",
        f'    """All {v.root} rows — the bare-route pick-an-item index (AR-1)."""',
        f"    return session.exec(select({v.root})).all()",
        "",
        f"__all__ = [{(v.module + '_data')!r}, {(v.module + '_roots')!r}]", "",
    ]
    return "\n".join(lines)


def _render_computed_panel_completeness(v: ViewSpec) -> str:
    """The ``completeness`` compute binding (AR-2 / FR-9): live counts -> score + nudges.

    REUSES the generated ``app/completeness.py`` (``ENTITIES`` + ``compute_completeness``) — the
    scoring rule lives there (presence or manifest-weighted), never duplicated here. This module
    only gathers the ``present`` dict (per-entity row counts) the compute function takes.
    """
    return "\n".join([
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        "import app.tables as _tables",
        "from app.completeness import ENTITIES, compute_completeness", "", "",
        f"def {v.module}_data(session: Session) -> dict[str, Any]:",
        '    """Live per-entity row counts -> the generated compute_completeness -> score + nudges',
        '    (FR-9: guidance, never a gate)."""',
        "    present: dict[str, int] = {}",
        "    for entity in ENTITIES:",
        "        model = getattr(_tables, entity)",
        "        present[entity] = len(session.exec(select(model)).all())",
        "    result = compute_completeness(present)",
        '    return {"score": result.score, "nudges": list(result.nudges), "present": present}', "",
        f"__all__ = [{(v.module + '_data')!r}]", "",
    ])


# compute binding -> module renderer (the AR-2 extension point; mirrors manifest._COMPUTE_BINDINGS).
_COMPUTE_RENDERERS = {
    "completeness": _render_computed_panel_completeness,
}


def _render_computed_panel(v: ViewSpec) -> str:
    return _COMPUTE_RENDERERS[v.compute](v)


def _pk_fields(schema, entity: str) -> Tuple[str, ...]:
    """The entity's primary-key field(s): ``@id`` scalars, else the ``@@id([...])`` compound."""
    ids = tuple(f.name for f in schema.scalar_fields(entity) if f.is_id)
    if ids:
        return ids
    for attr in schema.models[entity].block_attributes:
        if attr.startswith("@@id"):
            inner = attr[attr.find("[") + 1:attr.find("]")]
            return tuple(s.strip() for s in inner.split(",") if s.strip())
    return ()


def _render_import_flow(v: ViewSpec, schema) -> str:
    """Import-flow module (AR-4 / FR-10 restore): validate + restore over the export contract.

    The round-trip partner of the model-scoped export-package — consumes its exact JSON payload
    (entity -> field-faithful row dicts). Validation never touches the DB; restore UPSERTS by
    primary key (the retired ``import_routes.py`` merge semantics: existing keys update in place,
    new keys insert, re-importing the same file is idempotent, nothing is ever deleted — replace
    is the user clearing first). Datetime columns are exported as strings (``to_json``'s
    ``default=str``) but SQLModel table models do not coerce on construction, so the baked
    ``_DATETIME_FIELDS`` map (from the contract, not hardcoded names) converts them back.
    """
    dt_entries = []
    pk_entries = []
    for name in schema.models:
        dts = tuple(f.name for f in schema.scalar_fields(name) if f.type == "DateTime")
        if dts:
            dt_entries.append(f"    {name!r}: (" + ", ".join(repr(d) for d in dts) + ("," if len(dts) == 1 else "") + "),")
        pk = _pk_fields(schema, name)
        if pk:
            pk_entries.append(f"    {name!r}: (" + ", ".join(repr(p) for p in pk) + ("," if len(pk) == 1 else "") + "),")
    dt_lit = "{\n" + "\n".join(dt_entries) + "\n}" if dt_entries else "{}"
    pk_lit = "{\n" + "\n".join(pk_entries) + "\n}" if pk_entries else "{}"
    m = v.module
    return "\n".join([
        "from __future__ import annotations", "",
        "from datetime import datetime",
        "from typing import Any", "",
        "from sqlmodel import Session", "",
        "import app.tables as _tables",
        "from app.export import ENTITY_ORDER, FIELDS", "",
        "# Baked from the contract: datetime-typed columns (exported as strings; SQLModel table",
        "# models do not coerce on construction) and primary keys (the UPSERT identity).",
        f"_DATETIME_FIELDS: dict[str, tuple[str, ...]] = {dt_lit}",
        f"_PK: dict[str, tuple[str, ...]] = {pk_lit}", "", "",
        f"def {m}_validate(payload: Any) -> dict[str, Any]:",
        '    """Validate an export payload against the contract WITHOUT touching the DB:',
        '    unknown entities, non-list entity values, non-mapping rows, and unknown fields',
        '    are all reported as errors — nothing is written (AR-4 validation phase)."""',
        "    errors: list[str] = []",
        "    counts: dict[str, int] = {}",
        "    if not isinstance(payload, dict):",
        "        return {\"valid\": False, \"errors\": [\"payload must be a JSON object of {entity: [rows]}\"], \"counts\": counts}",
        "    for entity in payload:",
        "        if entity not in FIELDS:",
        "            errors.append(f\"unknown entity {entity!r}\")",
        "    for entity in ENTITY_ORDER:",
        "        rows = payload.get(entity, [])",
        "        if not isinstance(rows, list):",
        "            errors.append(f\"{entity} must be a list of row objects\")",
        "            continue",
        "        counts[entity] = len(rows)",
        "        allowed = set(FIELDS[entity])",
        "        for i, row in enumerate(rows):",
        "            if not isinstance(row, dict):",
        "                errors.append(f\"{entity}[{i}] must be a mapping\")",
        "                continue",
        "            unknown = sorted(set(row) - allowed)",
        "            if unknown:",
        "                errors.append(f\"{entity}[{i}] has unknown fields {unknown}\")",
        "    return {\"valid\": not errors, \"errors\": errors, \"counts\": counts}", "", "",
        "def _coerce_row(entity: str, row: dict[str, Any]) -> dict[str, Any]:",
        '    """Project a row onto the contract fields, converting exported datetime strings back',
        '    to real datetimes (export serializes them via to_json\'s default=str)."""',
        "    dt_fields = _DATETIME_FIELDS.get(entity, ())",
        "    out: dict[str, Any] = {}",
        "    for field in FIELDS[entity]:",
        "        if field not in row:",
        "            continue",
        "        value = row[field]",
        "        if field in dt_fields and isinstance(value, str):",
        "            value = datetime.fromisoformat(value)",
        "        out[field] = value",
        "    return out", "", "",
        f"def {m}_restore(session: Session, payload: dict[str, Any]) -> dict[str, int]:",
        '    """Restore the export payload — the explicit, confirmed step: UPSERT each row by',
        "    primary key (merge semantics: existing keys update in place, new keys insert;",
        '    re-importing the same file is idempotent; nothing is ever deleted)."""',
        "    written: dict[str, int] = {}",
        "    for entity in ENTITY_ORDER:",
        "        model = getattr(_tables, entity)",
        "        pk = _PK.get(entity, ())",
        "        count = 0",
        "        for raw in payload.get(entity, []):",
        "            data = _coerce_row(entity, raw)",
        "            key = tuple(data.get(f) for f in pk)",
        "            existing = None",
        "            if pk and all(k is not None for k in key):",
        "                existing = session.get(model, key[0] if len(key) == 1 else key)",
        "            if existing is not None:",
        "                for field, value in data.items():",
        "                    setattr(existing, field, value)",
        "                session.add(existing)",
        "            else:",
        "                session.add(model(**data))",
        "            count += 1",
        "        written[entity] = count",
        "    session.commit()",
        "    return written", "",
        f"__all__ = [{(m + '_validate')!r}, {(m + '_restore')!r}]", "",
    ])


def _render_export_package_model(v: ViewSpec) -> str:
    """Model-scoped export-package (AR-3 / FR-10): the WHOLE model, serialized by ``app/export.py``.

    The data module REUSES the generated serialization layer (``ENTITY_ORDER``/``FIELDS`` +
    ``to_json``/``to_markdown``) — no duplicated serialization logic. The payload shape
    (entity name -> list of field-faithful row dicts) is the round-trippable JSON the AR-4
    import flow will consume.
    """
    return "\n".join([
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        "import app.tables as _tables",
        "from app.export import ENTITY_ORDER, FIELDS, to_json, to_markdown", "", "",
        f"def {v.module}_payload(session: Session) -> dict[str, list[dict[str, Any]]]:",
        '    """Whole-model payload: entity name -> field-faithful row dicts (the import-flow shape)."""',
        "    payload: dict[str, list[dict[str, Any]]] = {}",
        "    for entity in ENTITY_ORDER:",
        "        model = getattr(_tables, entity)",
        "        rows = session.exec(select(model)).all()",
        "        payload[entity] = [{f: getattr(row, f) for f in FIELDS[entity]} for row in rows]",
        "    return payload", "", "",
        f"def {v.module}_json(session: Session) -> str:",
        '    """Complete, round-trippable JSON of all entities (app/export.py `to_json`)."""',
        f"    return to_json({v.module}_payload(session))", "", "",
        f"def {v.module}_markdown(session: Session) -> str:",
        '    """Human-readable Markdown of the full model (app/export.py `to_markdown`)."""',
        f"    return to_markdown({v.module}_payload(session))", "",
        f"__all__ = [{(v.module + '_payload')!r}, {(v.module + '_json')!r}, "
        f"{(v.module + '_markdown')!r}]", "",
    ])


def _render_export_package(v: ViewSpec) -> str:
    if v.scope == "model":
        return _render_export_package_model(v)
    entities = sorted({v.root} | {r.frm for r in v.relations})
    imports = ", ".join(entities)
    lines = [
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {imports}", "", "",
        "def _row_to_dict(row: Any) -> dict[str, Any]:",
        '    """Lossless dump of a SQLModel row to a plain dict."""',
        "    return {k: getattr(row, k) for k in row.__class__.model_fields}", "", "",
        f"def {v.module}_package(session: Session, root_id: str) -> dict[str, Any]:",
        f'    """Export-package: assemble {v.root} + resolved relations into a lossless package dict."""',
        f"    root = session.get({v.root}, root_id)",
        '    pkg: dict[str, Any] = {"root": _row_to_dict(root) if root is not None else None}',
    ]
    for r in v.relations:
        lines.append(
            f"    pkg[{r.name!r}] = [_row_to_dict(x) for x in session.exec("
            f"select({r.frm}).where({r.frm}.{r.fk} == root_id)).all()]"
        )
    lines += [
        "    return pkg", "", "",
        f"def {v.module}_to_markdown(pkg: dict[str, Any]) -> str:",
        f'    """Named layout: a `# {v.root}` section then a `## <relation>` section per relation."""',
        "    lines: list[str] = []",
        f'    lines.append("# {v.root}")',
        '    root = pkg.get("root") or {}',
        "    for k in sorted(root):",
        '        lines.append(f"- {k}: {root[k]}")',
    ]
    for r in v.relations:
        lines += [
            f'    lines.append("")',
            f'    lines.append("## {r.name}")',
            f"    for item in pkg.get({r.name!r}, []):",
            '        lines.append(f"- {item}")',
        ]
    lines += [
        '    return chr(10).join(lines)', "",
        f"__all__ = [{(v.module + '_package')!r}, {(v.module + '_to_markdown')!r}]", "",
    ]
    return "\n".join(lines)


_MODULE_RENDERERS = {
    "dashboard": _render_dashboard,
    "board": _render_board,
    "workspace": _render_workspace,
    "detail-compose": _render_detail_compose,
    "export-package": _render_export_package,
    "computed-panel": _render_computed_panel,
}

# Kinds that take a ``/{id}`` route -> their data/package fn is called with the path id.
_ID_ROUTED = {"workspace", "detail-compose", "export-package"}


def render_view_module(v: ViewSpec, schema_sha: str, views_sha: str, schema=None) -> str:
    if v.kind == "import-flow":  # contract-driven: bakes datetime-field + PK maps from the schema
        body = _render_import_flow(v, schema)
    else:
        body = _MODULE_RENDERERS[v.kind](v)
    return _header(schema_sha, views_sha, "view-module") + "\n\n" + body


# --------------------------------------------------------------------------- #
# Router + templates + tests
# --------------------------------------------------------------------------- #

def _is_model_export(v: ViewSpec) -> bool:
    return v.kind == "export-package" and v.scope == "model"


def _is_model_compose(v: ViewSpec) -> bool:
    return v.kind == "detail-compose" and v.scope == "model"


def render_view_router(views: Tuple[ViewSpec, ...], schema_sha: str, views_sha: str) -> str:
    import_lines: List[str] = []
    for v in views:
        if _is_model_export(v):
            import_lines.append(
                f"from app.views.{v.module} import {v.module}_json, {v.module}_markdown"
            )
        elif v.kind == "import-flow":
            import_lines.append(
                f"from app.views.{v.module} import {v.module}_restore, {v.module}_validate"
            )
        elif v.kind == "export-package":
            import_lines.append(f"from app.views.{v.module} import {v.module}_package")
        elif (
            v.kind == "detail-compose"
            and "{" not in v.route
            and not _is_model_compose(v)
        ):
            # Query-id form: the bare-route pick-an-item index needs _roots too.
            # (scope: model emits a single whole-model _data — no index.)
            import_lines.append(
                f"from app.views.{v.module} import {v.module}_data, {v.module}_roots"
            )
        else:
            import_lines.append(f"from app.views.{v.module} import {v.module}_data")
    imports = "\n".join(import_lines)
    # `Response` (raw-body JSON/Markdown) is only imported when a model-scoped export needs it,
    # keeping the router byte-identical for manifests without one. Likewise the import-flow's
    # multipart/refusal machinery (json, Form, HTTPException, UploadFile) only when one exists.
    has_import_flow = any(v.kind == "import-flow" for v in views)
    responses = (
        "from fastapi.responses import HTMLResponse, Response\n"
        if any(_is_model_export(v) for v in views)
        else "from fastapi.responses import HTMLResponse\n"
    )
    json_import = "import json\n\n" if has_import_flow else ""
    fastapi_import = (
        "from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile\n"
        if has_import_flow
        else "from fastapi import APIRouter, Depends, Request\n"
    )
    routes: List[str] = []
    for v in views:
        tmpl = f"views/{v.module}.html"
        if _is_model_export(v):  # AR-3: literal <base>/markdown + <base>/json routes
            base = v.route.rstrip("/")
            routes.append(
                f"@views_router.get({(base + '/markdown')!r})\n"
                f"def {v.module}_markdown_route(session: Session = Depends(get_session)):\n"
                f"    return Response({v.module}_markdown(session), "
                "media_type='text/markdown; charset=utf-8')"
            )
            routes.append(
                f"@views_router.get({(base + '/json')!r})\n"
                f"def {v.module}_json_route(session: Session = Depends(get_session)):\n"
                f"    return Response({v.module}_json(session), media_type='application/json')"
            )
        elif v.kind == "export-package":
            routes.append(
                f"@views_router.get({v.route!r})\n"
                f"def {v.module}(id: str, session: Session = Depends(get_session)):\n"
                f"    return {v.module}_package(session, id)"
            )
        elif (
            v.kind == "detail-compose"
            and "{" not in v.route
            and not _is_model_compose(v)
        ):
            # Query-id form: the nav links this bare as a page — a bare GET renders a
            # pick-an-item index of roots; ?id=<root> renders the composed detail.
            # (scope: model detail-compose takes the whole-model branch below, AR-1.)
            idx_tmpl = f"views/{v.module}_index.html"
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(request: Request, id: Optional[str] = None, session: Session = Depends(get_session)):\n"
                f"    if id is None:\n"
                f"        roots = {v.module}_roots(session)\n"
                f"        return _templates.TemplateResponse(request, {idx_tmpl!r}, {{'roots': roots, 'detail_route': {v.route!r}}})\n"
                f"    data = {v.module}_data(session, id)\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, {{'data': data}})"
            )
        elif v.kind in _ID_ROUTED and not _is_model_compose(v):  # workspace / path-param detail -> HTML, /{id}
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(id: str, request: Request, session: Session = Depends(get_session)):\n"
                f"    data = {v.module}_data(session, id)\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, {{'data': data}})"
            )
        elif v.kind == "computed-panel":  # AR-2: bare route, the compute result as `data`
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(request: Request, session: Session = Depends(get_session)):\n"
                f"    data = {v.module}_data(session)\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, {{'data': data}})"
            )
        elif v.kind == "import-flow":  # AR-4: form -> non-mutating validate -> confirmed restore
            base = v.route.rstrip("/")
            routes.append(
                f"@views_router.get({(base or '/import')!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(request: Request):\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, {{}})"
            )
            routes.append(
                f"@views_router.post({(base + '/validate')!r})\n"
                f"def {v.module}_validate_route(file: UploadFile):\n"
                "    try:\n"
                "        payload = json.loads(file.file.read())\n"
                "    except ValueError as exc:\n"
                "        return {'valid': False, 'errors': [f'not valid JSON: {exc}'], 'counts': {}}\n"
                f"    return {v.module}_validate(payload)"
            )
            routes.append(
                f"@views_router.post({(base + '/restore')!r})\n"
                f"def {v.module}_restore_route(\n"
                "    file: UploadFile,\n"
                "    confirm: str = Form(''),\n"
                "    session: Session = Depends(get_session),\n"
                "):\n"
                "    if confirm != 'restore':  # the destructive step is explicit, never implied\n"
                "        raise HTTPException(\n"
                "            status_code=400,\n"
                "            detail=\"restore writes to the database — resubmit with confirm='restore'\",\n"
                "        )\n"
                "    try:\n"
                "        payload = json.loads(file.file.read())\n"
                "    except ValueError as exc:\n"
                "        raise HTTPException(status_code=422, detail=f'not valid JSON: {exc}')\n"
                f"    report = {v.module}_validate(payload)\n"
                "    if not report['valid']:  # invalid payloads are reported, never written\n"
                "        raise HTTPException(status_code=422, detail={'validation': report})\n"
                f"    written = {v.module}_restore(session, payload)\n"
                "    return {'imported': written, 'total': sum(written.values())}"
            )
        else:
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(request: Request, session: Session = Depends(get_session)):\n"
                f"    rows = {v.module}_data(session)\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, {{'rows': rows}})"
            )
    needs_optional = any(
        v.kind == "detail-compose" and "{" not in v.route and not _is_model_compose(v)
        for v in views
    )
    body = (
        "from __future__ import annotations\n\n"
        + ("from typing import Optional\n\n" if needs_optional else "")
        + f"{json_import}"
        + f"{fastapi_import}"
        f"{responses}"
        "from fastapi.templating import Jinja2Templates\n"
        "from sqlmodel import Session\n\n"
        "from app.db import get_session\n"
        f"{imports}\n\n"
        'views_router = APIRouter(tags=["views"])\n'
        '_templates = Jinja2Templates(directory="app/templates")\n\n\n'
        + "\n\n\n".join(routes)
        + "\n\n\n__all__ = ['views_router']\n"
    )
    return _header(schema_sha, views_sha, "view-router") + "\n\n" + body


def render_view_index_template(v: ViewSpec, schema_sha: str, views_sha: str) -> str:
    """The bare-route pick-an-item index for a query-id detail-compose view (AR-1)."""
    head = (
        "{#\n"
        "# GENERATED from prisma/schema.prisma (+ views.yaml) — do not edit by hand.\n"
        "# startd8-artifact: view-template\n"
        f"# startd8-entity: {v.module}_index\n"
        f"# schema-sha256: {schema_sha}\n"
        f"# views-sha256: {views_sha}\n"
        "#}\n"
    )
    return head + (
        '{% extends "base.html" %}\n'
        "{% block content %}\n"
        f"<h1>{v.module}</h1>\n"
        "{% if not roots %}<p>Nothing here yet — add and confirm a "
        f"{v.root} first.</p>{{% endif %}}\n"
        "<ul>\n"
        "{% for r in roots %}"
        '<li><a href="{{ detail_route }}?id={{ r.id }}">'
        "{{ r.name or r.title or r.headline or r.id }}</a></li>\n"
        "{% endfor %}\n"
        "</ul>\n"
        "{% endblock %}\n"
    )


def render_view_template(v: ViewSpec, schema_sha: str, views_sha: str) -> str:
    head = (
        "{#\n"
        "# GENERATED from prisma/schema.prisma (+ views.yaml) — do not edit by hand.\n"
        "# startd8-artifact: view-template\n"
        f"# startd8-entity: {v.module}\n"
        f"# schema-sha256: {schema_sha}\n"
        f"# views-sha256: {views_sha}\n"
        "#}\n"
    )
    if v.kind == "board":
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            "{% for stage, rows in rows %}<section><h2>{{ stage }}</h2>\n"
            "<ul>{% for r in rows %}<li>{{ r.id }}</li>{% endfor %}</ul></section>{% endfor %}\n"
            "{% endblock %}\n"
        )
    elif v.kind == "workspace":
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            "<ul>{% for r in data.resolved %}<li>{% if r.dangling %}⚠ dangling{% else %}{{ r.entity.id }}{% endif %}</li>{% endfor %}</ul>\n"
            "{% endblock %}\n"
        )
    elif _is_model_compose(v):  # AR-1: every root on one page; meaningful empty state; unlinked flagged
        rel_lines = "".join(
            f"<h3>{r.name}</h3>\n<ul>{{% for x in item.{r.name} %}}<li>{{{{ x.id }}}}</li>{{% endfor %}}</ul>\n"
            for r in v.relations
        )
        unlinked = (
            '{% if not item.linked %}<p class="unlinked">not yet linked</p>{% endif %}\n'
            if v.relations else ""
        )
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            f'{{% if not rows %}}<p class="empty">No {v.root} records yet — add one to start the map.</p>{{% endif %}}\n'
            "{% for item in rows %}<section><h2>{{ item.root.id }}</h2>\n"
            + unlinked + rel_lines +
            "</section>{% endfor %}\n"
            "{% endblock %}\n"
        )
    elif v.kind == "detail-compose":
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            "<p>{{ data.root.id }}</p>\n"
            "{% for name, shown in data.panels.items() %}{% if shown %}<section><h2>{{ name }}</h2></section>{% endif %}{% endfor %}\n"
            "{% endblock %}\n"
        )
    elif v.kind == "computed-panel":  # AR-2: score + ordered nudges (guidance, never a gate)
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            '<p class="score">{{ (data.score * 100) | round | int }}%</p>\n'
            '{% if data.nudges %}<ul class="nudges">{% for n in data.nudges %}<li>{{ n }}</li>{% endfor %}</ul>\n'
            '{% else %}<p class="complete">All signals met.</p>{% endif %}\n'
            "{% endblock %}\n"
        )
    elif v.kind == "import-flow":  # AR-4: upload form; restore demands the explicit confirm tick
        base = v.route.rstrip("/")
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            f'<form method="post" action="{base}/validate" enctype="multipart/form-data">\n'
            '  <input type="file" name="file" required>\n'
            "  <button type=\"submit\">Validate</button>\n"
            "</form>\n"
            f'<form method="post" action="{base}/restore" enctype="multipart/form-data">\n'
            '  <input type="file" name="file" required>\n'
            '  <label><input type="checkbox" name="confirm" value="restore"> '
            "I understand this writes to the database</label>\n"
            "  <button type=\"submit\">Restore</button>\n"
            "</form>\n"
            "{% endblock %}\n"
        )
    elif v.kind == "export-package":  # served as JSON; template is a minimal placeholder
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            "{% endblock %}\n"
        )
    else:  # dashboard
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            "<ul>{% for r in rows %}<li>{{ r.root.id }}</li>{% endfor %}</ul>\n"
            "{% endblock %}\n"
        )
    return head + block


# Prisma scalar -> a valid seed value (table-column level) for the rung-4 view-test fixtures. A field
# needs a seed value only if it is required AND has no @default (id/owner/source/confirmed/timestamps
# all default), so the seeds fill the contract's *genuinely* required content fields (e.g. a JD's
# required rawText) — the gap the all-optional unit fixture masked until the real-contract dry-run.
_SEED_SAMPLE = {
    "String": '"sample"', "Int": "0", "BigInt": "0", "Float": "0.0", "Boolean": "False",
    "Decimal": '"0"', "DateTime": '"2020-01-01T00:00:00"', "Json": "None", "Bytes": 'b"x"',
}


def _field_has_default(field) -> bool:
    attrs = " ".join(field.attributes).lower()
    return "@default" in attrs or "@updatedat" in attrs or "@id" in attrs


def _seed_sample(field, schema) -> str:
    if field.type in schema.enums:
        vals = schema.enums[field.type]
        return f'"{vals[0]}"' if vals else '""'
    return _SEED_SAMPLE.get(field.type, '"sample"')


def _seed(schema, var: str, entity: str, explicit: dict) -> str:
    """A seed line filling *explicit* fields + every required, non-defaulted, non-list scalar of *entity*."""
    parts = dict(explicit)
    for f in schema.scalar_fields(entity):
        if f.name in parts or f.is_optional or f.is_list or _field_has_default(f):
            continue
        parts[f.name] = _seed_sample(f, schema)
    kw = ", ".join(f"{k}={v}" for k, v in parts.items())
    return f"        {var} = t.{entity}({kw}); s.add({var}); s.commit(); s.refresh({var})"


# The in-process app builder the route-level tests share (AR-1 bare-route 200, AR-4 confirm gate).
# Emitted ONLY when a view needs route tests, keeping renders byte-identical for other manifests.
_API_HELPER = (
    "def _api(engine):\n"
    '    """A minimal app mounting views_router on this test\'s engine (user_routers-seam stand-in)."""\n'
    "    from fastapi import FastAPI\n\n"
    "    from app.db import get_session\n"
    "    from app.views.routes import views_router\n\n"
    "    def _session_override():\n"
    "        with Session(engine) as s:\n"
    "            yield s\n\n"
    "    api = FastAPI()\n"
    "    api.include_router(views_router)\n"
    "    api.dependency_overrides[get_session] = _session_override\n"
    "    return api"
)


def _needs_route_test(v: ViewSpec) -> bool:
    return _is_model_compose(v) or v.kind == "import-flow"


def render_view_tests(views: Tuple[ViewSpec, ...], schema, schema_sha: str, views_sha: str) -> str:
    """Rung-4 view tests — exercise each data function against a fixtured DB (the D1 gate)."""
    blocks = [_render_view_test(schema, v) for v in views]
    preamble = (
        _TEST_SHIM + "\n"
        "import pytest\n\n"
        'pytest.importorskip("sqlmodel")\n\n'
        "from sqlmodel import Session, SQLModel, create_engine  # noqa: E402"
    )
    if any(_needs_route_test(v) for v in views):
        blocks = [_API_HELPER] + blocks
    header = _header(schema_sha, views_sha, "view-tests")
    body = preamble + ("\n\n\n" + "\n\n\n".join(blocks) if blocks else "\n")
    return header + "\n\n" + body + "\n"


def _render_view_test(schema, v: ViewSpec) -> str:
    if _is_model_export(v):
        return _render_model_export_test(schema, v)
    if _is_model_compose(v):
        return _render_model_compose_test(schema, v)
    if v.kind == "computed-panel":
        return _render_computed_panel_test(schema, v)
    if v.kind == "import-flow":
        return _render_import_flow_test(schema, v)
    if v.kind == "export-package":
        import_line = (
            f"    from app.views.{v.module} import {v.module}_package, {v.module}_to_markdown"
        )
    else:
        import_line = f"    from app.views.{v.module} import {v.module}_data"
    setup = [
        f"def test_{v.module}_data(tmp_path):",
        "    import app.tables as t",
        import_line,
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    with Session(engine) as s:",
    ]
    if v.kind == "dashboard":
        setup.append(_seed(schema, "root", v.root, {}))
        for i, a in enumerate(v.aggregates):
            setup.append(_seed(schema, f"_x{i}", a.of, {a.fk: "root.id"}))
        setup += [f"        rows = {v.module}_data(s)", "    assert len(rows) == 1"]
        for a in v.aggregates:
            setup.append(f"    assert rows[0][{a.name!r}] == 1")
        if v.signal:
            setup.append("    assert rows[0]['signal'] is True")
    elif v.kind == "board":
        a, b = v.order[0], (v.order[1] if len(v.order) > 1 else v.order[0])
        setup += [
            _seed(schema, "_r1", v.root, {v.group_by: repr(a)}),
            _seed(schema, "_r2", v.root, {v.group_by: repr(b)}),
            f"        board = {v.module}_data(s)",
            "    cols = dict(board)",
            f"    assert len(cols.get({a!r}, [])) >= 1",
            f"    assert [s for s, _ in board][:{len(v.order)}] == {list(v.order)!r}",
        ]
    elif v.kind == "workspace":  # the key test: resolution + dangling flag (+ gap if declared)
        p = v.polymorphic
        first_type, first_entity = p.type_map[0]
        root_explicit: dict = {}
        if v.gap is not None:
            # seed the first needs field with two newline-split needs so `gaps` is non-trivial
            root_explicit[v.gap.needs_from[0]] = repr("need-a\nneed-b")
        setup += [
            _seed(schema, "root", v.root, root_explicit),
            _seed(schema, "ent", first_entity, {}),
            _seed(schema, "_good", p.of, {p.fk: "root.id", p.type_field: repr(first_type), p.id_field: "ent.id"}),
            _seed(schema, "_dangling", p.of, {p.fk: "root.id", p.type_field: repr(first_type), p.id_field: "'nope'"}),
            f"        data = {v.module}_data(s, root.id)",
            "    resolved = data['resolved']",
            "    assert any(not r['dangling'] for r in resolved)  # the real ref resolves",
            "    assert any(r['dangling'] for r in resolved)       # the bad ref is flagged, not crashed",
        ]
        if v.gap is not None:
            setup += [
                "    assert 'gaps' in data       # gap set-difference computed (non-crashing)",
                "    assert isinstance(data['gaps'], list)",
            ]
    elif v.kind == "detail-compose":
        setup.append(_seed(schema, "root", v.root, {}))
        for i, r in enumerate(v.relations):
            setup.append(_seed(schema, f"_rel{i}", r.frm, {r.fk: "root.id"}))
        setup += [
            f"        data = {v.module}_data(s, root.id)",
            "    assert data['root'] is not None",
        ]
        for r in v.relations:
            setup.append(f"    assert len(data[{r.name!r}]) >= 1  # relation {r.name} resolved")
        for pn in v.panels:
            setup.append(f"    assert {pn.name!r} in data['panels']  # panel bool computed")
    else:  # export-package — package losslessness + named MD layout
        setup.append(_seed(schema, "root", v.root, {}))
        for i, r in enumerate(v.relations):
            setup.append(_seed(schema, f"_rel{i}", r.frm, {r.fk: "root.id"}))
        setup += [
            f"        pkg = {v.module}_package(s, root.id)",
            f"        md = {v.module}_to_markdown(pkg)",
            "    assert pkg['root']['id'] == root.id  # root present + lossless",
        ]
        for r in v.relations:
            setup.append(f"    assert len(pkg[{r.name!r}]) >= 1  # relation {r.name} in package")
        setup.append(f"    assert '# {v.root}' in md  # root section header")
        for r in v.relations:
            setup.append(f"    assert '## {r.name}' in md  # {r.name} section header")
    return "\n".join(setup)


def _render_computed_panel_test(schema, v: ViewSpec) -> str:
    """Computed-panel test (AR-2): the binding really feeds live counts into the generated
    compute function — empty model nudges (never blocks), a seeded row moves the inputs."""
    first = next(iter(schema.models))
    return "\n".join([
        f"def test_{v.module}_data(tmp_path):",
        "    import app.tables as t",
        f"    from app.views.{v.module} import {v.module}_data",
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    with Session(engine) as s:",
        f"        empty = {v.module}_data(s)",
        "        assert 0.0 <= empty['score'] <= 1.0",
        "        assert empty['nudges']  # an empty model nudges — guidance, never a gate (FR-9)",
        _seed(schema, "root", first, {}),
        f"        seeded = {v.module}_data(s)",
        f"    assert seeded['present'][{first!r}] == 1  # live row counts feed the compute binding",
        "    assert seeded['score'] >= empty['score']",
    ])


def _render_model_compose_test(schema, v: ViewSpec) -> str:
    """Model-compose tests (AR-1): data correctness + the bare-route 200 acceptance.

    The route test is the FR-8 regression pin: bare GET (no ``?id=``) answers 200 on an EMPTY
    DB (meaningful empty state, not 422) and on a populated one.
    """
    data_lines = [
        f"def test_{v.module}_data(tmp_path):",
        "    import app.tables as t",
        f"    from app.views.{v.module} import {v.module}_data",
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    with Session(engine) as s:",
        f"        assert {v.module}_data(s) == []  # empty model -> empty list, not an error",
        _seed(schema, "root", v.root, {}),
    ]
    for i, r in enumerate(v.relations):
        data_lines.append(_seed(schema, f"_rel{i}", r.frm, {r.fk: "root.id"}))
    if v.relations:
        data_lines.append(_seed(schema, "_unlinked", v.root, {}))
    data_lines += [
        f"        rows = {v.module}_data(s)",
        f"    assert len(rows) == {2 if v.relations else 1}  # EVERY root present (whole-model iterate)",
    ]
    for r in v.relations:
        data_lines.append(
            f"    assert any(len(item[{r.name!r}]) >= 1 for item in rows)  # relation {r.name} resolved"
        )
    if v.relations:
        data_lines += [
            "    assert any(item['linked'] for item in rows)      # the linked root is marked",
            "    assert any(not item['linked'] for item in rows)  # the unlinked root flagged, not dropped",
        ]
    for pn in v.panels:
        data_lines.append(f"    assert {pn.name!r} in rows[0]['panels']  # panel bool computed")
    route_lines = [
        f"def test_{v.module}_route(tmp_path):",
        '    pytest.importorskip("fastapi")',
        '    pytest.importorskip("httpx")',
        "    from fastapi.testclient import TestClient",
        "",
        "    import app.tables as t",
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    client = TestClient(_api(engine))",
        f"    resp = client.get({v.route!r})",
        "    assert resp.status_code == 200  # bare route, EMPTY DB (the /value-map 422 regression)",
        "    assert resp.text.strip()        # meaningful empty state, not a blank body",
        "    with Session(engine) as s:",
        _seed(schema, "root", v.root, {}),
        f"    resp = client.get({v.route!r})",
        "    assert resp.status_code == 200  # bare route, populated DB",
        "    assert root.id in resp.text     # the root actually renders",
    ]
    return "\n".join(data_lines) + "\n\n\n" + "\n".join(route_lines)


def _render_import_flow_test(schema, v: ViewSpec) -> str:
    """Import-flow tests (AR-4): the FR-10 round-trip + the explicit-confirmation gate.

    Round-trip acceptance (FR-10: "export-then-import reproduces an identical value model"):
    export JSON from a seeded DB -> validate -> restore into an EMPTY DB -> re-export ->
    byte-equal. Plus idempotence (re-importing the same file writes no duplicates) and the
    route-level refusal of an unconfirmed restore.
    """
    first = next(iter(schema.models))
    base = v.route.rstrip("/")
    round_trip = [
        f"def test_{v.module}_round_trip(tmp_path):",
        "    import json",
        "",
        "    import app.tables as t",
        "    from sqlmodel import select",
        "",
        "    from app.export import ENTITY_ORDER, FIELDS, to_json",
        f"    from app.views.{v.module} import {v.module}_restore, {v.module}_validate",
        "",
        "    def _payload(s):",
        "        out = {}",
        "        for entity in ENTITY_ORDER:",
        "            rows = s.exec(select(getattr(t, entity))).all()",
        "            out[entity] = [{f: getattr(r, f) for f in FIELDS[entity]} for r in rows]",
        "        return out",
        "",
        '    engine_a = create_engine(f"sqlite:///{tmp_path}/a.db")',
        '    engine_b = create_engine(f"sqlite:///{tmp_path}/b.db")',
        "    SQLModel.metadata.create_all(engine_a)",
        "    SQLModel.metadata.create_all(engine_b)",
        "    with Session(engine_a) as s:",
        _seed(schema, "root", first, {}),
        "        exported = to_json(_payload(s))",
        "    payload = json.loads(exported)",
        f"    report = {v.module}_validate(payload)",
        "    assert report['valid'], report['errors']",
        "    assert sum(report['counts'].values()) == 1",
        "    bad = dict(payload)",
        "    bad['Ghost'] = []",
        f"    assert {v.module}_validate(bad)['valid'] is False  # unknown entity reported, not written",
        f"    bad = {{{first!r}: [{{'noSuchField': 1}}]}}",
        f"    assert {v.module}_validate(bad)['valid'] is False  # field shapes checked vs the contract",
        "    with Session(engine_b) as s:  # restore into the EMPTY db (FR-10)",
        f"        written = {v.module}_restore(s, payload)",
        "        assert sum(written.values()) == 1",
        "        assert to_json(_payload(s)) == exported  # round-trip: re-export is byte-equal",
        f"        {v.module}_restore(s, payload)           # idempotent: same file, no duplicates",
        "        assert to_json(_payload(s)) == exported",
    ]
    confirm_gate = [
        f"def test_{v.module}_routes_confirm_gate(tmp_path):",
        '    pytest.importorskip("fastapi")',
        '    pytest.importorskip("httpx")',
        '    pytest.importorskip("multipart")',
        "    from fastapi.testclient import TestClient",
        "",
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    client = TestClient(_api(engine))",
        f"    resp = client.get({(base or '/import')!r})",
        "    assert resp.status_code == 200  # the upload form renders",
        '    files = {"file": ("model.json", "{}", "application/json")}',
        f"    resp = client.post({(base + '/validate')!r}, files=files)",
        "    assert resp.status_code == 200 and resp.json()['valid'] is True",
        f"    resp = client.post({(base + '/restore')!r}, files=files)",
        "    assert resp.status_code == 400  # destructive restore REFUSED without explicit confirm",
        f"    resp = client.post({(base + '/restore')!r}, files=files, data={{'confirm': 'restore'}})",
        "    assert resp.status_code == 200 and resp.json()['total'] == 0",
        '    bad = {"file": ("model.json", "not json", "application/json")}',
        f"    resp = client.post({(base + '/restore')!r}, files=bad, data={{'confirm': 'restore'}})",
        "    assert resp.status_code == 422  # invalid payloads refused, reported, never written",
    ]
    return "\n".join(round_trip) + "\n\n\n" + "\n".join(confirm_gate)


def _render_model_export_test(schema, v: ViewSpec) -> str:
    """Model-export test: whole-model coverage + JSON round-trip through app/export.py's shape."""
    first = next(iter(schema.models))
    return "\n".join([
        f"def test_{v.module}_data(tmp_path):",
        "    import json",
        "",
        "    import app.tables as t",
        "    from app.export import ENTITY_ORDER",
        f"    from app.views.{v.module} import "
        f"{v.module}_json, {v.module}_markdown, {v.module}_payload",
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    with Session(engine) as s:",
        _seed(schema, "root", first, {}),
        f"        payload = {v.module}_payload(s)",
        f"        exported_json = {v.module}_json(s)",
        f"        exported_md = {v.module}_markdown(s)",
        "    assert set(payload) == set(ENTITY_ORDER)  # whole model: every entity present",
        f"    assert len(payload[{first!r}]) == 1",
        "    restored = json.loads(exported_json)  # round-trip: entity name -> list of row dicts",
        "    assert set(restored) == set(payload)",
        f"    assert restored[{first!r}][0]['id'] == root.id  # field-faithful, restorable (AR-4)",
        f"    assert '# ' + {first!r} in exported_md  # a markdown section per entity",
    ])


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def render_views(schema_text: str, views_text: str) -> Tuple[Tuple[str, str], ...]:
    """Every composite-view artifact as ``(relative_path, text)`` pairs.

    ``known_entities`` for strict validation is derived from the schema (reuses the parser via
    ``backend_codegen`` would cause a cycle, so we parse names cheaply here).
    """
    from ..languages.prisma_parser import parse_prisma_schema

    schema = parse_prisma_schema(schema_text)
    known = frozenset(schema.models)
    views = parse_views(views_text, known_entities=known)
    s_sha, v_sha = schema_sha256(schema_text), schema_sha256(views_text)

    out: List[Tuple[str, str]] = [("app/views/__init__.py", "")]
    for v in views:
        out.append((_module_path(v), render_view_module(v, s_sha, v_sha, schema=schema)))
        if _is_model_export(v):
            continue  # served as raw Markdown/JSON responses — no template at all (AR-3)
        out.append((f"app/templates/views/{v.module}.html", render_view_template(v, s_sha, v_sha)))
        if v.kind == "detail-compose" and "{" not in v.route:
            out.append((
                f"app/templates/views/{v.module}_index.html",
                render_view_index_template(v, s_sha, v_sha),
            ))
    out.append(("app/views/routes.py", render_view_router(views, s_sha, v_sha)))
    out.append(("tests/test_views.py", render_view_tests(views, schema, s_sha, v_sha)))
    return tuple(out)
