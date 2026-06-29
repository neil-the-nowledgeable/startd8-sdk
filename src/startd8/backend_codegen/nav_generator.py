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
from ._headers import header_nav, header_nav_tmpl

NAV_KINDS = ("nav-registry", "nav-partial")

# Owned output paths → artifact kind (mirrors pages_layout / the CANONICAL_LAYOUT precedent).
NAV_LAYOUT: Dict[str, str] = {
    "app/nav.py": "nav-registry",
    "app/templates/_nav.html": "nav-partial",
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

    # entities (schema) — no label exists in generated code; derive one (FR-1a)
    from ..languages.prisma_parser import parse_prisma_schema
    from .crud_generator import _model_names

    schema = parse_prisma_schema(schema_text)
    for name in _model_names(schema, schema_text):
        entries.append(
            NavEntry(key=f"entity:{name}", label=_titleize(name), href=f"/ui/{name.lower()}", group="entity")
        )

    # views.yaml `views:` section (optional) — friendly name + route already exist (FR-1b). NOTE:
    # views.yaml is a MULTI-section manifest (views:/forms:/flows:/editors:); an app may declare only
    # `flows:` with no top-level `views:`. parse_views is strict, so enumerate views only when the
    # `views:` section is actually present (else this is a forms/flows/editors-only manifest).
    if views_text and _has_views_section(views_text):
        from ..view_codegen.manifest import parse_views

        for v in parse_views(views_text, known_entities=frozenset(schema.models)):
            entries.append(NavEntry(key=f"view:{v.route}", label=v.name, href=v.route, group="view"))

    return tuple(entries)


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


def render_nav(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> List[Tuple[str, str]]:
    """Both nav artifacts as ``(path, text)`` pairs — what the assembler emits (always-on, FR-13)."""
    return [
        ("app/nav.py", render_nav_module(schema_text, views_text, pages_text, source_file)),
        ("app/templates/_nav.html", render_nav_partial(schema_text, views_text, pages_text, source_file)),
    ]
