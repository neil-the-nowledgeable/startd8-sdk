"""Cap 1 (FR-PG-6/7/8): content-pages generation — strict parse, owned router/shell + untracked
prose fragment, nav injection into base.html, and the two-hash (schema + pages) drift model where a
``.md`` edit never flags drift but a ``pages.yaml`` edit does.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.backend_codegen import render_backend
from startd8.backend_codegen.drift import (
    check_drift,
    embedded_artifact_kind,
    embedded_entity,
    embedded_pages_sha,
    is_owned_generated_file,
)
from startd8.backend_codegen.htmx_generator import render_base_template
from startd8.backend_codegen.pages_generator import (
    nav_items,
    parse_pages,
    render_page_shell,
    render_pages,
    render_pages_router,
)

pytestmark = pytest.mark.unit

SCHEMA = """\
model Profile {
  id   String @id
  name String
}
"""

PAGES = """\
# the content manifest
pages:
  - slug: "/"
    title: "StartDate — Home"
    nav_label: "Home"
    content: pages/home.md
  - slug: "/how-it-works"
    title: "How it works"
    nav_label: "How it works"
    content: pages/how_it_works.md
nav:
  - { label: "Home", href: "/" }
  - { label: "Profile", href: "/ui/profile" }
  - { label: "How it works", href: "/how-it-works" }
"""

HOME_MD = "# Welcome\n\nLand your **next** start date.\n"
HOW_MD = "# How it works\n\n1. Add a profile\n2. Done\n"


# --------------------------------------------------------------------------- #
# Strict parse
# --------------------------------------------------------------------------- #

def test_parse_pages_happy():
    pages, nav = parse_pages(PAGES)
    assert [p.slug for p in pages] == ["/", "/how-it-works"]
    assert pages[0].name == "home" and pages[1].name == "how_it_works"
    assert nav is not None and nav[0] == {"label": "Home", "href": "/"}


@pytest.mark.parametrize(
    "bad, msg",
    [
        ("pages:\n  - {slug: '/', title: t, content: c, color: red}", "unknown keys"),
        ("pages:\n  - {slug: '/', content: c}", "missing required `title`"),
        ("pages:\n  - {slug: 'home', title: t, content: c}", "must start with '/'"),
        (
            "pages:\n  - {slug: '/', title: a, content: c}\n  - {slug: '/', title: b, content: d}",
            "duplicate slugs",
        ),
        (
            "pages:\n  - {slug: '/a-b', title: a, content: c}\n  - {slug: '/a_b', title: b, content: d}",
            "collide to the same file-name",
        ),
        ("nope: []", "top-level `pages:`"),
        ("pages: []", "declares no pages"),
        (
            "pages:\n  - {slug: '/', title: t, content: c}\nnav:\n  - {label: x}",
            "missing required `href`",
        ),
    ],
)
def test_parse_pages_strict_failures(bad, msg):
    with pytest.raises(ValueError) as exc:
        parse_pages(bad)
    assert msg in str(exc.value)


def test_nav_items_derives_when_no_override():
    no_nav = "pages:\n  - {slug: '/', title: Home, nav_label: Home, content: pages/home.md}\n"
    assert nav_items(no_nav) == [{"label": "Home", "href": "/"}]


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #

def test_router_one_route_per_slug_compiles():
    router = render_pages_router(SCHEMA, PAGES)
    compile(router, "<pages>", "exec")
    assert "@pages_router.get('/', response_class=HTMLResponse)" in router
    assert "def page_home(request: Request):" in router
    assert "@pages_router.get('/how-it-works', response_class=HTMLResponse)" in router
    # request-first TemplateResponse (the runtime-verified Starlette signature)
    assert 'templates.TemplateResponse(request, "pages/home.html", {})' in router
    assert embedded_artifact_kind(router) == "pages-router"


def test_shell_extends_base_and_includes_untracked_fragment():
    shell = render_page_shell(SCHEMA, PAGES, "prisma/schema.prisma", "home")
    assert '{% extends "base.html" %}' in shell
    assert '{% include "pages/_home.body.html" %}' in shell
    assert "{% block title %}StartDate — Home{% endblock %}" in shell
    # no prose baked into the owned shell (so a .md edit can't change it)
    assert "Land your" not in shell
    assert embedded_artifact_kind(shell) == "pages-content"
    assert embedded_entity(shell) == "home"


def test_base_template_always_includes_nav_partial():
    """The top nav is now the always-on default-nav partial (FR-13/14): base.html includes
    ``_nav.html`` tolerantly in BOTH the schema-only and pages-configured shapes, and no longer
    inlines ``<nav>`` itself. The header kind still distinguishes the two shapes."""
    plain = render_base_template(SCHEMA)
    assert '{% include "_nav.html" ignore missing %}' in plain
    assert "<nav" not in plain  # nav markup lives in the partial, not base.html
    assert embedded_artifact_kind(plain) == "htmx-base"

    # FR-27: base.html is a single schema-only `htmx-base` kind always — and byte-identical whether or
    # not pages_text is given (its body no longer depends on pages; the nav lives in the partial).
    withpages = render_base_template(SCHEMA, "prisma/schema.prisma", PAGES)
    assert '{% include "_nav.html" ignore missing %}' in withpages
    assert "<nav" not in withpages
    assert embedded_artifact_kind(withpages) == "htmx-base"
    assert embedded_pages_sha(withpages) is None  # no pages-sha — base.html is schema-only now
    assert withpages == plain  # the `pages-base` two-hash variant was retired

    # The nav is now a generic, data-driven partial (FR-19): it iterates the registry resolved at
    # startup (request.app.state.nav) rather than baking the links, with a11y + active state (FR-16/17).
    from startd8.backend_codegen.nav_generator import render_nav_partial

    partial = render_nav_partial(SCHEMA, None, PAGES)
    assert '<nav aria-label="Primary"' in partial  # FR-16 labelled landmark
    assert "{%- for item in _nav %}" in partial  # data-driven over app.state.nav
    assert 'aria-current="page"' in partial  # FR-16 active item
    assert "{{ item.href }}" in partial and "{{ item.label }}" in partial  # auto-escaped (FR-19)
    assert "request.url.path.startswith(item.href ~ '/')" in partial  # FR-17 nested active match
    assert "item.group !=" in partial  # FR-18 group separator
    # No baked per-page links anymore — the rendered links come from the runtime registry.
    assert '<a href="/how-it-works"' not in partial


def test_body_fragment_is_rendered_at_generate_time_and_untracked(tmp_path):
    app_dir = tmp_path / "app"
    (app_dir / "pages").mkdir(parents=True)
    (app_dir / "pages" / "home.md").write_text(HOME_MD, encoding="utf-8")
    (app_dir / "pages" / "how_it_works.md").write_text(HOW_MD, encoding="utf-8")

    arts = dict(render_pages(SCHEMA, PAGES, app_dir=app_dir))
    frag = arts["app/templates/pages/_home.body.html"]
    assert "<h1>Welcome</h1>" in frag  # markdown rendered at generate time
    assert "<strong>next</strong>" in frag
    # the fragment is NOT owned/drift-tracked (no provenance header)
    assert is_owned_generated_file(frag) is False
    # the owned artifacts ARE recognized
    assert is_owned_generated_file(arts["app/pages.py"]) is True
    assert is_owned_generated_file(arts["app/templates/pages/home.html"]) is True


def test_render_pages_missing_md_is_loud(tmp_path):
    app_dir = tmp_path / "app"
    (app_dir / "pages").mkdir(parents=True)  # no .md files written
    with pytest.raises(ValueError) as exc:
        render_pages(SCHEMA, PAGES, app_dir=app_dir)
    assert "content file not found" in str(exc.value)


# --------------------------------------------------------------------------- #
# Drift — the load-bearing behavior
# --------------------------------------------------------------------------- #

def test_drift_in_sync_then_stale_on_pages_edit():
    shell = render_page_shell(SCHEMA, PAGES, "prisma/schema.prisma", "home")
    assert check_drift(SCHEMA, shell, pages_text=PAGES).status == "in_sync"
    # editing pages.yaml (e.g. a title) → stale
    edited = PAGES.replace("StartDate — Home", "StartDate — Start")
    assert check_drift(SCHEMA, shell, pages_text=edited).status == "stale"


def test_drift_md_edit_does_not_flag():
    # The owned shell/router/base never embed prose, so any .md change leaves them in_sync.
    for owned in (
        render_page_shell(SCHEMA, PAGES, "prisma/schema.prisma", "home"),
        render_pages_router(SCHEMA, PAGES),
        render_base_template(SCHEMA, "prisma/schema.prisma", PAGES),
    ):
        assert check_drift(SCHEMA, owned, pages_text=PAGES).status == "in_sync"


def test_drift_hand_edit_is_tampered():
    shell = render_page_shell(SCHEMA, PAGES, "prisma/schema.prisma", "home")
    tampered = shell.replace("{% endblock %}", "{% endblock %}\n<!-- hi -->")
    assert check_drift(SCHEMA, tampered, pages_text=PAGES).status == "tampered"


def test_pages_kind_without_manifest_errors():
    shell = render_page_shell(SCHEMA, PAGES, "prisma/schema.prisma", "home")
    assert check_drift(SCHEMA, shell, pages_text=None).status == "error"


# --------------------------------------------------------------------------- #
# Assembler integration
# --------------------------------------------------------------------------- #

def test_render_backend_includes_pages_and_nav(tmp_path):
    app_dir = tmp_path / "app"
    (app_dir / "pages").mkdir(parents=True)
    (app_dir / "pages" / "home.md").write_text(HOME_MD, encoding="utf-8")
    (app_dir / "pages" / "how_it_works.md").write_text(HOW_MD, encoding="utf-8")

    arts = dict(render_backend(SCHEMA, pages_text=PAGES, pages_app_dir=app_dir))
    assert "app/pages.py" in arts
    assert "app/templates/pages/home.html" in arts
    assert "app/templates/pages/_home.body.html" in arts
    # base.html includes the nav partial and is the schema-only htmx-base kind (FR-27)
    assert embedded_artifact_kind(arts["app/templates/base.html"]) == "htmx-base"
    # main.py mounts the optional pages_router
    assert "from .pages import pages_router" in arts["app/main.py"]


def test_render_backend_without_pages_is_unchanged():
    arts = dict(render_backend(SCHEMA))
    assert "app/pages.py" not in arts
    assert embedded_artifact_kind(arts["app/templates/base.html"]) == "htmx-base"
