"""SPIKE: default top-navigation registry + partial (3-input owned kind).

This is a *spike* to falsify the R3 risk in
``docs/design/default-navigation/DEFAULT_NAVIGATION_PLAN.md``: can an always-on nav be added as a
3-input (schema + views.yaml + pages.yaml) owned/deterministic kind that the real drift + skip-hook
machinery recognizes as ``$0``-owned and ``in_sync``? Only the pieces needed to answer that are built.

Enumeration is deterministic and aggregates all three navigable surface classes:
- content pages (pages.yaml): label = ``nav_label or title``, href = slug  (all-visible default, FR-2)
- entity CRUD UIs (schema):   label = titleized class name, href = ``/ui/<name.lower()>``  (FR-1a)
- views (views.yaml):         label = ``ViewSpec.name``, href = ``ViewSpec.route``  (FR-1b)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_nav_tmpl

NAV_KINDS = ("nav-partial",)


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
    """The deterministic, all-visible default nav registry. Order: page -> entity -> view."""
    entries: List[NavEntry] = []

    # pages.yaml (optional) — all-visible default: label falls back to title (NOT the nav_label filter)
    if pages_text:
        from .pages_generator import parse_pages

        pages, _ = parse_pages(pages_text)
        for p in pages:
            entries.append(
                NavEntry(
                    key=f"page:{p.slug}",
                    label=p.nav_label or p.title,
                    href=p.slug,
                    group="page",
                )
            )

    # entities (schema) — no label exists in generated code; derive one (FR-1a)
    from ..languages.prisma_parser import parse_prisma_schema
    from .crud_generator import _model_names

    schema = parse_prisma_schema(schema_text)
    for name in _model_names(schema, schema_text):
        entries.append(
            NavEntry(
                key=f"entity:{name}",
                label=_titleize(name),
                href=f"/ui/{name.lower()}",
                group="entity",
            )
        )

    # views.yaml (optional) — friendly name + route already exist (FR-1b)
    if views_text:
        from ..view_codegen.manifest import parse_views

        for v in parse_views(views_text, known_entities=frozenset(schema.models)):
            entries.append(
                NavEntry(key=f"view:{v.route}", label=v.name, href=v.route, group="view")
            )

    return tuple(entries)


def render_nav_partial(
    schema_text: str,
    views_text: Optional[str] = None,
    pages_text: Optional[str] = None,
    source_file: str = "prisma/schema.prisma",
) -> str:
    """``app/templates/_nav.html`` (kind ``nav-partial``) — the always-on top nav.

    Carries a 3-sha provenance header (schema + views.yaml + pages.yaml). The visibility filter is a
    runtime concern (startup-read config, FR-6) and is NOT baked here: the partial renders the FULL
    default set; ``visible_nav`` subtracts hidden keys at request time. So these bytes depend only on
    the three deterministic inputs.
    """
    head = header_nav_tmpl(
        source_file,
        schema_sha256(schema_text),
        schema_sha256(views_text or ""),
        schema_sha256(pages_text or ""),
        "nav-partial",
    )
    links: List[str] = []
    base_style = "margin-right:1.25rem;color:#0a7d4b;text-decoration:none"
    for n in nav_registry(schema_text, views_text, pages_text):
        active = "{% if request.url.path == " + repr(n.href) + " %};font-weight:700{% endif %}"
        # the runtime visibility gate: render only if this key is not hidden (config-driven, FR-7)
        links.append(
            "{% if " + repr(n.key) + " not in nav_hidden %}"
            f'<a href="{n.href}" style="{base_style}{active}">{n.label}</a>'
            "{% endif %}"
        )
    body = (
        '<nav style="padding:0.9rem 1.25rem;border-bottom:1px solid #e3e3e3;'
        'background:#fafafa;font-family:system-ui,-apple-system,sans-serif">'
        + "".join(links)
        + "</nav>\n"
    )
    return head + "\n" + body
