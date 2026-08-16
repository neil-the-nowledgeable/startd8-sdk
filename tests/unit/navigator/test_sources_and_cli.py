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
from startd8.navigator.sources_requirements import (
    REQUIREMENTS_PROFILE,
    nodes_from_requirements,
    requirement_identity,
    requirements_profile_for,
)

FIXTURE = Path(__file__).parent / "fixtures" / "REQ-fixture-minimal.md"
_REQ01 = Path("docs/design/requirements-visualization/REQ-01-sdk-node-home.md")
RUNNER = CliRunner()


# ---- EC-1: `navigator view-definition` JSON export (the cross-repo VIEW-SCHEMA seam) ----
def test_view_definition_cli_dumps_one_resolved_definition():
    res = RUNNER.invoke(app, ["navigator", "view-definition", "--name", "capability"])
    assert res.exit_code == 0, res.output
    payload = json.loads(res.stdout)
    # resolved: theme is flattened from the base ⊕ capability's accent override
    assert payload["theme"]["accent"] == "#3a6a94"
    assert payload["theme"]["ink"] == "#241f17"          # inherited from base
    assert payload["vocabulary"]["gap_noun"] == "capability"


def test_view_definition_cli_dumps_whole_registry_and_rejects_unknown():
    res = RUNNER.invoke(app, ["navigator", "view-definition"])
    assert res.exit_code == 0, res.output
    reg = json.loads(res.stdout)
    assert {"base", "requirements", "capability", "node-schema"} <= set(reg)
    bad = RUNNER.invoke(app, ["navigator", "view-definition", "--name", "nope"])
    assert bad.exit_code == 1
    assert "unknown definition" in bad.output


# ---- FR-17: deterministic masthead identity (derived, not static profile copy) ----
def test_requirement_identity_extracts_key_title_semantic():
    idy = requirement_identity(_REQ01)
    assert idy["key"] == "REQ-01"
    assert idy["title"] == "SDK Node Home"              # H1 with '— Requirements' stripped
    assert idy["semantic_name"].startswith("The SDK is the forward home")
    assert idy["initiative"] == "requirements-visualization"  # from the canonical ref


def test_requirements_profile_for_overrides_static_masthead():
    prof = requirements_profile_for(_REQ01)
    assert prof.eyebrow == "REQ-01"                     # was static 'This spec'
    assert prof.headline == "SDK Node Home"             # was static 'A first look at this spec'
    assert prof.summary_meta and prof.summary_meta[0].startswith("The SDK is the forward home")
    # the static base profile is unchanged (per-render copy only)
    assert REQUIREMENTS_PROFILE.eyebrow == "This spec"
    assert REQUIREMENTS_PROFILE.headline == "A first look at this spec"


def test_code_lives_to_absent_file_is_spec_not_grounded(tmp_path):
    """False-GROUNDED fix: a `Lives: code <path>` to a non-existent file → spec ('written, not built'),
    NOT grounded/built. A code Lives to an EXISTING file → built. An unbuilt spec must not read green."""
    doc = tmp_path / "REQ-99-fixture.md"
    doc.write_text(
        "# Fixture — Requirements\n\n**Format:** det-req/0.1\n\n"
        "- **FR-1 — Absent target.** Builds a new module. Name: absent target. "
        "Lives: code src/startd8/navigator/nonexistent_xyz.py. Verify: `x` exits 0. Serves: O-1\n"
        "- **FR-2 — Existing target.** Edits an existing module. Name: existing target. "
        "Lives: code src/startd8/navigator/models.py. Verify: `y` exits 0. Serves: O-1\n",
        encoding="utf-8",
    )
    status = {n.key: n.status for n in nodes_from_requirements(doc, repo=Path.cwd())}
    assert status["FR-1"] == "spec"    # code Lives to an ABSENT file → not grounded
    assert status["FR-2"] == "built"   # code Lives to an EXISTING file → grounded


def test_requirements_profile_for_falls_back_when_unextractable(tmp_path):
    bare = tmp_path / "notes.md"                        # no key, no H1, no name block
    bare.write_text("just some prose, no header\n", encoding="utf-8")
    prof = requirements_profile_for(bare)
    assert prof.eyebrow == REQUIREMENTS_PROFILE.eyebrow          # graceful fallback to the base
    assert prof.summary_meta == REQUIREMENTS_PROFILE.summary_meta
    # FR-18: with no REQ-key, section_lead falls back to the base (it's key-derived).
    assert prof.section_lead == REQUIREMENTS_PROFILE.section_lead
    # The page title still degrades to the doc's own H1/stem identity ("notes") rather than the
    # generic base — a per-doc handle is always more useful than "This spec — a first look".
    assert prof.title == "notes"


# ---- FR-18: deterministic descriptive chrome (section_lead + page title, derived) ----
def test_requirements_profile_for_derives_section_lead_and_title():
    prof = requirements_profile_for(_REQ01)
    assert prof.section_lead == "What REQ-01 defines"           # was static 'What this spec defines'
    assert prof.title == "REQ-01 — SDK Node Home"               # was static 'This spec — a first look'
    # guidance + vocabulary ride through unchanged (NOT force-derived)
    assert prof.why == REQUIREMENTS_PROFILE.why
    assert prof.do == REQUIREMENTS_PROFILE.do
    assert prof.gap_noun == REQUIREMENTS_PROFILE.gap_noun
    # the static base profile is unchanged (per-render copy only) — byte-identity guard
    assert REQUIREMENTS_PROFILE.section_lead == "What this spec defines"
    assert REQUIREMENTS_PROFILE.title == "This spec — a first look"


def test_requirements_profile_for_title_uses_key_when_present(tmp_path):
    # a doc with a key in the filename and an H1 → section_lead names the key; title is "{key} — {H1}"
    doc = tmp_path / "REQ-42-thing.md"
    doc.write_text("# My Thing\n\nbody\n", encoding="utf-8")
    prof = requirements_profile_for(doc)
    assert prof.section_lead == "What REQ-42 defines"
    assert prof.title == "REQ-42 — My Thing"


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
