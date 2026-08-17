"""Coverage, no-fitness guard, prose residue, and the Goodhart gate (FR-6 / FR-7).

The loop's honesty layer: a "passing" run is unambiguously "the runnable fitness passed over a
non-empty set that met the floor", NEVER "the spec is satisfied". This module computes:

  - **coverage** = runnable FRs / total FRs (FR-6), the fitness denominator.
  - the **residue** — the ``assertion``/``manual`` FRs held for a human gate (FR-6).
  - a **``no_fitness``** terminal when the runnable set is empty (FR-6) — never a vacuous green.
  - the **``coverage_below_floor``** terminal when coverage < an operator floor (FR-6).
  - the FR-7 Goodhart gate: every ``pass`` carries a persisted ``assertion_confirmed`` (default
    ``unreviewed``); :func:`is_spec_satisfied` returns ``False`` while any pass is ``unreviewed``.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from . import (
    ASSERTION_CONFIRMED_TRUE,
    VERDICT_ERROR,
    VERDICT_FAIL,
    VERDICT_PASS,
    OracleVerdict,
)
from .grammar import RUNNABLE_KINDS

# The rung/loop status strings — a fitness verdict, never "spec satisfied" (FR-6/NR-6).
STATUS_FITNESS_PASSED = "runnable fitness passed"
STATUS_FITNESS_FAILED = "runnable fitness failed"
STATUS_NO_FITNESS = "no_fitness"
STATUS_COVERAGE_BELOW_FLOOR = "coverage_below_floor"


class CoverageReport(BaseModel):
    """Fitness coverage + residue for a spec (FR-6)."""

    total_frs: int
    runnable_frs: int
    residue_fr_ids: List[str] = Field(default_factory=list)

    @property
    def coverage(self) -> float:
        return (self.runnable_frs / self.total_frs) if self.total_frs else 0.0


def compute_coverage(verdicts: List[OracleVerdict]) -> CoverageReport:
    """Coverage = runnable-kind FRs / total FRs; residue = the non-runnable FR ids (FR-6)."""
    total = len(verdicts)
    runnable = [v for v in verdicts if v.kind in RUNNABLE_KINDS]
    residue = [v.fr_id for v in verdicts if v.kind not in RUNNABLE_KINDS]
    return CoverageReport(
        total_frs=total,
        runnable_frs=len(runnable),
        residue_fr_ids=residue,
    )


def rung_status(verdicts: List[OracleVerdict]) -> str:
    """The ORACLE-rung status (FR-3/FR-6).

    pass iff every runnable FR passed AND the runnable set is non-empty; an empty runnable set →
    ``no_fitness`` (a distinct non-pass, never a vacuous green).
    """
    runnable = [v for v in verdicts if v.kind in RUNNABLE_KINDS]
    if not runnable:
        return STATUS_NO_FITNESS
    if all(v.verdict == VERDICT_PASS for v in runnable):
        return STATUS_FITNESS_PASSED
    return STATUS_FITNESS_FAILED


def failing_runnable(verdicts: List[OracleVerdict]) -> List[OracleVerdict]:
    """The runnable FRs that did not pass (fail/error) — the FR-4 regen-feedback source."""
    return [
        v
        for v in verdicts
        if v.kind in RUNNABLE_KINDS and v.verdict in (VERDICT_FAIL, VERDICT_ERROR)
    ]


def coverage_meets_floor(
    coverage: CoverageReport, min_coverage: Optional[float]
) -> bool:
    """FR-6: True iff no floor is set or coverage >= the floor."""
    if min_coverage is None:
        return True
    return coverage.coverage >= min_coverage


def is_spec_satisfied(verdicts: List[OracleVerdict]) -> bool:
    """FR-7 Goodhart gate: 'is the spec satisfied?'

    Returns ``False`` while ANY runnable pass is ``unreviewed`` (default), and ``True`` only when
    the fitness passed AND every pass is ``assertion_confirmed == true``. Binds to the REQ-08 D-3
    honesty boundary: oracle-pass ≠ spec-satisfied without a recorded human confirmation.
    """
    if rung_status(verdicts) != STATUS_FITNESS_PASSED:
        return False
    passes = [v for v in verdicts if v.verdict == VERDICT_PASS]
    if not passes:
        return False
    return all(v.assertion_confirmed == ASSERTION_CONFIRMED_TRUE for v in passes)


class OracleReport(BaseModel):
    """The terminal loop artifact (FR-6/FR-7/FR-8): what ran, coverage, residue, terminal cause."""

    spec_path: str
    app_root: str
    terminal_cause: str  # pass | budget | max_iterations | stall | coverage_below_floor | no_fitness | disabled | regen_rejected
    status: str  # STATUS_FITNESS_* / no_fitness / coverage_below_floor / disabled
    iterations: int
    coverage: CoverageReport
    verdicts: List[OracleVerdict] = Field(default_factory=list)
    cumulative_cost_usd: float = 0.0
    spec_satisfied: bool = False

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)

    def residue_lines(self) -> List[str]:
        """Human-gate residue: the non-runnable FRs' assertion text (FR-6)."""
        return [
            f"{v.fr_id}: {v.assertion_text}"
            for v in self.verdicts
            if v.fr_id in set(self.coverage.residue_fr_ids)
        ]
