#!/usr/bin/env python3
"""
Run the PrimeContractorWorkflow against a context seed from plan-ingestion.

This script bridges the context seed (from PlanIngestionWorkflow) to the
PrimeContractorWorkflow orchestrator via FeatureQueue.add_features_from_seed().

Usage:
    # Dry-run (test orchestration, no LLM calls, no file writes):
    python3 scripts/run_prime_workflow.py \
        --seed out/project/plan-ingestion/prime-context-seed.json \
        --project-root /path/to/target/project \
        --dry-run

    # Full run (generates code, integrates per-feature):
    python3 scripts/run_prime_workflow.py \
        --seed out/project/plan-ingestion/prime-context-seed.json \
        --project-root /path/to/target/project \
        --output-dir out/project

    # Single task:
    python3 scripts/run_prime_workflow.py \
        --seed out/project/plan-ingestion/prime-context-seed.json \
        --project-root /path/to/target/project \
        --task-filter PI-014

    # With cost budget:
    python3 scripts/run_prime_workflow.py \
        --seed out/project/plan-ingestion/prime-context-seed.json \
        --cost-budget 5.00
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

from startd8.contractors.generators.lead_contractor import (  # noqa: E402
    LeadContractorCodeGenerator,
)
from startd8.contractors.prime_contractor import PrimeContractorWorkflow  # noqa: E402
from startd8.contractors.queue import FeatureQueue, FeatureStatus  # noqa: E402


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the workflow run."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def print_results(result: dict[str, Any]) -> None:
    """Print a human-readable summary of prime workflow results."""
    # User-facing output — intentionally uses print() rather than logger.
    print("\n" + "=" * 70)
    print("PRIME CONTRACTOR WORKFLOW RESULTS")
    print("=" * 70)
    print(f"  Processed:  {result.get('processed', 0)}")
    print(f"  Succeeded:  {result.get('succeeded', 0)}")
    print(f"  Failed:     {result.get('failed', 0)}")
    print(f"  Progress:   {result.get('progress', 0):.1f}%")
    print(f"  Total cost: ${result.get('total_cost_usd', 0):.4f}")
    if result.get("aborted"):
        print(f"  ABORTED:    {result.get('abort_reason', 'unknown')}")
    print("=" * 70)

    history = result.get("history", [])
    if history:
        print("\nFeature History:")
        for entry in history:
            icon = "+" if entry.get("success") else "X"
            name = entry.get("feature_name", entry.get("feature_id", "?"))
            cost = entry.get("cost_usd", 0)
            print(f"  [{icon}] {name}  cost=${cost:.4f}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run PrimeContractorWorkflow against a context seed",
    )
    parser.add_argument(
        "--seed", required=True,
        help="Path to the context seed JSON file (prime-context-seed.json)",
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
        "--task-filter", default=None,
        help=(
            "Comma-separated task IDs to process (e.g. PI-001 or PI-001,PI-002). "
            "Only these tasks will be run."
        ),
    )
    parser.add_argument(
        "--retry-incomplete", action="store_true",
        help=(
            "Auto-discover incomplete tasks by scanning workflow-result files. "
            "Runs only incomplete tasks; exits 0 if all tasks are already complete."
        ),
    )
    parser.add_argument(
        "--max-features", type=int, default=None,
        help="Maximum number of features to process (default: all)",
    )
    parser.add_argument(
        "--lead-agent", default=None,
        help="Lead agent spec (default: from model catalog)",
    )
    parser.add_argument(
        "--drafter-agent", default=None,
        help="Drafter agent spec (default: from model catalog)",
    )
    parser.add_argument(
        "--allow-dirty", action="store_true", default=True,
        help="Proceed even with uncommitted changes in git (default: True for seed-based runs)",
    )
    parser.add_argument(
        "--auto-stash", action="store_true",
        help="Auto-stash uncommitted changes before proceeding",
    )
    parser.add_argument(
        "--force-regenerate", action="store_true",
        help=(
            "Force regeneration of all features, ignoring cached/existing generated files. "
            "Overrides Mottainai reuse logic and staleness detection."
        ),
    )
    parser.add_argument(
        "--mode", choices=["standalone", "pipeline"], default=None,
        help=(
            "Execution mode: 'standalone' (zero-change default) or 'pipeline' "
            "(exploit rich pipeline context). Default: auto-detect from seed content."
        ),
    )
    parser.add_argument(
        "--validate", action="store_true", default=None,
        help="Enable post-generation validation (overrides mode default)",
    )
    parser.add_argument(
        "--no-validate", action="store_true",
        help="Disable post-generation validation (overrides mode default)",
    )
    parser.add_argument(
        "--strict-validation", action="store_true",
        help="Non-zero exit on validation failures (implies --validate)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    # Conflict detection for validation flags
    if args.validate and args.no_validate:
        parser.error("--validate and --no-validate are mutually exclusive")
    if args.strict_validation and args.no_validate:
        parser.error("--strict-validation and --no-validate are mutually exclusive")

    setup_logging(verbose=args.verbose)

    logger = logging.getLogger("run_prime_workflow")

    # Auto-configure OTel
    try:
        from startd8.otel import auto_configure_otel, format_telemetry_banner, get_otel_runtime_state
        otel_state = get_otel_runtime_state()
        logger.info(format_telemetry_banner(otel_state))
        if otel_state["will_configure"]:
            auto_configure_otel()
    except Exception as exc:
        logger.debug("OTel auto-configure skipped: %s", exc)

    # Validate seed path
    seed_path = Path(args.seed)
    if not seed_path.exists():
        logger.error("Seed file not found: %s", seed_path)
        return 1

    # Determine output dir
    output_dir = Path(args.output_dir) if args.output_dir else seed_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    project_root = Path(args.project_root).resolve()

    # ------------------------------------------------------------------
    # Auto-enrich: prefer existing enriched seed, else run preflight
    # ------------------------------------------------------------------
    base_stem = seed_path.stem.removesuffix("-enriched")
    all_suffixes = "".join(seed_path.suffixes)
    enriched_candidate = seed_path.with_name(
        base_stem + "-enriched" + all_suffixes
    )
    if enriched_candidate != seed_path and enriched_candidate.exists():
        base_seed = seed_path.with_name(base_stem + all_suffixes)
        if base_seed.exists() and base_seed.stat().st_mtime > enriched_candidate.stat().st_mtime:
            logger.warning(
                "Enriched seed is stale — will re-run DomainPreflightWorkflow. "
                "base=%s enriched=%s", base_seed, enriched_candidate,
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
        has_enrichment = any(t.get("_enrichment") for t in tasks)
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
                "project_root": str(project_root),
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
                seed_path = enriched_path
            else:
                logger.warning(
                    "DomainPreflightWorkflow failed: %s — continuing with unenriched seed",
                    preflight_result.error,
                )
    except Exception as exc:
        logger.warning(
            "Auto-enrichment check failed: %s — continuing with original seed",
            exc,
        )

    # ------------------------------------------------------------------
    # Auto-discover incomplete tasks (--retry-incomplete)
    # ------------------------------------------------------------------
    task_filter: list[str] | None = None

    if args.retry_incomplete:
        if args.task_filter:
            parser.error("--retry-incomplete and --task-filter are mutually exclusive")
        try:
            seed_tasks = json.loads(seed_path.read_text(encoding="utf-8")).get("tasks", [])
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Cannot read seed for --retry-incomplete: %s", exc)
            return 1

        incomplete: list[str] = []
        complete: list[str] = []

        # Primary source: .prime_contractor_state.json (authoritative queue state)
        state_features: dict[str, Any] = {}
        state_file = project_root / ".prime_contractor_state.json"
        if state_file.exists():
            try:
                state_features = json.loads(
                    state_file.read_text(encoding="utf-8"),
                ).get("features", {})
            except (json.JSONDecodeError, OSError):
                pass

        for t in seed_tasks:
            tid = t["task_id"]
            sf = state_features.get(tid)
            if sf and sf.get("status") == "complete":
                complete.append(tid)
                continue
            # Fallback: check per-task result files
            rp = output_dir / f"prime-result-{tid}.json"
            if rp.exists():
                try:
                    r = json.loads(rp.read_text(encoding="utf-8"))
                    if r.get("success"):
                        complete.append(tid)
                    else:
                        incomplete.append(tid)
                except (json.JSONDecodeError, OSError):
                    incomplete.append(tid)
            else:
                incomplete.append(tid)

        if not incomplete:
            logger.info(
                "All %d tasks have successful results — nothing to retry",
                len(seed_tasks),
            )
            print(f"\nAll {len(seed_tasks)} tasks complete!")
            return 0

        logger.info(
            "Auto-discovered %d incomplete task(s) out of %d: %s",
            len(incomplete), len(seed_tasks), incomplete,
        )
        task_filter = incomplete

    elif args.task_filter:
        task_filter = [t.strip() for t in args.task_filter.split(",") if t.strip()]
        if not task_filter:
            parser.error("--task-filter requires at least one non-empty task ID")

    # ------------------------------------------------------------------
    # Build code generator
    # ------------------------------------------------------------------
    gen_kwargs: dict[str, Any] = {
        "output_dir": output_dir / "generated",
    }
    if args.lead_agent:
        gen_kwargs["lead_agent"] = args.lead_agent
    if args.drafter_agent:
        gen_kwargs["drafter_agent"] = args.drafter_agent

    code_generator = LeadContractorCodeGenerator(**gen_kwargs)

    # ------------------------------------------------------------------
    # Build workflow
    # ------------------------------------------------------------------
    workflow = PrimeContractorWorkflow(
        project_root=project_root,
        dry_run=args.dry_run,
        allow_dirty=args.allow_dirty,
        auto_stash=args.auto_stash,
        code_generator=code_generator,
        cli_mode=args.mode,
    )

    # Load features from seed
    logger.info("Loading features from seed: %s", seed_path)
    added = workflow.queue.add_features_from_seed(seed_path)
    logger.info("Loaded %d features from seed", len(added))

    # Load seed context into the workflow (replaces ad-hoc attribute stashing).
    # Re-read required: seed_path may have changed to an enriched version
    # after the auto-enrichment block above.
    seed_data = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    workflow.load_seed_context(seed_data, cli_mode=args.mode)
    workflow.force_regenerate = args.force_regenerate

    # Wire validation overrides from CLI flags (Phase 5: REQ-PEM-014)
    if args.strict_validation:
        workflow._validation_override = True  # --strict-validation implies --validate
        workflow.strict_validation = True
    elif args.validate:
        workflow._validation_override = True
    elif args.no_validate:
        workflow._validation_override = False

    # Reset failed and blocked features so they are retried.
    # The state file persists FAILED/BLOCKED from prior runs, but the
    # underlying issues may have been fixed in the SDK since then.
    #
    # Mottainai: if a feature already has generated files on disk, reset
    # to GENERATED (not PENDING) so process_feature() skips code generation
    # and goes straight to integration.  This avoids re-spending LLM cost
    # on code that was already produced successfully.
    #
    # Note: error_message is preserved (not cleared) so that process_feature()
    # can inject it as prior_error feedback if the feature is re-generated.
    reset_count = 0
    reuse_count = 0
    for fid, feature in workflow.queue.features.items():
        if feature.status in (FeatureStatus.FAILED, FeatureStatus.BLOCKED):
            has_files = feature.generated_files and all(
                Path(f).exists() for f in feature.generated_files
            )
            if has_files:
                feature.status = FeatureStatus.GENERATED
                reuse_count += 1
            else:
                feature.status = FeatureStatus.PENDING
            feature.integration_attempts = 0
            reset_count += 1
    # Also un-mark features that a prior --task-filter run marked COMPLETE
    # but that are NOT actually complete (no successful result file).  This
    # prevents features from getting stuck in COMPLETE across filter changes.
    for fid, feature in workflow.queue.features.items():
        if feature.status == FeatureStatus.COMPLETE and not feature.completed_at:
            feature.status = FeatureStatus.PENDING
            reset_count += 1
    if reset_count:
        workflow.queue.save_state()
        logger.info(
            "Reset %d failed/blocked feature(s) for retry (%d reusing existing generated files)",
            reset_count, reuse_count,
        )

    # Apply task filter if specified
    if task_filter:
        filter_set = set(task_filter)
        # Mark non-filtered features as complete to skip them
        for fid, feature in workflow.queue.features.items():
            if fid not in filter_set and feature.status in (
                FeatureStatus.PENDING, FeatureStatus.GENERATED,
            ):
                feature.status = FeatureStatus.COMPLETE
        logger.info("Task filter applied: %s (%d task(s))", task_filter, len(task_filter))

    logger.info("Seed: %s", seed_path)
    logger.info("Project root: %s", project_root)
    logger.info("Output dir: %s", output_dir)
    logger.info("Execution mode: %s", workflow.execution_mode)
    logger.info("Dry run: %s", args.dry_run)
    if workflow._validation_override is not None:
        logger.info("Validation override: %s", workflow._validation_override)
    if workflow.strict_validation:
        logger.info("Strict validation: enabled (non-zero exit on failures)")
    if args.cost_budget is not None:
        logger.info("Cost budget: $%.2f", args.cost_budget)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------
    try:
        result = workflow.run(
            max_features=args.max_features,
            max_cost_usd=args.cost_budget,
        )
    except Exception as exc:
        logger.error("Workflow failed: %s", exc, exc_info=True)
        return 1

    # Print results
    print_results(result)

    # Write result JSON
    if task_filter and len(task_filter) == 1:
        result_filename = f"prime-result-{task_filter[0]}.json"
    elif task_filter:
        filter_slug = "-".join(sorted(task_filter))
        result_filename = f"prime-result-{filter_slug}.json"
    else:
        result_filename = "prime-result.json"

    result_path = output_dir / result_filename
    result_data = {
        "processed": result.get("processed", 0),
        "succeeded": result.get("succeeded", 0),
        "failed": result.get("failed", 0),
        "progress": result.get("progress", 0),
        "total_cost_usd": result.get("total_cost_usd", 0),
        "total_input_tokens": result.get("total_input_tokens", 0),
        "total_output_tokens": result.get("total_output_tokens", 0),
        "success": result.get("succeeded", 0) > 0 and not result.get("aborted"),
        "aborted": result.get("aborted", False),
        "abort_reason": result.get("abort_reason"),
        "dry_run": args.dry_run,
        "execution_mode": workflow.execution_mode,
        "seed_path": str(seed_path),
        "task_filter": task_filter,
        "history": result.get("history", []),
    }

    if not args.dry_run:
        result_path.parent.mkdir(parents=True, exist_ok=True)
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, indent=2, default=str)
        logger.info("Wrote result to %s", result_path)
    else:
        logger.info("Dry run — skipping result file write")

    # Return code based on result
    if result.get("aborted"):
        return 1
    if result.get("failed", 0) > 0:
        return 1

    # --strict-validation: non-zero exit if any feature has validation failures
    if args.strict_validation:
        for entry in result.get("history", []):
            validation = entry.get("validation", {})
            if validation.get("failures"):
                logger.error(
                    "Strict validation: feature '%s' has validation failures",
                    entry.get("feature_name", entry.get("feature_id", "?")),
                )
                return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
