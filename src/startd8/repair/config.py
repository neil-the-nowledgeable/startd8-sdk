"""Repair pipeline configuration.

``RepairConfig`` is a frozen dataclass following the ``ModeConfig`` pattern
from ``prime_contractor.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


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
        max_semantic_repairs_per_file: Safety bound on semantic repairs per file.
        semantic_repair_circuit_breaker_threshold: Consecutive failures before
            disabling semantic repair for the remainder of the run.
    """

    repair_enabled: bool = True
    repairable_categories: frozenset[str] = frozenset({"syntax", "import", "lint", "semantic"})
    pre_checkpoint_repair: bool = False
    staging_root: Optional[Path] = None
    circuit_breaker_threshold: int = 3
    per_step_timeout_s: float = 2.0
    total_timeout_s: float = 5.0
    delta_threshold: float = 0.5
    staging_retention_hours: int = 24
    # Semantic repair (REQ-SR-100–400)
    semantic_repair_categories: frozenset[str] = frozenset()
    max_semantic_repairs_per_file: int = 5
    semantic_repair_circuit_breaker_threshold: int = 3
