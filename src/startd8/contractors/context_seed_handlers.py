"""
Context Seed Phase Handlers for ArtisanContractorWorkflow.

Bridges enriched context seeds (from PlanIngestionWorkflow + DomainPreflightWorkflow)
to the ArtisanContractorWorkflow orchestrator by providing concrete AbstractPhaseHandler
implementations for each WorkflowPhase.

WorkflowPhase mapping (from artisan_contractor.py docstring):
    PLAN      → Load seed + validate + build task plan
    SCAFFOLD  → Verify target directories + resolve dependencies
    IMPLEMENT → Generate code per task via LeadContractorCodeGenerator
    TEST      → Run post-generation validators against generated code
    REVIEW    → LLM-based quality review of generated implementations
    FINALIZE  → Collect artifacts + write comprehensive execution report

Implementation Passes:
    Pass 1: Scaffold all handler interfaces, __init__ params,
        private helper stubs, and factory config propagation.
    Pass 2: Wire ImplementPhaseHandler to LeadContractorCodeGenerator.
    Pass 3: Wire TestPhaseHandler to subprocess validators.
    Pass 4: Polish FinalizePhaseHandler artifact collection (checksums,
        line counts, domain tags), cost aggregation (test phase), manifest
        per-task status rollup, and overall success/partial/failed status.

Usage::

    from startd8.contractors.context_seed_handlers import ContextSeedHandlers
    from startd8.contractors.artisan_contractor import (
        ArtisanContractorWorkflow, WorkflowConfig, WorkflowPhase,
    )

    config = WorkflowConfig(dry_run=True, project_root="/path/to/project")
    workflow = ArtisanContractorWorkflow(config=config)

    handlers = ContextSeedHandlers.create_all(
        enriched_seed_path="out/artisan-context-seed-enriched.json",
        lead_agent="anthropic:claude-sonnet-4-5-20250927",
        drafter_agent="gemini:gemini-2.5-flash-lite",
    )
    for phase, handler in handlers.items():
        workflow.register_handler(phase, handler)

    result = workflow.execute(context={})
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)
from startd8.contractors.protocols import CodeGenerator, GenerationResult

logger = logging.getLogger(__name__)

__all__ = [
    "HandlerConfig",
    "ContextSeedHandlers",
    "PlanPhaseHandler",
    "ScaffoldPhaseHandler",
    "ImplementPhaseHandler",
    "TestPhaseHandler",
    "ReviewPhaseHandler",
    "FinalizePhaseHandler",
]


# ============================================================================
# Handler configuration
# ============================================================================


@dataclass
class HandlerConfig:
    """Shared configuration propagated to all phase handlers.

    Attributes:
        lead_agent: Agent spec for architect/reviewer (e.g. ``"anthropic:claude-sonnet-4-5-20250927"``).
        drafter_agent: Agent spec for drafter (e.g. ``"gemini:gemini-2.5-flash-lite"``).
        max_iterations: Maximum draft → review iterations per task.
        pass_threshold: Minimum review score (0-100) to pass.
        max_tokens: Override max_tokens for agent creation (None = provider default).
        fail_on_truncation: Fail workflow on detected truncation.
        check_truncation: Enable heuristic truncation detection.
        strict_truncation: Use strict detection threshold.
        test_timeout_seconds: Timeout for each validator subprocess.
        review_temperature: Temperature for LLM review calls.
    """

    lead_agent: str = "anthropic:claude-sonnet-4-5-20250927"
    drafter_agent: str = "gemini:gemini-2.5-flash-lite"
    max_iterations: int = 3
    pass_threshold: int = 80
    max_tokens: Optional[int] = None
    fail_on_truncation: bool = True
    check_truncation: bool = True
    strict_truncation: bool = False
    test_timeout_seconds: int = 120
    review_temperature: float = 0.0


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

        task = cls(
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
        if not task.task_id:
            raise ValueError(f"Seed entry missing required field 'task_id': {entry}")
        if not task.title:
            raise ValueError(f"Seed entry missing required field 'title': {entry}")
        return task


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
    """Sort tasks by dependency order (tasks with no deps first).

    Uses DFS with gray/black coloring to detect cycles.  If a cycle is
    found, logs a warning with the involved task IDs and falls back to
    the original input order (safe — the orchestrator can still run, it
    just won't guarantee prerequisite ordering).
    """
    id_to_task = {t.task_id: t for t in tasks}
    # WHITE = not visited, GRAY = in current DFS path, BLACK = finished
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {t.task_id: WHITE for t in tasks}
    result: list[str] = []
    cycle_members: list[str] = []

    def visit(task_id: str) -> bool:
        """Return True if a cycle was detected."""
        state = color.get(task_id, BLACK)  # unknown IDs treated as done
        if state == BLACK:
            return False
        if state == GRAY:
            cycle_members.append(task_id)
            return True

        color[task_id] = GRAY
        task = id_to_task.get(task_id)
        if task:
            for dep_id in task.depends_on:
                if visit(dep_id):
                    cycle_members.append(task_id)
                    return True
        color[task_id] = BLACK
        result.append(task_id)
        return False

    has_cycle = False
    for t in tasks:
        if color[t.task_id] == WHITE:
            if visit(t.task_id):
                has_cycle = True
                break

    if has_cycle:
        logger.warning(
            "Dependency cycle detected among tasks: %s — "
            "falling back to original seed order",
            " → ".join(reversed(cycle_members)),
        )
        return list(tasks)

    return [id_to_task[tid] for tid in result if tid in id_to_task]


def _ensure_context_loaded(context: dict[str, Any]) -> list[SeedTask]:
    """Return the task list from context, reloading from seed if needed.

    After a checkpoint resume the context dict is empty because the
    orchestrator does not persist it.  Every handler that needs tasks
    calls this helper, which transparently reloads the seed when the
    PLAN phase's data is absent.
    """
    tasks: list[SeedTask] | None = context.get("tasks")
    if tasks is not None:
        return tasks

    seed_path = context.get("enriched_seed_path")
    if not seed_path:
        logger.warning(
            "Context missing 'tasks' and 'enriched_seed_path' — "
            "cannot reload seed (possible checkpoint resume without PLAN phase)"
        )
        return []

    logger.info("Reloading enriched seed for resumed workflow from %s", seed_path)
    seed_data = _load_enriched_seed(seed_path)
    tasks = _topological_sort(_parse_tasks(seed_data))

    # Re-populate the keys that PlanPhaseHandler normally sets
    plan_meta = seed_data.get("plan", {})
    preflight = seed_data.get("_preflight", {})

    context["tasks"] = tasks
    context["task_index"] = {t.task_id: t for t in tasks}
    context["plan_title"] = plan_meta.get("title", "Untitled Plan")
    context["plan_goals"] = plan_meta.get("goals", [])
    context["preflight_summary"] = preflight.get("check_summary", {})
    domain_counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        domain_counts[t.domain] += 1
    context["domain_summary"] = dict(domain_counts)
    context["total_estimated_loc"] = sum(t.estimated_loc for t in tasks)

    return tasks


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

        # Populate context for downstream phases.
        # Note: we intentionally do NOT store the raw seed_data blob in
        # context — it can be large and is not needed after parsing.  If a
        # checkpoint resume needs it, _ensure_context_loaded re-reads the file.
        context["enriched_seed_path"] = self.enriched_seed_path
        context["tasks"] = sorted_tasks
        context["task_index"] = {t.task_id: t for t in sorted_tasks}
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
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        project_root = Path(context.get("project_root", "."))

        logger.info("SCAFFOLD phase: checking %d tasks against %s", len(tasks), project_root)

        dirs_needed: set[str] = set()
        dirs_exist: set[str] = set()
        dirs_created: set[str] = set()
        files_existing: list[str] = []

        skipped_targets: list[str] = []

        for task in tasks:
            for target in task.target_files:
                target_path = project_root / target
                parent = target_path.parent

                # Guard: skip targets whose resolved parent falls outside
                # project_root (e.g. absolute paths in target_files).
                try:
                    parent_rel = str(parent.relative_to(project_root))
                except ValueError:
                    logger.warning(
                        "SCAFFOLD: target %r resolves outside project root, skipping",
                        target,
                    )
                    skipped_targets.append(target)
                    continue

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
            "skipped_targets": skipped_targets,
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
    """IMPLEMENT phase: Generate code per task in dependency order.

    In dry-run mode: reports what would be implemented per task (unchanged).
    In real mode: invokes :class:`LeadContractorCodeGenerator` for each task,
    writing generated files to ``project_root / target_file``.

    Wires to :class:`LeadContractorCodeGenerator` for actual code generation:
        * ``_resolve_generator`` lazily creates the generator (or uses an injected one).
        * ``_build_task_context`` assembles the prompt context dict for a task,
          including existing file contents and dependency outputs.
        * ``_generate_for_task`` calls ``generator.generate()`` and returns the report.
        * ``execute`` orchestrates the full loop with env-check, dep-check, and
          cost aggregation.
    """

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        code_generator: Optional[CodeGenerator] = None,
    ) -> None:
        self.config = handler_config or HandlerConfig()
        self._generator = code_generator  # None → auto-created via _resolve_generator()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _resolve_generator(self, project_root: Path) -> CodeGenerator:
        """Resolve the code generator, creating one if not injected.

        Returns the injected generator if set, otherwise creates a
        :class:`LeadContractorCodeGenerator` from ``self.config``.

        A new generator is created per call when ``project_root`` differs
        from the cached instance's ``output_dir``, since
        ``LeadContractorCodeGenerator`` binds ``output_dir`` at init time.

        Args:
            project_root: The project root, used as the generator's output
                directory so files land in the correct location.

        Returns:
            A ``CodeGenerator`` instance ready to use.
        """
        if self._generator is not None:
            # Invalidate cache if project_root changed since last creation
            cached_output_dir = getattr(self._generator, "output_dir", None)
            if cached_output_dir is not None and Path(cached_output_dir) != project_root:
                logger.info(
                    "IMPLEMENT: project_root changed (%s → %s), recreating generator",
                    cached_output_dir, project_root,
                )
                self._generator = None
            else:
                return self._generator

        from startd8.contractors.generators.lead_contractor import LeadContractorCodeGenerator

        self._generator = LeadContractorCodeGenerator(
            lead_agent=self.config.lead_agent,
            drafter_agent=self.config.drafter_agent,
            max_iterations=self.config.max_iterations,
            pass_threshold=self.config.pass_threshold,
            output_dir=project_root,
            max_tokens=self.config.max_tokens,
            fail_on_truncation=self.config.fail_on_truncation,
            check_truncation=self.config.check_truncation,
            strict_truncation=self.config.strict_truncation,
        )
        return self._generator

    #: Maximum bytes to read from an existing file before truncating.
    #: Keeps the LLM context window manageable for large files.
    _MAX_EXISTING_FILE_BYTES: int = 60_000

    def _build_task_context(
        self,
        task: SeedTask,
        project_root: Path,
        prior_results: Dict[str, GenerationResult],
    ) -> Dict[str, Any]:
        """Build the context dict for a single task's code generation.

        Includes:
        - Task description and constraints
        - Target file paths and existing content (if any)
        - Outputs of dependency tasks (for cross-task awareness)
        - Enrichment metadata (domain, environment checks)

        Args:
            task: The seed task to build context for.
            project_root: Root of the target project.
            prior_results: Map of task_id → GenerationResult for completed deps.

        Returns:
            Context dict suitable for ``CodeGenerator.generate()``.
        """
        ctx: Dict[str, Any] = {
            "task_id": task.task_id,
            "feature_id": task.feature_id,
            "domain": task.domain,
            "target_files": task.target_files,
            "estimated_loc": task.estimated_loc,
            "prompt_constraints": task.prompt_constraints,
            "environment_checks": task.environment_checks,
            "project_root": str(project_root),
        }

        # Read existing file contents for modify-in-place tasks
        for target in task.target_files:
            target_path = project_root / target
            if target_path.exists():
                try:
                    content = target_path.read_text(encoding="utf-8")
                    if len(content) > self._MAX_EXISTING_FILE_BYTES:
                        content = (
                            content[: self._MAX_EXISTING_FILE_BYTES]
                            + f"\n\n# ... truncated ({len(content)} bytes total)"
                        )
                    ctx.setdefault("existing_files", {})[target] = content
                except (UnicodeDecodeError, OSError) as exc:
                    logger.warning(
                        "IMPLEMENT: could not read existing file %s: %s",
                        target_path, exc,
                    )

        # Inject real dependency outputs for cross-task context
        dep_outputs: Dict[str, Any] = {}
        for dep_id in task.depends_on:
            dep_result = prior_results.get(dep_id)
            if dep_result and dep_result.success:
                dep_files: Dict[str, str] = {}
                for gen_file in dep_result.generated_files:
                    try:
                        if gen_file.exists():
                            content = gen_file.read_text(encoding="utf-8")
                            if len(content) > self._MAX_EXISTING_FILE_BYTES:
                                content = (
                                    content[: self._MAX_EXISTING_FILE_BYTES]
                                    + f"\n\n# ... truncated ({len(content)} bytes total)"
                                )
                            dep_files[str(gen_file)] = content
                    except (UnicodeDecodeError, OSError) as exc:
                        logger.warning(
                            "IMPLEMENT: could not read dep output %s: %s",
                            gen_file, exc,
                        )
                dep_outputs[dep_id] = dep_files
        if dep_outputs:
            ctx["dependency_outputs"] = dep_outputs

        return ctx

    def _generate_for_task(
        self,
        task: SeedTask,
        context: Dict[str, Any],
        project_root: Path,
        generator: CodeGenerator,
    ) -> Tuple[Dict[str, Any], GenerationResult]:
        """Run code generation for a single task and return report + result.

        Args:
            task: The seed task.
            context: Task context from ``_build_task_context``.
            project_root: Root directory for output.
            generator: The code generator to invoke.

        Returns:
            Tuple of (task_report dict, GenerationResult).
        """
        task_report: Dict[str, Any] = {
            "task_id": task.task_id,
            "feature_id": task.feature_id,
            "title": task.title,
            "domain": task.domain,
            "target_files": task.target_files,
            "estimated_loc": task.estimated_loc,
            "depends_on": task.depends_on,
            "prompt_constraints_count": len(task.prompt_constraints),
            "validators": task.post_generation_validators,
        }

        result = generator.generate(
            task=task.description,
            context=context,
            target_files=task.target_files,
        )
        task_report["status"] = "generated" if result.success else "generation_failed"
        task_report["cost"] = result.cost_usd
        task_report["tokens"] = {
            "input": result.input_tokens,
            "output": result.output_tokens,
        }
        task_report["iterations"] = result.iterations
        if result.error:
            task_report["error"] = result.error

        return task_report, result

    def _check_environment(self, task: SeedTask) -> List[Dict[str, Any]]:
        """Check environment readiness for a task.

        Returns list of environment issues (fail/warn checks).
        """
        return [
            c for c in task.environment_checks
            if c.get("status") in ("fail", "warn")
        ]

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        project_root = Path(context.get("project_root", "."))

        logger.info("IMPLEMENT phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        task_reports: list[dict[str, Any]] = []
        total_cost = 0.0
        prior_results: Dict[str, GenerationResult] = {}

        for task in tasks:
            env_issues = self._check_environment(task)

            if dry_run:
                # --- Dry-run path (unchanged from original) ---
                task_report: Dict[str, Any] = {
                    "task_id": task.task_id,
                    "feature_id": task.feature_id,
                    "title": task.title,
                    "domain": task.domain,
                    "target_files": task.target_files,
                    "estimated_loc": task.estimated_loc,
                    "depends_on": task.depends_on,
                    "prompt_constraints_count": len(task.prompt_constraints),
                    "validators": task.post_generation_validators,
                    "status": "dry_run_skipped",
                }
                if env_issues:
                    task_report["environment_issues"] = env_issues
                task_reports.append(task_report)
                continue

            # --- Real-mode path ---

            # Skip tasks with blocking environment failures
            if any(c.get("status") == "fail" for c in env_issues):
                logger.warning(
                    "IMPLEMENT: skipping task %s due to environment failures",
                    task.task_id,
                )
                task_reports.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "env_blocked",
                    "environment_issues": env_issues,
                })
                continue

            # Skip tasks whose dependencies failed
            failed_deps = [
                dep_id for dep_id in task.depends_on
                if dep_id in prior_results and not prior_results[dep_id].success
            ]
            if failed_deps:
                logger.warning(
                    "IMPLEMENT: skipping task %s — deps failed: %s",
                    task.task_id, failed_deps,
                )
                task_reports.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "dep_blocked",
                    "failed_dependencies": failed_deps,
                })
                continue

            # Build context and generate
            task_ctx = self._build_task_context(task, project_root, prior_results)

            generator = self._resolve_generator(project_root)
            report, result = self._generate_for_task(
                task, task_ctx, project_root, generator,
            )

            prior_results[task.task_id] = result
            total_cost += result.cost_usd
            task_reports.append(report)

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
            "generation_results": {
                tid: {"success": r.success, "error": r.error, "cost": r.cost_usd}
                for tid, r in prior_results.items()
            },
        }

        context["implementation"] = output
        context["generation_results"] = prior_results  # for TEST phase
        duration = time.monotonic() - start

        logger.info(
            "IMPLEMENT phase complete: %d tasks processed, $%.4f cost (%.2fs)",
            len(task_reports), total_cost, duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}


class TestPhaseHandler(AbstractPhaseHandler):
    """TEST phase: Run post-generation validators against generated code.

    In dry-run mode: reports the test plan per task (unchanged).
    In real mode: executes validator commands (pytest, mypy, ruff, etc.)
    as subprocesses and collects pass/fail results.

    Helpers:
        * ``_resolve_validator_command`` — maps validator names to CLI commands.
        * ``_run_validator`` — executes a single validator subprocess with
          timeout handling.
        * ``_run_validators_for_task`` — runs all validators for one task,
          skipping tasks whose generation was not successful.
    """

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()

    # ------------------------------------------------------------------
    # Validator command mapping
    # ------------------------------------------------------------------

    #: Known validator names → CLI command templates.
    #: ``{project_root}`` and ``{target_files}`` are substituted at runtime.
    VALIDATOR_COMMANDS: Dict[str, str] = {
        "pytest": "python -m pytest {target_files} --tb=short -q",
        "mypy": "python -m mypy {target_files} --ignore-missing-imports",
        "ruff": "python -m ruff check {target_files}",
        "ruff_format": "python -m ruff format --check {target_files}",
        "black": "python -m black --check {target_files}",
        "pylint": "python -m pylint {target_files}",
        "import_check": "python -c \"import {module}\"",
        "syntax_check": "python -m py_compile {target_files}",
    }

    def _resolve_validator_command(
        self,
        validator_name: str,
        target_files: List[str],
        project_root: Path,
    ) -> Optional[str]:
        """Resolve a validator name to a runnable CLI command.

        Args:
            validator_name: Name from ``task.post_generation_validators``.
            target_files: List of file paths (relative to project_root).
            project_root: The project root directory.

        Returns:
            Formatted command string, or None if validator is unknown.
        """
        template = self.VALIDATOR_COMMANDS.get(validator_name)
        if template is None:
            logger.warning("TEST: unknown validator %r — skipping", validator_name)
            return None

        files_str = " ".join(str(project_root / f) for f in target_files)
        return template.format(
            target_files=files_str,
            project_root=str(project_root),
            module=target_files[0].replace("/", ".").replace(".py", "") if target_files else "",
        )

    def _run_validator(
        self,
        command: str,
        project_root: Path,
        timeout: int,
    ) -> Dict[str, Any]:
        """Execute a single validator command as a subprocess.

        Args:
            command: The CLI command to run.
            project_root: Working directory for the subprocess.
            timeout: Timeout in seconds.

        Returns:
            Dict with keys: ``passed``, ``returncode``, ``stdout``,
            ``stderr``, ``timed_out``.
        """
        logger.debug("TEST: running validator: %s (cwd=%s)", command, project_root)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(project_root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            passed = proc.returncode == 0
            result = {
                "passed": passed,
                "returncode": proc.returncode,
                "stdout": proc.stdout[-2000:] if proc.stdout else "",
                "stderr": proc.stderr[-2000:] if proc.stderr else "",
                "timed_out": False,
            }
            if not passed:
                logger.info(
                    "TEST: validator failed (rc=%d): %s",
                    proc.returncode,
                    command,
                )
            return result
        except subprocess.TimeoutExpired:
            logger.warning(
                "TEST: validator timed out after %ds: %s", timeout, command
            )
            return {
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Timed out after {timeout}s",
                "timed_out": True,
            }
        except OSError as exc:
            logger.error("TEST: validator command failed to start: %s", exc)
            return {
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": f"Command failed to start: {exc}",
                "timed_out": False,
            }

    def _run_validators_for_task(
        self,
        task: SeedTask,
        project_root: Path,
        generation_result: Optional[GenerationResult],
    ) -> Dict[str, Any]:
        """Run all validators for a single task.

        Validators are only executed when *generation_result* indicates
        success.  If the generation failed or was not attempted the task
        is reported as skipped with ``all_passed = False``.

        Args:
            task: The seed task.
            project_root: Project root directory.
            generation_result: The generation result from IMPLEMENT phase
                (if any).

        Returns:
            Dict with per-validator results and overall pass/fail.
        """
        # Skip if generation was not successful
        if generation_result is None or not generation_result.success:
            return {
                "task_id": task.task_id,
                "title": task.title,
                "domain": task.domain,
                "validators_run": 0,
                "all_passed": False,
                "results": [],
                "skipped_reason": "generation_not_successful",
            }

        validator_results: List[Dict[str, Any]] = []
        all_passed = True

        for validator_name in task.post_generation_validators:
            command = self._resolve_validator_command(
                validator_name, task.target_files, project_root,
            )
            if command is None:
                validator_results.append({
                    "validator": validator_name,
                    "skipped": True,
                    "reason": "unknown_validator",
                })
                continue

            result = self._run_validator(
                command, project_root, self.config.test_timeout_seconds,
            )
            result["validator"] = validator_name
            result["command"] = command
            validator_results.append(result)

            if not result.get("passed", False):
                all_passed = False

        return {
            "task_id": task.task_id,
            "title": task.title,
            "domain": task.domain,
            "validators_run": len(validator_results),
            "all_passed": all_passed,
            "results": validator_results,
        }

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        project_root = Path(context.get("project_root", "."))
        generation_results: Dict[str, GenerationResult] = context.get("generation_results", {})

        logger.info("TEST phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        test_plan: list[dict[str, Any]] = []
        validator_counts: dict[str, int] = defaultdict(int)
        total_passed = 0
        total_failed = 0

        for task in tasks:
            validators = task.post_generation_validators
            for v in validators:
                validator_counts[v] += 1

            if dry_run:
                # --- Dry-run path (unchanged) ---
                test_entry = {
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "validators": validators,
                    "validator_count": len(validators),
                    "status": "dry_run_planned",
                }
                test_plan.append(test_entry)
                continue

            # --- Real-mode path ---
            gen_result = generation_results.get(task.task_id)

            # Skip tasks that were not generated
            if gen_result is None or not gen_result.success:
                test_plan.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "validators": validators,
                    "validator_count": len(validators),
                    "status": "skipped_no_generation",
                })
                continue

            # Run validators
            task_test_result = self._run_validators_for_task(
                task, project_root, gen_result,
            )
            task_test_result["status"] = (
                "passed" if task_test_result["all_passed"] else "failed"
            )
            test_plan.append(task_test_result)

            if task_test_result["all_passed"]:
                total_passed += 1
            else:
                total_failed += 1

        output = {
            "test_plan": test_plan,
            "total_validators": sum(len(t.post_generation_validators) for t in tasks),
            "unique_validators": dict(validator_counts),
            "tasks_with_tests": len([t for t in test_plan if t.get("validator_count", 0) > 0 or t.get("validators_run", 0) > 0]),
            "total_passed": total_passed,
            "total_failed": total_failed,
        }

        context["test_results"] = output
        duration = time.monotonic() - start

        logger.info(
            "TEST phase complete: %d validators across %d tasks, %d passed, %d failed (%.2fs)",
            output["total_validators"], len(test_plan), total_passed, total_failed, duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


class ReviewPhaseHandler(AbstractPhaseHandler):
    """REVIEW phase: LLM-based quality review of generated implementations.

    In dry-run mode: reports review checklist (unchanged).
    In real mode: sends generated code to a review agent (Claude) for
    quality scoring, then aggregates pass/fail verdicts.

    Pass 1 scaffold:
        * ``__init__`` accepts :class:`HandlerConfig`.
        * ``_resolve_review_agent`` lazily creates the review LLM agent.
        * ``_build_review_prompt`` assembles the review prompt for a task.
        * ``_parse_review_response`` extracts score/verdict from LLM output.
        * ``_review_task`` orchestrates a single task review.
        * Real-mode ``execute`` calls helpers but falls through to
          ``"awaiting_implementation"`` until Pass 3 wires the LLM call.
    """

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()
        self._review_agent: Any = None  # Pass 3: BaseAgent instance

    # ------------------------------------------------------------------
    # Review prompt template
    # ------------------------------------------------------------------

    REVIEW_PROMPT_TEMPLATE = """You are reviewing generated code for quality and correctness.

## Task
**ID:** {task_id}
**Title:** {title}
**Domain:** {domain}

## Task Description
{description}

## Prompt Constraints
{constraints}

## Generated Code
```
{generated_code}
```

## Test Results
{test_results}

## Review Instructions
Evaluate the implementation against the task description and constraints.

## Required Output Format

### Score: [0-100]

### Verdict: [PASS/FAIL]
PASS if score >= {pass_threshold} and no blocking issues.

### Strengths
- [What was done well]

### Issues
- [severity: BLOCKING/MAJOR/MINOR] [description]

### Suggestions
- [Specific improvements]
"""

    def _resolve_review_agent(self) -> Any:
        """Lazily resolve the review agent from config.

        Creates a :class:`BaseAgent` instance using the lead_agent spec
        with low temperature for consistent reviews.

        Returns:
            A BaseAgent instance.

        TODO: Pass 3 — instantiate via ``resolve_agent_spec``.
        """
        if self._review_agent is not None:
            return self._review_agent

        # Pass 3: replace with actual agent resolution
        #   from startd8.utils.agent_resolution import resolve_agent_spec
        #   self._review_agent = resolve_agent_spec(
        #       self.config.lead_agent,
        #       temperature=self.config.review_temperature,
        #   )
        #   return self._review_agent
        raise NotImplementedError(
            "Review agent not yet wired (Pass 3)"
        )

    def _build_review_prompt(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: Dict[str, Any],
    ) -> str:
        """Build the review prompt for a single task.

        Args:
            task: The seed task.
            generated_code: The code that was generated.
            test_results: Test results from the TEST phase.

        Returns:
            Formatted review prompt string.
        """
        constraints_str = "\n".join(
            f"- {c}" for c in task.prompt_constraints
        ) or "None specified"

        test_str = json.dumps(test_results, indent=2, default=str) if test_results else "No tests run"

        return self.REVIEW_PROMPT_TEMPLATE.format(
            task_id=task.task_id,
            title=task.title,
            domain=task.domain,
            description=task.description,
            constraints=constraints_str,
            generated_code=generated_code[:8000],  # truncate for prompt
            test_results=test_str[:2000],
            pass_threshold=self.config.pass_threshold,
        )

    def _parse_review_response(self, response: str) -> Dict[str, Any]:
        """Parse score, verdict, and issues from the LLM review response.

        Args:
            response: Raw LLM output.

        Returns:
            Dict with ``score``, ``verdict``, ``strengths``, ``issues``, ``suggestions``.

        TODO: Pass 3 — robust parsing with regex fallbacks.
        """
        import re

        score = 0
        verdict = "FAIL"

        # Extract score
        score_match = re.search(r"###\s*Score:\s*(\d+)", response)
        if score_match:
            score = min(100, max(0, int(score_match.group(1))))

        # Extract verdict
        verdict_match = re.search(r"###\s*Verdict:\s*(PASS|FAIL)", response, re.IGNORECASE)
        if verdict_match:
            verdict = verdict_match.group(1).upper()

        return {
            "score": score,
            "verdict": verdict,
            "passed": verdict == "PASS" and score >= self.config.pass_threshold,
            "raw_response": response[:4000],  # truncate for storage
        }

    def _review_task(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Conduct LLM review for a single task.

        Args:
            task: The seed task.
            generated_code: Code to review.
            test_results: Test results for context.

        Returns:
            Review result dict with score, verdict, cost.

        TODO: Pass 3 — call review agent and parse response.
        """
        # Pass 3: replace with actual LLM call
        #   agent = self._resolve_review_agent()
        #   prompt = self._build_review_prompt(task, generated_code, test_results)
        #   response_text, token_count, token_usage = agent.generate(prompt)
        #   review = self._parse_review_response(response_text)
        #   review["cost"] = <calculate from token_usage>
        #   review["tokens"] = {"input": token_usage.input_tokens, "output": token_usage.output_tokens}
        #   return review

        return {
            "task_id": task.task_id,
            "score": 0,
            "verdict": "NOT_REVIEWED",
            "passed": False,
            "cost": 0.0,
            "status": "awaiting_implementation",
        }

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        preflight_summary = context.get("preflight_summary", {})
        generation_results: Dict[str, GenerationResult] = context.get("generation_results", {})
        test_results_ctx: Dict[str, Any] = context.get("test_results", {})
        test_plan = test_results_ctx.get("test_plan", [])
        test_by_task = {t["task_id"]: t for t in test_plan if isinstance(t, dict)}

        logger.info("REVIEW phase: reviewing %d tasks (dry_run=%s)", len(tasks), dry_run)

        review_items: list[dict[str, Any]] = []
        constraint_coverage: dict[str, int] = defaultdict(int)
        total_cost = 0.0
        total_passed = 0
        total_failed = 0

        for task in tasks:
            # Count constraint types (always, for coverage report)
            for constraint in task.prompt_constraints:
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

            if dry_run:
                # --- Dry-run path (unchanged) ---
                review_items.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "constraint_count": len(task.prompt_constraints),
                    "env_failures": len(env_fails),
                    "env_warnings": len(env_warns),
                    "review_status": "dry_run_pending",
                })
                continue

            # --- Real-mode path (scaffolded — wired in Pass 3) ---
            gen_result = generation_results.get(task.task_id)

            # Skip tasks that were not generated successfully
            if gen_result is None or not gen_result.success:
                review_items.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "constraint_count": len(task.prompt_constraints),
                    "env_failures": len(env_fails),
                    "env_warnings": len(env_warns),
                    "review_status": "skipped_no_generation",
                })
                continue

            # Read generated code for review
            # Pass 3: read actual file contents from gen_result.generated_files
            generated_code = "# TODO: Pass 3 — read generated files"
            task_test = test_by_task.get(task.task_id, {})

            review = self._review_task(task, generated_code, task_test)
            review["title"] = task.title
            review["domain"] = task.domain
            review["constraint_count"] = len(task.prompt_constraints)
            review["env_failures"] = len(env_fails)
            review["env_warnings"] = len(env_warns)
            review["review_status"] = review.get("status", "awaiting_implementation")

            total_cost += review.get("cost", 0.0)
            if review.get("passed", False):
                total_passed += 1
            else:
                total_failed += 1

            review_items.append(review)

        output = {
            "review_items": review_items,
            "preflight_summary": preflight_summary,
            "constraint_coverage": dict(constraint_coverage),
            "tasks_with_env_issues": len([
                r for r in review_items
                if r.get("env_failures", 0) > 0 or r.get("env_warnings", 0) > 0
            ]),
            "total_cost": total_cost,
            "total_passed": total_passed,
            "total_failed": total_failed,
        }

        context["review_results"] = output
        duration = time.monotonic() - start

        logger.info(
            "REVIEW phase complete: %d items, %d passed, %d failed, $%.4f cost (%.2fs)",
            len(review_items), total_passed, total_failed, total_cost, duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}


class FinalizePhaseHandler(AbstractPhaseHandler):
    """FINALIZE phase: Collect artifacts and write comprehensive execution report.

    Produces a workflow execution report aggregating all phase results,
    lists generated files with checksums and line counts, computes a
    per-task status rollup joining generation/test/review outcomes, and
    writes both a human-readable report and a machine-readable manifest.

    Key outputs written to ``output_dir``:

    * ``workflow-execution-report.json`` — full summary with cost
      breakdown, artifact inventory, and per-phase stats.
    * ``generation-manifest.json`` — machine-readable manifest with
      per-task status, artifact checksums, and cost attribution.
    """

    def __init__(
        self,
        output_dir: Optional[str] = None,
        handler_config: Optional[HandlerConfig] = None,
    ) -> None:
        self.output_dir = output_dir
        self.config = handler_config or HandlerConfig()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_generated_artifacts(
        self,
        context: dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Inventory all files generated during the IMPLEMENT phase.

        Reads ``context["generation_results"]`` and lists output files
        with sizes, hashes, line counts, and domain tags.

        Args:
            context: Shared workflow context.

        Returns:
            List of artifact dicts with keys: ``task_id``, ``path``,
            ``exists``, ``size_bytes``, ``line_count``, ``sha256``,
            ``domain``.
        """
        artifacts: List[Dict[str, Any]] = []
        generation_results: Dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )

        # Build task_id → SeedTask lookup for domain metadata
        tasks: list[SeedTask] = context.get("tasks", [])
        id_to_task: Dict[str, SeedTask] = {t.task_id: t for t in tasks}

        for task_id, result in generation_results.items():
            if result.success:
                task = id_to_task.get(task_id)
                for fpath in result.generated_files:
                    artifact: Dict[str, Any] = {
                        "task_id": task_id,
                        "path": str(fpath),
                        "exists": (
                            fpath.exists() if hasattr(fpath, "exists") else False
                        ),
                        "domain": task.domain if task else "unknown",
                    }
                    if hasattr(fpath, "exists") and fpath.exists():
                        raw_bytes = fpath.read_bytes()
                        artifact["size_bytes"] = len(raw_bytes)
                        artifact["sha256"] = hashlib.sha256(raw_bytes).hexdigest()
                        try:
                            text = raw_bytes.decode("utf-8", errors="strict")
                            artifact["line_count"] = len(text.splitlines())
                        except (UnicodeDecodeError, ValueError):
                            # Binary file — line count not applicable
                            artifact["line_count"] = None
                    artifacts.append(artifact)

        return artifacts

    def _build_cost_summary(self, context: dict[str, Any]) -> Dict[str, Any]:
        """Aggregate costs across all phases.

        Args:
            context: Shared workflow context.

        Returns:
            Dict with per-phase and total cost breakdowns.

        Note:
            PLAN and SCAFFOLD phases are zero-cost (no LLM calls) and
            excluded for clarity.  TEST phase cost is included even
            though current validators are subprocess-based (zero cost);
            this future-proofs for LLM-based test generation.
        """
        implementation = context.get("implementation", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})

        impl_cost = implementation.get("total_cost", 0.0)
        test_cost = test_results.get("total_cost", 0.0)
        review_cost = review_results.get("total_cost", 0.0)
        total = impl_cost + test_cost + review_cost

        return {
            "implementation_cost": impl_cost,
            "test_cost": test_cost,
            "review_cost": review_cost,
            "total_cost": total,
            "currency": "USD",
        }

    def _write_manifest(
        self,
        artifacts: List[Dict[str, Any]],
        summary: Dict[str, Any],
        context: dict[str, Any],
        output_dir: Path,
    ) -> Optional[Path]:
        """Write a machine-readable manifest of all changes.

        Includes per-task status rollup joining generation results with
        test and review outcomes, artifact checksums (from enriched
        ``_collect_generated_artifacts``), and cost breakdown.

        Args:
            artifacts: List of generated artifact dicts (with ``sha256``).
            summary: The full workflow summary.
            context: Shared workflow context (for test/review joining).
            output_dir: Directory to write the manifest.

        Returns:
            Path to the manifest file, or None if no artifacts.
        """
        if not artifacts:
            return None

        # Per-task status rollup: join generation, test, and review data
        generation_results: Dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )
        test_results_map: Dict[str, Any] = context.get("test_results", {}).get(
            "per_task", {}
        )
        review_results_map: Dict[str, Any] = context.get("review_results", {}).get(
            "per_task", {}
        )

        task_status: Dict[str, Dict[str, Any]] = {}
        for task_id, gen_result in generation_results.items():
            test_info = test_results_map.get(task_id, {})
            review_info = review_results_map.get(task_id, {})
            task_status[task_id] = {
                "generated": gen_result.success,
                "files_count": len(gen_result.generated_files),
                "generation_cost_usd": gen_result.cost_usd,
                "tests_passed": test_info.get("passed", None),
                "review_score": review_info.get("score", None),
                "review_passed": review_info.get("passed", None),
            }

        manifest = {
            "workflow_version": "0.4.0",
            "artifacts": artifacts,
            "task_status": task_status,
            "summary": {
                "plan_title": summary.get("plan_title", ""),
                "task_count": summary.get("task_count", 0),
                "total_cost": summary.get("cost_summary", {}).get(
                    "total_cost", 0.0
                ),
                "status": summary.get("status", "unknown"),
            },
        }

        manifest_path = output_dir / "generation-manifest.json"
        try:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, default=str)
            logger.info("Wrote manifest: %s", manifest_path)
        except OSError as exc:
            logger.warning("Failed to write manifest to %s: %s", manifest_path, exc)
            return None
        return manifest_path

    # ------------------------------------------------------------------
    # Public execute
    # ------------------------------------------------------------------

    def execute(
        self,
        phase: WorkflowPhase,
        context: dict[str, Any],
        dry_run: bool = False,
    ) -> dict[str, Any]:
        start = time.monotonic()
        logger.info("FINALIZE phase: generating summary (dry_run=%s)", dry_run)

        plan_title = context.get("plan_title", "Untitled")
        tasks: list[SeedTask] = _ensure_context_loaded(context)
        domain_summary = context.get("domain_summary", {})
        preflight_summary = context.get("preflight_summary", {})
        scaffold = context.get("scaffold", {})
        implementation = context.get("implementation", {})
        test_results = context.get("test_results", {})
        review_results = context.get("review_results", {})

        # Collect artifacts and costs
        artifacts = self._collect_generated_artifacts(context)
        cost_summary = self._build_cost_summary(context)

        # Compute overall status rollup
        generation_results: Dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )
        total_tasks = len(tasks)
        generated_ok = sum(
            1 for r in generation_results.values() if r.success
        )
        generated_fail = sum(
            1 for r in generation_results.values() if not r.success
        )

        if generated_fail == 0 and generated_ok == total_tasks:
            overall_status = "success"
        elif generated_ok == 0:
            overall_status = "failed"
        else:
            overall_status = "partial"

        summary: Dict[str, Any] = {
            "plan_title": plan_title,
            "task_count": total_tasks,
            "status": overall_status,
            "tasks_succeeded": generated_ok,
            "tasks_failed": generated_fail,
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
                "generation_results": {
                    tid: {
                        "success": r.success,
                        "error": r.error,
                        "cost_usd": r.cost_usd,
                        "files": [str(f) for f in r.generated_files],
                        "model": r.model,
                        "iterations": r.iterations,
                    }
                    for tid, r in generation_results.items()
                },
            },
            "test_summary": {
                "total_validators": test_results.get("total_validators", 0),
                "tasks_with_tests": test_results.get("tasks_with_tests", 0),
                "total_passed": test_results.get("total_passed", 0),
                "total_failed": test_results.get("total_failed", 0),
            },
            "review_summary": {
                "tasks_with_env_issues": review_results.get("tasks_with_env_issues", 0),
                "total_passed": review_results.get("total_passed", 0),
                "total_failed": review_results.get("total_failed", 0),
                "total_cost": review_results.get("total_cost", 0.0),
            },
            "cost_summary": cost_summary,
            "generated_artifacts": artifacts,
            "artifact_count": len(artifacts),
            "dry_run": dry_run,
        }

        # Write report and manifest
        if self.output_dir and not dry_run:
            output_path = Path(self.output_dir) / "workflow-execution-report.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2, default=str)
            logger.info("Wrote execution report to %s", output_path)
            summary["report_path"] = str(output_path)

            # Write manifest of generated files
            manifest_path = self._write_manifest(
                artifacts, summary, context, Path(self.output_dir),
            )
            if manifest_path:
                summary["manifest_path"] = str(manifest_path)

        context["workflow_summary"] = summary
        duration = time.monotonic() - start

        logger.info(
            "FINALIZE phase complete: %s — %d artifacts, $%.4f total cost (%.2fs)",
            overall_status, len(artifacts),
            cost_summary.get("total_cost", 0.0), duration,
        )

        return {"output": summary, "cost": 0.0, "metadata": {"duration": duration}}


# ============================================================================
# Factory
# ============================================================================


class ContextSeedHandlers:
    """Factory for creating all phase handlers from an enriched context seed.

    Accepts optional agent configuration that is propagated to all handlers
    requiring LLM access (IMPLEMENT, TEST, REVIEW) and artifact generation
    (FINALIZE).

    Example::

        handlers = ContextSeedHandlers.create_all(
            enriched_seed_path="out/artisan-context-seed-enriched.json",
            lead_agent="anthropic:claude-sonnet-4-5-20250927",
            drafter_agent="gemini:gemini-2.5-flash-lite",
            output_dir="out/artifacts",
        )
    """

    @staticmethod
    def create_all(
        enriched_seed_path: str,
        output_dir: Optional[str] = None,
        *,
        # Agent configuration (keyword-only)
        lead_agent: str = "anthropic:claude-sonnet-4-5-20250927",
        drafter_agent: str = "gemini:gemini-2.5-flash-lite",
        max_iterations: int = 3,
        pass_threshold: int = 80,
        max_tokens: Optional[int] = None,
        fail_on_truncation: bool = True,
        check_truncation: bool = True,
        strict_truncation: bool = False,
        test_timeout_seconds: int = 120,
        review_temperature: float = 0.0,
        code_generator: Optional[CodeGenerator] = None,
    ) -> dict[WorkflowPhase, AbstractPhaseHandler]:
        """Create handlers for all six workflow phases.

        Args:
            enriched_seed_path: Path to the enriched context seed JSON.
            output_dir: Optional output directory for artifacts.
            lead_agent: Agent spec for architect/reviewer.
            drafter_agent: Agent spec for drafter.
            max_iterations: Maximum draft → review iterations per task.
            pass_threshold: Minimum review score (0-100) to pass.
            max_tokens: Override max_tokens for agent creation.
            fail_on_truncation: Fail workflow on detected truncation.
            check_truncation: Enable heuristic truncation detection.
            strict_truncation: Use strict detection threshold.
            test_timeout_seconds: Timeout for each validator subprocess.
            review_temperature: Temperature for LLM review calls.
            code_generator: Optional pre-configured CodeGenerator instance.

        Returns:
            Dict mapping WorkflowPhase → handler instance.
        """
        config = HandlerConfig(
            lead_agent=lead_agent,
            drafter_agent=drafter_agent,
            max_iterations=max_iterations,
            pass_threshold=pass_threshold,
            max_tokens=max_tokens,
            fail_on_truncation=fail_on_truncation,
            check_truncation=check_truncation,
            strict_truncation=strict_truncation,
            test_timeout_seconds=test_timeout_seconds,
            review_temperature=review_temperature,
        )

        return {
            WorkflowPhase.PLAN: PlanPhaseHandler(enriched_seed_path),
            WorkflowPhase.SCAFFOLD: ScaffoldPhaseHandler(),
            WorkflowPhase.IMPLEMENT: ImplementPhaseHandler(
                handler_config=config,
                code_generator=code_generator,
            ),
            WorkflowPhase.TEST: TestPhaseHandler(handler_config=config),
            WorkflowPhase.REVIEW: ReviewPhaseHandler(handler_config=config),
            WorkflowPhase.FINALIZE: FinalizePhaseHandler(
                output_dir=output_dir,
                handler_config=config,
            ),
        }
