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
    return "\n".join([
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
        '    return {"root": root, "resolved": resolved}', "",
        f"__all__ = [{(v.module + '_data')!r}]", "",
    ])


_MODULE_RENDERERS = {
    "dashboard": _render_dashboard,
    "board": _render_board,
    "workspace": _render_workspace,
}


def render_view_module(v: ViewSpec, schema_sha: str, views_sha: str) -> str:
    body = _MODULE_RENDERERS[v.kind](v)
    return _header(schema_sha, views_sha, "view-module") + "\n\n" + body


# --------------------------------------------------------------------------- #
# Router + templates + tests
# --------------------------------------------------------------------------- #

def render_view_router(views: Tuple[ViewSpec, ...], schema_sha: str, views_sha: str) -> str:
    imports = "\n".join(f"from app.views.{v.module} import {v.module}_data" for v in views)
    routes: List[str] = []
    for v in views:
        tmpl = f"views/{v.module}.html"
        if v.kind == "workspace":
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(id: str, request: Request, session: Session = Depends(get_session)):\n"
                f"    data = {v.module}_data(session, id)\n"
                f"    return _templates.TemplateResponse({tmpl!r}, {{'request': request, 'data': data}})"
            )
        else:
            routes.append(
                f"@views_router.get({v.route!r}, response_class=HTMLResponse)\n"
                f"def {v.module}(request: Request, session: Session = Depends(get_session)):\n"
                f"    rows = {v.module}_data(session)\n"
                f"    return _templates.TemplateResponse({tmpl!r}, {{'request': request, 'rows': rows}})"
            )
    body = (
        "from __future__ import annotations\n\n"
        "from fastapi import APIRouter, Depends, Request\n"
        "from fastapi.responses import HTMLResponse\n"
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
    setup = [
        f"def test_{v.module}_data(tmp_path):",
        "    import app.tables as t",
        f"    from app.views.{v.module} import {v.module}_data",
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
    else:  # workspace — the key test: resolution + dangling flag
        p = v.polymorphic
        first_type, first_entity = p.type_map[0]
        setup += [
            _seed(schema, "root", v.root, {}),
            _seed(schema, "ent", first_entity, {}),
            _seed(schema, "_good", p.of, {p.fk: "root.id", p.type_field: repr(first_type), p.id_field: "ent.id"}),
            _seed(schema, "_dangling", p.of, {p.fk: "root.id", p.type_field: repr(first_type), p.id_field: "'nope'"}),
            f"        data = {v.module}_data(s, root.id)",
            "    resolved = data['resolved']",
            "    assert any(not r['dangling'] for r in resolved)  # the real ref resolves",
            "    assert any(r['dangling'] for r in resolved)       # the bad ref is flagged, not crashed",
        ]
    return "\n".join(setup)


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
        out.append((f"app/templates/views/{v.module}.html", render_view_template(v, s_sha, v_sha)))
    out.append(("app/views/routes.py", render_view_router(views, s_sha, v_sha)))
    out.append(("tests/test_views.py", render_view_tests(views, schema, s_sha, v_sha)))
    return tuple(out)
