"""K1 `startd8 kickoff check` — conformance pre-flight CLI.

K2 (the §2.7 build-preferences env-keys agreement check) is deferred; those assertions are
not exercised here.
"""

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


def test_check_renders_and_exits_zero_by_default() -> None:
    result = runner.invoke(app, ["kickoff", "check", str(FIXTURE)])
    assert result.exit_code == 0, result.output
    assert "Conformance:" in result.output
    # generator-gaps are counted separately from the author worklist
    assert "generator-gap" in result.output


def test_strict_gates_on_conformance_failures() -> None:
    """The fixture has author-actionable non-conformances ⇒ --strict exits 1."""
    result = runner.invoke(app, ["kickoff", "check", str(FIXTURE), "--strict"])
    assert result.exit_code == 1, result.output


def test_strict_passes_on_conformant_doc(tmp_path: Path) -> None:
    doc = tmp_path / "ok.md"
    doc.write_text(CONFORMANT_DOC, encoding="utf-8")
    result = runner.invoke(app, ["kickoff", "check", str(doc), "--strict"])
    assert result.exit_code == 0, result.output
    assert "docs conform" in result.output


def test_json_output_is_the_extraction_report() -> None:
    result = runner.invoke(app, ["kickoff", "check", str(FIXTURE), "--json"])
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["grammar_version"].startswith("authoring-contract-")
    assert body["counts"]["extracted"] > 0
    assert "kickoff.md" in body["source_docs"]


def test_project_enables_contract_diff(tmp_path: Path) -> None:
    """--project surfaces the contract DIFF; an agreeing schema yields a clean diff (K1 scope)."""
    project = tmp_path / "proj"
    (project / "prisma").mkdir(parents=True)
    (project / "prisma" / "schema.prisma").write_text(
        "model Profile {\n  id String @id\n  name String\n}\n", encoding="utf-8"
    )
    doc = tmp_path / "doc.md"
    doc.write_text(CONFORMANT_DOC, encoding="utf-8")
    result = runner.invoke(
        app, ["kickoff", "check", str(doc), "--project", str(project), "--json"]
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.stdout)
    assert body["contract_diff"] == []  # Profile agrees with the live contract


def test_unreadable_doc_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["kickoff", "check", str(tmp_path / "missing.md")])
    assert result.exit_code == 2


# FR-F1/F8: a truncated in-table `choice of:` is advisory — visible + warn by default, fails --strict.
_TRUNCATED_CHOICE_DOC = (
    "## Entities\n\n"
    "### Assignment\n"
    "| Field | Type | Required | Notes |\n"
    "|-------|------|----------|-------|\n"
    "| status | choice of: not_started|in_progress|submitted | yes | |\n"
)


def test_choice_of_advisory_warns_but_exits_zero_by_default(tmp_path: Path) -> None:
    doc = tmp_path / "trunc.md"
    doc.write_text(_TRUNCATED_CHOICE_DOC, encoding="utf-8")
    result = runner.invoke(app, ["kickoff", "check", str(doc)])
    assert result.exit_code == 0, result.output
    assert "advisory:" in result.output
    assert "choice-of-single-value" in result.output


def test_choice_of_advisory_promotes_to_failure_under_strict(tmp_path: Path) -> None:
    """The false-green bug: on `main` this doc passed --strict clean (enum silently truncated). The
    advisory must now promote it to a conformance failure."""
    doc = tmp_path / "trunc.md"
    doc.write_text(_TRUNCATED_CHOICE_DOC, encoding="utf-8")
    result = runner.invoke(app, ["kickoff", "check", str(doc), "--strict"])
    assert result.exit_code == 1, result.output
