"""Java semantic validation — regex-based checks for generated Java code.

No external tool dependency.  Eight checks:
1. System.out.println/System.err.println in service classes (should use SLF4J)
2. SQL injection risk via string concatenation
3. Interface file containing class declarations
4. Empty catch blocks (swallow exceptions silently)
5. Raw generic type usage (e.g. ``List`` instead of ``List<String>``)
6. Missing @Override annotation on well-known override methods
7. Missing explicit access modifiers on classes/methods
8. Wildcard imports (``import java.util.*;``)

Known limitation: comment skip only catches ``//`` and ``/*`` at line start.
Multi-line ``/* ... */`` blocks and mid-line comments may cause false positives.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .semantic_checks import SemanticIssue, _basename, _is_comment_line, _stamp_file_path

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
        if _is_comment_line(stripped):
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
        if _is_comment_line(stripped):
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


_EMPTY_CATCH_RE = re.compile(
    r'catch\s*\([^)]*\)\s*\{\s*\}',
)

_RAW_COLLECTION_RE = re.compile(
    r'\b(List|Map|Set|Collection|Iterable)\s+\w+\s*[=;]',
)

_WELL_KNOWN_OVERRIDES = frozenset({
    "toString", "equals", "hashCode", "run", "close", "compareTo",
})

_OVERRIDE_METHOD_RE = re.compile(
    r'(?:public|protected|private)?\s*(?:static\s+)?(?:\w+(?:<[^>]+>)?)\s+'
    r'(?P<name>\w+)\s*\(',
)

_WILDCARD_IMPORT_RE = re.compile(r'import\s+(?:static\s+)?[\w.]+\.\*\s*;')

_ACCESS_MODIFIER_RE = re.compile(r'\b(?:public|private|protected)\b')

_TYPE_RETURN_PATTERNS = re.compile(
    r'^\s*(?:void|int|long|short|byte|char|float|double|boolean|String|'
    r'(?:[A-Z]\w*(?:<[^>]+>)?))\s+\w+\s*\(',
)

_CLASS_NO_MODIFIER_RE = re.compile(
    r'^\s*(?:abstract\s+|final\s+|static\s+)*class\s+\w+',
)


def _check_empty_catch_blocks(source: str) -> List[SemanticIssue]:
    """Flag empty catch blocks (swallow exceptions silently)."""
    issues: List[SemanticIssue] = []
    # Strip single-line comments before matching
    lines = source.splitlines()
    cleaned_lines = []
    for line in lines:
        if _is_comment_line(line.strip()):
            cleaned_lines.append("")
        else:
            cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    for m in _EMPTY_CATCH_RE.finditer(cleaned):
        line_num = cleaned[:m.start()].count('\n') + 1
        if not any(iss.line == line_num for iss in issues):
            issues.append(SemanticIssue(
                check="empty_catch_block",
                severity="warning",
                message=(
                    "Empty catch block — exceptions should be logged or re-thrown"
                ),
                line=line_num,
            ))
    return issues


def _check_raw_type_usage(source: str) -> List[SemanticIssue]:
    """Flag raw generic type usage (e.g. ``List items`` instead of ``List<Item> items``)."""
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        m = _RAW_COLLECTION_RE.search(stripped)
        if m:
            # Check that it's NOT followed by < (parameterized type)
            after_type = stripped[m.start():]
            type_name = m.group(1)
            rest = after_type[len(type_name):]
            if '<' not in rest.split('=')[0].split(';')[0]:
                issues.append(SemanticIssue(
                    check="raw_type_usage",
                    severity="warning",
                    message=(
                        f"Raw type `{type_name}` — use parameterized type "
                        f"(e.g. `{type_name}<String>`)"
                    ),
                    line=i,
                ))
    return issues


def _check_missing_override(source: str) -> List[SemanticIssue]:
    """Flag well-known override methods missing @Override annotation."""
    issues: List[SemanticIssue] = []
    lines = source.splitlines()
    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        m = _OVERRIDE_METHOD_RE.search(stripped)
        if m and m.group("name") in _WELL_KNOWN_OVERRIDES:
            # Check if preceding non-blank line has @Override
            has_override = False
            for j in range(i - 2, max(i - 4, -1), -1):
                if j < 0:
                    break
                prev = lines[j].strip()
                if prev == "":
                    continue
                if "@Override" in prev:
                    has_override = True
                break
            if not has_override:
                issues.append(SemanticIssue(
                    check="missing_override",
                    severity="warning",
                    message=(
                        f"Method `{m.group('name')}()` should have @Override annotation"
                    ),
                    line=i,
                ))
    return issues


def _check_missing_access_modifiers(source: str) -> List[SemanticIssue]:
    """Flag class and method declarations missing explicit access modifiers."""
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        # Check class declarations without access modifier
        if _CLASS_NO_MODIFIER_RE.match(stripped):
            if not _ACCESS_MODIFIER_RE.search(stripped):
                issues.append(SemanticIssue(
                    check="missing_access_modifier",
                    severity="warning",
                    message="Class declaration missing explicit access modifier",
                    line=i,
                ))
        # Check method declarations without access modifier
        elif _TYPE_RETURN_PATTERNS.match(stripped):
            if not _ACCESS_MODIFIER_RE.search(stripped):
                issues.append(SemanticIssue(
                    check="missing_access_modifier",
                    severity="warning",
                    message="Method declaration missing explicit access modifier",
                    line=i,
                ))
    return issues


def _check_wildcard_imports(source: str) -> List[SemanticIssue]:
    """Flag wildcard imports (e.g. ``import java.util.*;``)."""
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if _is_comment_line(stripped):
            continue
        if _WILDCARD_IMPORT_RE.search(stripped):
            issues.append(SemanticIssue(
                check="wildcard_import",
                severity="warning",
                message="Wildcard import — use explicit imports instead",
                line=i,
            ))
    return issues


def _check_package_filepath_alignment(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag package declarations that don't match the directory structure (REQ-KZ-JV-100.2).

    Java convention: ``src/main/java/com/example/service/Foo.java`` should
    declare ``package com.example.service;``.  Strips ``src/main/java/``,
    ``src/test/java/``, ``src/``, and ``java/`` prefixes before comparison.
    """
    if not file_path or not file_path.endswith(".java"):
        return []

    pkg_match = re.search(r'^\s*package\s+([\w.]+)\s*;', source, re.MULTILINE)
    if not pkg_match:
        return []  # Missing package caught by structural checks

    actual_pkg = pkg_match.group(1)

    # Derive expected package from file path
    from pathlib import PurePosixPath
    parts = list(PurePosixPath(file_path).parent.parts)

    # Strip common non-package directory prefixes
    _STRIP_PREFIXES = [
        ("src", "main", "java"),
        ("src", "test", "java"),
        ("src", "main"),
        ("src", "test"),
        ("src",),
        ("java",),
    ]
    for prefix in _STRIP_PREFIXES:
        prefix_len = len(prefix)
        if (
            len(parts) >= prefix_len
            and tuple(p.lower() for p in parts[:prefix_len]) == prefix
        ):
            parts = parts[prefix_len:]
            break

    if not parts or parts == ["."]:
        return []

    expected_pkg = ".".join(parts)

    if actual_pkg == expected_pkg:
        return []

    # Case-insensitive comparison for case-only mismatch
    if actual_pkg.lower() == expected_pkg.lower():
        return [SemanticIssue(
            check="package_case_mismatch",
            severity="warning",
            message=(
                f"Package case mismatch: declared `{actual_pkg}` "
                f"but directory structure implies `{expected_pkg}`"
            ),
        )]

    return [SemanticIssue(
        check="package_filepath_mismatch",
        severity="warning",
        message=(
            f"Package `{actual_pkg}` does not match expected "
            f"`{expected_pkg}` derived from file path `{file_path}`"
        ),
    )]


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
    issues.extend(_check_empty_catch_blocks(source))
    issues.extend(_check_raw_type_usage(source))
    issues.extend(_check_missing_override(source))
    issues.extend(_check_missing_access_modifiers(source))
    issues.extend(_check_wildcard_imports(source))
    issues.extend(_check_package_filepath_alignment(source, file_path))

    return _stamp_file_path(issues, file_path)
