"""OWASP Top 10 coverage matrix — static mapping of implemented checks.

Reports which OWASP categories have check coverage and which are uncovered,
making security posture gaps visible in postmortem output.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

# OWASP Top 10 (2021) → check types that cover each category.
# Uses SecurityCheckType values from query_prime.models.
_OWASP_COVERAGE: Dict[str, Dict[str, Any]] = {
    "A01:2021": {
        "name": "Broken Access Control",
        "checks": [],  # No auth checks implemented yet
    },
    "A02:2021": {
        "name": "Cryptographic Failures",
        "checks": ["credential_leakage"],  # Credential detection covers partial
    },
    "A03:2021": {
        "name": "Injection",
        "checks": ["injection"],  # Two-pass SQL injection detection
    },
    "A04:2021": {
        "name": "Insecure Design",
        "checks": [],  # No design-level checks
    },
    "A05:2021": {
        "name": "Security Misconfiguration",
        "checks": ["lifecycle"],  # Resource lifecycle covers partial
    },
    "A06:2021": {
        "name": "Vulnerable and Outdated Components",
        "checks": [],  # No dependency scanning
    },
    "A07:2021": {
        "name": "Identification and Authentication Failures",
        "checks": [],  # No auth checks
    },
    "A08:2021": {
        "name": "Software and Data Integrity Failures",
        "checks": [],  # No deserialization checks
    },
    "A09:2021": {
        "name": "Security Logging and Monitoring Failures",
        "checks": ["credential_leakage"],  # Detects credential logging
    },
    "A10:2021": {
        "name": "Server-Side Request Forgery (SSRF)",
        "checks": [],  # No SSRF checks
    },
}


def generate_owasp_coverage(
    checks_that_ran: Optional[Set[str]] = None,
    findings_by_check: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """Generate an OWASP Top 10 coverage report.

    Args:
        checks_that_ran: Set of check type strings that actually executed
            (e.g. {"injection", "credential_leakage", "lifecycle"}).
            When None, reports based on implementation status only.
        findings_by_check: Optional dict of check_type → finding count.

    Returns:
        List of dicts, one per OWASP category, with:
        - category: OWASP ID (e.g. "A03:2021")
        - name: Category name
        - status: "COVERED" | "PARTIAL" | "UNCOVERED"
        - checks: List of check types that cover this category
        - findings: Number of findings (0 if no checks ran)
    """
    checks_ran = checks_that_ran or set()
    findings = findings_by_check or {}

    report: List[Dict[str, Any]] = []
    for category_id, info in _OWASP_COVERAGE.items():
        category_checks = info["checks"]
        ran = [c for c in category_checks if c in checks_ran]
        finding_count = sum(findings.get(c, 0) for c in category_checks)

        if not category_checks:
            status = "UNCOVERED"
        elif len(ran) == len(category_checks):
            status = "COVERED"
        elif ran:
            status = "PARTIAL"
        else:
            status = "UNCOVERED"

        report.append({
            "category": category_id,
            "name": info["name"],
            "status": status,
            "checks": category_checks,
            "findings": finding_count,
        })

    return report
