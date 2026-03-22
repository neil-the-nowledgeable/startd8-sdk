"""TODO Completion Workflow — DEPRECATED (v3).

.. deprecated:: 0.4.0
    This standalone workflow is superseded by in-band TODO completion in
    ``PrimeContractorWorkflow`` (REQ-TCW v3.0.0).  Use
    ``workflow.enable_todo_completion()`` on the Prime Contractor instance
    instead.  The scan-only (no execution) mode is preserved below for
    backward compatibility with existing scripts.

See ``docs/design/prime/TODO_COMPLETION_WORKFLOW_REQUIREMENTS.md`` v3.0.0.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from startd8.logging_config import get_logger
from startd8.workflows.models import (
    ValidationResult,
    WorkflowMetadata,
    WorkflowResult,
    WorkflowInput,
)

if TYPE_CHECKING:
    from startd8.agents import BaseAgent
    from startd8.workflows.base import ProgressCallback

logger = get_logger(__name__)

__all__ = ["TodoCompletionWorkflow"]


class TodoCompletionWorkflow:
    """Scan generated code for TODO stubs and produce an inventory.

    .. deprecated:: 0.4.0
        Execution is now handled by ``PrimeContractorWorkflow.enable_todo_completion()``.
        This class is retained only for scan-only mode (inventory + plan generation
        without execution).
    """

    @property
    def metadata(self) -> WorkflowMetadata:
        return WorkflowMetadata(
            workflow_id="todo-completion",
            name="TODO Completion Workflow (deprecated — use Prime Contractor)",
            description=(
                "Scan generated code for TODO stubs and produce inventory. "
                "Execution is now handled by PrimeContractorWorkflow."
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
        """Scan-only TODO inventory (deprecated execution path removed).

        To execute TODO tasks, use ``PrimeContractorWorkflow.enable_todo_completion()``
        instead.  This method now only scans and produces the inventory + seed.
        """
        if config.get("execute"):
            warnings.warn(
                "TodoCompletionWorkflow execution is deprecated. "
                "Use PrimeContractorWorkflow.enable_todo_completion() instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        scan_dir = config["scan_dir"]
        output_dir = config["output_dir"]
        source_run_id = config.get("source_run_id", "")
        categories_str = config.get("categories", "A,B")
        max_tasks = config.get("max_tasks", 20)
        instrumentation_contract = config.get("instrumentation_contract")

        categories = {c.strip().upper() for c in str(categories_str).split(",")}

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # --- Phase 1: Scan ---
        if on_progress:
            on_progress(1, 2, "Scanning for TODOs...")

        from startd8.validators.todo_scanner import scan_directory
        inventory = scan_directory(
            scan_dir,
            instrumentation_contract=instrumentation_contract,
        )

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

        inventory.save(out / "todo-inventory.json")

        if not inventory.entries:
            return WorkflowResult(
                workflow_id="todo-completion",
                success=True,
                output={"message": "No TODOs found matching categories", "todo_count": 0},
                metadata={"todo_count": 0},
            )

        # --- Phase 2: Plan (scan-only — no execution) ---
        if on_progress:
            on_progress(2, 2, "Generating completion plan...")

        from startd8.seeds.todo_derivation import derive_tasks_from_todos

        tasks = derive_tasks_from_todos(
            inventory,
            instrumentation_contract=instrumentation_contract,
            source_run_id=source_run_id,
        )

        if len(tasks) > max_tasks:
            tasks = tasks[:max_tasks]

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

        return WorkflowResult(
            workflow_id="todo-completion",
            success=True,
            output={
                "todo_count": inventory.summary.get("total", 0),
                "todo_count_a": inventory.summary.get("A", 0),
                "todo_count_b": inventory.summary.get("B", 0),
                "task_count": len(tasks),
                "executed": False,
                "seed_path": str(seed_path),
                "inventory_path": str(out / "todo-inventory.json"),
                "todo_completed": 0,
                "todo_deferred": len(tasks),
                "todo_completion_rate": 0.0,
            },
            metadata={
                "todo_count": inventory.summary.get("total", 0),
                "task_count": len(tasks),
                "executed": False,
            },
        )
