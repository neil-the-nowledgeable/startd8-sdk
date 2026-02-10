"""
Context Seed Phase Handlers for ArtisanContractorWorkflow.

Bridges enriched context seeds (from PlanIngestionWorkflow + DomainPreflightWorkflow)
to the ArtisanContractorWorkflow orchestrator by providing concrete AbstractPhaseHandler
implementations for each WorkflowPhase.

WorkflowPhase mapping (from artisan_contractor.py docstring):
    PLAN      → Load seed + validate + build task plan
    SCAFFOLD  → Verify target directories + resolve dependencies
    IMPLEMENT → Process tasks (dry-run reports what would be done)
    TEST      → Validate post-generation constraints
    REVIEW    → Quality review checklist
    FINALIZE  → Generate summary + write output artifacts

Usage::

    from startd8.contractors.context_seed_handlers import ContextSeedHandlers
    from startd8.contractors.artisan_contractor import (
        ArtisanContractorWorkflow, WorkflowConfig, WorkflowPhase,
    )

    config = WorkflowConfig(dry_run=True, project_root="/path/to/project")
    workflow = ArtisanContractorWorkflow(config=config)

    handlers = ContextSeedHandlers.create_all(
        enriched_seed_path="out/artisan-context-seed-enriched.json",
    )
    for phase, handler in handlers.items():
        workflow.register_handler(phase, handler)

    result = workflow.execute(context={})
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ContextSeedHandlers",
    "PlanPhaseHandler",
    "ScaffoldPhaseHandler",
    "ImplementPhaseHandler",
    "TestPhaseHandler",
    "ReviewPhaseHandler",
    "FinalizePhaseHandler",
]


# ============================================================================
# Shared data structures
# ============================================================================


@dataclass
class SeedTask:
    """Parsed task from an enriched context seed."""

    task_id: str
    title: str
    task_type: str
    story_points: int
    priority: str
    labels: list[str]
    depends_on: list[str]
    description: str
    target_files: list[str]
    estimated_loc: int
    feature_id: str
    # Enrichment fields
    domain: str
    domain_reasoning: str
    environment_checks: list[dict[str, Any]]
    prompt_constraints: list[str]
    post_generation_validators: list[str]
    available_siblings: list[str]
    existing_content_hash: Optional[str]

    @classmethod
    def from_seed_entry(cls, entry: dict[str, Any]) -> SeedTask:
        """Parse a task entry from the enriched context seed JSON."""
        config = entry.get("config", {})
        context = config.get("context", {})
        enrichment = entry.get("_enrichment", {})

        return cls(
            task_id=entry.get("task_id", ""),
            title=entry.get("title", ""),
            task_type=entry.get("task_type", "task"),
            story_points=entry.get("story_points", 0),
            priority=entry.get("priority", "medium"),
            labels=entry.get("labels", []),
            depends_on=entry.get("depends_on", []),
            description=config.get("task_description", ""),
            target_files=context.get("target_files", []),
            estimated_loc=context.get("estimated_loc", 0),
            feature_id=context.get("feature_id", ""),
            domain=enrichment.get("domain", "unknown"),
            domain_reasoning=enrichment.get("domain_reasoning", ""),
            environment_checks=enrichment.get("environment_checks", []),
            prompt_constraints=enrichment.get("prompt_constraints", []),
            post_generation_validators=enrichment.get(
                "post_generation_validators", []
            ),
            available_siblings=enrichment.get("available_siblings", []),
            existing_content_hash=enrichment.get("existing_content_hash"),
        )


def _load_enriched_seed(seed_path: str) -> dict[str, Any]:
    """Load and validate an enriched context seed JSON file."""
    path = Path(seed_path)
    if not path.exists():
        raise FileNotFoundError(f"Enriched seed not found: {seed_path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError("Enriched seed must be a JSON object")

    # Tasks live at the top level (from PlanIngestionWorkflow), not under plan
    if "tasks" not in data:
        raise ValueError("Enriched seed must contain a 'tasks' list")

    return data


def _parse_tasks(seed_data: dict[str, Any]) -> list[SeedTask]:
    """Parse all tasks from the enriched seed."""
    raw_tasks = seed_data.get("tasks", [])
    tasks = []
    for entry in raw_tasks:
        if isinstance(entry, dict):
            tasks.append(SeedTask.from_seed_entry(entry))
    return tasks


def _topological_sort(tasks: list[SeedTask]) -> list[SeedTask]:
    """Sort tasks by dependency order (tasks with no deps first)."""
    id_to_task = {t.task_id: t for t in tasks}
    visited: set[str] = set()
    result: list[str] = []

    def visit(task_id: str) -> None:
        if task_id in visited:
            return
        visited.add(task_id)
        task = id_to_task.get(task_id)
        if task:
            for dep_id in task.depends_on:
                visit(dep_id)
            result.append(task_id)

    for t in tasks:
        visit(t.task_id)

    return [id_to_task[tid] for tid in result if tid in id_to_task]


# ============================================================================
# Phase Handlers
# ============================================================================


class PlanPhaseHandler(AbstractPhaseHandler):
    """PLAN phase: Load enriched seed, validate, build execution plan.

    Populates context with parsed tasks, dependency order, and domain summary.
    """

    def __init__(self, enriched_seed_path: str) -> None:
        self.enriched_seed_path = enriched_seed_path

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("PLAN phase: loading enriched seed from %s", self.enriched_seed_path)

        # Load and parse
        seed_data = _load_enriched_seed(self.enriched_seed_path)
        tasks = _parse_tasks(seed_data)
        sorted_tasks = _topological_sort(tasks)

        # Extract plan metadata
        plan_meta = seed_data.get("plan", {})
        preflight = seed_data.get("_preflight", {})

        # Domain summary
        domain_counts: dict[str, int] = defaultdict(int)
        for t in tasks:
            domain_counts[t.domain] += 1

        # Check summary from preflight
        check_summary = preflight.get("check_summary", {})
        fail_count = check_summary.get("fail", 0)

        # Populate context for downstream phases
        context["enriched_seed_path"] = self.enriched_seed_path
        context["seed_data"] = seed_data
        context["tasks"] = sorted_tasks
        context["task_index"] = {t.task_id: t for t in tasks}
        context["plan_title"] = plan_meta.get("title", "Untitled Plan")
        context["plan_goals"] = plan_meta.get("goals", [])
        context["domain_summary"] = dict(domain_counts)
        context["preflight_summary"] = check_summary
        context["total_estimated_loc"] = sum(t.estimated_loc for t in tasks)

        output = {
            "plan_title": context["plan_title"],
            "task_count": len(tasks),
            "execution_order": [t.task_id for t in sorted_tasks],
            "domain_summary": dict(domain_counts),
            "preflight_check_summary": check_summary,
            "total_estimated_loc": context["total_estimated_loc"],
            "preflight_failures": fail_count,
            "goals": context["plan_goals"],
        }

        duration = time.monotonic() - start
        logger.info(
            "PLAN phase complete: %d tasks, %d domains, %d preflight failures (%.2fs)",
            len(tasks), len(domain_counts), fail_count, duration,
        )

        if fail_count > 0 and not dry_run:
            logger.warning(
                "PLAN phase: %d preflight failures detected — review before implementing",
                fail_count,
            )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


class ScaffoldPhaseHandler(AbstractPhaseHandler):
    """SCAFFOLD phase: Verify target directories, check dependencies.

    Creates missing directories and validates the project environment.
    """

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        tasks: list[SeedTask] = context.get("tasks", [])
        project_root = Path(context.get("project_root", "."))

        logger.info("SCAFFOLD phase: checking %d tasks against %s", len(tasks), project_root)

        dirs_needed: set[str] = set()
        dirs_exist: set[str] = set()
        dirs_created: set[str] = set()
        files_existing: list[str] = []

        for task in tasks:
            for target in task.target_files:
                target_path = project_root / target
                parent = target_path.parent
                parent_rel = str(parent.relative_to(project_root))

                dirs_needed.add(parent_rel)

                if parent.exists():
                    dirs_exist.add(parent_rel)
                elif not dry_run:
                    parent.mkdir(parents=True, exist_ok=True)
                    dirs_created.add(parent_rel)
                    logger.info("Created directory: %s", parent)

                if target_path.exists():
                    files_existing.append(target)

        dirs_missing = dirs_needed - dirs_exist - dirs_created

        output = {
            "directories_needed": sorted(dirs_needed),
            "directories_exist": sorted(dirs_exist),
            "directories_created": sorted(dirs_created),
            "directories_missing": sorted(dirs_missing) if dry_run else [],
            "existing_target_files": files_existing,
            "project_root": str(project_root),
        }

        # Store scaffold results in context
        context["scaffold"] = output

        duration = time.monotonic() - start
        logger.info(
            "SCAFFOLD phase complete: %d dirs needed, %d exist, %d created, %d existing files (%.2fs)",
            len(dirs_needed), len(dirs_exist), len(dirs_created), len(files_existing), duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


class ImplementPhaseHandler(AbstractPhaseHandler):
    """IMPLEMENT phase: Process tasks in dependency order.

    In dry-run mode: reports what would be implemented per task.
    In real mode: would orchestrate LLM code generation (future work).
    """

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        tasks: list[SeedTask] = context.get("tasks", [])
        project_root = Path(context.get("project_root", "."))

        logger.info("IMPLEMENT phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        task_reports: list[dict[str, Any]] = []
        total_cost = 0.0

        for task in tasks:
            task_report = {
                "task_id": task.task_id,
                "feature_id": task.feature_id,
                "title": task.title,
                "domain": task.domain,
                "target_files": task.target_files,
                "estimated_loc": task.estimated_loc,
                "depends_on": task.depends_on,
                "prompt_constraints_count": len(task.prompt_constraints),
                "validators": task.post_generation_validators,
                "status": "dry_run_skipped" if dry_run else "pending",
            }

            if not dry_run:
                # Real implementation would:
                # 1. Build prompt from task description + constraints
                # 2. Call LLM via drafter model
                # 3. Validate output against post_generation_validators
                # 4. Write files to target_files
                # For now, mark as pending (future work with PhaseRunner)
                task_report["status"] = "not_implemented"
                task_report["note"] = (
                    "Real LLM code generation requires PhaseRunner integration "
                    "with draft→validate→gate pattern. Use --dry-run to test orchestration."
                )

            # Check environment readiness
            env_issues = [
                c for c in task.environment_checks
                if c.get("status") in ("fail", "warn")
            ]
            if env_issues:
                task_report["environment_issues"] = env_issues

            task_reports.append(task_report)

        # Group by domain for summary
        domain_tasks: dict[str, list[str]] = defaultdict(list)
        for task in tasks:
            domain_tasks[task.domain].append(task.task_id)

        output = {
            "task_reports": task_reports,
            "tasks_processed": len(task_reports),
            "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
            "total_estimated_loc": sum(t.estimated_loc for t in tasks),
            "total_cost": total_cost,
        }

        context["implementation"] = output
        duration = time.monotonic() - start

        logger.info(
            "IMPLEMENT phase complete: %d tasks processed (%.2fs)",
            len(task_reports), duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}


class TestPhaseHandler(AbstractPhaseHandler):
    """TEST phase: Validate post-generation constraints.

    In dry-run mode: reports the test plan per task.
    In real mode: would run validators against generated code.
    """

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        tasks: list[SeedTask] = context.get("tasks", [])

        logger.info("TEST phase: building test plan for %d tasks (dry_run=%s)", len(tasks), dry_run)

        test_plan: list[dict[str, Any]] = []
        validator_counts: dict[str, int] = defaultdict(int)

        for task in tasks:
            validators = task.post_generation_validators
            for v in validators:
                validator_counts[v] += 1

            test_entry = {
                "task_id": task.task_id,
                "title": task.title,
                "domain": task.domain,
                "validators": validators,
                "validator_count": len(validators),
                "status": "dry_run_planned" if dry_run else "not_run",
            }
            test_plan.append(test_entry)

        output = {
            "test_plan": test_plan,
            "total_validators": sum(len(t.post_generation_validators) for t in tasks),
            "unique_validators": dict(validator_counts),
            "tasks_with_tests": len([t for t in test_plan if t["validator_count"] > 0]),
        }

        context["test_results"] = output
        duration = time.monotonic() - start

        logger.info(
            "TEST phase complete: %d validators across %d tasks (%.2fs)",
            output["total_validators"], len(test_plan), duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


class ReviewPhaseHandler(AbstractPhaseHandler):
    """REVIEW phase: Quality review checklist.

    In dry-run mode: reports review checklist.
    In real mode: would run code quality analysis.
    """

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        tasks: list[SeedTask] = context.get("tasks", [])
        preflight_summary = context.get("preflight_summary", {})

        logger.info("REVIEW phase: building review checklist (dry_run=%s)", dry_run)

        # Build review checklist from enrichment data
        review_items: list[dict[str, Any]] = []
        constraint_coverage: dict[str, int] = defaultdict(int)

        for task in tasks:
            # Count constraint types
            for constraint in task.prompt_constraints:
                # Extract constraint category from first few words
                key = constraint.split("(")[0].strip()[:60]
                constraint_coverage[key] += 1

            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            env_warns = [
                c for c in task.environment_checks
                if c.get("status") == "warn"
            ]

            review_items.append({
                "task_id": task.task_id,
                "title": task.title,
                "domain": task.domain,
                "constraint_count": len(task.prompt_constraints),
                "env_failures": len(env_fails),
                "env_warnings": len(env_warns),
                "review_status": "dry_run_pending" if dry_run else "not_reviewed",
            })

        output = {
            "review_items": review_items,
            "preflight_summary": preflight_summary,
            "constraint_coverage": dict(constraint_coverage),
            "tasks_with_env_issues": len([
                r for r in review_items
                if r["env_failures"] > 0 or r["env_warnings"] > 0
            ]),
        }

        context["review_results"] = output
        duration = time.monotonic() - start

        logger.info(
            "REVIEW phase complete: %d items reviewed (%.2fs)",
            len(review_items), duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


class FinalizePhaseHandler(AbstractPhaseHandler):
    """FINALIZE phase: Generate summary and write output artifacts.

    Produces a workflow execution report with all phase results.
    """

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = output_dir

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("FINALIZE phase: generating summary (dry_run=%s)", dry_run)

        plan_title = context.get("plan_title", "Untitled")
        tasks: list[SeedTask] = context.get("tasks", [])
        domain_summary = context.get("domain_summary", {})
        preflight_summary = context.get("preflight_summary", {})
        scaffold = context.get("scaffold", {})
        implementation = context.get("implementation", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})

        summary = {
            "plan_title": plan_title,
            "task_count": len(tasks),
            "domain_summary": domain_summary,
            "preflight_summary": preflight_summary,
            "scaffold_summary": {
                "dirs_needed": len(scaffold.get("directories_needed", [])),
                "dirs_created": len(scaffold.get("directories_created", [])),
                "existing_files": len(scaffold.get("existing_target_files", [])),
            },
            "implementation_summary": {
                "tasks_processed": implementation.get("tasks_processed", 0),
                "total_estimated_loc": implementation.get("total_estimated_loc", 0),
            },
            "test_summary": {
                "total_validators": test_results.get("total_validators", 0),
                "tasks_with_tests": test_results.get("tasks_with_tests", 0),
            },
            "review_summary": {
                "tasks_with_env_issues": review_results.get("tasks_with_env_issues", 0),
            },
            "dry_run": dry_run,
        }

        # Write summary artifact if output_dir specified
        if self.output_dir and not dry_run:
            output_path = Path(self.output_dir) / "workflow-execution-report.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, default=str)
            logger.info("Wrote execution report to %s", output_path)
            summary["report_path"] = str(output_path)

        context["workflow_summary"] = summary
        duration = time.monotonic() - start

        logger.info("FINALIZE phase complete (%.2fs)", duration)

        return {"output": summary, "cost": 0.0, "metadata": {"duration": duration}}


# ============================================================================
# Factory
# ============================================================================


class ContextSeedHandlers:
    """Factory for creating all phase handlers from an enriched context seed."""

    @staticmethod
    def create_all(
        enriched_seed_path: str,
        output_dir: Optional[str] = None,
    ) -> dict[WorkflowPhase, AbstractPhaseHandler]:
        """Create handlers for all six workflow phases.

        Args:
            enriched_seed_path: Path to the enriched context seed JSON.
            output_dir: Optional output directory for artifacts.

        Returns:
            Dict mapping WorkflowPhase → handler instance.
        """
        return {
            WorkflowPhase.PLAN: PlanPhaseHandler(enriched_seed_path),
            WorkflowPhase.SCAFFOLD: ScaffoldPhaseHandler(),
            WorkflowPhase.IMPLEMENT: ImplementPhaseHandler(),
            WorkflowPhase.TEST: TestPhaseHandler(),
            WorkflowPhase.REVIEW: ReviewPhaseHandler(),
            WorkflowPhase.FINALIZE: FinalizePhaseHandler(output_dir=output_dir),
        }
