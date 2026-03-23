#!/usr/bin/env python3
"""Standalone Prime Contractor Post-Mortem Runner.

Produces a structured post-mortem report from PrimeContractor run artifacts.

Usage:
    # Auto-discover from run directory:
    python3 scripts/run_prime_postmortem.py \\
        --run-dir .cap-dev-pipe/pipeline-output/my-project/run-003/plan-ingestion

    # Explicit paths:
    python3 scripts/run_prime_postmortem.py \\
        --result prime-result.json \\
        --seed prime-context-seed-enriched.json \\
        --queue-state .prime_contractor_state.json \\
        --output-dir ./postmortem-output
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Add src/ to path for SDK imports
_SCRIPT_DIR = Path(__file__).resolve().parent
_SDK_SRC = _SCRIPT_DIR.parent / "src"
if _SDK_SRC.is_dir():
    sys.path.insert(0, str(_SDK_SRC))

from startd8.contractors.prime_postmortem import (
    CAUSE_TO_SUGGESTION,
    PrimePostMortemEvaluator,
    generate_kaizen_suggestions,
)
from startd8.contractors.batch_postmortem import (
    BatchPostMortemEvaluator,
    append_run_to_ledger,
    compute_seed_checksum,
    derive_batch_id,
    load_or_create_ledger,
    save_ledger,
)


def _discover_artifacts(run_dir: Path) -> dict:
    """Auto-discover postmortem input files from a run directory.

    Looks for:
    - prime-result*.json (the run result)
    - prime-context-seed-enriched.json or prime-context-seed.json (the seed)
    - .prime_contractor_state.json in PROJECT_ROOT (queue state)

    Returns:
        Dict with 'result', 'seed', 'queue_state' paths (or None if not found).
    """
    artifacts: dict = {"result": None, "seed": None, "queue_state": None}

    # Result file — try specific patterns
    for pattern in ["prime-result.json", "prime-result-*.json"]:
        matches = sorted(run_dir.glob(pattern))
        if matches:
            artifacts["result"] = matches[-1]  # Latest
            break

    # Seed file
    for name in [
        "prime-context-seed-enriched.json",
        "prime-context-seed.json",
    ]:
        candidate = run_dir / name
        if candidate.is_file():
            artifacts["seed"] = candidate
            break

    # Queue state — walk up to find PROJECT_ROOT
    search = run_dir
    for _ in range(8):  # Limit depth
        candidate = search / ".prime_contractor_state.json"
        if candidate.is_file():
            artifacts["queue_state"] = candidate
            break
        search = search.parent

    return artifacts


def _reconstruct_queue_state(result_dict: dict) -> dict:
    """Reconstruct minimal queue state from result history.

    When .prime_contractor_state.json is unavailable, build a minimal
    feature dict from the result's history entries.
    """
    queue_state: dict = {}
    for entry in result_dict.get("history", []):
        fid = entry.get("feature_id", "")
        if not fid:
            continue
        queue_state[fid] = {
            "id": fid,
            "name": entry.get("feature_name", fid),
            "status": "complete" if entry.get("success") else "failed",
            "error_message": entry.get("error", ""),
            "target_files": entry.get("target_files", []),
            # History entries use "files" for generated output paths;
            # prefer explicit "generated_files" but fall back to "files".
            "generated_files": entry.get("generated_files") or entry.get("files", []),
        }
    return queue_state


def main():
    parser = argparse.ArgumentParser(
        description="Run post-mortem analysis on PrimeContractor results."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        help="Run directory for auto-discovery of artifacts.",
    )
    parser.add_argument("--result", type=Path, help="Path to prime-result JSON.")
    parser.add_argument("--seed", type=Path, help="Path to seed JSON.")
    parser.add_argument("--queue-state", type=Path, help="Path to queue state JSON.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Output directory for report files.",
    )
    parser.add_argument(
        "--emit-metrics",
        action="store_true",
        help="Write kaizen-metrics.json alongside postmortem report (REQ-KZ-300).",
    )
    parser.add_argument(
        "--emit-suggestions",
        action="store_true",
        help="Write kaizen-suggestions.json alongside postmortem report (REQ-KZ-501).",
    )
    parser.add_argument(
        "--update-index",
        action="store_true",
        help="Append run to kaizen-index.json and prune old entries (REQ-KZ-301).",
    )
    parser.add_argument(
        "--kaizen-keep",
        type=int,
        default=20,
        help="Max runs to retain in kaizen index (default: 20, range: 5-200).",
    )
    parser.add_argument(
        "--seed-path",
        type=Path,
        help="Seed file path for batch identity (SHA256 of contents).",
    )
    parser.add_argument(
        "--batch-ledger-dir",
        type=Path,
        help="Directory for batch-ledger.json (default: auto-resolve pipeline base).",
    )
    parser.add_argument(
        "--skip-batch",
        action="store_true",
        help="Skip batch post-mortem analysis.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory for disk quality validation (Phase B/E).",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help=(
            "Explicit run ID (preferred). If provided, skips auto-resolution "
            "from run-metadata.json / env vars / directory names (F-AC-05)."
        ),
    )
    args = parser.parse_args()

    # Discover or use explicit paths
    if args.run_dir:
        discovered = _discover_artifacts(args.run_dir)
        result_path = args.result or discovered["result"]
        seed_path = args.seed or discovered["seed"]
        queue_state_path = args.queue_state or discovered["queue_state"]
    else:
        result_path = args.result
        seed_path = args.seed
        queue_state_path = args.queue_state

    if not result_path or not result_path.is_file():
        print("ERROR: No result file found. Use --result or --run-dir.", file=sys.stderr)
        sys.exit(1)

    # Load artifacts
    result_dict = json.loads(result_path.read_text(encoding="utf-8"))

    seed_tasks = None
    if seed_path and seed_path.is_file():
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
        seed_tasks = seed_data.get("tasks", [])

    queue_state: dict = {}
    if queue_state_path and queue_state_path.is_file():
        queue_state = json.loads(queue_state_path.read_text(encoding="utf-8"))
        # Handle wrapped format: {"features": {...}, "order": [...]}
        if "features" in queue_state and "order" in queue_state:
            queue_state = queue_state["features"]
    else:
        print("INFO: No queue state file — reconstructing from result history.")
        queue_state = _reconstruct_queue_state(result_dict)

    # Default output to run-dir if not specified
    output_dir = args.output_dir
    if args.run_dir and output_dir == Path("."):
        output_dir = args.run_dir

    # Evaluate
    evaluator = PrimePostMortemEvaluator()
    project_root = str(args.project_root) if args.project_root else None
    report = evaluator.evaluate(
        result_dict=result_dict,
        queue_state=queue_state,
        seed_tasks=seed_tasks,
        output_dir=str(output_dir),
        project_root=project_root,
    )

    # Resolve run ID once, pass through to all helpers (F-AC-05)
    run_id = _resolve_run_id(output_dir, explicit_id=args.run_id)

    if args.emit_metrics:
        _emit_kaizen_metrics(report, output_dir, run_id=run_id)

    if args.emit_suggestions:
        _emit_kaizen_suggestions(report, output_dir, run_id=run_id)

    if args.update_index:
        _update_kaizen_index(output_dir, keep=args.kaizen_keep, run_id=run_id)

    # -----------------------------------------------------------------------
    # Batch post-mortem analysis
    # -----------------------------------------------------------------------
    if not args.skip_batch and args.seed_path and args.seed_path.is_file():
        try:
            _run_batch_postmortem(
                seed_path=args.seed_path,
                result_dict=result_dict,
                queue_state=queue_state,
                seed_tasks=seed_tasks,
                output_dir=output_dir,
                batch_ledger_dir=args.batch_ledger_dir,
                run_id=run_id,
            )
        except Exception as exc:
            print(f"  Batch post-mortem failed (non-fatal): {exc}", file=sys.stderr)

    # Print summary
    print()
    print("=" * 60)
    print("PRIME CONTRACTOR POST-MORTEM")
    print("=" * 60)
    print(f"  Score:    {report.aggregate_score:.2f}")
    print(f"  Verdict:  {report.aggregate_verdict}")
    print(f"  Features: {report.successful_features}/{report.total_features} passed")
    if report.failed_features:
        print(f"  Failed:   {report.failed_features}")
    if report.cross_feature_patterns:
        print(f"  Patterns: {len(report.cross_feature_patterns)}")
    if report.lessons:
        print(f"  Lessons:  {len(report.lessons)}")
    if report.cost_summary:
        print(f"  Cost:     ${report.cost_summary.total_usd:.4f}")
    print()
    print(f"  Report:   {output_dir}/prime-postmortem-report.json")
    print(f"  Summary:  {output_dir}/prime-postmortem-summary.md")
    print()


# ---------------------------------------------------------------------------
# Batch post-mortem
# ---------------------------------------------------------------------------


def _run_batch_postmortem(
    seed_path: Path,
    result_dict: dict,
    queue_state: dict,
    seed_tasks: list | None,
    output_dir: Path,
    batch_ledger_dir: Path | None,
    run_id: str | None = None,
) -> None:
    """Run batch-aware cross-run post-mortem analysis."""
    # 1. Compute batch identity
    checksum = compute_seed_checksum(str(seed_path))
    batch_id = derive_batch_id(checksum)

    # 2. Resolve ledger directory
    if batch_ledger_dir:
        ledger_dir = batch_ledger_dir
    else:
        ledger_dir = _resolve_pipeline_base(output_dir)
    ledger_path = str(ledger_dir / "batch-ledger.json")

    # 3. Determine total tasks from seed
    total_tasks = 0
    if seed_tasks:
        total_tasks = len(seed_tasks)
    else:
        try:
            seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
            total_tasks = len(seed_data.get("tasks", []))
        except (json.JSONDecodeError, OSError):
            pass

    # 4. Load or create ledger
    ledger = load_or_create_ledger(ledger_path, str(seed_path), checksum, total_tasks)

    # 5. Build per-feature results from history
    per_feature_results: dict = {}
    for entry in result_dict.get("history", []):
        fid = entry.get("feature_id", "")
        if fid:
            per_feature_results[fid] = entry

    if not per_feature_results:
        print("  Batch post-mortem: no features to record — skipping.")
        return

    # 6. Append current run (F-AC-05: use pre-resolved run_id)
    run_id = run_id or _resolve_run_id(output_dir)
    import datetime
    timestamp = datetime.datetime.now().isoformat()

    ledger = append_run_to_ledger(
        ledger, run_id, timestamp, per_feature_results, queue_state, seed_tasks
    )

    # 7. Save ledger
    save_ledger(ledger, ledger_path)

    # 8. Evaluate batch post-mortem
    evaluator = BatchPostMortemEvaluator()
    report = evaluator.evaluate(ledger)

    # 9. Write batch outputs
    evaluator.write_outputs(report, str(output_dir))

    # 10. Print batch summary
    print()
    print("  Batch Post-Mortem:")
    print(f"    Batch ID:    {report.batch_id}")
    print(f"    Verdict:     {report.batch_verdict}")
    print(
        f"    Progress:    {report.cumulative_passed}/{report.total_tasks} "
        f"({report.remaining} remaining)"
    )
    print(f"    Runs:        {report.runs_completed}")
    if report.persistent_failures:
        print(f"    Persistent:  {len(report.persistent_failures)} task(s)")
    if report.newly_resolved:
        print(f"    Resolved:    {len(report.newly_resolved)} task(s) this run")
    if report.force_regenerated:
        print(f"    Force-regen: {len(report.force_regenerated)} task(s)")
    if report.velocity:
        print(
            f"    Velocity:    {report.velocity.tasks_per_run_avg} tasks/run "
            f"({report.velocity.trend})"
        )
    if report.cumulative_cost:
        print(f"    Total cost:  ${report.cumulative_cost.total_usd:.4f}")
    print(f"    Ledger:      {ledger_path}")
    print()


# ---------------------------------------------------------------------------
# Kaizen: Metrics emission (REQ-KZ-300)
# ---------------------------------------------------------------------------

# _CAUSE_TO_SUGGESTION is now imported from startd8.contractors.prime_postmortem
# as CAUSE_TO_SUGGESTION.  Local alias for backward compatibility.
_CAUSE_TO_SUGGESTION = CAUSE_TO_SUGGESTION


def _extract_top_root_causes(report: object) -> list:
    """Aggregate root causes from pipeline_attribution stages."""
    cause_counts: dict[str, int] = {}
    attribution = getattr(report, "pipeline_attribution", None) or []
    for attr in attribution:
        root_causes = getattr(attr, "root_causes", {}) or {}
        for cause, count in root_causes.items():
            cause_counts[cause] = cause_counts.get(cause, 0) + count
    return [
        {"cause": cause, "count": count}
        for cause, count in sorted(cause_counts.items(), key=lambda x: -x[1])[:5]
    ]


def _resolve_run_id(output_dir: Path, explicit_id: str | None = None) -> str:
    """Derive the run ID, preferring an explicit value when provided.

    Resolution order (F-AC-05: single authoritative source preferred):
    1. explicit_id (from --run-id CLI arg) — highest priority
    2. run-metadata.json in the run directory
    3. KAIZEN_RUN_ID env var (legacy fallback)
    4. Parent directory name (last resort)
    """
    if explicit_id:
        return explicit_id

    # run-metadata.json (authoritative file-based source)
    for parent in [output_dir, output_dir.parent]:
        meta_path = parent / "run-metadata.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                rid = meta.get("run_id", "")
                if rid:
                    return rid
            except (json.JSONDecodeError, OSError):
                pass

    # Legacy env var fallback (cap-dev-pipe sets this)
    env_id = os.environ.get("KAIZEN_RUN_ID", "")
    if env_id and env_id != "latest":
        return env_id

    # Last resort: directory name
    for parent in [output_dir.parent, output_dir]:
        name = parent.name
        if name.startswith("run-"):
            return name

    return "unknown"


def _resolve_pipeline_base(output_dir: Path) -> Path:
    """Find the pipeline-output project directory (parent of run-XXX dirs).

    Walks up from output_dir looking for the directory that contains run-* subdirs.
    """
    for parent in [output_dir.parent, output_dir.parent.parent, output_dir]:
        if parent.name.startswith("run-"):
            return parent.parent
        # Check if parent contains run-* dirs
        if any(d.name.startswith("run-") for d in parent.iterdir() if d.is_dir()):
            return parent
    return output_dir.parent


def _collect_todo_metrics(output_dir: Path, report: object) -> dict:
    """Collect TODO completion metrics for kaizen-metrics.json (REQ-TCW-401).

    Reads the instrumentation inventory and result files produced by the
    TODO completion workflow (v2 subprocess or v3 in-band) and returns
    metrics for inclusion in kaizen-metrics.json.
    """
    instr_dir = output_dir / "instrumentation"
    inventory_path = instr_dir / "todo-inventory.json"
    result_path = instr_dir / "instrumentation-result.json"

    if not inventory_path.exists():
        return {}

    try:
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        summary = inventory.get("summary", {})
        total = summary.get("total", 0)

        metrics: dict = {
            "todo_count": total,
            "todo_count_a": summary.get("A", 0),
            "todo_count_b": summary.get("B", 0),
            "todo_count_c": summary.get("C", 0),
            "todo_security_count": summary.get("security_todos", 0),
        }

        if result_path.exists():
            result = json.loads(result_path.read_text(encoding="utf-8"))
            completed = result.get("todo_completed", 0)
            metrics["todo_completed"] = completed
            metrics["todo_deferred"] = result.get("todo_deferred", total)
            metrics["todo_completion_rate"] = (
                round(completed / total * 100, 2) if total > 0 else 0.0
            )
            metrics["todo_executed"] = result.get("executed", False)
        else:
            metrics["todo_completed"] = 0
            metrics["todo_deferred"] = total
            metrics["todo_completion_rate"] = 0.0

        # Also count TODOs detected in per-feature postmortem data
        feature_todo_total = 0
        for fpm in getattr(report, "features", []):
            feature_todo_total += (
                getattr(fpm, "todo_count_a", 0)
                + getattr(fpm, "todo_count_b", 0)
                + getattr(fpm, "todo_count_c", 0)
            )
        if feature_todo_total > 0:
            metrics["todo_count_from_postmortem"] = feature_todo_total

        return metrics
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        print(f"  [kaizen] Warning: failed to collect TODO metrics: {exc}")
        return {}


def _copy_query_security_standalone(output_dir: Path) -> None:
    """QP-GAP-006: Copy query-security-metrics.json from project root to run dir.

    The trend script scans run directories for this file but the Anzen gate
    writes it to the project root. This function finds the project root copy
    and places it alongside kaizen-metrics.json in the run output.
    """
    dest = output_dir / "query-security-metrics.json"
    if dest.is_file():
        return  # Already present

    # Walk up to find project root
    candidate = output_dir
    for _ in range(10):
        src = candidate / "query-security-metrics.json"
        if src.is_file() and src != dest:
            try:
                import shutil
                shutil.copy2(str(src), str(dest))
                return
            except OSError:
                return
        candidate = candidate.parent
        if candidate == candidate.parent:
            break


def _merge_query_security_from_project_root(
    metrics: dict, output_dir: Path,
) -> None:
    """REQ-QPA-100: Merge query_security from project-root kaizen-metrics.json.

    The Anzen gate writes ``query_security`` into the project-root
    kaizen-metrics.json via ``update_query_security_metrics()``.  The
    pipeline-output copy is built fresh by the postmortem and does NOT
    include this section.  This function reads the project-root copy and
    merges the ``query_security`` key if present.
    """
    # Walk up from output_dir to find project root (has .startd8/ or .git/)
    candidate = output_dir
    for _ in range(10):
        root_marker = candidate / "kaizen-metrics.json"
        if root_marker.is_file() and root_marker != output_dir / "kaizen-metrics.json":
            try:
                root_data = json.loads(root_marker.read_text(encoding="utf-8"))
                qs = root_data.get("query_security")
                if qs:
                    metrics["query_security"] = qs
                    return
            except (json.JSONDecodeError, OSError):
                pass
        candidate = candidate.parent
        if candidate == candidate.parent:
            break

    # Fallback: check .startd8/kaizen-metrics.json or project root
    # by looking for .contextcore.yaml or pyproject.toml
    for marker in (".contextcore.yaml", "pyproject.toml", ".git"):
        candidate = output_dir
        for _ in range(10):
            if (candidate / marker).exists():
                km = candidate / "kaizen-metrics.json"
                if km.is_file():
                    try:
                        root_data = json.loads(km.read_text(encoding="utf-8"))
                        qs = root_data.get("query_security")
                        if qs:
                            metrics["query_security"] = qs
                            return
                    except (json.JSONDecodeError, OSError):
                        pass
                break
            candidate = candidate.parent
            if candidate == candidate.parent:
                break


def _merge_observability_quality(metrics: dict, output_dir: Path) -> None:
    """REQ-KZ-OBS-500: Merge observability artifact quality into kaizen-metrics.

    Observability artifacts are generated earlier in the pipeline (before
    the postmortem runs), writing quality data to observability-quality.json.
    This function finds that file and merges the ``observability_artifacts``
    section into the metrics dict before it's written to kaizen-metrics.json.
    """
    candidates = [
        output_dir / "observability-quality.json",
        output_dir.parent / "observability" / "observability-quality.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                obs = data.get("observability_artifacts")
                if obs:
                    metrics["observability_artifacts"] = obs
                    return
            except (json.JSONDecodeError, OSError):
                continue


def _copy_security_artifacts_to_pipeline_output(output_dir: Path) -> None:
    """REQ-QPA-101/102: Copy security gate artifacts to pipeline output.

    The Anzen gate writes ``security-gate-metrics.json`` and
    ``query-security-metrics.json`` to the project root.  Copy them to
    the pipeline output directory so trend scripts can find them.
    """
    import shutil

    # Find project root
    candidate = output_dir
    project_root = None
    for _ in range(10):
        if (candidate / ".contextcore.yaml").exists() or (candidate / "pyproject.toml").exists():
            project_root = candidate
            break
        candidate = candidate.parent
        if candidate == candidate.parent:
            break

    if project_root is None:
        return

    for filename in ("security-gate-metrics.json", "query-security-metrics.json"):
        src = project_root / filename
        dst = output_dir / filename
        if src.is_file() and not dst.exists():
            try:
                shutil.copy2(str(src), str(dst))
            except OSError:
                pass


def _emit_kaizen_metrics(report: object, output_dir: Path, run_id: str | None = None) -> None:
    """Extract standardized Kaizen metrics from post-mortem report (REQ-KZ-300)."""
    run_id = run_id or _resolve_run_id(output_dir)
    kaizen_enabled = os.environ.get("KAIZEN_ENABLED", "false").lower() == "true"
    kaizen_source_run = os.environ.get("KAIZEN_SOURCE_RUN", "")

    cost = getattr(report, "cost_summary", None)
    micro = getattr(report, "micro_prime_analysis", None)
    total = getattr(report, "total_features", 0) or 0
    passed = getattr(report, "successful_features", 0) or 0

    # Null-guard pipeline_attribution (R3-S5 / R2-S8)
    attribution = getattr(report, "pipeline_attribution", None) or []
    pipeline_attr = [
        {
            "stage": str(getattr(a.stage, "value", a.stage)),
            "failures": a.failure_count,
        }
        for a in attribution
        if getattr(a, "failure_count", 0) > 0
    ]

    metrics: dict = {
        "schema_version": "1.0",
        "run_id": run_id,
        "timestamp": getattr(report, "timestamp", ""),
        "route": "prime",
        "kaizen_enabled": kaizen_enabled,
        "kaizen_config_source_run": kaizen_source_run,
        "success_rate": passed / total if total > 0 else 0.0,
        "pass_count": passed,
        "fail_count": getattr(report, "failed_features", 0) or 0,
        "total_features": total,
        "total_cost_usd": getattr(cost, "total_usd", 0.0) if cost else 0.0,
        "cost_per_success_usd": (
            cost.total_usd / max(passed, 1) if cost else 0.0
        ),
        "verdict": getattr(report, "aggregate_verdict", ""),
        "aggregate_score": getattr(report, "aggregate_score", 0.0),
        "top_root_causes": _extract_top_root_causes(report),
        "pipeline_attribution": pipeline_attr,
        "lesson_count": len(getattr(report, "lessons", []) or []),
    }

    if micro:
        metrics["micro_prime"] = {
            "total_elements": micro.total_elements,
            "successful_elements": micro.successful_elements,
            "escalated_elements": micro.escalated_elements,
            "tier_distribution": micro.tier_distribution,
            "avg_generation_time_ms": micro.avg_generation_time_ms,
        }
        if micro.total_elements > 0:
            metrics["escalation_rate"] = micro.escalated_elements / micro.total_elements

    # Disk quality (Phase E)
    avg_delta = getattr(report, "avg_assembly_delta", None)
    if avg_delta is not None:
        metrics["avg_assembly_delta"] = avg_delta

    # REQ-SV2-700: Per-category semantic issue breakdown
    category_breakdown: dict[str, dict[str, int]] = {}
    verdict_downgrades = 0
    features_with_errors: list[str] = []
    for fpm in getattr(report, "features", []):
        if getattr(fpm, "semantic_error_count", 0) > 0:
            features_with_errors.append(fpm.feature_id)
        if "semantic" in (getattr(fpm, "verdict", "") or ""):
            verdict_downgrades += 1
        for issue in getattr(getattr(fpm, "disk_compliance", None), "semantic_issues", []) or []:
            if isinstance(issue, dict):
                cat = issue.get("category", "unknown")
                sev = issue.get("severity", "warning")
                entry = category_breakdown.setdefault(cat, {"error": 0, "warning": 0})
                entry[sev] = entry.get(sev, 0) + 1
    if category_breakdown:
        metrics["semantic_issue_breakdown"] = category_breakdown
        metrics["semantic_verdict_downgrades"] = verdict_downgrades
        metrics["features_with_semantic_errors"] = features_with_errors

    # Semantic repair summary (DC-3 dual scoring)
    repair_summary: dict[str, object] = {}
    total_repairs = 0
    features_repaired: list[str] = []
    for fpm in getattr(report, "features", []):
        n = getattr(fpm, "semantic_repairs_applied", 0)
        if n > 0:
            total_repairs += n
            features_repaired.append(fpm.feature_id)
        pre = getattr(fpm, "pre_semantic_repair_score", None)
        if pre is not None:
            repair_summary.setdefault("pre_repair_scores", {})[fpm.feature_id] = pre
    if total_repairs > 0:
        repair_summary["total_repairs"] = total_repairs
        repair_summary["features_repaired"] = features_repaired
        metrics["semantic_repair_summary"] = repair_summary

    # REQ-TCW-401: TODO completion metrics
    todo_metrics = _collect_todo_metrics(output_dir, report)
    if todo_metrics:
        metrics.update(todo_metrics)

    # REQ-QPA-100: Merge query_security from project-root kaizen-metrics.json
    # (written by Anzen gate via update_query_security_metrics) into the
    # pipeline-output copy so cross-run trend scripts can find it.
    _merge_query_security_from_project_root(metrics, output_dir)

    # QP-GAP-006 / REQ-QPI-002: Copy standalone query-security-metrics.json
    # to the run directory so trend scripts can find it alongside kaizen-metrics.json.
    _copy_query_security_standalone(output_dir)

    # REQ-KZ-OBS-500: Merge observability artifact quality into metrics
    # (obs artifacts are generated earlier in the pipeline, before this
    # script runs; the data lives in observability-quality.json)
    _merge_observability_quality(metrics, output_dir)

    metrics_path = output_dir / "kaizen-metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  Kaizen metrics: {metrics_path}")

    # REQ-QPA-101/102: Copy security gate artifacts to pipeline output
    _copy_security_artifacts_to_pipeline_output(output_dir)


# ---------------------------------------------------------------------------
# Kaizen: Suggestion emission (REQ-KZ-501)
# ---------------------------------------------------------------------------


def _emit_kaizen_suggestions(report: object, output_dir: Path, run_id: str | None = None) -> None:
    """Generate structured improvement suggestions from cross-feature patterns (REQ-KZ-501)."""
    suggestions = generate_kaizen_suggestions(report)

    output = {
        "schema_version": "1.0",
        "source_run": run_id or _resolve_run_id(output_dir),
        "suggestions": suggestions,
    }
    suggestions_path = output_dir / "kaizen-suggestions.json"
    suggestions_path.write_text(
        json.dumps(output, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  Kaizen suggestions: {suggestions_path} ({len(suggestions)} generated)")


# ---------------------------------------------------------------------------
# Kaizen: Index management (REQ-KZ-301, 302)
# ---------------------------------------------------------------------------

_DEFAULT_KAIZEN_KEEP = 20
_MIN_KAIZEN_KEEP = 5
_MAX_KAIZEN_KEEP = 200


def _update_kaizen_index(output_dir: Path, keep: int = _DEFAULT_KAIZEN_KEEP, run_id: str | None = None) -> None:
    """Append current run to kaizen-index.json and prune old entries.

    Args:
        output_dir: The phase output directory (e.g. .../run-004/plan-ingestion).
        keep: Maximum number of runs to retain in the index.
        run_id: Pre-resolved run ID (F-AC-05). Falls back to auto-resolution.
    """
    import shutil
    from datetime import datetime

    keep = max(_MIN_KAIZEN_KEEP, min(keep, _MAX_KAIZEN_KEEP))

    run_id = run_id or _resolve_run_id(output_dir)
    pipeline_base = _resolve_pipeline_base(output_dir)
    index_path = pipeline_base / "kaizen-index.json"
    metrics_path = output_dir / "kaizen-metrics.json"

    # Determine run_dir (parent of plan-ingestion)
    run_dir = output_dir.parent if output_dir.name == "plan-ingestion" else output_dir

    # Load or create index
    if index_path.exists():
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            index = {"schema_version": "1.0", "runs": []}
    else:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index = {"schema_version": "1.0", "runs": []}

    # Idempotent: skip if run_id already present
    if any(r.get("run_id") == run_id for r in index["runs"]):
        print(f"  [kaizen] Run {run_id} already in index — updating in place.")
        index["runs"] = [r for r in index["runs"] if r.get("run_id") != run_id]

    # Build entry
    entry: dict = {
        "run_id": run_id,
        "timestamp": datetime.now().strftime("%Y%m%dT%H%M"),
        "run_dir": str(run_dir),
        "metrics_path": str(metrics_path) if metrics_path.exists() else None,
    }
    if metrics_path.exists():
        try:
            m = json.loads(metrics_path.read_text(encoding="utf-8"))
            entry["success_rate"] = m.get("success_rate")
            entry["total_features"] = m.get("total_features")
            entry["kaizen_enabled"] = m.get("kaizen_enabled", False)
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  [kaizen] Warning: failed to parse kaizen-metrics.json: {exc}")

    # Resolve kaizen_prompts_path (REQ-KZ-301): check known subdirectory
    # patterns under the run's kaizen-prompts directory.
    kaizen_prompts_base = output_dir / "kaizen-prompts"
    if kaizen_prompts_base.is_dir():
        # Prefer {run_id}/ subdirectory, fall back to standalone/
        for subdir_name in (run_id, "standalone"):
            candidate = kaizen_prompts_base / subdir_name
            if candidate.is_dir():
                entry["kaizen_prompts_path"] = str(candidate)
                break

    index["runs"].append(entry)

    # Sort by timestamp, newest first for retention
    runs = sorted(index["runs"], key=lambda r: r.get("timestamp", ""), reverse=True)

    # Retention: prune oldest beyond keep limit
    keep_ids = {r["run_id"] for r in runs[:keep]}
    to_prune = [r for r in runs if r["run_id"] not in keep_ids]
    for r in to_prune:
        prune_dir = Path(r.get("run_dir", ""))
        if prune_dir.is_dir() and prune_dir.name.startswith("run-"):
            shutil.rmtree(prune_dir)
            print(f"  [kaizen] Pruned run: {r['run_id']}")

    index["runs"] = sorted(
        [r for r in runs if r["run_id"] in keep_ids],
        key=lambda r: r.get("timestamp", ""),
    )

    # Atomic write
    tmp = Path(str(index_path) + ".tmp")
    tmp.write_text(json.dumps(index, indent=2), encoding="utf-8")
    tmp.replace(index_path)
    print(f"  [kaizen] Index updated: {index_path} ({len(index['runs'])} runs, max {keep})")


if __name__ == "__main__":
    main()
