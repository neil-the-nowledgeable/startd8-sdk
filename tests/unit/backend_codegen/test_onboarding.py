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


def test_parse_onboarding_basic():
    spec = parse_onboarding(VIEWS, known_entities=frozenset({"Profile", "Metric", "Note"}))
    assert spec is not None
    assert spec.route == "/welcome" and spec.title == "Welcome"
    assert spec.continue_href == "/ui/profile"
    assert len(spec.tips) == 2
    assert spec.empty_state_map["Profile"].startswith("Add your first")


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
    # Starlette request-first TemplateResponse (legacy name-first 500s).
    assert 'TemplateResponse(\n        request,\n        "onboarding/welcome.html"' in router
    assert '"request": request' not in router
    tmpl = arts[1][1]
    assert "role=\"dialog\"" not in tmpl and "modal" not in tmpl.lower()
    assert "onboarding-tips" in tmpl
    assert "localStorage" in tmpl
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


def test_drift_round_trip_and_skip_hook():
    arts = dict(render_onboarding(SCHEMA, VIEWS))
    for path, text in arts.items():
        assert owned_file_in_sync(SCHEMA, text, views_text=VIEWS) is True, path
    again = dict(render_onboarding(SCHEMA, VIEWS))
    for path, text in arts.items():
        assert again[path] == text
