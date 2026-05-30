#!/usr/bin/env python3
"""
Implement auto-decompose via PrimeContractor (dogfooding).

This script uses the SDK's own PrimeContractor workflow to implement
the auto-decompose feature — five tasks that add decomposition logic,
entry guards, callback guards, and tests.

Usage:
    # Dry run — preview tasks without executing
    python3 scripts/run_auto_decompose.py --dry-run

    # Execute all tasks
    python3 scripts/run_auto_decompose.py

    # Reset state and retry from scratch
    python3 scripts/run_auto_decompose.py --reset-state

    # Retry only failed tasks
    python3 scripts/run_auto_decompose.py --retry-failed

    # Continue past failures
    python3 scripts/run_auto_decompose.py --continue-on-failure

Environment:
    ANTHROPIC_API_KEY: Required for Claude lead agent
    GOOGLE_API_KEY: Required for Gemini drafter agent
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Add src to path for development
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from startd8.contractors.cli_helpers import add_workflow_args, apply_workflow_args
from startd8.contractors.generators.primary_contractor import LeadContractorCodeGenerator
from startd8.contractors.prime_contractor import PrimeContractorWorkflow
from startd8.contractors.queue import FeatureSpec

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TARGET_FILE = "src/startd8/contractors/prime_contractor.py"
TEST_FILE = "tests/contractors/test_contractors.py"

PROJECT_ID = "startd8-sdk"
SPRINT_ID = "sprint-auto-decompose"

# Task definitions — mirrors scripts/auto_decompose_tasks.yaml
TASKS = [
    {
        "id": "AD-001",
        "name": "Add _process_decomposed_feature() method",
        "target_files": [TARGET_FILE],
        "dependencies": [],
        "description": (
            "Add a new private method `_process_decomposed_feature(self, feature: FeatureSpec) -> bool` "
            "to the PrimeContractorWorkflow class. The method decomposes a multi-file feature into "
            "sequential single-file sub-features, generating and integrating each one in order. "
            "Sub-features are transient (not added to the queue). The on_feature_complete callback "
            "fires only on the last sub-feature. The parent feature is marked complete/failed based "
            "on the aggregate outcome."
        ),
    },
    {
        "id": "AD-002",
        "name": "Add len(target_files) > 1 guard to process_feature()",
        "target_files": [TARGET_FILE],
        "dependencies": ["AD-001"],
        "description": (
            "Modify process_feature() to check `len(feature.target_files) > 1` at the top. "
            "If True and status is PENDING, route to _process_decomposed_feature(). "
            "Single-file and GENERATED features follow the existing path unchanged."
        ),
    },
    {
        "id": "AD-003",
        "name": "Only fire on_feature_complete on last sub-feature",
        "target_files": [TARGET_FILE],
        "dependencies": ["AD-001"],
        "description": (
            "In _process_decomposed_feature(), save self.on_feature_complete before the loop, "
            "set it to None for non-final sub-features, and restore it for the last sub-feature "
            "and on all failure/exit paths. This prevents intermediate checkpoints from running "
            "on incomplete multi-file state."
        ),
    },
    {
        "id": "AD-004",
        "name": "Unit tests for decomposition logic",
        "target_files": [TEST_FILE],
        "dependencies": ["AD-001", "AD-002", "AD-003"],
        "description": (
            "Add TestAutoDecompose class with 5 tests: single_file_bypasses, multi_file_triggers, "
            "sub_feature_ids, callback_fires_only_on_last, failure_marks_parent_failed. "
            "All tests use dry_run=True and LoggingInstrumentor. No LLM calls."
        ),
    },
    {
        "id": "AD-005",
        "name": "Integration tests (2-file + 3-file features)",
        "target_files": [TEST_FILE],
        "dependencies": ["AD-004"],
        "description": (
            "Add TestAutoDecomposeIntegration class with 5 tests: two_file_dry_run, three_file_dry_run, "
            "reads_current_file_content, decomposition_with_dependencies, mixed_single_and_multi. "
            "Tests exercise full workflow.run() path with real files in tmp_path."
        ),
    },
]


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def on_feature_complete(feature: FeatureSpec) -> None:
    """Run pytest after test features are integrated."""
    if feature.id.startswith("AD-004") or feature.id.startswith("AD-005"):
        print(f"\n  Running pytest for {feature.name}...")
        result = subprocess.run(
            [
                sys.executable, "-m", "pytest",
                str(PROJECT_ROOT / "tests" / "contractors" / "test_contractors.py"),
                "-v", "--tb=short", "-x",
            ],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0:
            print(f"  Tests passed for {feature.name}")
        else:
            print(f"  Tests FAILED for {feature.name}")
            if result.stdout:
                # Print last 20 lines of output
                lines = result.stdout.strip().split("\n")
                for line in lines[-20:]:
                    print(f"    {line}")


# ---------------------------------------------------------------------------
# Workflow setup
# ---------------------------------------------------------------------------

def build_workflow(args: argparse.Namespace) -> PrimeContractorWorkflow:
    """Create and configure the PrimeContractor workflow."""
    # Resolve instrumentor: prefer ContextCore, fall back to logging
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
            output_dir=PROJECT_ROOT / "generated" / "auto-decompose",
        )

    workflow = PrimeContractorWorkflow(
        project_root=PROJECT_ROOT,
        dry_run=args.dry_run,
        auto_commit=False,
        strict_checkpoints=False,
        allow_dirty=True,  # We modify the SDK itself
        code_generator=code_generator,
        instrumentor=instrumentor,
        on_feature_complete=on_feature_complete,
    )

    return workflow


def populate_queue(workflow: PrimeContractorWorkflow) -> None:
    """Add the 5 auto-decompose features to the workflow queue."""
    for task in TASKS:
        workflow.queue.add_feature(
            feature_id=task["id"],
            name=task["name"],
            description=task["description"],
            dependencies=task["dependencies"],
            target_files=task["target_files"],
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Implement auto-decompose via PrimeContractor (dogfooding)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Workflow control flags from cli_helpers
    add_workflow_args(parser)

    # Agent configuration
    agent_group = parser.add_argument_group("Agent configuration")
    agent_group.add_argument(
        "--lead-agent",
        default="anthropic:claude-sonnet-4-6",
        help="Lead agent spec (default: claude-sonnet-4-6)",
    )
    agent_group.add_argument(
        "--drafter-agent",
        default="gemini:gemini-2.5-flash-lite",
        help="Drafter agent spec (default: gemini-2.5-flash-lite)",
    )
    agent_group.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum review iterations (default: 3)",
    )

    # Cost control
    cost_group = parser.add_argument_group("Cost control")
    cost_group.add_argument(
        "--max-cost",
        type=float,
        default=5.0,
        help="Maximum total cost in USD (default: 5.0)",
    )

    args = parser.parse_args()

    # Build workflow
    print("=" * 60)
    print("AUTO-DECOMPOSE: PrimeContractor Dogfooding")
    print(f"Project: {PROJECT_ID}")
    print(f"Sprint:  {SPRINT_ID}")
    print(f"Mode:    {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 60)

    workflow = build_workflow(args)
    populate_queue(workflow)

    # Apply CLI flags (--reset-state, --retry-failed, --clean, etc.)
    apply_workflow_args(workflow, args)

    # Show queue before running
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
    print(f"Tokens:     {result.get('total_input_tokens', 0)} in / "
          f"{result.get('total_output_tokens', 0)} out")
    if result.get("aborted"):
        print(f"Aborted:    {result.get('abort_reason', 'unknown')}")
    print("=" * 60)

    # Exit code: 0 if all succeeded, 1 otherwise
    sys.exit(0 if result["succeeded"] == result["processed"] else 1)


if __name__ == "__main__":
    main()
