"""K1 `startd8 kickoff check` — conformance pre-flight CLI."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from startd8.cli_kickoff import kickoff_app

app = typer.Typer()
app.add_typer(kickoff_app, name="kickoff")

runner = CliRunner()

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "manifest_extraction" / "kickoff.md"

CONFORMANT_DOC = """\
## Entities

### Profile
| Field | Type | Required | Notes |
|-------|------|----------|-------|
| name | text | yes | |

## Pages

| Page | Purpose | Content file |
|------|---------|--------------|
| Home | Landing | home.md |
"""


def test_check_renders_worklist_and_exits_zero_by_default(tmp_path: Path) -> None:
    result = runner.invoke(app, ["kickoff", "check", str(FIXTURE)])
    assert result.exit_code == 0, result.output
    assert "Co-work worklist" in result.output          # the fixture's deliberate non-conformances
    assert "generator-gap" in result.output             # counted separately, not in the worklist
    assert "one-field-per-row" in result.output


def test_strict_gates_on_conformance_not_generator_gaps(tmp_path: Path) -> None:
    # Fixture doc: has conformance failures ⇒ strict exits 1.
    result = runner.invoke(app, ["kickoff", "check", str(FIXTURE), "--strict"])
    assert result.exit_code == 1
    # Conformant doc: only gaps/defaults remain ⇒ strict exits 0.
    doc = tmp_path / "ok.md"
    doc.write_text(CONFORMANT_DOC, encoding="utf-8")
    result = runner.invoke(app, ["kickoff", "check", str(doc), "--strict"])
    assert result.exit_code == 0, result.output
    assert "docs conform" in result.output


def test_json_output_is_the_extraction_report(tmp_path: Path) -> None:
    result = runner.invoke(app, ["kickoff", "check", str(FIXTURE), "--json"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["grammar_version"].startswith("authoring-contract-")
    assert body["counts"]["extracted"] > 0
    assert "kickoff.md" in body["source_docs"]


def test_project_enables_diff_and_agreement(tmp_path: Path) -> None:
    project = tmp_path / "proj"
    (project / "prisma").mkdir(parents=True)
    (project / "prisma" / "schema.prisma").write_text(
        "model Profile {\n  id String @id\n  name String\n}\n", encoding="utf-8"
    )
    (project / "inputs").mkdir()
    (project / "inputs" / "build-preferences.yaml").write_text(
        'budgets:\n  per_pipeline_run: "$5.00"\n', encoding="utf-8"
    )
    doc = tmp_path / "doc.md"
    doc.write_text(
        CONFORMANT_DOC
        + "\n## Scaffold & runtime\n\n| Setting | Value | Plain meaning |\n"
        "|---|---|---|\n| env keys | COST_BUDGET_USD (default 10.00) | |\n",
        encoding="utf-8",
    )
    result = runner.invoke(
        app, ["kickoff", "check", str(doc), "--project", str(project), "--json"]
    )
    body = json.loads(result.stdout)
    reasons = [r.get("reason", "") for r in body["records"]]
    assert any("two-surfaces-disagree" in x for x in reasons)
    assert body["contract_diff"] == []  # Profile agrees with the live contract


def test_unreadable_doc_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["kickoff", "check", str(tmp_path / "missing.md")])
    assert result.exit_code == 2
