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
    assert "index" in keys  # the sitemap is itself a nav entry (FR-28e)
    groups = {e.group for e in nav_registry(SCHEMA, VIEWS, PAGES)}
    assert groups == {"page", "entity", "view", "index"}


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


def test_index_router_routes_depend_on_root_page():
    from startd8.backend_codegen.nav_generator import index_route

    page_root = "pages:\n  - slug: /\n    title: Home\n    content: pages/home.md\n"
    page_other = "pages:\n  - slug: /about\n    title: About\n    content: pages/about.md\n"

    # No content page owns `/` → index serves BOTH `/_index` (stable) and `/` (home).
    free = render_index_router(SCHEMA, VIEWS, page_other)
    assert '@index_router.get("/_index"' in free
    assert '@index_router.get("/", response_class=HTMLResponse)' in free
    assert index_route(page_other) == "/"

    # A content page owns `/` → index serves ONLY `/_index` (sitemap); `/` is left to the page.
    taken = render_index_router(SCHEMA, VIEWS, page_root)
    assert '@index_router.get("/_index"' in taken
    assert '@index_router.get("/", response_class=HTMLResponse)' not in taken
    assert index_route(page_root) == "/_index"


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


# --- FR-26: entity nav-label override via the schema `/// @nav` doc-comment ----------------------

def test_entity_nav_label_override_from_schema():
    """`/// @nav <Label>` overrides the derived entity label; the key (identity) is unchanged."""
    annotated = (
        "/// @nav People\n"
        "model Person {\n  id String @id\n  name String\n}\n"
        "model InvoiceLine {\n  id String @id\n}\n"
    )
    by_key = {e.key: e for e in nav_registry(annotated)}
    # overridden label, identity key unchanged
    assert by_key["entity:Person"].label == "People"
    # un-annotated entity still gets the title-cased default
    assert by_key["entity:InvoiceLine"].label == "Invoice Line"


def test_entity_label_defaults_when_no_annotation():
    by_key = {e.key: e for e in nav_registry("model Widget {\n  id String @id\n}\n")}
    assert by_key["entity:Widget"].label == "Widget"


# --- FR-29: live admin toggle (store + mode-aware admin router) -----------------------------------

def test_nav_admin_router_is_mode_invariant_with_tolerant_auth():
    """FR-29c: the admin router is byte-identical across modes; auth is a tolerant import (enforced
    when app/auth.py exists = deployed, open otherwise = installed)."""
    from startd8.backend_codegen.nav_generator import render_nav_admin_router

    installed = render_nav_admin_router(SCHEMA)
    # the mode-aware-but-mode-invariant wiring
    assert "from .auth import require_principal" in installed
    assert "_guard = [Depends(_require_principal)]" in installed
    assert "dependencies=_guard" in installed
    # the generated router must be identical regardless of deployment mode (mode-invariant bytes)
    from startd8.backend_codegen import render_backend

    inst = dict(render_backend(SCHEMA, deployment_mode="installed"))["app/nav_admin.py"]
    depl = dict(render_backend(SCHEMA, deployment_mode="deployed"))["app/nav_admin.py"]
    assert inst == depl


def test_nav_store_uses_raw_sql_not_a_sqlmodel_table():
    """FR-29a: the system table is raw SQL (CREATE TABLE IF NOT EXISTS) — NOT a SQLModel model — so it
    stays out of the user contract and out of create_all/alembic."""
    from startd8.backend_codegen.nav_generator import render_nav_store

    store = render_nav_store(SCHEMA)
    assert "CREATE TABLE IF NOT EXISTS nav_hidden" in store
    assert "table=True" not in store  # not a SQLModel table
    assert "def resolve_visible" in store and "load_hidden" in store  # config UNION db composition
