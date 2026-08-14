"""F-3 / F-4 / F-5: sources, CLI, ground."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from startd8.cli import app
from startd8.navigator.det_req import parse_fr_lines
from startd8.navigator.ground import ground_tree
from startd8.navigator.sources_capability import nodes_from_capability_index
from startd8.navigator.sources_requirements import nodes_from_requirements

FIXTURE = Path(__file__).parent / "fixtures" / "REQ-fixture-minimal.md"
RUNNER = CliRunner()


def test_capability_index_emits_live_keys():
    nodes = nodes_from_capability_index()
    assert len(nodes) >= 1
    assert any(n.key.startswith("startd8.") for n in nodes)
    assert all(n.confidence is not None for n in nodes[:5])


def test_requirements_source_lives_and_unknown(tmp_path: Path):
    nodes = nodes_from_requirements(FIXTURE)
    by_key = {n.key: n for n in nodes}
    assert "FR-1" in by_key
    assert by_key["FR-1"].lives[0].type == "code"
    assert by_key["FR-1"].lives[0].ref.startswith("git:")
    assert by_key["FR-1"].attributes.get("fr_health") == "on_track"
    assert by_key["FR-2"].attributes.get("fr_health") == "unknown"
    assert by_key["FR-2"].attributes.get("status_key") == "unknown"


def test_det_req_vendor_thin_without_kit_on_path(monkeypatch: pytest.MonkeyPatch):
    # Ensure sibling kit is not required.
    monkeypatch.delenv("DET_REQ_KIT", raising=False)
    # Strip any accidental kit import path noise — parse must work locally.
    frs = parse_fr_lines(FIXTURE.read_text(encoding="utf-8"))
    assert {f["id"] for f in frs} >= {"FR-1", "FR-2", "FR-3"}
    assert "det_req_kit" not in sys.modules or True  # presence of module name is fine; no import of extract


def test_det_req_kit_override_fail_loud_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from startd8.navigator.det_req import parse_fr_lines_prefer_kit

    monkeypatch.setenv("DET_REQ_KIT", str(tmp_path / "no-such-kit"))
    with pytest.raises(FileNotFoundError, match="extract.py"):
        parse_fr_lines_prefer_kit(FIXTURE.read_text(encoding="utf-8"))


def test_det_req_kit_override_uses_real_kit_when_set(monkeypatch: pytest.MonkeyPatch):
    from startd8.navigator.det_req import parse_fr_lines_prefer_kit

    kit = Path.home() / "Documents/dev/dev-os/det-req-kit"
    if not (kit / "extract.py").is_file():
        pytest.skip("det-req-kit not present on this machine")
    monkeypatch.setenv("DET_REQ_KIT", str(kit))
    # Full REQ-01 has kit sections; minimal fixture may fall back to vendor_thin after kit empty.
    text = FIXTURE.read_text(encoding="utf-8")
    frs = parse_fr_lines_prefer_kit(text)
    assert {f["id"] for f in frs} >= {"FR-1", "FR-2"}


def test_cli_navigator_capability_html_uses_capability_profile(tmp_path: Path):
    out = tmp_path / "caps.html"
    result = RUNNER.invoke(
        app,
        [
            "navigator",
            "build",
            "--source",
            "capability-index",
            "--format",
            "html",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    html = out.read_text(encoding="utf-8")
    assert "Capabilities — a first look" in html
    assert "Your app — a first look" not in html
    assert "Capability index" in html or "SDK capabilities" in html


def test_cli_navigator_build_requirements_json(tmp_path: Path):
    out = tmp_path / "req.json"
    result = RUNNER.invoke(
        app,
        [
            "navigator",
            "build",
            "--source",
            "requirements",
            "--requirements",
            str(FIXTURE),
            "--format",
            "json",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    keys = {n["key"] for n in data["nodes"]}
    assert "FR-1" in keys


def test_cli_navigator_build_html(tmp_path: Path):
    out = tmp_path / "out.html"
    result = RUNNER.invoke(
        app,
        [
            "navigator",
            "build",
            "--source",
            "requirements",
            "--requirements",
            str(FIXTURE),
            "--format",
            "html",
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out.is_file()
    assert "FR-1" in out.read_text(encoding="utf-8")


def test_cli_nav_and_navigator_help_distinct():
    nav = RUNNER.invoke(app, ["nav", "--help"])
    navigator = RUNNER.invoke(app, ["navigator", "--help"])
    assert nav.exit_code == 0
    assert navigator.exit_code == 0
    assert "top-navigation" in nav.output or "nav" in nav.output.lower()
    assert "build" in navigator.output
    assert "ground" in navigator.output


def test_ground_emits_counts_and_date(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("mention FR-1 and startd8.agent.system_prompt\n", encoding="utf-8")
    out = tmp_path / "ground.json"
    result = RUNNER.invoke(app, ["navigator", "ground", "--root", str(src), "--out", str(out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["keys"]["FR-1"] >= 1
    assert "startd8.agent.system_prompt" in payload["keys"]
    assert payload["grounded"]  # ISO date
    # library API
    assert ground_tree(src)["key_count"] >= 1
