"""Deterministic composite-view emitters (class-3 determinism — REQ-VIEW-3).

Pure, no-LLM projection of ``views.yaml`` + the contract into owned **multi-entity** views that
``backend_codegen`` (single-entity CRUD) does not emit: a data module per view (the resolver/
aggregator/grouper — pure SQLModel ``select`` + Python), a router, minimal templates over the owned
``base.html``, and the rung-4 view tests that prove resolution/aggregation/grouping correctness
(incl. the dangling-polymorphic-ref-flagged-not-crashed invariant — RUN-029/032).

Two-hash drift: a view file is stale if **either** the schema or ``views.yaml`` changed.
"""

from __future__ import annotations

import json
from typing import Dict, List, Optional, Tuple

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
    if v.columns_from:
        return _render_entity_board(v)
    order_lit = "[" + ", ".join(f'"{s}"' for s in v.order) + "]"
    return "\n".join([
        "from __future__ import annotations", "",
        "from enum import Enum",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {v.root}", "",
        f"_ORDER = {order_lit}", "", "",
        f"def {v.module}_data(session: Session) -> list[tuple[str, list[Any]]]:",
        f'    """Board: group {v.root} by `{v.group_by}` in the owned order; '
        'unknown statuses kept (no row lost), appended last."""',
        "    cols: dict[str, list[Any]] = {}",
        f"    for root in session.exec(select({v.root})).all():",
        f"        _key = getattr(root, {v.group_by!r})",
        "        # Group by the field's string form so the _ORDER (plain strings) matches whether "
        "the column is a str, a str-mixed Enum, or a plain Enum (a non-str Enum member would "
        "otherwise never equal an _ORDER string — empty columns, a silent looks-like-success bug).",
        "        _key = _key.value if isinstance(_key, Enum) else _key",
        "        cols.setdefault(_key, []).append(root)",
        "    ordered = [(s, cols.pop(s, [])) for s in _ORDER]",
        "    ordered += [(s, rows) for s, rows in cols.items()]  # statuses outside the allow-list",
        "    return ordered", "",
        f"__all__ = [{(v.module + '_data')!r}]", "",
    ])


def _render_entity_board(v: ViewSpec) -> str:
    """Entity-backed board (FR-EB): columns ARE a related entity's runtime rows, ordered by a
    numeric ``order_by`` field — no static ``_ORDER`` list. Columns are queried at request time
    (user-definable, no regeneration); each column holds the root rows whose ``group_by`` matches
    its id; roots matching no column are kept in an "Unassigned" tail (no row lost).

    Returns ``list[tuple[str, list]]`` (column label -> root rows) — the SAME shape the static
    board returns, so the board template renders both variants identically. The label is the
    column row's ``name``/``title`` (falling back to its id), so columns read as user-named stages.
    """
    imports = ", ".join(sorted({v.root, v.columns_from}))
    return "\n".join([
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {imports}", "", "",
        f"def {v.module}_data(session: Session) -> list[tuple[str, list[Any]]]:",
        f'    """Entity-backed board: columns are {v.columns_from} rows ordered by `{v.order_by}`;'
        f' group {v.root} by `{v.group_by}` == column id; unmatched roots kept in an Unassigned'
        ' tail (no row lost). Columns are runtime data — reorder/rename/add with no regeneration."""',
        f"    columns = session.exec(select({v.columns_from})"
        f".order_by({v.columns_from}.{v.order_by})).all()",
        "    grouped: dict[Any, list[Any]] = {}",
        f"    for root in session.exec(select({v.root})).all():",
        f"        grouped.setdefault(getattr(root, {v.group_by!r}), []).append(root)",
        "    ordered: list[tuple[str, list[Any]]] = []",
        "    _claimed: set[Any] = set()",
        "    for col in columns:",
        "        _label = getattr(col, \"name\", None) or getattr(col, \"title\", None) or col.id",
        "        ordered.append((str(_label), grouped.get(col.id, [])))",
        "        _claimed.add(col.id)",
        "    # any root whose ref matches no column (incl. None) -> the Unassigned tail, never dropped",
        "    _leftover: list[Any] = []",
        "    for _key, _rows in grouped.items():",
        "        if _key not in _claimed:",
        "            _leftover.extend(_rows)",
        "    if _leftover:",
        '        ordered.append(("Unassigned", _leftover))',
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


def _fk_target(via_fk: str, schema) -> Optional[str]:
    """SDK FK convention: ``<lowerCamel(Target)>Id`` → ``Target`` (validated against the schema)."""
    if schema and via_fk.endswith("Id"):
        cand = via_fk[:-2]
        cand = cand[:1].upper() + cand[1:]
        if schema.model(cand) is not None:
            return cand
    return None


def _resolved_rel_map(v: ViewSpec, vd, schema) -> Dict[str, Tuple[str, str, str]]:
    """FR-DM-6: relations with a display binding (via_fk + label_field) whose FK target resolves →
    {rel_name: (via_fk, label_field, target_entity)}. The data-fetch + template use this identically
    so a bound relation renders the target's LABEL, not the join-row id (kills ``neil-cpo-01``)."""
    out: Dict[str, Tuple[str, str, str]] = {}
    if not vd:
        return out
    rel_names = {r.name for r in v.relations}
    for rd in vd.relations:
        if rd.name in rel_names and rd.via_fk and rd.label_field:
            tgt = _fk_target(rd.via_fk, schema)
            if tgt is not None:
                out[rd.name] = (rd.via_fk, rd.label_field, tgt)
    return out


def _render_detail_compose_model(v: ViewSpec, vd=None, schema=None) -> str:
    """Model-scoped detail-compose (AR-1 / FR-8): EVERY root + resolved relations on ONE page.

    The whole-model compose behind the Value Map: iterate ALL roots, resolve each declared
    relation per root, compute conditional panels per root, and flag a root with no resolved
    relation rows as unlinked (the "not yet linked" empty-ish state) — never drop it. The route
    takes no ``{id}``; bare GET serves 200 on empty AND populated DBs (empty -> empty list ->
    the template's meaningful empty state). FR-DM-6: relations bound in display.yaml resolve the
    join row → the target entity's label (``{id, label}``) instead of leaking the join-row id.
    """
    resolved = _resolved_rel_map(v, vd, schema)
    extra_targets = {t for (_fk, _lf, t) in resolved.values()}
    entities = sorted({v.root} | {r.frm for r in v.relations} | extra_targets)
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
    if vd and vd.root_label_field:                  # FR-DM-6: group heading = the root's label
        lines.append(
            f'        item["root_label"] = getattr(root, {vd.root_label_field!r}, None) or root.id'
        )
    for r in v.relations:
        if r.name in resolved:                      # FR-DM-6: resolve join row → target {id, label}
            via_fk, label_field, tgt = resolved[r.name]
            lines += [
                f"        item[{r.name!r}] = []",
                f"        for _j in session.exec("
                f"select({r.frm}).where({r.frm}.{r.fk} == root.id)).all():",
                f"            _tid = getattr(_j, {via_fk!r})",
                f"            _t = session.get({tgt}, _tid)",
                f"            item[{r.name!r}].append("
                f"{{'id': _tid, 'label': getattr(_t, {label_field!r}, None) or _tid}})",
            ]
        else:
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


# --------------------------------------------------------------------------- #
# computed-panel compute-binding registry (AR-2) — THE single source of truth
# --------------------------------------------------------------------------- #
# A compute binding is exactly ``(name, renderer-fn)``: ``name`` is the manifest's
# ``compute:`` token, ``renderer-fn`` emits the binding's ``app/views/<view>.py`` data module.
# This dict is the ONE place the vocabulary lives — ``manifest.parse_views`` derives its
# parse-time validation set from ``compute_binding_names()`` (a deferred import, since
# renderers depends on manifest), so "what parses" and "what renders" can never drift.
#
# To add a new $0 compute binding (worked example — FR-37 funnel metrics):
#   1. Write the generated-source contract the binding reads (e.g. ``app/funnel.py`` exposing
#      ``STAGES`` + ``compute_funnel(counts)`` — the deterministic per-stage conversion math),
#      the same way ``completeness`` reuses the generated ``app/completeness.py``. The renderer
#      must IMPORT that contract, never re-implement the metric here.
#   2. Add a ``_render_computed_panel_funnel(v: ViewSpec) -> str`` emitting the view's data module
#      (gather live inputs -> call the generated compute fn -> return the panel dict).
#   3. Register it below: ``"funnel": _render_computed_panel_funnel``.
# That single entry opens the vocabulary: ``parse_views`` now accepts ``compute: funnel`` and the
# render dispatch picks it up automatically — no other edit, no duplicated allow-list. (``funnel``
# and ``prediction`` are intentionally NOT implemented here; each needs its own generated-source
# contract, out of scope for the registry mechanism itself.)
_COMPUTE_RENDERERS = {
    "completeness": _render_computed_panel_completeness,
}


def compute_binding_names() -> frozenset:
    """The registered compute-binding vocabulary — the single source of truth for both the
    manifest parse-validation set and the render dispatch (see ``_COMPUTE_RENDERERS``)."""
    return frozenset(_COMPUTE_RENDERERS)


def _render_computed_panel(v: ViewSpec) -> str:
    return _COMPUTE_RENDERERS[v.compute](v)


# --------------------------------------------------------------------------- #
# rendered-content (AR-6 / FR-16) — the prose-from-a-JSON-field presenter
# --------------------------------------------------------------------------- #
# A SINGLE prose-from-JSON renderer (``app/views/_prose.py``), reused by BOTH the rendered-content
# view AND the model-scoped export-package's named layout (FR-10) — no duplicated extraction logic.
# It tolerates the column being a dict, a JSON string, or empty/missing, and never raises: an
# empty/missing body yields "" (the empty state), never a crash or a leaked JSON blob/trace ids.
_PROSE_MODULE = "\n".join([
    "from __future__ import annotations", "",
    "import json",
    "from html import escape",
    "from typing import Any", "", "",
    "def prose_body(value: Any, key: str = \"body\") -> str:",
    '    """The prose stored under *key* in a JSON content column. Tolerates a dict, a JSON string,',
    '    or None/empty -> "" (never raises, never leaks the raw blob or trace ids)."""',
    "    data: Any = value",
    "    if isinstance(value, str):",
    "        try:",
    "            data = json.loads(value)",
    "        except (ValueError, TypeError):",
    "            return value  # a plain string column is itself the prose",
    "    if isinstance(data, dict):",
    "        body = data.get(key)",
    "        return body if isinstance(body, str) else \"\"",
    "    return \"\"", "", "",
    "def prose_preview(value: Any, key: str = \"body\", limit: int = 140) -> str:",
    '    """A one-line preview of the prose (kind + preview list view) — never JSON."""',
    "    text = \" \".join(prose_body(value, key).split())",
    "    return text if len(text) <= limit else text[: limit - 1].rstrip() + \"\\u2026\"", "", "",
    "def prose_html(value: Any, key: str = \"body\") -> str:",
    '    """Render the prose as HTML paragraphs (blank-line split), HTML-escaped — no Markdown',
    '    dependency, no JSON, no trace ids. Empty body -> \"\" (the caller shows the empty state)."""',
    "    text = prose_body(value, key)",
    "    if not text.strip():",
    "        return \"\"",
    "    blocks = [b.strip() for b in text.replace(\"\\r\\n\", \"\\n\").split(\"\\n\\n\") if b.strip()]",
    "    return \"\\n\".join(",
    "        \"<p>\" + escape(b).replace(\"\\n\", \"<br>\") + \"</p>\" for b in blocks",
    "    )", "",
    "__all__ = [\"prose_body\", \"prose_preview\", \"prose_html\"]", "",
])


def _render_rendered_content(v: ViewSpec) -> str:
    """Rendered-content module (AR-6 / FR-16): list + read one entity's prose-from-a-JSON-field.

    Two data fns: ``<view>_list`` returns each row's (id, kind, preview) — kind + a prose preview,
    never JSON; ``<view>_data`` returns one row resolved to ``{id, kind, body, html}`` for the
    detail view (prose, copyable plain ``body``, no trace ids). The prose extraction is the shared
    ``app/views/_prose.py`` renderer (also feeding the FR-10 export), never duplicated here.
    """
    cf, pk = v.content_field, v.prose_key
    return "\n".join([
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        f"from app.tables import {v.root}",
        "from app.views._prose import prose_body, prose_html, prose_preview", "", "",
        f"def {v.module}_list(session: Session) -> list[dict[str, Any]]:",
        f'    """List view: each {v.root} as kind + a prose preview (never the raw JSON)."""',
        "    out: list[dict[str, Any]] = []",
        f"    for row in session.exec(select({v.root})).all():",
        f"        value = getattr(row, {cf!r}, None)",
        "        out.append({",
        "            \"id\": row.id,",
        f"            \"kind\": getattr(row, \"kind\", None) or {v.module!r},",
        f"            \"preview\": prose_preview(value, {pk!r}),",
        "        })",
        "    return out", "", "",
        f"def {v.module}_data(session: Session, root_id: str) -> dict[str, Any]:",
        f'    """Detail view: one {v.root}\'s prose under its kind heading — body (copyable plain',
        '    text) + html (rendered paragraphs); no JSON, no trace ids. Missing row/body -> empty."""',
        f"    row = session.get({v.root}, root_id)",
        "    if row is None:",
        '        return {"id": root_id, "kind": ' + repr(v.module) + ', "body": "", "html": ""}',
        f"    value = getattr(row, {cf!r}, None)",
        "    return {",
        "        \"id\": row.id,",
        f"        \"kind\": getattr(row, \"kind\", None) or {v.module!r},",
        f"        \"body\": prose_body(value, {pk!r}),",
        f"        \"html\": prose_html(value, {pk!r}),",
        "    }", "",
        f"__all__ = [{(v.module + '_list')!r}, {(v.module + '_data')!r}]", "",
    ])


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


def _render_export_package_model(v: ViewSpec, prose_specs: Tuple[ViewSpec, ...] = ()) -> str:
    """Model-scoped export-package (AR-3 / FR-10): the WHOLE model, serialized by ``app/export.py``.

    The data module REUSES the generated serialization layer (``ENTITY_ORDER``/``FIELDS`` +
    ``to_json``/``to_markdown``) — no duplicated serialization logic. The payload shape
    (entity name -> list of field-faithful row dicts) is the round-trippable JSON the AR-4
    import flow will consume.

    FR-10 conformance: when the manifest declares rendered-content views (AR-6), the Markdown
    layout appends each such entity's prose **verbatim**, rendered as prose via the SAME
    ``app/views/_prose.py`` ``prose_body`` renderer the in-app presenter uses — NOT a per-entity
    ``dataJson`` dump. The pitches/summary land in the export as the text the person would send.
    """
    prose_roots = sorted({pv.root for pv in prose_specs})
    extra_imports: List[str] = []
    if prose_specs:
        extra_imports.append(f"from app.tables import {', '.join(prose_roots)}")
        extra_imports.append("from app.views._prose import prose_body")
    lines = [
        "from __future__ import annotations", "",
        "from typing import Any", "",
        "from sqlmodel import Session, select", "",
        "import app.tables as _tables",
        "from app.export import ENTITY_ORDER, FIELDS, to_json, to_markdown",
    ]
    lines += extra_imports
    lines += [
        "", "",
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
        '    """Human-readable Markdown of the model: the generic per-entity dump of the NON-prose',
        "    entities, then each rendered-content entity rendered ONCE as a named prose section",
        '    (kind-headed, body verbatim) — never also as a row in the generic dump (F-10b: no',
        "    duplicate blank row, no JSON / trace ids). NOTE: a fuller domain-specific named layout",
        "    (e.g. résumé bullets + interview-prep ordering) is the consuming app's owned-glue — the",
        '    generic archetype can only present prose-vs-structured cleanly, not impose a domain order."""',
        f"    payload = {v.module}_payload(session)",
    ]
    if prose_specs:
        # F-10b: drop the prose entities from the generic dump ENTIRELY (not just
        # redact their content field) — they are rendered as named prose below, so a
        # blanked row in the dump would be a confusing duplicate. The JSON export
        # (<view>_json) keeps every entity, so AR-4 round-trip is unaffected.
        prose_roots = "{" + ", ".join(f"{pv.root!r}" for pv in prose_specs) + "}"
        lines += [
            f"    _prose_entities = {prose_roots}  # rendered as named prose below, not in the dump",
            "    _dump = {_e: _rows for _e, _rows in payload.items() if _e not in _prose_entities}",
            "    sections: list[str] = [to_markdown(_dump)]",
        ]
        for pv in prose_specs:
            heading = pv.module.replace("_", " ").title()
            lines += [
                f'    # {pv.root} prose (rendered-content {pv.module}), verbatim',
                '    sections.append("")',
                f'    sections.append("# {heading}")',
                f"    for _row in session.exec(select({pv.root})).all():",
                f"        _kind = getattr(_row, \"kind\", None) or {pv.module!r}",
                f"        _body = prose_body(getattr(_row, {pv.content_field!r}, None), {pv.prose_key!r})",
                "        if not _body.strip():",
                "            continue",
                '        sections.append("")',
                '        sections.append(f"## {_kind}")',
                '        sections.append(_body)  # VERBATIM — the prose exactly as stored',
            ]
        lines.append("    return chr(10).join(sections)")
    else:
        lines.append("    return to_markdown(payload)")
    lines += [
        "",
        f"__all__ = [{(v.module + '_payload')!r}, {(v.module + '_json')!r}, "
        f"{(v.module + '_markdown')!r}]", "",
    ]
    return "\n".join(lines)


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
    "rendered-content": _render_rendered_content,
}

# Kinds that take a ``/{id}`` route -> their data/package fn is called with the path id.
_ID_ROUTED = {"workspace", "detail-compose", "export-package"}


def render_view_module(
    v: ViewSpec, schema_sha: str, views_sha: str, schema=None, views: Tuple[ViewSpec, ...] = (),
    view_display=None,
) -> str:
    if _is_model_compose(v) and view_display is not None:
        body = _render_detail_compose_model(v, view_display, schema)  # FR-DM-6 label resolution
    elif v.kind == "import-flow":  # contract-driven: bakes datetime-field + PK maps from the schema
        body = _render_import_flow(v, schema)
    elif _is_model_export(v):
        # FR-10 conformance: the named MD layout renders rendered-content prose VERBATIM (the same
        # AR-6 prose-from-JSON renderer), not a per-entity dataJson dump. Needs the sibling
        # rendered-content specs in the manifest to know which entity/field holds the prose.
        body = _render_export_package_model(v, _prose_content_specs(views))
    else:
        body = _MODULE_RENDERERS[v.kind](v)
    return _header(schema_sha, views_sha, "view-module") + "\n\n" + body


def _prose_content_specs(views: Tuple[ViewSpec, ...]) -> Tuple[ViewSpec, ...]:
    """The rendered-content views (AR-6) in a manifest — the entities whose JSON column holds prose
    the FR-10 model export renders verbatim. Order-stable (declaration order)."""
    return tuple(v for v in views if v.kind == "rendered-content")


# --------------------------------------------------------------------------- #
# Router + templates + tests
# --------------------------------------------------------------------------- #

def _is_model_export(v: ViewSpec) -> bool:
    return v.kind == "export-package" and v.scope == "model"


def _is_model_compose(v: ViewSpec) -> bool:
    return v.kind == "detail-compose" and v.scope == "model"


def render_view_router(
    views: Tuple[ViewSpec, ...], schema_sha: str, views_sha: str,
    chrome_views: "frozenset[str]" = frozenset(),
) -> str:
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
        elif v.kind == "rendered-content":  # AR-6: a bare list + ?id= prose detail
            import_lines.append(
                f"from app.views.{v.module} import {v.module}_data, {v.module}_list"
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
            if v.module in chrome_views:  # Phase-2 export landing: a bare HTML page for /export
                routes.append(
                    f"@views_router.get({(base or '/')!r}, response_class=HTMLResponse)\n"
                    f"def {v.module}(request: Request):\n"
                    f"    return _templates.TemplateResponse(request, {('views/' + v.module + '.html')!r}, {{}})"
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
        elif v.kind == "rendered-content":  # AR-6: bare list (kind + preview); ?id= prose detail
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(request: Request, id: Optional[str] = None, "
                "session: Session = Depends(get_session)):\n"
                f"    if id is None:\n"
                f"        rows = {v.module}_list(session)\n"
                f"        return _templates.TemplateResponse(request, {tmpl!r}, "
                f"{{'rows': rows, 'data': None, 'detail_route': {v.route!r}}})\n"
                f"    data = {v.module}_data(session, id)\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, "
                "{'rows': None, 'data': data})"
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
        (v.kind == "detail-compose" and "{" not in v.route and not _is_model_compose(v))
        or v.kind == "rendered-content"
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


# --------------------------------------------------------------------------- #
# View prose (view-chrome copy) — title/intro from a standalone view_prose.yaml,
# rendered into an UNTRACKED fragment the owned template {% include %}s. The include
# is emitted ONLY when prose exists for the view, so no-prose output is byte-identical
# to today (the include line never names the title text → editing copy never drifts).
# --------------------------------------------------------------------------- #

def _view_title_block(v: ViewSpec, has_prose: bool) -> str:
    """The view's heading line. With prose → include the untracked fragment; without → today's literal.

    The two branches are byte-distinct, but the include line is **content-independent** (it carries no
    title text), so editing ``view_prose.yaml`` only rewrites the fragment and never changes this owned
    template. With no prose for the view, this returns the exact pre-feature literal.
    """
    if has_prose:
        return '{% include "views/_' + v.module + '.prose.html" %}\n'
    return f"<h1>{v.module}</h1>\n"


def render_view_prose_fragment(prose, fallback_title: str) -> str:
    """The untracked view-chrome fragment (``app/templates/views/_<name>.prose.html``). No header.

    Generate-time render: an escaped ``<h1>`` title (``prose.title`` or the view's machine name as
    fallback) + an optional markdown-rendered intro. Not drift-tracked (no provenance header), so editing
    ``view_prose.yaml`` never flags drift; overwritten on every regenerate. Mirrors
    ``pages_generator.render_page_body_fragment``.
    """
    import html

    title = prose.title if (prose and prose.title) else fallback_title
    parts = [f"<h1>{html.escape(title)}</h1>\n"]
    if prose and prose.intro:
        from ..backend_codegen.pages_generator import render_markdown

        parts.append(f'<div class="view-intro">{render_markdown(prose.intro)}</div>\n')
    return "".join(parts)


def render_view_empty_fragment(prose) -> str:
    """The untracked no-rows fragment (``app/templates/views/_<name>.empty.html``). No header.

    Holds only the escaped ``empty`` copy; the owned template wraps the include in its own
    ``{% if not rows %}`` so the structural condition stays hashed while the *words* do not. Editing the
    ``empty`` text only rewrites this fragment ⇒ ``--check`` stays green. Phase 2 (model-compose only).
    """
    import html

    return f'<p class="empty">{html.escape(prose.empty)}</p>\n'


def _view_empty_block(v: ViewSpec, default_html: str, has_empty: bool) -> str:
    """The model-compose no-rows line: include the untracked empty fragment when authored, else today's
    literal (byte-identical when absent). The ``{% if not rows %}`` guard stays in the owned template."""
    if has_empty:
        return '{% if not rows %}{% include "views/_' + v.module + '.empty.html" %}{% endif %}\n'
    return default_html


def render_export_landing_template(v: ViewSpec, schema_sha: str, views_sha: str) -> str:
    """Owned HTML landing for a model-scoped export-package (Phase 2). Emitted ONLY when the export
    view has title/intro prose — so ``/export`` (a 404 today) becomes a page that explains the export
    and links the two download formats. The heading/intro come from the untracked prose fragment
    (``{% include %}``); the two format links are fixed structure (their *labels* are a later
    ``controls`` increment). Byte-identical-when-absent holds because this whole file is opt-in.
    """
    head = (
        "{#\n"
        "# GENERATED from prisma/schema.prisma (+ views.yaml) — do not edit by hand.\n"
        "# startd8-artifact: view-template\n"
        f"# startd8-entity: {v.module}\n"
        f"# schema-sha256: {schema_sha}\n"
        f"# views-sha256: {views_sha}\n"
        "#}\n"
    )
    base = v.route.rstrip("/")
    block = (
        '{% extends "base.html" %}\n{% block content %}\n'
        + _view_title_block(v, True)  # landing exists only with chrome ⇒ always the fragment include
        + '<ul class="export-formats">\n'
        + f'  <li><a href="{base}/markdown">Download as Markdown</a></li>\n'
        + f'  <li><a href="{base}/json">Download as JSON</a></li>\n'
        + "</ul>\n"
        + "{% endblock %}\n"
    )
    return head + block


def render_view_index_template(
    v: ViewSpec, schema_sha: str, views_sha: str, has_prose: bool = False
) -> str:
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
        + _view_title_block(v, has_prose)
        + "{% if not roots %}<p>Nothing here yet — add and confirm a "
        f"{v.root} first.</p>{{% endif %}}\n"
        "<ul>\n"
        "{% for r in roots %}"
        '<li><a href="{{ detail_route }}?id={{ r.id }}">'
        "{{ r.name or r.title or r.headline or r.id }}</a></li>\n"
        "{% endfor %}\n"
        "</ul>\n"
        "{% endblock %}\n"
    )


def render_view_template(
    v: ViewSpec, schema_sha: str, views_sha: str, schema=None, view_display=None,
    has_prose: bool = False, has_empty: bool = False,
) -> str:
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
            + _view_title_block(v, has_prose) +
            "{% for stage, rows in rows %}<section><h2>{{ stage }}</h2>\n"
            "<ul>{% for r in rows %}<li>{{ r.id }}</li>{% endfor %}</ul></section>{% endfor %}\n"
            "{% endblock %}\n"
        )
    elif v.kind == "workspace":
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            + _view_title_block(v, has_prose) +
            "<ul>{% for r in data.resolved %}<li>{% if r.dangling %}⚠ dangling{% else %}{{ r.entity.id }}{% endif %}</li>{% endfor %}</ul>\n"
            "{% endblock %}\n"
        )
    elif v.kind == "rendered-content":  # AR-6: list (kind + preview) | detail (prose + copy)
        # Detail (data set): the prose under its kind heading — rendered HTML, NO JSON, NO trace
        # ids; a copy-to-clipboard control carries the body as plain text. Empty body -> empty
        # state, never an error. List (rows set): kind + a prose preview, never JSON.
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            "{% if data %}\n"
            "<article>\n"
            "<h1>{{ data.kind }}</h1>\n"
            "{% if data.html %}\n"
            '<div class="prose">{{ data.html | safe }}</div>\n'
            '<button type="button" class="copy" '
            'data-copy="{{ data.body }}" onclick="navigator.clipboard.writeText('
            "this.getAttribute('data-copy'))\">Copy</button>\n"
            "{% else %}\n"
            '<p class="empty">Nothing to read yet.</p>\n'
            "{% endif %}\n"
            "</article>\n"
            "{% else %}\n"
            + _view_title_block(v, has_prose) +
            "{% if not rows %}<p class=\"empty\">Nothing here yet.</p>{% endif %}\n"
            "<ul>\n"
            "{% for r in rows %}"
            '<li><a href="{{ detail_route }}?id={{ r.id }}"><strong>{{ r.kind }}</strong>'
            " — {{ r.preview }}</a></li>\n"
            "{% endfor %}\n"
            "</ul>\n"
            "{% endif %}\n"
            "{% endblock %}\n"
        )
    elif _is_model_compose(v):  # AR-1: every root on one page; meaningful empty state; unlinked flagged
        # FR-DM-6: bound relations render the resolved target label ({{ x.label }}); the group
        # heading uses the root's label when display.yaml sets root_label_field. Unbound → id (today).
        resolved = _resolved_rel_map(v, view_display, schema)
        rel_lines = "".join(
            (f"<h3>{r.name}</h3>\n<ul>{{% for x in item.{r.name} %}}<li>"
             + ("{{ x.label }}" if r.name in resolved else "{{ x.id }}")
             + "</li>{% endfor %}</ul>\n")
            for r in v.relations
        )
        heading = "{{ item.root_label }}" if (view_display and view_display.root_label_field) else "{{ item.root.id }}"
        unlinked = (
            '{% if not item.linked %}<p class="unlinked">not yet linked</p>{% endif %}\n'
            if v.relations else ""
        )
        empty_default = (
            f'{{% if not rows %}}<p class="empty">No {v.root} records yet — add one to start the map.</p>{{% endif %}}\n'
        )
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            + _view_title_block(v, has_prose)
            + _view_empty_block(v, empty_default, has_empty)
            + "{% for item in rows %}<section><h2>" + heading + "</h2>\n"
            + unlinked + rel_lines +
            "</section>{% endfor %}\n"
            "{% endblock %}\n"
        )
    elif v.kind == "detail-compose":
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            + _view_title_block(v, has_prose) +
            "<p>{{ data.root.id }}</p>\n"
            "{% for name, shown in data.panels.items() %}{% if shown %}<section><h2>{{ name }}</h2></section>{% endif %}{% endfor %}\n"
            "{% endblock %}\n"
        )
    elif v.kind == "computed-panel":  # AR-2: score + ordered nudges (guidance, never a gate)
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            + _view_title_block(v, has_prose) +
            '<p class="score">{{ (data.score * 100) | round | int }}%</p>\n'
            '{% if data.nudges %}<ul class="nudges">{% for n in data.nudges %}<li>{{ n }}</li>{% endfor %}</ul>\n'
            '{% else %}<p class="complete">All signals met.</p>{% endif %}\n'
            "{% endblock %}\n"
        )
    elif v.kind == "import-flow":  # AR-4: upload form; restore demands the explicit confirm tick
        base = v.route.rstrip("/")
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            + _view_title_block(v, has_prose) +
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
            + _view_title_block(v, has_prose) +
            "{% endblock %}\n"
        )
    else:  # dashboard
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            + _view_title_block(v, has_prose) +
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
    blocks = [_render_view_test(schema, v, views) for v in views]
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


def _render_view_test(schema, v: ViewSpec, views: Tuple[ViewSpec, ...] = ()) -> str:
    if _is_model_export(v):
        return _render_model_export_test(schema, v, _prose_content_specs(views))
    if _is_model_compose(v):
        return _render_model_compose_test(schema, v)
    if v.kind == "computed-panel":
        return _render_computed_panel_test(schema, v)
    if v.kind == "import-flow":
        return _render_import_flow_test(schema, v)
    if v.kind == "rendered-content":
        return _render_rendered_content_test(schema, v)
    if v.kind == "board" and v.columns_from:
        return _render_entity_board_test(schema, v)
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


def _render_rendered_content_test(schema, v: ViewSpec) -> str:
    """Rendered-content test (AR-6 / FR-16): the detail renders body-as-PROSE (not JSON, no trace
    ids), the list shows kind + a prose preview, copy yields plain text, an empty/missing body is
    the empty state — proven against a row whose JSON column holds ``{body, traces}``."""
    cf, pk = v.content_field, v.prose_key
    # A known prose body + a trace id that MUST NOT leak into the rendered prose.
    body_text = "Lead with the win. Then the proof.\n\nClose with the ask."
    trace_id = "cap-trace-xyz"
    # Valid JSON (json.dumps — NOT repr, which emits single-quoted non-JSON the
    # prose renderer can't parse): this is the shape generate_artifacts emits.
    payload = json.dumps({pk: body_text, "traces": [trace_id]})
    return "\n".join([
        f"def test_{v.module}_renders_prose_not_json(tmp_path):",
        "    import app.tables as t",
        f"    from app.views.{v.module} import {v.module}_data, {v.module}_list",
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    with Session(engine) as s:",
        _seed(schema, "row", v.root, {cf: repr(payload), "kind": repr("value-summary")}),
        _seed(schema, "blank", v.root, {cf: repr("")}),  # empty body -> empty state, never errors
        f"        detail = {v.module}_data(s, row.id)",
        f"        empty = {v.module}_data(s, blank.id)",
        f"        listing = {v.module}_list(s)",
        f"        missing = {v.module}_data(s, 'no-such-id')",
        "    # detail: body is the verbatim prose (copy yields THIS, plain text, no markup)",
        f"    assert detail['body'] == {body_text!r}",
        "    # the rendered html is PROSE — contains the words, never the JSON braces or trace ids",
        '    assert "Lead with the win" in detail["html"]',
        '    assert "<p>" in detail["html"]            # rendered as paragraphs',
        '    assert "{" not in detail["html"]          # no raw JSON leaked',
        f"    assert {trace_id!r} not in detail['html']  # no visible trace ids (FR-16)",
        f"    assert {trace_id!r} not in detail['body']",
        "    # list: kind + a prose preview, never the JSON blob",
        "    assert any(r['kind'] == 'value-summary' for r in listing)",
        f"    assert all({trace_id!r} not in r['preview'] for r in listing)",
        '    assert any("Lead with the win" in r["preview"] for r in listing)',
        "    # empty/missing body -> empty state, not an error",
        "    assert empty['body'] == '' and empty['html'] == ''",
        "    assert missing['body'] == '' and missing['html'] == ''",
    ])


def _render_entity_board_test(schema, v: ViewSpec) -> str:
    """Entity-backed board test (FR-EB): columns come from a related entity's runtime rows ordered
    by ``order_by``; reordering a position reorders the columns with NO regeneration; an unmatched
    root lands in the Unassigned tail (no row lost)."""
    cf, ob, gb = v.columns_from, v.order_by, v.group_by
    # Seed two column rows OUT of position order (c_b created first, position 2) so passing the
    # assertion requires the data fn to actually sort by order_by, not insertion order.
    return "\n".join([
        f"def test_{v.module}_data(tmp_path):",
        "    import app.tables as t",
        f"    from app.views.{v.module} import {v.module}_data",
        '    engine = create_engine(f"sqlite:///{tmp_path}/v.db")',
        "    SQLModel.metadata.create_all(engine)",
        "    with Session(engine) as s:",
        _seed(schema, "c_b", cf, {ob: "2", "name": repr("Second")}),
        _seed(schema, "c_a", cf, {ob: "1", "name": repr("First")}),
        _seed(schema, "_r_a", v.root, {gb: "c_a.id"}),
        _seed(schema, "_r_b", v.root, {gb: "c_b.id"}),
        _seed(schema, "_r_orphan", v.root, {gb: repr("no-such-column")}),
        f"        board = {v.module}_data(s)",
        "        labels = [label for label, _ in board]",
        "        # columns appear in order_by (position) order, not insertion order",
        '        assert labels[:2] == ["First", "Second"]',
        "        cols = dict(board)",
        '        assert len(cols["First"]) == 1 and len(cols["Second"]) == 1  # grouped by ref',
        '        assert "Unassigned" in cols and len(cols["Unassigned"]) == 1  # orphan kept, not lost',
        "        # reorder a position -> the columns reorder with NO regeneration (columns are data)",
        f"        c_a.{ob} = 9",
        "        s.add(c_a); s.commit()",
        f"        reordered = [label for label, _ in {v.module}_data(s)]",
        '        assert reordered[:2] == ["Second", "First"]  # First now sorts last',
        "    assert board is not None",
    ])


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


def _render_model_export_test(schema, v: ViewSpec, prose_specs: Tuple[ViewSpec, ...] = ()) -> str:
    """Model-export test: whole-model coverage + JSON round-trip through app/export.py's shape,
    plus the FR-10 conformance pin — when the manifest declares a rendered-content entity, the
    Markdown export contains that entity's prose VERBATIM (rendered as prose, not a JSON dump)."""
    first = next(iter(schema.models))
    lines = [
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
    ]
    # FR-10: seed each rendered-content entity with a known JSON-stored body, then assert the
    # markdown export carries that prose verbatim (not the {body, traces} JSON blob).
    pin = prose_specs[0] if prose_specs else None
    if pin is not None:
        prose_body = "Our edge in one line. The proof in the next."
        trace = "trace-deadbeef"
        payload_json = json.dumps({pin.prose_key: prose_body, "traces": [trace]})
        lines.append(
            _seed(schema, "_art", pin.root, {pin.content_field: repr(payload_json)})
        )
    lines += [
        f"        payload = {v.module}_payload(s)",
        f"        exported_json = {v.module}_json(s)",
        f"        exported_md = {v.module}_markdown(s)",
        "    assert set(payload) == set(ENTITY_ORDER)  # whole model: every entity present",
        f"    assert len(payload[{first!r}]) == 1",
        "    restored = json.loads(exported_json)  # round-trip: entity name -> list of row dicts",
        "    assert set(restored) == set(payload)",
        f"    assert restored[{first!r}][0]['id'] == root.id  # field-faithful, restorable (AR-4)",
        f"    assert '# ' + {first!r} in exported_md  # a markdown section per entity",
    ]
    if pin is not None:
        lines += [
            f"    assert {prose_body!r} in exported_md  # FR-10: artifact prose VERBATIM in the export",
            f"    assert {trace!r} not in exported_md   # the JSON traces are NOT dumped",
        ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def render_views(
    schema_text: str, views_text: str, display_text: Optional[str] = None,
    view_prose_text: Optional[str] = None,
) -> Tuple[Tuple[str, str], ...]:
    """Every composite-view artifact as ``(relative_path, text)`` pairs.

    ``known_entities`` for strict validation is derived from the schema (reuses the parser via
    ``backend_codegen`` would cause a cycle, so we parse names cheaply here). *display_text*
    (``display.yaml``) drives FR-DM-6 composite-view label resolution (via_fk → target → label).
    *view_prose_text* (``view_prose.yaml``) supplies view-chrome copy (title/intro): when a view has
    prose, its owned template ``{% include %}``s an untracked fragment (also emitted here); absent ⇒
    byte-identical to today. Threaded to the drift checker too (``views_in_sync``) so the include line
    re-renders identically — prose *content* never enters the hash, only its *presence* affects the
    owned template, and that is a structural regen correctly caught by ``--check``.
    """
    from ..languages.prisma_parser import parse_prisma_schema
    from .view_prose import parse_view_prose

    schema = parse_prisma_schema(schema_text)
    view_displays: Dict[str, object] = {}
    if display_text:
        from ..backend_codegen.display_manifest import parse_display
        _, view_displays = parse_display(display_text, schema)
    known = frozenset(schema.models)
    # Field-level loud-fail for AR-6 content_field: entity -> its scalar field names.
    known_fields = {
        name: frozenset(f.name for f in schema.scalar_fields(name)) for name in schema.models
    }
    views = parse_views(views_text, known_entities=known, known_fields=known_fields)
    view_prose = parse_view_prose(
        view_prose_text, known_views=frozenset(v.module for v in views)
    )
    # Surface guard (loud-fail rather than silently drop authored prose): `empty` only has a clean
    # no-rows surface on a model-scoped detail-compose today. (A model-scoped export's title/intro DO
    # have a surface now — the Phase-2 export landing page below; but an export has no row list, so
    # `empty` on one still fails here.)
    for v in views:
        p = view_prose.get(v.module)
        if p is not None and p.empty and not _is_model_compose(v):
            raise ValueError(
                f"view_prose.yaml: view {v.module!r} uses `empty`, but only a model-scoped "
                "detail-compose has a no-rows surface today (Phase 2 will add the others)"
            )
    s_sha, v_sha = schema_sha256(schema_text), schema_sha256(views_text)

    out: List[Tuple[str, str]] = [("app/views/__init__.py", "")]
    # The single prose-from-JSON renderer (AR-6 / FR-16): emitted only when a rendered-content view
    # exists, so manifests without one render byte-identically. Shared by the view AND the FR-10
    # model export — never duplicated.
    if _prose_content_specs(views):
        out.append((
            "app/views/_prose.py",
            _header(s_sha, v_sha, "view-prose-helper") + "\n\n" + _PROSE_MODULE,
        ))
    for v in views:
        vd = view_displays.get(v.module)            # FR-DM-6: per-view display (None ⇒ today's output)
        prose = view_prose.get(v.module)            # view-chrome copy (None ⇒ today's literal output)
        # The heading include fires on title/intro presence; `empty` is independent (a view may carry
        # only `empty`, leaving its title literal). Both default off ⇒ byte-identical when absent.
        has_chrome = bool(prose and (prose.title or prose.intro))
        has_empty = bool(prose and prose.empty)
        out.append((_module_path(v), render_view_module(
            v, s_sha, v_sha, schema=schema, views=views, view_display=vd)))
        if _is_model_export(v):
            # Served as raw Markdown/JSON (no template) — UNLESS the export carries title/intro, in
            # which case it opts into a Phase-2 HTML landing page (+ a bare route, see render_view_router).
            if has_chrome:
                out.append((f"app/templates/views/{v.module}.html",
                            render_export_landing_template(v, s_sha, v_sha)))
                out.append((f"app/templates/views/_{v.module}.prose.html",
                            render_view_prose_fragment(prose, v.module)))
            continue
        out.append((f"app/templates/views/{v.module}.html",
                    render_view_template(v, s_sha, v_sha, schema=schema, view_display=vd,
                                         has_prose=has_chrome, has_empty=has_empty)))
        # Untracked fragments (no header ⇒ not owned files ⇒ skipped by drift/--check).
        if has_chrome:
            out.append((f"app/templates/views/_{v.module}.prose.html",
                        render_view_prose_fragment(prose, v.module)))
        if has_empty:
            out.append((f"app/templates/views/_{v.module}.empty.html",
                        render_view_empty_fragment(prose)))
        if v.kind == "detail-compose" and "{" not in v.route:
            out.append((
                f"app/templates/views/{v.module}_index.html",
                render_view_index_template(v, s_sha, v_sha, has_prose=has_chrome),
            ))
    # The router gains a bare HTML landing route only for export views that carry chrome (others
    # unchanged ⇒ byte-identical when no export prose, incl. all Phase-1 manifests).
    chrome_views = frozenset(
        name for name, p in view_prose.items() if p.title or p.intro
    )
    out.append(("app/views/routes.py", render_view_router(views, s_sha, v_sha, chrome_views)))
    out.append(("tests/test_views.py", render_view_tests(views, schema, s_sha, v_sha)))
    return tuple(out)
