"""Route SecurityFinding through the universal SARIF sink (rung 1 of the consume ladder).

Module: src/startd8/query_prime/sarif.py — proves SecurityFinding is a drop-in for
coverage_map.render_sarif_from_findings, with the query-security catalog supplying helpUris.
"""

from __future__ import annotations

from startd8.coverage_map.findings_sarif import SARIF_SCHEMA_URI
from startd8.query_prime.models import SecurityCheckType, SecurityFinding
from startd8.query_prime.sarif import render_security_sarif, result_to_sarif
from startd8.query_prime.security import verify_file

_CSHARP_INJECTION = '''
public async Task DeleteCartAsync(string userId)
{
    var cmd = new NpgsqlCommand(
        $"DELETE FROM cart_items WHERE userId = '{userId}'", conn);
    await cmd.ExecuteNonQueryAsync();
}
'''


def _run0(doc):
    return doc["runs"][0]


def test_security_finding_renders_valid_sarif():
    f = SecurityFinding(
        check_type=SecurityCheckType.INJECTION, severity="error",
        message="string-concat SQL", line=7, file_path="svc/q.py",
    )
    doc = render_security_sarif([f], corpus="svc/q.py")
    assert doc["$schema"] == SARIF_SCHEMA_URI and doc["version"] == "2.1.0"
    run = _run0(doc)
    assert run["tool"]["driver"]["name"] == "query-security"
    res = run["results"][0]
    assert res["ruleId"] == "injection"          # bare check_type.value (on-the-wire)
    assert res["level"] == "error"
    loc = res["locations"][0]["physicalLocation"]
    assert loc["artifactLocation"]["uri"] == "svc/q.py"
    assert loc["region"]["startLine"] == 7
    # helpUri sourced from the query-security catalog
    rule = next(r for r in run["tool"]["driver"]["rules"] if r["id"] == "injection")
    assert rule["helpUri"].endswith("#injection")


def test_severity_is_the_findings_own_not_the_catalog_default():
    # lifecycle's catalog default is 'warning'; a finding may carry 'error' — the finding wins.
    f = SecurityFinding(SecurityCheckType.LIFECYCLE, "error", "unclosed cursor", 3, "a.py")
    assert _run0(render_security_sarif([f]))["results"][0]["level"] == "error"


def test_finding_without_file_is_skipped_and_counted():
    keep = SecurityFinding(SecurityCheckType.INJECTION, "error", "m", 1, "a.py")
    nofile = SecurityFinding(SecurityCheckType.CREDENTIAL_LEAKAGE, "error", "m", 2, None)
    run = _run0(render_security_sarif([keep, nofile]))
    assert len(run["results"]) == 1
    assert run["invocations"][0]["properties"]["skipped"] == 1


def test_enum_check_type_becomes_stable_bare_rule_id():
    findings = [SecurityFinding(t, "error", "m", 1, "a.py") for t in SecurityCheckType]
    rules = {r["id"] for r in _run0(render_security_sarif(findings))["tool"]["driver"]["rules"]}
    assert rules == {t.value for t in SecurityCheckType}


def test_end_to_end_verify_file_to_sarif():
    """The real caller: verify_file → SecurityVerificationResult → SARIF."""
    result = verify_file(_CSHARP_INJECTION, "svc/Cart.cs", "postgresql", "csharp")
    assert result.findings, "expected the injection detector to fire on the C# f-string SQL"
    run = _run0(result_to_sarif(result, corpus="svc/Cart.cs"))
    assert "injection" in {r["id"] for r in run["tool"]["driver"]["rules"]}
    assert all(
        r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] == "svc/Cart.cs"
        for r in run["results"]
    )
