"""Failure routing table (REQ-RPL-002).

Maps diagnostic categories to ordered repair step sequences.
Returns the union of matched steps, deduplicated, in canonical order.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

from .models import Diagnostic, RepairRoute, SemanticDiagnostic
from .steps import (
    AstValidateStep,
    BracketBalanceStep,
    ClassBodyDeduplicationStep,
    DefinitionOrderFixStep,
    DunderAllFixStep,
    DuplicateRemovalStep,
    ErrorDrivenImportCompletion,
    ExtendedLintFixStep,
    FenceStripStep,
    FutureImportReorderStep,
    IndentNormalizeStep,
    SemanticMethodFixStep,
    UnusedVariableRemovalStep,
    VariableInitializationStep,
)

if TYPE_CHECKING:
    from .config import RepairConfig
    from .protocol import RepairStep

# Canonical step order — steps are always applied in this sequence
# regardless of which diagnostics matched them.
_CANONICAL_ORDER = [
    "fence_strip",
    "future_import_reorder",
    "indent_normalize",
    "bracket_balance",
    "class_body_dedup",
    "definition_order_fix",
    "import_completion",
    "variable_initialization",
    "duplicate_removal",
    "extended_lint_fix",
    "dunder_all_fix",
    "unused_variable_removal",
    "semantic_method_fix",
    "semantic_import_fix",
    "semantic_method_resolution_fix",
    "semantic_discarded_return_fix",
    "semantic_duplicate_main_fix",
    "ast_validate",
]

# Routing table: category → (matched_pattern, step_names, confidence)
_ROUTING_TABLE: list[tuple[str, str, list[str], str]] = [
    ("syntax", "syntax_error", ["fence_strip", "future_import_reorder", "indent_normalize", "bracket_balance", "class_body_dedup", "ast_validate"], "HIGH"),
    ("import", "missing_import", ["definition_order_fix", "import_completion", "variable_initialization", "duplicate_removal", "ast_validate"], "HIGH"),
    ("lint", "lint_violation", ["fence_strip", "future_import_reorder", "indent_normalize", "class_body_dedup", "definition_order_fix", "import_completion", "variable_initialization", "duplicate_removal", "extended_lint_fix", "dunder_all_fix", "unused_variable_removal", "ast_validate"], "MEDIUM"),
    # Semantic repair: per-category routing (REQ-SR-100–400).
    # The "pattern" field doubles as the semantic_category to match against.
    ("semantic", "import_resolution", ["semantic_import_fix", "ast_validate"], "HIGH"),
    ("semantic", "method_resolution", ["semantic_method_resolution_fix", "ast_validate"], "HIGH"),
    ("semantic", "discarded_return", ["semantic_discarded_return_fix", "ast_validate"], "MEDIUM"),
    ("semantic", "duplicate_main_guard", ["semantic_duplicate_main_fix", "ast_validate"], "HIGH"),
]

# Step name → step class constructor
_STEP_FACTORIES: dict[str, type] = {
    "fence_strip": FenceStripStep,
    "future_import_reorder": FutureImportReorderStep,
    "indent_normalize": IndentNormalizeStep,
    "bracket_balance": BracketBalanceStep,
    "class_body_dedup": ClassBodyDeduplicationStep,
    "definition_order_fix": DefinitionOrderFixStep,
    "import_completion": ErrorDrivenImportCompletion,
    "variable_initialization": VariableInitializationStep,
    "duplicate_removal": DuplicateRemovalStep,
    "extended_lint_fix": ExtendedLintFixStep,
    "dunder_all_fix": DunderAllFixStep,
    "semantic_method_fix": SemanticMethodFixStep,
    "unused_variable_removal": UnusedVariableRemovalStep,
    # Semantic repair steps (REQ-SR-100–400) — factories added in Commits 2–5.
    # Steps are in _CANONICAL_ORDER for position but factories are registered
    # when each step implementation ships.
    "ast_validate": AstValidateStep,
}


def route_failures(
    diagnostics: List[Diagnostic],
    config: "RepairConfig",
) -> RepairRoute:
    """Route diagnostics to an ordered sequence of repair steps.

    Args:
        diagnostics: Parsed checkpoint diagnostics.
        config: Repair pipeline configuration.

    Returns:
        RepairRoute with matched patterns, ordered steps, and confidence.
    """
    matched_patterns: list[str] = []
    step_names: set[str] = set()
    min_confidence = "HIGH"
    confidence_rank = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}

    categories = {d.category for d in diagnostics}

    # Collect semantic sub-categories for fine-grained routing
    semantic_subcategories: set[str] = set()
    if "semantic" in categories:
        for d in diagnostics:
            if isinstance(d, SemanticDiagnostic) and d.semantic_category:
                semantic_subcategories.add(d.semantic_category)

    for cat, pattern, steps, confidence in _ROUTING_TABLE:
        if cat not in categories or cat not in config.repairable_categories:
            continue
        # Semantic entries use pattern as sub-category discriminator
        if cat == "semantic" and pattern not in semantic_subcategories:
            continue
        matched_patterns.append(pattern)
        step_names.update(steps)
        if confidence_rank.get(confidence, 0) < confidence_rank.get(min_confidence, 0):
            min_confidence = confidence

    if not step_names:
        return RepairRoute(
            matched_patterns=[],
            steps=[],
            confidence="LOW",
        )

    # Sort by canonical order
    ordered_steps = [s for s in _CANONICAL_ORDER if s in step_names]

    return RepairRoute(
        matched_patterns=matched_patterns,
        steps=ordered_steps,
        confidence=min_confidence,
    )


def create_steps_from_route(route: RepairRoute) -> List["RepairStep"]:
    """Instantiate RepairStep objects from a RepairRoute."""
    steps: list[RepairStep] = []
    for step_name in route.steps:
        factory = _STEP_FACTORIES.get(step_name)
        if factory:
            steps.append(factory())
    return steps
