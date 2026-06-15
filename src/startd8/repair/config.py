"""Repair pipeline configuration.

``RepairConfig`` is a frozen dataclass following the ``ModeConfig`` pattern
from ``prime_contractor.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


# Default per-language semantic repair categories (P3-3).
# Each language enables only the categories that have working repair steps.
_DEFAULT_SEMANTIC_CATEGORIES_BY_LANGUAGE: Dict[str, frozenset[str]] = {
    "python": frozenset({
        "import_resolution", "method_resolution",
        "discarded_return", "duplicate_main_guard",
    }),
    "go": frozenset({
        "unchecked_error", "dot_import", "python_contamination",
    }),
    "nodejs": frozenset({
        "var_usage", "duplicate_require", "python_contamination",
    }),
    "vue": frozenset({
        "var_usage", "duplicate_require", "python_contamination",
    }),
    "java": frozenset({
        "wildcard_import", "java_sql_injection",
    }),
    "csharp": frozenset({
        "csharp_sql_injection", "csharp_convention_error",
    }),
}


@dataclass(frozen=True)
class RepairConfig:
    """Immutable configuration for the repair pipeline.

    Attributes:
        repair_enabled: Master switch for the repair pipeline.
        repairable_categories: Set of diagnostic categories eligible for repair.
        pre_checkpoint_repair: Run repair steps before the first checkpoint.
        staging_root: Root directory for staging copies.
        circuit_breaker_threshold: Max consecutive failures before disabling.
        per_step_timeout_s: Timeout per individual repair step.
        total_timeout_s: Total timeout for the entire repair pipeline.
        delta_threshold: Skip step if it changes more than this fraction of lines.
        staging_retention_hours: Hours to retain failed staging dirs for debugging.
        semantic_repair_categories: Per-category enable for semantic repair (DC-4).
            Default empty — no semantic categories enabled until gate criteria met.
            Used as fallback when language_id is not provided to
            ``get_semantic_categories()``.
        semantic_repair_categories_by_language: Per-language semantic repair
            categories (P3-3). Overrides ``semantic_repair_categories`` when
            a language_id is provided. Defaults to language-specific sets
            matching the repair steps that exist for each language.
        max_semantic_repairs_per_file: Safety bound on semantic repairs per file.
        semantic_repair_circuit_breaker_threshold: Consecutive failures before
            disabling semantic repair for the remainder of the run.
    """

    repair_enabled: bool = True
    # Observer/counterfactual mode (benchmark instrumentation):
    #   "apply"  — normal behaviour: repair runs and is persisted.
    #   "shadow" — repair runs against a throwaway copy ONLY; the raw model
    #              output is preserved as the deliverable and a per-unit
    #              "what repair would have done" report is emitted. Repair has
    #              ZERO influence on the build (checkpoints/retries see raw).
    #   "off"    — equivalent to repair_enabled=False (no run, no report).
    repair_mode: str = "apply"
    # Quality observability (FR-B1/B4): when True, the integration pipeline persists a
    # consolidated defect ledger (.startd8/defect-ledger/*.json) of every detected flaw and
    # skips the advisory downgrade so import/lint failures stay FAILED. Additive, default-off —
    # nothing changes when unset. Composes with repair_mode="shadow" + --benchmark-mode.
    expose_defects: bool = False
    repairable_categories: frozenset[str] = frozenset({"syntax", "import", "lint", "semantic", "security", "convention", "content_contract"})
    pre_checkpoint_repair: bool = False
    staging_root: Optional[Path] = None
    circuit_breaker_threshold: int = 3
    per_step_timeout_s: float = 2.0
    total_timeout_s: float = 5.0
    delta_threshold: float = 0.5
    staging_retention_hours: int = 24
    # Semantic repair (REQ-SR-100–400)
    semantic_repair_categories: frozenset[str] = frozenset()
    semantic_repair_categories_by_language: Dict[str, frozenset[str]] = field(
        default_factory=lambda: dict(_DEFAULT_SEMANTIC_CATEGORIES_BY_LANGUAGE),
    )
    max_semantic_repairs_per_file: int = 5
    semantic_repair_circuit_breaker_threshold: int = 3

    def get_semantic_categories(
        self,
        language_id: Optional[str] = None,
    ) -> frozenset[str]:
        """Get semantic repair categories for a language.

        Args:
            language_id: Language ID (e.g. 'python', 'go'). When provided,
                returns language-specific categories. Falls back to the
                flat ``semantic_repair_categories`` for unknown languages.

        Returns:
            Frozenset of enabled semantic repair category names.
        """
        if language_id and language_id in self.semantic_repair_categories_by_language:
            return self.semantic_repair_categories_by_language[language_id]
        return self.semantic_repair_categories
