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
from typing import Any

# Ensure the SDK is importable (dev mode — installed editable is preferred)
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from startd8.contractors.artisan_contractor import (  # noqa: E402
    ArtisanContractorWorkflow,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowResult,
    WorkflowStatus,
)
from startd8.contractors.context_seed_handlers import ContextSeedHandlers  # noqa: E402
from startd8.contractors.handoff import (  # noqa: E402
    DESIGN_HANDOFF_FILENAME,
    load_design_handoff,
    write_design_handoff,
)

_MIN_PHASE_TIMEOUT_SECONDS = 2400.0
_MIN_IMPLEMENT_TIMEOUT_SECONDS = 2400.0
_DEFAULT_TEST_TIMEOUT_SECONDS = 300


def _handoff_extras_from_seed(seed_path: Path) -> dict[str, Any]:
    """Extract artifact paths and context_files from seed for handoff."""
    try:
        data = json.loads(seed_path.read_text(encoding="utf-8"))
        artifacts = data.get("artifacts") or {}
        context_files = data.get("context_files") or []
        return {
            "artifact_manifest_path": artifacts.get("artifact_manifest_path"),
            "project_context_path": artifacts.get("project_context_path"),
            "context_files": context_files,
            "example_artifacts": artifacts.get("example_artifacts", {}),
            "coverage_gaps": artifacts.get("coverage_gaps", []),
        }
    except (json.JSONDecodeError, OSError):
        return {
            "artifact_manifest_path": None,
            "project_context_path": None,
            "context_files": [],
            "example_artifacts": {},
            "coverage_gaps": [],
        }


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the workflow run."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    # Quiet noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def print_phase_results(result: WorkflowResult) -> None:
    # User-facing output — intentionally uses print() rather than logger,
    # since this is a CLI runner script producing human-readable summaries.
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
        help="TOTAL workflow timeout in seconds (wall-clock cap across all phases)",
    )
    parser.add_argument(
        "--phase-timeout", type=float, default=_MIN_PHASE_TIMEOUT_SECONDS,
        help=(
            "Per-phase timeout in seconds (each phase gets this much time). "
            f"Minimum/default: {int(_MIN_PHASE_TIMEOUT_SECONDS)}"
        ),
    )
    parser.add_argument(
        "--implement-timeout", type=float, default=_MIN_IMPLEMENT_TIMEOUT_SECONDS,
        help=(
            "IMPLEMENT phase internal DevelopmentPhase thread timeout in seconds. "
            f"Minimum/default: {int(_MIN_IMPLEMENT_TIMEOUT_SECONDS)}"
        ),
    )
    parser.add_argument(
        "--test-timeout", type=int, default=_DEFAULT_TEST_TIMEOUT_SECONDS,
        help=(
            "TEST phase per-validator subprocess timeout in seconds. "
            f"Default: {_DEFAULT_TEST_TIMEOUT_SECONDS}"
        ),
    )
    parser.add_argument(
        "--checkpoint-dir", default=".startd8/checkpoints",
        help="Directory for checkpoint files (default: .startd8/checkpoints)",
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
    parser.add_argument(
        "--no-auto-commit", action="store_true",
        help="Disable auto-commit (default: commit each feature's generated code to git after implementation)",
    )
    parser.add_argument(
        "--no-scaffold-test-first", action="store_true",
        help="Disable test scaffolding for artifact generator tasks before implementation",
    )
    parser.add_argument(
        "--task-filter",
        default=None,
        help=(
            "Comma-separated task IDs to process (e.g. PI-001 or PI-001,PI-002). "
            "Only these tasks run through all 7 phases. "
            "Enables deterministic workflow IDs for reliable --resume per task."
        ),
    )
    parser.add_argument(
        "--abort-on-preflight-fail", action="store_true",
        help="Abort PLAN phase if preflight checks report any failures",
    )
    parser.add_argument(
        "--design-max-tokens", type=int, default=None,
        help=(
            "Override max_output_tokens for design phase LLM calls. "
            "Use 16384 or 32768 for complex plans to avoid truncation (stop_reason=max_tokens). "
            "When unset, uses per-task calibration from plan-ingestion seed."
        ),
    )
    parser.add_argument(
        "--max-tokens", type=int, default=None,
        help=(
            "Override max_tokens for agent creation (applies to implement phase). "
            "When unset, uses per-task implement_max_output_tokens from "
            "design_calibration, then provider default (32768 for Anthropic)."
        ),
    )
    parser.add_argument(
        "--force-implement", action="store_true",
        help="Ignore cached generation_results; always run fresh IMPLEMENT (no resume from .startd8/state/)",
    )
    parser.add_argument(
        "--force-design", action="store_true",
        help="Ignore cached design handoff; always run fresh DESIGN with LLM calls",
    )
    parser.add_argument(
        "--force-review", action="store_true",
        help="Ignore cached review_results; always run fresh REVIEW with LLM calls",
    )

    # --dress-rehearsal and --adopt-prior are mutually exclusive:
    # dress-rehearsal generates *new* design artifacts into a staging dir,
    # adopt-prior *consumes* existing artifacts from a prior run.
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dress-rehearsal", action="store_true",
        help=(
            "Dress-rehearsal mode: run with real LLM calls through DESIGN to surface issues "
            "(truncation, section mismatches) before committing. Writes to staging dir. "
            "Distinct from --dry-run (which skips LLM calls entirely). "
            "Defaults to --stop-after design when set."
        ),
    )
    mode_group.add_argument(
        "--adopt-prior", nargs="?", const="auto", default=None,
        help=(
            "Adopt design artifacts from a prior dress-rehearsal (or design-only) run. "
            "Tasks whose design_results are already 'designed' skip LLM calls. "
            "Pass a directory or handoff file path, or omit the value to auto-detect "
            "from <output-dir>/.dress-rehearsal/. "
            "Example: --adopt-prior  (auto)  or  --adopt-prior /path/to/handoff-dir"
        ),
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger("run_artisan_workflow")

    # Auto-configure OTel (metrics + traces) so artisan workflow data
    # reaches Mimir/Tempo/Loki via the collector.  In "auto" mode this
    # is a no-op when no collector is reachable.
    try:
        from startd8.otel import auto_configure_otel, format_telemetry_banner, get_otel_runtime_state
        otel_state = get_otel_runtime_state()
        logger.info(format_telemetry_banner(otel_state))
        if otel_state["will_configure"]:
            auto_configure_otel()
    except Exception as exc:
        logger.debug("OTel auto-configure skipped: %s", exc)

    # Keep timeouts sane for long multi-task artisan runs.
    if args.phase_timeout is not None and args.phase_timeout < _MIN_PHASE_TIMEOUT_SECONDS:
        logger.warning(
            "--phase-timeout=%s is below recommended minimum; using %s",
            args.phase_timeout,
            int(_MIN_PHASE_TIMEOUT_SECONDS),
        )
        args.phase_timeout = _MIN_PHASE_TIMEOUT_SECONDS
    if args.implement_timeout is not None and args.implement_timeout < _MIN_IMPLEMENT_TIMEOUT_SECONDS:
        logger.warning(
            "--implement-timeout=%s is below recommended minimum; using %s",
            args.implement_timeout,
            int(_MIN_IMPLEMENT_TIMEOUT_SECONDS),
        )
        args.implement_timeout = _MIN_IMPLEMENT_TIMEOUT_SECONDS
    if args.test_timeout is not None and args.test_timeout < 60:
        logger.warning(
            "--test-timeout=%s is below minimum; using 60",
            args.test_timeout,
        )
        args.test_timeout = 60

    # Validate seed path
    seed_path = Path(args.seed)
    if not seed_path.exists():
        logger.error("Seed file not found: %s", seed_path)
        return 1

    # Determine output dir
    output_dir = args.output_dir or str(seed_path.parent)

    # Dress-rehearsal mode: run with real LLM calls through DESIGN to surface issues
    # before committing. Writes to staging dir; distinct from dry-run (no LLM).
    if args.dress_rehearsal:
        output_dir = str(Path(output_dir) / ".dress-rehearsal")
        if not args.stop_after:
            args.stop_after = "design"
        # Dress-rehearsal requires real LLM calls; override dry-run if set
        args.dry_run = False
        logger.info("Dress-rehearsal mode: output_dir=%s, stop-after=%s", output_dir, args.stop_after)

    # ------------------------------------------------------------------
    # Adopt prior design artifacts (from dress-rehearsal or design-only)
    # ------------------------------------------------------------------
    adopted_design_results: dict[str, Any] | None = None

    if args.adopt_prior is not None:
        # Resolve source: explicit path or auto-detect from <output_dir>/.dress-rehearsal/
        if args.adopt_prior == "auto":
            adopt_source = Path(output_dir) / ".dress-rehearsal"
        else:
            adopt_source = Path(args.adopt_prior)

        try:
            handoff = load_design_handoff(adopt_source)
            adopted_design_results = handoff.design_results
            adopted_count = sum(
                1 for r in adopted_design_results.values()
                if r.get("status") == "designed"
            )
            logger.info(
                "Adopting %d prior design result(s) from %s (workflow %s)",
                adopted_count, adopt_source, handoff.workflow_id,
            )
        except FileNotFoundError:
            logger.warning(
                "No design-handoff.json found at %s — running without prior artifacts",
                adopt_source,
            )
        except ValueError as exc:
            logger.warning("Could not load prior handoff: %s — ignoring", exc)

    elif not args.dress_rehearsal and not args.dry_run:
        # Auto-detection hint: check if dress-rehearsal artifacts exist
        dr_handoff = Path(output_dir) / ".dress-rehearsal" / DESIGN_HANDOFF_FILENAME
        if dr_handoff.exists():
            logger.info(
                "Prior dress-rehearsal artifacts detected at %s. "
                "Use --adopt-prior to reuse them and skip redundant LLM calls.",
                dr_handoff.parent,
            )

    # Parse task filter (comma-separated task IDs)
    task_filter: list[str] | None = None
    if args.task_filter:
        task_filter = [t.strip() for t in args.task_filter.split(",") if t.strip()]
        if not task_filter:
            parser.error("--task-filter requires at least one non-empty task ID")

    # ------------------------------------------------------------------
    # Auto-enrich: prefer existing enriched seed, else run preflight
    # ------------------------------------------------------------------
    # Check for a prior enriched seed on disk before paying for a new
    # DomainPreflightWorkflow run.  Convention: enriched seeds live at
    # {stem}-enriched{suffix} alongside the original seed file.
    base_stem = seed_path.stem.removesuffix("-enriched")
    all_suffixes = "".join(seed_path.suffixes)
    enriched_candidate = seed_path.with_name(
        base_stem + "-enriched" + all_suffixes
    )
    if enriched_candidate != seed_path and enriched_candidate.exists():
        # Staleness check: if the base seed is newer than the enriched
        # version, the enriched version is stale and must be regenerated.
        base_seed = seed_path.with_name(base_stem + all_suffixes)
        if base_seed.exists() and base_seed.stat().st_mtime > enriched_candidate.stat().st_mtime:
            logger.warning(
                "Enriched seed is stale (base seed modified after enrichment) — "
                "will re-run DomainPreflightWorkflow. base=%s enriched=%s",
                base_seed, enriched_candidate,
            )
        else:
            logger.info(
                "Found enriched seed on disk — using %s (skip DomainPreflightWorkflow)",
                enriched_candidate,
            )
            seed_path = enriched_candidate

    try:
        seed_data = json.loads(seed_path.read_text(encoding="utf-8"))
        tasks = seed_data.get("tasks", [])
        has_enrichment = any(
            t.get("_enrichment") for t in tasks
        )
        if tasks and not has_enrichment:
            logger.info(
                "Seed lacks _enrichment data — running DomainPreflightWorkflow "
                "to classify domains and add prompt constraints"
            )
            from startd8.workflows.builtin.domain_preflight_workflow import (
                DomainPreflightWorkflow,
            )
            preflight = DomainPreflightWorkflow()
            preflight_result = preflight.run({
                "context_seed_path": str(seed_path),
                "project_root": str(Path(args.project_root).resolve()),
            })
            if preflight_result.success:
                enriched_path = Path(
                    preflight_result.output["enriched_seed_path"]
                )
                logger.info(
                    "Auto-enriched seed written: %s (domains: %s)",
                    enriched_path,
                    preflight_result.output.get("domain_summary", {}),
                )
                # Use the enriched seed going forward
                seed_path = enriched_path
            else:
                logger.warning(
                    "DomainPreflightWorkflow failed: %s — continuing "
                    "with unenriched seed",
                    preflight_result.error,
                )
    except Exception as exc:
        logger.warning(
            "Auto-enrichment check failed: %s — continuing with original seed",
            exc,
        )

    # Deterministic workflow ID when filtering to specific tasks so that
    # --resume reliably finds the checkpoint for the same task(s).
    workflow_kwargs: dict[str, Any] = {}
    if task_filter:
        filter_key = "-".join(sorted(task_filter))
        workflow_kwargs["workflow_id"] = f"artisan-{filter_key}"

    # Create workflow config
    config = WorkflowConfig(
        dry_run=args.dry_run,
        cost_budget=args.cost_budget,
        total_timeout_seconds=args.timeout,
        phase_timeout_seconds=args.phase_timeout,
        checkpoint_dir=args.checkpoint_dir,
        project_root=str(Path(args.project_root).resolve()),
        metadata={
            "seed_path": str(seed_path),
            "runner": "run_artisan_workflow.py",
        },
        **workflow_kwargs,
    )

    logger.info("Workflow ID: %s", config.workflow_id)
    logger.info("Seed: %s", seed_path)
    logger.info("Project root: %s", config.project_root)
    logger.info("Dry run: %s", config.dry_run)
    if task_filter:
        logger.info("Task filter: %s (%d task(s))", task_filter, len(task_filter))
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
    if args.max_tokens is not None:
        handler_kwargs["max_tokens"] = args.max_tokens
    if args.design_max_tokens is not None:
        handler_kwargs["design_max_tokens"] = args.design_max_tokens
    if args.implement_timeout is not None:
        handler_kwargs["development_timeout_seconds"] = args.implement_timeout
    if args.test_timeout is not None:
        handler_kwargs["test_timeout_seconds"] = args.test_timeout
    if args.no_auto_commit:
        handler_kwargs["auto_commit"] = False
    if args.no_scaffold_test_first:
        handler_kwargs["scaffold_test_first"] = False
    if args.force_implement:
        handler_kwargs["force_implement"] = True
    if args.force_design:
        handler_kwargs["force_design"] = True
    if args.force_review:
        handler_kwargs["force_review"] = True

    handlers = ContextSeedHandlers.create_all(**handler_kwargs)
    for wp_phase, handler in handlers.items():
        workflow.register_handler(wp_phase, handler)

    # Execute — pass enriched_seed_path in context so handlers can
    # reload task data after a checkpoint resume (context is not persisted).
    initial_context: dict[str, Any] = {
        "enriched_seed_path": str(seed_path.resolve()),
    }
    if task_filter:
        initial_context["task_filter"] = task_filter
    if args.abort_on_preflight_fail:
        initial_context["abort_on_preflight_fail"] = True
    if adopted_design_results:
        initial_context["design_results"] = adopted_design_results

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
        extras = _handoff_extras_from_seed(seed_path)
        handoff_path = write_design_handoff(
            output_dir=output_dir,
            enriched_seed_path=str(seed_path.resolve()),
            project_root=str(Path(args.project_root).resolve()),
            workflow_id=config.workflow_id,
            completed_phases=[p.value for p in phases],
            design_results=initial_context.get("design_results", {}),
            scaffold=initial_context.get("scaffold", {}),
            artifact_manifest_path=extras.get("artifact_manifest_path"),
            project_context_path=extras.get("project_context_path"),
            context_files=extras.get("context_files", []),
            example_artifacts=extras.get("example_artifacts", {}),
            coverage_gaps=extras.get("coverage_gaps", []),
        )
        logger.info("Wrote design handoff: %s", handoff_path)

    # Print results
    print_phase_results(result)

    # Write result JSON
    if task_filter:
        filter_slug = "-".join(sorted(task_filter))
        result_path = Path(output_dir) / f"workflow-result-{filter_slug}.json"
    else:
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
