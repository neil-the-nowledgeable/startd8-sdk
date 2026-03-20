"""Node.js semantic validation — regex-based checks for generated JavaScript code.

No external tool dependency.  Four checks:
1. console.log in non-entry modules (should use structured logging)
2. var declarations (should use const/let)
3. Unhandled promise (async call without await or .catch)
4. Duplicate require/import of same module

Known limitation: comment skip only catches ``//`` and ``/*`` at line start.
"""

from __future__ import annotations

import re
from typing import List, Optional

from .semantic_checks import SemanticIssue, _basename, _stamp_file_path

_CONSOLE_LOG_RE = re.compile(
    r'\bconsole\s*\.\s*(?:log|warn|error|info|debug)\s*\(',
)

_VAR_DECL_RE = re.compile(r'^\s*var\s+\w+')

_REQUIRE_RE = re.compile(
    r"""(?:require\s*\(\s*['"]([^'"]+)['"]\s*\)|"""
    r"""from\s+['"]([^'"]+)['"]\s*;?)""",
)


def _check_console_log_in_service(
    source: str,
    file_path: Optional[str],
) -> List[SemanticIssue]:
    """Flag console.log in non-entry modules (should use structured logging)."""
    issues: List[SemanticIssue] = []
    # Allow console.log in entry points
    if file_path:
        name = _basename(file_path)
        if name in ("index.js", "main.js", "app.js", "server.js", "cli.js"):
            return []

    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        if _CONSOLE_LOG_RE.search(stripped):
            issues.append(SemanticIssue(
                check="console_log_in_service",
                severity="warning",
                message=(
                    "console.log/warn/error detected — "
                    "use a structured logger (winston, pino) instead"
                ),
                line=i,
            ))
    return issues


def _check_var_usage(source: str) -> List[SemanticIssue]:
    """Flag var declarations (should use const or let)."""
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        if _VAR_DECL_RE.match(stripped):
            issues.append(SemanticIssue(
                check="var_usage",
                severity="warning",
                message="Use `const` or `let` instead of `var`",
                line=i,
            ))
    return issues


def _check_duplicate_requires(source: str) -> List[SemanticIssue]:
    """Flag duplicate require() or import of the same module."""
    issues: List[SemanticIssue] = []
    seen: dict[str, int] = {}
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        m = _REQUIRE_RE.search(stripped)
        if m:
            module = m.group(1) or m.group(2)
            if module in seen:
                issues.append(SemanticIssue(
                    check="duplicate_require",
                    severity="warning",
                    message=(
                        f"Duplicate import of `{module}` "
                        f"(first at line {seen[module]})"
                    ),
                    line=i,
                ))
            else:
                seen[module] = i
    return issues


def _check_unhandled_promises(source: str) -> List[SemanticIssue]:
    """Flag async function calls without await or .catch().

    Detects simple patterns: a line calling an async-looking function
    (name contains 'async' or returns promise) without await or .catch.
    """
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("/*"):
            continue
        # Skip lines that already have await
        if re.search(r'\bawait\b', stripped):
            continue
        # Skip lines that have .catch or .then
        if '.catch(' in stripped or '.then(' in stripped:
            continue
        # Detect common async patterns without await
        # Pattern: standalone function call that's known async
        if re.match(r'^\s*\w+\s*\.\s*(?:save|create|update|delete|find|remove|connect|close|send|fetch)\s*\(', stripped):
            # Only flag if it's a standalone statement (ends with ; or ))
            if stripped.rstrip().endswith(';') or stripped.rstrip().endswith(')'):
                issues.append(SemanticIssue(
                    check="unhandled_promise",
                    severity="warning",
                    message=(
                        "Potentially unhandled promise — "
                        "add `await` or `.catch()` for error handling"
                    ),
                    line=i,
                ))
    return issues


def run_nodejs_semantic_checks(
    source: str,
    file_path: Optional[str] = None,
) -> List[SemanticIssue]:
    """Run all Node.js semantic checks on source code.

    Args:
        source: JavaScript/TypeScript source code string.
        file_path: Optional file path for context-sensitive checks.

    Returns:
        List of SemanticIssue objects.
    """
    issues: List[SemanticIssue] = []
    issues.extend(_check_console_log_in_service(source, file_path))
    issues.extend(_check_var_usage(source))
    issues.extend(_check_duplicate_requires(source))
    issues.extend(_check_unhandled_promises(source))

    return _stamp_file_path(issues, file_path)
