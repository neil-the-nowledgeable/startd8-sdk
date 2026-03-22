"""Go semantic validation — regex-based checks for generated Go code.

No external tool dependency.  Six checks:
1. Unchecked errors (err returned but not checked)
2. Duplicate function names in same file
3. fmt.Println in non-main packages (should use structured logging)
4. Wildcard dot-imports (import . "pkg")
5. Python contamination (cross-language fingerprints)
6. Package/directory name mismatch
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..languages._validation_utils import GO_CONTAMINATION_FINGERPRINTS
from .semantic_checks import SemanticIssue, _basename, _is_comment_line, _stamp_file_path

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

def _check_unchecked_errors(source: str) -> List[SemanticIssue]:
    """Flag error values that are assigned but not checked.

    Detects patterns where ``err`` is assigned but the next non-blank
    line doesn't contain ``if err != nil``.
    """
    issues: List[SemanticIssue] = []
    lines = source.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if _is_comment_line(stripped):
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
        if _is_comment_line(stripped):
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
        if _is_comment_line(stripped):
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
        if _is_comment_line(stripped):
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


def _check_python_contamination(source: str) -> List[SemanticIssue]:
    """Flag Python fingerprints in Go source files (REQ-KZ-GO-201).

    Uses line-level scanning with context awareness (REQ-KZ-GO-402b):
    - Skips lines inside backtick-delimited raw string literals.
    - Skips matches after ``//`` on the same line.
    - Tracks ``/* ... */`` block comment state.
    - Reports ALL matching fingerprints (REQ-KZ-GO-402a item 3).
    """
    issues: List[SemanticIssue] = []
    seen: set[str] = set()
    in_raw_string = False
    in_block_comment = False

    for i, line in enumerate(source.splitlines(), start=1):
        # Track block comment state
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
                # Fall through to check code after */ on this line
                line = line[line.index("*/") + 2:]
            else:
                continue
        if "/*" in line:
            if "*/" in line:
                # Single-line block comment — remove it, check remainder
                start = line.index("/*")
                end = line.index("*/") + 2
                line = line[:start] + line[end:]
            else:
                in_block_comment = True
                # Check code before /* on this line
                line = line[:line.index("/*")]

        # Track backtick raw string state (toggle per backtick)
        backtick_count = line.count("`")
        if in_raw_string:
            if backtick_count % 2 == 1:
                in_raw_string = False
            continue
        if backtick_count % 2 == 1:
            in_raw_string = True
            # Still check the part before the backtick
            check_line = line[:line.index("`")]
        else:
            check_line = line

        # Strip inline comments for matching
        comment_pos = check_line.find("//")
        check_text = check_line[:comment_pos] if comment_pos >= 0 else check_line
        stripped = check_text.strip()
        if not stripped:
            continue

        for fp in GO_CONTAMINATION_FINGERPRINTS:
            if fp in stripped and fp not in seen:
                seen.add(fp)
                issues.append(SemanticIssue(
                    check="python_contamination",
                    severity="error",
                    message=f"Python fingerprint `{fp.strip()}` in Go file — file is non-functional",
                    line=i,
                ))
    return issues


def _check_package_filepath_alignment(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag package declarations that don't match the directory name.

    Go convention: the package name matches the directory name
    (e.g., file at ``cmd/server/main.go`` has ``package main``,
    file at ``internal/store/redis.go`` has ``package store``).
    """
    if not file_path or not file_path.endswith(".go"):
        return []

    pkg_match = _PACKAGE_RE.search(source)
    if not pkg_match:
        return []

    actual_pkg = pkg_match.group(1)

    from pathlib import PurePosixPath
    parent_dir = PurePosixPath(file_path).parent.name
    if not parent_dir or parent_dir == ".":
        return []

    # Go package should match directory name (except _test suffix)
    expected_pkg = parent_dir.replace("-", "")  # hyphens stripped in Go packages
    if actual_pkg == expected_pkg or actual_pkg == expected_pkg + "_test":
        return []

    return [SemanticIssue(
        check="package_dir_mismatch",
        severity="warning",
        message=(
            f"Package `{actual_pkg}` does not match directory name "
            f"`{parent_dir}` — Go convention requires package name to match directory"
        ),
    )]


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
    issues.extend(_check_python_contamination(source))
    issues.extend(_check_unchecked_errors(source))
    issues.extend(_check_duplicate_function_names(source))
    issues.extend(_check_fmt_println_in_service(source))
    issues.extend(_check_dot_imports(source))
    issues.extend(_check_package_filepath_alignment(source, file_path))

    return _stamp_file_path(issues, file_path)
