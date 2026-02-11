#!/usr/bin/env python3
"""
Run the ArtisanContractorWorkflow against an enriched context seed.

This script bridges the enriched context seed (from PlanIngestionWorkflow +
DomainPreflightWorkflow) to the ArtisanContractorWorkflow orchestrator using
ContextSeedHandlers.

Usage:
    # Dry-run (test orchestration, no LLM calls, no file writes):
    python3 scripts/run_artisan_workflow.py \\
        --seed out/autism-policy-test/artisan-context-seed-enriched.json \\
        --project-root /path/to/target/project \\
        --dry-run

    # Full run (creates directories, writes artifacts):
    python3 scripts/run_artisan_workflow.py \\
        --seed out/autism-policy-test/artisan-context-seed-enriched.json \\
        --project-root /path/to/target/project \\
        --output-dir out/autism-policy-test

    # With cost budget:
    python3 scripts/run_artisan_workflow.py \\
        --seed out/autism-policy-test/artisan-context-seed-enriched.json \\
        --cost-budget 5.00 \\
        --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Ensure the SDK is importable (dev mode — installed editable is preferred)
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowResult,
    WorkflowStatus,
)
from startd8.contractors.context_seed_handlers import ContextSeedHandlers
from startd8.contractors.handoff import write_design_handoff


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the workflow run."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    # Quiet noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def print_phase_results(result: WorkflowResult) -> None:
    """Print a human-readable summary of phase results."""
    print("\n" + "=" * 70)
    print(f"Workflow: {result.workflow_id}")
    print(f"Status:   {result.status.value}")
    print(f"Dry Run:  {result.dry_run}")
    print(f"Duration: {result.total_duration_seconds:.2f}s")
    print(f"Cost:     ${result.total_cost:.4f}")
    print("=" * 70)

    for pr in result.phase_results:
        icon = {
            "completed": "+",
            "dry_run": "~",
            "skipped": "-",
            "failed": "X",
            "timed_out": "!",
        }.get(pr.status.value, "?")

        print(f"\n  [{icon}] {pr.phase.value:10s}  status={pr.status.value}  "
              f"cost=${pr.cost:.4f}  duration={pr.duration_seconds:.2f}s")

        if pr.output and isinstance(pr.output, dict):
            # Print key metrics from each phase
            if pr.phase == WorkflowPhase.PLAN:
                print(f"      Tasks: {pr.output.get('task_count', '?')}")
                print(f"      LOC:   {pr.output.get('total_estimated_loc', '?')}")
                ds = pr.output.get("domain_summary", {})
                if ds:
                    print(f"      Domains: {ds}")
                cs = pr.output.get("preflight_check_summary", {})
                if cs:
                    print(f"      Preflight: {cs}")

            elif pr.phase == WorkflowPhase.SCAFFOLD:
                print(f"      Dirs needed:  {len(pr.output.get('directories_needed', []))}")
                print(f"      Dirs created: {len(pr.output.get('directories_created', []))}")
                print(f"      Files exist:  {len(pr.output.get('existing_target_files', []))}")

            elif pr.phase == WorkflowPhase.DESIGN:
                print(f"      Tasks designed: {pr.output.get('tasks_designed', '?')}")
                print(f"      Agreed: {pr.output.get('tasks_agreed', '?')}")
                if pr.output.get("output_dir"):
                    print(f"      Output: {pr.output['output_dir']}")

            elif pr.phase == WorkflowPhase.IMPLEMENT:
                print(f"      Tasks processed: {pr.output.get('tasks_processed', '?')}")
                db = pr.output.get("domain_breakdown", {})
                if db:
                    print(f"      By domain: {db}")

            elif pr.phase == WorkflowPhase.TEST:
                print(f"      Validators: {pr.output.get('total_validators', '?')}")
                print(f"      Tasks with tests: {pr.output.get('tasks_with_tests', '?')}")

            elif pr.phase == WorkflowPhase.REVIEW:
                print(f"      Env issues: {pr.output.get('tasks_with_env_issues', '?')}")

            elif pr.phase == WorkflowPhase.FINALIZE:
                if "report_path" in pr.output:
                    print(f"      Report: {pr.output['report_path']}")

        if pr.error_message:
            print(f"      ERROR: {pr.error_message}")

    print("\n" + "=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run ArtisanContractorWorkflow against an enriched context seed",
    )
    parser.add_argument(
        "--seed", required=True,
        help="Path to the enriched context seed JSON file",
    )
    parser.add_argument(
        "--project-root", default=".",
        help="Target project root directory (default: current directory)",
    )
    parser.add_argument(
        "--output-dir", default=None,
        help="Output directory for artifacts (default: same dir as seed)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulate execution without side effects",
    )
    parser.add_argument(
        "--cost-budget", type=float, default=None,
        help="Maximum cost budget in USD",
    )
    parser.add_argument(
        "--timeout", type=float, default=None,
        help="Total workflow timeout in seconds",
    )
    parser.add_argument(
        "--checkpoint-dir", default=None,
        help="Directory for checkpoint files (enables resume)",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last checkpoint",
    )
    parser.add_argument(
        "--stop-after", default=None,
        choices=[p.value for p in WorkflowPhase],
        help="Stop after this phase completes (e.g. --stop-after design)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--lead-agent", default=None,
        help="Lead agent spec (default: anthropic:claude-sonnet-4-5-20250929)",
    )
    parser.add_argument(
        "--drafter-agent", default=None,
        help="Drafter agent spec (default: from ContextSeedHandlers defaults)",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger("run_artisan_workflow")

    # Validate seed path
    seed_path = Path(args.seed)
    if not seed_path.exists():
        logger.error("Seed file not found: %s", seed_path)
        return 1

    # Determine output dir
    output_dir = args.output_dir or str(seed_path.parent)

    # Create workflow config
    config = WorkflowConfig(
        dry_run=args.dry_run,
        cost_budget=args.cost_budget,
        total_timeout_seconds=args.timeout,
        checkpoint_dir=args.checkpoint_dir,
        project_root=str(Path(args.project_root).resolve()),
        metadata={
            "seed_path": str(seed_path),
            "runner": "run_artisan_workflow.py",
        },
    )

    logger.info("Workflow ID: %s", config.workflow_id)
    logger.info("Seed: %s", seed_path)
    logger.info("Project root: %s", config.project_root)
    logger.info("Dry run: %s", config.dry_run)
    if config.cost_budget is not None:
        logger.info("Cost budget: $%.2f", config.cost_budget)

    # Determine phase sublist when --stop-after is set
    phases = None
    if args.stop_after:
        stop_phase = WorkflowPhase.from_value(args.stop_after)
        all_phases = WorkflowPhase.ordered()
        stop_idx = all_phases.index(stop_phase)
        phases = all_phases[:stop_idx + 1]
        logger.info("Stop-after: running phases %s", [p.value for p in phases])

    # Create workflow and register handlers
    workflow = ArtisanContractorWorkflow(config=config, phases=phases)

    handler_kwargs: dict = {
        "enriched_seed_path": str(seed_path.resolve()),
        "output_dir": output_dir,
    }
    if args.lead_agent:
        handler_kwargs["lead_agent"] = args.lead_agent
    if args.drafter_agent:
        handler_kwargs["drafter_agent"] = args.drafter_agent

    handlers = ContextSeedHandlers.create_all(**handler_kwargs)
    for wp_phase, handler in handlers.items():
        workflow.register_handler(wp_phase, handler)

    # Execute — pass enriched_seed_path in context so handlers can
    # reload task data after a checkpoint resume (context is not persisted).
    initial_context = {
        "enriched_seed_path": str(seed_path.resolve()),
    }

    try:
        result = workflow.execute(
            context=initial_context,
            resume_from_checkpoint=args.resume,
        )
    except Exception as exc:
        logger.error("Workflow failed: %s", exc, exc_info=True)
        return 1

    # Write design handoff when stopping after a phase that includes DESIGN
    if (
        result.status == WorkflowStatus.COMPLETED
        and not args.dry_run
        and phases is not None
        and WorkflowPhase.DESIGN in phases
    ):
        handoff_path = write_design_handoff(
            output_dir=output_dir,
            enriched_seed_path=str(seed_path.resolve()),
            project_root=str(Path(args.project_root).resolve()),
            workflow_id=config.workflow_id,
            completed_phases=[p.value for p in phases],
            design_results=initial_context.get("design_results", {}),
            scaffold=initial_context.get("scaffold", {}),
        )
        logger.info("Wrote design handoff: %s", handoff_path)

    # Print results
    print_phase_results(result)

    # Write result JSON
    result_path = Path(output_dir) / "workflow-result.json"
    result_data = {
        "workflow_id": result.workflow_id,
        "status": result.status.value,
        "dry_run": result.dry_run,
        "total_cost": result.total_cost,
        "total_duration_seconds": result.total_duration_seconds,
        "start_time": result.start_time,
        "end_time": result.end_time,
        "phase_results": [
            {
                "phase": pr.phase.value,
                "status": pr.status.value,
                "cost": pr.cost,
                "duration_seconds": pr.duration_seconds,
                "error_message": pr.error_message,
            }
            for pr in result.phase_results
        ],
    }

    if not args.dry_run:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2, default=str)
        logger.info("Wrote result to %s", result_path)
    else:
        logger.info("Dry run — skipping result file write")

    # Return code based on status
    if result.status == WorkflowStatus.COMPLETED:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
