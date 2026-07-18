"""M-DL5 — the descriptive layer (FR-DL): manifest coverage, determinism, and the --describe render.

Guards three properties of `wireframe/descriptive.yaml` + `describe.py`:
  1. Coverage — every live section key has an authored record, and the manifest parses (FR-DL-9).
  2. Determinism — `describe(section, plan)` / `describe_summary(plan)` are pure functions of
     (authored record × live plan): same inputs → byte-identical output, no LLM (FR-DL-8).
  3. Render — `--describe` surfaces the WHAT/WHY/DO/NEXT per section and routes the aggregate
     summary's WHY/DO through the header (FR-DL-3, FR-DL-12); default output is unchanged.
"""

from __future__ import annotations

from pathlib import Path

import typer
import yaml
from typer.testing import CliRunner

from startd8.cli_wireframe import wireframe
from startd8.wireframe import build_wireframe_plan, load_assembly_inputs
from startd8.wireframe.describe import (
    all_keys,
    describe,
    describe_summary,
)

app = typer.Typer()
app.command()(wireframe)
runner = CliRunner()


def _plan(root: Path):
    return build_wireframe_plan(load_assembly_inputs(project_root=root), authoring=True)


# 1 — coverage (FR-DL-9) ------------------------------------------------------------------------

def test_manifest_parses_and_records_carry_the_full_grammar() -> None:
    """descriptive.yaml is valid YAML and every non-summary record has what/why/do/next."""
    from startd8.wireframe import describe as _mod

    data = yaml.safe_load(Path(_mod.__file__).with_name("descriptive.yaml").read_text("utf-8"))
    recs = data["records"]
    assert "summary" in recs, "FR-DL-12 aggregate summary record must exist"
    for key, rec in recs.items():
        assert {"what", "why", "do"} <= rec.keys(), f"{key}: missing core clause"
        if key != "summary":
            assert "next" in rec, f"{key}: missing FR-DL-3 next drill hint"


def test_every_live_section_key_is_authored(golden_root: Path) -> None:
    """No live section renders unnarrated under --describe (FR-DL-9 coverage surface)."""
    plan = _plan(golden_root)
    authored = set(all_keys())
    for section in plan.sections:
        assert section.key in authored, f"section {section.key!r} has no descriptive record"


# 2 — determinism (FR-DL-8) ---------------------------------------------------------------------

def test_describe_is_deterministic(golden_root: Path) -> None:
    plan = _plan(golden_root)
    for section in plan.sections:
        first = describe(section, plan)
        second = describe(section, plan)
        assert first == second, f"describe({section.key}) not deterministic"
        if first is not None:
            assert first["key"] == section.key  # provenance by construction (FR-DL-9)
            assert first["next"], f"{section.key}: next hint filled"


def test_describe_summary_is_deterministic(golden_root: Path) -> None:
    plan = _plan(golden_root)
    s1 = describe_summary(plan)
    s2 = describe_summary(plan)
    assert s1 == s2 and s1 is not None
    assert s1["why"] and s1["do"]  # FR-DL-12: the header's meaning, authored


# 3 — render (FR-DL-3 / FR-DL-12) ---------------------------------------------------------------

def test_describe_flag_surfaces_section_and_summary_narration(golden_root: Path) -> None:
    out = runner.invoke(
        app, ["--project", str(golden_root), "--describe", "--no-write"]
    ).output
    assert "WHAT:" in out and "WHY:" in out and "DO:" in out
    assert "NEXT:" in out  # FR-DL-3 drill hints render per section


def test_default_output_omits_narration(golden_root: Path) -> None:
    """--describe is opt-in: the default tree carries no WHAT/NEXT narration lines."""
    out = runner.invoke(app, ["--project", str(golden_root), "--no-write"]).output
    assert "WHAT:" not in out
    assert "NEXT:" not in out
