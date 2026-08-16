"""Route repair diagnostics through the SARIF sink (consume-ladder rung 1, producer #4).

Module: src/startd8/repair/sarif.py — proves the repair Diagnostic family is a drop-in for
coverage_map.render_sarif_from_findings (rule-id ← category; region iff the diagnostic has a line;
severity ← the diagnostic's own, else degrades to warning).
"""

from __future__ import annotations

from startd8.coverage_map.findings_sarif import SARIF_SCHEMA_URI
from startd8.repair.models import (
    Diagnostic,
    ImportDiagnostic,
    SemanticDiagnostic,
    SyntaxDiagnostic,
)
from startd8.repair.sarif import render_repair_sarif


def _run0(doc):
    return doc["runs"][0]


def test_syntax_diagnostic_has_region_and_degrades_severity():
    doc = render_repair_sarif([SyntaxDiagnostic(category="syntax", file="a.py", message="bad", line=5)])
    assert doc["$schema"] == SARIF_SCHEMA_URI and doc["version"] == "2.1.0"
    run = _run0(doc)
    assert run["tool"]["driver"]["name"] == "repair"
    res = run["results"][0]
    assert res["ruleId"] == "syntax"
    assert res["level"] == "warning"          # base/Syntax carry no severity field → degrade
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "a.py"
    assert loc["region"]["startLine"] == 5


def test_import_diagnostic_is_file_level_no_region():
    run = _run0(render_repair_sarif([ImportDiagnostic(category="import", file="b.py", message="no mod")]))
    loc = run["results"][0]["locations"][0]["physicalLocation"]
    assert "region" not in loc                # ImportDiagnostic has no line
    assert run["results"][0]["ruleId"] == "import"


def test_semantic_diagnostic_carries_its_own_severity():
    doc = render_repair_sarif([
        SemanticDiagnostic(category="semantic", file="c.py", message="unresolved", severity="error", line=9)
    ])
    res = _run0(doc)["results"][0]
    assert res["level"] == "error"            # SemanticDiagnostic has a severity field
    assert res["locations"][0]["physicalLocation"]["region"]["startLine"] == 9


def test_distinct_categories_become_distinct_rules():
    diags = [
        SyntaxDiagnostic(category="syntax", file="a.py", message="x", line=1),
        Diagnostic(category="test", file="b.py", message="y"),
        ImportDiagnostic(category="import", file="c.py", message="z"),
    ]
    rules = {r["id"] for r in _run0(render_repair_sarif(diags))["tool"]["driver"]["rules"]}
    assert rules == {"syntax", "test", "import"}


def test_diagnostic_without_file_is_skipped_and_counted():
    keep = SyntaxDiagnostic(category="syntax", file="a.py", message="x", line=1)
    nofile = Diagnostic(category="test", file="", message="y")
    run = _run0(render_repair_sarif([keep, nofile]))
    assert len(run["results"]) == 1
    assert run["invocations"][0]["properties"]["skipped"] == 1
