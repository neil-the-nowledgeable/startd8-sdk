"""Java semantic validation — regex-based checks for generated Java code.

No external tool dependency.  Three checks:
1. System.out.println/System.err.println in service classes (should use SLF4J)
2. SQL injection risk via string concatenation
3. Interface file containing class declarations

Known limitation: comment skip only catches ``//`` and ``/*`` at line start.
Multi-line ``/* ... */`` blocks and mid-line comments may cause false positives.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .semantic_checks import SemanticIssue, _basename, _stamp_file_path

_SQL_KW = r'(?:SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|TRUNCATE)\b'
_SQL_CONCAT_RE = re.compile(rf'"[^"]*\b{_SQL_KW}[^"]*"\s*\+', re.IGNORECASE)
_SQL_FORMAT_RE = re.compile(rf'String\s*\.\s*format\s*\(\s*"[^"]*\b{_SQL_KW}', re.IGNORECASE)


def _check_system_out(source: str) -> List[SemanticIssue]:
    """Flag System.out.println/System.err.println in non-main classes."""
    issues: List[SemanticIssue] = []
    # Check if this is a main class — if it has public static void main, allow System.out
    has_main = bool(re.search(
        r'public\s+static\s+void\s+main\s*\(\s*String\s*\[\s*\]',
        source,
    ))
    if has_main:
        return []

    for i, line in enumerate(source.splitlines(), start=1):
        if re.search(r'\bSystem\s*\.\s*(?:out|err)\s*\.\s*print(?:ln)?\s*\(', line):
            issues.append(SemanticIssue(
                check="system_out_in_service",
                severity="warning",
                message=(
                    "System.out/err.println detected — "
                    "use SLF4J (LoggerFactory.getLogger()) instead"
                ),
                line=i,
            ))
    return issues


def _check_sql_injection_risk(source: str) -> List[SemanticIssue]:
    """Flag string concatenation in SQL contexts.

    Detects patterns like:
    - "SELECT ... " + variable
    - String.format("SELECT ... %s", variable)
    """
    issues: List[SemanticIssue] = []

    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        # String concatenation with SQL: "SELECT..." + var
        if _SQL_CONCAT_RE.search(stripped):
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: string concatenation in SQL query — "
                    "use PreparedStatement instead"
                ),
                line=i,
            ))
        # String.format with SQL
        elif _SQL_FORMAT_RE.search(stripped):
            issues.append(SemanticIssue(
                check="sql_injection_risk",
                severity="error",
                message=(
                    "SQL injection risk: String.format() in SQL query — "
                    "use PreparedStatement instead"
                ),
                line=i,
            ))
    return issues


def _check_interface_file_contains_class(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag Java interface files that contain class declarations."""
    if not file_path:
        return []

    name = _basename(file_path)
    stem = name.rsplit(".", 1)[0] if "." in name else name

    # Check files named *Interface.java or starting with I + uppercase
    is_interface_file = (
        name.endswith(".java")
        and (
            stem.endswith("Interface")
            or (stem.startswith("I") and len(stem) > 1 and stem[1].isupper())
        )
    )
    if not is_interface_file:
        return []

    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        if re.search(
            r'\b(?:public|private|protected)?\s*(?:final\s+|abstract\s+|static\s+)*class\s+\w+',
            stripped,
        ):
            issues.append(SemanticIssue(
                check="interface_file_contains_class",
                severity="warning",
                message=(
                    f"Interface file `{name}` contains a class declaration — "
                    f"interface files should contain ONLY the interface definition"
                ),
                line=i,
            ))
    return issues


def run_java_semantic_checks(
    source: str,
    file_path: Optional[str] = None,
) -> List[SemanticIssue]:
    """Run all Java semantic checks on source code.

    Args:
        source: Java source code string.
        file_path: Optional file path for context-sensitive checks.

    Returns:
        List of SemanticIssue objects.
    """
    issues: List[SemanticIssue] = []
    issues.extend(_check_system_out(source))
    issues.extend(_check_sql_injection_risk(source))
    issues.extend(_check_interface_file_contains_class(source, file_path))

    return _stamp_file_path(issues, file_path)
