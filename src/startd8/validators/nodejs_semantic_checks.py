"""Node.js semantic validation — regex-based checks for generated JavaScript code.

No external tool dependency.  Six checks:
1. console.log in non-entry modules (should use structured logging)
2. var declarations (should use const/let)
3. Unhandled promise (async call without await or .catch)
4. Duplicate require/import of same module
5. Python contamination fingerprints
6. CommonJS/ESM module system mixing

Known limitation: comment skip only catches ``//`` and ``/*`` at line start.
"""

from __future__ import annotations

import re
from typing import List, Optional

from ..languages._validation_utils import get_contamination_fingerprints
from .semantic_checks import SemanticIssue, _basename, _is_comment_line, _stamp_file_path

_CONSOLE_LOG_RE = re.compile(
    r'\bconsole\s*\.\s*(?:log|warn|error|info|debug)\s*\(',
)

_VAR_DECL_RE = re.compile(r'^\s*var\s+\w+')

_REQUIRE_RE = re.compile(
    r"""(?:require\s*\(\s*['"]([^'"]+)['"]\s*\)|"""
    r"""from\s+['"]([^'"]+)['"]\s*;?)""",
)

_AWAIT_RE = re.compile(r'\bawait\b')

_ASYNC_CALL_RE = re.compile(
    r'^\s*\w+\s*\.\s*(?:save|create|update|delete|find|remove|connect|close|send|fetch)\s*\(',
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
        if _is_comment_line(stripped):
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
        if _is_comment_line(stripped):
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
        if _is_comment_line(stripped):
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
        if _is_comment_line(stripped):
            continue
        if _AWAIT_RE.search(stripped):
            continue
        if '.catch(' in stripped or '.then(' in stripped:
            continue
        if _ASYNC_CALL_RE.match(stripped):
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


# Use centralized fingerprints — avoids per-language copy drift.
_PY_FINGERPRINTS = get_contamination_fingerprints("nodejs")

# "self." requires a line-start anchor to avoid false positives
# in string literals like "help yourself." (QW-1).
_SELF_DOT_RE = re.compile(r'^\s*self\.')


def _check_python_contamination(source: str) -> List[SemanticIssue]:
    """Flag Python fingerprints in JS/TS source files (REQ-KZ-ND-100).

    Line-by-line matching prevents false positives from fingerprints
    appearing inside string literals or comments.
    """
    issues: List[SemanticIssue] = []
    for i, line in enumerate(source.splitlines(), start=1):
        stripped = line.strip()
        # Check shebang BEFORE comment skip — _is_comment_line treats #
        # as a comment, but Python shebangs in JS files are contamination
        if stripped.startswith("#!/usr/bin/env python") or stripped.startswith("#!/usr/bin/python"):
            issues.append(SemanticIssue(
                check="python_contamination",
                severity="error",
                message="Python fingerprint `#!/usr/bin/env python` in JS/TS file — file is non-functional",
                line=i,
            ))
            return issues
        if _is_comment_line(stripped):
            continue
        # Check self. with line-start anchor (avoids "yourself." FP)
        if _SELF_DOT_RE.match(line):
            issues.append(SemanticIssue(
                check="python_contamination",
                severity="error",
                message="Python fingerprint `self.` in JS/TS file — file is non-functional",
                line=i,
            ))
            return issues
        # Check other fingerprints at statement level
        for fp in _PY_FINGERPRINTS:
            if stripped.startswith(fp) or (fp == "def " and re.match(r'^\s*def\s+\w+\s*\(', line)):
                issues.append(SemanticIssue(
                    check="python_contamination",
                    severity="error",
                    message=f"Python fingerprint `{fp.strip()}` in JS/TS file — file is non-functional",
                    line=i,
                ))
                return issues
    return issues


def _check_module_system_consistency(source: str) -> List[SemanticIssue]:
    """Flag mixing of CommonJS and ESM syntax in the same file (REQ-KZ-ND-200).

    CJS: require(), module.exports
    ESM: import/export statements
    Mixing them causes runtime errors in Node.js.
    """
    has_cjs = bool(re.search(r'\brequire\s*\(', source))
    has_esm_import = bool(re.search(r'^\s*import\s+', source, re.MULTILINE))
    has_esm_export = bool(re.search(r'^\s*export\s+', source, re.MULTILINE))
    has_module_exports = bool(re.search(r'\bmodule\.exports\b', source))

    has_cjs_any = has_cjs or has_module_exports
    has_esm_any = has_esm_import or has_esm_export

    if has_cjs_any and has_esm_any:
        return [SemanticIssue(
            check="module_system_mixing",
            severity="error",
            message=(
                "CommonJS (require/module.exports) and ESM (import/export) "
                "mixed in same file — pick one module system"
            ),
        )]
    return []


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
    issues.extend(_check_python_contamination(source))
    issues.extend(_check_console_log_in_service(source, file_path))
    issues.extend(_check_var_usage(source))
    issues.extend(_check_duplicate_requires(source))
    issues.extend(_check_unhandled_promises(source))
    issues.extend(_check_module_system_consistency(source))

    # package.json version validation (dispatched by file type)
    if file_path and file_path.endswith("package.json"):
        issues.extend(_check_package_json_version(source))

    return _stamp_file_path(issues, file_path)


# Known valid Node.js major versions (LTS and current).
_NODE_VERSION_RANGE = (14, 24)


def _check_package_json_version(source: str) -> List[SemanticIssue]:
    """Validate Node.js engine version in package.json.

    Checks:
    - ``"engines": {"node": ">=X"}`` or ``"^X"`` — major version in range.
    - ``"type"`` field present (ESM vs CJS clarity).
    - No Python contamination in package.json.
    """
    issues: List[SemanticIssue] = []

    try:
        import json
        data = json.loads(source)
    except (json.JSONDecodeError, ValueError):
        issues.append(SemanticIssue(
            check="invalid_package_json",
            severity="error",
            message="package.json is not valid JSON",
        ))
        return issues

    # Check engines.node version range
    engines = data.get("engines", {})
    if isinstance(engines, dict):
        node_constraint = engines.get("node", "")
        if node_constraint:
            # Extract major version from constraints like ">=18", "^20.0.0", "18.x"
            version_match = re.search(r'(\d+)', str(node_constraint))
            if version_match:
                major = int(version_match.group(1))
                min_v, max_v = _NODE_VERSION_RANGE
                if not (min_v <= major <= max_v):
                    issues.append(SemanticIssue(
                        check="invalid_node_version",
                        severity="error",
                        message=(
                            f"Node.js engine version `{major}` is outside "
                            f"known valid range ({min_v}–{max_v})"
                        ),
                    ))

    # Check for missing "type" field (ESM/CJS ambiguity)
    if "type" not in data:
        issues.append(SemanticIssue(
            check="missing_module_type",
            severity="warning",
            message=(
                'package.json missing "type" field — add '
                '"type": "module" (ESM) or "type": "commonjs" (CJS) '
                "to make module system explicit"
            ),
        ))

    return issues
