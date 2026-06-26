"""FR-PC-*: config-file provider/model selection for the agentic Concierge.

Covers the `resolve_concierge_agent_spec` precedence (FR-PC-4), malformed-skip (FR-PC-9),
angle-bracket-placeholder-as-unset (FR-PC-10), and that the catalog default stays a
`model_catalog` reference (FR-PC-6), plus a build-preferences round-trip regression.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.kickoff_experience.concierge_agent import resolve_concierge_agent_spec
from startd8.kickoff_inputs import parse_build_preferences
from startd8.model_catalog import Models


def _write_build_prefs(project: Path, concierge_agent: str | None) -> None:
    inputs = project / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    body = "domain: build-preferences\n"
    if concierge_agent is not None:
        body += f"concierge_agent: {concierge_agent}\n"
    (inputs / "build-preferences.yaml").write_text(body, encoding="utf-8")


def test_default_layer_is_catalog_reference(tmp_path):
    """No flag, no project config, no global config → catalog default (FR-PC-6, not a literal)."""
    spec, source = resolve_concierge_agent_spec(tmp_path, None)
    assert source == "default"
    assert spec == Models.CLAUDE_SONNET_LATEST


def test_flag_wins_over_everything(tmp_path):
    """Explicit --agent flag beats project config (FR-PC-4 top of precedence)."""
    _write_build_prefs(tmp_path, "gemini:gemini-2.5-pro")
    spec, source = resolve_concierge_agent_spec(tmp_path, "openai:gpt-5.5")
    assert (spec, source) == ("openai:gpt-5.5", "flag")


def test_project_config_used_when_no_flag(tmp_path):
    """build-preferences.yaml concierge_agent is read live (FR-PC-2/OQ-2)."""
    _write_build_prefs(tmp_path, "gemini:gemini-2.5-pro")
    spec, source = resolve_concierge_agent_spec(tmp_path, None)
    assert (spec, source) == ("gemini:gemini-2.5-pro", "project")


def test_global_config_layer(tmp_path, monkeypatch):
    """Global ~/.startd8 preference applies when no flag and no project value (FR-PC-3)."""
    import startd8.kickoff_experience.concierge_agent as mod

    monkeypatch.setattr(mod, "_project_concierge_agent", lambda _root: None)

    class _FakeMgr:
        def get_preference(self, key):
            return "ollama:llama3" if key == "concierge_agent" else None

    monkeypatch.setattr(mod, "_global_concierge_agent",
                        lambda: mod._usable(_FakeMgr().get_preference("concierge_agent")))
    spec, source = resolve_concierge_agent_spec(tmp_path, None)
    assert (spec, source) == ("ollama:llama3", "global")


def test_malformed_project_config_skips_not_crashes(tmp_path):
    """A malformed build-preferences.yaml degrades to the next layer, never raises (FR-PC-9)."""
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    # unknown top-level key → parse_build_preferences loud-fails; resolver must swallow it
    (inputs / "build-preferences.yaml").write_text(
        "domain: build-preferences\nbogus_key: 1\n", encoding="utf-8")
    spec, source = resolve_concierge_agent_spec(tmp_path, None)
    assert source == "default"
    assert spec == Models.CLAUDE_SONNET_LATEST


def test_angle_bracket_placeholder_is_unset(tmp_path):
    """A `<provider:model>` template placeholder is treated as unset (FR-PC-10)."""
    _write_build_prefs(tmp_path, "<provider:model>")
    spec, source = resolve_concierge_agent_spec(tmp_path, None)
    assert source == "default"


def test_empty_flag_falls_through(tmp_path):
    """An empty-string flag is not an explicit choice — fall through to project config."""
    _write_build_prefs(tmp_path, "mistral:mistral-large-latest")
    spec, source = resolve_concierge_agent_spec(tmp_path, "  ")
    assert (spec, source) == ("mistral:mistral-large-latest", "project")


def test_build_preferences_round_trips_concierge_agent():
    """The new key parses and survives (FR-PC-2 grammar; regression for the closed allowlist)."""
    manifest = parse_build_preferences(
        "domain: build-preferences\nconcierge_agent: anthropic:claude-opus-4-8\n")
    assert manifest.concierge_agent == "anthropic:claude-opus-4-8"


def test_build_preferences_rejects_non_string_concierge_agent():
    with pytest.raises(ValueError):
        parse_build_preferences("domain: build-preferences\nconcierge_agent: 42\n")
