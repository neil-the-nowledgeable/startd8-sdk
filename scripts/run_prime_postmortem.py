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

from startd8.contractors.prime_postmortem import PrimePostMortemEvaluator


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
            "generated_files": entry.get("generated_files", []),
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
    report = evaluator.evaluate(
        result_dict=result_dict,
        queue_state=queue_state,
        seed_tasks=seed_tasks,
        output_dir=str(output_dir),
    )

    if args.emit_metrics:
        _emit_kaizen_metrics(report, output_dir)

    if args.emit_suggestions:
        _emit_kaizen_suggestions(report, output_dir)

    if args.update_index:
        _update_kaizen_index(output_dir, keep=args.kaizen_keep)

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
# Kaizen: Metrics emission (REQ-KZ-300)
# ---------------------------------------------------------------------------

# All 16 RootCause values mapped to prompt hints (REQ-KZ-501 / R2-S6).
_CAUSE_TO_SUGGESTION: dict[str, dict] = {
    "duplicate_import": {
        "phase": "draft",
        "hint": "Check for existing imports before adding new ones. Deduplicate at file top.",
    },
    "unfilled_stub": {
        "phase": "draft",
        "hint": "Replace every stub/placeholder with real implementation before returning.",
    },
    "scope_corruption": {
        "phase": "draft",
        "hint": "Preserve the existing function and class structure. Do not reorganize scopes.",
    },
    "phantom_import": {
        "phase": "draft",
        "hint": "Validate all imports exist in the target project before referencing them.",
    },
    "indentation_error": {
        "phase": "draft",
        "hint": "Match the indentation style of the surrounding file exactly.",
    },
    "splicer_mismatch": {
        "phase": "draft",
        "hint": "Ensure generated code anchors (function/class names) match the target file exactly.",
    },
    "tier_escalation": {
        "phase": "spec",
        "hint": "Decompose complex features into smaller, independently implementable units.",
    },
    "ast_failure": {
        "phase": "draft",
        "hint": "Emit syntactically valid Python at all times; run a mental parse check before returning.",
    },
    "size_regression": {
        "phase": "draft",
        "hint": "Do not generate significantly more lines than the original file; prefer surgical edits.",
    },
    "generation_error": {
        "phase": "draft",
        "hint": "If generation fails, emit a minimal valid stub rather than an error string.",
    },
    "dependency_blocked": {
        "phase": "spec",
        "hint": "Declare dependencies explicitly in the spec so blocked features are skipped early.",
    },
    "unknown": {
        "phase": "draft",
        "hint": "Inspect the failure message and add a targeted fix rather than regenerating the whole file.",
    },
}


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


def _resolve_run_id(output_dir: Path) -> str:
    """Derive the run ID from run-metadata.json, env var, or directory name.

    Resolution order:
    1. run-metadata.json in the run directory (authoritative)
    2. KAIZEN_RUN_ID env var (set by cap-dev-pipe shell scripts)
    3. Parent directory name (fallback)

    Ensures kaizen works standalone without cap-dev-pipe env vars.
    """
    # Walk up from output_dir (e.g. .../run-004/plan-ingestion) to find run-metadata.json
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

    # Env var fallback (cap-dev-pipe sets this)
    env_id = os.environ.get("KAIZEN_RUN_ID", "")
    if env_id and env_id != "latest":
        return env_id

    # Last resort: use parent directory name if it looks like a run dir
    for parent in [output_dir.parent, output_dir]:
        name = parent.name
        if name.startswith("run-"):
            return name

    return getattr(os, "_kaizen_fallback_id", "") or "unknown"


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


def _emit_kaizen_metrics(report: object, output_dir: Path) -> None:
    """Extract standardized Kaizen metrics from post-mortem report (REQ-KZ-300)."""
    run_id = _resolve_run_id(output_dir)
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

    metrics_path = output_dir / "kaizen-metrics.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  Kaizen metrics: {metrics_path}")


# ---------------------------------------------------------------------------
# Kaizen: Suggestion emission (REQ-KZ-501)
# ---------------------------------------------------------------------------


def _emit_kaizen_suggestions(report: object, output_dir: Path) -> None:
    """Generate structured improvement suggestions from cross-feature patterns (REQ-KZ-501)."""
    suggestions = []
    for pattern in getattr(report, "cross_feature_patterns", []) or []:
        if getattr(pattern, "frequency", 0) < 2:
            continue
        # Match on pattern_type (structured field), not description (free text) — avoids false positives.
        pattern_type = getattr(pattern, "pattern_type", None)
        template = _CAUSE_TO_SUGGESTION.get(pattern_type)
        if not template:
            print(
                f"  [kaizen] No suggestion template for pattern type '{pattern_type}' — skipping.",
                file=sys.stderr,
            )
            continue
        suggestions.append({
            "pattern": getattr(pattern, "description", ""),
            "pattern_type": pattern_type,
            "frequency": pattern.frequency,
            "suggested_action": template["hint"],
            "config_key": "prompt_hints",
            "phase": template["phase"],
            "confidence": "high" if pattern.frequency >= 3 else "medium",
            "auto_applicable": False,
        })

    output = {
        "schema_version": "1.0",
        "source_run": _resolve_run_id(output_dir),
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


def _update_kaizen_index(output_dir: Path, keep: int = _DEFAULT_KAIZEN_KEEP) -> None:
    """Append current run to kaizen-index.json and prune old entries.

    Derives run_id from run-metadata.json (not env vars), making this
    independent of cap-dev-pipe shell wrappers.

    Args:
        output_dir: The phase output directory (e.g. .../run-004/plan-ingestion).
        keep: Maximum number of runs to retain in the index.
    """
    import shutil
    from datetime import datetime

    keep = max(_MIN_KAIZEN_KEEP, min(keep, _MAX_KAIZEN_KEEP))

    run_id = _resolve_run_id(output_dir)
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
        except (json.JSONDecodeError, OSError):
            pass

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
