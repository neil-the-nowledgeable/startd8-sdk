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


if __name__ == "__main__":
    main()
