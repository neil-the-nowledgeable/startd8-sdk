"""Go semantic validation — regex-based checks for generated Go code.

No external tool dependency.  Four checks:
1. Unchecked errors (err returned but not checked)
2. Duplicate function names in same file
3. fmt.Println in non-main packages (should use structured logging)
4. Wildcard dot-imports (import . "pkg")

Known limitation: comment skip only catches ``//`` at line start.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .semantic_checks import SemanticIssue, _basename, _stamp_file_path

# Pattern: function call with err return that's not checked
_ERR_ASSIGN_RE = re.compile(
    r'^\s*(?:\w+\s*,\s*)?err\s*(?::=|=)\s*\S+',
)
_ERR_CHECK_RE = re.compile(
    r'if\s+err\s*!=\s*nil',
)

# Pattern: func declaration
_FUNC_DECL_RE = re.compile(
    r'^\s*func\s+(?:\([^)]*\)\s+)?(?P<name>\w+)\s*\(',
)

# Pattern: fmt.Println/Printf/Print
_FMT_PRINT_RE = re.compile(
    r'\bfmt\s*\.\s*(?:Print|Println|Printf)\s*\(',
)

# Pattern: package declaration
_PACKAGE_RE = re.compile(r'^\s*package\s+(\w+)')

# Pattern: dot-import
_DOT_IMPORT_RE = re.compile(
    r'^\s*(?:import\s+)?\.\s+"[^"]+"',
)

# Pattern: Go type declaration
_GO_TYPE_DECL_RE = re.compile(
    r'\b(?:func|type|var|const)\s+\w+',
)


def _check_unchecked_errors(source: str) -> List[SemanticIssue]:
    """Flag error values that are assigned but not checked.

    Detects patterns where ``err`` is assigned but the next non-blank
    line doesn't contain ``if err != nil``.
    """
    issues: List[SemanticIssue] = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if _ERR_ASSIGN_RE.match(stripped):
            # Look ahead for err check within next 3 lines
            found_check = False
            for j in range(i + 1, min(i + 4, len(lines))):
                next_line = lines[j].strip()
                if next_line == "" or next_line.startswith("//"):
                    continue
                if _ERR_CHECK_RE.search(next_line):
                    found_check = True
                    break
                # Any other non-blank line means err was not checked
                break
            if not found_check:
                issues.append(SemanticIssue(
                    check="unchecked_error",
                    severity="warning",
                    message=(
                        "Error value `err` assigned but not checked — "
                        "add `if err != nil` handling"
                    ),
                    line=i + 1,
                ))
    return issues


def _check_duplicate_function_names(source: str) -> List[SemanticIssue]:
    """Flag duplicate function declarations in the same file."""
    issues: List[SemanticIssue] = []
    seen: dict[str, int] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        m = _FUNC_DECL_RE.match(stripped)
        if m:
            name = m.group("name")
            if name in seen:
                issues.append(SemanticIssue(
                    check="duplicate_function",
                    severity="warning",
                    message=(
                        f"Duplicate function `{name}` "
                        f"(first at line {seen[name]}, again at line {i})"
                    ),
                    line=i,
                ))
            else:
                seen[name] = i
    return issues


def _check_fmt_println_in_service(source: str) -> List[SemanticIssue]:
    """Flag fmt.Println/Printf in non-main packages (should use structured logging)."""
    issues: List[SemanticIssue] = []
    # Determine package name
    pkg_match = _PACKAGE_RE.search(source)
    if pkg_match and pkg_match.group(1) == "main":
        return []  # main package can use fmt.Println

    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if _FMT_PRINT_RE.search(stripped):
            issues.append(SemanticIssue(
                check="fmt_println_in_service",
                severity="warning",
                message=(
                    "fmt.Print*/Println in non-main package — "
                    "use structured logging (logrus, zap, slog) instead"
                ),
                line=i,
            ))
    return issues


def _check_dot_imports(source: str) -> List[SemanticIssue]:
    """Flag dot-imports (import . "pkg") which pollute the namespace."""
    issues: List[SemanticIssue] = []
    in_import_block = False
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        if stripped == "import (":
            in_import_block = True
            continue
        if in_import_block and stripped == ")":
            in_import_block = False
            continue
        if in_import_block and _DOT_IMPORT_RE.match(stripped):
            issues.append(SemanticIssue(
                check="dot_import",
                severity="warning",
                message="Dot-import pollutes namespace — use explicit import",
                line=i,
            ))
        elif not in_import_block and re.match(r'^\s*import\s+\.\s+"', stripped):
            issues.append(SemanticIssue(
                check="dot_import",
                severity="warning",
                message="Dot-import pollutes namespace — use explicit import",
                line=i,
            ))
    return issues


def run_go_semantic_checks(
    source: str,
    file_path: Optional[str] = None,
) -> List[SemanticIssue]:
    """Run all Go semantic checks on source code.

    Args:
        source: Go source code string.
        file_path: Optional file path for context-sensitive checks.

    Returns:
        List of SemanticIssue objects.
    """
    issues: List[SemanticIssue] = []
    issues.extend(_check_unchecked_errors(source))
    issues.extend(_check_duplicate_function_names(source))
    issues.extend(_check_fmt_println_in_service(source))
    issues.extend(_check_dot_imports(source))

    return _stamp_file_path(issues, file_path)
