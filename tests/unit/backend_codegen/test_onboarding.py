"""``onboarding:`` archetype — first-run welcome / tips-as-content / empty-state checklist."""

from __future__ import annotations

import pytest

from startd8.backend_codegen.onboarding_manifest import parse_onboarding
from startd8.backend_codegen.onboarding_generator import render_onboarding
from startd8.backend_codegen.crud_generator import render_main
from startd8.backend_codegen.drift import (
    embedded_artifact_kind,
    owned_file_in_sync,
)
from startd8.backend_codegen.pages_generator import render_pages_router

pytestmark = pytest.mark.unit

SCHEMA = """
model Profile {
  id   String @id @default(cuid())
  name String
}
model Metric {
  id        String @id @default(cuid())
  profileId String
  value     Float
}
model Note {
  id    String @id @default(cuid())
  body  String
}
""".strip()

VIEWS = """
onboarding:
  route: /welcome
  title: Welcome
  lead: A short orientation — skip anytime.
  continue_href: /ui/profile
  help_href: /about
  tips:
    - Start by adding a Profile
    - Metrics hang off a Profile
  empty_states:
    Profile: Add your first profile to get started.
    Note: Capture a note when you are ready.
""".strip()

PAGES = """
pages:
  - slug: /
    title: Home
    nav_label: Home
    content: pages/home.md
""".strip()

VIEWS_REDIRECT = """
onboarding:
  route: /welcome
  title: Welcome to your app
  nav_label: Welcome
  redirect_root_if_empty: true
  empty_states:
    Profile: Add a profile.
""".strip()


def test_parse_onboarding_basic():
    spec = parse_onboarding(VIEWS, known_entities=frozenset({"Profile", "Metric", "Note"}))
    assert spec is not None
    assert spec.route == "/welcome" and spec.title == "Welcome"
    assert spec.continue_href == "/ui/profile"
    assert len(spec.tips) == 2
    assert spec.empty_state_map["Profile"].startswith("Add your first")
    assert spec.redirect_root_if_empty is False
    assert spec.nav_text == "Welcome"


def test_parse_onboarding_nav_label_and_redirect():
    spec = parse_onboarding(
        VIEWS_REDIRECT, known_entities=frozenset({"Profile", "Metric", "Note"})
    )
    assert spec is not None
    assert spec.nav_label == "Welcome"
    assert spec.nav_text == "Welcome"
    assert spec.redirect_root_if_empty is True


def test_parse_onboarding_absent_is_tolerant():
    assert parse_onboarding("editors: {}\n") is None
    assert parse_onboarding("") is None
    assert parse_onboarding(None) is None


def test_parse_onboarding_unknown_key_loud():
    with pytest.raises(ValueError, match="unknown keys"):
        parse_onboarding("onboarding:\n  route: /w\n  title: T\n  wizard: true\n")


def test_parse_onboarding_unknown_entity_loud():
    with pytest.raises(ValueError, match="unknown entity"):
        parse_onboarding(
            "onboarding:\n  route: /w\n  title: T\n  empty_states: {Ghost: hi}\n",
            known_entities=frozenset({"Profile"}),
        )


def test_render_onboarding_emits_three_artifacts():
    arts = render_onboarding(SCHEMA, VIEWS)
    paths = [p for p, _ in arts]
    assert paths == [
        "app/onboarding/welcome.py",
        "app/templates/onboarding/welcome.html",
        "app/onboarding/__init__.py",
    ]
    router = arts[0][1]
    assert "onboarding_welcome_router" in router
    assert "from app.tables import Profile" in router
    assert "from app.tables import Note" in router
    assert "def checklist_all_empty" in router
    # Starlette request-first TemplateResponse (legacy name-first 500s).
    assert 'TemplateResponse(\n        request,\n        "onboarding/welcome.html"' in router
    assert '"request": request' not in router
    tmpl = arts[1][1]
    assert "role=\"dialog\"" not in tmpl and "modal" not in tmpl.lower()
    assert "onboarding-tips" in tmpl
    assert "localStorage" in tmpl
    assert "onboarding-welcome" in tmpl
    assert "--hh-teal" in tmpl  # ledger-token fallbacks
    assert embedded_artifact_kind(router) == "fastapi-onboarding"
    assert embedded_artifact_kind(tmpl) == "onboarding-welcome"


def test_render_onboarding_absent_is_empty():
    assert render_onboarding(SCHEMA, "views: []\n") == []


def test_render_onboarding_ui_route_rejected():
    bad = "onboarding:\n  route: /ui/welcome\n  title: Nope\n"
    with pytest.raises(ValueError, match="/ui/"):
        render_onboarding(SCHEMA, bad)


def test_main_mount_unconditional():
    main = render_main(SCHEMA)
    assert "from .onboarding import onboarding_routers" in main
    assert "ModuleNotFoundError" in main


def test_nav_includes_onboarding_welcome():
    from startd8.backend_codegen.nav_generator import nav_registry

    entries = nav_registry(SCHEMA, VIEWS, pages_text=None)
    welcome = [e for e in entries if e.href == "/welcome"]
    assert len(welcome) == 1
    assert welcome[0].label == "Welcome"
    assert welcome[0].group == "page"


def test_nav_uses_nav_label_over_title():
    from startd8.backend_codegen.nav_generator import nav_registry

    entries = nav_registry(SCHEMA, VIEWS_REDIRECT, pages_text=None)
    welcome = [e for e in entries if e.href == "/welcome"]
    assert welcome[0].label == "Welcome"


def test_pages_root_redirect_when_flagged():
    router = render_pages_router(SCHEMA, PAGES, views_text=VIEWS_REDIRECT)
    assert "checklist_all_empty" in router
    assert "RedirectResponse(" in router and "/welcome" in router and "status_code=303" in router
    assert "forms-sha256:" in router
    plain = render_pages_router(SCHEMA, PAGES, views_text=VIEWS)
    assert "checklist_all_empty" not in plain
    assert "forms-sha256:" not in plain


def test_drift_round_trip_and_skip_hook():
    arts = dict(render_onboarding(SCHEMA, VIEWS))
    for path, text in arts.items():
        assert owned_file_in_sync(SCHEMA, text, views_text=VIEWS) is True, path
    again = dict(render_onboarding(SCHEMA, VIEWS))
    for path, text in arts.items():
        assert again[path] == text


def test_humanize_view_labels_in_nav():
    from startd8.backend_codegen.nav_generator import _humanize_view_label, nav_registry

    assert _humanize_view_label("chore_fairness") == "Chore Fairness"
    assert _humanize_view_label("rx-run-out") == "Rx Run Out"
    views = """
views:
  - name: chore_fairness
    kind: dashboard
    route: /views/chore-fairness
    root: Profile
onboarding:
  route: /welcome
  title: Welcome
""".strip()
    entries = nav_registry(SCHEMA, views, pages_text=None)
    view = [e for e in entries if e.group == "view"]
    assert view and view[0].label == "Chore Fairness"
