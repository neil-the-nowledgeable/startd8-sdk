"""Kickoff-audience M1 (FR-1/FR-2/FR-3) — the persistence spine.

Covers the enum/coerce, the resolution ladder (flag > project > global > default=Intermediate), the
single canonical setter (project SOTTO-safe edit + global scope), strict manifest validation, and the
`startd8 kickoff audience` CLI. M1 writes ONLY the preference — no pre-pass, no build side effects.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.concierge import audience as aud
from startd8.concierge.audience import (
    DEFAULT_AUDIENCE,
    KickoffAudience,
    coerce_audience,
    resolve_audience_preference,
    set_audience_preference,
)
from startd8.kickoff_inputs import build_preferences as bp


# --- helpers -------------------------------------------------------------------------------------

_PREFS_REL = Path("docs") / "kickoff" / "inputs" / "build-preferences.yaml"


def _prefs_path(project_root: Path) -> Path:
    return project_root.joinpath(_PREFS_REL)


@pytest.fixture
def no_global(monkeypatch):
    """Isolate resolution from the real ~/.startd8 config: the global layer reports unset."""
    monkeypatch.setattr(aud, "_global_audience", lambda: None)


# --- drift guard ---------------------------------------------------------------------------------

def test_enum_values_match_manifest_valid_set():
    """The strict manifest validator's literal set MUST match the canonical enum (single source)."""
    assert {a.value for a in KickoffAudience} == set(bp._VALID_AUDIENCES)


def test_default_is_intermediate():
    assert DEFAULT_AUDIENCE is KickoffAudience.INTERMEDIATE


# --- coerce --------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("beginner", KickoffAudience.BEGINNER),
    ("INTERMEDIATE", KickoffAudience.INTERMEDIATE),
    ("  Advanced  ", KickoffAudience.ADVANCED),
    (KickoffAudience.BEGINNER, KickoffAudience.BEGINNER),
    (None, None),
    ("", None),
    ("expert", None),
    (42, None),
])
def test_coerce_audience(raw, expected):
    assert coerce_audience(raw) is expected


# --- resolution ladder ---------------------------------------------------------------------------

def test_resolve_default_when_unset(tmp_path, no_global):
    res = resolve_audience_preference(tmp_path)
    assert res.value is KickoffAudience.INTERMEDIATE
    assert res.source == "default"


def test_resolve_flag_wins(tmp_path, no_global):
    res = resolve_audience_preference(tmp_path, flag="beginner")
    assert res.value is KickoffAudience.BEGINNER
    assert res.source == "flag"


def test_resolve_project_layer(tmp_path, no_global):
    p = _prefs_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("domain: build-preferences\naudience: advanced\n", encoding="utf-8")
    res = resolve_audience_preference(tmp_path)
    assert res.value is KickoffAudience.ADVANCED
    assert res.source == "project"


def test_resolve_flag_beats_project(tmp_path, no_global):
    p = _prefs_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("domain: build-preferences\naudience: advanced\n", encoding="utf-8")
    res = resolve_audience_preference(tmp_path, flag="beginner")
    assert res.value is KickoffAudience.BEGINNER
    assert res.source == "flag"


def test_resolve_global_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(aud, "_global_audience", lambda: KickoffAudience.BEGINNER)
    res = resolve_audience_preference(tmp_path)  # no project file
    assert res.value is KickoffAudience.BEGINNER
    assert res.source == "global"


def test_resolve_project_beats_global(tmp_path, monkeypatch):
    monkeypatch.setattr(aud, "_global_audience", lambda: KickoffAudience.BEGINNER)
    p = _prefs_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("domain: build-preferences\naudience: advanced\n", encoding="utf-8")
    res = resolve_audience_preference(tmp_path)
    assert res.value is KickoffAudience.ADVANCED
    assert res.source == "project"


def test_resolve_ignores_malformed_project_sheet(tmp_path, no_global):
    """A malformed build-preferences.yaml degrades the project layer to unset (never crashes)."""
    p = _prefs_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("domain: build-preferences\naudience: expert\n", encoding="utf-8")  # invalid value
    res = resolve_audience_preference(tmp_path)
    assert res.value is KickoffAudience.INTERMEDIATE
    assert res.source == "default"


# --- setter: project scope (SOTTO-safe targeted edit) --------------------------------------------

def test_set_project_creates_minimal_sheet(tmp_path, no_global):
    result = set_audience_preference("beginner", project_root=tmp_path, scope="project")
    assert result.value is KickoffAudience.BEGINNER
    assert result.scope == "project"
    assert _prefs_path(tmp_path).is_file()
    # round-trips through the resolver
    assert resolve_audience_preference(tmp_path).value is KickoffAudience.BEGINNER


def test_set_project_preserves_existing_content(tmp_path, no_global):
    """The targeted edit must not disturb other keys/comments (SOTTO)."""
    p = _prefs_path(tmp_path)
    p.parent.mkdir(parents=True)
    original = (
        "# my build prefs\n"
        "domain: build-preferences\n"
        "guided: false\n"
        "budgets:\n"
        "  per_pipeline_run: $5.00\n"
    )
    p.write_text(original, encoding="utf-8")
    set_audience_preference("advanced", project_root=tmp_path, scope="project")
    text = p.read_text(encoding="utf-8")
    assert "# my build prefs" in text          # comment preserved
    assert "guided: false" in text             # sibling key preserved
    assert "per_pipeline_run: $5.00" in text   # nested value preserved
    assert "audience: advanced" in text
    # still strictly parseable, and both prefs survive
    parsed = bp.parse_build_preferences(text)
    assert parsed.audience == "advanced"
    assert parsed.guided is False


def test_set_project_replaces_existing_audience_line(tmp_path, no_global):
    p = _prefs_path(tmp_path)
    p.parent.mkdir(parents=True)
    p.write_text("domain: build-preferences\naudience: beginner\n", encoding="utf-8")
    set_audience_preference("advanced", project_root=tmp_path, scope="project")
    text = p.read_text(encoding="utf-8")
    assert text.count("audience:") == 1          # replaced, not duplicated
    assert "audience: advanced" in text


def test_set_project_refuses_to_touch_malformed_file(tmp_path, no_global):
    """Never mutate a sheet we can't parse — loud-fail and leave the file untouched."""
    p = _prefs_path(tmp_path)
    p.parent.mkdir(parents=True)
    bad = "domain: build-preferences\nunknown_key: x\n"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(ValueError):
        set_audience_preference("beginner", project_root=tmp_path, scope="project")
    assert p.read_text(encoding="utf-8") == bad  # untouched


# --- setter: global scope ------------------------------------------------------------------------

def test_set_global_scope(tmp_path, monkeypatch):
    from startd8.config import ConfigManager

    cm = ConfigManager(config_dir=tmp_path)
    monkeypatch.setattr("startd8.config.get_config_manager", lambda *a, **k: cm)
    result = set_audience_preference("advanced", scope="global")
    assert result.scope == "global"
    assert cm.get_preference("audience") == "advanced"


# --- setter: errors ------------------------------------------------------------------------------

def test_set_unknown_audience_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown audience"):
        set_audience_preference("expert", project_root=tmp_path)


def test_set_unknown_scope_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown scope"):
        set_audience_preference("beginner", project_root=tmp_path, scope="sideways")


# --- strict manifest validation ------------------------------------------------------------------

def test_manifest_accepts_valid_audience():
    m = bp.parse_build_preferences("domain: build-preferences\naudience: beginner\n")
    assert m.audience == "beginner"


def test_manifest_absent_audience_is_none():
    m = bp.parse_build_preferences("domain: build-preferences\n")
    assert m.audience is None


def test_manifest_rejects_unknown_audience():
    with pytest.raises(ValueError, match="audience"):
        bp.parse_build_preferences("domain: build-preferences\naudience: wizard\n")


def test_manifest_audience_is_top_level_key():
    assert "audience" in bp._TOP_LEVEL_KEYS


# --- CLI smoke -----------------------------------------------------------------------------------

def test_cli_audience_set_then_show(tmp_path, monkeypatch):
    import json

    from typer.testing import CliRunner

    from startd8.cli_concierge import audience_app

    monkeypatch.setattr(aud, "_global_audience", lambda: None)
    runner = CliRunner()

    r_set = runner.invoke(
        audience_app, ["set", "beginner", "--project", str(tmp_path), "--json"]
    )
    assert r_set.exit_code == 0, r_set.output
    assert json.loads(r_set.output)["audience"] == "beginner"

    r_show = runner.invoke(
        audience_app, ["show", "--project", str(tmp_path), "--json"]
    )
    assert r_show.exit_code == 0, r_show.output
    payload = json.loads(r_show.output)
    assert payload["audience"] == "beginner"
    assert payload["source"] == "project"


def test_cli_audience_set_invalid_exits_nonzero(tmp_path):
    from typer.testing import CliRunner

    from startd8.cli_concierge import audience_app

    r = CliRunner().invoke(audience_app, ["set", "expert", "--project", str(tmp_path)])
    assert r.exit_code != 0
