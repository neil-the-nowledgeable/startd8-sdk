"""Content-pages generator (Cap 1) — owned, non-entity pages from a ``pages.yaml`` manifest.

The mechanical-assembly thesis applied to *content* pages (home ``/``, how-it-works, …): the route,
the page template, and the site nav are **fixed-shape given the manifest**, so they are owned/$0/
generated. Only the page *prose* (``app/pages/*.md``) is authored — exactly like the AI layer, where
only the per-pass prompt is authored and the glue is generated.

Inputs: the ``.prisma`` schema (for the shared 2-hash provenance) + ``pages.yaml`` (the manifest) +
``app/pages/*.md`` (the prose, read at **generate** time and rendered to HTML so the running app needs
no ``markdown`` dependency).

Generated artifacts:
- ``app/pages.py``                         — a ``pages_router`` with one GET route per slug.
- ``app/templates/pages/<name>.html``      — owned shell (extends ``base.html``, includes the body),
                                             carries the 2-hash ``pages-content`` header.
- ``app/templates/pages/_<name>.body.html`` — the generate-time markdown render; **untracked** (no
                                             header) so editing the source ``.md`` never flags drift.

The nav is injected into ``base.html`` by the HTMX generator (``render_base_template``); see
:func:`build_nav_html`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_pages, header_pages_tmpl

# Content-page artifact kinds (registered into drift._PAGES_KINDS). ``pages-base`` is the nav-bearing
# base.html (emitted by htmx_generator), ``pages-router`` is app/pages.py, ``pages-content`` is a
# per-page shell template (carries the slug-name in the startd8-entity slot for re-render dispatch).
PAGES_KINDS = ("pages-base", "pages-router", "pages-content")

_PAGE_KEYS = {"slug", "title", "nav_label", "content"}
_NAV_KEYS = {"label", "href"}
_MD_EXTENSIONS = ["extra", "sane_lists"]  # mirrors the consumer POC's render settings


@dataclass(frozen=True)
class ContentPage:
    slug: str
    title: str
    content: str  # path to the markdown file, relative to app/ (e.g. "pages/home.md")
    nav_label: Optional[str] = None

    @property
    def name(self) -> str:
        """The stable file/route stem for this page (``/`` → ``home``; ``/how-it-works`` → ``how_it_works``)."""
        return _page_name(self.slug)


def _page_name(slug: str) -> str:
    s = re.sub(r"[^0-9a-zA-Z]+", "_", slug.strip("/")).strip("_").lower()
    return s or "home"


# --------------------------------------------------------------------------- #
# Strict parse (mirrors ai_layer.parse_ai_passes)
# --------------------------------------------------------------------------- #

def parse_pages(text: str) -> Tuple[Tuple[ContentPage, ...], Optional[Tuple[dict, ...]]]:
    """Parse + **strictly** validate ``pages.yaml`` (malformed → loud failure).

    Returns ``(pages, nav_override)`` where ``nav_override`` is ``None`` when no top-level ``nav:`` is
    declared (the nav is then derived from each page's ``nav_label``). Loud-fails on: a non-mapping
    root / missing ``pages:`` list, unknown per-page keys, missing required keys, non-``/`` slugs,
    duplicate slugs, duplicate derived page-names (would collide on disk), and malformed ``nav:`` items.
    """
    data = yaml.safe_load(text or "") or {}
    if not isinstance(data, dict) or "pages" not in data:
        raise ValueError("pages.yaml must be a mapping with a top-level `pages:` list")
    pages: List[ContentPage] = []
    for i, entry in enumerate(data["pages"] or []):
        if not isinstance(entry, dict):
            raise ValueError(f"pages.yaml: page #{i} must be a mapping")
        unknown = set(entry) - _PAGE_KEYS
        if unknown:
            raise ValueError(f"pages.yaml: page #{i} has unknown keys {sorted(unknown)}")
        for req in ("slug", "title", "content"):
            if not entry.get(req):
                raise ValueError(f"pages.yaml: page #{i} missing required `{req}`")
        slug = str(entry["slug"])
        if not slug.startswith("/"):
            raise ValueError(f"pages.yaml: slug must start with '/': {slug!r}")
        pages.append(
            ContentPage(
                slug=slug,
                title=str(entry["title"]),
                content=str(entry["content"]),
                nav_label=(str(entry["nav_label"]) if entry.get("nav_label") else None),
            )
        )
    if not pages:
        raise ValueError("pages.yaml declares no pages")
    slugs = [p.slug for p in pages]
    if len(set(slugs)) != len(slugs):
        raise ValueError(f"pages.yaml has duplicate slugs: {slugs}")
    names = [p.name for p in pages]
    if len(set(names)) != len(names):
        raise ValueError(f"pages.yaml has pages whose slugs collide to the same file-name: {names}")

    nav_override: Optional[Tuple[dict, ...]] = None
    if "nav" in data and data["nav"] is not None:
        items: List[dict] = []
        for j, item in enumerate(data["nav"] or []):
            if not isinstance(item, dict):
                raise ValueError(f"pages.yaml: nav[{j}] must be a mapping")
            bad = set(item) - _NAV_KEYS
            if bad:
                raise ValueError(f"pages.yaml: nav[{j}] has unknown keys {sorted(bad)}")
            for req in ("label", "href"):
                if not item.get(req):
                    raise ValueError(f"pages.yaml: nav[{j}] missing required `{req}`")
            items.append({"label": str(item["label"]), "href": str(item["href"])})
        nav_override = tuple(items)
    return tuple(pages), nav_override


def nav_items(text: str) -> List[dict]:
    """The resolved nav: the explicit ``nav:`` list if declared, else derived from ``nav_label``."""
    pages, override = parse_pages(text)
    if override is not None:
        return list(override)
    return [{"label": p.nav_label, "href": p.slug} for p in pages if p.nav_label]


# --------------------------------------------------------------------------- #
# Markdown render (build-time only — keeps the generated app dependency-free)
# --------------------------------------------------------------------------- #

def render_markdown(md_text: str) -> str:
    """Render markdown → HTML at GENERATE time (finding #1). ``markdown`` is an SDK build-time dep."""
    try:
        import markdown
    except ImportError as exc:  # pragma: no cover - install-time guard
        raise ValueError(
            "the `markdown` package is required to generate content pages "
            "(pip install 'markdown>=3.0.0')"
        ) from exc
    return markdown.markdown(md_text, extensions=_MD_EXTENSIONS)


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #

def _pages_sha(pages_text: str) -> str:
    return schema_sha256(pages_text)


def render_pages_router(
    schema_text: str, pages_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """``app/pages.py`` — a ``pages_router`` with one GET route per slug (kind ``pages-router``)."""
    pages, _ = parse_pages(pages_text)
    header = header_pages(source_file, schema_sha256(schema_text), _pages_sha(pages_text), "pages-router")
    routes: List[str] = []
    for p in pages:
        routes.append(
            f'@pages_router.get({p.slug!r}, response_class=HTMLResponse)\n'
            f"def page_{p.name}(request: Request):\n"
            f'    """Render the {p.slug!r} content page (prose rendered at generate time)."""\n'
            f'    return templates.TemplateResponse(request, "pages/{p.name}.html", {{}})'
        )
    body = (
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from fastapi import APIRouter, Request\n"
        "from fastapi.responses import HTMLResponse\n"
        "from fastapi.templating import Jinja2Templates\n\n"
        'templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))\n'
        "pages_router = APIRouter()\n\n\n"
        + "\n\n\n".join(routes)
        + '\n\n\n__all__ = ["pages_router"]\n'
    )
    return header + "\n\n" + body


def render_page_shell(
    schema_text: str, pages_text: str, source_file: str, slug_name: str
) -> str:
    """A per-page owned shell template ``app/templates/pages/<name>.html`` (kind ``pages-content``).

    Pure structure: extends ``base.html`` (so it inherits the nav) and ``{% include %}``s the untracked
    body fragment. Carries **no prose**, so it re-renders byte-identically regardless of any ``.md``
    edit — that is what keeps a prose edit out of the drift hash.
    """
    pages = {p.name: p for p in parse_pages(pages_text)[0]}
    page = pages.get(slug_name)
    if page is None:
        raise ValueError(f"no such page in manifest: {slug_name!r}")
    head = header_pages_tmpl(
        source_file, schema_sha256(schema_text), _pages_sha(pages_text), "pages-content", slug_name
    )
    body = (
        '{% extends "base.html" %}\n'
        "{% block title %}" + page.title + "{% endblock %}\n"
        "{% block content %}\n"
        '{% include "pages/_' + page.name + '.body.html" %}\n'
        "{% endblock %}\n"
    )
    return head + "\n" + body


def render_page_body_fragment(md_text: str) -> str:
    """The untracked rendered-prose fragment (``app/templates/pages/_<name>.body.html``). No header.

    Generate-time markdown→HTML. Not drift-tracked (no provenance header) so editing the source ``.md``
    never flags drift; it is overwritten on every regenerate.
    """
    return render_markdown(md_text) + "\n"


def build_nav_html(pages_text: str) -> str:
    """The ``<nav>`` markup injected into ``base.html`` (active link bolded via ``request.url.path``)."""
    items = nav_items(pages_text)
    links: List[str] = []
    base_style = "margin-right:1.25rem;color:#0a7d4b;text-decoration:none"
    for n in items:
        href = n["href"]
        label = n["label"]
        active = (
            "{% if request.url.path == " + repr(href) + " %};font-weight:700{% endif %}"
        )
        links.append(f'<a href="{href}" style="{base_style}{active}">{label}</a>')
    return (
        '  <nav style="padding:0.9rem 1.25rem;border-bottom:1px solid #e3e3e3;'
        'background:#fafafa;font-family:system-ui,-apple-system,sans-serif">'
        + "".join(links)
        + "</nav>\n"
    )


# --------------------------------------------------------------------------- #
# Layout + assembly
# --------------------------------------------------------------------------- #

def pages_layout(pages_text: str) -> Dict[str, str]:
    """Owned content-page output paths → kind (router + per-page shells). Fragments are untracked."""
    pages, _ = parse_pages(pages_text)
    layout: Dict[str, str] = {"app/pages.py": "pages-router"}
    for p in pages:
        layout[f"app/templates/pages/{p.name}.html"] = "pages-content"
    return layout


def render_pages(
    schema_text: str,
    pages_text: str,
    source_file: str = "prisma/schema.prisma",
    *,
    app_dir: Optional[Path] = None,
) -> List[Tuple[str, str]]:
    """Content-page artifacts as ``(path, text)`` pairs.

    Always emits the owned router + per-page shells. Emits the **untracked** body fragments only when
    *app_dir* is given (it reads ``app_dir/<page.content>``) — the write path passes it; the drift
    re-render path does not (fragments are untracked, so they never participate in ``--check``).
    A referenced ``.md`` missing on disk is a loud error.
    """
    pages, _ = parse_pages(pages_text)  # fail loud before emitting anything
    out: List[Tuple[str, str]] = [("app/pages.py", render_pages_router(schema_text, pages_text, source_file))]
    for p in pages:
        out.append(
            (f"app/templates/pages/{p.name}.html", render_page_shell(schema_text, pages_text, source_file, p.name))
        )
    if app_dir is not None:
        for p in pages:
            md_path = app_dir / p.content
            if not md_path.is_file():
                raise ValueError(
                    f"pages.yaml: content file not found for {p.slug!r}: {md_path} "
                    f"(expected under {app_dir}/)"
                )
            md_text = md_path.read_text(encoding="utf-8")
            out.append((f"app/templates/pages/_{p.name}.body.html", render_page_body_fragment(md_text)))
    return out
