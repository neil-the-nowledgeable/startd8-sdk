"""Default top-navigation: deterministic registry + always-on partial + runtime visibility module.

The always-on top nav for every generated app (FR-13). It aggregates all three navigable surface
classes deterministically at build time and renders them into a shared ``_nav.html`` partial that
``base.html`` includes on every page. Per-item visibility is a *runtime* concern: an operator lists
hidden keys in an optional ``nav.config.json`` (read once at startup), and the partial omits those —
edit the file, restart (FR-6/7). No DB, no migration, no auth coupling (req v0.3).

Three owned artifacts, all deriving from THREE inputs (schema + ``views.yaml`` + ``pages.yaml``):
- ``app/nav.py``            (kind ``nav-registry``) — ``DEFAULT_NAV`` data + ``load_hidden()``/``visible_nav()``
- ``app/templates/_nav.html`` (kind ``nav-partial``) — the rendered ``<nav>`` (links gated by ``nav_hidden``)

Enumeration:
- content pages (pages.yaml): label = ``nav_label or title``, href = slug  (all-visible default, FR-2)
- entity CRUD UIs (schema):   label = titleized class name, href = ``/ui/<name.lower()>``  (FR-1a)
- views (views.yaml):         label = ``ViewSpec.name``, href = ``ViewSpec.route``  (FR-1b)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_nav, header_nav_tmpl, header_standard

# The 3-input nav kinds (schema + views.yaml + pages.yaml). The live-toggle artifacts (nav-store /
# nav-admin-*) are schema-only + mode-invariant, so they are NOT here — they route through the default
# schema-only drift renderer.
NAV_KINDS = ("nav-registry", "nav-partial", "nav-index-router", "nav-index-page")
NAV_STORE_KINDS = ("nav-store", "nav-admin-router", "nav-admin-page")

# Owned output paths → artifact kind (mirrors pages_layout / the CANONICAL_LAYOUT precedent).
# The index pair is conditional (emitted only when no content page owns ``/`` — see render_nav).
NAV_LAYOUT: Dict[str, str] = {
    "app/nav.py": "nav-registry",
    "app/templates/_nav.html": "nav-partial",
    "app/index.py": "nav-index-router",
    "app/templates/index.html": "nav-index-page",
    "app/nav_store.py": "nav-store",
    "app/nav_admin.py": "nav-admin-router",
    "app/templates/nav_admin.html": "nav-admin-page",
}


@dataclass(frozen=True)
class NavEntry:
    key: str
    label: str
    href: str
    group: str  # "page" | "entity" | "view"


def _titleize(name: str) -> str:
    """``InvoiceLine`` -> ``Invoice Line`` (deterministic, no I/O)."""
    out: List[str] = []
    for i, ch in enumerate(name):
        if i and ch.isupper() and not name[i - 1].isupper():
            out.append(" ")
        out.append(ch)
    return "".join(out).strip() or name


def nav_registry(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
) -> Tuple[NavEntry, ...]:
    """The deterministic, all-visible default nav registry. Order: page -> entity -> view (FR-1/5)."""
    entries: List[NavEntry] = []

    # pages.yaml (optional) — all-visible default: label falls back to title (NOT the nav_label filter)
    if pages_text:
        from .pages_generator import parse_pages

        pages, _ = parse_pages(pages_text)
        for p in pages:
            entries.append(
                NavEntry(key=f"page:{p.slug}", label=p.nav_label or p.title, href=p.slug, group="page")
            )

    # entities (schema) — no label exists in generated code; derive one (FR-1a), unless the model
    # carries a `/// @nav <Label>` override in the schema (FR-26). The override changes only the
    # display label; the key stays ``entity:<Name>`` (identity is unchanged).
    from ..languages.prisma_parser import parse_prisma_schema
    from .crud_generator import _model_names

    schema = parse_prisma_schema(schema_text)
    for name in _model_names(schema, schema_text):
        model = schema.model(name)
        label = (model.nav_label if model and model.nav_label else _titleize(name))
        entries.append(
            NavEntry(key=f"entity:{name}", label=label, href=f"/ui/{name.lower()}", group="entity")
        )

    # views.yaml `views:` section (optional) — friendly name + route already exist (FR-1b). NOTE:
    # views.yaml is a MULTI-section manifest (views:/forms:/flows:/editors:); an app may declare only
    # `flows:` with no top-level `views:`. parse_views is strict, so enumerate views only when the
    # `views:` section is actually present (else this is a forms/flows/editors-only manifest).
    if views_text and _has_views_section(views_text):
        from ..view_codegen.manifest import parse_views

        for v in parse_views(views_text, known_entities=frozenset(schema.models)):
            entries.append(NavEntry(key=f"view:{v.route}", label=v.name, href=v.route, group="view"))

    # The generated home/index is itself a navigable surface (FR-28e), so it appears in the nav bar.
    # Its own ``group`` is "index", which the index page deliberately does not list (it lists only
    # page/entity/view) — so the sitemap never lists itself.
    entries.append(NavEntry(key="index", label="Index", href=index_route(pages_text), group="index"))

    return tuple(entries)


def index_route(pages_text: Optional[str]) -> str:
    """The index's primary route: ``/`` when free, else the stable ``/_index`` sitemap (FR-28a)."""
    return "/_index" if pages_owns_root(pages_text) else "/"


def _has_views_section(views_text: str) -> bool:
    """True iff *views_text* declares a non-empty top-level ``views:`` list (vs forms/flows/editors only)."""
    import yaml

    try:
        doc = yaml.safe_load(views_text) or {}
    except Exception:
        return False
    return isinstance(doc, dict) and bool(doc.get("views"))


def render_nav_partial(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> str:
    """``app/templates/_nav.html`` (kind ``nav-partial``) — the always-on top nav.

    **Generic + data-driven (FR-19):** the template iterates the registry the app resolves at startup
    (``request.app.state.nav`` = ``visible_nav()``), rather than baking a copy of the links. So
    ``app/nav.py`` is the single source of truth and the visibility config (FR-6/7) is honoured without
    re-rendering. Fail-open to an empty nav if state is unset (e.g. rendered outside a request).
    - **FR-16 accessibility:** ``<nav aria-label="Primary">`` landmark + ``aria-current="page"`` on the
      active item.
    - **FR-17 nested active state:** exact match for pages/views; entity items also match a path
      *prefix* (``/ui/widget`` is active on ``/ui/widget/123``), guarded so a ``/`` href can't match all.
    - **FR-18 grouping:** a separator is emitted at each ``group`` boundary (page → entity → view).
    Labels/hrefs are emitted via ``{{ }}`` so Jinja **auto-escapes** them (no build-time escaping needed).
    The body is input-independent; the 3-sha header still versions it against schema/views/pages.
    """
    head = header_nav_tmpl(
        source_file,
        schema_sha256(schema_text),
        schema_sha256(views_text or ""),
        schema_sha256(pages_text or ""),
        "nav-partial",
    )
    link_style = "margin-right:1.25rem;color:#0a7d4b;text-decoration:none"
    body = (
        "{% set _nav = request.app.state.nav if request and request.app.state.nav is defined else [] %}\n"
        '<nav aria-label="Primary" style="padding:0.9rem 1.25rem;border-bottom:1px solid #e3e3e3;'
        'background:#fafafa;font-family:system-ui,-apple-system,sans-serif">\n'
        "{%- for item in _nav %}\n"
        "{%- if not loop.first and item.group != _nav[loop.index0 - 1].group %}"
        '<span aria-hidden="true" style="margin:0 0.5rem;color:#bbb">|</span>{% endif %}\n'
        "{%- set _active = request.url.path == item.href or (item.group == 'entity' "
        "and item.href != '/' and request.url.path.startswith(item.href ~ '/')) %}\n"
        '  <a href="{{ item.href }}"{% if _active %} aria-current="page"{% endif %} '
        f'style="{link_style}{{% if _active %}};font-weight:700{{% endif %}}">{{{{ item.label }}}}</a>\n'
        "{%- endfor %}\n"
        "</nav>\n"
    )
    return head + "\n" + body


def render_nav_module(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> str:
    """``app/nav.py`` (kind ``nav-registry``) — the baked default registry + the runtime visibility read.

    This is the **single source of truth** for the rendered nav (FR-19): ``main.py`` calls
    ``visible_nav()`` at startup and stashes it on ``app.state.nav``, which the generic ``_nav.html``
    partial iterates. ``load_hidden()`` reads the optional ``nav.config.json`` at app root once
    (fail-open to empty on missing/malformed — the app must never fail to render nav, FR-7).
    """
    head = header_nav(
        source_file,
        schema_sha256(schema_text),
        schema_sha256(views_text or ""),
        schema_sha256(pages_text or ""),
        "nav-registry",
    )
    rows = ",\n".join(
        f"    {{'key': {n.key!r}, 'label': {n.label!r}, 'href': {n.href!r}, 'group': {n.group!r}}}"
        for n in nav_registry(schema_text, views_text, pages_text)
    )
    body = f'''from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, FrozenSet, List

# The deterministic, all-visible default top-navigation registry (one entry per navigable surface).
DEFAULT_NAV: List[Dict[str, str]] = [
{rows}
]

# Where an operator lists hidden nav keys to hide them across restarts (FR-6). Override with
# STARTD8_NAV_CONFIG; default is `nav.config.json` at the app root (sibling of the `app/` package).
_CONFIG_PATH = os.environ.get(
    "STARTD8_NAV_CONFIG", str(Path(__file__).resolve().parent.parent / "nav.config.json")
)


def load_hidden() -> FrozenSet[str]:
    """The set of hidden nav keys from `nav.config.json`, read once at startup.

    Fail-open: a missing / unreadable / malformed config yields an empty set (all visible), so the
    app never fails to render its nav because of operator config (FR-7).
    """
    try:
        data: Any = json.loads(Path(_CONFIG_PATH).read_text())
        hidden = data.get("hidden", []) if isinstance(data, dict) else []
        return frozenset(str(k) for k in hidden)
    except Exception:
        return frozenset()


def visible_nav(hidden: FrozenSet[str] | None = None) -> List[Dict[str, str]]:
    """`DEFAULT_NAV` minus the hidden keys (defaults to the on-disk config)."""
    hidden = load_hidden() if hidden is None else hidden
    return [item for item in DEFAULT_NAV if item["key"] not in hidden]
'''
    return head + "\n\n" + body


def pages_owns_root(pages_text: Optional[str]) -> bool:
    """True if a content page already claims ``/`` — then the index must not (FR-28a)."""
    if not pages_text:
        return False
    from .pages_generator import parse_pages

    return any(p.slug == "/" for p in parse_pages(pages_text)[0])


_GROUP_LABELS = {"page": "Pages", "entity": "Records", "view": "Views"}


def render_index_page(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> str:
    """``app/templates/index.html`` (kind ``nav-index-page``) — the generated home/index (FR-28).

    Data-driven over the same registry as the nav (``request.app.state.nav`` = ``visible_nav()``), so it
    reflects the runtime visibility config (FR-6) and reuses the single source of truth (FR-19). Extends
    ``base.html`` (so it also carries the top nav). Accessible: one ``<h1>``, a ``<section>``/``<h2>``
    per non-empty group, a list of links (FR-28c). Labels/hrefs via ``{{ }}`` → Jinja auto-escapes.
    """
    head = header_nav_tmpl(
        source_file,
        schema_sha256(schema_text),
        schema_sha256(views_text or ""),
        schema_sha256(pages_text or ""),
        "nav-index-page",
    )
    groups_map = ", ".join(f"'{g}': '{label}'" for g, label in _GROUP_LABELS.items())
    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}Home{% endblock %}\n"
        "{% block content %}\n"
        "{% set _nav = request.app.state.nav if request and request.app.state.nav is defined else [] %}\n"
        "{% set _counts = nav_counts | default({}) %}\n"
        "{% set _labels = {" + groups_map + "} %}\n"
        '<h1 style="font-family:system-ui,-apple-system,sans-serif">What’s in this app</h1>\n'
        "{%- for group in ['page', 'entity', 'view'] %}\n"
        "{%- set _items = _nav | selectattr('group', 'equalto', group) | list %}\n"
        "{%- if _items %}\n"
        '  <section aria-labelledby="idx-{{ group }}" style="margin:1.25rem 0">\n'
        '    <h2 id="idx-{{ group }}" style="font-family:system-ui,-apple-system,sans-serif">'
        "{{ _labels[group] }}</h2>\n"
        "    <ul>\n"
        "{%- for item in _items %}\n"
        '      <li><a href="{{ item.href }}" style="color:#0a7d4b">{{ item.label }}</a>'
        "{%- if item.key in _counts %} "
        '<span style="color:#888">({{ _counts[item.key] }})</span>{% endif %}</li>\n'
        "{%- endfor %}\n"
        "    </ul>\n"
        "  </section>\n"
        "{%- endif %}\n"
        "{%- endfor %}\n"
        # FR-29e: discoverable link to the live admin toggle.
        '<p style="margin-top:1.5rem"><a href="/admin/nav" style="color:#0a7d4b">'
        "Manage navigation →</a></p>\n"
        "{% endblock %}\n"
    )
    return head + "\n" + body


def render_index_router(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> str:
    """``app/index.py`` (kind ``nav-index-router``) — serves the home/index at ``/`` (FR-28a).

    Always serves the stable ``/_index`` sitemap; **additionally** serves ``/`` when no content page
    owns it (FR-28a). Each handler computes per-entity **row counts** (FR-28f) for the visible entity
    surfaces and passes them to the template (``Records → Widget (12)``). ``main.py`` mounts it after
    ``pages_router`` as a belt-and-suspenders shadow guard. The on-disk bytes depend on ``pages.yaml``
    (whether ``/`` is claimed) — covered by the 3-sha header's ``pages-sha``."""
    head = header_nav(
        source_file,
        schema_sha256(schema_text),
        schema_sha256(views_text or ""),
        schema_sha256(pages_text or ""),
        "nav-index-router",
    )
    serves_root = not pages_owns_root(pages_text)
    root_route = (
        '@index_router.get("/", response_class=HTMLResponse)\n'
        "def index(request: Request, session: Session = Depends(get_session)):\n"
        '    """The home/index at ``/`` (no content page claims it) — same body as the sitemap."""\n'
        '    return templates.TemplateResponse(\n'
        '        request, "index.html", {"nav_counts": _entity_counts(request, session)}\n'
        "    )\n\n\n"
        if serves_root
        else ""
    )
    body = (
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from fastapi import APIRouter, Depends, Request\n"
        "from fastapi.responses import HTMLResponse\n"
        "from fastapi.templating import Jinja2Templates\n"
        "from sqlalchemy import func\n"
        "from sqlmodel import Session, select\n\n"
        "from . import tables\n"
        "from .db import get_session\n"
        "from .nav import DEFAULT_NAV  # noqa: F401  (kept importable for transparency)\n\n"
        'templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))\n'
        "index_router = APIRouter()\n\n\n"
        "def _entity_counts(request, session):\n"
        '    """Per-entity row counts for the VISIBLE entity nav items (FR-28f).\n\n'
        "    Keyed by nav key (``entity:<Name>``). Fail-open: any count that errors (missing table, DB\n"
        "    error) is simply omitted — the index must always render.\n"
        '    """\n'
        "    counts = {}\n"
        '    for item in getattr(request.app.state, "nav", []) or []:\n'
        '        if item.get("group") != "entity":\n'
        "            continue\n"
        '        model = getattr(tables, item["key"].split(":", 1)[1], None)\n'
        "        if model is None:\n"
        "            continue\n"
        "        try:\n"
        '            counts[item["key"]] = session.exec(\n'
        "                select(func.count()).select_from(model)\n"
        "            ).one()\n"
        "        except Exception:\n"
        "            pass  # fail-open: omit this count, never break the index\n"
        "    return counts\n\n\n"
        '@index_router.get("/_index", response_class=HTMLResponse)\n'
        "def sitemap(request: Request, session: Session = Depends(get_session)):\n"
        '    """The always-reachable sitemap — lists what is in this app, with row counts (FR-28/28e/28f)."""\n'
        '    return templates.TemplateResponse(\n'
        '        request, "index.html", {"nav_counts": _entity_counts(request, session)}\n'
        "    )\n\n\n"
        + root_route
        + '__all__ = ["index_router"]\n'
    )
    return head + "\n\n" + body


def render_nav_store(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """``app/nav.store.py`` → ``app/nav_store.py`` (kind ``nav-store``) — the live-toggle persistence (FR-29a).

    A presence-based ``nav_hidden(key, updated_at)`` table (a row = that key is hidden), created via an
    idempotent ``CREATE TABLE IF NOT EXISTS`` at startup with **raw SQL** — NOT a SQLModel model — so it
    is not in the user contract and is decoupled from ``create_all``/alembic (works byte-identically in
    both deployment modes). Visibility is the union of the FR-6 config file and this table.
    Schema-independent (constant body); the header carries schema-sha only for drift bookkeeping.
    """
    head = header_standard(source_file, schema_sha256(schema_text), "nav-store")
    body = '''from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Set

from sqlalchemy import text
from sqlmodel import Session

from .nav import DEFAULT_NAV, load_hidden

_DDL = (
    "CREATE TABLE IF NOT EXISTS nav_hidden ("
    "  key TEXT PRIMARY KEY,"
    "  updated_at TEXT"
    ")"
)


def ensure_nav_table(engine) -> None:
    """Create the nav_hidden table if absent (idempotent; mode-invariant — no create_all/alembic)."""
    with engine.begin() as conn:
        conn.execute(text(_DDL))


def db_hidden_keys(session: Session) -> Set[str]:
    """The set of nav keys hidden via the live admin toggle (presence in nav_hidden = hidden)."""
    try:
        return {row[0] for row in session.execute(text("SELECT key FROM nav_hidden")).all()}
    except Exception:
        return set()  # fail-open: never break nav rendering on a store error


def apply_hidden(session: Session, hidden_keys: Set[str]) -> None:
    """Make nav_hidden hold exactly *hidden_keys* — atomically, in one transaction/commit.

    The admin form fully specifies the desired state, so we DELETE-all + re-INSERT rather than upsert
    per key: a single commit (not one per nav entry), all-or-nothing on failure, and no dependency on
    ``ON CONFLICT`` (so it works on older SQLite too)."""
    session.execute(text("DELETE FROM nav_hidden"))
    stamp = datetime.now(timezone.utc).isoformat()
    for key in sorted(hidden_keys):
        session.execute(
            text("INSERT INTO nav_hidden (key, updated_at) VALUES (:k, :t)"),
            {"k": key, "t": stamp},
        )
    session.commit()


def resolve_visible(session: Session) -> List[Dict[str, str]]:
    """DEFAULT_NAV minus the union of config-hidden (FR-6) and DB-hidden (live toggle) keys (FR-29)."""
    hidden = set(load_hidden()) | db_hidden_keys(session)
    return [item for item in DEFAULT_NAV if item["key"] not in hidden]
'''
    return head + "\n\n" + body


def render_nav_admin_router(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """``app/nav_admin.py`` (kind ``nav-admin-router``) — the live admin toggle UI (FR-29b/c).

    Mode-INVARIANT bytes: auth is a **tolerant import** — enforced when ``app/auth.py`` exists (deployed),
    open when it doesn't (installed, loopback-only) with a banner. POST refreshes ``app.state.nav`` so the
    toggle is live in-process (FR-29d)."""
    head = header_standard(source_file, schema_sha256(schema_text), "nav-admin-router")
    body = '''from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from sqlmodel import Session

from .db import get_session
from .nav import DEFAULT_NAV
from .nav_store import apply_hidden, db_hidden_keys, resolve_visible

# Mode-aware auth, mode-invariant bytes: enforce when auth.py is present (deployed), else open
# (installed — loopback-only). `_SECURED` drives the unauthenticated banner in the template.
try:  # deployed mode emits app/auth.py
    from .auth import require_principal as _require_principal

    _guard = [Depends(_require_principal)]
    _SECURED = True
except ModuleNotFoundError:  # installed mode — no auth configured (local, loopback-only)
    _guard = []
    _SECURED = False

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
nav_admin_router = APIRouter()


@nav_admin_router.get("/admin/nav", response_class=HTMLResponse, dependencies=_guard)
def nav_admin(request: Request, session: Session = Depends(get_session)):
    """List every nav entry with its current visibility (config + DB) so an admin can toggle it."""
    hidden = db_hidden_keys(session)
    return templates.TemplateResponse(
        request,
        "nav_admin.html",
        {"entries": DEFAULT_NAV, "hidden": hidden, "secured": _SECURED},
    )


@nav_admin_router.post("/admin/nav", dependencies=_guard)
async def nav_admin_save(request: Request, session: Session = Depends(get_session)):
    """Apply the form: checked = visible, unchecked = hidden. Writes the DB and refreshes app.state.nav."""
    form = await request.form()
    visible = set(form.getlist("visible"))
    hidden = {item["key"] for item in DEFAULT_NAV if item["key"] not in visible}
    apply_hidden(session, hidden)  # one atomic transaction (not a commit per nav entry)
    request.app.state.nav = resolve_visible(session)  # live refresh (FR-29d)
    return RedirectResponse("/admin/nav", status_code=303)


__all__ = ["nav_admin_router"]
'''
    return head + "\n\n" + body


def render_nav_admin_page(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """``app/templates/nav_admin.html`` (kind ``nav-admin-page``) — the admin toggle form (FR-29b/c)."""
    head = header_nav_tmpl(  # Jinja-comment header; schema-only (views/pages shas are constant "")
        source_file, schema_sha256(schema_text), schema_sha256(""), schema_sha256(""), "nav-admin-page"
    )
    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}Manage navigation{% endblock %}\n"
        "{% block content %}\n"
        '<h1 style="font-family:system-ui,-apple-system,sans-serif">Manage navigation</h1>\n'
        "{%- if not secured %}\n"
        '  <p role="alert" style="background:#fff3cd;border:1px solid #ffe69c;padding:0.6rem 0.9rem">\n'
        "    ⚠ This admin page is <strong>unauthenticated</strong> (installed/local mode, "
        "loopback-only). Deploy with auth to protect it.</p>\n"
        "{%- endif %}\n"
        '<form method="post" action="/admin/nav">\n'
        '  <p style="color:#555">Unchecked items are hidden from the top nav and index '
        "(across restarts, until changed here).</p>\n"
        "{%- for item in entries %}\n"
        '  <div style="margin:0.25rem 0">\n'
        '    <label><input type="checkbox" name="visible" value="{{ item.key }}"'
        "{% if item.key not in hidden %} checked{% endif %}> "
        "{{ item.label }} <span style=\"color:#888\">({{ item.group }})</span></label>\n"
        "  </div>\n"
        "{%- endfor %}\n"
        '  <button type="submit" style="margin-top:0.75rem;padding:0.4rem 1rem">Save</button>\n'
        "</form>\n"
        "{% endblock %}\n"
    )
    return head + "\n" + body


def render_nav(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> List[Tuple[str, str]]:
    """The nav artifacts as ``(path, text)`` pairs — what the assembler emits (always-on, FR-13).

    Always emitted: the registry module, the nav partial, the home/index pair, and the live-toggle trio
    (nav_store + admin router + admin template, FR-29). The index is **always reachable at** ``/_index``
    and additionally serves ``/`` when no content page claims it — that route choice lives inside
    :func:`render_index_router` (FR-28a/28e), not here.
    """
    return [
        ("app/nav.py", render_nav_module(schema_text, views_text, pages_text, source_file)),
        ("app/templates/_nav.html", render_nav_partial(schema_text, views_text, pages_text, source_file)),
        ("app/index.py", render_index_router(schema_text, views_text, pages_text, source_file)),
        ("app/templates/index.html", render_index_page(schema_text, views_text, pages_text, source_file)),
        ("app/nav_store.py", render_nav_store(schema_text, source_file)),
        ("app/nav_admin.py", render_nav_admin_router(schema_text, source_file)),
        ("app/templates/nav_admin.html", render_nav_admin_page(schema_text, source_file)),
    ]
