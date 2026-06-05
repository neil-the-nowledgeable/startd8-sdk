"""Deterministic HTMX/Jinja UI generation (Python contract-codegen, Step 5 / FR-4).

Projects the ``.prisma`` contract into the owned **server-rendered UI**: Jinja templates + the
FastAPI HTML routes that serve them. This is where the locked HTMX vocabulary lives —
**CRUD + inline validation** (list / detail / create+edit form / delete + validate-on-blur,
field-level errors, partial swaps). Per the target architecture, the UI is *templated from the
contract* (field → input widget), not hand-authored — so the React/component-invention classes
cannot occur.

Artifacts (all owned, all $0.00-skippable via the shared drift path):
- ``app/web.py`` — HTML-serving routes per entity (list / new / create / detail / edit / update /
  delete) + a ``/validate`` endpoint for inline field validation. Plain ``#`` header (kind
  ``fastapi-web``).
- ``app/templates/base.html`` (``htmx-base``), ``_field_error.html`` (``htmx-field-error``), and
  per-entity ``<e>/list.html`` / ``<e>/detail.html`` / ``<e>/form.html`` (``htmx-list`` /
  ``htmx-detail`` / ``htmx-form``, each tagged ``# startd8-entity: <Name>``). Template headers wrap
  the same ``#`` provenance lines inside a Jinja ``{# … #}`` comment so the existing drift regexes
  recognize them with no new machinery.

Field→widget map (FR-4): enum→``<select>``, Boolean→checkbox, Int/BigInt + Float/Decimal→number,
DateTime→datetime-local, everything else (String/Bytes/list)→text. Entities without a single-column
PK get list + create only (no by-id routes), mirroring the CRUD generator.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..frontend_codegen.schema_renderer import composite_type_names, schema_sha256
from ..languages.prisma_parser import PrismaField, PrismaSchema, parse_prisma_schema
from .ai_layer import _PROVENANCE_OMIT
from .crud_generator import _model_names, _pk_field

# ----------------------------------------------------------------------------- #
# Headers
# ----------------------------------------------------------------------------- #


def _py_header(source_file: str, sha: str, kind: str) -> str:
    return (
        f"# GENERATED from {source_file} — do not edit by hand; "
        f"regenerate via `startd8 generate backend`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: the Prisma schema.\n"
        f"# schema-sha256: {sha}"
    )


def _tmpl_header(source_file: str, sha: str, kind: str, entity: str = "") -> str:
    """A Jinja ``{# … #}`` comment wrapping the standard ``#`` provenance lines (drift-compatible)."""
    lines = [
        "{#",
        f"# GENERATED from {source_file} — do not edit by hand; "
        f"regenerate via `startd8 generate backend`.",
        f"# startd8-artifact: {kind}",
    ]
    if entity:
        lines.append(f"# startd8-entity: {entity}")
    lines.append("# Source of truth: the Prisma schema.")
    lines.append(f"# schema-sha256: {sha}")
    lines.append("#}")
    return "\n".join(lines)


# ----------------------------------------------------------------------------- #
# Field → widget / validation kind
# ----------------------------------------------------------------------------- #


def _field_kind(field: PrismaField, schema: PrismaSchema) -> str:
    """One of: select | checkbox | int | float | datetime | text (the widget + coercion kind)."""
    if field.is_list:
        return "text"  # comma-separated list input (v1)
    if field.type in schema.enums:
        return "select"
    if field.type == "Boolean":
        return "checkbox"
    if field.type in ("Int", "BigInt"):
        return "int"
    if field.type in ("Float", "Decimal"):
        return "float"
    if field.type == "DateTime":
        return "datetime"
    return "text"


def form_fields(schema: PrismaSchema, name: str) -> List[PrismaField]:
    """All scalar fields — used for read-only display (list/detail), where system fields are fine.

    Public (wireframe FR-W1/R6-S2): consumed by ``startd8.wireframe`` for field-level form
    planning. The ``_form_fields`` alias is retained for existing internal callers (R4-S3).
    """
    return list(schema.scalar_fields(name))


def writable_fields(schema: PrismaSchema, name: str) -> List[PrismaField]:
    """Scalar fields a *human* authors in a form (FR-PG-5).

    Drops the PK and the server-managed provenance/timestamp columns so users are never asked to
    hand-type a CUID or ISO timestamps. Reuses the exact omission set the AI edge schema already
    applies (``ai_layer._PROVENANCE_OMIT`` + ``f.is_id``) — same policy, not a new one. These columns
    are auto-managed on create (id cuid default, ``ownerId``/``source``/``confirmed``/timestamps via
    table defaults), exactly as the AI ``_persist`` path relies on.
    """
    return [
        f
        for f in schema.scalar_fields(name)
        if not f.is_id and f.name not in _PROVENANCE_OMIT
    ]


# Back-compat private aliases (R4-S3): existing internal call sites keep working; new external
# consumers (wireframe) use the public names.
_form_fields = form_fields
_writable_fields = writable_fields


def _is_required(field: PrismaField) -> bool:
    """Required iff non-optional AND not a list (an empty list is a valid value)."""
    return not field.is_optional and not field.is_list


# ----------------------------------------------------------------------------- #
# Templates
# ----------------------------------------------------------------------------- #


def render_base_template(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    pages_text: Optional[str] = None,
) -> str:
    """The shared base layout. With *pages_text* it carries the manifest ``<nav>`` (kind ``pages-base``,
    2-hash header) so the nav appears on **every** page (entity + content); without it, the nav-less
    schema-only base (kind ``htmx-base``)."""
    sha = schema_sha256(schema_text)
    if pages_text is not None:
        from ._headers import header_pages_tmpl
        from .pages_generator import build_nav_html

        head = header_pages_tmpl(source_file, sha, schema_sha256(pages_text), "pages-base")
        nav = build_nav_html(pages_text)
    else:
        head = _tmpl_header(source_file, sha, "htmx-base")
        nav = ""
    body = (
        "<!doctype html>\n"
        '<html lang="en">\n'
        '<head>\n  <meta charset="utf-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "  <title>{% block title %}StartDate{% endblock %}</title>\n"
        '  <script src="https://unpkg.com/htmx.org@2.0.3"></script>\n'
        "</head>\n<body>\n"
        + nav
        + "  <main>{% block content %}{% endblock %}</main>\n"
        "</body>\n</html>\n"
    )
    return head + "\n" + body


def render_field_error_template(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    sha = schema_sha256(schema_text)
    head = _tmpl_header(source_file, sha, "htmx-field-error")
    # Rendered by the /validate route into the field's error slot. Empty message => no error shown.
    body = '{% if message %}<span class="field-error">{{ message }}</span>{% endif %}\n'
    return head + "\n" + body


def render_list_template(schema_text: str, source_file: str, entity: str) -> str:
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    e = entity.lower()
    pk = _pk_field(schema, entity)
    fields = _form_fields(schema, entity)
    head = _tmpl_header(source_file, sha, "htmx-list", entity)

    cols = "".join(f"<th>{f.name}</th>" for f in fields)
    cells = "".join("<td>{{ item." + f.name + " }}</td>" for f in fields)

    lines = [
        '{% extends "base.html" %}',
        "{% block title %}" + entity + "{% endblock %}",
        "{% block content %}",
        f"<h1>{entity}</h1>",
        f'<a href="/ui/{e}/new">New {entity}</a>',
        f"<table>\n  <thead><tr>{cols}<th></th></tr></thead>",
        "  <tbody>",
        "  {% for item in items %}",
    ]
    if pk is not None:
        rid = "{{ item." + pk.name + " }}"
        lines += [
            f'  <tr id="row-{rid}">{cells}<td>',
            f'    <a href="/ui/{e}/{rid}">view</a>',
            f'    <a href="/ui/{e}/{rid}/edit">edit</a>',
            f'    <button hx-post="/ui/{e}/{rid}/delete" hx-target="#row-{rid}" '
            'hx-swap="outerHTML" hx-confirm="Delete?">delete</button>',
            "  </td></tr>",
        ]
    else:
        lines.append(f"  <tr>{cells}<td></td></tr>")
    lines += [
        "  {% endfor %}",
        "  </tbody>\n</table>",
        "{% endblock %}",
    ]
    return head + "\n" + "\n".join(lines) + "\n"


def render_detail_template(schema_text: str, source_file: str, entity: str) -> str:
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    fields = _form_fields(schema, entity)
    head = _tmpl_header(source_file, sha, "htmx-detail", entity)
    rows = "\n".join(
        f"  <dt>{f.name}</dt><dd>{{{{ item.{f.name} }}}}</dd>" for f in fields
    )
    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}" + entity + " detail{% endblock %}\n"
        "{% block content %}\n"
        f"<h1>{entity}</h1>\n<dl>\n{rows}\n</dl>\n"
        "{% endblock %}\n"
    )
    return head + "\n" + body


def _form_input_html(
    entity_lower: str, field: PrismaField, schema: PrismaSchema
) -> str:
    """The label + widget + inline-validation hooks + error slot for one form field."""
    name = field.name
    kind = _field_kind(field, schema)
    required = " required" if _is_required(field) else ""
    hx = (
        f' hx-post="/ui/{entity_lower}/validate" hx-trigger="blur changed"'
        f' hx-target="#err-{name}" hx-swap="innerHTML" hx-include="this"'
    )
    val = "{{ item." + name + " if item and item." + name + " is not none else '' }}"

    if kind == "select":
        opts = []
        for v in schema.enums[field.type]:
            sel = (
                "{% if item and item." + name + ' == "' + v + '" %}selected{% endif %}'
            )
            opts.append(f'    <option value="{v}" {sel}>{v}</option>')
        widget = (
            f'<select name="{name}" id="f-{name}"{required}{hx}>\n'
            + "\n".join(opts)
            + "\n  </select>"
        )
    elif kind == "checkbox":
        chk = "{% if item and item." + name + " %}checked{% endif %}"
        widget = f'<input type="checkbox" name="{name}" id="f-{name}" {chk}{hx}>'
    elif kind in ("int", "float"):
        step = ' step="any"' if kind == "float" else ""
        widget = (
            f'<input type="number"{step} name="{name}" id="f-{name}"'
            f' value="{val}"{required}{hx}>'
        )
    elif kind == "datetime":
        widget = (
            f'<input type="datetime-local" name="{name}" id="f-{name}"'
            f' value="{val}"{required}{hx}>'
        )
    else:
        widget = (
            f'<input type="text" name="{name}" id="f-{name}"'
            f' value="{val}"{required}{hx}>'
        )

    return (
        f'  <div class="field">\n'
        f'    <label for="f-{name}">{name}</label>\n'
        f"    {widget}\n"
        f'    <small id="err-{name}" class="field-error"></small>\n'
        f"  </div>"
    )


def render_form_template(schema_text: str, source_file: str, entity: str) -> str:
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    e = entity.lower()
    pk = _pk_field(schema, entity)
    fields = _writable_fields(schema, entity)  # forms expose only human-authored fields (FR-PG-5)
    head = _tmpl_header(source_file, sha, "htmx-form", entity)

    # One template serves create (item is None) and edit (item set); action differs.
    if pk is not None:
        pkref = "{{ item." + pk.name + " }}"
        action = (
            "{% if item %}/ui/" + e + "/" + pkref + "{% else %}/ui/" + e + "{% endif %}"
        )
    else:
        action = "/ui/" + e
    inputs = "\n".join(_form_input_html(e, f, schema) for f in fields)

    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}" + entity + " form{% endblock %}\n"
        "{% block content %}\n"
        f"<h1>{entity}</h1>\n"
        f'<form method="post" action="{action}">\n'
        f"{inputs}\n"
        '  <button type="submit">Save</button>\n'
        "</form>\n"
        "{% endblock %}\n"
    )
    return head + "\n" + body


# ----------------------------------------------------------------------------- #
# web.py — HTML-serving routes + inline-validation endpoint
# ----------------------------------------------------------------------------- #


_WEB_HELPERS = '''\
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
web_router = APIRouter()


def _coerce(kind: str, raw: str):
    """Coerce a raw form string to the field's Python kind (Pydantic does the rest on validate)."""
    if raw == "" or raw is None:
        return None
    if kind == "int":
        return int(raw)
    if kind == "float":
        return float(raw)
    if kind == "checkbox":
        return raw not in ("", "off", "false", "0")
    if kind == "text-list":
        return [p.strip() for p in raw.split(",") if p.strip()]
    return raw


def _field_error(kind: str, required: bool, raw: str) -> str:
    """Deterministic single-field validation message ("" = valid)."""
    if required and (raw is None or str(raw).strip() == ""):
        return "This field is required."
    if raw in (None, ""):
        return ""
    if kind == "int":
        try:
            int(raw)
        except ValueError:
            return "Must be a whole number."
    if kind == "float":
        try:
            float(raw)
        except ValueError:
            return "Must be a number."
    return ""
'''


def _entity_routes(schema: PrismaSchema, name: str) -> str:
    e = name.lower()
    pk = _pk_field(schema, name)
    fields = _writable_fields(schema, name)  # create/update + validation cover human-authored fields only
    # field -> (kind, required) rules; list scalars use the "text-list" coercion kind.
    rule_items = []
    for f in fields:
        kind = "text-list" if f.is_list else _field_kind(f, schema)
        rule_items.append(f'"{f.name}": ("{kind}", {_is_required(f)})')
    rules = "{" + ", ".join(rule_items) + "}"
    pkkind = "str"
    pkname = pk.name if pk is not None else "id"

    lines = [
        f"# --- {name} ---",
        f"_{e}_rules = {rules}",
        "",
        "",
        f'@web_router.get("/ui/{e}", response_class=HTMLResponse)',
        f"def list_{e}(request: Request, session: Session = Depends(get_session)):",
        f"    items = list(session.exec(select({name})).all())",
        "    return templates.TemplateResponse(",
        f'        request, "{e}/list.html", {{"items": items}}',
        "    )",
        "",
        "",
        f'@web_router.get("/ui/{e}/new", response_class=HTMLResponse)',
        f"def new_{e}(request: Request):",
        "    return templates.TemplateResponse(",
        f'        request, "{e}/form.html", {{"item": None}}',
        "    )",
        "",
        "",
        f'@web_router.post("/ui/{e}/validate", response_class=HTMLResponse)',
        f"async def validate_{e}(request: Request):",
        "    form = await request.form()",
        "    message = ''",
        "    for key, value in form.items():",
        f"        if key in _{e}_rules:",
        f"            kind, required = _{e}_rules[key]",
        "            message = _field_error(kind, required, value)",
        "            break",
        "    return templates.TemplateResponse(",
        '        request, "_field_error.html", {"message": message}',
        "    )",
        "",
        "",
        f'@web_router.post("/ui/{e}", response_class=HTMLResponse)',
        f"async def create_{e}(request: Request, session: Session = Depends(get_session)):",
        "    form = await request.form()",
        f"    data = {{k: _coerce(_{e}_rules[k][0], form.get(k))",
        f"            for k in _{e}_rules if form.get(k) not in (None, '')}}",
        f"    obj = {name}(**data)",
        "    session.add(obj)",
        "    session.commit()",
        f'    return HTMLResponse(headers={{"HX-Redirect": "/ui/{e}"}})',
    ]

    if pk is not None:
        pkref = "{" + pkname + "}"
        lines += [
            "",
            "",
            f'@web_router.get("/ui/{e}/{pkref}", response_class=HTMLResponse)',
            f"def detail_{e}({pkname}: {pkkind}, request: Request, "
            f"session: Session = Depends(get_session)):",
            f"    item = session.get({name}, {pkname})",
            "    if item is None:",
            f'        raise HTTPException(status_code=404, detail="{name} not found")',
            "    return templates.TemplateResponse(",
            f'        request, "{e}/detail.html", {{"item": item}}',
            "    )",
            "",
            "",
            f'@web_router.get("/ui/{e}/{pkref}/edit", response_class=HTMLResponse)',
            f"def edit_{e}({pkname}: {pkkind}, request: Request, "
            f"session: Session = Depends(get_session)):",
            f"    item = session.get({name}, {pkname})",
            "    if item is None:",
            f'        raise HTTPException(status_code=404, detail="{name} not found")',
            "    return templates.TemplateResponse(",
            f'        request, "{e}/form.html", {{"item": item}}',
            "    )",
            "",
            "",
            f'@web_router.post("/ui/{e}/{pkref}", response_class=HTMLResponse)',
            f"async def update_{e}({pkname}: {pkkind}, request: Request, "
            f"session: Session = Depends(get_session)):",
            f"    obj = session.get({name}, {pkname})",
            "    if obj is None:",
            f'        raise HTTPException(status_code=404, detail="{name} not found")',
            "    form = await request.form()",
            f"    for k in _{e}_rules:",
            "        if form.get(k) not in (None, ''):",
            f"            setattr(obj, k, _coerce(_{e}_rules[k][0], form.get(k)))",
            "    session.add(obj)",
            "    session.commit()",
            f'    return HTMLResponse(headers={{"HX-Redirect": "/ui/{e}"}})',
            "",
            "",
            f'@web_router.post("/ui/{e}/{pkref}/delete", response_class=HTMLResponse)',
            f"def delete_{e}({pkname}: {pkkind}, "
            f"session: Session = Depends(get_session)):",
            f"    obj = session.get({name}, {pkname})",
            "    if obj is not None:",
            "        session.delete(obj)",
            "        session.commit()",
            '    return HTMLResponse("")',
        ]
    return "\n".join(lines)


def render_web(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """Render ``app/web.py`` — HTML-serving routes + the inline-validation endpoint."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)

    header = _py_header(source_file, sha, "fastapi-web")
    imports = (
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from fastapi import APIRouter, Depends, HTTPException, Request\n"
        "from fastapi.responses import HTMLResponse\n"
        "from fastapi.templating import Jinja2Templates\n"
        "from sqlmodel import Session, select\n\n"
        "from .db import get_session\n"
    )
    if names:
        imports += "from .tables import " + ", ".join(sorted(names)) + "\n"

    blocks = [_entity_routes(schema, n) for n in names]
    body = _WEB_HELPERS + ("\n\n" + "\n\n\n".join(blocks) if blocks else "")
    return header + "\n\n" + imports + "\n\n" + body + "\n"


def render_ui(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    pages_text: Optional[str] = None,
) -> Tuple[Tuple[str, str], ...]:
    """All UI artifacts as ``(relative_path, text)`` pairs: web.py + base/error + per-entity templates.

    *pages_text* (when content pages are enabled) makes ``base.html`` carry the manifest nav."""
    schema = parse_prisma_schema(schema_text)
    composites = composite_type_names(schema_text)
    names = [n for n in schema.models if n not in composites]

    out: List[Tuple[str, str]] = [
        ("app/web.py", render_web(schema_text, source_file)),
        ("app/templates/base.html", render_base_template(schema_text, source_file, pages_text)),
        (
            "app/templates/_field_error.html",
            render_field_error_template(schema_text, source_file),
        ),
    ]
    for n in names:
        e = n.lower()
        out.append(
            (
                f"app/templates/{e}/list.html",
                render_list_template(schema_text, source_file, n),
            )
        )
        out.append(
            (
                f"app/templates/{e}/detail.html",
                render_detail_template(schema_text, source_file, n),
            )
        )
        out.append(
            (
                f"app/templates/{e}/form.html",
                render_form_template(schema_text, source_file, n),
            )
        )
    return tuple(out)
