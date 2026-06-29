"""SPIKE — falsify R3 for the always-on default nav (docs/design/default-navigation/).

Question: can an always-on nav be a 3-input (schema + views.yaml + pages.yaml) owned/deterministic
kind that the REAL drift + skip-hook machinery recognizes as $0-owned and in_sync — and flips stale
when ANY of the three inputs changes? These tests import the production drift functions directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.backend_codegen.drift import check_drift, owned_file_in_sync
from startd8.backend_codegen.nav_generator import (
    nav_registry,
    render_index_page,
    render_index_router,
    render_nav_partial,
)

FIX = Path(__file__).resolve().parents[2] / "fixtures" / "wireframe" / "prisma"
SCHEMA = (FIX / "schema.prisma").read_text()
VIEWS = (FIX / "views.yaml").read_text()
PAGES = (FIX / "pages.yaml").read_text()


def test_registry_aggregates_all_three_surface_classes():
    keys = {e.key for e in nav_registry(SCHEMA, VIEWS, PAGES)}
    # pages (all-visible default, incl. those with nav_label), entities (derived), views (as-is)
    assert {"page:/", "page:/about"} <= keys
    assert {"entity:Profile", "entity:Metric", "entity:Note"} <= keys
    assert "view:/views/profiles" in keys
    groups = {e.group for e in nav_registry(SCHEMA, VIEWS, PAGES)}
    assert groups == {"page", "entity", "view"}


def test_render_is_deterministic_byte_identical():
    a = render_nav_partial(SCHEMA, VIEWS, PAGES)
    b = render_nav_partial(SCHEMA, VIEWS, PAGES)
    assert a == b  # idempotency / byte-identical generation (FR-10)


def test_real_check_drift_in_sync():
    rendered = render_nav_partial(SCHEMA, VIEWS, PAGES)
    res = check_drift(SCHEMA, rendered, forms_text=VIEWS, pages_text=PAGES)
    assert res.status == "in_sync", res.detail


def test_real_skip_hook_recognizes_as_owned_in_sync():
    """The CORE R3 proof: owned_file_in_sync (the skip-hook predicate) recognizes the 3-input nav
    file as $0-owned, given it threads BOTH manifests (which it already does on its signature)."""
    rendered = render_nav_partial(SCHEMA, VIEWS, PAGES)
    assert owned_file_in_sync(SCHEMA, rendered, views_text=VIEWS, pages_text=PAGES) is True


@pytest.mark.parametrize(
    "mut_schema,mut_views,mut_pages",
    [
        (SCHEMA + "\nmodel Extra { id String @id }\n", VIEWS, PAGES),  # schema changed
        (SCHEMA, VIEWS + "\n  - name: extra\n    kind: dashboard\n    route: /x\n    root: Note\n", PAGES),  # views changed
        (SCHEMA, VIEWS, PAGES.replace("About", "Aboutt")),  # pages changed
    ],
    ids=["schema-change", "views-change", "pages-change"],
)
def test_three_input_staleness(mut_schema, mut_views, mut_pages):
    """A change to ANY of the three inputs must flip the original file to stale (3-input drift)."""
    rendered = render_nav_partial(SCHEMA, VIEWS, PAGES)
    res = check_drift(mut_schema, rendered, forms_text=mut_views, pages_text=mut_pages)
    assert res.status == "stale", res.detail
    assert owned_file_in_sync(mut_schema, rendered, views_text=mut_views, pages_text=mut_pages) is False


def test_hand_edit_is_tampered():
    rendered = render_nav_partial(SCHEMA, VIEWS, PAGES)
    tampered = rendered.replace("</nav>", '<a href="/evil">x</a></nav>')
    res = check_drift(SCHEMA, tampered, forms_text=VIEWS, pages_text=PAGES)
    assert res.status == "tampered", res.detail


def test_unthreaded_manifests_fall_through_safely():
    """If a caller forgets to thread the manifests, the skip-hook returns False (safe fall-through to
    LLM), NOT a false in_sync — this is the forms:/editors: bug class, and the nav kind inherits the
    correct safe behavior."""
    rendered = render_nav_partial(SCHEMA, VIEWS, PAGES)
    # pages_text omitted → pages-sha can't be recomputed → not recognized as in_sync
    assert owned_file_in_sync(SCHEMA, rendered, views_text=VIEWS) is False


# --- FR-28: home/index page (a 3-input owned kind in the nav family) -----------------------------

def test_index_page_template_lists_groups_accessibly():
    """The index template is data-driven over app.state.nav, grouped, with accessible headings."""
    page = render_index_page(SCHEMA, VIEWS, None)
    assert "{% extends \"base.html\" %}" in page
    assert "<h1" in page  # single top heading (FR-28c)
    assert "selectattr('group', 'equalto', group)" in page  # grouped by page/entity/view (FR-28b)
    assert 'aria-labelledby="idx-{{ group }}"' in page  # accessible sections
    assert "request.app.state.nav" in page  # single source of truth (FR-19/28b)


def test_index_router_serves_root():
    router = render_index_router(SCHEMA, VIEWS, None)
    assert '@index_router.get("/", response_class=HTMLResponse)' in router
    assert 'TemplateResponse(request, "index.html"' in router


def test_index_artifacts_drift_roundtrip():
    """Both index kinds round-trip through the real drift + skip-hook (3-input, like the rest of nav)."""
    page = render_index_page(SCHEMA, VIEWS, None)
    router = render_index_router(SCHEMA, VIEWS, None)
    for text in (page, router):
        assert check_drift(SCHEMA, text, forms_text=VIEWS, pages_text=None).status == "in_sync"
        assert owned_file_in_sync(SCHEMA, text, views_text=VIEWS, pages_text=None) is True
    # any input change → stale (3-input), same as the rest of the family
    mutated = SCHEMA + "\nmodel Extra { id String @id }\n"
    assert check_drift(mutated, page, forms_text=VIEWS, pages_text=None).status == "stale"
