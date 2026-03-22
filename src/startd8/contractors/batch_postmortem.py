"""Batch-Aware Cross-Run Post-Mortem Analysis.

Accumulates per-task results across multiple PrimeContractor runs sharing
the same seed file (a "batch"). Produces cumulative analysis including:
- Progression tracking across runs
- Persistent failure identification
- Force-regeneration detection
- Cumulative cost and velocity estimates

The batch layer sits alongside the existing single-run postmortem — it does
not replace it.

Batch identity: SHA256 of the seed file contents. Same seed = same batch.
Changed seed = new batch. --fresh = new batch (ledger deleted upstream).
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from startd8.logging_config import get_logger
from startd8.utils.trend_math import linear_slope as _linear_slope

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class TaskRunEntry:
    """One attempt at a task within a single run."""

    run_id: str
    timestamp: str
    verdict: str  # PASS / FAIL / PARTIAL
    cost_usd: float = 0.0
    root_cause: str = ""
    pipeline_stage: str = ""
    force_regenerated: bool = False
    error_message: str = ""


@dataclasses.dataclass
class TaskLedgerRecord:
    """Cumulative record for one task across all runs in a batch."""

    task_id: str
    task_name: str
    history: List[TaskRunEntry] = dataclasses.field(default_factory=list)
    current_status: str = "pending"  # pending / passed / failed


@dataclasses.dataclass
class RunSnapshot:
    """Per-run summary within a batch."""

    run_id: str
    timestamp: str
    tasks_attempted: int = 0
    tasks_passed: int = 0
    tasks_failed: int = 0
    cumulative_passed: int = 0
    remaining: int = 0
    force_regenerated_count: int = 0
    cost_usd: float = 0.0


@dataclasses.dataclass
class BatchLedger:
    """Top-level batch ledger accumulating results across runs."""

    batch_id: str
    seed_path: str
    seed_checksum: str
    total_tasks: int
    created_at: str
    updated_at: str
    tasks: Dict[str, TaskLedgerRecord] = dataclasses.field(default_factory=dict)
    runs: List[RunSnapshot] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class PersistentFailure:
    """A task that failed in two or more runs."""

    task_id: str
    failure_count: int
    root_causes: List[str] = dataclasses.field(default_factory=list)
    resolved_in_run: str = ""


@dataclasses.dataclass
class CumulativeCostSummary:
    """Cost aggregation across all runs in a batch."""

    total_usd: float = 0.0
    per_task_avg_usd: float = 0.0
    retry_cost_usd: float = 0.0
    retry_cost_fraction: float = 0.0


@dataclasses.dataclass
class VelocityEstimate:
    """Velocity metrics for batch progression."""

    tasks_per_run_avg: float = 0.0
    estimated_runs_remaining: int = 0
    trend: str = "stable"  # accelerating / decelerating / stable


@dataclasses.dataclass
class BatchPostMortemReport:
    """Top-level batch post-mortem report."""

    batch_id: str
    total_tasks: int
    runs_completed: int
    cumulative_passed: int = 0
    remaining: int = 0
    batch_verdict: str = "IN_PROGRESS"  # COMPLETE / IN_PROGRESS / STALLED
    progression: List[RunSnapshot] = dataclasses.field(default_factory=list)
    persistent_failures: List[PersistentFailure] = dataclasses.field(
        default_factory=list
    )
    newly_resolved: List[str] = dataclasses.field(default_factory=list)
    force_regenerated: List[str] = dataclasses.field(default_factory=list)
    cumulative_cost: Optional[CumulativeCostSummary] = None
    velocity: Optional[VelocityEstimate] = None


# ---------------------------------------------------------------------------
# Ledger CRUD
# ---------------------------------------------------------------------------


def compute_seed_checksum(seed_path: str) -> str:
    """Compute SHA256 checksum of a seed file."""
    h = hashlib.sha256()
    with open(seed_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def derive_batch_id(checksum: str) -> str:
    """Derive a batch ID from a seed checksum."""
    return f"batch-{checksum[:12]}"


def load_or_create_ledger(
    ledger_path: str,
    seed_path: str,
    checksum: str,
    total_tasks: int,
) -> BatchLedger:
    """Load an existing ledger or create a new one.

    If the ledger exists but has a different seed checksum, a new ledger
    is created (the seed changed, so it's a new batch).
    """
    path = Path(ledger_path)
    now = datetime.datetime.now().isoformat()

    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            existing_checksum = data.get("seed_checksum", "")
            if existing_checksum == checksum:
                return _deserialize_ledger(data)
            logger.info(
                "Seed checksum changed (%s -> %s) — starting new batch",
                existing_checksum[:12],
                checksum[:12],
            )
        except (json.JSONDecodeError, OSError, KeyError):
            logger.warning("Failed to load existing ledger — creating new one")

    batch_id = derive_batch_id(checksum)
    return BatchLedger(
        batch_id=batch_id,
        seed_path=seed_path,
        seed_checksum=checksum,
        total_tasks=total_tasks,
        created_at=now,
        updated_at=now,
    )


def detect_force_regenerated(
    ledger: BatchLedger, current_run_feature_ids: Set[str]
) -> Set[str]:
    """Detect tasks that were force-regenerated.

    A task is force-regenerated if it PASSed in a prior run and appears
    in the current run's feature list.
    """
    force_regen: Set[str] = set()
    for task_id in current_run_feature_ids:
        record = ledger.tasks.get(task_id)
        if not record:
            continue
        # Check if any prior entry was a PASS
        for entry in record.history:
            if entry.verdict == "PASS":
                force_regen.add(task_id)
                break
    return force_regen


def append_run_to_ledger(
    ledger: BatchLedger,
    run_id: str,
    timestamp: str,
    per_feature_results: Dict[str, Dict[str, Any]],
    queue_state: Dict[str, Any],
    seed_tasks: Optional[List[Dict[str, Any]]] = None,
) -> BatchLedger:
    """Append a run's results to the batch ledger.

    Idempotent: if run_id already exists, it replaces the prior entry.

    Args:
        ledger: The batch ledger to update.
        run_id: Unique identifier for this run.
        timestamp: ISO timestamp of the run.
        per_feature_results: Map of feature_id -> result dict from history.
        queue_state: Serialized queue state {feature_id: feature_dict}.
        seed_tasks: Optional seed task list for name lookup.
    """
    # Build seed name lookup
    seed_name_lookup: Dict[str, str] = {}
    if seed_tasks:
        for task in seed_tasks:
            tid = task.get("task_id", task.get("id", ""))
            if tid:
                seed_name_lookup[tid] = task.get("title", task.get("name", tid))

    # Detect force-regenerated before appending
    current_ids = set(per_feature_results.keys())
    force_regen_ids = detect_force_regenerated(ledger, current_ids)

    # Remove prior entries for this run_id (idempotent)
    for record in ledger.tasks.values():
        record.history = [e for e in record.history if e.run_id != run_id]
    ledger.runs = [r for r in ledger.runs if r.run_id != run_id]

    # Append new entries
    run_cost = 0.0
    run_passed = 0
    run_failed = 0
    force_regen_count = 0

    for feature_id, result in per_feature_results.items():
        success = result.get("success", False)
        cost = result.get("cost_usd", 0.0) or 0.0
        error_msg = result.get("error", "") or ""
        root_cause = result.get("root_cause", "") or ""
        pipeline_stage = result.get("pipeline_stage", "") or ""
        is_force_regen = feature_id in force_regen_ids

        verdict = "PASS" if success else "FAIL"

        entry = TaskRunEntry(
            run_id=run_id,
            timestamp=timestamp,
            verdict=verdict,
            cost_usd=cost,
            root_cause=root_cause,
            pipeline_stage=pipeline_stage,
            force_regenerated=is_force_regen,
            error_message=error_msg,
        )

        if feature_id not in ledger.tasks:
            # Resolve name from queue_state or seed
            name = (
                queue_state.get(feature_id, {}).get("name", "")
                or seed_name_lookup.get(feature_id, feature_id)
            )
            ledger.tasks[feature_id] = TaskLedgerRecord(
                task_id=feature_id,
                task_name=name,
            )

        ledger.tasks[feature_id].history.append(entry)

        # Update current_status
        if success:
            ledger.tasks[feature_id].current_status = "passed"
            run_passed += 1
        else:
            # Only mark failed if not previously passed (unless force-regen)
            if ledger.tasks[feature_id].current_status != "passed" or is_force_regen:
                ledger.tasks[feature_id].current_status = "failed"
            run_failed += 1

        run_cost += cost
        if is_force_regen:
            force_regen_count += 1

    # Compute cumulative passed across all tasks
    cumulative_passed = sum(
        1 for r in ledger.tasks.values() if r.current_status == "passed"
    )
    remaining = ledger.total_tasks - cumulative_passed

    snapshot = RunSnapshot(
        run_id=run_id,
        timestamp=timestamp,
        tasks_attempted=len(per_feature_results),
        tasks_passed=run_passed,
        tasks_failed=run_failed,
        cumulative_passed=cumulative_passed,
        remaining=remaining,
        force_regenerated_count=force_regen_count,
        cost_usd=run_cost,
    )
    ledger.runs.append(snapshot)
    ledger.updated_at = timestamp

    return ledger


def save_ledger(ledger: BatchLedger, ledger_path: str) -> None:
    """Save the ledger to disk via atomic write (.tmp + rename)."""
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    data = _serialize_ledger(ledger)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)
    logger.info("Batch ledger saved: %s", path)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _serialize_ledger(ledger: BatchLedger) -> Dict[str, Any]:
    """Serialize a BatchLedger to a JSON-compatible dict."""
    return {
        "batch_id": ledger.batch_id,
        "seed_path": ledger.seed_path,
        "seed_checksum": ledger.seed_checksum,
        "total_tasks": ledger.total_tasks,
        "created_at": ledger.created_at,
        "updated_at": ledger.updated_at,
        "tasks": {
            tid: {
                "task_id": rec.task_id,
                "task_name": rec.task_name,
                "current_status": rec.current_status,
                "history": [dataclasses.asdict(e) for e in rec.history],
            }
            for tid, rec in ledger.tasks.items()
        },
        "runs": [dataclasses.asdict(r) for r in ledger.runs],
    }


def _deserialize_ledger(data: Dict[str, Any]) -> BatchLedger:
    """Deserialize a dict into a BatchLedger."""
    tasks: Dict[str, TaskLedgerRecord] = {}
    for tid, tdata in data.get("tasks", {}).items():
        history = [
            TaskRunEntry(**e) for e in tdata.get("history", [])
        ]
        tasks[tid] = TaskLedgerRecord(
            task_id=tdata.get("task_id", tid),
            task_name=tdata.get("task_name", tid),
            history=history,
            current_status=tdata.get("current_status", "pending"),
        )

    runs = [RunSnapshot(**r) for r in data.get("runs", [])]

    return BatchLedger(
        batch_id=data["batch_id"],
        seed_path=data.get("seed_path", ""),
        seed_checksum=data["seed_checksum"],
        total_tasks=data.get("total_tasks", 0),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
        tasks=tasks,
        runs=runs,
    )


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class BatchPostMortemEvaluator:
    """Evaluates a batch ledger to produce a cumulative post-mortem report."""

    def evaluate(self, ledger: BatchLedger) -> BatchPostMortemReport:
        """Produce a batch post-mortem report from the ledger."""
        cumulative_passed = sum(
            1 for r in ledger.tasks.values() if r.current_status == "passed"
        )
        remaining = ledger.total_tasks - cumulative_passed

        # Determine batch verdict
        if remaining == 0:
            batch_verdict = "COMPLETE"
        elif ledger.runs and ledger.runs[-1].tasks_passed == 0:
            batch_verdict = "STALLED"
        else:
            batch_verdict = "IN_PROGRESS"

        # Collect force-regenerated task IDs across all runs
        force_regen_ids: List[str] = []
        seen_force_regen: Set[str] = set()
        for record in ledger.tasks.values():
            for entry in record.history:
                if entry.force_regenerated and record.task_id not in seen_force_regen:
                    force_regen_ids.append(record.task_id)
                    seen_force_regen.add(record.task_id)

        current_run_id = ledger.runs[-1].run_id if ledger.runs else ""

        report = BatchPostMortemReport(
            batch_id=ledger.batch_id,
            total_tasks=ledger.total_tasks,
            runs_completed=len(ledger.runs),
            cumulative_passed=cumulative_passed,
            remaining=remaining,
            batch_verdict=batch_verdict,
            progression=list(ledger.runs),
            persistent_failures=self._identify_persistent_failures(ledger),
            newly_resolved=self._identify_newly_resolved(ledger, current_run_id),
            force_regenerated=force_regen_ids,
            cumulative_cost=self._compute_cumulative_cost(ledger),
            velocity=self._compute_velocity(ledger),
        )
        return report

    def _identify_persistent_failures(
        self, ledger: BatchLedger
    ) -> List[PersistentFailure]:
        """Identify tasks that failed in 2+ runs."""
        persistent: List[PersistentFailure] = []
        for record in ledger.tasks.values():
            fail_entries = [e for e in record.history if e.verdict == "FAIL"]
            if len(fail_entries) >= 2:
                root_causes = list(
                    dict.fromkeys(e.root_cause for e in fail_entries if e.root_cause)
                )
                # Check if eventually resolved
                resolved_in = ""
                if record.current_status == "passed":
                    pass_entries = [e for e in record.history if e.verdict == "PASS"]
                    if pass_entries:
                        resolved_in = pass_entries[-1].run_id

                persistent.append(PersistentFailure(
                    task_id=record.task_id,
                    failure_count=len(fail_entries),
                    root_causes=root_causes,
                    resolved_in_run=resolved_in,
                ))
        return persistent

    def _identify_newly_resolved(
        self, ledger: BatchLedger, current_run_id: str
    ) -> List[str]:
        """Identify tasks that failed previously but passed in the current run."""
        resolved: List[str] = []
        if not current_run_id:
            return resolved

        for record in ledger.tasks.values():
            current_entries = [
                e for e in record.history if e.run_id == current_run_id
            ]
            prior_entries = [
                e for e in record.history if e.run_id != current_run_id
            ]

            # Passed in current run and failed in at least one prior run
            if (
                any(e.verdict == "PASS" for e in current_entries)
                and any(e.verdict == "FAIL" for e in prior_entries)
            ):
                resolved.append(record.task_id)

        return resolved

    def _compute_velocity(self, ledger: BatchLedger) -> VelocityEstimate:
        """Compute velocity metrics from run progression."""
        if not ledger.runs:
            return VelocityEstimate()

        # New passes per run (not cumulative, just new)
        new_passes: List[int] = []
        prev_cumulative = 0
        for run in ledger.runs:
            new_in_run = run.cumulative_passed - prev_cumulative
            new_passes.append(max(new_in_run, 0))
            prev_cumulative = run.cumulative_passed

        avg = sum(new_passes) / len(new_passes) if new_passes else 0.0

        # Trend: compare last run to average
        trend = "stable"
        if len(new_passes) >= 2:
            last = new_passes[-1]
            if avg > 0:
                if last > avg * 1.2:
                    trend = "accelerating"
                elif last < avg * 0.8:
                    trend = "decelerating"

        # Estimated remaining runs
        remaining = ledger.total_tasks - (
            ledger.runs[-1].cumulative_passed if ledger.runs else 0
        )
        estimated_remaining = 0
        if avg > 0 and remaining > 0:
            estimated_remaining = max(1, int(remaining / avg + 0.5))

        return VelocityEstimate(
            tasks_per_run_avg=round(avg, 2),
            estimated_runs_remaining=estimated_remaining,
            trend=trend,
        )

    def _compute_cumulative_cost(self, ledger: BatchLedger) -> CumulativeCostSummary:
        """Compute cumulative cost across all runs."""
        total_usd = sum(r.cost_usd for r in ledger.runs)

        # Retry cost: cost of runs after the first attempt at each task
        # (tasks that appeared in multiple runs)
        task_first_cost: Dict[str, float] = {}
        task_total_cost: Dict[str, float] = {}
        for record in ledger.tasks.values():
            for entry in record.history:
                tid = record.task_id
                if tid not in task_first_cost:
                    task_first_cost[tid] = entry.cost_usd
                task_total_cost[tid] = task_total_cost.get(tid, 0.0) + entry.cost_usd

        retry_cost = sum(
            total - first
            for tid, total in task_total_cost.items()
            for first in [task_first_cost.get(tid, 0.0)]
            if total > first
        )

        tasks_with_cost = len([c for c in task_total_cost.values() if c > 0])

        return CumulativeCostSummary(
            total_usd=total_usd,
            per_task_avg_usd=total_usd / tasks_with_cost if tasks_with_cost else 0.0,
            retry_cost_usd=retry_cost,
            retry_cost_fraction=retry_cost / total_usd if total_usd > 0 else 0.0,
        )

    def render_markdown(self, report: BatchPostMortemReport) -> str:
        """Render the batch report as markdown."""
        lines = [
            "# Batch Post-Mortem Report",
            "",
            f"**Batch ID:** {report.batch_id}",
            f"**Verdict:** {report.batch_verdict}",
            f"**Progress:** {report.cumulative_passed}/{report.total_tasks} "
            f"({report.remaining} remaining)",
            f"**Runs completed:** {report.runs_completed}",
            "",
        ]

        # Progression table
        if report.progression:
            lines.extend([
                "## Progression",
                "",
                "| Run | Attempted | Passed | Failed | Cumulative | Remaining | Cost |",
                "|-----|-----------|--------|--------|------------|-----------|------|",
            ])
            for run in report.progression:
                lines.append(
                    f"| {run.run_id} | {run.tasks_attempted} | {run.tasks_passed} "
                    f"| {run.tasks_failed} | {run.cumulative_passed}/{report.total_tasks} "
                    f"| {run.remaining} | ${run.cost_usd:.4f} |"
                )
            lines.append("")

        # Persistent failures
        if report.persistent_failures:
            lines.extend(["## Persistent Failures", ""])
            for pf in report.persistent_failures:
                resolved = (
                    f" (resolved in {pf.resolved_in_run})" if pf.resolved_in_run else ""
                )
                causes = ", ".join(pf.root_causes) if pf.root_causes else "unknown"
                lines.append(
                    f"- **{pf.task_id}**: failed {pf.failure_count}x "
                    f"(causes: {causes}){resolved}"
                )
            lines.append("")

        # Newly resolved
        if report.newly_resolved:
            lines.extend(["## Newly Resolved", ""])
            for tid in report.newly_resolved:
                lines.append(f"- {tid}")
            lines.append("")

        # Force regenerated
        if report.force_regenerated:
            lines.extend(["## Force Regenerated", ""])
            for tid in report.force_regenerated:
                lines.append(f"- {tid}")
            lines.append("")

        # Velocity
        if report.velocity:
            v = report.velocity
            lines.extend([
                "## Velocity",
                "",
                f"- Tasks per run (avg): {v.tasks_per_run_avg}",
                f"- Estimated runs remaining: {v.estimated_runs_remaining}",
                f"- Trend: {v.trend}",
                "",
            ])

        # Cost
        if report.cumulative_cost:
            c = report.cumulative_cost
            lines.extend([
                "## Cumulative Cost",
                "",
                f"- Total: ${c.total_usd:.4f}",
                f"- Per task (avg): ${c.per_task_avg_usd:.4f}",
                f"- Retry cost: ${c.retry_cost_usd:.4f} "
                f"({c.retry_cost_fraction:.1%} of total)",
                "",
            ])

        return "\n".join(lines)

    def build_security_section(
        self,
        output_dir: str,
        archived_run_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build batch-level security section from archived run metrics.

        Reads ``kaizen-metrics.json`` security keys from each archived run
        to track aggregate score trajectory and consecutive injection runs.

        Args:
            output_dir: Current run output directory.
            archived_run_dirs: List of archived run directories (oldest first).

        Returns:
            Dict with aggregate_score_trajectory, consecutive_injection_runs,
            and latest metrics.
        """
        run_dirs = archived_run_dirs or []
        # Include current run
        all_dirs = run_dirs + [output_dir]

        scores: List[float] = []
        consecutive_injection_max = 0

        for rdir in all_dirs:
            metrics_path = Path(rdir) / "kaizen-metrics.json"
            if not metrics_path.is_file():
                continue
            try:
                data = json.loads(metrics_path.read_text())
                sec = data.get("security", {})
                agg = sec.get("aggregate_score", 1.0)
                scores.append(agg)
                consec = sec.get("consecutive_injection_runs", 0)
                if consec > consecutive_injection_max:
                    consecutive_injection_max = consec
            except (json.JSONDecodeError, OSError):
                continue

        return {
            "aggregate_score_trajectory": [round(s, 4) for s in scores],
            "consecutive_injection_runs_max": consecutive_injection_max,
            "runs_with_security_data": len(scores),
        }

    def build_observability_section(
        self,
        output_dir: str,
        archived_run_dirs: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Build batch-level observability artifact section (REQ-KZ-OBS-601).

        Reads ``kaizen-metrics.json`` observability_artifacts keys from each
        archived run to track per-type score trajectories and phantom ratios.

        Args:
            output_dir: Current run output directory.
            archived_run_dirs: List of archived run directories (oldest first).

        Returns:
            Dict with per-type score trajectories, composite slope, and
            phantom service tracking.
        """
        run_dirs = (archived_run_dirs or []) + [output_dir]

        composite_scores: List[float] = []
        dashboard_scores: List[float] = []
        alert_scores: List[float] = []
        slo_scores: List[float] = []
        phantom_ratios: List[float] = []

        for rdir in run_dirs:
            metrics_path = Path(rdir) / "kaizen-metrics.json"
            if not metrics_path.is_file():
                continue
            try:
                data = json.loads(metrics_path.read_text())
                obs = data.get("observability_artifacts")
                if not obs:
                    continue
                composite_scores.append(obs.get("avg_composite_score", 0.0))
                dashboard_scores.append(obs.get("avg_dashboard_spec_score", 0.0))
                alert_scores.append(obs.get("avg_alert_rule_score", 0.0))
                slo_scores.append(obs.get("avg_slo_definition_score", 0.0))
                # Phantom ratio: phantom_detected / services_evaluated
                evaluated = obs.get("services_evaluated", 0)
                phantom = obs.get("phantom_services_detected", 0)
                if evaluated > 0:
                    phantom_ratios.append(phantom / evaluated)
                else:
                    phantom_ratios.append(0.0)
            except (json.JSONDecodeError, OSError):
                continue

        result: Dict[str, Any] = {
            "runs_with_observability_data": len(composite_scores),
        }

        if len(composite_scores) >= 2:
            result["avg_composite_slope"] = round(
                _linear_slope(composite_scores) or 0.0, 4
            )
            result["avg_dashboard_slope"] = round(
                _linear_slope(dashboard_scores) or 0.0, 4
            )
            result["avg_alert_slope"] = round(
                _linear_slope(alert_scores) or 0.0, 4
            )
            result["avg_slo_slope"] = round(
                _linear_slope(slo_scores) or 0.0, 4
            )
        if phantom_ratios:
            result["phantom_ratio_slope"] = round(
                (_linear_slope(phantom_ratios) or 0.0), 4
            ) if len(phantom_ratios) >= 2 else 0.0
            result["phantom_services_per_run"] = [
                round(r, 4) for r in phantom_ratios
            ]
            result["phantom_services_resolved"] = (
                len(phantom_ratios) >= 2
                and phantom_ratios[-1] == 0.0
                and any(r > 0 for r in phantom_ratios[:-1])
            )
        if composite_scores:
            result["red_coverage_improving"] = (
                len(dashboard_scores) >= 2
                and dashboard_scores[-1] > dashboard_scores[0]
            )
            result["composite_trajectory"] = [
                round(s, 4) for s in composite_scores
            ]

        return result

    def write_outputs(
        self, report: BatchPostMortemReport, output_dir: str
    ) -> None:
        """Write batch post-mortem outputs to disk."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON report
        report_path = out / "batch-postmortem-report.json"
        report_dict = dataclasses.asdict(report)

        # Add security section if data available
        try:
            sec_section = self.build_security_section(output_dir)
            if sec_section.get("runs_with_security_data", 0) > 0:
                report_dict["security"] = sec_section
        except Exception:
            logger.debug("Batch security section skipped", exc_info=True)

        # Add observability section if data available (REQ-KZ-OBS-601)
        try:
            obs_section = self.build_observability_section(output_dir)
            if obs_section.get("runs_with_observability_data", 0) > 0:
                report_dict["observability_trend"] = obs_section
        except Exception:
            logger.debug("Batch observability section skipped", exc_info=True)

        report_json = json.dumps(report_dict, indent=2, default=str)
        report_path.write_text(report_json, encoding="utf-8")
        logger.info("Batch post-mortem report: %s", report_path)

        # Markdown summary
        md_path = out / "batch-postmortem-summary.md"
        md_content = self.render_markdown(report)
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Batch post-mortem summary: %s", md_path)
