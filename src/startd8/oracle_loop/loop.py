"""The closed oracle-generation loop (FR-4 / FR-5 / FR-8 / FR-10 / FR-11).

Drives: (plan-ingest →) generate → deploy+ORACLE rung → on-fail regenerate-with-feedback → re-grade,
terminating fail-closed on the FIRST of {all runnable pass · cumulative budget · max-iterations ·
no-progress stall}, plus the FR-6 ``no_fitness`` / ``coverage_below_floor`` gates and the FR-11
default-off gate.

Injection seams keep the loop $0-testable (no real LLM): the caller supplies

  - ``generate_fn(feedback: Optional[GenFeedback]) -> GenOutcome`` — runs one generation pass; the
    real CLI wires this to Prime's ``process_feature`` regen path (FR-4), honoring its preconditions
    and mapping a ``_seam_marked_targets`` reject to a FATAL ``regen_rejected``.
  - ``deploy_fn(app_root) -> List[OracleVerdict]`` — deploys the output and runs the ORACLE rung; the
    real CLI wires this to ``deploy_app_local(..., spec_path=...)`` then reads ``oracle_verdicts``.

The **structured** regen feedback (FR-4 / R1-F7) carries the failing FR's intent + exact command +
observed-vs-expected + ``assertion_text`` — a behavioral target for a cheap model, not a bare stderr.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from ..logging_config import get_logger
from . import (
    OracleVerdict,
    oracle_loop_enabled,
)
from .report import (
    STATUS_COVERAGE_BELOW_FLOOR,
    STATUS_FITNESS_FAILED,
    STATUS_FITNESS_PASSED,
    STATUS_NO_FITNESS,
    CoverageReport,
    OracleReport,
    compute_coverage,
    coverage_meets_floor,
    failing_runnable,
    is_spec_satisfied,
    rung_status,
)

logger = get_logger("startd8.oracle_loop.loop")

# Terminal causes (FR-5 / FR-6 / FR-8 / FR-11). ``pass`` = 0 exit; the rest are fail-closed.
CAUSE_PASS = "pass"
CAUSE_BUDGET = "budget"
CAUSE_MAX_ITERATIONS = "max_iterations"
CAUSE_STALL = "stall"
CAUSE_COVERAGE_BELOW_FLOOR = "coverage_below_floor"
CAUSE_NO_FITNESS = "no_fitness"
CAUSE_REGEN_REJECTED = "regen_rejected"
CAUSE_DISABLED = "disabled"

# Exit codes (FR-8): 0 iff pass, non-zero (1) otherwise. The cause is the diagnostic.
_NONZERO = 1


@dataclass
class GenFeedback:
    """Structured regeneration feedback for one failing FR (FR-4 / R1-F7)."""

    fr_id: str
    intent: str  # the FR Name/intent — a behavioral target, not just an id
    command_or_probe: str
    observed: str
    expected: str
    assertion_text: str

    def render(self) -> str:
        return (
            f"[FR {self.fr_id}] {self.intent}\n"
            f"  Verify command/probe: {self.command_or_probe}\n"
            f"  Observed: {self.observed}\n"
            f"  Expected: {self.expected}\n"
            f"  Behavioral goal (assertion): {self.assertion_text}"
        )


@dataclass
class GenOutcome:
    """Result of one generation pass returned by the injected ``generate_fn``."""

    app_root: Path
    cost_usd: float = 0.0
    # A FATAL Prime outcome (e.g. ``_seam_marked_targets`` reject) → loop terminates ``regen_rejected``.
    regen_rejected: bool = False
    reject_reason: str = ""


# Type aliases for the injection seams.
GenerateFn = Callable[[Optional[List[GenFeedback]]], GenOutcome]
DeployFn = Callable[[Path], List[OracleVerdict]]


def build_feedback(
    verdicts: List[OracleVerdict], fr_intent: dict
) -> List[GenFeedback]:
    """Turn the failing runnable verdicts into structured feedback (FR-4).

    ``fr_intent`` maps ``fr_id -> intent string`` (the FR Name); a missing entry falls back to the
    fr_id so the feedback still names a target.
    """
    out: List[GenFeedback] = []
    for v in failing_runnable(verdicts):
        expected = "command exits 0" if v.kind == "one-shot" else "probe status matches"
        out.append(
            GenFeedback(
                fr_id=v.fr_id,
                intent=fr_intent.get(v.fr_id, v.fr_id),
                command_or_probe=v.command_or_probe,
                observed=v.reason,
                expected=expected,
                assertion_text=v.assertion_text,
            )
        )
    return out


def _signature(v: OracleVerdict) -> str:
    """A failure signature: fr_id + command + a stable hash of the reason tail (R1-F4)."""
    import hashlib

    tail = (v.reason or "")[-120:]
    h = hashlib.sha256(tail.encode("utf-8", "replace")).hexdigest()[:12]
    return f"{v.fr_id}|{v.command_or_probe}|{h}"


def _failure_multiset(verdicts: List[OracleVerdict]) -> List[str]:
    return sorted(_signature(v) for v in failing_runnable(verdicts))


class _StallDetector:
    """Monotone-reduction stall detector (FR-5 / R1-F4).

    Stall = the multiset of failure signatures fails to SHRINK for ``patience`` consecutive rounds.
    A loop that rotates WHICH FRs fail (so the set differs each round) still trips, because the
    *count* of outstanding failures does not decrease. This is strictly stronger than set-equality.
    """

    def __init__(self, patience: int = 3) -> None:
        self.patience = patience
        self._best_size: Optional[int] = None
        self._no_progress_rounds = 0

    def record(self, verdicts: List[OracleVerdict]) -> bool:
        size = len(_failure_multiset(verdicts))
        if self._best_size is None or size < self._best_size:
            self._best_size = size
            self._no_progress_rounds = 0
            return False
        # No reduction vs the best-so-far.
        self._no_progress_rounds += 1
        return self._no_progress_rounds >= self.patience


def run_build_to_spec_loop(
    spec_path: Path | str,
    *,
    generate_fn: GenerateFn,
    deploy_fn: DeployFn,
    fr_intent: Optional[dict] = None,
    max_iterations: int = 3,
    max_cost_usd: Optional[float] = None,
    min_coverage: Optional[float] = None,
    stall_patience: int = 3,
    enabled: Optional[bool] = None,
) -> OracleReport:
    """Run the closed loop and return the terminal :class:`OracleReport` (FR-4/5/6/7/8/10/11).

    ``enabled`` overrides the FR-11 config gate for tests; ``None`` consults
    :func:`oracle_loop_enabled` (default false). While disabled the loop runs NO generation/deploy
    and returns a ``disabled`` report.
    """
    spec_path = Path(spec_path)
    fr_intent = fr_intent or {}
    is_enabled = oracle_loop_enabled() if enabled is None else enabled

    if not is_enabled:
        logger.info("oracle_loop disabled — refusing build-to-spec (FR-11)")
        return OracleReport(
            spec_path=str(spec_path),
            app_root="",
            terminal_cause=CAUSE_DISABLED,
            status=CAUSE_DISABLED,
            iterations=0,
            coverage=CoverageReport(total_frs=0, runnable_frs=0),
        )

    stall = _StallDetector(patience=stall_patience)
    cumulative_cost = 0.0
    feedback: Optional[List[GenFeedback]] = None
    verdicts: List[OracleVerdict] = []
    coverage = CoverageReport(total_frs=0, runnable_frs=0)
    app_root = Path("")
    prev_sigs: Optional[List[str]] = None

    for iteration in range(1, max_iterations + 1):
        # ---- generate (FR-4: honors the injected generator's preconditions) ----
        outcome = generate_fn(feedback)
        cumulative_cost += outcome.cost_usd
        app_root = outcome.app_root

        if outcome.regen_rejected:
            logger.error(
                "regen rejected (FATAL): %s", outcome.reject_reason,
                extra={"terminal_cause": CAUSE_REGEN_REJECTED},
            )
            return _finalize(
                spec_path, app_root, CAUSE_REGEN_REJECTED, iteration,
                coverage, verdicts, cumulative_cost,
            )

        # ---- deploy + ORACLE rung (FR-3 via the injected deploy_fn) ----
        verdicts = deploy_fn(app_root)
        coverage = compute_coverage(verdicts)
        status = rung_status(verdicts)

        # FR-6: no-fitness / coverage-floor gates (checked once fitness is observed).
        if status == STATUS_NO_FITNESS:
            _emit_iteration(iteration, coverage, verdicts, prev_sigs, cumulative_cost)
            return _finalize(
                spec_path, app_root, CAUSE_NO_FITNESS, iteration,
                coverage, verdicts, cumulative_cost,
            )
        if not coverage_meets_floor(coverage, min_coverage):
            _emit_iteration(iteration, coverage, verdicts, prev_sigs, cumulative_cost)
            report = _finalize(
                spec_path, app_root, CAUSE_COVERAGE_BELOW_FLOOR, iteration,
                coverage, verdicts, cumulative_cost,
            )
            report.status = STATUS_COVERAGE_BELOW_FLOOR
            return report

        _emit_iteration(iteration, coverage, verdicts, prev_sigs, cumulative_cost)
        prev_sigs = _failure_multiset(verdicts)

        # ---- pass? ----
        if status == STATUS_FITNESS_PASSED:
            return _finalize(
                spec_path, app_root, CAUSE_PASS, iteration,
                coverage, verdicts, cumulative_cost,
            )

        # ---- stall (FR-5, monotone-reduction) ----
        if stall.record(verdicts):
            logger.warning("loop stalled (no-progress)", extra={"terminal_cause": CAUSE_STALL})
            return _finalize(
                spec_path, app_root, CAUSE_STALL, iteration,
                coverage, verdicts, cumulative_cost,
            )

        # ---- cumulative budget (FR-5) ----
        if max_cost_usd is not None and cumulative_cost >= max_cost_usd:
            logger.warning(
                "cumulative budget reached: $%.4f >= $%.4f",
                cumulative_cost, max_cost_usd,
                extra={"terminal_cause": CAUSE_BUDGET},
            )
            return _finalize(
                spec_path, app_root, CAUSE_BUDGET, iteration,
                coverage, verdicts, cumulative_cost,
            )

        # ---- build the structured feedback for the next generation pass (FR-4) ----
        feedback = build_feedback(verdicts, fr_intent)

    # Exhausted the iteration cap without a pass (FR-5).
    logger.warning("max iterations reached", extra={"terminal_cause": CAUSE_MAX_ITERATIONS})
    return _finalize(
        spec_path, app_root, CAUSE_MAX_ITERATIONS, max_iterations,
        coverage, verdicts, cumulative_cost,
    )


def _finalize(
    spec_path: Path,
    app_root: Path,
    cause: str,
    iterations: int,
    coverage: CoverageReport,
    verdicts: List[OracleVerdict],
    cost: float,
) -> OracleReport:
    status = STATUS_FITNESS_PASSED if cause == CAUSE_PASS else STATUS_FITNESS_FAILED
    if cause == CAUSE_NO_FITNESS:
        status = STATUS_NO_FITNESS
    elif cause == CAUSE_DISABLED:
        status = CAUSE_DISABLED
    report = OracleReport(
        spec_path=str(spec_path),
        app_root=str(app_root),
        terminal_cause=cause,
        status=status,
        iterations=iterations,
        coverage=coverage,
        verdicts=verdicts,
        cumulative_cost_usd=cost,
        spec_satisfied=is_spec_satisfied(verdicts),
    )
    logger.info(
        "loop terminal cause=%s iterations=%d coverage=%.2f cost=$%.4f",
        cause, iterations, coverage.coverage, cost,
        extra={"terminal_cause": cause, "coverage": coverage.coverage},
    )
    return report


def _emit_iteration(
    iteration: int,
    coverage: CoverageReport,
    verdicts: List[OracleVerdict],
    prev_sigs: Optional[List[str]],
    cost: float,
) -> None:
    """FR-10: one structured telemetry record per iteration via ``get_logger`` (not logging.getLogger)."""
    cur = set(_failure_multiset(verdicts))
    prev = set(prev_sigs or [])
    logger.info(
        "oracle_loop iteration",
        extra={
            "iteration": iteration,
            "coverage": coverage.coverage,
            "runnable_frs": coverage.runnable_frs,
            "total_frs": coverage.total_frs,
            "failing_count": len(cur),
            "verdict_deltas": {
                "newly_failing": sorted(cur - prev),
                "newly_passing": sorted(prev - cur),
            },
            "cumulative_cost_usd": cost,
        },
    )


def exit_code_for_cause(cause: str) -> int:
    """FR-8: 0 iff ``pass``; non-zero for every fail-closed terminal cause."""
    return 0 if cause == CAUSE_PASS else _NONZERO
