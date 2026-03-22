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
import os
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
        "--config", default=None,
        help=(
            "Path to prime-contractor.json config file (F-AC-02). "
            "Consolidates micro-prime, complexity-routing, repair, validation, "
            "and agent settings. Auto-discovered from .startd8/prime-contractor.json "
            "if not specified. CLI args override config file values."
        ),
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
    parser.add_argument(
        "--complexity-loc-complex-min", type=int, default=None,
        help="Override min LOC for COMPLEX tier (default: 500)",
    )
    parser.add_argument(
        "--complexity-blast-radius-complex-threshold", type=int, default=None,
        help="Override blast radius threshold for COMPLEX tier (default: 5)",
    )
    parser.add_argument(
        "--complexity-non-python-trivial-loc-max", type=int, default=None,
        help="Override max LOC for non-Python TRIVIAL tier (default: 100)",
    )
    parser.add_argument(
        "--complexity-non-python-simple-loc-max", type=int, default=None,
        help="Override max LOC for non-Python SIMPLE tier (default: 300)",
    )
    # Micro Prime local generation (REQ-MP-700)
    parser.add_argument(
        "--micro-prime", action="store_true", default=False,
        help="Enable Micro Prime element-by-element generation with LeadContractor fallback (default: off, AC-R4-R3)",
    )
    parser.add_argument(
        "--no-micro-prime", action="store_true",
        help="Disable Micro Prime (use LeadContractor only, redundant when --micro-prime is not passed)",
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
    parser.add_argument(
        "--todo-completion", action="store_true",
        help=(
            "Enable post-generation TODO scan and task completion (REQ-TCW-400). "
            "Also activatable via ENABLE_TODO_COMPLETION=true env var."
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
    # Load consolidated config (F-AC-02), then apply CLI overrides
    # ------------------------------------------------------------------
    from startd8.contractors.prime_contractor_config import (
        apply_cli_overrides,
        load_prime_contractor_config,
    )

    pc_config = load_prime_contractor_config(
        config_path=args.config,
        project_root=project_root,
    )
    pc_config = apply_cli_overrides(pc_config, args)

    # ------------------------------------------------------------------
    # Prefer enriched seed if available (F-AC-06: enrichment now upstream)
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
                "Enriched seed is stale (base newer than enriched). "
                "Re-run plan-ingestion to refresh enrichment. "
                "Proceeding with base seed: %s", base_seed,
            )
        else:
            logger.info(
                "Using enriched seed: %s",
                enriched_candidate,
            )
            seed_path = enriched_candidate
    else:
        # Check if enrichment is missing
        try:
            _check_data = json.loads(seed_path.read_text(encoding="utf-8"))
            _tasks = _check_data.get("tasks", [])
            if _tasks and not any(t.get("_enrichment") for t in _tasks):
                logger.warning(
                    "Seed lacks domain enrichment. For best results, "
                    "re-run plan-ingestion (enrichment is now applied upstream). "
                    "Proceeding without enrichment."
                )
        except (json.JSONDecodeError, OSError):
            pass  # Seed will be validated below

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
    # Build code generator (uses pc_config.agents for agent specs)
    # ------------------------------------------------------------------
    gen_kwargs: dict[str, Any] = {
        "output_dir": output_dir / "generated",
    }
    if pc_config.agents.lead:
        gen_kwargs["lead_agent"] = pc_config.agents.lead
    if pc_config.agents.drafter:
        gen_kwargs["drafter_agent"] = pc_config.agents.drafter

    code_generator = LeadContractorCodeGenerator(**gen_kwargs)

    # ------------------------------------------------------------------
    # Build workflow (uses pc_config for repair)
    # ------------------------------------------------------------------
    # Post-generation repair pipeline (REQ-RPL-200)
    repair_config = None
    if pc_config.repair_enabled:
        from startd8.repair.config import RepairConfig
        repair_config = RepairConfig(**{
            k: v for k, v in pc_config.repair.items()
            if k in RepairConfig.__dataclass_fields__
        }) if pc_config.repair else RepairConfig()
    else:
        logger.info("Repair pipeline: disabled")

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
    workflow.force_regenerate = args.force_regenerate or pc_config.micro_prime.get("dry_run", False)

    # ------------------------------------------------------------------
    # Wire subsystems from pc_config (F-AC-02: consolidated config)
    # ------------------------------------------------------------------

    # Micro Prime (REQ-MP-710) — must be called BEFORE complexity routing
    if pc_config.micro_prime_enabled:
        from startd8.micro_prime.config_loader import load_micro_prime_settings
        from startd8.micro_prime.models import MicroPrimeConfig

        # Load .startd8/micro_prime.json as base, then overlay config values
        base_config, _cloud_agent_spec = load_micro_prime_settings(
            workflow.project_root,
        )
        mp_config_kwargs: dict[str, Any] = base_config.model_dump()
        # Config file and CLI overrides (already merged in pc_config.micro_prime)
        mp_config_kwargs.update({
            k: v for k, v in pc_config.micro_prime.items()
            if k in MicroPrimeConfig.model_fields
        })
        workflow.enable_micro_prime(config=MicroPrimeConfig(**mp_config_kwargs))

    # Complexity routing (REQ-MP-807)
    if pc_config.complexity_routing_enabled:
        # Use pre-parsed config from _parse_config() + CLI overrides
        cr_config = pc_config.complexity_config
        # REQ-MP-700: Route TRIVIAL/SIMPLE through MicroPrime when both enabled
        mp_generator = workflow.code_generator if pc_config.micro_prime_enabled else None
        workflow.enable_complexity_routing(
            config=cr_config,
            tier3_agent=pc_config.agents.tier3,
            trivial_generator=mp_generator,
            simple_generator=mp_generator,
        )

    # Validation (Phase 5: REQ-PEM-014)
    if pc_config.validation.strict:
        workflow._validation_override = True
        workflow.strict_validation = True
    elif pc_config.validation.enabled is True:
        workflow._validation_override = True
    elif pc_config.validation.enabled is False:
        workflow._validation_override = False

    # Wire Kaizen prompt capture (REQ-KZ-200, 201, 204)
    if args.kaizen:
        kaizen_dir = (
            Path(args.kaizen_dir).resolve()
            if args.kaizen_dir
            else output_dir / "kaizen-prompts"
        )
        kaizen_dir.mkdir(parents=True, exist_ok=True)
        workflow._kaizen.enabled = True
        workflow._kaizen.prompt_dir = kaizen_dir
        # Expose redaction config path via env so _load_redaction_config() can read it
        # without requiring an additional constructor argument (consistent with R2-S7).
        if args.kaizen_redactions:
            import os as _os
            _os.environ["KAIZEN_REDACTIONS"] = str(Path(args.kaizen_redactions).resolve())

    # Wire Kaizen config hint injection (REQ-KZ-502)
    if args.kaizen_config:
        workflow._kaizen.config = workflow._load_kaizen_config(args.kaizen_config)

    # Wire TODO completion (REQ-TCW-400)
    _todo_env = os.environ.get("ENABLE_TODO_COMPLETION", "").lower()
    if _todo_env == "true" or getattr(args, "todo_completion", False):
        workflow.enable_todo_completion()

    # ------------------------------------------------------------------
    # Reset failed/blocked features for retry (F-AC-03 simplified)
    # ------------------------------------------------------------------
    # Mottainai: reuse existing generated files when possible.
    # error_message preserved for prior_error feedback on retry.
    reset_count = 0
    reuse_count = 0
    for fid, feature in workflow.queue.features.items():
        if feature.status in (
            FeatureStatus.FAILED, FeatureStatus.BLOCKED, FeatureStatus.DEVELOPING,
            FeatureStatus.INTEGRATING,
        ):
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
    if reset_count:
        workflow.queue.save_state()
        logger.info(
            "Reset %d failed/blocked feature(s) for retry (%d reusing existing generated files)",
            reset_count, reuse_count,
        )

    # ------------------------------------------------------------------
    # Apply task filter via skip set (F-AC-03: no status mutation)
    # ------------------------------------------------------------------
    if task_filter:
        filter_set = set(task_filter)
        # --force-regenerate + --task-filter: reset filtered COMPLETE
        # features to PENDING so they are re-processed.
        if workflow.force_regenerate:
            for fid in filter_set:
                feature = workflow.queue.features.get(fid)
                if feature and feature.status == FeatureStatus.COMPLETE:
                    feature.status = FeatureStatus.PENDING
                    feature.integration_attempts = 0
                    logger.info(
                        "Force-regenerate: reset COMPLETE feature %s to PENDING",
                        fid,
                    )
        # F-AC-03: Use skip set instead of mutating status to COMPLETE.
        # Non-filtered features are skipped at runtime without persisting
        # fake COMPLETE status that corrupts subsequent runs.
        skip_ids = {
            fid for fid in workflow.queue.features
            if fid not in filter_set
        }
        workflow.queue.set_skip_ids(skip_ids)
        logger.info("Task filter applied: %s (%d task(s))", task_filter, len(task_filter))

    logger.info("Seed: %s", seed_path)
    logger.info("Project root: %s", project_root)
    logger.info("Output dir: %s", output_dir)
    logger.debug("Execution mode: %s (also logged by load_seed_context)", workflow.execution_mode)
    logger.info("Dry run: %s", args.dry_run)
    if pc_config.micro_prime_enabled:
        logger.info("Micro Prime: enabled (model=%s)", pc_config.micro_prime.get("model", "default"))
    if pc_config.micro_prime.get("dry_run"):
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
            workflow._kaizen.prompt_dir,
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
