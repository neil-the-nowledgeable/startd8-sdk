"""Deterministic HTMX/Jinja UI generation (Python contract-codegen, Step 5 / FR-4).

Projects the ``.prisma`` contract into the owned **server-rendered UI**: Jinja templates + the
FastAPI HTML routes that serve them. This is where the locked HTMX vocabulary lives —
**CRUD + inline validation** (list / detail / create+edit form / delete + validate-on-blur,
field-level errors, partial swaps). Per the target architecture, the UI is *templated from the
contract* (field → input widget), not hand-authored — so the React/component-invention classes
cannot occur. Entities carrying a ``confirmed`` Boolean also get a **confirm toggle** (AR-5 /
``CONFIRM_AFFORDANCE_REQUIREMENTS.md``) — the curation half of the suggest→confirm loop.

Artifacts (all owned, all $0.00-skippable via the shared drift path):
- ``app/web.py`` — HTML-serving routes per entity (list / new / create / detail / edit / update /
  delete) + a ``/validate`` endpoint for inline field validation. Plain ``#`` header (kind
  ``fastapi-web``; with a forms manifest, ``fastapi-web-forms`` carrying a 2-hash header).
- ``app/templates/base.html`` (``htmx-base``), ``_field_error.html`` (``htmx-field-error``), and
  per-entity ``<e>/list.html`` / ``<e>/_row.html`` / ``<e>/detail.html`` / ``<e>/form.html``
  (``htmx-list`` / ``htmx-row`` / ``htmx-detail`` / ``htmx-form``, each tagged
  ``# startd8-entity: <Name>``). The list ``{% include %}``s the row partial, which is the single
  source of row markup so the confirm route can re-render one row. Confirmed-bearing entities also
  get ``<e>/_confirm.html`` (``htmx-confirm``) — the detail-page confirm block (FR-CA-5). Template
  headers wrap
  the same ``#`` provenance lines inside a Jinja ``{# … #}`` comment so the existing drift regexes
  recognize them with no new machinery.

Post-submit behavior (FORM_SUBMIT_BEHAVIOR_REQUIREMENTS.md): the form is a plain browser POST, so
create/update answer with a real **303 See Other** (Post/Redirect/Get — the old ``HX-Redirect``
header is browser-ignored and produced a blank page). The default destination is the new record's
detail page with a stateless ``?created=1`` query-param flash; ``views.yaml``'s top-level
``forms:`` section overrides per entity (``on_create: detail|list|form|confirmation``).
``confirmation`` adds a per-entity ``<e>/created.html`` (kind ``htmx-created``, 2-hash header).

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
from .display_manifest import parse_display
from .filters_manifest import EntityFilter, parse_filters
from .forms_manifest import ON_CREATE_DEFAULT, parse_forms
from .tenancy import scoped_entities as _scoped_entities

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


def _confirm_field(schema: PrismaSchema, name: str) -> Optional[PrismaField]:
    """The ``confirmed`` provenance Boolean, iff the entity carries one (FR-CA-1).

    The confirm-affordance trigger: a scalar field literally named ``confirmed`` of type
    ``Boolean`` (`CONFIRM_AFFORDANCE_REQUIREMENTS.md`). The toggle route also needs a by-id path,
    so callers additionally gate on a single-column PK. Returns ``None`` when absent — entities
    without it are unchanged (no confirm control, no confirm route)."""
    for f in schema.scalar_fields(name):
        if f.name == "confirmed" and f.type == "Boolean" and not f.is_list:
            return f
    return None


# ----------------------------------------------------------------------------- #
# Templates
# ----------------------------------------------------------------------------- #


# Minimal owned styling, inlined in base.html as a always-present *fallback*. `startd8 polish`
# overrides it with a mounted /static/css/app.css (linked below, after this block, so the external
# sheet wins the cascade). When polish hasn't run, the link 404s harmlessly and this fallback applies.
_BASE_STYLE = """\
  <style>
    body { font-family: system-ui, sans-serif; margin: 0; color: #222; }
    main { max-width: 60rem; margin: 0 auto; padding: 1rem; }
    nav { background: #f4f4f4; padding: .5rem 1rem; }
    nav a { margin-right: .75rem; }
    table { border-collapse: collapse; width: 100%; margin-top: .75rem; }
    th, td { border: 1px solid #ddd; padding: .4rem .6rem; text-align: left; }
    tr.new-row td { background: #eaf7ea; }
    .flash { background: #eaf7ea; border: 1px solid #b7e0b7; padding: .5rem .75rem; }
    .field { margin-bottom: .75rem; }
    .field label { display: block; font-weight: 600; margin-bottom: .2rem; }
    .field-error { color: #b00020; }
    button { padding: .3rem .8rem; }
  </style>
"""


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
        + _BASE_STYLE
        + '  <link rel="stylesheet" href="/static/css/app.css">\n'
        # Tolerant presentation-polish theme hooks — the template analog of main.py's optional
        # `user_routers` seam. No-ops until `startd8 polish` drops the partials into templates/theme/;
        # they let polish add a head extra, a header bar, and a footer without editing this owned file.
        + '  {% include "theme/_head_extra.html" ignore missing %}\n'
        + "</head>\n<body>\n"
        + '  {% include "theme/_header.html" ignore missing %}\n'
        + nav
        + '  <main id="main-content" tabindex="-1">{% block content %}{% endblock %}</main>\n'
        + '  {% include "theme/_footer.html" ignore missing %}\n'
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


def _confirm_control(entity_lower: str, rid: str, cf_name: str, target: str) -> str:
    """The confirm/unconfirm toggle markup (AR-5 / FR-CA-4), parameterized by HTMX *target*.

    One source for the suggest→confirm verb shared by the list row (target ``#row-<pk>``, swaps
    the whole row so the ``confirmed`` cell updates) and the detail page (target ``#confirm-<pk>``,
    swaps just the confirm block — FR-CA-5). Full toggle, reversible, no guard dialog."""
    return (
        "{% if item." + cf_name + " %}"
        '<span class="confirmed">✓ confirmed</span> '
        f'<button hx-post="/ui/{entity_lower}/{rid}/confirm" hx-target="{target}" '
        'hx-swap="outerHTML">unconfirm</button>'
        "{% else %}"
        f'<button hx-post="/ui/{entity_lower}/{rid}/confirm" hx-target="{target}" '
        'hx-swap="outerHTML">confirm</button>'
        "{% endif %}"
    )


def render_confirm_template(schema_text: str, source_file: str, entity: str) -> str:
    """``<e>/_confirm.html`` — the detail-page confirm block (kind ``htmx-confirm``, schema-only).

    FR-CA-5: the same suggest→confirm toggle on the detail page. A self-contained
    ``<span id="confirm-<pk>">`` so the HTMX ``outerHTML`` swap re-establishes the same id and
    subsequent toggles keep working. Emitted only for entities carrying a ``confirmed`` Boolean
    with a single-column PK; the detail template ``{% include %}``s it for exactly those."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    e = entity.lower()
    pk = _pk_field(schema, entity)
    cf = _confirm_field(schema, entity)
    head = _tmpl_header(source_file, sha, "htmx-confirm", entity)
    rid = "{{ item." + pk.name + " }}"
    control = _confirm_control(e, rid, cf.name, f"#confirm-{rid}")
    return head + "\n" + f'<span id="confirm-{rid}">{control}</span>\n'


_LABEL_HEURISTIC = ("name", "title", "label", "headline")


def _default_label_field(schema: PrismaSchema, entity: str) -> Optional[str]:
    """FR-DM-7: the zero-config row label — first of name/title/label/headline that's a column."""
    cols = {f.name for f in schema.scalar_fields(entity)}
    return next((c for c in _LABEL_HEURISTIC if c in cols), None)


def _display_columns(schema: PrismaSchema, entity: str, display) -> List[Tuple[str, str, str]]:
    """(field, header_label, format) per displayed list column. With a manifest, use its `columns`;
    otherwise (FR-DM-7) default to the human/domain fields — the same id+provenance omit policy forms
    use — so a zero-config app never leads with id/ownerId/... `hidden_fields` removes more."""
    if display and display.columns:
        return [(c.field, c.label or c.field, c.format) for c in display.columns]
    fields = writable_fields(schema, entity)            # FR-DM-7: drop id + provenance/timestamps
    if display and display.hidden_fields:
        fields = [f for f in fields if f.name not in display.hidden_fields]
    return [(f.name, f.name, "") for f in fields]


def _cell_expr(field: str, fmt: str, e: str, pk_ref: str) -> str:
    """FR-DM-5: the Jinja cell expression for a field given its display `format`."""
    base = "item." + field
    if fmt == "badge":
        return '<span class="badge">{{ ' + base + " }}</span>"
    if fmt == "date":
        return "{{ " + base + ".strftime('%Y-%m-%d') if " + base + " else '' }}"
    if fmt.startswith("truncate:"):
        return "{{ " + base + "|truncate(" + fmt.split(":", 1)[1] + ") }}"
    if fmt == "link":
        return '<a href="/ui/' + e + "/" + pk_ref + '">{{ ' + base + " }}</a>"
    return "{{ " + base + " }}"


def render_row_template(schema_text: str, source_file: str, entity: str, display=None) -> str:
    """``<e>/_row.html`` — one table row (kind ``htmx-row``, schema-only, entity-tagged).

    The single source of truth for a list row (FR-CA-3): the list loop ``{% include %}``s it, and
    the confirm route re-renders it standalone so a toggled row swaps in with a working, restated
    control (FR-CA-4). Renders the read-only cells + view/edit/(confirm)/delete actions. When the
    entity carries a ``confirmed`` Boolean (`_confirm_field`), the actions include the confirm
    toggle. PK-less entities get cells + an empty action cell (no by-id actions). ``created`` is the
    list's just-stored pk (undefined when rendered standalone → no highlight)."""
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    e = entity.lower()
    pk = _pk_field(schema, entity)
    head = _tmpl_header(source_file, sha, "htmx-row", entity)

    rid = "{{ item." + pk.name + " }}" if pk is not None else ""
    cols = _display_columns(schema, entity, display)
    cells = "".join("<td>" + _cell_expr(f, fmt, e, rid) + "</td>" for f, _lbl, fmt in cols)
    if pk is None:
        return head + "\n" + f"<tr>{cells}<td></td></tr>\n"
    # ?created=<pk> (list mode) highlights the just-stored row (FR-FS OQ-6 follow-through).
    hl = "{% if created == item." + pk.name + '|string %} class="new-row"{% endif %}'
    cf = _confirm_field(schema, entity)
    confirm_html = ""
    if cf is not None:
        # The suggest→confirm verb (AR-5 / FR-CA-3/4). The row control swaps the whole row
        # (so the `confirmed` cell updates too) → it targets the row, not a confirm block.
        confirm_html = _confirm_control(e, rid, cf.name, f"#row-{rid}") + "\n    "
    # FR-DM-2/7: the view link reads as the row's label — display.label_field, else the zero-config
    # heuristic (name/title/label/headline), else a generic "view".
    _lf = display.label_field if (display and display.label_field) else _default_label_field(schema, entity)
    view_text = ("{{ item." + _lf + " or 'view' }}") if _lf else "view"
    body = (
        f'<tr id="row-{rid}"{hl}>{cells}<td>\n'
        f'    <a href="/ui/{e}/{rid}">{view_text}</a>\n'
        f'    <a href="/ui/{e}/{rid}/edit">edit</a>\n'
        f"    {confirm_html}"
        f'<button hx-post="/ui/{e}/{rid}/delete" hx-target="#row-{rid}" '
        'hx-swap="outerHTML" hx-confirm="Delete?">delete</button>\n'
        "  </td></tr>\n"
    )
    return head + "\n" + body


def _filter_form_html(e: str, ef: EntityFilter) -> str:
    """P0-2: a GET filter form (facet inputs + search box) that preserves current values."""
    parts = [f'<form method="get" action="/ui/{e}" class="filters">']
    for field in ef.facets:
        parts.append(
            f'  <label>{field} <input type="text" name="{field}"'
            f' value="{{{{ filters.get("{field}", "") }}}}"></label>'
        )
    if ef.search:
        parts.append(
            '  <label>search <input type="search" name="q"'
            ' value="{{ filters.get(\'q\', \'\') }}"></label>'
        )
    parts.append('  <button type="submit">Filter</button>')
    parts.append(f'  <a href="/ui/{e}">clear</a>')
    parts.append("</form>")
    return "\n".join(parts)


def render_list_template(
    schema_text: str, source_file: str, entity: str, efilter: Optional[EntityFilter] = None,
    display=None,
) -> str:
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    e = entity.lower()
    head = _tmpl_header(source_file, sha, "htmx-list", entity)

    # FR-DM-2: <thead> from the display columns (labels, order); else current all-scalars.
    cols = "".join(f"<th>{label}</th>" for _f, label, _fmt in _display_columns(schema, entity, display))
    filter_form = (_filter_form_html(e, efilter) + "\n") if efilter else ""
    title = display.title if (display and display.title) else entity      # FR-DM-3 page title

    lines = [
        '{% extends "base.html" %}',
        "{% block title %}" + entity + "{% endblock %}",
        "{% block content %}",
        # Post-create flash (FR-FS-3): set when the route passes the ?created query param through.
        '{% if created %}<p class="flash">✓ ' + entity + " stored.</p>{% endif %}",
        f"<h1>{title}</h1>",
        f'<a href="/ui/{e}/new">New {entity}</a>',
        filter_form.rstrip("\n") if filter_form else None,
        f"<table>\n  <thead><tr>{cols}<th></th></tr></thead>",
        "  <tbody>",
        # Row markup lives in the shared partial (FR-CA-3) so the confirm route can re-render it.
        '  {% for item in items %}{% include "' + e + '/_row.html" %}{% endfor %}',
        "  </tbody>\n</table>",
        "{% endblock %}",
    ]
    return head + "\n" + "\n".join(x for x in lines if x is not None) + "\n"


def _detail_dl(fields_: List[str]) -> str:
    return "<dl>\n" + "\n".join(
        f"  <dt>{fn}</dt><dd>{{{{ item.{fn} }}}}</dd>" for fn in fields_
    ) + "\n</dl>"


def render_detail_template(schema_text: str, source_file: str, entity: str, display=None) -> str:
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    e = entity.lower()
    head = _tmpl_header(source_file, sha, "htmx-detail", entity)

    # FR-DM-3: grouped <section>s when the display declares them; else the flat <dl> over all scalars
    # (minus hidden_fields when a manifest is present).
    if display and display.sections:
        detail_html = "\n".join(
            f"<section>\n<h2>{s.title}</h2>\n{_detail_dl(list(s.fields))}\n</section>"
            for s in display.sections
        )
    else:
        fields = writable_fields(schema, entity)        # FR-DM-7: drop id + provenance by default
        if display and display.hidden_fields:
            fields = [f for f in fields if f.name not in display.hidden_fields]
        detail_html = _detail_dl([f.name for f in fields])
    title = display.title if (display and display.title) else entity
    subtitle = (f'<p class="subtitle">{display.subtitle}</p>\n' if (display and display.subtitle) else "")
    # FR-CA-5: confirmed-bearing entities get the confirm toggle on the detail page too.
    confirm_block = ""
    if _confirm_field(schema, entity) is not None and _pk_field(schema, entity) is not None:
        confirm_block = '{% include "' + e + '/_confirm.html" %}\n'
    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}" + entity + " detail{% endblock %}\n"
        "{% block content %}\n"
        # Post-submit flash (FR-FS-3/FR-FS-6): the create/update PRG redirects land here.
        '{% if created %}<p class="flash">✓ ' + entity + " stored.</p>{% endif %}\n"
        '{% if updated %}<p class="flash">✓ ' + entity + " updated.</p>{% endif %}\n"
        f"<h1>{title}</h1>\n{subtitle}{detail_html}\n"
        f"{confirm_block}"
        # FR-AIT-3: tolerant seam — the AI layer emits <e>/_ai_triggers.html only for entities with a
        # pass `trigger:`; `ignore missing` makes this inert (and byte-stable) for everyone else.
        '{% include "' + e + '/_ai_triggers.html" ignore missing %}\n'
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
    # On the create form (item is None) fall back to a query-param prefill value (FK pre-linking).
    # `prefill` is undefined in edit/list contexts; the `if prefill` guard keeps Jinja safe there.
    val = (
        "{{ item." + name + " if item and item." + name + " is not none"
        " else (prefill.get('" + name + "') if prefill else '') }}"
    )

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

    # ?created=<pk> (form mode) gets a "view it" link; no-PK entities echo created=1 — no link.
    view_link = (
        f' <a href="/ui/{e}/{{{{ created }}}}">view it</a>' if pk is not None else ""
    )
    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}" + entity + " form{% endblock %}\n"
        "{% block content %}\n"
        # Post-create flash (FR-FS-3): on_create: form lands back here with ?created=<pk>.
        '{% if created %}<p class="flash">✓ ' + entity + f" stored.{view_link}</p>{{% endif %}}\n"
        f"<h1>{entity}</h1>\n"
        f'<form method="post" action="{action}">\n'
        f"{inputs}\n"
        '  <button type="submit">Save</button>\n'
        "</form>\n"
        "{% endblock %}\n"
    )
    return head + "\n" + body


def render_created_template(
    schema_text: str, source_file: str, entity: str, forms_text: str
) -> str:
    """``<e>/created.html`` — the dedicated confirmation page (``on_create: confirmation``).

    Kind ``htmx-created``, 2-hash header (schema + views.yaml): the template only *exists* because
    the forms manifest selected the confirmation archetype, so its provenance carries the manifest.
    Shows the stored values + the three onward links (view / add another / back to list).
    """
    from ._headers import header_forms_tmpl

    schema = parse_prisma_schema(schema_text)
    e = entity.lower()
    pk = _pk_field(schema, entity)
    fields = _form_fields(schema, entity)
    head = header_forms_tmpl(
        source_file, schema_sha256(schema_text), schema_sha256(forms_text),
        "htmx-created", entity,
    )
    rows = "\n".join(
        f"  <dt>{f.name}</dt><dd>{{{{ item.{f.name} }}}}</dd>" for f in fields
    )
    pkref = "{{ item." + (pk.name if pk is not None else "id") + " }}"
    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}" + entity + " stored{% endblock %}\n"
        "{% block content %}\n"
        '<p class="flash">✓ ' + entity + " stored.</p>\n"
        f"<dl>\n{rows}\n</dl>\n"
        f'<a href="/ui/{e}/{pkref}">view</a>\n'
        f'<a href="/ui/{e}/new">add another</a>\n'
        f'<a href="/ui/{e}">back to list</a>\n'
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


def _create_redirect(e: str, pkname: str, has_pk: bool, on_create: str) -> List[str]:
    """The post-create PRG tail (FR-FS-1/2/4): 303 to the configured destination.

    Plain browser form POSTs ignore the old ``HX-Redirect`` header (the blank-page defect), so the
    handler answers with a real ``303 See Other``. ``detail`` carries ``?created=1`` (pk is in the
    path); ``list``/``form`` echo ``?created=<pk>`` so the destination can later highlight/link the
    new row (OQ-6). Entities without a single-column PK have no detail/confirmation page — those
    modes fall back to ``list`` at generation time (FR-FS-8).
    """
    if not has_pk and on_create in ("detail", "confirmation"):
        return [
            f"    # no single-column PK -> no detail page; '{on_create}' falls back to list (FR-FS-8)",
            f'    return RedirectResponse("/ui/{e}?created=1", status_code=303)',
        ]
    if on_create == "detail":
        target = f'f"/ui/{e}/{{obj.{pkname}}}?created=1"'
    elif on_create == "confirmation":
        target = f'f"/ui/{e}/{{obj.{pkname}}}/created"'
    elif on_create == "form":
        target = (
            f'f"/ui/{e}/new?created={{obj.{pkname}}}"' if has_pk
            else f'"/ui/{e}/new?created=1"'
        )
    else:  # list
        target = (
            f'f"/ui/{e}?created={{obj.{pkname}}}"' if has_pk
            else f'"/ui/{e}?created=1"'
        )
    return [f"    return RedirectResponse({target}, status_code=303)"]


def _list_query_lines(
    schema: PrismaSchema, name: str, ef: EntityFilter, owner_field: Optional[str] = None
) -> List[str]:
    """The filter/search query-building lines for a filtered ``list_<e>`` handler (P0-2).

    When *owner_field* is set (Tier B), the base statement is row-scoped to the principal BEFORE any
    facet/search filter is applied (FR-TEN-2)."""
    base = (
        f"    stmt = select({name}).where({name}.{owner_field} == principal.id)"
        if owner_field else f"    stmt = select({name})"
    )
    lines = [base]
    for field in ef.facets:
        f = schema.model(name).field(field)
        lines.append(f'    _v = request.query_params.get("{field}")')
        if f is not None and f.is_list:           # JSON-array column → membership (quoted, no false sub-hits)
            lines.append("    if _v:")
            lines.append(
                f'        stmt = stmt.where(_sa_cast({name}.{field}, _SAString)'
                # autoescape: LIKE wildcards (% _) in user input are escaped, not treated as wildcards
                ".contains('\"' + _v + '\"', autoescape=True))"
            )
        else:                                       # scalar → exact match
            lines.append("    if _v:")
            lines.append(f"        stmt = stmt.where({name}.{field} == _v)")
    if ef.search:
        terms = ", ".join(
            f"_sa_cast({name}.{s}, _SAString).icontains(_q, autoescape=True)" for s in ef.search
        )
        lines.append('    _q = request.query_params.get("q")')
        lines.append("    if _q:")
        lines.append(f"        stmt = stmt.where(_or({terms}))")
    lines.append("    items = list(session.exec(stmt).all())")
    return lines


def _entity_routes(
    schema: PrismaSchema, name: str, on_create: str = ON_CREATE_DEFAULT,
    efilter: Optional[EntityFilter] = None, owner_field: Optional[str] = None,
) -> str:
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

    # Tier B (FR-TEN-2): when scoped, every DB-touching handler resolves the principal and the query
    # is row-scoped — get/detail/edit/update/delete/confirm/created 404 on a non-owned row (never 403:
    # existence is not leaked), list filters by owner, create server-sets it. owner_field None →
    # today's unscoped output byte-for-byte.
    pdep = ", principal: Principal = Depends(require_principal)" if owner_field else ""

    def guard404(var: str) -> List[str]:
        cond = f"{var} is None or {var}.{owner_field} != principal.id" if owner_field else f"{var} is None"
        return [f"    if {cond}:", f'        raise HTTPException(status_code=404, detail="{name} not found")']

    lines = [
        f"# --- {name} ---",
        f"_{e}_rules = {rules}",
        "",
        "",
        f'@web_router.get("/ui/{e}", response_class=HTMLResponse)',
        f"def list_{e}(request: Request, session: Session = Depends(get_session){pdep}):",
        *(
            _list_query_lines(schema, name, efilter, owner_field) if efilter
            else [
                f"    items = list(session.exec(select({name}).where({name}.{owner_field} == principal.id)).all())"
                if owner_field
                else f"    items = list(session.exec(select({name})).all())"
            ]
        ),
        '    ctx = {"items": items, "created": request.query_params.get("created"),',
        '           "filters": dict(request.query_params)}',
        "    return templates.TemplateResponse(",
        f'        request, "{e}/list.html", ctx',
        "    )",
        "",
        "",
        f'@web_router.get("/ui/{e}/new", response_class=HTMLResponse)',
        f"def new_{e}(request: Request):",
        # Prefill known writable fields from query params, so `/ui/<e>/new?<fk>=<id>` pre-links a
        # parent (e.g. `?jobDescriptionId=<id>`). Restricted to declared fields — unknown params ignored.
        f"    prefill = {{k: v for k, v in request.query_params.items() if k in _{e}_rules}}",
        '    ctx = {"item": None, "prefill": prefill, "created": request.query_params.get("created")}',
        "    return templates.TemplateResponse(",
        f'        request, "{e}/form.html", ctx',
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
        f"async def create_{e}(request: Request, session: Session = Depends(get_session){pdep}):",
        "    form = await request.form()",
        f"    data = {{k: _coerce(_{e}_rules[k][0], form.get(k))",
        f"            for k in _{e}_rules if form.get(k) not in (None, '')}}",
        f"    obj = {name}(**data)",
        *([f"    obj.{owner_field} = principal.id"] if owner_field else []),
        "    session.add(obj)",
        "    session.commit()",
        "    session.refresh(obj)",  # uniform PK recovery: default_factory AND DB-side autoincrement
        *_create_redirect(e, pkname, pk is not None, on_create),
    ]

    if pk is not None:
        pkref = "{" + pkname + "}"
        lines += [
            "",
            "",
            f'@web_router.get("/ui/{e}/{pkref}", response_class=HTMLResponse)',
            f"def detail_{e}({pkname}: {pkkind}, request: Request, "
            f"session: Session = Depends(get_session){pdep}):",
            f"    item = session.get({name}, {pkname})",
            *guard404("item"),
            '    ctx = {"item": item, "created": request.query_params.get("created"),',
            '           "updated": request.query_params.get("updated")}',
            "    return templates.TemplateResponse(",
            f'        request, "{e}/detail.html", ctx',
            "    )",
            "",
            "",
            f'@web_router.get("/ui/{e}/{pkref}/edit", response_class=HTMLResponse)',
            f"def edit_{e}({pkname}: {pkkind}, request: Request, "
            f"session: Session = Depends(get_session){pdep}):",
            f"    item = session.get({name}, {pkname})",
            *guard404("item"),
            "    return templates.TemplateResponse(",
            f'        request, "{e}/form.html", {{"item": item}}',
            "    )",
            "",
            "",
            f'@web_router.post("/ui/{e}/{pkref}", response_class=HTMLResponse)',
            f"async def update_{e}({pkname}: {pkkind}, request: Request, "
            f"session: Session = Depends(get_session){pdep}):",
            f"    obj = session.get({name}, {pkname})",
            *guard404("obj"),
            "    form = await request.form()",
            f"    for k in _{e}_rules:",
            "        if form.get(k) not in (None, ''):",
            f"            setattr(obj, k, _coerce(_{e}_rules[k][0], form.get(k)))",
            *([f"    obj.{owner_field} = principal.id"] if owner_field else []),  # ownership immutable
            "    session.add(obj)",
            "    session.commit()",
            # PRG on edit too (FR-FS-6): back to the detail page with the updated flash.
            f'    return RedirectResponse(f"/ui/{e}/{{{pkname}}}?updated=1", status_code=303)',
            "",
            "",
            f'@web_router.post("/ui/{e}/{pkref}/delete", response_class=HTMLResponse)',
            f"def delete_{e}({pkname}: {pkkind}, "
            f"session: Session = Depends(get_session){pdep}):",
            f"    obj = session.get({name}, {pkname})",
            # Scoped: 404 on a missing OR non-owned row (consistent with get/update; never a fake
            # "deleted" flash). Unscoped: today's tolerant delete.
            *(
                [*guard404("obj"), "    session.delete(obj)", "    session.commit()"]
                if owner_field
                else ["    if obj is not None:", "        session.delete(obj)", "        session.commit()"]
            ),
            # The hx-swap="outerHTML" replaces the row with this flash row (visible until reload),
            # so deletion gets the same confirmation feedback as create/update (FR-FS-3 family).
            "    return HTMLResponse(",
            f'        \'<tr><td colspan="{len(_form_fields(schema, name)) + 1}">\'',
            f"        '<p class=\"flash\">✓ {name} deleted.</p></td></tr>'",
            "    )",
        ]
        cf = _confirm_field(schema, name)
        if cf is not None:
            # AR-5 / FR-CA-2: the suggest→confirm verb. Full toggle. One route serves both surfaces
            # (FR-CA-5): the HX-Target header says which fragment to swap — the detail confirm block
            # (#confirm-<pk>) or, by default, the list row (re-rendered so its `confirmed` cell flips).
            lines += [
                "",
                "",
                f'@web_router.post("/ui/{e}/{pkref}/confirm", response_class=HTMLResponse)',
                f"def confirm_{e}({pkname}: {pkkind}, request: Request, "
                f"session: Session = Depends(get_session){pdep}):",
                f"    obj = session.get({name}, {pkname})",
                *guard404("obj"),
                f"    obj.{cf.name} = not obj.{cf.name}",
                "    session.add(obj)",
                "    session.commit()",
                "    session.refresh(obj)",
                '    if request.headers.get("hx-target", "").startswith("confirm-"):',
                "        return templates.TemplateResponse(",
                f'            request, "{e}/_confirm.html", {{"item": obj}}',
                "        )",
                "    return templates.TemplateResponse(",
                f'        request, "{e}/_row.html", {{"item": obj}}',
                "    )",
            ]
        if on_create == "confirmation":
            # The dedicated confirmation page (FR-FS-5) — the create handler 303s here.
            lines += [
                "",
                "",
                f'@web_router.get("/ui/{e}/{pkref}/created", response_class=HTMLResponse)',
                f"def created_{e}({pkname}: {pkkind}, request: Request, "
                f"session: Session = Depends(get_session){pdep}):",
                f"    item = session.get({name}, {pkname})",
                *guard404("item"),
                "    return templates.TemplateResponse(",
                f'        request, "{e}/created.html", {{"item": item}}',
                "    )",
            ]
    return "\n".join(lines)


def _validate_filter_fields(schema: PrismaSchema, filters: dict) -> None:
    """P0-2: every facet/search field must be a real column on its entity (loud-fail at render)."""
    for entity, ef in filters.items():
        model = schema.model(entity)
        cols = {f.name for f in model.fields} if model else set()
        for field in (*ef.facets, *ef.search):
            if field not in cols:
                raise ValueError(
                    f"views.yaml: filters[{entity}] references unknown field {field!r}"
                )


def render_web(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    forms_text: Optional[str] = None,
    tenant_owner_field: Optional[str] = None,
) -> str:
    """Render ``app/web.py`` — HTML-serving routes + the inline-validation endpoint.

    *forms_text* (the full ``views.yaml``; only its ``forms:`` section is read) selects each
    entity's post-create destination (FR-FS-4). With it, the artifact derives from two inputs —
    kind ``fastapi-web-forms``, 2-hash header; without it, the schema-only ``fastapi-web``
    (the ``htmx-base``/``pages-base`` precedent: a distinct kind per dep-set).
    """
    schema = parse_prisma_schema(schema_text)
    sha = schema_sha256(schema_text)
    names = _model_names(schema, schema_text)
    forms = parse_forms(forms_text, known_entities=frozenset(names))
    filters = parse_filters(forms_text, known_entities=frozenset(names))
    _validate_filter_fields(schema, filters)       # P0-2: facet/search fields must be real columns

    scoped = (
        set(_scoped_entities(schema_text, tenant_owner_field)) if tenant_owner_field else set()
    )
    if forms_text is not None:
        from ._headers import header_forms

        header = header_forms(
            source_file, sha, schema_sha256(forms_text), "fastapi-web-forms"
        )
    else:
        header = _py_header(source_file, sha, "fastapi-web")
    if tenant_owner_field:  # self-described owner FK so the skip-hook re-renders the scoped file
        header += f"\n# startd8-tenant: {tenant_owner_field}"
    imports = (
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from fastapi import APIRouter, Depends, HTTPException, Request\n"
        "from fastapi.responses import HTMLResponse, RedirectResponse\n"
        "from fastapi.templating import Jinja2Templates\n"
        "from sqlmodel import Session, select\n\n"
        "from .db import get_session\n"
    )
    if scoped:  # the principal dependency the scoped handlers resolve (auth seam, deployed-only)
        imports += "from .auth import Principal, require_principal\n"
    if filters:  # P0-2: cast/or_ for facet membership + free-text search query building
        imports += "from sqlalchemy import String as _SAString, cast as _sa_cast, or_ as _or\n"
    if names:
        imports += "from .tables import " + ", ".join(sorted(names)) + "\n"

    blocks = [
        _entity_routes(
            schema, n, forms.get(n, ON_CREATE_DEFAULT), filters.get(n),
            owner_field=(tenant_owner_field if n in scoped else None),
        )
        for n in names
    ]
    body = _WEB_HELPERS + ("\n\n" + "\n\n\n".join(blocks) if blocks else "")
    return header + "\n\n" + imports + "\n\n" + body + "\n"


def render_ui(
    schema_text: str,
    source_file: str = "prisma/schema.prisma",
    pages_text: Optional[str] = None,
    forms_text: Optional[str] = None,
    display_text: Optional[str] = None,
    tenant_owner_field: Optional[str] = None,
) -> Tuple[Tuple[str, str], ...]:
    """All UI artifacts as ``(relative_path, text)`` pairs: web.py + base/error + per-entity templates.

    *pages_text* (when content pages are enabled) makes ``base.html`` carry the manifest nav.
    *forms_text* (``views.yaml``) selects per-entity post-create behavior; entities declaring
    ``on_create: confirmation`` additionally get a ``<e>/created.html`` template (FR-FS-5).
    *display_text* (``display.yaml``) drives per-entity list columns/labels/order + detail sections
    (FR-DM); absent ⇒ today's all-scalars behavior (opt-in)."""
    schema = parse_prisma_schema(schema_text)
    composites = composite_type_names(schema_text)
    names = [n for n in schema.models if n not in composites]
    forms = parse_forms(forms_text, known_entities=frozenset(names))
    filters = parse_filters(forms_text, known_entities=frozenset(names))
    displays, _ = parse_display(display_text, schema)

    out: List[Tuple[str, str]] = [
        ("app/web.py", render_web(schema_text, source_file, forms_text, tenant_owner_field)),
        ("app/templates/base.html", render_base_template(schema_text, source_file, pages_text)),
        (
            "app/templates/_field_error.html",
            render_field_error_template(schema_text, source_file),
        ),
    ]
    for n in names:
        e = n.lower()
        ed = displays.get(n)                       # FR-DM: per-entity display (None ⇒ default)
        out.append(
            (
                f"app/templates/{e}/list.html",
                render_list_template(schema_text, source_file, n, filters.get(n), ed),
            )
        )
        out.append(
            (
                f"app/templates/{e}/_row.html",
                render_row_template(schema_text, source_file, n, ed),
            )
        )
        out.append(
            (
                f"app/templates/{e}/detail.html",
                render_detail_template(schema_text, source_file, n, ed),
            )
        )
        out.append(
            (
                f"app/templates/{e}/form.html",
                render_form_template(schema_text, source_file, n),
            )
        )
        # FR-CA-5: the detail-page confirm block, only for confirmed-bearing entities with a PK.
        if _confirm_field(schema, n) is not None and _pk_field(schema, n) is not None:
            out.append(
                (
                    f"app/templates/{e}/_confirm.html",
                    render_confirm_template(schema_text, source_file, n),
                )
            )
        if forms.get(n) == "confirmation" and _pk_field(schema, n) is not None:
            out.append(
                (
                    f"app/templates/{e}/created.html",
                    render_created_template(schema_text, source_file, n, forms_text or ""),
                )
            )
    return tuple(out)
