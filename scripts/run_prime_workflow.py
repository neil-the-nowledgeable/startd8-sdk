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

    # With auto-commit (commit each feature after integration):
    python3 scripts/run_prime_workflow.py \
        --seed out/project/plan-ingestion/prime-context-seed.json \
        --project-root /path/to/target/project \
        --auto-commit
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
        "--auto-commit", action="store_true",
        help="Commit each feature's integrated code to git after successful integration",
    )
    parser.add_argument(
        "--force-regenerate", action="store_true",
        help=(
            "Force regeneration of all features, ignoring cached/existing generated files. "
            "Overrides Mottainai reuse logic and staleness detection."
        ),
    )
    parser.add_argument(
        "--walkthrough", action="store_true",
        help="Build and persist all LLM prompts without calling LLMs",
    )
    parser.add_argument(
        "--walkthrough-postmortem", action="store_true",
        help="Run post-mortem evaluation on persisted walkthrough prompts",
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
    # Complexity routing (REQ-MP-807)
    parser.add_argument(
        "--complexity-routing", action="store_true",
        help="Enable per-feature complexity-based model routing",
    )
    parser.add_argument(
        "--tier3-agent", default=None,
        help="Agent spec for COMPLEX tier (e.g. anthropic:claude-opus-4-6)",
    )
    parser.add_argument(
        "--complexity-loc-simple-max", type=int, default=None,
        help="Override max LOC for SIMPLE tier (default: 150)",
    )
    # Micro Prime local generation (REQ-MP-700)
    parser.add_argument(
        "--micro-prime", action="store_true", default=True,
        help="Enable Micro Prime as primary generator with LeadContractor fallback (default: on)",
    )
    parser.add_argument(
        "--no-micro-prime", action="store_true",
        help="Disable Micro Prime (use LeadContractor only)",
    )
    parser.add_argument(
        "--micro-prime-model", default=None,
        help="Ollama model name for Micro Prime (default: startd8-coder)",
    )
    parser.add_argument(
        "--micro-prime-max-tokens", type=int, default=None,
        help="Max output tokens per element for Micro Prime (default: 512)",
    )
    parser.add_argument(
        "--micro-prime-no-templates", action="store_true",
        help="Disable Micro Prime template registry (force all through Ollama)",
    )
    parser.add_argument(
        "--micro-prime-no-repair", action="store_true",
        help="Disable Micro Prime repair pipeline",
    )
    parser.add_argument(
        "--micro-prime-dry-run", action="store_true",
        help="Classify elements and check Ollama without generating code",
    )
    parser.add_argument(
        "--micro-prime-cloud-retry-attempts", type=int, default=None,
        help=(
            "Max attempts for cloud escalation per element "
            "(default: 1)"
        ),
    )
    parser.add_argument(
        "--micro-prime-cloud-retry-strategy",
        choices=["same_prompt", "append_error"],
        default=None,
        help=(
            "Retry strategy for cloud escalation "
            "(default: same_prompt)"
        ),
    )
    parser.add_argument(
        "--micro-prime-cloud-retry-max-chars", type=int, default=None,
        help=(
            "Max chars for appended retry context "
            "(default: 512)"
        ),
    )
    # Post-generation repair pipeline (REQ-RPL-200) — enabled by default
    parser.add_argument(
        "--repair", action="store_true", default=True,
        help="Enable post-generation repair pipeline (default: on)",
    )
    parser.add_argument(
        "--no-repair", action="store_true",
        help="Disable post-generation repair pipeline",
    )
    # Kaizen prompt capture (REQ-KZ-200, 201, 204)
    parser.add_argument(
        "--kaizen", action="store_true",
        help=(
            "Enable Kaizen prompt and response capture. Persists LLM prompts "
            "and raw responses to --kaizen-dir/{run_id}/{feature_id}/ for "
            "post-run analysis (REQ-KZ-200, 201)."
        ),
    )
    parser.add_argument(
        "--kaizen-dir", default=None,
        help=(
            "Directory for Kaizen prompt capture output "
            "(default: <output-dir>/kaizen-prompts). "
            "Used only when --kaizen is set."
        ),
    )
    parser.add_argument(
        "--kaizen-redactions", default=None,
        help=(
            "Path to a JSON file containing redaction regex patterns (REQ-KZ-204). "
            "Format: list of regex strings, or {\"patterns\": [...]}. "
            "Matched text in captured responses is replaced with [REDACTED]."
        ),
    )
    parser.add_argument(
        "--kaizen-config", default=None,
        help=(
            "Path to kaizen-config.json for prompt hint injection (REQ-KZ-502). "
            "Hints in the config are injected into LLM prompts to improve successive runs."
        ),
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
    output_dir = Path(args.output_dir).resolve() if args.output_dir else seed_path.parent.resolve()
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
    # Post-generation repair pipeline (REQ-RPL-200)
    repair_config = None
    if not args.no_repair:
        from startd8.repair.config import RepairConfig
        repair_config = RepairConfig()
    else:
        logger.info("Repair pipeline: disabled (--no-repair)")

    workflow = PrimeContractorWorkflow(
        project_root=project_root,
        dry_run=args.dry_run,
        allow_dirty=args.allow_dirty,
        auto_stash=args.auto_stash,
        auto_commit=args.auto_commit,
        code_generator=code_generator,
        cli_mode=args.mode,
        walkthrough=args.walkthrough,
        repair_config=repair_config,
    )

    # Load features from seed
    logger.info("Loading features from seed: %s", seed_path)
    added = workflow.queue.add_features_from_seed(seed_path)
    logger.info("Loaded %d features from seed", len(added))

    # Load seed context into the workflow (replaces ad-hoc attribute stashing).
    # Re-read required: seed_path may have changed to an enriched version
    # after the auto-enrichment block above.
    seed_data = json.loads(Path(seed_path).read_text(encoding="utf-8"))
    workflow.load_seed_context(seed_data, cli_mode=args.mode, seed_path=str(seed_path))
    workflow.force_regenerate = args.force_regenerate or args.micro_prime_dry_run

    # Wire Micro Prime via workflow API (REQ-MP-710)
    # Must be called BEFORE enable_complexity_routing() so the router
    # sees the wrapped generator.
    # --no-micro-prime overrides the default; --micro-prime-dry-run implies --micro-prime
    if args.no_micro_prime:
        args.micro_prime = False
    if args.micro_prime_dry_run:
        args.micro_prime = True
    if args.micro_prime:
        from startd8.micro_prime.config_loader import load_micro_prime_settings
        from startd8.micro_prime.models import MicroPrimeConfig

        # Load .startd8/micro_prime.json as base, then overlay CLI args.
        # This ensures project-level settings (e.g. escalation_enabled=false)
        # are respected even when CLI flags are passed.
        base_config, _cloud_agent_spec = load_micro_prime_settings(
            workflow.project_root,
        )
        mp_config_kwargs: dict[str, Any] = base_config.model_dump()

        # CLI args override file-based settings
        if args.micro_prime_model is not None:
            mp_config_kwargs["model"] = args.micro_prime_model
        if args.micro_prime_max_tokens is not None:
            mp_config_kwargs["max_tokens"] = args.micro_prime_max_tokens
        if args.micro_prime_no_templates:
            mp_config_kwargs["templates_enabled"] = False
        if args.micro_prime_no_repair:
            mp_config_kwargs["repair_enabled"] = False
        if args.micro_prime_cloud_retry_attempts is not None:
            mp_config_kwargs["cloud_escalation_max_attempts"] = (
                args.micro_prime_cloud_retry_attempts
            )
        if args.micro_prime_cloud_retry_strategy is not None:
            mp_config_kwargs["cloud_escalation_retry_strategy"] = (
                args.micro_prime_cloud_retry_strategy
            )
        if args.micro_prime_cloud_retry_max_chars is not None:
            mp_config_kwargs["cloud_escalation_retry_max_chars"] = (
                args.micro_prime_cloud_retry_max_chars
            )
        if args.micro_prime_dry_run:
            mp_config_kwargs["dry_run"] = True

        workflow.enable_micro_prime(config=MicroPrimeConfig(**mp_config_kwargs))

    # Wire complexity routing from CLI flags (REQ-MP-807)
    if args.complexity_routing:
        cr_config = None
        if args.complexity_loc_simple_max is not None:
            from startd8.complexity import ComplexityRoutingConfig
            cr_config = ComplexityRoutingConfig(
                loc_simple_max=args.complexity_loc_simple_max,
            )
        # REQ-MP-700: When both --micro-prime and --complexity-routing are set,
        # route TRIVIAL/SIMPLE tiers through the wrapped MicroPrimeCodeGenerator.
        mp_generator = workflow.code_generator if args.micro_prime else None
        workflow.enable_complexity_routing(
            config=cr_config,
            tier3_agent=args.tier3_agent,
            trivial_generator=mp_generator,
            simple_generator=mp_generator,
        )

    # Wire validation overrides from CLI flags (Phase 5: REQ-PEM-014)
    if args.strict_validation:
        workflow._validation_override = True  # --strict-validation implies --validate
        workflow.strict_validation = True
    elif args.validate:
        workflow._validation_override = True
    elif args.no_validate:
        workflow._validation_override = False

    # Wire Kaizen prompt capture (REQ-KZ-200, 201, 204)
    if args.kaizen:
        kaizen_dir = (
            Path(args.kaizen_dir).resolve()
            if args.kaizen_dir
            else output_dir / "kaizen-prompts"
        )
        kaizen_dir.mkdir(parents=True, exist_ok=True)
        workflow._kaizen_enabled = True
        workflow._kaizen_prompt_dir = kaizen_dir
        # Expose redaction config path via env so _load_redaction_config() can read it
        # without requiring an additional constructor argument (consistent with R2-S7).
        if args.kaizen_redactions:
            import os as _os
            _os.environ["KAIZEN_REDACTIONS"] = str(Path(args.kaizen_redactions).resolve())

    # Wire Kaizen config hint injection (REQ-KZ-502)
    if args.kaizen_config:
        workflow._kaizen_config = workflow._load_kaizen_config(args.kaizen_config)

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
        if feature.status in (
            FeatureStatus.FAILED, FeatureStatus.BLOCKED, FeatureStatus.DEVELOPING,
        ):
            # DEVELOPING means generation was interrupted — files are stale,
            # always regenerate.  --force-regenerate also overrides Mottainai
            # reuse for FAILED/BLOCKED.
            if feature.status == FeatureStatus.DEVELOPING or workflow.force_regenerate:
                feature.status = FeatureStatus.PENDING
            else:
                has_files = feature.generated_files and all(
                    (Path(f) if Path(f).is_absolute() else Path(f).resolve()).exists()
                    for f in feature.generated_files
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
    logger.debug("Execution mode: %s (also logged by load_seed_context)", workflow.execution_mode)
    logger.info("Dry run: %s", args.dry_run)
    if args.micro_prime:
        logger.info("Micro Prime: enabled (model=%s)", args.micro_prime_model or "default")
    if args.micro_prime_dry_run:
        logger.info("Micro Prime dry-run: classification only, no code generation")
    if repair_config is not None:
        logger.info("Repair pipeline: enabled (categories=%s)", sorted(repair_config.repairable_categories))
    if workflow._validation_override is not None:
        logger.info("Validation override: %s", workflow._validation_override)
    if workflow.strict_validation:
        logger.info("Strict validation: enabled (non-zero exit on failures)")
    if args.cost_budget is not None:
        logger.info("Cost budget: $%.2f", args.cost_budget)
    if args.kaizen:
        logger.info(
            "Kaizen: enabled (dir=%s, redactions=%s)",
            workflow._kaizen_prompt_dir,
            args.kaizen_redactions or "none",
        )

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

    # Walkthrough postmortem
    if args.walkthrough and args.walkthrough_postmortem:
        try:
            from startd8.contractors.postmortem import (
                launch_walkthrough_postmortem_async,
            )

            walkthrough_root = str(project_root / ".startd8" / "walkthrough")
            thread = launch_walkthrough_postmortem_async(
                seed_path=str(seed_path),
                workflow_result=result,
                walkthrough_root=walkthrough_root,
                output_dir=str(output_dir),
            )
            thread.join(timeout=120)
            logger.info("Walkthrough postmortem completed")
        except Exception as exc:
            logger.warning("Walkthrough postmortem failed: %s", exc, exc_info=True)

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
        "walkthrough": args.walkthrough,
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
