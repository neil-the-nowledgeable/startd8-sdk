"""Route cross_file Finding through the SARIF sink (consume-ladder rung 1, producer #3).

Module: src/startd8/validators/cross_file_sarif.py — proves Finding is a file-level drop-in
for coverage_map.render_sarif_from_findings (rule-id ← check_id, file ← source_file, no region).
"""

from __future__ import annotations

from startd8.coverage_map.findings_sarif import SARIF_SCHEMA_URI
from startd8.validators.cross_file_sarif import render_crossfile_sarif
from startd8.validators.cross_file_verifier import Finding


def _finding(check_id="zod_symmetry", source_file="z.ts", severity="error", message="drift"):
    return Finding(check_id=check_id, kind=check_id, source_file=source_file, locus="email",
                   severity=severity, scope="cross_file", message=message, remediation="fix it")


def _run0(doc):
    return doc["runs"][0]


def test_finding_renders_valid_file_level_sarif():
    doc = render_crossfile_sarif([_finding(message="Zod string vs Prisma Int")], corpus="z.ts")
    assert doc["$schema"] == SARIF_SCHEMA_URI and doc["version"] == "2.1.0"
    run = _run0(doc)
    assert run["tool"]["driver"]["name"] == "cross-file"
    res = run["results"][0]
    assert res["ruleId"] == "zod_symmetry"          # rule-id ← check_id
    assert res["level"] == "error"
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "z.ts"
    assert "region" not in loc                      # no line — file-level (locus ≠ line)
    rule = next(r for r in run["tool"]["driver"]["rules"] if r["id"] == "zod_symmetry")
    assert rule["helpUri"].endswith("#zod_symmetry")


def test_distinct_check_ids_become_distinct_rules():
    findings = [_finding(check_id=c) for c in ("zod_symmetry", "unresolvable_import", "prisma_usage")]
    rules = {r["id"] for r in _run0(render_crossfile_sarif(findings))["tool"]["driver"]["rules"]}
    assert rules == {"zod_symmetry", "unresolvable_import", "prisma_usage"}


def test_severity_is_the_findings_own():
    # tsconfig_paths defaults to 'warning' in the catalog; a finding may carry 'error' — finding wins.
    doc = render_crossfile_sarif([_finding(check_id="tsconfig_paths", severity="error")])
    assert _run0(doc)["results"][0]["level"] == "error"


def test_finding_with_no_source_file_is_skipped_and_counted():
    run = _run0(render_crossfile_sarif([_finding(), _finding(source_file="")]))
    assert len(run["results"]) == 1
    assert run["invocations"][0]["properties"]["skipped"] == 1
