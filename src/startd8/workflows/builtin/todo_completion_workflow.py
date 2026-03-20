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
        generation_profile (str): Optional generation profile. When present,
            recorded in provenance. Does not override explicit ``execute``.
    """

    # Profiles that imply instrumentation is relevant
    _INSTRUMENTATION_PROFILES = frozenset({"source", "full"})

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
        generation_profile = config.get("generation_profile", "")

        if generation_profile:
            logger.info("Generation profile: %s", generation_profile)

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

        # SP-TD-010: Load security contract for dual contract injection (B+S TODOs)
        security_contract = config.get("security_contract")
        if security_contract is None:
            try:
                from startd8.security_prime.contract import derive_security_contract
                security_contract = derive_security_contract(
                    plan_text=config.get("plan_text", ""),
                    feature_descriptions=[
                        e.raw_text for e in inventory.entries if e.security_sensitive
                    ] or None,
                )
            except ImportError:
                pass  # security_prime not available

        tasks = derive_tasks_from_todos(
            inventory,
            instrumentation_contract=instrumentation_contract,
            source_run_id=source_run_id,
            security_contract=security_contract,
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

        # --- Phase 3.5: Coverage (REQ-TCW-402) ---
        coverage_result = None
        if instrumentation_contract:
            try:
                from startd8.validators.instrumentation_coverage import (
                    compute_instrumentation_coverage,
                )
                coverage_result = compute_instrumentation_coverage(
                    Path(scan_dir),
                    instrumentation_contract,
                )
                logger.info(
                    "Instrumentation coverage: %.1f%% (%d/%d)",
                    coverage_result.coverage_pct,
                    coverage_result.satisfied_entries,
                    coverage_result.contract_entries,
                )
            except Exception as exc:
                logger.warning("Coverage computation failed: %s", exc)

        # --- Phase 3.6: Provenance (REQ-TCW-400) ---
        provenance = {
            "source": "instrumentation",
            "parent_run_id": source_run_id,
            "scan_dir": str(scan_dir),
            "output_dir": str(output_dir),
            "seed_path": str(seed_path),
            "inventory_path": str(out / "todo-inventory.json"),
        }
        if generation_profile:
            provenance["generation_profile"] = generation_profile
        provenance_path = out / "instrumentation-provenance.json"
        provenance_path.write_text(
            json.dumps(provenance, indent=2, default=str), encoding="utf-8",
        )

        # --- Phase 4: Report ---
        if on_progress:
            on_progress(4, 4, "Writing report...")

        todo_completed = 0
        todo_deferred = 0
        if execution_result and isinstance(execution_result, dict):
            todo_completed = execution_result.get("pass_count", len(tasks) if execution_result.get("success") else 0)
            todo_deferred = len(tasks) - todo_completed

        result_output = {
            "todo_count": inventory.summary.get("total", 0),
            "todo_count_a": inventory.summary.get("A", 0),
            "todo_count_b": inventory.summary.get("B", 0),
            "task_count": len(tasks),
            "executed": executed,
            "seed_path": str(seed_path),
            "inventory_path": str(out / "todo-inventory.json"),
            "todo_completed": todo_completed,
            "todo_deferred": todo_deferred,
            "todo_completion_rate": (
                round(todo_completed / len(tasks) * 100, 2) if tasks else 0.0
            ),
        }
        if coverage_result:
            result_output["instrumentation_coverage"] = coverage_result.coverage_pct
            result_output["instrumentation_gaps"] = coverage_result.gaps
        if generation_profile:
            result_output["generation_profile"] = generation_profile
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
                "generation_profile": generation_profile or "",
            },
        )

    def _execute_plan(
        self,
        seed: Dict[str, Any],
        output_dir: str,
        agents: Optional[List[Any]],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute the completion plan with task-type dispatch (REQ-TCW-305).

        Routes tasks by ``task_type``:
        - ``uncomment`` → deterministic ``uncomment_block()`` (zero LLM cost)
        - ``implement``/``dependency``/``edit`` → PrimeContractorWorkflow

        Per-task error isolation (REQ-TCW-307): failed tasks do NOT block
        independent subsequent tasks.

        Returns:
            Dict with ``success``, ``status``, ``output_dir``,
            ``pass_count``, and ``total_features`` keys.
        """
        import json

        tasks = seed.get("tasks", [])
        if not tasks:
            return {"success": True, "status": "no_tasks", "pass_count": 0, "total_features": 0}

        instrumentation_dir = Path(output_dir) / "instrumentation"
        instrumentation_dir.mkdir(parents=True, exist_ok=True)
        project_root = Path(config.get("scan_dir", "."))

        # Split tasks by type
        uncomment_tasks = [t for t in tasks if t.get("task_type") == "uncomment"]
        llm_tasks = [t for t in tasks if t.get("task_type") != "uncomment"]

        pass_count = 0
        fail_count = 0
        errors: List[Dict[str, str]] = []

        # --- Deterministic uncomment tasks (zero LLM cost) ---
        if uncomment_tasks:
            from startd8.validators.todo_scanner import uncomment_block

            for task in uncomment_tasks:
                try:
                    ctx = task.get("config", {}).get("context", {})
                    target_files = ctx.get("target_files") or task.get("target_files", [])
                    language = ctx.get("language", "python")

                    for tf in target_files:
                        tf_path = Path(tf)
                        file_path = tf_path if tf_path.is_absolute() else project_root / tf
                        if not file_path.is_file():
                            logger.warning("Uncomment target not found: %s", file_path)
                            continue

                        content = file_path.read_text(encoding="utf-8", errors="replace")

                        # If structured comment_block available, verify content matches
                        comment_block = ctx.get("comment_block")
                        if comment_block and comment_block.get("content_lines"):
                            lines = content.splitlines()
                            start_0 = comment_block["start_line"] - 1
                            expected = comment_block["content_lines"]
                            actual = lines[start_0:start_0 + len(expected)]
                            if [l.rstrip() for l in actual] != [l.rstrip() for l in expected]:
                                logger.debug(
                                    "Comment block drift in %s: expected %r, got %r",
                                    file_path,
                                    expected[0].rstrip() if expected else "",
                                    actual[0].rstrip() if actual else "",
                                )
                                logger.info(
                                    "Comment block shifted in %s — falling back to full-file scan",
                                    file_path,
                                )

                        result, count = uncomment_block(content, language=language)
                        if count > 0:
                            file_path.write_text(result, encoding="utf-8")
                            logger.info(
                                "Uncommented %d block(s) in %s", count, file_path,
                            )

                    pass_count += 1
                except (OSError, ValueError) as exc:
                    fail_count += 1
                    task_id = task.get("task_id", "?")
                    logger.warning(
                        "Uncomment task %s failed: %s", task_id, exc, exc_info=True,
                    )
                    errors.append({"task_id": task_id, "error": str(exc)})

        # --- LLM-backed tasks via Prime Contractor ---
        if llm_tasks:
            llm_seed = dict(seed, tasks=llm_tasks)
            seed_file = instrumentation_dir / "instrumentation-seed.json"
            seed_file.write_text(
                json.dumps(llm_seed, indent=2, default=str), encoding="utf-8",
            )

            from startd8.contractors.prime_contractor import PrimeContractorWorkflow
            from startd8.contractors.generators import LeadContractorCodeGenerator

            code_generator = LeadContractorCodeGenerator(
                output_dir=instrumentation_dir / "generated",
            )
            todo_state_file = instrumentation_dir / ".todo_prime_state.json"

            workflow = PrimeContractorWorkflow(
                project_root=project_root,
                dry_run=False,
                allow_dirty=True,
                auto_commit=False,
                code_generator=code_generator,
                state_file=todo_state_file,
            )

            added = workflow.queue.add_features_from_seed(str(seed_file))
            logger.info("Loaded %d LLM tasks from seed", len(added))

            workflow.load_seed_context(llm_seed)

            result = workflow.run()

            llm_pass = result.get("successful_features", 0)
            llm_total = result.get("total_features", len(added))
            pass_count += llm_pass
            fail_count += llm_total - llm_pass

        total = len(tasks)
        return {
            "success": pass_count > 0,
            "status": "complete",
            "output_dir": str(instrumentation_dir),
            "pass_count": pass_count,
            "total_features": total,
            "errors": errors if errors else None,
        }
