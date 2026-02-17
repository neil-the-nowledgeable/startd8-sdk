#!/usr/bin/env python3
"""
Run a design-only workflow: PLAN → SCAFFOLD → DESIGN.

Convenience wrapper around ArtisanContractorWorkflow that stops after
generating design documents — no code generation, testing, or review.

Usage:
    python3 scripts/run_artisan_design_only.py \
        --seed out/artisan-context-seed-enriched.json \
        --output-dir out/designs \
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

from startd8.contractors.artisan_contractor import (
    ArtisanContractorWorkflow,
    WorkflowConfig,
    WorkflowPhase,
    WorkflowStatus,
)
from startd8.contractors.context_seed_handlers import ContextSeedHandlers
from startd8.contractors.handoff import write_design_handoff


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
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run design-only workflow (PLAN → SCAFFOLD → DESIGN)",
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
        help="Output directory for design docs (default: same dir as seed)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulate execution without side effects",
    )
    parser.add_argument(
        "--lead-agent", default=None,
        help="Lead agent spec for design generation",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--abort-on-preflight-fail", action="store_true",
        help="Abort PLAN phase if preflight checks report any failures",
    )

    args = parser.parse_args()
    setup_logging(verbose=args.verbose)

    logger = logging.getLogger("run_artisan_design_only")

    seed_path = Path(args.seed)
    if not seed_path.exists():
        logger.error("Seed file not found: %s", seed_path)
        return 1

    output_dir = args.output_dir or str(seed_path.parent)

    config = WorkflowConfig(
        dry_run=args.dry_run,
        project_root=str(Path(args.project_root).resolve()),
        metadata={
            "seed_path": str(seed_path),
            "runner": "run_artisan_design_only.py",
        },
    )

    phases = [WorkflowPhase.PLAN, WorkflowPhase.SCAFFOLD, WorkflowPhase.DESIGN]
    workflow = ArtisanContractorWorkflow(config=config, phases=phases)

    handler_kwargs: dict = {
        "enriched_seed_path": str(seed_path.resolve()),
        "output_dir": output_dir,
    }
    if args.lead_agent:
        handler_kwargs["lead_agent"] = args.lead_agent

    handlers = ContextSeedHandlers.create_all(**handler_kwargs)
    for wp_phase, handler in handlers.items():
        workflow.register_handler(wp_phase, handler)

    initial_context: dict = {"enriched_seed_path": str(seed_path.resolve())}
    if args.abort_on_preflight_fail:
        initial_context["abort_on_preflight_fail"] = True

    logger.info("Workflow ID: %s", config.workflow_id)
    logger.info("Design-only: phases=%s", [p.value for p in phases])

    try:
        result = workflow.execute(context=initial_context)
    except Exception as exc:
        logger.error("Workflow failed: %s", exc, exc_info=True)
        return 1

    # Write handoff for the second half (IMPLEMENT → FINALIZE)
    if result.status == WorkflowStatus.COMPLETED and not args.dry_run:
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
            source_checksum=initial_context.get("source_checksum"),
        )
        logger.info("Wrote design handoff: %s", handoff_path)

    # Print summary
    print(f"\nDesign-only workflow: {result.status.value}")
    print(f"Duration: {result.total_duration_seconds:.2f}s  Cost: ${result.total_cost:.4f}")
    for pr in result.phase_results:
        icon = {"completed": "+", "dry_run": "~", "skipped": "-", "failed": "X"}.get(
            pr.status.value, "?"
        )
        print(f"  [{icon}] {pr.phase.value:10s}  {pr.status.value}  ${pr.cost:.4f}")
        if pr.phase == WorkflowPhase.DESIGN and pr.output and isinstance(pr.output, dict):
            print(f"      Designed: {pr.output.get('tasks_designed', '?')}")
            print(f"      Agreed:   {pr.output.get('tasks_agreed', '?')}")
            if pr.output.get("output_dir"):
                print(f"      Output:   {pr.output['output_dir']}")

    return 0 if result.status == WorkflowStatus.COMPLETED else 1


if __name__ == "__main__":
    sys.exit(main())
