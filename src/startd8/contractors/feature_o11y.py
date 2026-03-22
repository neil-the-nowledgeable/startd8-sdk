"""Feature Observability — real-time progress indication for Prime Contractor.

Provides callback-driven status reporting at two tiers:

- **T1 (default):** One-line status per feature — works in all environments
  (CI, pipes, terminals). No dependencies beyond stdlib.
- **T2 (opt-in):** Rich live progress display with ETA, cost accumulator,
  and feature table. Requires Rich and a terminal.

Usage in run_prime_workflow.py::

    from startd8.contractors.feature_o11y import FeatureObserver

    observer = FeatureObserver(total_features=len(added))
    workflow = PrimeContractorWorkflow(
        ...,
        on_feature_complete=observer.on_feature_complete,
    )
    result = workflow.run(...)
    observer.print_summary()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from ..logging_config import get_logger

logger = get_logger(__name__)

# Status icons (match queue.py conventions)
_ICONS = {
    True: "\u2713",   # ✓
    False: "\u2717",  # ✗
    "skip": "\u2014", # —
    "review_pass": "\u25cf",  # ●
    "review_fail": "\u25cb",  # ○
    "gate_fired": "\u21bb",   # ↻
}


@dataclass
class FeatureSignal:
    """Captured signal from a completed feature."""

    name: str
    feature_id: str
    success: bool
    cost_usd: float = 0.0
    review_score: Optional[int] = None
    review_verdict: Optional[str] = None
    disk_quality_score: Optional[float] = None
    gate_fired: bool = False
    elapsed_s: float = 0.0


class FeatureObserver:
    """Observes Prime Contractor feature processing and emits progress signals.

    T1 mode (default): Prints a one-line status per feature to stdout.
    T2 mode (progress=True): Rich live display (if Rich is available).
    """

    def __init__(
        self,
        total_features: int = 0,
        *,
        progress: bool = False,
        quiet: bool = False,
    ) -> None:
        self.total_features = total_features
        self._quiet = quiet
        self._signals: list[FeatureSignal] = []
        self._start_time = time.monotonic()
        self._feature_start: float = 0.0
        self._cumulative_cost: float = 0.0

        # T2: Rich progress (lazy init)
        self._use_rich = progress
        self._rich_progress: Any = None
        self._rich_task: Any = None
        if self._use_rich:
            self._init_rich_progress()

    # ------------------------------------------------------------------
    # Callbacks (wire into PrimeContractor)
    # ------------------------------------------------------------------

    def on_feature_start(self, feature: Any) -> None:
        """Called before feature processing begins (optional pre-hook)."""
        self._feature_start = time.monotonic()
        if self._use_rich and self._rich_progress is not None:
            name = getattr(feature, "name", str(getattr(feature, "id", "?")))
            self._rich_progress.update(
                self._rich_task,
                description=f"[bold]{name}[/bold]",
            )

    def on_feature_complete(self, feature: Any) -> None:
        """Primary callback — wired to PrimeContractor.on_feature_complete."""
        now = time.monotonic()
        # If on_feature_start was called, use that. Otherwise measure since
        # last completion (or workflow start).
        ref = self._feature_start if self._feature_start else (
            self._last_complete if hasattr(self, "_last_complete") else self._start_time
        )
        elapsed = now - ref
        self._last_complete = now
        signal = self._extract_signal(feature, elapsed)
        self._signals.append(signal)
        self._cumulative_cost += signal.cost_usd

        if self._use_rich and self._rich_progress is not None:
            self._update_rich(signal)
        elif not self._quiet:
            self._print_status_line(signal)

    # ------------------------------------------------------------------
    # T1: One-line status output
    # ------------------------------------------------------------------

    def _print_status_line(self, signal: FeatureSignal) -> None:
        """Print a single-line feature status update."""
        n = len(self._signals)
        total = self.total_features or "?"
        icon = _ICONS[signal.success]

        # Build status fragments
        parts = [
            f"[{n}/{total}]",
            icon,
            signal.name,
        ]

        # Cost
        parts.append(f"${signal.cost_usd:.4f}")

        # Review verdict (if available)
        if signal.review_verdict:
            rv_icon = _ICONS.get(
                "review_pass" if signal.review_verdict == "PASS" else "review_fail",
                "",
            )
            score_str = f"{signal.review_score}" if signal.review_score is not None else "?"
            parts.append(f"review:{rv_icon}{score_str}")

        # Quality gate
        if signal.gate_fired:
            parts.append(f"{_ICONS['gate_fired']}gate")

        # Disk quality
        if signal.disk_quality_score is not None:
            parts.append(f"dq:{signal.disk_quality_score:.2f}")

        # Elapsed
        parts.append(f"{signal.elapsed_s:.1f}s")

        # Running total
        parts.append(f"(total:${self._cumulative_cost:.4f})")

        print(f"  {' '.join(parts)}")

    # ------------------------------------------------------------------
    # T2: Rich live progress
    # ------------------------------------------------------------------

    def _init_rich_progress(self) -> None:
        """Initialize Rich progress display."""
        try:
            from rich.progress import (
                BarColumn,
                MofNCompleteColumn,
                Progress,
                SpinnerColumn,
                TextColumn,
                TimeElapsedColumn,
                TimeRemainingColumn,
            )

            self._rich_progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]Feature O11y[/bold blue]"),
                BarColumn(),
                MofNCompleteColumn(),
                TextColumn("[green]${task.fields[cost]:.4f}[/green]"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                expand=False,
            )
            self._rich_task = self._rich_progress.add_task(
                "Processing features",
                total=self.total_features or None,
                cost=0.0,
            )
            self._rich_progress.start()
        except ImportError:
            logger.warning("Rich not available — falling back to T1 status lines")
            self._use_rich = False
            self._rich_progress = None

    def _update_rich(self, signal: FeatureSignal) -> None:
        """Update Rich progress after feature completion."""
        if self._rich_progress is None:
            return
        self._rich_progress.update(
            self._rich_task,
            advance=1,
            cost=self._cumulative_cost,
            description=f"[bold]{'✓' if signal.success else '✗'} {signal.name}[/bold]",
        )

    def stop(self) -> None:
        """Stop Rich progress display (call before printing summary)."""
        if self._rich_progress is not None:
            self._rich_progress.stop()

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Print a final feature o11y summary."""
        self.stop()
        if not self._signals:
            return

        elapsed_total = time.monotonic() - self._start_time
        succeeded = sum(1 for s in self._signals if s.success)
        failed = len(self._signals) - succeeded
        gate_fires = sum(1 for s in self._signals if s.gate_fired)

        review_scores = [s.review_score for s in self._signals if s.review_score is not None]
        avg_review = sum(review_scores) / len(review_scores) if review_scores else None

        dq_scores = [s.disk_quality_score for s in self._signals if s.disk_quality_score is not None]
        avg_dq = sum(dq_scores) / len(dq_scores) if dq_scores else None

        print(f"\n{'─' * 60}")
        print("Feature O11y Summary")
        print(f"{'─' * 60}")
        print(f"  Features:    {succeeded} succeeded, {failed} failed ({len(self._signals)} total)")
        print(f"  Cost:        ${self._cumulative_cost:.4f}")
        print(f"  Elapsed:     {elapsed_total:.1f}s ({elapsed_total / max(len(self._signals), 1):.1f}s/feature)")
        if avg_review is not None:
            print(f"  Avg review:  {avg_review:.0f}/100")
        if avg_dq is not None:
            print(f"  Avg disk Qlty: {avg_dq:.2f}")
        if gate_fires:
            print(f"  Gate fires:  {gate_fires}")
        print(f"{'─' * 60}\n")

    # ------------------------------------------------------------------
    # Signal extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_signal(feature: Any, elapsed: float) -> FeatureSignal:
        """Extract observable signals from a completed feature."""
        meta = getattr(feature, "metadata", None) or {}
        review = meta.get("review", {})
        status = getattr(feature, "status", None)

        # Determine success from status enum or metadata
        success = False
        if hasattr(status, "value"):
            success = status.value in ("complete", "completed")
        elif isinstance(status, str):
            success = status in ("complete", "completed")

        # Cost may be on the feature directly or in metadata
        cost = getattr(feature, "_cost_usd", None)
        if cost is None:
            cost = meta.get("_cost_usd", 0.0)

        return FeatureSignal(
            name=getattr(feature, "name", str(getattr(feature, "id", "?"))),
            feature_id=str(getattr(feature, "id", "")),
            success=success,
            cost_usd=cost or 0.0,
            review_score=review.get("score"),
            review_verdict=review.get("verdict"),
            disk_quality_score=meta.get("disk_quality_score"),
            gate_fired=bool(meta.get("_redrafted")),
            elapsed_s=elapsed,
        )
