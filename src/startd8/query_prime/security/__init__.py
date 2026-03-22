"""Security verification pipeline — REQ-QP-603.

Executes checks in fixed order: injection -> credential -> lifecycle.
Injection + credential findings -> hard fail (SecurityVerdict.FAIL).
Lifecycle findings -> WARN (or FAIL when strict_lifecycle=True).
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from ..models import (
    DatabaseType,
    SecurityCheckType,
    SecurityFinding,
    SecurityVerdict,
    SecurityVerificationResult,
)
from .credentials import detect_credential_leakage
from .injection import detect_injection
from .lifecycle import detect_lifecycle_issues


def verify_file(
    source: str,
    file_path: str,
    database: DatabaseType | str,
    language: str,
    *,
    strict_lifecycle: bool = False,
) -> SecurityVerificationResult:
    """Run the full security verification pipeline on a source file.

    Executes checks in fixed order:
    1. Injection detection
    2. Credential leakage detection
    3. Resource lifecycle issues

    Verdict logic:
    - Injection or credential findings -> SecurityVerdict.FAIL
    - Lifecycle findings only -> SecurityVerdict.WARN (or FAIL if strict_lifecycle)
    - No findings -> SecurityVerdict.PASS

    Args:
        source: Source code text.
        file_path: Path to the source file.
        database: Database type for pattern-aware checks.
        language: Programming language.
        strict_lifecycle: When True, lifecycle issues cause FAIL instead of WARN.

    Returns:
        SecurityVerificationResult with verdict and all findings.
    """
    all_findings: List[SecurityFinding] = []
    timing: Dict[str, float] = {}

    # Phase 1: Injection
    t0 = time.monotonic()
    injection_findings = detect_injection(
        source, database, language, file_path=file_path,
    )
    timing["injection_ms"] = round((time.monotonic() - t0) * 1000, 3)
    all_findings.extend(injection_findings)

    # Phase 2: Credentials
    t0 = time.monotonic()
    credential_findings = detect_credential_leakage(
        source, language, file_path=file_path,
    )
    timing["credential_ms"] = round((time.monotonic() - t0) * 1000, 3)
    all_findings.extend(credential_findings)

    # Phase 3: Lifecycle
    t0 = time.monotonic()
    lifecycle_findings = detect_lifecycle_issues(
        source, database, language, file_path=file_path,
    )
    timing["lifecycle_ms"] = round((time.monotonic() - t0) * 1000, 3)
    all_findings.extend(lifecycle_findings)

    # Compute counts
    errors = sum(1 for f in all_findings if f.severity == "error")
    warnings = sum(1 for f in all_findings if f.severity == "warning")
    total_checks = 3  # injection, credential, lifecycle

    # Determine verdict
    has_hard_fail = any(
        f.check_type in (SecurityCheckType.INJECTION, SecurityCheckType.CREDENTIAL_LEAKAGE)
        and f.severity == "error"
        for f in all_findings
    )
    has_lifecycle_issues = any(
        f.check_type == SecurityCheckType.LIFECYCLE
        for f in all_findings
    )

    if has_hard_fail:
        verdict = SecurityVerdict.FAIL
    elif has_lifecycle_issues and strict_lifecycle:
        verdict = SecurityVerdict.FAIL
    elif has_lifecycle_issues:
        verdict = SecurityVerdict.WARN
    else:
        verdict = SecurityVerdict.PASS

    passed = total_checks - (1 if errors > 0 else 0) - (1 if warnings > 0 else 0)

    return SecurityVerificationResult(
        file_path=file_path,
        verdict=verdict,
        checks_passed=max(0, passed),
        checks_failed=1 if errors > 0 else 0,
        checks_warned=1 if warnings > 0 else 0,
        findings=all_findings,
        verification_timing_ms=timing,
    )
