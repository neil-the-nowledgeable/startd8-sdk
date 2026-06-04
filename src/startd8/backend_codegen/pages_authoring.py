"""UI-driven page-authoring generator (Authoring Phases 1–4).

Emits a small **owned, in-app** authoring surface so a content page can be created/edited from a web
UI instead of hand-editing files — under the *design-time author + regenerate* model: the UI writes
the generator **inputs** (`pages.yaml` entry + `app/pages/*.md`); the page goes live on the next
`startd8 generate backend --pages`. Gated behind ``--pages-authoring`` (requires ``--pages``).

Why a *generated* validator and not an SDK import: the generated app must never depend on the SDK,
and ships no `pyyaml` by default. So the strict-parse rules of ``pages_generator.parse_pages`` are
**re-emitted as owned code** in ``app/pages_io.py`` (NFR-UI-3), and ``pyyaml`` is added to the app's
runtime requirements only when authoring is enabled (NFR-UI-4).

Artifacts (all owned, schema-hashed via the standard 1-hash header — they are generic, i.e. they do
not vary with ``pages.yaml`` content or the entity schema):
- ``app/pages_io.py``                         — safe read/append `pages.yaml` + read/write prose; path-safe.
- ``app/pages_admin.py``                       — ``pages_admin_router`` with the authoring routes.
- ``app/templates/pages/_authoring.html``      — the add form + body editor + authored-pages list.
"""

from __future__ import annotations

from typing import List, Tuple

from ..frontend_codegen.schema_renderer import schema_sha256
from ._headers import header_standard

AUTHORING_KINDS = ("pages-io", "pages-admin", "pages-admin-tmpl")


def _tmpl_header(source_file: str, sha: str, kind: str) -> str:
    """A Jinja ``{# … #}`` comment wrapping the standard ``#`` provenance lines (drift-compatible)."""
    return (
        "{#\n"
        f"# GENERATED from {source_file} — do not edit by hand; "
        f"regenerate via `startd8 generate backend`.\n"
        f"# startd8-artifact: {kind}\n"
        f"# Source of truth: the Prisma schema.\n"
        f"# schema-sha256: {sha}\n"
        "#}"
    )


# --------------------------------------------------------------------------- #
# app/pages_io.py — safe, SDK-free file IO for the authoring routes
# --------------------------------------------------------------------------- #

_PAGES_IO_BODY = r'''from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

import yaml

# Resolve the project inputs from this file's location: app/pages_io.py -> project root is app/'s parent.
_APP_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _APP_DIR.parent
_PAGES_YAML = _PROJECT_ROOT / "prisma" / "pages.yaml"
_PAGES_DIR = _APP_DIR / "pages"

# The pages.yaml contract, re-stated here as owned code (the app must not import the SDK).
_PAGE_KEYS = {"slug", "title", "nav_label", "content"}


class PageError(ValueError):
    """A human-friendly validation/IO failure surfaced back into the authoring form."""


def slugify(slug: str) -> str:
    """``/`` -> ``home``; ``/how-it-works`` -> ``how_it_works`` (the stable page file-name)."""
    s = re.sub(r"[^0-9a-zA-Z]+", "_", slug.strip("/")).strip("_").lower()
    return s or "home"


def content_path_for(slug: str) -> str:
    return "pages/%s.md" % slugify(slug)


def _load() -> dict:
    if not _PAGES_YAML.is_file():
        return {"pages": []}
    data = yaml.safe_load(_PAGES_YAML.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PageError("pages.yaml is malformed (not a mapping)")
    return data


def list_pages() -> List[dict]:
    """The current page entries (each a dict with at least slug/title/content)."""
    return list(_load().get("pages") or [])


def _validate_all(data: dict) -> None:
    """Re-validate the full manifest — kept at PARITY with the SDK `parse_pages` so the UI never
    accepts a manifest the next `generate backend --pages` would reject (CRP R1-F4/S4). Checks: page
    key-set/required/slug-format/dup-slug, **derived file-name collision**, and **`nav:` items**.
    """
    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise PageError("pages.yaml must have a non-empty `pages:` list")
    seen = set()
    for i, entry in enumerate(pages):
        if not isinstance(entry, dict):
            raise PageError("page #%d must be a mapping" % i)
        unknown = set(entry) - _PAGE_KEYS
        if unknown:
            raise PageError("page #%d has unknown keys %s" % (i, sorted(unknown)))
        for req in ("slug", "title", "content"):
            if not entry.get(req):
                raise PageError("page #%d missing required `%s`" % (i, req))
        slug = str(entry["slug"])
        if not slug.startswith("/"):
            raise PageError("slug must start with '/': %r" % slug)
        if slug in seen:
            raise PageError("duplicate slug: %s" % slug)
        seen.add(slug)
    names = [slugify(str(e["slug"])) for e in pages]
    if len(set(names)) != len(names):
        raise PageError("pages whose slugs collide to the same file-name: %s" % names)
    nav = data.get("nav")
    if nav is not None:
        if not isinstance(nav, list):
            raise PageError("`nav:` must be a list")
        for j, item in enumerate(nav):
            if not isinstance(item, dict):
                raise PageError("nav[%d] must be a mapping" % j)
            bad = set(item) - {"label", "href"}
            if bad:
                raise PageError("nav[%d] has unknown keys %s" % (j, sorted(bad)))
            for req in ("label", "href"):
                if not item.get(req):
                    raise PageError("nav[%d] missing required `%s`" % (j, req))


def validate_new(slug: str, title: str) -> None:
    """Validate a *proposed* new page before any write (friendly, field-level errors)."""
    if not slug or not slug.startswith("/"):
        raise PageError("Slug must start with '/' (e.g. /about).")
    if not title or not title.strip():
        raise PageError("Title is required.")
    existing = [str(p.get("slug")) for p in list_pages()]
    if slug in existing:
        raise PageError("A page with slug %s already exists." % slug)
    name = slugify(slug)
    if any(slugify(s) == name for s in existing):
        raise PageError("That slug collides with an existing page file-name (%s)." % name)


def _format_block(entry: dict) -> str:
    """One page entry as an indented YAML block (2-space list indent), preserving key order."""
    dumped = yaml.safe_dump([entry], sort_keys=False, allow_unicode=True, default_flow_style=False)
    return "\n".join(("  " + line if line else line) for line in dumped.splitlines())


def _insert_into_pages_block(text: str, block: str) -> str:
    """Insert *block* at the end of the top-level ``pages:`` list, preserving comments + ``nav:``."""
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.match(r"^pages\s*:\s*$", line):
            start = i
            break
    if start is None:
        raise PageError("pages.yaml has no top-level `pages:` list to append to.")
    # The block runs until the next top-level key (a non-indented, non-blank, non-comment line).
    end = len(lines)
    for j in range(start + 1, len(lines)):
        s = lines[j]
        if s and not s[0].isspace() and not s.lstrip().startswith("#"):
            end = j
            break
    insert_at = end
    # Trim trailing blank lines inside the block so the new entry sits flush under the last page.
    while insert_at - 1 > start and not lines[insert_at - 1].strip():
        insert_at -= 1
    new_lines = lines[:insert_at] + block.splitlines() + lines[insert_at:]
    return "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")


def append_page(slug: str, title: str, nav_label: Optional[str] = None) -> dict:
    """Validate + append one page entry to pages.yaml, preserving the file; re-validate the result."""
    validate_new(slug, title)
    entry = {"slug": slug, "title": title.strip(), "content": content_path_for(slug)}
    if nav_label and nav_label.strip():
        entry["nav_label"] = nav_label.strip()
    original = _PAGES_YAML.read_text(encoding="utf-8") if _PAGES_YAML.is_file() else "pages:\n"
    new_text = _insert_into_pages_block(original, _format_block(entry))
    # Never commit a manifest that wouldn't parse. A YAMLError here (e.g. an unusual existing indent
    # the text-insert can't match) is surfaced as a friendly PageError, NOT a raw 500 — and because
    # the write happens only after this succeeds, the on-disk file is never left corrupted.
    try:
        reparsed = yaml.safe_load(new_text) or {}
    except yaml.YAMLError as exc:
        raise PageError(
            "Could not safely add the page — pages.yaml has an unexpected shape. "
            "Edit it by hand, then retry. (%s)" % exc
        )
    _validate_all(reparsed)
    _PAGES_YAML.write_text(new_text, encoding="utf-8")
    return entry


def _prose_path(slug: str) -> Path:
    """The on-disk prose path for *slug*, confined to app/pages/ (path-traversal safe)."""
    name = slugify(slug)
    path = (_PAGES_DIR / ("%s.md" % name)).resolve()
    if path.parent != _PAGES_DIR.resolve():
        raise PageError("Refusing to write outside app/pages/.")
    return path


def write_prose(slug: str, markdown: str) -> Path:
    path = _prose_path(slug)
    _PAGES_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown if markdown is not None else "", encoding="utf-8")
    return path


def read_prose(slug: str) -> str:
    path = _prose_path(slug)
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def remove_prose(slug: str) -> None:
    path = _prose_path(slug)
    if path.is_file():
        path.unlink()
'''


def render_pages_io(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """``app/pages_io.py`` — owned, SDK-free file IO + validator for the authoring routes (kind ``pages-io``)."""
    header = header_standard(source_file, schema_sha256(schema_text), "pages-io")
    return header + "\n\n" + _PAGES_IO_BODY


# --------------------------------------------------------------------------- #
# app/pages_admin.py — the authoring routes
# --------------------------------------------------------------------------- #

_PAGES_ADMIN_BODY = r'''from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .pages_io import (
    PageError,
    append_page,
    list_pages,
    read_prose,
    remove_prose,
    slugify,
    validate_new,
    write_prose,
)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
pages_admin_router = APIRouter()

# The exact command that publishes a draft (design-time author + regenerate — no auto-regen).
_PUBLISH_HINT = "startd8 generate backend --schema prisma/schema.prisma --pages prisma/pages.yaml --out ."


def _safe_pages():
    """Current pages as a list of dicts; tolerant of a hand-corrupted manifest (never raises)."""
    try:
        return [p for p in list_pages() if isinstance(p, dict)]
    except PageError:
        return None  # signals "manifest unreadable" to the view


def _find(name):
    return next((p for p in (_safe_pages() or []) if slugify(str(p.get("slug"))) == name), None)


def _view(request, *, message="", error="", form=None, editing=None):
    raw = _safe_pages()
    if raw is None:
        raw, error = [], (error or "pages.yaml could not be read — fix it by hand to manage pages here.")
    # Augment each entry with its derived file-name so the template's edit link matches the route.
    pages = [dict(p, name=slugify(str(p.get("slug")))) for p in raw]
    return templates.TemplateResponse(
        request,
        "pages/_authoring.html",
        {
            "pages": pages,
            "message": message,
            "error": error,
            "form": form or {},
            "editing": editing,
            "publish_hint": _PUBLISH_HINT,
        },
    )


@pages_admin_router.get("/ui/pages", response_class=HTMLResponse)
def authoring_home(request: Request):
    """List authored pages + the add-page form."""
    return _view(request)


@pages_admin_router.post("/ui/pages", response_class=HTMLResponse)
async def create_page(request: Request):
    """Create a page end-to-end: append the pages.yaml entry AND write the .md, atomically."""
    form = await request.form()
    slug = (form.get("slug") or "").strip()
    title = (form.get("title") or "").strip()
    nav_label = (form.get("nav_label") or "").strip()
    body = form.get("body") or ""
    try:
        # Validate the proposed page BEFORE touching disk, so a bad/duplicate slug never clobbers an
        # existing page's prose. Only once it's known-new+valid do we write prose then commit the
        # manifest entry, rolling the (new) prose back if the entry write fails (FR-UI-3, atomic).
        validate_new(slug, title)
        write_prose(slug, body)
        try:
            append_page(slug, title, nav_label)
        except Exception:
            remove_prose(slug)
            raise
    except PageError as exc:
        return _view(
            request,
            error=str(exc),
            form={"slug": slug, "title": title, "nav_label": nav_label, "body": body},
        )
    return _view(
        request,
        message=(
            "Saved “%s”. Run the command below to publish (the page goes live after regenerate)."
            % title
        ),
    )


@pages_admin_router.get("/ui/pages/{name}/edit", response_class=HTMLResponse)
def edit_page(name: str, request: Request):
    """Load an existing page's raw markdown into the editor (prose-only edit)."""
    match = _find(name)
    if match is None:
        return _view(request, error="No such page: %s" % name)
    slug = str(match.get("slug"))
    return _view(
        request,
        editing=name,
        form={
            "slug": slug,
            "title": str(match.get("title", "")),
            "nav_label": str(match.get("nav_label", "")),
            "body": read_prose(slug),
        },
    )


@pages_admin_router.post("/ui/pages/{name}", response_class=HTMLResponse)
async def update_prose(name: str, request: Request):
    """Save edited markdown back to app/pages/<name>.md (does not change the manifest entry)."""
    form = await request.form()
    match = _find(name)
    if match is None:
        return _view(request, error="No such page: %s" % name)
    slug = str(match.get("slug"))
    try:
        write_prose(slug, form.get("body") or "")
    except PageError as exc:
        return _view(request, error=str(exc))
    return _view(
        request,
        message="Updated “%s” prose. Regenerate to publish the change." % name,
    )


__all__ = ["pages_admin_router"]
'''


def render_pages_admin(schema_text: str, source_file: str = "prisma/schema.prisma") -> str:
    """``app/pages_admin.py`` — the authoring routes (kind ``pages-admin``)."""
    header = header_standard(source_file, schema_sha256(schema_text), "pages-admin")
    return header + "\n\n" + _PAGES_ADMIN_BODY


# --------------------------------------------------------------------------- #
# app/templates/pages/_authoring.html — the form + body editor + list
# --------------------------------------------------------------------------- #

_AUTHORING_TMPL_BODY = r'''{% extends "base.html" %}
{% block title %}Pages{% endblock %}
{% block content %}
<h1>Pages</h1>

{% if message %}<p style="padding:.6rem .8rem;background:#e7f6ee;border:1px solid #b6e0c8;border-radius:6px">{{ message }}</p>
<pre style="background:#0d1117;color:#e6edf3;padding:.8rem;border-radius:6px;overflow:auto"><code>{{ publish_hint }}</code></pre>{% endif %}
{% if error %}<p style="padding:.6rem .8rem;background:#fdecea;border:1px solid #f5c6cb;border-radius:6px;color:#a12">{{ error }}</p>{% endif %}

<h2>{% if editing %}Edit “{{ editing }}” prose{% else %}Add a page{% endif %}</h2>
<form method="post"
      action="{% if editing %}/ui/pages/{{ editing }}{% else %}/ui/pages{% endif %}">
  {% if not editing %}
  <div class="field">
    <label for="f-slug">Slug</label>
    <input type="text" name="slug" id="f-slug" value="{{ form.slug or '' }}"
           placeholder="/about" required>
    <small>The URL path. Must start with “/”. The markdown file name is derived from it.</small>
  </div>
  <div class="field">
    <label for="f-title">Title</label>
    <input type="text" name="title" id="f-title" value="{{ form.title or '' }}" required>
  </div>
  <div class="field">
    <label for="f-nav">Nav label (optional)</label>
    <input type="text" name="nav_label" id="f-nav" value="{{ form.nav_label or '' }}"
           placeholder="leave blank to hide from the nav">
  </div>
  {% endif %}
  <div class="field">
    <label for="f-body">Content (Markdown)</label>
    <textarea name="body" id="f-body" rows="14" style="width:100%;font-family:ui-monospace,monospace"
              placeholder="# Heading&#10;&#10;Your prose here.">{{ form.body or '' }}</textarea>
    <small>Supported: headings, <strong>**bold**</strong>, lists, links, tables (python-markdown
      “extra” + “sane_lists”). Rendered at generate time — no live preview.</small>
  </div>
  <button type="submit">{% if editing %}Save prose{% else %}Create page{% endif %}</button>
  {% if editing %}<a href="/ui/pages" style="margin-left:1rem">cancel</a>{% endif %}
</form>

<h2>Existing pages</h2>
<ul>
  {% for p in pages %}
  <li>
    <a href="{{ p.slug }}">{{ p.title }}</a>
    <code>{{ p.slug }}</code>
    — <a href="/ui/pages/{{ p.name }}/edit">edit prose</a>
  </li>
  {% endfor %}
</ul>
{% endblock %}
'''


def render_pages_admin_template(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> str:
    """``app/templates/pages/_authoring.html`` — the authoring UI (kind ``pages-admin-tmpl``)."""
    head = _tmpl_header(source_file, schema_sha256(schema_text), "pages-admin-tmpl")
    return head + "\n" + _AUTHORING_TMPL_BODY


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #

def render_authoring(
    schema_text: str, source_file: str = "prisma/schema.prisma"
) -> List[Tuple[str, str]]:
    """All authoring artifacts as ``(path, text)`` pairs (owned, schema-hashed)."""
    return [
        ("app/pages_io.py", render_pages_io(schema_text, source_file)),
        ("app/pages_admin.py", render_pages_admin(schema_text, source_file)),
        ("app/templates/pages/_authoring.html", render_pages_admin_template(schema_text, source_file)),
    ]
