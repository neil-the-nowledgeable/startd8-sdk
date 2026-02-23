#!/usr/bin/env python3
"""
Run the implementation half of the artisan workflow: IMPLEMENT → TEST → REVIEW → FINALIZE.

Picks up where the design-only workflow left off, using the design-handoff.json
file to reconstruct context state (enriched_seed_path, design_results, scaffold).

Usage:
    # With explicit handoff file:
    python3 scripts/run_artisan_implement_only.py \
        --handoff out/designs/design-handoff.json

    # Auto-detect handoff in output directory:
    python3 scripts/run_artisan_implement_only.py \
        --output-dir out/designs

    # Fallback without handoff (reloads tasks from seed only):
    python3 scripts/run_artisan_implement_only.py \
        --seed out/artisan-context-seed-enriched.json

    # With CLI overrides:
    python3 scripts/run_artisan_implement_only.py \
        --handoff out/designs/design-handoff.json \
        --project-root /path/to/project \
        --cost-budget 5.00 \
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
from startd8.contractors.handoff import HandoffData, load_design_handoff, verify_context_checksums, verify_source_checksum, HandoffContextDriftError

_DEFAULT_TEST_TIMEOUT_SECONDS = 300


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the workflow run."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
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
            if pr.phase == WorkflowPhase.IMPLEMENT:
                print(f"      Tasks processed: {pr.output.get('tasks_processed', '?')}")
                db = pr.output.get("domain_breakdown", {})
                if db:
                    print(f"      By domain: {db}")

            elif pr.phase == WorkflowPhase.INTEGRATE:
                print(f"      Merged: {pr.output.get('passed', '?')}/{pr.output.get('total', '?')}")

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


def _update_contract_status(output_dir: str | Path, status: str, error: str | None = None) -> None:
    """Update the status of the handoff contract file if it exists."""
    try:
        contract_path = Path(output_dir) / "design-handoff-contract.json"
        if not contract_path.exists():
            return

        data = json.loads(contract_path.read_text(encoding="utf-8"))
        data["status"] = status
        if error:
            data["error"] = str(error)
        
        # Basic atomic write
        tmp = contract_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.replace(contract_path)
    except Exception as exc:
        logging.getLogger("run_artisan_implement_only").warning(
            "Failed to update contract status: %s", exc
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run implementation workflow (IMPLEMENT → TEST → REVIEW → FINALIZE)",
    )

    # Source options (mutually preferred, not mutually exclusive for overrides)
    source = parser.add_argument_group("source", "Where to load context from")
    source.add_argument(
        "--handoff",
        help="Path to design-handoff.json file",
    )
    source.add_argument(
        "--output-dir", default=None,
        help="Directory containing design-handoff.json (auto-detected)",
    )
    source.add_argument(
        "--seed", default=None,
        help="Fallback: path to enriched context seed (no design_results)",
    )

    # Override options
    parser.add_argument(
        "--project-root", default=None,
        help="Override project root from handoff",
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
        "--test-timeout", type=int, default=_DEFAULT_TEST_TIMEOUT_SECONDS,
        help=(
            "TEST phase per-validator subprocess timeout in seconds "
            f"(default: {_DEFAULT_TEST_TIMEOUT_SECONDS})"
        ),
    )
    parser.add_argument(
        "--lead-agent", default=None,
        help="Lead agent spec for implementation",
    )
    parser.add_argument(
        "--drafter-agent", default=None,
        help="Drafter agent spec for code generation",
    )
    parser.add_argument(
        "--strict-handoff", action="store_true",
        help="Fail if context files have changed since design phase",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger("run_artisan_implement_only")

    if args.test_timeout is not None and args.test_timeout < 60:
        logger.warning(
            "--test-timeout=%s is below minimum; using 60",
            args.test_timeout,
        )
        args.test_timeout = 60

    # --- Resolve context source ---
    seed_path: str | None = None
    project_root: str = str(Path(args.project_root).resolve()) if args.project_root else str(Path.cwd())
    output_dir: str | None = args.output_dir
    design_results: dict = {}
    scaffold: dict = {}
    handoff_workflow_id: str | None = None
    handoff: HandoffData | None = None

    if args.handoff:
        # Explicit handoff file
        try:
            handoff = load_design_handoff(args.handoff)
            # Item 12: Verify checksums
            warnings = verify_context_checksums(handoff.context_files, strict=args.strict_handoff)
            for w in warnings:
                logger.warning(w)
        except (FileNotFoundError, ValueError, HandoffContextDriftError) as exc:
            logger.error("Failed to load/verify handoff: %s", exc)
            return 1

        # BP-2: Verify enriched seed hasn't drifted since design
        source_warning = verify_source_checksum(handoff)
        if source_warning:
            logger.warning(source_warning)

        seed_path = handoff.enriched_seed_path
        project_root = args.project_root or handoff.project_root
        if args.project_root:
            project_root = str(Path(args.project_root).resolve())
        output_dir = output_dir or handoff.output_dir
        design_results = handoff.design_results
        scaffold = handoff.scaffold
        handoff_workflow_id = handoff.workflow_id
        logger.info("Loaded handoff from %s (workflow %s)", args.handoff, handoff.workflow_id)

    elif args.output_dir:
        # Auto-detect handoff in output directory
        try:
            handoff = load_design_handoff(args.output_dir)
            # Item 12: Verify checksums
            warnings = verify_context_checksums(handoff.context_files, strict=args.strict_handoff)
            for w in warnings:
                logger.warning(w)
        except FileNotFoundError:
            logger.error(
                "No design-handoff.json found in %s. "
                "Use --handoff or --seed instead.", args.output_dir,
            )
            return 1
        except (ValueError, HandoffContextDriftError) as exc:
            logger.error("Invalid/drifted handoff in %s: %s", args.output_dir, exc)
            return 1

        # BP-2: Verify enriched seed hasn't drifted since design
        source_warning = verify_source_checksum(handoff)
        if source_warning:
            logger.warning(source_warning)

        seed_path = handoff.enriched_seed_path
        project_root = args.project_root or handoff.project_root
        if args.project_root:
            project_root = str(Path(args.project_root).resolve())
        output_dir = args.output_dir
        design_results = handoff.design_results
        scaffold = handoff.scaffold
        handoff_workflow_id = handoff.workflow_id
        logger.info("Auto-detected handoff in %s (workflow %s)", args.output_dir, handoff.workflow_id)

    elif args.seed:
        # Fallback: seed only (no design_results)
        seed_path = str(Path(args.seed).resolve())
        output_dir = output_dir or str(Path(args.seed).parent)
        logger.info("Fallback mode: loading from seed only (no design_results)")

    else:
        parser.error("One of --handoff, --output-dir, or --seed is required")

    # Validate seed exists
    if seed_path and not Path(seed_path).exists():
        # CLI --seed override
        if args.seed:
            seed_path = str(Path(args.seed).resolve())
        if not Path(seed_path).exists():
            logger.error("Seed file not found: %s", seed_path)
            return 1

    assert output_dir is not None  # guaranteed by logic above

    # --- Build workflow config ---
    config = WorkflowConfig(
        dry_run=args.dry_run,
        cost_budget=args.cost_budget,
        total_timeout_seconds=args.timeout,
        project_root=project_root,
        metadata={
            "seed_path": seed_path or "",
            "runner": "run_artisan_implement_only.py",
            "design_handoff_source": args.handoff or args.output_dir or "seed_only",
            "design_workflow_id": handoff_workflow_id or "",
        },
    )

    # --- Implementation phases only ---
    phases = [
        WorkflowPhase.IMPLEMENT,
        WorkflowPhase.INTEGRATE,
        WorkflowPhase.TEST,
        WorkflowPhase.REVIEW,
        WorkflowPhase.FINALIZE,
    ]
    workflow = ArtisanContractorWorkflow(config=config, phases=phases)

    handler_kwargs: dict = {
        "enriched_seed_path": seed_path or "",
        "output_dir": output_dir,
    }
    if args.lead_agent:
        handler_kwargs["lead_agent"] = args.lead_agent
    if args.drafter_agent:
        handler_kwargs["drafter_agent"] = args.drafter_agent
    if args.test_timeout is not None:
        handler_kwargs["test_timeout_seconds"] = args.test_timeout

    # Create all handlers but only register the 4 implementation-phase handlers
    all_handlers = ContextSeedHandlers.create_all(**handler_kwargs)
    for wp_phase in phases:
        if wp_phase in all_handlers:
            workflow.register_handler(wp_phase, all_handlers[wp_phase])

    # --- Reconstruct initial context ---
    initial_context: dict = {}
    if seed_path:
        initial_context["enriched_seed_path"] = seed_path
    if design_results:
        initial_context["design_results"] = design_results
    if scaffold:
        initial_context["scaffold"] = scaffold

    # B-6: Reconstruct design_mode_summary from handoff (lost in split runs)
    if handoff is not None and handoff.design_mode_summary:
        initial_context["design_mode_summary"] = handoff.design_mode_summary

    logger.info("Workflow ID: %s", config.workflow_id)
    logger.info("Implementation-only: phases=%s", [p.value for p in phases])
    if handoff_workflow_id:
        logger.info("Continuing from design workflow: %s", handoff_workflow_id)

    # --- Execute ---
    if output_dir:
        _update_contract_status(output_dir, "in_progress")

    try:
        result = workflow.execute(context=initial_context)
    except Exception as exc:
        logger.error("Workflow failed: %s", exc, exc_info=True)
        if output_dir:
            _update_contract_status(output_dir, "failed", str(exc))
        return 1

    # --- Print results ---
    print_phase_results(result)

    # --- Write result JSON ---
    result_path = Path(output_dir) / "implement-workflow-result.json"
    result_data = {
        "workflow_id": result.workflow_id,
        "status": result.status.value,
        "dry_run": result.dry_run,
        "total_cost": result.total_cost,
        "total_duration_seconds": result.total_duration_seconds,
        "start_time": result.start_time,
        "end_time": result.end_time,
        "design_workflow_id": handoff_workflow_id or "",
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

    if result.status == WorkflowStatus.COMPLETED:
        if output_dir:
            _update_contract_status(output_dir, "completed")
        return 0
    
    if output_dir:
        _update_contract_status(output_dir, "failed", f"Workflow status: {result.status.value}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
