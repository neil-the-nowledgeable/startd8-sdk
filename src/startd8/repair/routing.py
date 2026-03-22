"""Failure routing table (REQ-RPL-002).

Maps diagnostic categories to ordered repair step sequences.
Returns the union of matched steps, deduplicated, in canonical order.

Language-aware routing: when ``language_id`` is provided, only routes
matching that language (or language-agnostic routes) are selected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from .models import Diagnostic, RepairRoute, SemanticDiagnostic
from .steps import (
    AstValidateStep,
    BracketBalanceStep,
    ClassBodyDeduplicationStep,
    CSharpConventionFixStep,
    CSharpSyntaxValidateStep,
    DefinitionOrderFixStep,
    DunderAllFixStep,
    DuplicateRemovalStep,
    ErrorDrivenImportCompletion,
    ExtendedLintFixStep,
    FenceStripStep,
    FutureImportReorderStep,
    GoSyntaxValidateStep,
    IndentNormalizeStep,
    JavaSyntaxValidateStep,
    JsSyntaxValidateStep,
    SemanticDiscardedReturnFixStep,
    SemanticDuplicateMainFixStep,
    SemanticImportFixStep,
    SemanticMethodFixStep,
    SemanticMethodResolutionFixStep,
    TodoUncommentStep,
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
    "todo_uncomment",
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
    "java_syntax_validate",
    "go_syntax_validate",
    "csharp_syntax_validate",
    "js_syntax_validate",
]

# Routing table: (category, pattern, step_names, confidence, language)
# language=None means the route applies to all languages (or when no
# language_id is provided for backward compatibility).
_ROUTING_TABLE: list[tuple[str, str, list[str], str, Optional[str]]] = [
    # Python routes (language=None for backward compat — these are the original routes)
    ("syntax", "syntax_error", ["fence_strip", "todo_uncomment", "future_import_reorder", "indent_normalize", "bracket_balance", "class_body_dedup", "ast_validate"], "HIGH", "python"),
    ("import", "missing_import", ["definition_order_fix", "import_completion", "variable_initialization", "duplicate_removal", "ast_validate"], "HIGH", "python"),
    ("lint", "lint_violation", ["fence_strip", "todo_uncomment", "future_import_reorder", "indent_normalize", "class_body_dedup", "definition_order_fix", "import_completion", "variable_initialization", "duplicate_removal", "extended_lint_fix", "dunder_all_fix", "unused_variable_removal", "ast_validate"], "MEDIUM", "python"),
    # Semantic repair: per-category routing (REQ-SR-100–400) — Python-specific
    ("semantic", "import_resolution", ["semantic_import_fix", "ast_validate"], "HIGH", "python"),
    ("semantic", "method_resolution", ["semantic_method_resolution_fix", "ast_validate"], "HIGH", "python"),
    ("semantic", "discarded_return", ["semantic_discarded_return_fix", "ast_validate"], "MEDIUM", "python"),
    ("semantic", "duplicate_main_guard", ["semantic_duplicate_main_fix", "ast_validate"], "HIGH", "python"),
    # Java repair routes
    ("syntax", "java_syntax_error", ["fence_strip", "todo_uncomment", "bracket_balance", "java_syntax_validate"], "HIGH", "java"),
    ("import", "java_import_error", ["fence_strip", "todo_uncomment", "java_syntax_validate"], "MEDIUM", "java"),
    # Go repair routes
    ("syntax", "go_syntax_error", ["fence_strip", "todo_uncomment", "bracket_balance", "go_syntax_validate"], "HIGH", "go"),
    ("import", "go_import_error", ["fence_strip", "todo_uncomment", "go_syntax_validate"], "MEDIUM", "go"),
    # C# repair routes
    ("syntax", "csharp_syntax_error", ["fence_strip", "csharp_convention_fix", "todo_uncomment", "bracket_balance", "csharp_syntax_validate"], "HIGH", "csharp"),
    ("import", "csharp_import_error", ["fence_strip", "csharp_convention_fix", "todo_uncomment", "csharp_syntax_validate"], "MEDIUM", "csharp"),
    ("convention", "csharp_convention_error", ["csharp_convention_fix", "csharp_syntax_validate"], "MEDIUM", "csharp"),
    # Node.js repair routes
    ("syntax", "js_syntax_error", ["fence_strip", "todo_uncomment", "bracket_balance", "js_syntax_validate"], "HIGH", "nodejs"),
    ("import", "js_import_error", ["fence_strip", "todo_uncomment", "js_syntax_validate"], "MEDIUM", "nodejs"),
]

# Step name → step class constructor
_STEP_FACTORIES: dict[str, type] = {
    "fence_strip": FenceStripStep,
    "todo_uncomment": TodoUncommentStep,
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
    # Semantic repair steps (REQ-SR-100–400)
    "semantic_import_fix": SemanticImportFixStep,
    "semantic_method_resolution_fix": SemanticMethodResolutionFixStep,
    "semantic_discarded_return_fix": SemanticDiscardedReturnFixStep,
    "semantic_duplicate_main_fix": SemanticDuplicateMainFixStep,
    "ast_validate": AstValidateStep,
    "java_syntax_validate": JavaSyntaxValidateStep,
    "go_syntax_validate": GoSyntaxValidateStep,
    "csharp_convention_fix": CSharpConventionFixStep,
    "csharp_syntax_validate": CSharpSyntaxValidateStep,
    "js_syntax_validate": JsSyntaxValidateStep,
}

# Map file extension → language_id for auto-detection
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".java": "java",
    ".go": "go",
    ".cs": "csharp",
    ".js": "nodejs",
    ".mjs": "nodejs",
    ".cjs": "nodejs",
    ".ts": "nodejs",
    ".tsx": "nodejs",
    ".jsx": "nodejs",
}


def infer_language_from_diagnostics(diagnostics: List[Diagnostic]) -> Optional[str]:
    """Infer language_id from diagnostic file extensions.

    Returns the language_id if all diagnostics agree on a single language,
    or None if mixed or unknown.
    """
    from pathlib import PurePosixPath

    languages: set[str] = set()
    for d in diagnostics:
        if d.file:
            ext = PurePosixPath(d.file).suffix.lower()
            lang = _EXT_TO_LANGUAGE.get(ext)
            if lang:
                languages.add(lang)
    if len(languages) == 1:
        return languages.pop()
    return None


def route_failures(
    diagnostics: List[Diagnostic],
    config: "RepairConfig",
    language_id: Optional[str] = None,
) -> RepairRoute:
    """Route diagnostics to an ordered sequence of repair steps.

    Args:
        diagnostics: Parsed checkpoint diagnostics.
        config: Repair pipeline configuration.
        language_id: Optional language identifier (e.g. "python", "java").
            When provided, only routes for that language are selected.
            When None, auto-infers from diagnostic file extensions;
            if inference fails, falls back to matching all routes
            (backward-compatible behavior).

    Returns:
        RepairRoute with matched patterns, ordered steps, and confidence.
    """
    # Auto-infer language if not provided
    if language_id is None:
        language_id = infer_language_from_diagnostics(diagnostics)

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

    for cat, pattern, steps, confidence, route_lang in _ROUTING_TABLE:
        if cat not in categories or cat not in config.repairable_categories:
            continue
        # Semantic entries use pattern as sub-category discriminator
        if cat == "semantic" and pattern not in semantic_subcategories:
            continue
        # Language filtering: skip routes that don't match the target language
        if language_id is not None and route_lang is not None:
            if route_lang != language_id:
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
