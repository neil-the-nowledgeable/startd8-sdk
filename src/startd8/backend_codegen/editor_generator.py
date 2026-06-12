"""Bulk child-field editor generation (FR-ED-1..16) — the ``editors:`` archetype.

An editor edits ONE field (``edit_field``) across a parent's filtered, grouped children in one
form/POST, with reset-to-default. The SDK owns the route pair + template + mount; the only app seam is
an optional ``default_value`` resolver (the ``flows:`` ``on_finish`` precedent). Deterministic, $0.

Generated per editor:
- ``app/editors/<name>.py`` — GET (scoped query → grouped form, pre-filled) + POST (dirty-detect vs the
  submitted default mirror, reset→NULL, server-side id + field allow-list, one txn, PRG).
- ``app/templates/editors/<name>/form.html`` — one ``<textarea>`` per child + a hidden ``default-<id>``
  mirror (FR-ED-12: the POST comparand, never a resolver recompute).
- ``app/editors/__init__.py`` — the ``editor_routers`` aggregator main.py mounts tolerantly.
"""

from __future__ import annotations

import warnings
from typing import List, Optional, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ..languages.prisma_parser import parse_prisma_schema
from ._headers import header_forms, header_forms_tmpl
from .crud_generator import _pk_field
from .editors_manifest import EditorSpec, parse_editors


def _validate_editor(schema, spec: EditorSpec) -> None:
    """Loud contract validation (FR-ED-3): entities/columns exist; route shape; /ui collision warn."""
    parent = schema.model(spec.parent)
    if parent is None:
        raise ValueError(f"editor {spec.name!r}: unknown parent entity {spec.parent!r}")
    child = schema.model(spec.child)
    if child is None:
        raise ValueError(f"editor {spec.name!r}: unknown child entity {spec.child!r}")
    for label, col in (("fk", spec.fk), ("edit_field", spec.edit_field)):
        if child.field(col) is None:
            raise ValueError(
                f"editor {spec.name!r}: {label} {col!r} is not a column on {spec.child}"
            )
    for label, col in (("group_by", spec.group_by), ("order_by", spec.order_by)):
        if col and child.field(col) is None:
            raise ValueError(
                f"editor {spec.name!r}: {label} {col!r} is not a column on {spec.child}"
            )
    for col in spec.filter_map:
        if child.field(col) is None:
            raise ValueError(
                f"editor {spec.name!r}: filter column {col!r} is not a column on {spec.child}"
            )
    # FR-ED-2 / OQ-8: exactly one `{id}` placeholder, and no other `{...}` braces.
    if spec.route.count("{") != 1 or "{id}" not in spec.route:
        raise ValueError(
            f"editor {spec.name!r}: route {spec.route!r} must contain exactly one `{{id}}` placeholder"
        )
    if spec.route.startswith("/ui/"):
        warnings.warn(
            f"editor {spec.name!r}: route {spec.route!r} starts with /ui/ (CRUD namespace) — "
            f"likely route collision",
            stacklevel=2,
        )


def render_editor_router(schema_text: str, views_text: str, spec: EditorSpec) -> str:
    """``app/editors/<name>.py`` — GET grouped editor + POST bulk save (FR-ED-4/5/6/9/12/14)."""
    schema = parse_prisma_schema(schema_text)
    _validate_editor(schema, spec)
    header = header_forms(
        "prisma/schema.prisma", schema_sha256(schema_text), schema_sha256(views_text),
        "fastapi-editor", entity=spec.name,
    )
    n = spec.name
    parent, child = spec.parent, spec.child
    pk = _pk_field(schema, child)
    pkname = pk.name if pk is not None else "id"
    ef = spec.edit_field
    has_group = bool(spec.group_by)

    # tolerant resolver seam (FR-ED-9): present → pre-fill/reset target; absent → raw edit_field
    resolver_import = (
        f"try:  # tolerant default_value resolver (owned fn; absent → raw edit_field) — FR-ED-9\n"
        f"    from app.editors.resolvers import {spec.default_value} as _resolve_default\n"
        f"except Exception:  # noqa: BLE001\n"
        f"    _resolve_default = None\n\n"
        if spec.default_value else "_resolve_default = None\n\n"
    )

    # filter equality clauses (own-column == literal); identical expr drives GET render + POST allow-list
    filter_clauses = "".join(
        f"    stmt = stmt.where({child}.{col} == {value!r})\n" for col, value in spec.filter
    )
    order_clause = f"    stmt = stmt.order_by({child}.{spec.order_by})\n" if spec.order_by else ""
    group_expr = f"getattr(child, {spec.group_by!r})" if has_group else "None"

    body = (
        "from __future__ import annotations\n\n"
        "import logging\n"
        "from pathlib import Path\n\n"
        "from fastapi import APIRouter, Depends, HTTPException, Request\n"
        "from fastapi.responses import HTMLResponse, RedirectResponse\n"
        "from fastapi.templating import Jinja2Templates\n"
        "from sqlmodel import Session, select\n\n"
        "from app.db import get_session\n"
        f"from app.tables import {parent}, {child}\n\n"
        "logger = logging.getLogger(__name__)\n"
        'templates = Jinja2Templates(directory=str(Path(__file__).resolve().parents[1] / "templates"))\n\n'
        + resolver_import
        + f'editor_{n}_router = APIRouter(tags=["editor:{n}"])\n\n\n'
        # server-derived editable set — the SAME WHERE for GET (render) and POST (allow-list), FR-ED-14
        f"def _editable_{n}(parent_id, session):\n"
        f"    stmt = select({child}).where({child}.{spec.fk} == parent_id)\n"
        + filter_clauses
        + order_clause
        + "    return list(session.exec(stmt).all())\n\n\n"
        # pre-fill/reset default — resolver if present (per-row guarded), else raw edit_field (FR-ED-9/12)
        f"def _default_for_{n}(child, session):\n"
        f"    if _resolve_default is not None:\n"
        f"        try:\n"
        f"            return _resolve_default(child, session)\n"
        f"        except Exception:  # noqa: BLE001 — one bad row must not blank the whole form (FR-ED-9)\n"
        f'            logger.exception("editor {n}: default_value resolver failed for a row")\n'
        f"    val = getattr(child, {ef!r})\n"
        f'    return val if val is not None else ""\n\n\n'
        f"def _norm(s):  # FR-ED-12: normalize one trailing newline (<textarea> appends one)\n"
        f'    s = s or ""\n'
        f'    return s[:-1] if s.endswith("\\n") else s\n\n\n'
        f"def _group_{n}(rows):\n"
        + (
            "    groups, index = [], {}\n"
            "    for r in rows:\n"
            '        k = r["group"]\n'
            "        if k not in index:\n"
            "            index[k] = len(groups)\n"
            '            groups.append({"key": k, "rows": []})\n'
            '        groups[index[k]]["rows"].append(r)\n'
            "    return groups\n\n\n"
            if has_group
            else '    return [{"key": None, "rows": rows}]\n\n\n'
        )
        # GET — render the grouped, pre-filled form (FR-ED-4)
        + f'@editor_{n}_router.get("{spec.route}", response_class=HTMLResponse)\n'
        f"def edit_{n}(id: str, request: Request, session: Session = Depends(get_session)):\n"
        f"    parent = session.get({parent}, id)\n"
        f"    if parent is None:\n"
        f'        raise HTTPException(status_code=404, detail="{parent} not found")\n'
        f"    rows = []\n"
        f"    for child in _editable_{n}(id, session):\n"
        f"        rows.append({{\n"
        f"            \"id\": str(getattr(child, {pkname!r})),\n"
        f"            \"default\": _default_for_{n}(child, session),\n"
        f"            \"group\": {group_expr},\n"
        f"        }})\n"
        f"    return templates.TemplateResponse(\n"
        f'        request, "editors/{n}/form.html",\n'
        f'        {{"parent_id": id, "groups": _group_{n}(rows), "label": {spec.label!r}}},\n'
        f"    )\n\n\n"
        # POST — bulk save with dirty-detect, reset, and row+field allow-list (FR-ED-5/6/12/14)
        + f'@editor_{n}_router.post("{spec.route}")\n'
        f"async def save_{n}(id: str, request: Request, session: Session = Depends(get_session)):\n"
        f"    parent = session.get({parent}, id)\n"
        f"    if parent is None:\n"
        f'        raise HTTPException(status_code=404, detail="{parent} not found")\n'
        f"    editable = {{str(getattr(c, {pkname!r})): c for c in _editable_{n}(id, session)}}\n"
        f"    form = await request.form()\n"
        f"    for key in form:\n"
        f'        if not key.startswith("item-"):  # field-level scope: only item-<id> (FR-ED-14)\n'
        f"            continue\n"
        f'        cid = key[len("item-"):]\n'
        f"        child = editable.get(cid)\n"
        f"        if child is None:  # id not in the server-derived set → ignore (IDOR/mass-assign guard)\n"
        f"            continue\n"
        f'        submitted = form.get(key) or ""\n'
        f'        mirror = form.get("default-" + cid, "") or ""\n'
        f"        if _norm(submitted) == _norm(mirror):  # unchanged → no write (preserve NULL/source)\n"
        f"            continue\n"
        + (
            f'        if submitted.strip() == "":  # empty → reset to default (FR-ED-6)\n'
            f"            setattr(child, {ef!r}, None)\n"
            f"        else:\n"
            f"            setattr(child, {ef!r}, submitted)\n"
            if spec.reset_to_default
            else f"        setattr(child, {ef!r}, submitted)\n"
        )
        + f"        session.add(child)\n"
        f"    session.commit()\n"
        f'    return RedirectResponse(f"{spec.route}", status_code=303)\n'
    )
    return header + "\n\n" + body


def render_editor_form(schema_text: str, views_text: str, spec: EditorSpec) -> str:
    """``app/templates/editors/<name>/form.html`` — grouped textareas + hidden default mirror (FR-ED-7/12)."""
    n = spec.name
    header = header_forms_tmpl(
        "prisma/schema.prisma", schema_sha256(schema_text), schema_sha256(views_text),
        "editor-form", entity=n,
    )
    action = spec.route.replace("{id}", "{{ parent_id }}")
    return (
        header + "\n"
        '{% extends "base.html" %}\n'
        "{% block title %}{{ label }}{% endblock %}\n"
        "{% block content %}\n"
        "<h1>{{ label }}</h1>\n"
        f'<form method="post" action="{action}">\n'
        "{% for group in groups %}\n"
        "  {% if group.key is not none %}<h2>{{ group.key }}</h2>{% endif %}\n"
        "  {% for row in group.rows %}\n"
        '  <p class="editor-row">\n'
        '    <label for="item-{{ row.id }}">{{ row.id }}</label>\n'
        '    <textarea id="item-{{ row.id }}" name="item-{{ row.id }}">{{ row.default }}</textarea>\n'
        '    <input type="hidden" name="default-{{ row.id }}" value="{{ row.default }}">\n'
        "  </p>\n"
        "  {% endfor %}\n"
        "{% endfor %}\n"
        '<button type="submit">{{ label }}</button>\n'
        "</form>\n"
        "{% endblock %}\n"
    )


def render_editor_aggregator(schema_text: str, views_text: str) -> str:
    """``app/editors/__init__.py`` — the flat ``editor_routers`` list main.py mounts tolerantly (FR-ED-8)."""
    schema = parse_prisma_schema(schema_text)
    editors = parse_editors(views_text, known_entities=frozenset(schema.models))
    header = header_forms(
        "prisma/schema.prisma", schema_sha256(schema_text), schema_sha256(views_text), "editor-aggregator"
    )
    imports = "\n".join(f"from .{e.name} import editor_{e.name}_router" for e in editors)
    listing = ", ".join(f"editor_{e.name}_router" for e in editors)
    return (
        header + "\n"
        "# editor routers aggregator; main.py mounts `editor_routers` tolerantly.\n"
        + imports + f"\n\neditor_routers = [{listing}]\n"
    )


def _editor_by_name(views_text: str, name: str) -> Optional[EditorSpec]:
    for e in parse_editors(views_text):
        if e.name == name:
            return e
    return None


def render_named_editor_router(schema_text: str, views_text: str, name: str) -> str:
    """Drift re-render by name; orphan (entry removed) → non-matching sentinel → drift, not crash (FR-ED-10)."""
    spec = _editor_by_name(views_text, name)
    if spec is None:
        return f"# orphan editor router {name!r}: no longer declared in views.yaml `editors:`\n"
    return render_editor_router(schema_text, views_text, spec)


def render_named_editor_form(schema_text: str, views_text: str, name: str) -> str:
    """Drift re-render of the editor form by name; orphan → sentinel (FR-ED-10)."""
    spec = _editor_by_name(views_text, name)
    if spec is None:
        return f"{{# orphan editor form {name!r}: no longer declared in views.yaml `editors:` #}}\n"
    return render_editor_form(schema_text, views_text, spec)


def render_editors(schema_text: str, views_text: str) -> List[Tuple[str, str]]:
    """All editor artifacts as (path, text): per-editor router + form + the aggregator. Empty when none."""
    schema = parse_prisma_schema(schema_text)
    editors = parse_editors(views_text, known_entities=frozenset(schema.models))
    if not editors:
        return []
    out: List[Tuple[str, str]] = []
    for spec in editors:
        out.append((f"app/editors/{spec.name}.py", render_editor_router(schema_text, views_text, spec)))
        out.append((
            f"app/templates/editors/{spec.name}/form.html",
            render_editor_form(schema_text, views_text, spec),
        ))
    out.append(("app/editors/__init__.py", render_editor_aggregator(schema_text, views_text)))
    return out
