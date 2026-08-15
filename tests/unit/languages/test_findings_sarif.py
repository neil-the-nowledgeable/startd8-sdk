"""Generic finding → SARIF 2.1.0 renderer.

Module: src/startd8/coverage_map/findings_sarif.py
Design: docs/design/SARIF-FINDINGS-REUSABILITY.md

Proves the renderer duck-types the SDK's real finding shapes (SemanticIssue and an enum-keyed
SecurityFinding-style object) and emits a valid 2.1.0 document.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Optional

import pytest

from startd8.coverage_map import render_sarif_from_findings
from startd8.coverage_map.findings_sarif import SARIF_SCHEMA_URI
from startd8.validators.semantic_checks import SemanticIssue, run_semantic_checks


def _run(findings, **kw):
    kw.setdefault("tool_name", "startd8-semantic")
    return render_sarif_from_findings(findings, **kw)


def _run0(doc):
    return doc["runs"][0]


# ---------------------------------------------------------------------------
# Shape / validity
# ---------------------------------------------------------------------------

def test_top_level_shape_is_sarif_210():
    doc = _run([SemanticIssue("bare_except_pass", "warning", "swallows", 3, "a.py")])
    assert doc["$schema"] == SARIF_SCHEMA_URI
    assert doc["version"] == "2.1.0"
    assert isinstance(doc["runs"], list) and len(doc["runs"]) == 1
    driver = _run0(doc)["tool"]["driver"]
    assert driver["name"] == "startd8-semantic"
    assert "rules" in driver
    assert _run0(doc)["invocations"][0]["executionSuccessful"] is True


def test_consumes_semantic_issue_directly():
    issues = [
        SemanticIssue("bare_except_pass", "warning", "swallows all", 12, "svc/a.py"),
        SemanticIssue("fake_work_stub", "error", "canned data", 40, "svc/b.py"),
    ]
    run = _run0(_run(issues))
    assert len(run["results"]) == 2
    r0 = run["results"][0]
    assert r0["ruleId"] == "bare_except_pass"
    assert r0["level"] == "warning"
    assert r0["message"]["text"] == "swallows all"
    loc = r0["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "svc/a.py"
    assert loc["region"]["startLine"] == 12
    # error severity → error level
    assert run["results"][1]["level"] == "error"


def test_rules_deduped_and_first_seen_order():
    issues = [
        SemanticIssue("dup_check", "warning", "m1", 1, "a.py"),
        SemanticIssue("other_check", "error", "m2", 2, "a.py"),
        SemanticIssue("dup_check", "warning", "m3", 3, "b.py"),
    ]
    rules = _run0(_run(issues))["tool"]["driver"]["rules"]
    assert [r["id"] for r in rules] == ["dup_check", "other_check"]
    assert all(r["name"] == r["id"] for r in rules)


@pytest.mark.parametrize(
    "severity,expected",
    [
        ("error", "error"), ("ERROR", "error"), ("critical", "error"), ("high", "error"),
        ("warning", "warning"), ("warn", "warning"), ("medium", "warning"),
        ("info", "note"), ("low", "note"),
        ("weird-unknown", "warning"), ("", "warning"), (None, "warning"),
    ],
)
def test_severity_maps_to_sarif_level(severity, expected):
    doc = _run([SemanticIssue("c", severity, "m", 1, "a.py")])
    assert _run0(doc)["results"][0]["level"] == expected


def test_missing_line_omits_region():
    doc = _run([SemanticIssue("c", "warning", "m", None, "a.py")])
    loc = _run0(doc)["results"][0]["locations"][0]["physicalLocation"]
    assert "region" not in loc
    assert loc["artifactLocation"]["uri"] == "a.py"


def test_findings_without_ruleid_or_file_are_skipped_and_counted():
    findings = [
        SemanticIssue("good", "warning", "m", 1, "a.py"),   # kept
        SemanticIssue("", "warning", "no rule id", 2, "b.py"),  # skipped: no rule id
        SemanticIssue("nofile", "warning", "m", 3, None),   # skipped: no file
    ]
    run = _run0(_run(findings))
    assert len(run["results"]) == 1
    assert run["invocations"][0]["properties"]["skipped"] == 2


# ---------------------------------------------------------------------------
# Duck-typing: SecurityFinding-style (enum check_type + file_path) and dicts
# ---------------------------------------------------------------------------

class _CheckType(enum.Enum):
    INJECTION = "INJECTION"
    CREDENTIAL_LEAKAGE = "CREDENTIAL_LEAKAGE"


@dataclass
class _SecurityFinding:
    check_type: _CheckType
    severity: str
    message: str
    line: Optional[int]
    file_path: Optional[str]


def test_consumes_check_type_enum_finding():
    findings = [_SecurityFinding(_CheckType.INJECTION, "error", "concat SQL", 7, "q.py")]
    run = _run0(render_sarif_from_findings(findings, tool_name="startd8-security"))
    assert run["results"][0]["ruleId"] == "INJECTION"  # enum.value, stable
    assert run["results"][0]["level"] == "error"
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["INJECTION"]


def test_consumes_plain_dict_findings():
    findings = [
        {"check_id": "zod_symmetry", "severity": "error", "message": "drift", "source_file": "z.ts"},
    ]
    run = _run0(render_sarif_from_findings(findings, tool_name="startd8-crossfile"))
    r0 = run["results"][0]
    assert r0["ruleId"] == "zod_symmetry"
    assert r0["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "z.ts"


def test_corpus_and_rule_help_uri_recorded():
    doc = _run(
        [SemanticIssue("c", "warning", "m", 1, "a.py")],
        corpus="/tmp/repo",
        rule_help_uris={"c": "https://example.test/c"},
    )
    run = _run0(doc)
    assert run["invocations"][0]["properties"]["corpus"] == "/tmp/repo"
    assert run["tool"]["driver"]["rules"][0]["helpUri"] == "https://example.test/c"


def test_empty_findings_is_valid_empty_run():
    doc = _run([])
    run = _run0(doc)
    assert run["results"] == []
    assert run["tool"]["driver"]["rules"] == []
    assert "properties" not in run["invocations"][0]  # no corpus, nothing skipped


# ---------------------------------------------------------------------------
# End-to-end: real validator output → SARIF (the reuse slice)
# ---------------------------------------------------------------------------

def test_end_to_end_python_semantic_validator_to_sarif():
    src = (
        "def handler():\n"
        "    try:\n"
        "        risky()\n"
        "    except:\n"
        "        pass\n"
    )
    issues = run_semantic_checks(src, file_path="svc/handler.py")
    assert issues, "expected the bare-except check to fire"
    run = _run0(render_sarif_from_findings(issues, tool_name="startd8-semantic-python"))
    assert run["results"], "issues should render to SARIF results"
    checks = {i.check for i in issues}
    rule_ids = {r["id"] for r in run["tool"]["driver"]["rules"]}
    assert checks == rule_ids
    for r in run["results"]:
        assert r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "svc/handler.py"
