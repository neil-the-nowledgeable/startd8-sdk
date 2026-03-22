"""Bridge between semantic validation and the repair pipeline.

Translates ``DiskComplianceResult.semantic_issues`` dicts from
``forward_manifest_validator.validate_disk_compliance()`` into
``SemanticDiagnostic`` objects that the repair routing table can dispatch.

Only categories with registered repair steps are translated — unknown
categories stay as detection-only warnings.
"""

from __future__ import annotations

from typing import List

from .models import Diagnostic, SemanticDiagnostic

# Categories that have a corresponding repair step registered in the
# routing table.  Updated when new semantic repair steps are added.
_REPAIRABLE_CATEGORIES: frozenset[str] = frozenset({
    "method_resolution",
    "import_resolution",
    "discarded_return",
    "duplicate_main_guard",
    # REQ-KZ-CS-402b: C# SQL injection → sql_parameterize step
    "sql_injection_risk",
})

# REQ-KZ-CS-402b: Categories that route through a non-"semantic" routing
# category.  SemanticDiagnostic forces category="semantic", but the routing
# table entry for C# SQL injection uses category="security".  These produce
# a plain Diagnostic with the correct routing category instead.
_CATEGORY_TO_ROUTE: dict[str, str] = {
    "sql_injection_risk": "security",
}

# Map semantic issue categories to routing-table pattern names.
# Default: the category name itself (e.g. "import_resolution").
_CATEGORY_TO_PATTERN: dict[str, str] = {
    "sql_injection_risk": "csharp_sql_injection",
}


def translate_to_diagnostics(
    semantic_issues: List[dict],
    file_path: str,
) -> List[Diagnostic]:
    """Convert semantic issue dicts to ``Diagnostic`` objects.

    Args:
        semantic_issues: Dicts from ``DiskComplianceResult.semantic_issues``
            with keys ``category``, ``severity``, ``message``, ``line``,
            ``symbol``.
        file_path: Path to the source file (for the diagnostic ``file`` field).

    Returns:
        List of ``Diagnostic`` (or ``SemanticDiagnostic``) — only repairable
        categories included.
    """
    diagnostics: list[Diagnostic] = []
    for issue in semantic_issues:
        if not isinstance(issue, dict):
            continue
        category = issue.get("category", "")
        if category not in _REPAIRABLE_CATEGORIES:
            continue

        route_category = _CATEGORY_TO_ROUTE.get(category)
        if route_category is not None:
            # REQ-KZ-CS-402b: non-semantic routing (e.g. "security")
            diagnostics.append(Diagnostic(
                category=route_category,
                file=file_path,
                message=issue.get("message", ""),
            ))
        else:
            diagnostics.append(SemanticDiagnostic(
                category="semantic",
                file=file_path,
                message=issue.get("message", ""),
                semantic_category=category,
                severity=issue.get("severity", "warning"),
                symbol=issue.get("symbol", ""),
                line=issue.get("line", 0),
            ))

    return diagnostics
