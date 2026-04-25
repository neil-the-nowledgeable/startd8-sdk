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
    ContaminationStripJsStep,
    CredentialSanitizeStep,
    CSharpAccessModifierStep,
    CSharpConventionFixStep,
    CSharpNamespaceFixStep,
    CSharpNullableFixStep,
    CSharpSyntaxValidateStep,
    DedupRequireStep,
    EslintAutoFixStep,
    DefinitionOrderFixStep,
    DunderAllFixStep,
    DuplicateRemovalStep,
    ErrorDrivenImportCompletion,
    ExtendedLintFixStep,
    FenceStripStep,
    FutureImportReorderStep,
    GoDotImportCleanupStep,
    GoPythonContaminationStripStep,
    GoSyntaxValidateStep,
    GoUncheckedErrorFixStep,
    IndentNormalizeStep,
    JavaImportSortStep,
    JavaSqlParameterizeStep,
    JavaDuplicateMethodStep,
    JavaMissingOverrideStep,
    JavaRawTypeFixStep,
    JavaSyntaxValidateStep,
    JsSyntaxValidateStep,
    SemanticDiscardedReturnFixStep,
    SemanticDuplicateMainFixStep,
    SemanticImportFixStep,
    SemanticMethodFixStep,
    SemanticMethodResolutionFixStep,
    ShebangStripStep,
    SqlParameterizeStep,
    TodoUncommentStep,
    UnusedVariableRemovalStep,
    VarToConstStep,
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
    "credential_sanitize",
    "csharp_convention_fix",
    "csharp_nullable_fix",
    "csharp_access_modifier_fix",
    "csharp_namespace_fix",
    "sql_parameterize",
    "java_import_sort",
    "java_sql_parameterize",
    "java_missing_override",
    "java_raw_type_fix",
    "java_duplicate_method_fix",
    "ast_validate",
    "java_syntax_validate",
    "go_contamination_strip",
    "go_dot_import_cleanup",
    "go_unchecked_error_fix",
    "go_syntax_validate",
    "csharp_syntax_validate",
    # Node.js repair steps (REQ-KZ-ND-402d Phase 2 + Phase 3)
    "shebang_strip",
    "contamination_strip_js",
    "eslint_autofix",
    "var_to_const",
    "dedup_require",
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
    # REQ-KZ-JV-402e: Java semantic repair routes
    ("security", "java_sql_injection", ["java_sql_parameterize", "java_syntax_validate"], "HIGH", "java"),
    ("semantic", "wildcard_import", ["java_import_sort", "java_syntax_validate"], "MEDIUM", "java"),
    # P4-1: Java semantic repair routes
    ("semantic", "missing_override", ["java_missing_override", "java_syntax_validate"], "MEDIUM", "java"),
    ("semantic", "raw_type_usage", ["java_raw_type_fix", "java_syntax_validate"], "MEDIUM", "java"),
    ("semantic", "duplicate_method", ["java_duplicate_method_fix", "java_syntax_validate"], "MEDIUM", "java"),
    # Go repair routes
    ("syntax", "go_syntax_error", ["fence_strip", "todo_uncomment", "bracket_balance", "go_syntax_validate"], "HIGH", "go"),
    ("import", "go_import_error", ["fence_strip", "todo_uncomment", "go_syntax_validate"], "MEDIUM", "go"),
    # Go semantic repair routes (REQ-KZ-GO-403d Phase 2)
    ("semantic", "python_contamination", ["go_contamination_strip", "go_syntax_validate"], "HIGH", "go"),
    ("semantic", "dot_import", ["go_dot_import_cleanup", "go_syntax_validate"], "MEDIUM", "go"),
    ("semantic", "unchecked_error", ["go_unchecked_error_fix", "go_syntax_validate"], "MEDIUM", "go"),
    # C# repair routes
    ("syntax", "csharp_syntax_error", ["fence_strip", "csharp_convention_fix", "sql_parameterize", "todo_uncomment", "bracket_balance", "csharp_syntax_validate"], "HIGH", "csharp"),
    ("import", "csharp_import_error", ["fence_strip", "csharp_convention_fix", "sql_parameterize", "todo_uncomment", "csharp_syntax_validate"], "MEDIUM", "csharp"),
    ("convention", "csharp_convention_error", ["csharp_convention_fix", "sql_parameterize", "csharp_syntax_validate"], "MEDIUM", "csharp"),
    ("security", "csharp_sql_injection", ["sql_parameterize", "csharp_syntax_validate"], "HIGH", "csharp"),
    # P4-2: C# semantic repair routes
    ("semantic", "missing_nullable_in_csproj", ["csharp_nullable_fix"], "MEDIUM", "csharp"),
    ("semantic", "missing_access_modifier", ["csharp_access_modifier_fix", "csharp_syntax_validate"], "MEDIUM", "csharp"),
    ("semantic", "namespace_filepath_mismatch", ["csharp_namespace_fix", "csharp_syntax_validate"], "MEDIUM", "csharp"),
    # Credential leakage repair — language-neutral step, per-language routing
    ("security", "credential_leakage", ["credential_sanitize", "csharp_syntax_validate"], "HIGH", "csharp"),
    ("security", "credential_leakage", ["credential_sanitize", "java_syntax_validate"], "HIGH", "java"),
    ("security", "credential_leakage", ["credential_sanitize", "go_syntax_validate"], "HIGH", "go"),
    ("security", "credential_leakage", ["credential_sanitize", "js_syntax_validate"], "HIGH", "nodejs"),
    ("security", "credential_leakage", ["credential_sanitize", "ast_validate"], "HIGH", "python"),
    # Node.js repair routes
    ("syntax", "js_syntax_error", ["fence_strip", "shebang_strip", "todo_uncomment", "bracket_balance", "js_syntax_validate"], "HIGH", "nodejs"),
    ("import", "js_import_error", ["fence_strip", "todo_uncomment", "js_syntax_validate"], "MEDIUM", "nodejs"),
    # REQ-KZ-ND-402d Phase 3: Node.js semantic repair routes
    # eslint_autofix is primary for var_usage/duplicate_require — internally
    # falls back to Phase 2 text-based steps when ESLint is unavailable.
    ("semantic", "var_usage", ["eslint_autofix", "js_syntax_validate"], "MEDIUM", "nodejs"),
    ("semantic", "duplicate_require", ["eslint_autofix", "js_syntax_validate"], "MEDIUM", "nodejs"),
    ("semantic", "python_contamination", ["contamination_strip_js", "js_syntax_validate"], "HIGH", "nodejs"),
]

# Step name → step class constructor
_STEP_FACTORIES: dict[str, type] = {
    "credential_sanitize": CredentialSanitizeStep,
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
    "java_import_sort": JavaImportSortStep,
    "java_sql_parameterize": JavaSqlParameterizeStep,
    "java_missing_override": JavaMissingOverrideStep,
    "java_raw_type_fix": JavaRawTypeFixStep,
    "java_duplicate_method_fix": JavaDuplicateMethodStep,
    "java_syntax_validate": JavaSyntaxValidateStep,
    "go_contamination_strip": GoPythonContaminationStripStep,
    "go_dot_import_cleanup": GoDotImportCleanupStep,
    "go_unchecked_error_fix": GoUncheckedErrorFixStep,
    "go_syntax_validate": GoSyntaxValidateStep,
    "csharp_convention_fix": CSharpConventionFixStep,
    "csharp_nullable_fix": CSharpNullableFixStep,
    "csharp_access_modifier_fix": CSharpAccessModifierStep,
    "csharp_namespace_fix": CSharpNamespaceFixStep,
    "sql_parameterize": SqlParameterizeStep,
    "csharp_syntax_validate": CSharpSyntaxValidateStep,
    "js_syntax_validate": JsSyntaxValidateStep,
    # REQ-KZ-ND-402d: Node.js semantic repair steps
    "shebang_strip": ShebangStripStep,
    "contamination_strip_js": ContaminationStripJsStep,
    "eslint_autofix": EslintAutoFixStep,
    "var_to_const": VarToConstStep,
    "dedup_require": DedupRequireStep,
}

# Map file extension → language_id for auto-detection
_EXT_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".java": "java",
    ".go": "go",
    ".cs": "csharp",
    ".vue": "vue",
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
