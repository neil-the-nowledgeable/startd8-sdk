"""Bridge between semantic validation and the repair pipeline.

Translates ``DiskComplianceResult.semantic_issues`` dicts from
``forward_manifest_validator.validate_disk_compliance()`` into
``SemanticDiagnostic`` objects that the repair routing table can dispatch.

Only categories with registered repair steps are translated — unknown
categories stay as detection-only warnings.
"""

from __future__ import annotations

from typing import List

from .models import SemanticDiagnostic

# Categories that have a corresponding repair step registered in the
# routing table.  Updated when new semantic repair steps are added.
_REPAIRABLE_CATEGORIES: frozenset[str] = frozenset({
    "method_resolution",
    "import_resolution",
    "discarded_return",
    "duplicate_main_guard",
})


def translate_to_diagnostics(
    semantic_issues: list[dict],
    file_path: str,
) -> List[SemanticDiagnostic]:
    """Convert semantic issue dicts to ``SemanticDiagnostic`` objects.

    Args:
        semantic_issues: Dicts from ``DiskComplianceResult.semantic_issues``
            with keys ``category``, ``severity``, ``message``, ``line``,
            ``symbol``.
        file_path: Path to the source file (for the diagnostic ``file`` field).

    Returns:
        List of ``SemanticDiagnostic`` — only repairable categories included.
    """
    diagnostics: list[SemanticDiagnostic] = []
    for issue in semantic_issues:
        if not isinstance(issue, dict):
            continue
        category = issue.get("category", "")
        if category not in _REPAIRABLE_CATEGORIES:
            continue

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
