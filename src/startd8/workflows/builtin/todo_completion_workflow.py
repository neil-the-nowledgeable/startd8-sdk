"""TODO Completion Workflow (REQ-TCW-200–303).

Scans generated code for TODO stubs, classifies them, derives completion
tasks, and optionally executes them via Prime Contractor in edit mode.

Phases:
1. Scan — run todo_scanner on generated files
2. Plan — run todo_derivation to create seed tasks
3. Execute — (optional) run Prime Contractor with the generated seed
4. Report — write inventory + plan to output directory
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from startd8.logging_config import get_logger
from startd8.workflows.models import (
    ValidationResult,
    WorkflowMetadata,
    WorkflowMetrics,
    WorkflowResult,
    WorkflowInput,
)

if TYPE_CHECKING:
    from startd8.agents import BaseAgent
    from startd8.workflows.base import ProgressCallback

logger = get_logger(__name__)

__all__ = ["TodoCompletionWorkflow"]


class TodoCompletionWorkflow:
    """Scan, plan, and optionally execute TODO completion tasks.

    Config keys:
        scan_dir (str): Directory containing generated files to scan.
        output_dir (str): Directory for inventory + plan output.
        source_run_id (str): ID of the pass-one run that produced the code.
        instrumentation_contract (dict): Optional per-service contract.
        categories (str): Comma-separated categories to process (default: "A,B").
        execute (bool): Whether to execute the plan (default: False = scan only).
        max_tasks (int): Maximum number of tasks in the plan (default: 20).
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="todo-completion",
            name="TODO Completion Workflow",
            description=(
                "Scan generated code for TODO stubs, classify them, "
                "derive completion tasks, and execute via Prime Contractor."
            ),
            capabilities=["instrumentation", "todo-resolution", "code-quality"],
            inputs=[
                WorkflowInput(
                    name="scan_dir",
                    type="text",
                    required=True,
                    description="Directory containing generated files to scan",
                ),
                WorkflowInput(
                    name="output_dir",
                    type="text",
                    required=True,
                    description="Directory for output artifacts",
                ),
                WorkflowInput(
                    name="source_run_id",
                    type="text",
                    required=False,
                    description="ID of the pass-one run",
                ),
                WorkflowInput(
                    name="categories",
                    type="text",
                    required=False,
                    description="Categories to process: A, B, or A,B (default: A,B)",
                ),
                WorkflowInput(
                    name="execute",
                    type="text",
                    required=False,
                    description="Execute the plan via Prime Contractor (default: false)",
                ),
            ],
        )

    def validate_config(self, config: Dict[str, Any]) -> ValidationResult:
        errors: List[str] = []
        if not config.get("scan_dir"):
            errors.append("Missing required input: scan_dir")
        if not config.get("output_dir"):
            errors.append("Missing required input: output_dir")
        if errors:
            return ValidationResult(valid=False, errors=errors)
        return ValidationResult(valid=True, errors=[])

    def run(
        self,
        config: Dict[str, Any],
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> WorkflowResult:
        """Execute the TODO completion workflow."""
        scan_dir = config["scan_dir"]
        output_dir = config["output_dir"]
        source_run_id = config.get("source_run_id", "")
        categories_str = config.get("categories", "A,B")
        execute = config.get("execute", False)
        max_tasks = config.get("max_tasks", 20)
        instrumentation_contract = config.get("instrumentation_contract")

        categories = {c.strip().upper() for c in str(categories_str).split(",")}

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # --- Phase 1: Scan ---
        if on_progress:
            on_progress(1, 4, "Scanning for TODOs...")

        from startd8.validators.todo_scanner import scan_directory
        inventory = scan_directory(
            scan_dir,
            instrumentation_contract=instrumentation_contract,
        )

        # Filter by requested categories
        inventory.entries = [
            e for e in inventory.entries if e.category in categories
        ]
        inventory.compute_summary()

        logger.info(
            "TODO scan: %d entries (A=%d, B=%d, C=%d)",
            inventory.summary.get("total", 0),
            inventory.summary.get("A", 0),
            inventory.summary.get("B", 0),
            inventory.summary.get("C", 0),
        )

        # Save inventory
        inventory.save(out / "todo-inventory.json")

        if not inventory.entries:
            return WorkflowResult(
                workflow_id="todo-completion",
                success=True,
                output={"message": "No TODOs found matching categories", "todo_count": 0},
                metadata={"todo_count": 0},
            )

        # --- Phase 2: Plan ---
        if on_progress:
            on_progress(2, 4, "Generating completion plan...")

        from startd8.seeds.todo_derivation import derive_tasks_from_todos
        tasks = derive_tasks_from_todos(
            inventory,
            instrumentation_contract=instrumentation_contract,
            source_run_id=source_run_id,
        )

        # Enforce max_tasks limit
        if len(tasks) > max_tasks:
            logger.warning(
                "Plan has %d tasks, limiting to %d (prioritizing Category A)",
                len(tasks), max_tasks,
            )
            tasks = tasks[:max_tasks]

        # Write the seed
        seed = {
            "schema_version": "1.0.0",
            "source": "todo-completion-workflow",
            "source_run_id": source_run_id,
            "tasks": tasks,
        }
        seed_path = out / "instrumentation-seed.json"
        seed_path.write_text(
            json.dumps(seed, indent=2, default=str), encoding="utf-8",
        )
        logger.info("Completion plan: %s (%d tasks)", seed_path, len(tasks))

        # --- Phase 3: Execute (optional) ---
        executed = False
        execution_result = None
        if execute and tasks:
            if on_progress:
                on_progress(3, 4, "Executing completion tasks...")

            try:
                execution_result = self._execute_plan(
                    seed, output_dir, agents, config,
                )
                executed = True
            except Exception as exc:
                logger.warning("Execution failed: %s", exc, exc_info=True)
                execution_result = {"error": str(exc), "error_type": type(exc).__name__}
        elif on_progress:
            on_progress(3, 4, "Skipping execution (scan-only mode)")

        # --- Phase 4: Report ---
        if on_progress:
            on_progress(4, 4, "Writing report...")

        result_output = {
            "todo_count": inventory.summary.get("total", 0),
            "todo_count_a": inventory.summary.get("A", 0),
            "todo_count_b": inventory.summary.get("B", 0),
            "task_count": len(tasks),
            "executed": executed,
            "seed_path": str(seed_path),
            "inventory_path": str(out / "todo-inventory.json"),
        }
        if execution_result:
            result_output["execution"] = execution_result

        return WorkflowResult(
            workflow_id="todo-completion",
            success=True,
            output=result_output,
            metadata={
                "todo_count": inventory.summary.get("total", 0),
                "todo_count_a": inventory.summary.get("A", 0),
                "todo_count_b": inventory.summary.get("B", 0),
                "task_count": len(tasks),
                "executed": executed,
            },
        )

    def _execute_plan(
        self,
        seed: Dict[str, Any],
        output_dir: str,
        agents: Optional[List[Any]],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute the completion plan via Prime Contractor.

        This is a thin wrapper that delegates to PrimeContractorWorkflow
        with the generated seed, running in edit mode.

        Returns:
            Dict with ``success``, ``status``, and ``output_dir`` keys.

        Raises:
            Exception: Propagated from PrimeContractorWorkflow if execution fails.
        """
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        instrumentation_dir = str(Path(output_dir) / "instrumentation")
        Path(instrumentation_dir).mkdir(parents=True, exist_ok=True)

        prime_config = {
            "seed": seed,
            "output_dir": instrumentation_dir,
            "project_root": config.get("scan_dir", "."),
            "source": "instrumentation",
            "parent_run_id": seed.get("source_run_id", ""),
        }

        workflow = PrimeContractorWorkflow()
        result = workflow.run(prime_config, agents=agents)

        return {
            "success": result.success,
            "status": str(result.status),
            "output_dir": instrumentation_dir,
        }
