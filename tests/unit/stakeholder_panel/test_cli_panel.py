# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""panel CLI tests (FR-8/FR-19). `list` is $0; `ask` uses a monkeypatched agent (no keys)."""

from __future__ import annotations

from typer.testing import CliRunner

from startd8.cli_panel import panel_app

from .conftest import ScriptedAgent

runner = CliRunner()

_ROSTER = (
    "domain: stakeholders\n"
    "personas:\n"
    "  - role_id: product-owner\n"
    "    display_name: Product Owner\n"
    "    goals: ['ship the MVP']\n"
    "  - role_id: end-user\n"
    "    display_name: End User\n"
    "    known_positions: ['wants one-click checkout']\n"
)


def _project(tmp_path):
    inputs = tmp_path / "docs" / "kickoff" / "inputs"
    inputs.mkdir(parents=True)
    (inputs / "stakeholders.yaml").write_text(_ROSTER, encoding="utf-8")
    return tmp_path


def test_list_is_readonly_and_lists_personas(tmp_path):
    result = runner.invoke(panel_app, ["list", str(_project(tmp_path))])
    assert result.exit_code == 0
    assert "product-owner" in result.stdout
    assert "end-user" in result.stdout


def test_list_json(tmp_path):
    result = runner.invoke(panel_app, ["list", str(_project(tmp_path)), "--json"])
    assert result.exit_code == 0
    assert '"domain": "stakeholders"' in result.stdout


def test_list_missing_roster_exits_2(tmp_path):
    result = runner.invoke(panel_app, ["list", str(tmp_path)])
    assert result.exit_code == 2


def test_ask_renders_synthetic_banner(tmp_path, monkeypatch):
    import startd8.utils.agent_resolution as ar

    monkeypatch.setattr(
        ar,
        "resolve_agent_spec",
        lambda spec, **kw: ScriptedAgent(
            name=kw.get("name", "p"), reply="We ship in Q3.\nGROUNDING: grounded"
        ),
    )
    result = runner.invoke(
        panel_app,
        [
            "ask",
            "--role",
            "product-owner",
            "--project",
            str(_project(tmp_path)),
            "When do we ship?",
        ],
    )
    assert result.exit_code == 0
    assert "We ship in Q3." in result.stdout
    assert "SYNTHETIC, UNRATIFIED" in result.stdout  # FR-19 banner


def test_ask_unknown_role_exits_2(tmp_path, monkeypatch):
    import startd8.utils.agent_resolution as ar

    monkeypatch.setattr(ar, "resolve_agent_spec", lambda spec, **kw: ScriptedAgent())
    result = runner.invoke(
        panel_app,
        ["ask", "--role", "cfo", "--project", str(_project(tmp_path)), "Budget?"],
    )
    assert result.exit_code == 2
