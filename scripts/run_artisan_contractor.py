#!/usr/bin/env python3
"""
Execute the Artisan Contractor implementation plan via PrimeContractor.

Loads 37 tasks from the plan-ingestion output and feeds them through
PrimeContractorWorkflow for sequential code generation + integration.

Usage:
    # Dry run — preview tasks and dependency order
    python3 scripts/run_artisan_contractor.py --dry-run

    # Execute all tasks (foundation first, then phases, etc.)
    python3 scripts/run_artisan_contractor.py

    # Execute with specific agents
    python3 scripts/run_artisan_contractor.py \
        --lead-agent anthropic:claude-sonnet-4-5-20250929 \
        --drafter-agent gemini:gemini-2.5-flash-lite

    # Resume after failure (retry failed, skip completed)
    python3 scripts/run_artisan_contractor.py --retry-failed

    # Continue past failures to unblocked tasks
    python3 scripts/run_artisan_contractor.py --continue-on-failure

    # Full reset — start from scratch
    python3 scripts/run_artisan_contractor.py --reset-state

    # Limit cost
    python3 scripts/run_artisan_contractor.py --max-cost 10.0

Environment:
    ANTHROPIC_API_KEY: Required for Claude lead agent
    GOOGLE_API_KEY:    Required for Gemini drafter agent
"""

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from startd8.contractors.cli_helpers import add_workflow_args, apply_workflow_args
from startd8.contractors.generators.lead_contractor import LeadContractorCodeGenerator
from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.queue import FeatureSpec
from startd8.utils.prime_task_enrichment import extract_target_files

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Primary source: enriched tracker YAML (has target_file per task)
TASKS_FILE = PROJECT_ROOT / "out" / "artisan_contractor_tasks.yaml"
# Fallback: raw ingestion output
TASKS_FILE_FALLBACK = PROJECT_ROOT / "out" / "plan-ingestion-tasks.yaml"

PROJECT_ID = "artisan-contractor"
SPRINT_ID = "sprint-1"


# ---------------------------------------------------------------------------
# Task loading
# ---------------------------------------------------------------------------

def load_tasks_from_enriched_yaml(path: Path) -> list[dict]:
    """Load tasks from the enriched artisan_contractor_tasks.yaml."""
    data = yaml.safe_load(path.read_text())
    tasks = data.get("tasks", [])
    result = []
    for t in tasks:
        result.append({
            "id": t["id"],
            "name": t["title"],
            "description": t["description"],
            "dependencies": t.get("blocked_by", []),
            "target_files": [t["target_file"]] if t.get("target_file") else [],
            "estimated_loc": t.get("estimated_loc", 0),
            "priority": t.get("priority", "p1"),
            "phase": t.get("phase", ""),
        })
    return result


def load_tasks_from_ingestion_yaml(path: Path) -> list[dict]:
    """Load tasks from raw plan-ingestion-tasks.yaml."""
    data = yaml.safe_load(path.read_text())
    tasks = data.get("tasks", [])
    result = []
    for t in tasks:
        config = t.get("config", {})
        description = config.get("task_description", t.get("title", ""))
        target_files = extract_target_files(description)
        result.append({
            "id": t["task_id"],
            "name": t["title"],
            "description": description,
            "dependencies": t.get("depends_on", []),
            "target_files": target_files,
            "estimated_loc": 0,
            "priority": t.get("priority", "medium"),
            "phase": "",
        })
    return result


def load_tasks() -> list[dict]:
    """Load tasks from the best available source."""
    if TASKS_FILE.exists():
        print(f"Loading tasks from: {TASKS_FILE.name}")
        return load_tasks_from_enriched_yaml(TASKS_FILE)
    elif TASKS_FILE_FALLBACK.exists():
        print(f"Loading tasks from fallback: {TASKS_FILE_FALLBACK.name}")
        return load_tasks_from_ingestion_yaml(TASKS_FILE_FALLBACK)
    else:
        print("ERROR: No task file found. Run PlanIngestionWorkflow first.")
        print(f"  Expected: {TASKS_FILE}")
        print(f"  Or:       {TASKS_FILE_FALLBACK}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def on_feature_complete(feature: FeatureSpec) -> None:
    """Post-feature callback — run targeted tests if available."""
    success = feature.status.value == "complete"
    status = "PASSED" if success else "FAILED"
    print(f"\n  [{status}] {feature.id}: {feature.name}")

    if not success or not feature.target_files:
        return

    # Run tests related to the feature's target file
    target = feature.target_files[0]
    if target.startswith("tests/"):
        # The feature IS a test file — run it directly
        test_path = PROJECT_ROOT / target
        if test_path.exists():
            _run_test(feature, str(test_path))
    elif target.startswith("src/startd8/contractors/artisan"):
        # Source file — check if there's a corresponding test
        test_name = Path(target).stem
        test_candidates = [
            f"tests/unit/contractors/test_{test_name}.py",
            f"tests/unit/contractors/test_artisan_{test_name.replace('artisan_', '')}.py",
        ]
        for candidate in test_candidates:
            test_path = PROJECT_ROOT / candidate
            if test_path.exists():
                _run_test(feature, str(test_path))
                break


def _run_test(feature: FeatureSpec, test_path: str) -> None:
    """Run a test file and print summary."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_path, "-v", "--tb=short", "-x"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode == 0:
        print(f"    Tests passed: {test_path}")
    else:
        print(f"    Tests FAILED: {test_path}")
        if result.stdout:
            lines = result.stdout.strip().split("\n")
            for line in lines[-15:]:
                print(f"      {line}")


# ---------------------------------------------------------------------------
# Workflow setup
# ---------------------------------------------------------------------------

def build_workflow(args: argparse.Namespace) -> PrimeContractorWorkflow:
    """Create and configure the PrimeContractor workflow."""
    # Resolve instrumentor
    instrumentor = None
    try:
        from startd8.contractors.adapters.contextcore import ContextCoreInstrumentor
        instrumentor = ContextCoreInstrumentor(project_id=PROJECT_ID)
        print(f"Using ContextCoreInstrumentor (project={PROJECT_ID})")
    except Exception:
        from startd8.contractors.adapters import LoggingInstrumentor
        instrumentor = LoggingInstrumentor(project_id=PROJECT_ID)
        print("ContextCore unavailable, using LoggingInstrumentor")

    # Build code generator (only needed for live runs)
    code_generator = None
    if not args.dry_run:
        code_generator = LeadContractorCodeGenerator(
            lead_agent=args.lead_agent,
            drafter_agent=args.drafter_agent,
            max_iterations=args.max_iterations,
            output_dir=PROJECT_ROOT / "generated" / "artisan-contractor",
            max_tokens=64000,
        )

    workflow = PrimeContractorWorkflow(
        project_root=PROJECT_ROOT,
        dry_run=args.dry_run,
        auto_commit=False,
        strict_checkpoints=False,
        allow_dirty=True,
        code_generator=code_generator,
        instrumentor=instrumentor,
        on_feature_complete=on_feature_complete,
        max_lines_per_feature=800,  # Artisan tasks are larger (up to 800 LOC)
    )

    return workflow


def populate_queue(workflow: PrimeContractorWorkflow, tasks: list[dict]) -> None:
    """Add all tasks from the ingested plan to the workflow queue."""
    for task in tasks:
        workflow.queue.add_feature(
            feature_id=task["id"],
            name=task["name"],
            description=task["description"],
            dependencies=task["dependencies"],
            target_files=task["target_files"],
        )


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def print_task_summary(tasks: list[dict]) -> None:
    """Print a summary of tasks grouped by phase."""
    phases: dict[str, list] = {}
    for t in tasks:
        phase = t.get("phase", "unknown")
        phases.setdefault(phase, []).append(t)

    total_loc = sum(t.get("estimated_loc", 0) for t in tasks)
    print(f"\nTask Summary: {len(tasks)} tasks, ~{total_loc:,} estimated LOC")
    print("-" * 60)
    for phase, phase_tasks in phases.items():
        phase_loc = sum(t.get("estimated_loc", 0) for t in phase_tasks)
        print(f"  {phase}: {len(phase_tasks)} tasks (~{phase_loc:,} LOC)")
        for t in phase_tasks:
            deps = f" [blocked_by: {', '.join(t['dependencies'])}]" if t["dependencies"] else ""
            print(f"    {t['id']}: {t['name']}{deps}")
    print()


# ---------------------------------------------------------------------------
# Status query (reads state file only — no workflow init)
# ---------------------------------------------------------------------------

def show_status() -> None:
    """Print live status from the state file without starting a workflow."""
    import json

    state_file = PROJECT_ROOT / ".prime_contractor_state.json"
    if not state_file.exists():
        print("No state file found. Run the workflow first.")
        sys.exit(0)

    data = json.loads(state_file.read_text())
    features = data.get("features", {})
    order = data.get("order", sorted(features.keys()))
    saved_at = data.get("saved_at", "unknown")

    icon_map = {
        "pending": "○", "developing": "◐", "generated": "◑",
        "integrating": "◕", "checkpoint": "◔", "complete": "●",
        "failed": "✗", "blocked": "⊘",
    }

    counts: dict[str, int] = {}
    for f in features.values():
        s = f.get("status", "pending")
        counts[s] = counts.get(s, 0) + 1

    total = len(features)
    complete = counts.get("complete", 0)
    failed = counts.get("failed", 0)
    pct = (complete / total * 100) if total else 0

    print(f"\n{'=' * 60}")
    print(f"ARTISAN CONTRACTOR STATUS  (as of {saved_at})")
    print(f"{'=' * 60}")
    print(f"\nProgress: {pct:.0f}% ({complete}/{total} features)")
    for status in ["pending", "developing", "generated", "integrating",
                    "checkpoint", "complete", "failed", "blocked"]:
        if counts.get(status, 0):
            print(f"  {icon_map.get(status, '?')} {status}: {counts[status]}")

    print(f"\n{'─' * 60}")
    for fid in order:
        f = features.get(fid, {})
        status = f.get("status", "pending")
        icon = icon_map.get(status, "?")
        name = f.get("name", fid)
        line = f"  {icon} {fid}: {name} ({status})"
        if f.get("error_message"):
            line += f"\n       Error: {f['error_message'][:80]}"
        print(line)

    if failed:
        print(f"\n  {failed} failed — use --retry-failed to retry")
    print()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Execute Artisan Contractor plan via PrimeContractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Status query (no workflow init)
    parser.add_argument(
        "--status", action="store_true",
        help="Show current feature status from state file and exit",
    )

    # Workflow control flags
    add_workflow_args(parser)

    # Agent configuration
    agent_group = parser.add_argument_group("Agent configuration")
    agent_group.add_argument(
        "--lead-agent",
        default="anthropic:claude-opus-4-6",
        help="Lead agent spec (default: claude-opus-4-6)",
    )
    agent_group.add_argument(
        "--drafter-agent",
        default="anthropic:claude-haiku-4-5-20251001",
        help="Drafter agent spec (default: claude-haiku-4-5)",
    )
    agent_group.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum review iterations per feature (default: 3)",
    )

    # Cost control
    cost_group = parser.add_argument_group("Cost control")
    cost_group.add_argument(
        "--max-cost",
        type=float,
        default=25.0,
        help="Maximum total cost in USD (default: 25.0)",
    )

    # Task filtering
    filter_group = parser.add_argument_group("Task filtering")
    filter_group.add_argument(
        "--phase",
        choices=["foundation", "phases", "orchestration", "unit_tests", "e2e_tests"],
        help="Only run tasks from a specific phase",
    )
    filter_group.add_argument(
        "--task-ids",
        nargs="+",
        help="Only run specific task IDs (e.g., PI-001 PI-002)",
    )

    args = parser.parse_args()

    # Status-only mode — read state file and exit
    if args.status:
        show_status()

    # Load tasks
    tasks = load_tasks()

    # Apply filters
    if args.phase:
        tasks = [t for t in tasks if t.get("phase") == args.phase]
        print(f"Filtered to phase '{args.phase}': {len(tasks)} tasks")
    if args.task_ids:
        id_set = set(args.task_ids)
        tasks = [t for t in tasks if t["id"] in id_set]
        print(f"Filtered to task IDs: {len(tasks)} tasks")

    if not tasks:
        print("ERROR: No tasks to process after filtering.")
        sys.exit(1)

    # Header
    print("=" * 60)
    print("ARTISAN CONTRACTOR: PrimeContractor Execution")
    print(f"Project: {PROJECT_ID}")
    print(f"Sprint:  {SPRINT_ID}")
    print(f"Mode:    {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Lead:    {args.lead_agent}")
    print(f"Drafter: {args.drafter_agent}")
    print(f"Budget:  ${args.max_cost:.2f}")
    print("=" * 60)

    print_task_summary(tasks)

    # Build workflow
    workflow = build_workflow(args)

    # Apply --reset-state BEFORE populating to avoid stale features from prior runs.
    # full_reset() deletes the state file but doesn't clear in-memory features
    # loaded during FeatureQueue.__init__, so we also clear the features dict.
    if getattr(args, "reset_state", False):
        print("Resetting workflow state and cleaning workspace...")
        workflow.full_reset(include_targets=getattr(args, "clean_all", False))
        workflow.queue.features.clear()
        workflow.queue.order.clear()

    populate_queue(workflow, tasks)

    # Apply remaining CLI flags (--retry-failed, --clean)
    # Skip reset_state since we already handled it above
    args_copy = argparse.Namespace(**vars(args))
    args_copy.reset_state = False
    apply_workflow_args(workflow, args_copy)

    # Show queue state
    workflow.queue.print_status()

    # Run
    stop_on_failure = not getattr(args, "continue_on_failure", False)
    result = workflow.run(
        stop_on_failure=stop_on_failure,
        max_cost_usd=args.max_cost,
    )

    # Summary
    print("\n" + "=" * 60)
    print("EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Processed:  {result['processed']}")
    print(f"Succeeded:  {result['succeeded']}")
    print(f"Failed:     {result['failed']}")
    print(f"Progress:   {result['progress']:.1f}%")
    print(f"Total Cost: ${result.get('total_cost_usd', 0):.4f}")
    print(f"Tokens:     {result.get('total_input_tokens', 0):,} in / "
          f"{result.get('total_output_tokens', 0):,} out")
    if result.get("aborted"):
        print(f"Aborted:    {result.get('abort_reason', 'unknown')}")
    print("=" * 60)

    sys.exit(0 if result["succeeded"] == result["processed"] else 1)


if __name__ == "__main__":
    main()
