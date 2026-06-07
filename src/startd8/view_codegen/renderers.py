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


def _render_detail_compose(v: ViewSpec) -> str:
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
        "",
        f"__all__ = [{(v.module + '_data')!r}]", "",
    ]
    return "\n".join(lines)


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
}

# Kinds that take a ``/{id}`` route -> their data/package fn is called with the path id.
_ID_ROUTED = {"workspace", "detail-compose", "export-package"}


def render_view_module(v: ViewSpec, schema_sha: str, views_sha: str) -> str:
    body = _MODULE_RENDERERS[v.kind](v)
    return _header(schema_sha, views_sha, "view-module") + "\n\n" + body


# --------------------------------------------------------------------------- #
# Router + templates + tests
# --------------------------------------------------------------------------- #

def _is_model_export(v: ViewSpec) -> bool:
    return v.kind == "export-package" and v.scope == "model"


def render_view_router(views: Tuple[ViewSpec, ...], schema_sha: str, views_sha: str) -> str:
    import_lines: List[str] = []
    for v in views:
        if _is_model_export(v):
            import_lines.append(
                f"from app.views.{v.module} import {v.module}_json, {v.module}_markdown"
            )
        elif v.kind == "export-package":
            import_lines.append(f"from app.views.{v.module} import {v.module}_package")
        else:
            import_lines.append(f"from app.views.{v.module} import {v.module}_data")
    imports = "\n".join(import_lines)
    # `Response` (raw-body JSON/Markdown) is only imported when a model-scoped export needs it,
    # keeping the router byte-identical for manifests without one.
    responses = (
        "from fastapi.responses import HTMLResponse, Response\n"
        if any(_is_model_export(v) for v in views)
        else "from fastapi.responses import HTMLResponse\n"
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
        elif v.kind in _ID_ROUTED:  # workspace / detail-compose -> HTML, /{id}
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(id: str, request: Request, session: Session = Depends(get_session)):\n"
                f"    data = {v.module}_data(session, id)\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, {{'data': data}})"
            )
        else:
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(request: Request, session: Session = Depends(get_session)):\n"
                f"    rows = {v.module}_data(session)\n"
                f"    return _templates.TemplateResponse(request, {tmpl!r}, {{'rows': rows}})"
            )
    body = (
        "from __future__ import annotations\n\n"
        "from fastapi import APIRouter, Depends, Request\n"
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
    elif v.kind == "detail-compose":
        block = (
            '{% extends "base.html" %}\n{% block content %}\n'
            f"<h1>{v.module}</h1>\n"
            "<p>{{ data.root.id }}</p>\n"
            "{% for name, shown in data.panels.items() %}{% if shown %}<section><h2>{{ name }}</h2></section>{% endif %}{% endfor %}\n"
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


def render_view_tests(views: Tuple[ViewSpec, ...], schema, schema_sha: str, views_sha: str) -> str:
    """Rung-4 view tests — exercise each data function against a fixtured DB (the D1 gate)."""
    blocks = [_render_view_test(schema, v) for v in views]
    preamble = (
        _TEST_SHIM + "\n"
        "import pytest\n\n"
        'pytest.importorskip("sqlmodel")\n\n'
        "from sqlmodel import Session, SQLModel, create_engine  # noqa: E402"
    )
    header = _header(schema_sha, views_sha, "view-tests")
    body = preamble + ("\n\n\n" + "\n\n\n".join(blocks) if blocks else "\n")
    return header + "\n\n" + body + "\n"


def _render_view_test(schema, v: ViewSpec) -> str:
    if _is_model_export(v):
        return _render_model_export_test(schema, v)
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
        out.append((_module_path(v), render_view_module(v, s_sha, v_sha)))
        if _is_model_export(v):
            continue  # served as raw Markdown/JSON responses — no template at all (AR-3)
        out.append((f"app/templates/views/{v.module}.html", render_view_template(v, s_sha, v_sha)))
    out.append(("app/views/routes.py", render_view_router(views, s_sha, v_sha)))
    out.append(("tests/test_views.py", render_view_tests(views, schema, s_sha, v_sha)))
    return tuple(out)
