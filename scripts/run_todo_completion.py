#!/usr/bin/env python3
"""Run the TodoCompletionWorkflow from the CLI (REQ-TCW-400).

Scans generated code for TODO stubs, derives completion tasks, and
optionally executes them via PrimeContractor.

Usage:
    # Scan only (default):
    python3 scripts/run_todo_completion.py \
        --project-root /path/to/generated/code \
        --output-dir /tmp/out

    # With execution:
    python3 scripts/run_todo_completion.py \
        --project-root /path/to/generated/code \
        --output-dir /tmp/out --execute

    # Category A only:
    python3 scripts/run_todo_completion.py \
        --project-root /path/to/generated/code \
        --output-dir /tmp/out --categories A
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


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the workflow run."""
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
    logging.basicConfig(level=level, format=fmt, datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def build_config(args: argparse.Namespace) -> dict[str, Any]:
    """Build workflow config from parsed CLI arguments.

    Extracted as a standalone function for testability.
    """
    config: dict[str, Any] = {
        "scan_dir": args.project_root,
        "output_dir": args.output_dir,
        "source_run_id": args.source_run_id or "",
        "categories": args.categories,
        "execute": args.execute and not args.scan_only,
        "max_tasks": args.max_tasks,
    }

    # Load instrumentation contract if provided
    if args.instrumentation_contract:
        contract_path = Path(args.instrumentation_contract)
        if contract_path.exists():
            try:
                config["instrumentation_contract"] = json.loads(
                    contract_path.read_text(encoding="utf-8"),
                )
            except (json.JSONDecodeError, OSError) as exc:
                logging.getLogger("run_todo_completion").warning(
                    "Could not load instrumentation contract %s: %s",
                    contract_path, exc,
                )

    return config


def print_summary(result_output: dict[str, Any]) -> None:
    """Print a human-readable summary of the workflow result."""
    print("\n" + "=" * 60)
    print("TODO COMPLETION WORKFLOW RESULTS")
    print("=" * 60)
    print(f"  TODOs found:     {result_output.get('todo_count', 0)}")
    print(f"    Category A:    {result_output.get('todo_count_a', 0)}")
    print(f"    Category B:    {result_output.get('todo_count_b', 0)}")
    print(f"  Tasks derived:   {result_output.get('task_count', 0)}")
    print(f"  Executed:        {result_output.get('executed', False)}")
    if result_output.get("execution"):
        exec_info = result_output["execution"]
        print(f"  Execution:       success={exec_info.get('success', '?')}")
    print("=" * 60)
    print()


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        description="Run TODO Completion Workflow (REQ-TCW-400)",
    )
    parser.add_argument(
        "--project-root", required=True,
        help="Directory to scan for TODOs (the generated code)",
    )
    parser.add_argument(
        "--output-dir", required=True,
        help="Where to write todo-inventory.json, instrumentation-seed.json, etc.",
    )
    parser.add_argument(
        "--source-run-id", default=None,
        help="Pass-one run ID for traceability",
    )
    parser.add_argument(
        "--categories", default="A,B",
        help="Comma-separated category filter (default: A,B)",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="Run derived tasks via PrimeContractor (without this, scan-only)",
    )
    parser.add_argument(
        "--scan-only", action="store_true",
        help="Explicit scan-only (overrides --execute if both given)",
    )
    parser.add_argument(
        "--max-tasks", type=int, default=20,
        help="Cap on derived task count (default: 20)",
    )
    parser.add_argument(
        "--instrumentation-contract", default=None,
        help="Path to JSON file with instrumentation contract",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print config and exit without running the workflow",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(verbose=args.verbose)
    logger = logging.getLogger("run_todo_completion")

    config = build_config(args)

    if args.dry_run:
        print("Dry run — config:")
        print(json.dumps(config, indent=2, default=str))
        return 0

    # Import workflow
    from startd8.workflows.builtin.todo_completion_workflow import (  # noqa: E402
        TodoCompletionWorkflow,
    )

    workflow = TodoCompletionWorkflow()

    # Validate
    validation = workflow.validate_config(config)
    if not validation.valid:
        for err in validation.errors:
            logger.error("Config error: %s", err)
        return 1

    # Execute
    try:
        result = workflow.run(config)
    except Exception as exc:
        logger.error("Workflow failed: %s", exc, exc_info=True)
        return 1

    # Print summary
    result_output = result.output or {}
    print_summary(result_output)

    # Write result JSON
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "instrumentation-result.json"
    result_path.write_text(
        json.dumps(result_output, indent=2, default=str), encoding="utf-8",
    )
    logger.info("Wrote result to %s", result_path)

    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
