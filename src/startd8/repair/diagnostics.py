"""Checkpoint diagnostic parsing (REQ-RPL-202).

Parses ``CheckpointResult`` output into typed ``Diagnostic`` subclasses
for consumption by the repair routing table.

Uses only stdlib types in the public API. The ``CheckpointResult`` type
is referenced via structural typing (duck typing) to avoid importing
from ``contractors/``.
"""

from __future__ import annotations

import re
from typing import Any, List

from .models import Diagnostic, ImportDiagnostic, LintDiagnostic, SyntaxDiagnostic

# R5-S4: ANSI escape sequence pattern
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")

# R5-S4: Secret patterns to redact
_SECRET_PATTERNS = re.compile(
    r"([A-Z_]*(?:API_KEY|SECRET|TOKEN|PASSWORD|CREDENTIALS))\s*=\s*\S+",
    re.IGNORECASE,
)

# Max line length for diagnostic messages
_MAX_LINE_LENGTH = 500


def _sanitize(text: str) -> str:
    """Sanitize diagnostic text (R5-S4).

    Strips ANSI escapes, truncates long lines, redacts secrets.
    """
    text = _ANSI_ESCAPE.sub("", text)
    text = _SECRET_PATTERNS.sub(r"\1=***REDACTED***", text)
    lines = text.splitlines()
    sanitized = []
    for line in lines:
        if len(line) > _MAX_LINE_LENGTH:
            line = line[:_MAX_LINE_LENGTH] + "..."
        sanitized.append(line)
    return "\n".join(sanitized)


# ═══════════════════════════════════════════════════════════════════════════
# Regex parsers per checkpoint type
# ═══════════════════════════════════════════════════════════════════════════

# Syntax: '  File "foo.py", line 10\n    SyntaxError: ...'
_SYNTAX_FILE_LINE = re.compile(
    r'File "(?P<file>.+?)", line (?P<line>\d+)',
)

# Import: 'foo.py: ModuleNotFoundError: No module named \'bar\''
_IMPORT_MODULE = re.compile(
    r"(?:ModuleNotFoundError|ImportError):\s*No module named ['\"](?P<module>[^'\"]+)['\"]",
)

# Import: 'cannot import name \'X\' from \'Y\''
_IMPORT_NAME = re.compile(
    r"cannot import name ['\"](?P<name>[^'\"]+)['\"] from ['\"](?P<module>[^'\"]+)['\"]",
)

# Lint: 'foo.py:10:4: F401 unused import'
_LINT_RULE = re.compile(
    r"(?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+):\s*(?P<rule>\w+)\s+(?P<message>.+)",
)


def classify_checkpoint_category(result: Any) -> str:
    """Classify a checkpoint result into a repair category.

    Args:
        result: A ``CheckpointResult``-like object with ``name`` and
            ``status`` attributes.

    Returns:
        One of "syntax", "import", "lint", "test", "size", or "unknown".
    """
    name = getattr(result, "name", "").lower()
    if "syntax" in name or "compile" in name:
        return "syntax"
    if "import" in name:
        return "import"
    if "lint" in name or "ruff" in name:
        return "lint"
    if "test" in name or "pytest" in name:
        return "test"
    if "size" in name or "regression" in name:
        return "size"
    return "unknown"


def parse_checkpoint_diagnostics(results: List[Any]) -> List[Diagnostic]:
    """Parse checkpoint results into typed diagnostics.

    Args:
        results: List of ``CheckpointResult``-like objects with ``name``,
            ``status``, ``errors``, and ``message`` attributes.

    Returns:
        List of typed ``Diagnostic`` subclass instances.
    """
    diagnostics: list[Diagnostic] = []

    for r in results:
        status = getattr(r, "status", None)
        # Only parse failed results
        if status is not None:
            status_val = status.value if hasattr(status, "value") else str(status)
            if status_val != "failed":
                continue

        category = classify_checkpoint_category(r)
        errors = getattr(r, "errors", []) or []
        message = getattr(r, "message", "")

        parts = [message] + list(errors)
        all_text = "\n".join(p for p in parts if p)
        all_text = _sanitize(all_text)

        if category == "syntax":
            diagnostics.extend(_parse_syntax_errors(all_text))
        elif category == "import":
            diagnostics.extend(_parse_import_errors(all_text))
        elif category == "lint":
            diagnostics.extend(_parse_lint_errors(all_text))
        else:
            # Non-repairable — pass through as base Diagnostic
            if errors:
                for err in errors:
                    diagnostics.append(Diagnostic(
                        category=category,
                        file="",
                        message=_sanitize(err),
                    ))
            elif message:
                diagnostics.append(Diagnostic(
                    category=category,
                    file="",
                    message=_sanitize(message),
                ))

    return diagnostics


def _parse_syntax_errors(text: str) -> list[Diagnostic]:
    """Parse syntax check output into SyntaxDiagnostic instances."""
    results: list[Diagnostic] = []
    for match in _SYNTAX_FILE_LINE.finditer(text):
        results.append(SyntaxDiagnostic(
            category="syntax",
            file=match.group("file"),
            message=text.strip(),
            line=int(match.group("line")),
        ))
    if not results:
        # Fallback: just create one diagnostic from the text
        results.append(SyntaxDiagnostic(
            category="syntax",
            file="",
            message=text.strip(),
        ))
    return results


def _parse_import_errors(text: str) -> list[Diagnostic]:
    """Parse import check output into ImportDiagnostic instances."""
    results: list[Diagnostic] = []

    for match in _IMPORT_NAME.finditer(text):
        results.append(ImportDiagnostic(
            category="import",
            file="",
            message=text.strip(),
            module=match.group("module"),
            name=match.group("name"),
        ))

    for match in _IMPORT_MODULE.finditer(text):
        module = match.group("module")
        # Skip if already captured by _IMPORT_NAME
        if any(d.module == module for d in results if isinstance(d, ImportDiagnostic)):
            continue
        results.append(ImportDiagnostic(
            category="import",
            file="",
            message=text.strip(),
            module=module,
        ))

    if not results:
        results.append(ImportDiagnostic(
            category="import",
            file="",
            message=text.strip(),
        ))
    return results


def _parse_lint_errors(text: str) -> list[Diagnostic]:
    """Parse lint check output into LintDiagnostic instances."""
    results: list[Diagnostic] = []
    for match in _LINT_RULE.finditer(text):
        rule = match.group("rule")
        # Rules starting with E7, E9, F are auto-fixable by ruff
        fixable = bool(re.match(r"^(E[79]|F)\d+$", rule))
        results.append(LintDiagnostic(
            category="lint",
            file=match.group("file"),
            message=match.group("message"),
            rule=rule,
            line=int(match.group("line")),
            fixable=fixable,
        ))
    if not results:
        results.append(LintDiagnostic(
            category="lint",
            file="",
            message=text.strip(),
        ))
    return results
