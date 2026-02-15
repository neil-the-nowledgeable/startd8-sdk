"""
Context Seed Phase Handlers for ArtisanContractorWorkflow.

Bridges enriched context seeds (from PlanIngestionWorkflow + DomainPreflightWorkflow)
to the ArtisanContractorWorkflow orchestrator by providing concrete AbstractPhaseHandler
implementations for each WorkflowPhase.

WorkflowPhase mapping (from artisan_contractor.py docstring):
    PLAN      → Load seed + validate + build task plan
    SCAFFOLD  → Verify target directories + resolve dependencies
    DESIGN    → Generate design docs per task via DesignDocumentationPhase
    IMPLEMENT → Generate code per task via LeadContractorCodeGenerator
    TEST      → Run post-generation validators against generated code
    REVIEW    → LLM-based quality review of generated implementations
    FINALIZE  → Collect artifacts + write comprehensive execution report

Context dict contract (keys populated by each phase):
    After PLAN:      tasks, task_index, plan_title, preflight_summary, domain_summary,
                     enriched_seed_path
    After SCAFFOLD:  scaffold (summary dict)
    After DESIGN:    design_results (Dict[task_id, dict] with design_document, agreed, iterations, cost)
    After IMPLEMENT: implementation (output dict), generation_results (Dict[task_id, GenerationResult])
    After TEST:      test_results (Dict with test_plan, per_task, total_cost)
    After REVIEW:    review_results (Dict with review_items, per_task, total_cost)
    After FINALIZE:  workflow_summary (final manifest dict)

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

import asyncio
import hashlib
import json
import shlex
import subprocess
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import (
    AbstractPhaseHandler,
    WorkflowPhase,
)
from startd8.contractors.protocols import (
    CodeGenerator,
    DRAFT_MODEL_CLAUDE_HAIKU,
    GenerationResult,
    REVIEW_MODEL_CLAUDE_OPUS,
)
from startd8.utils.file_operations import atomic_write_json
from startd8.utils.token_usage import (
    token_usage_cost,
    token_usage_input,
    token_usage_output,
)

from startd8.contractors.context_schema import (
    DesignPhaseOutput,
    FinalizePhaseOutput,
    ImplementPhaseOutput,
    PlanPhaseOutput,
    ReviewPhaseOutput,
    ScaffoldPhaseOutput,
    ValidationPhaseOutput,
)
from startd8.logging_config import get_logger

logger = get_logger(__name__)

from startd8.contractors.gate_contracts import GateEmitter

__all__ = [
    "HandlerConfig",
    "ContextSeedHandlers",
    "PlanPhaseHandler",
    "ScaffoldPhaseHandler",
    "DesignPhaseHandler",
    "ImplementPhaseHandler",
    "TestPhaseHandler",
    "ReviewPhaseHandler",
    "FinalizePhaseHandler",
]


def _log_task_timing(
    phase: str,
    task_id: str,
    index: int,
    total: int,
    phase_started_mono: float,
    previous_task_started_mono: Optional[float],
) -> float:
    """Log elapsed and inter-task timing for a phase task loop."""
    now = time.monotonic()
    elapsed_s = now - phase_started_mono
    elapsed_m = elapsed_s / 60.0
    delta_s = 0.0 if previous_task_started_mono is None else now - previous_task_started_mono
    logger.info(
        "%s task %d/%d: %s (elapsed %.1fs / %.2fmin, +%.1fs since previous task)",
        phase,
        index,
        total,
        task_id,
        elapsed_s,
        elapsed_m,
        delta_s,
    )
    return now


# ============================================================================
# Handler configuration
# ============================================================================


@dataclass
class HandlerConfig:
    """Shared configuration propagated to all phase handlers.

    Attributes:
        lead_agent: Agent spec for architect/reviewer.
            Defaults to ``REVIEW_MODEL_CLAUDE_OPUS`` from the model catalog.
        drafter_agent: Agent spec for drafter.
            Defaults to ``DRAFT_MODEL_CLAUDE_HAIKU`` from the model catalog.
        max_iterations: Maximum draft → review iterations per task.
        pass_threshold: Minimum review score (0-100) to pass.
        max_tokens: Override max_tokens for agent creation (None = provider default).
        design_max_tokens: Override max_output_tokens for design phase LLM calls.
            When set, overrides per-task design_calibration max_output_tokens.
            Use to avoid truncation for complex design docs (e.g., 8192).
        fail_on_truncation: Fail workflow on detected truncation.
        check_truncation: Enable heuristic truncation detection.
        strict_truncation: Use strict detection threshold.
        test_timeout_seconds: Timeout for each validator subprocess.
        review_temperature: Temperature for LLM review calls.
        review_max_code_chars: Max characters of generated code to include in review prompt.
        development_timeout_seconds: Timeout for the DevelopmentPhase thread (None = no limit).
        scaffold_test_first: For artifact generator tasks, ensure test scaffolding exists
            before implementation (Item 12). Default True.
        force_implement: If True, ignore cached generation_results and always run fresh
            IMPLEMENT (no resume from .startd8/state/generation_results.json).
    """

    lead_agent: str = REVIEW_MODEL_CLAUDE_OPUS.agent_spec
    drafter_agent: str = DRAFT_MODEL_CLAUDE_HAIKU.agent_spec
    max_iterations: int = 3
    pass_threshold: int = 80
    max_tokens: Optional[int] = None
    design_max_tokens: Optional[int] = None
    fail_on_truncation: bool = True
    check_truncation: bool = True
    strict_truncation: bool = False
    test_timeout_seconds: int = 120
    review_temperature: float = 0.0
    review_max_code_chars: int = 8000
    development_timeout_seconds: Optional[float] = None
    auto_commit: bool = True
    scaffold_test_first: bool = True
    force_implement: bool = False

    @classmethod
    def from_config(
        cls,
        cli_overrides: Optional[dict[str, Any]] = None,
    ) -> "HandlerConfig":
        """Build a HandlerConfig using the 3-tier priority chain.

        Priority: *cli_overrides* > env vars / config file (via
        ``ConfigManager.get_artisan_setting``) > dataclass defaults.

        Args:
            cli_overrides: Dict of field-name → value from CLI args.
                Only non-``None`` entries are considered overrides.

        Returns:
            A fully resolved ``HandlerConfig``.
        """
        from startd8.config import get_config_manager

        cfg_mgr = get_config_manager()
        overrides = cli_overrides or {}
        kwargs: dict[str, Any] = {}

        for f in fields(cls):
            # CLI override wins
            cli_val = overrides.get(f.name)
            if cli_val is not None:
                kwargs[f.name] = cli_val
                continue

            # Config manager checks env var → config file
            cfg_val = cfg_mgr.get_artisan_setting(f.name)
            if cfg_val is not None:
                kwargs[f.name] = cfg_val
                continue

            # Otherwise let the dataclass default apply (omit from kwargs)

        return cls(**kwargs)


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
    # Task-specific design doc content hints (supplement calibration sections)
    design_doc_sections: list[str]
    # Artifact types this task generates (e.g. dashboard, prometheus_rule, servicemonitor)
    artifact_types_addressed: list[str]
    # File scope from plan ingestion (defense-in-depth Principle 1):
    # Maps target_file → "primary" | "shared" | "stub".
    # When present, artisan uses this instead of re-deriving from design docs.
    file_scope: dict[str, str]

    @classmethod
    def from_seed_entry(cls, entry: dict[str, Any]) -> SeedTask:
        """Parse a task entry from the enriched context seed JSON."""
        config = entry.get("config", {})
        context = config.get("context", {})
        enrichment = entry.get("_enrichment", {})

        # Merge prompt_hints (from plan ingestion shared-module detection)
        # with enrichment prompt_constraints (from domain preflight rules).
        constraints = list(enrichment.get("prompt_constraints", []))
        for hint in context.get("prompt_hints", []):
            if hint not in constraints:
                constraints.append(hint)

        # --- WCP-003: Emit context.defaulted span event when domain is missing ---
        domain = enrichment.get("domain", "unknown")
        if domain == "unknown":
            try:
                from opentelemetry import trace
                span = trace.get_current_span()
                if span and span.is_recording():
                    span.add_event("context.defaulted", attributes={
                        "context.field": "domain",
                        "context.default_value": "unknown",
                        "context.expected_source": "domain_preflight._enrichment",
                        "context.task_id": entry.get("task_id", ""),
                    })
            except Exception:
                pass  # OTel not available — non-fatal
            logger.debug(
                "SeedTask %s: domain defaulted to 'unknown' (enrichment missing or incomplete)",
                entry.get("task_id", "?"),
            )

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
            domain=domain,
            domain_reasoning=enrichment.get("domain_reasoning", ""),
            environment_checks=enrichment.get("environment_checks", []),
            prompt_constraints=constraints,
            post_generation_validators=enrichment.get(
                "post_generation_validators", []
            ),
            available_siblings=enrichment.get("available_siblings", []),
            existing_content_hash=enrichment.get("existing_content_hash"),
            design_doc_sections=context.get("design_doc_sections", []),
            artifact_types_addressed=context.get("artifact_types_addressed", []),
            file_scope=context.get("_file_scope", {}),
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
    def _apply_runtime_task_selection(tasks_in: list[SeedTask]) -> list[SeedTask]:
        """Apply runtime selection (feature-serial single-task execution).

        PLAN-level ``task_filter`` is already applied when tasks are loaded.
        Here we only apply per-feature narrowing used by feature-serial mode.
        """
        current_feature_id = context.get("current_feature_id")
        if not current_feature_id:
            return tasks_in

        selected = [t for t in tasks_in if t.task_id == current_feature_id]
        if not selected:
            known = [t.task_id for t in tasks_in]
            raise RuntimeError(
                "Feature-serial execution requested unknown current_feature_id="
                f"{current_feature_id!r}. Available task_ids: {known}"
            )
        return selected

    tasks: list[SeedTask] | None = context.get("tasks")
    if tasks is not None:
        return _apply_runtime_task_selection(tasks)

    seed_path = context.get("enriched_seed_path")
    if not seed_path:
        raise RuntimeError(
            "Context missing 'tasks' and 'enriched_seed_path' — "
            "cannot reload seed. If resuming from checkpoint, ensure "
            "'enriched_seed_path' is provided in the initial context."
        )

    seed_path_obj = Path(seed_path)
    if not seed_path_obj.exists():
        raise FileNotFoundError(
            f"Enriched seed not found at '{seed_path}' — cannot reload tasks. "
            f"Ensure the seed file exists and the path is correct."
        )

    logger.info("Reloading enriched seed for resumed workflow from %s", seed_path)
    seed_data = _load_enriched_seed(seed_path)
    tasks = _topological_sort(_parse_tasks(seed_data))

    # Apply task filter so resumed workflows honour --task-filter.
    task_filter = context.get("task_filter")
    if task_filter:
        filter_set = set(task_filter)
        tasks = [t for t in tasks if t.task_id in filter_set]
        logger.info(
            "Applied task filter on reload — %d task(s): %s",
            len(tasks),
            [t.task_id for t in tasks],
        )

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
    context["example_artifacts"] = (seed_data.get("artifacts") or {}).get(
        "example_artifacts", {}
    )

    return _apply_runtime_task_selection(tasks)


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

        # Apply task filter if provided (e.g. --task-filter PI-001,PI-002).
        # This narrows the execution to a subset of tasks while preserving
        # the full seed's architectural context and calibration data.
        task_filter = context.get("task_filter")
        if task_filter:
            filter_set = set(task_filter)
            all_ids = {t.task_id for t in sorted_tasks}
            all_count = len(sorted_tasks)
            sorted_tasks = [t for t in sorted_tasks if t.task_id in filter_set]
            missing = filter_set - all_ids
            if missing:
                # Show available IDs so the user can spot typos (e.g. P1-001 vs PI-001)
                sample = sorted(all_ids)[:10]
                suffix = f" ... ({all_count} total)" if all_count > 10 else ""
                raise ValueError(
                    f"Task filter IDs not found in seed: {', '.join(sorted(missing))}. "
                    f"Available IDs: {', '.join(sample)}{suffix}"
                )
            logger.info(
                "PLAN phase: task filter applied — %d of %d tasks selected: %s",
                len(sorted_tasks), all_count,
                [t.task_id for t in sorted_tasks],
            )

        # Extract plan metadata
        plan_meta = seed_data.get("plan", {})
        preflight = seed_data.get("_preflight", {})

        # Domain summary (computed over filtered tasks)
        domain_counts: dict[str, int] = defaultdict(int)
        for t in sorted_tasks:
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
        context["total_estimated_loc"] = sum(t.estimated_loc for t in sorted_tasks)
        context["architectural_context"] = seed_data.get("architectural_context", {})
        context["design_calibration"] = seed_data.get("design_calibration", {})
        # Item 9: example artifacts per type for implement phase
        context["example_artifacts"] = (seed_data.get("artifacts") or {}).get(
            "example_artifacts", {}
        )

        # -- Phase 2 data flow fixes: extract ContextCore enrichment --
        _artifacts = seed_data.get("artifacts") or {}

        # Fix 1a: provenance chain — source_checksum
        source_checksum = _artifacts.get("source_checksum")
        context["source_checksum"] = source_checksum
        if source_checksum:
            logger.info(
                "PLAN phase: source_checksum present — provenance chain active: %s",
                source_checksum[:16],
            )
        else:
            logger.warning(
                "PLAN phase: source_checksum absent in seed — provenance chain broken"
            )

        # Fix 2b: parameter_sources for DESIGN/IMPLEMENT prompt injection
        context["parameter_sources"] = _artifacts.get("parameter_sources", {})

        # Fix 3b: semantic_conventions for DESIGN/IMPLEMENT prompt injection
        context["semantic_conventions"] = _artifacts.get("semantic_conventions", {})

        # Fix 5a: output_conventions for SCAFFOLD extension validation
        context["output_conventions"] = _artifacts.get("output_conventions", {})

        output = {
            "plan_title": context["plan_title"],
            "task_count": len(sorted_tasks),
            "execution_order": [t.task_id for t in sorted_tasks],
            "domain_summary": dict(domain_counts),
            "preflight_check_summary": check_summary,
            "total_estimated_loc": context["total_estimated_loc"],
            "preflight_failures": fail_count,
            "goals": context["plan_goals"],
        }
        if task_filter:
            output["task_filter"] = task_filter

        duration = time.monotonic() - start
        logger.info(
            "PLAN phase complete: %d tasks, %d domains, %d preflight failures (%.2fs)",
            len(sorted_tasks), len(domain_counts), fail_count, duration,
        )

        if fail_count > 0 and not dry_run:
            logger.warning(
                "PLAN phase: %d preflight failures detected — review before implementing",
                fail_count,
            )
            if context.get("abort_on_preflight_fail"):
                raise ValueError(
                    f"PLAN phase aborted: {fail_count} preflight failure(s) detected. "
                    "Address preflight issues before proceeding, or run without --abort-on-preflight-fail."
                )

        # Context contract: validate PLAN output model
        PlanPhaseOutput(
            enriched_seed_path=context["enriched_seed_path"],
            tasks=context["tasks"],
            task_index=context["task_index"],
            plan_title=context["plan_title"],
            plan_goals=context["plan_goals"],
            domain_summary=context["domain_summary"],
            preflight_summary=context["preflight_summary"],
            total_estimated_loc=context["total_estimated_loc"],
            architectural_context=context.get("architectural_context", {}),
            design_calibration=context.get("design_calibration", {}),
            example_artifacts=context.get("example_artifacts", {}),
            source_checksum=context.get("source_checksum"),
            parameter_sources=context.get("parameter_sources", {}),
            semantic_conventions=context.get("semantic_conventions", {}),
            output_conventions=context.get("output_conventions", {}),
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

        # Fix 5b: soft-validate target file extensions against output_conventions
        output_conventions = context.get("output_conventions", {})
        extension_warnings: list[str] = []
        if output_conventions:
            for task in tasks:
                for atype in task.artifact_types_addressed:
                    expected_ext = output_conventions.get(atype, {}).get("output_ext")
                    if expected_ext:
                        for tf in task.target_files:
                            if not tf.endswith(expected_ext):
                                msg = (
                                    f"task {task.task_id} file {tf} doesn't match "
                                    f"expected extension {expected_ext} for {atype}"
                                )
                                extension_warnings.append(msg)
                                logger.warning("SCAFFOLD: %s", msg)

        output = {
            "directories_needed": sorted(dirs_needed),
            "directories_exist": sorted(dirs_exist),
            "directories_created": sorted(dirs_created),
            "directories_missing": sorted(dirs_missing) if dry_run else [],
            "existing_target_files": files_existing,
            "skipped_targets": skipped_targets,
            "project_root": str(project_root),
            "extension_warnings": extension_warnings,
        }

        # Store scaffold results in context
        context["scaffold"] = output

        # Context contract: validate SCAFFOLD output model
        ScaffoldPhaseOutput(scaffold=context["scaffold"])

        duration = time.monotonic() - start
        logger.info(
            "SCAFFOLD phase complete: %d dirs needed, %d exist, %d created, %d existing files (%.2fs)",
            len(dirs_needed), len(dirs_exist), len(dirs_created), len(files_existing), duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


class DesignPhaseHandler(AbstractPhaseHandler):
    """DESIGN phase: Generate design docs per task via DesignDocumentationPhase.

    In dry-run mode: reports what would be designed per task (no LLM calls).
    In real mode: delegates to :class:`DesignDocumentationPhase` for each task,
    running the async dual-review design pipeline via a thread-owned event loop
    (same pattern as :class:`ImplementPhaseHandler`).

    Data flow:
        1. ``SeedTask`` → ``FeatureContext`` (per task)
        2. ``DesignDocumentationPhase.run(context)`` → ``DesignDocumentResult``
        3. Results serialized → ``context["design_results"]``

    Output files:
        When ``output_dir`` is set, writes ``{task_id}-design.md`` files
        containing the raw design document text.
    """

    supports_feature_serial: bool = True

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        output_dir: Optional[str] = None,
    ) -> None:
        self.config = handler_config or HandlerConfig()
        self.output_dir = output_dir
        self._llm_backend: Any = None
        self._design_phase: Any = None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_llm_backend(self) -> Any:
        """Lazily create the AgentLLMBackend."""
        if self._llm_backend is not None:
            return self._llm_backend

        from startd8.contractors.artisan_phases.design_documentation import (
            AgentLLMBackend,
        )

        self._llm_backend = AgentLLMBackend(agent_spec=self.config.lead_agent)
        return self._llm_backend

    def _get_design_phase(self) -> Any:
        """Lazily create the DesignDocumentationPhase."""
        if self._design_phase is not None:
            return self._design_phase

        from startd8.contractors.artisan_phases.design_documentation import (
            DesignDocumentationPhase,
        )

        self._design_phase = DesignDocumentationPhase(
            llm=self._get_llm_backend(),
            max_iterations=self.config.max_iterations,
        )
        return self._design_phase

    @staticmethod
    def _task_to_feature_context(
        task: SeedTask,
        *,
        plan_goals: list[str] | None = None,
        architectural_context: dict[str, Any] | None = None,
        prior_design_summaries: list[str] | None = None,
        calibration: dict[str, Any] | None = None,
        design_max_tokens_override: Optional[int] = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
    ) -> Any:
        """Convert a SeedTask to a FeatureContext for the design phase.

        Args:
            task: The seed task.
            plan_goals: Project-level goals for benefit-driven framing.
            architectural_context: Shared context from manifest + cross-feature analysis.
            prior_design_summaries: Summaries of earlier design docs for cross-task context.
            calibration: Per-task calibration dict (depth_tier, sections, max_output_tokens).
            design_max_tokens_override: Override max_output_tokens for all design tasks
                (from HandlerConfig.design_max_tokens). Takes precedence over calibration.
            parameter_sources: Per-artifact-type parameter origin mapping from onboarding.
            semantic_conventions: Metric/label naming conventions from onboarding.
        """
        from startd8.contractors.artisan_phases.design_documentation import (
            FeatureContext,
        )

        additional_context: dict[str, Any] = {}
        if task.domain != "unknown":
            additional_context["domain"] = task.domain
        if task.domain_reasoning:
            additional_context["domain_reasoning"] = task.domain_reasoning
        if task.available_siblings:
            additional_context["siblings"] = ", ".join(task.available_siblings)
        if task.feature_id:
            additional_context["feature_id"] = task.feature_id

        # Benefit-driven framing: inject project goals
        if plan_goals:
            additional_context["project_goals"] = (
                "This feature supports these project goals:\n"
                + "\n".join(f"- {g}" for g in plan_goals[:5])
            )

        # Architectural context from manifest + cross-feature analysis
        arch = architectural_context or {}
        objectives = arch.get("objectives", [])
        if objectives:
            additional_context["objectives"] = ", ".join(
                o.get("name", str(o)) if isinstance(o, dict) else str(o)
                for o in objectives[:5]
            )
        constraints = arch.get("constraints", [])
        if constraints:
            additional_context["constraints_from_manifest"] = [
                f"[{c.get('severity', 'info')}] {c.get('rule', str(c))}"
                if isinstance(c, dict) else str(c)
                for c in constraints
            ]

        # Shared modules (only those overlapping with this task's targets)
        shared = arch.get("shared_modules", [])
        if shared and task.target_files:
            task_targets = set(task.target_files)
            overlapping = [
                m["path"] for m in shared
                if isinstance(m, dict) and m.get("path") in task_targets
            ]
            if overlapping:
                additional_context["shared_modules"] = (
                    f"These files are also targeted by other features — "
                    f"coordinate interfaces: {', '.join(overlapping)}"
                )

        domain_concepts = arch.get("domain_concepts", [])
        if domain_concepts:
            additional_context["domain_concepts"] = ", ".join(domain_concepts[:10])

        import_conventions = arch.get("import_conventions", [])
        if import_conventions:
            additional_context["import_conventions"] = ", ".join(import_conventions[:5])

        # Cross-task context from prior designs
        if prior_design_summaries:
            additional_context["prior_designs"] = (
                "Previously designed tasks:\n"
                + "\n".join(f"- {s}" for s in prior_design_summaries[-5:])
            )

        # Calibration: depth guidance
        cal = calibration or {}
        depth_guidance = cal.get("depth_guidance")
        if depth_guidance:
            additional_context["depth_guidance"] = depth_guidance

        # Task-specific design doc content hints (supplement structural sections)
        if task.design_doc_sections:
            additional_context["design_doc_sections"] = task.design_doc_sections

        # Fix 2c: inject parameter_sources relevant to this task's artifact types
        all_param_sources = parameter_sources or {}
        if all_param_sources and task.artifact_types_addressed:
            task_param_sources = {
                atype: all_param_sources[atype]
                for atype in task.artifact_types_addressed
                if atype in all_param_sources
            }
            if task_param_sources:
                param_lines = ["Parameter sources (from ContextCore manifest):"]
                for atype, sources in task_param_sources.items():
                    param_lines.append(f"  {atype}: {json.dumps(sources, indent=2)}")
                additional_context["parameter_sources"] = "\n".join(param_lines)

        # Fix 3c: inject semantic_conventions
        sem_conv = semantic_conventions or {}
        if sem_conv:
            conv_lines = ["Semantic conventions:"]
            for key, val in sem_conv.items():
                conv_lines.append(f"  {key}: {val}")
            additional_context["semantic_conventions"] = "\n".join(conv_lines)

        sections = cal.get("sections")
        max_output_tokens = (
            design_max_tokens_override
            if design_max_tokens_override is not None
            else cal.get("max_output_tokens")
        )

        return FeatureContext(
            feature_name=task.title,
            description=task.description,
            target_file=task.target_files[0] if task.target_files else "",
            constraints=list(task.prompt_constraints),
            additional_context=additional_context,
            sections=sections,
            max_output_tokens=max_output_tokens,
            depth_guidance=depth_guidance,
        )

    @staticmethod
    def _run_design_async(
        design_phase: Any,
        feature_context: Any,
        timeout: float | None = None,
    ) -> Any:
        """Run DesignDocumentationPhase.run() in a dedicated thread-owned event loop.

        Uses the same pattern as ImplementPhaseHandler._run_development_phase()
        to avoid nested event-loop errors.

        Args:
            design_phase: The DesignDocumentationPhase instance.
            feature_context: The FeatureContext for the design task.
            timeout: Maximum seconds to wait for the thread. ``None``
                means wait indefinitely.
        """
        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result_box["result"] = loop.run_until_complete(
                    design_phase.run(feature_context)
                )
            except BaseException as exc:
                error_box["error"] = exc
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            logger.error(
                "DesignDocumentationPhase did not complete within %.0fs — "
                "abandoning background thread (daemon=True)",
                timeout,
            )
            raise TimeoutError(
                f"DesignDocumentationPhase.run() did not complete within {timeout}s"
            )

        if "error" in error_box:
            raise error_box["error"]
        return result_box["result"]

    @staticmethod
    def _serialize_result(result: Any) -> dict[str, Any]:
        """Serialize a DesignDocumentResult to a checkpoint-safe dict."""
        return {
            "design_document": result.design_document.raw_text,
            "feature_name": result.design_document.feature_name,
            "agreed": result.agreed,
            "iterations": result.iterations,
            "completed_at": result.completed_at.isoformat(),
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

        logger.info("DESIGN phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        design_results: dict[str, dict[str, Any]] = {}
        total_cost = 0.0
        tasks_designed = 0
        tasks_agreed = 0
        tasks_failed = 0
        tasks_adopted = 0

        # Prior design_results injected via --adopt-prior (or checkpoint resume)
        prior_design_results: dict[str, dict[str, Any]] = context.get("design_results", {})

        # Extract shared context for cross-task design quality
        plan_goals = context.get("plan_goals", [])
        arch_context = context.get("architectural_context", {})
        calibration_map = context.get("design_calibration", {})
        prior_summaries: list[str] = []
        previous_task_started_mono: Optional[float] = None

        for idx, task in enumerate(tasks, start=1):
            previous_task_started_mono = _log_task_timing(
                "DESIGN",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
            # Skip tasks with env failures
            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            if env_fails:
                design_results[task.task_id] = {
                    "status": "env_blocked",
                    "environment_issues": env_fails,
                }
                continue

            # ----------------------------------------------------------
            # Adopt prior design result (from dress-rehearsal / prior run)
            # ----------------------------------------------------------
            prior = prior_design_results.get(task.task_id, {})
            if (
                prior.get("status") == "designed"
                and prior.get("design_document")
            ):
                design_results[task.task_id] = {
                    **prior,
                    "status": "adopted",
                    "adopted_from": "prior_design_results",
                }
                tasks_adopted += 1
                if prior.get("agreed"):
                    tasks_agreed += 1

                # Feed into cross-task progressive context
                doc_text = prior["design_document"]
                first_line = doc_text[:300].split("\n")[0]
                prior_summaries.append(
                    f"{task.task_id} ({task.title}): {first_line}"
                )

                # Copy design doc to current output_dir if configured
                if self.output_dir:
                    out_path = Path(self.output_dir) / f"{task.task_id}-design.md"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(doc_text, encoding="utf-8")
                    design_results[task.task_id]["output_file"] = str(out_path)

                logger.info(
                    "DESIGN: adopted prior result for %s (agreed=%s, cost=$%.4f)",
                    task.task_id, prior.get("agreed"), prior.get("cost", 0.0),
                )
                continue

            if dry_run:
                design_results[task.task_id] = {
                    "status": "dry_run_skipped",
                    "title": task.title,
                    "target_file": task.target_files[0] if task.target_files else "",
                    "constraints_count": len(task.prompt_constraints),
                    "domain": task.domain,
                }
                continue

            # Real-mode: run design documentation phase per task
            task_calibration = calibration_map.get(task.task_id, {})
            feature_context = self._task_to_feature_context(
                task,
                plan_goals=plan_goals,
                architectural_context=arch_context,
                prior_design_summaries=prior_summaries,
                calibration=task_calibration,
                design_max_tokens_override=self.config.design_max_tokens,
                parameter_sources=context.get("parameter_sources", {}),
                semantic_conventions=context.get("semantic_conventions", {}),
            )

            # Snapshot cost before this task
            backend = self._get_llm_backend()
            cost_before = backend.total_cost_usd

            try:
                design_phase = self._get_design_phase()
                result = self._run_design_async(
                    design_phase, feature_context,
                    timeout=self.config.development_timeout_seconds,
                )
                task_cost = backend.total_cost_usd - cost_before
                total_cost += task_cost

                serialized = self._serialize_result(result)
                serialized["status"] = "designed"
                serialized["cost"] = task_cost
                design_results[task.task_id] = serialized

                tasks_designed += 1
                if result.agreed:
                    tasks_agreed += 1

                # Accumulate cross-task summary for progressive context
                doc_text = result.design_document.raw_text
                first_line = doc_text[:300].split("\n")[0]
                summary = f"{task.task_id} ({task.title}): {first_line}"
                prior_summaries.append(summary)

                # Write design doc to output_dir if configured
                if self.output_dir:
                    out_path = Path(self.output_dir) / f"{task.task_id}-design.md"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(
                        result.design_document.raw_text, encoding="utf-8"
                    )
                    design_results[task.task_id]["output_file"] = str(out_path)
                    logger.info("Wrote design doc: %s", out_path)

            except Exception as exc:
                task_cost = backend.total_cost_usd - cost_before
                total_cost += task_cost
                tasks_failed += 1
                logger.warning(
                    "DESIGN: failed for task %s: %s", task.task_id, exc
                )
                design_results[task.task_id] = {
                    "status": "design_failed",
                    "error": str(exc),
                    "cost": task_cost,
                }

        context["design_results"] = design_results

        # Context contract: validate DESIGN output model
        DesignPhaseOutput(design_results=context["design_results"])

        env_blocked = sum(
            1 for r in design_results.values()
            if r.get("status") == "env_blocked"
        )
        output: dict[str, Any] = {
            "tasks_designed": tasks_designed,
            "tasks_adopted": tasks_adopted,
            "tasks_agreed": tasks_agreed,
            "tasks_failed": tasks_failed,
            "tasks_skipped": len(tasks) - tasks_designed - tasks_adopted - tasks_failed - env_blocked,
            "total_cost": total_cost,
        }
        if self.output_dir:
            output["output_dir"] = self.output_dir

        duration = time.monotonic() - start
        logger.info(
            "DESIGN phase complete: %d designed, %d adopted, %d agreed, %d failed, $%.4f cost (%.2fs)",
            tasks_designed, tasks_adopted, tasks_agreed, tasks_failed, total_cost, duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}


class ImplementPhaseHandler(AbstractPhaseHandler):
    """IMPLEMENT phase: Generate code per task via DevelopmentPhase engine.

    In dry-run mode: reports what would be implemented per task (unchanged).
    In real mode: delegates to :class:`DevelopmentPhase` with a
    :class:`LeadContractorChunkExecutor`, gaining parallelism, state
    persistence, crash recovery, and retry with error-informed feedback.

    Bridges the sync ``handler.execute()`` call from
    :class:`ArtisanContractorWorkflow` to the async ``DevelopmentPhase.run()``
    via ``asyncio.run()``.

    Data flow:
        1. ``SeedTask`` list → ``DevelopmentChunk`` list (``_tasks_to_chunks``)
        2. Build ``DevelopmentPlan`` → ``DevelopmentPhase.run()``
        3. ``DevelopmentResult`` → output dict + ``context["generation_results"]``
           (``_map_development_result``)
    """

    supports_feature_serial: bool = True

    def __init__(
        self,
        handler_config: Optional[HandlerConfig] = None,
        code_generator: Optional[CodeGenerator] = None,
        enriched_seed_path: Optional[Path] = None,
        project_root: Optional[Path] = None,
    ) -> None:
        self.config = handler_config or HandlerConfig()
        self._code_generator = code_generator
        self._enriched_seed_path = enriched_seed_path
        self._project_root = project_root

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_environment(self, task: SeedTask) -> list[dict[str, Any]]:
        """Check environment readiness for a task.

        Returns list of environment issues (fail/warn checks).
        """
        return [
            c for c in task.environment_checks
            if c.get("status") in ("fail", "warn")
        ]

    @staticmethod
    def _validate_multi_file_tasks(tasks: list[SeedTask]) -> None:
        """Pre-IMPLEMENT validation: warn about risky multi-file tasks.

        Logs structured warnings for tasks that are likely to encounter
        multi-file split failures so operators can monitor and intervene
        early. This is a defense-in-depth layer — it doesn't block
        execution but makes risk visible.

        Checks:
        1. Multi-file tasks (>1 target) — higher split failure risk.
        2. Multi-file tasks with ``__init__.py`` — often confuses LLMs.
        3. Tasks whose prompt_constraints mention "shared module" — known
           shared files that the LLM may skip.
        4. Cross-task file overlap — files targeted by multiple tasks.
        """
        multi_file_tasks = [t for t in tasks if len(t.target_files) > 1]
        if not multi_file_tasks:
            return

        # Only build the file→tasks index when there are multi-file tasks
        # to check (avoids iterating all tasks when none are multi-file).
        file_to_tasks: dict[str, list[str]] = {}
        for task in tasks:
            for tf in task.target_files:
                file_to_tasks.setdefault(tf, []).append(task.task_id)

        logger.info(
            "IMPLEMENT pre-validation: %d of %d tasks are multi-file",
            len(multi_file_tasks),
            len(tasks),
        )

        for task in multi_file_tasks:
            risk_flags: list[str] = []

            # __init__.py is often omitted by LLMs
            init_files = [f for f in task.target_files if f.endswith("__init__.py")]
            if init_files:
                risk_flags.append(f"includes __init__.py ({', '.join(init_files)})")

            # Shared module hint present
            shared_hints = [
                c for c in task.prompt_constraints
                if "shared module" in c.lower() or "shared file" in c.lower()
            ]
            if shared_hints:
                risk_flags.append("contains shared-module constraint")

            # Files targeted by other tasks too
            overlapping = [
                f for f in task.target_files
                if len(file_to_tasks.get(f, [])) > 1
            ]
            if overlapping:
                risk_flags.append(
                    f"overlapping files: {', '.join(overlapping)}"
                )

            # File scope from seed — contract-level classification
            if task.file_scope:
                non_primary = {
                    f: s for f, s in task.file_scope.items()
                    if s != "primary"
                }
                if non_primary:
                    risk_flags.append(
                        f"file_scope: {non_primary} (Gate 2c will pre-stub)"
                    )

            if risk_flags:
                logger.warning(
                    "IMPLEMENT pre-validation: task %s (%d files) has elevated "
                    "multi-file split risk — %s. Stub generation will activate "
                    "if LLM omits files.",
                    task.task_id,
                    len(task.target_files),
                    "; ".join(risk_flags),
                )
            else:
                logger.info(
                    "IMPLEMENT pre-validation: task %s has %d target files",
                    task.task_id,
                    len(task.target_files),
                )

    @staticmethod
    def _validate_generation_completeness(
        tasks: list[SeedTask],
        generation_results: dict[str, "GenerationResult"],
        project_root: Path,
        downstream_map: dict[str, list[str]] | None = None,
    ) -> list[dict[str, Any]]:
        """Gate 3: post-IMPLEMENT validation of multi-file split completeness.

        Per the Export Pipeline Analysis Guide's defense-in-depth Principle 1
        (validate at every boundary): verifies that multi-file tasks actually
        produced all their target files on disk.

        Returns a list of validation findings (one per multi-file task that
        has issues).  Empty list means all multi-file tasks are complete.

        This is the last gate before output is accepted — it catches cases
        where Gate 2 warnings were present but the drafter still omitted
        files despite all mitigation layers.

        Enhancement (defense-in-depth): ``downstream_map`` from Gate 2c
        allows distinguishing **downstream stubs** (expected, pre-created)
        from **generation failure stubs** (unexpected, needs attention).
        """
        findings: list[dict[str, Any]] = []
        downstream_map = downstream_map or {}

        for task in tasks:
            if len(task.target_files) <= 1:
                continue

            gr = generation_results.get(task.task_id)
            if gr is None:
                continue  # Task wasn't processed (dep-blocked, skipped, etc.)

            task_downstream = set(downstream_map.get(task.task_id, []))

            # Check which target files actually exist on disk
            generated_paths = {str(p) for p in (gr.generated_files or [])}
            missing_on_disk: list[str] = []
            stubbed: list[str] = []
            downstream_stubbed: list[str] = []

            for tf in task.target_files:
                full_path = project_root / tf
                if not full_path.exists():
                    if tf in task_downstream:
                        # Downstream file not on disk — unexpected since
                        # Gate 2c should have pre-created it.
                        missing_on_disk.append(tf)
                    else:
                        missing_on_disk.append(tf)
                elif full_path.exists():
                    # Check for stub sentinel (auto-generated placeholder)
                    try:
                        content = full_path.read_text(encoding="utf-8")
                        is_stub = (
                            "STUB_PLACEHOLDER" in content
                            or "# AUTO-STUB" in content
                            or "# STARTD8_AUTO_STUB" in content
                            or "downstream — will be implemented by later tasks" in content
                        )
                        if is_stub:
                            if tf in task_downstream:
                                downstream_stubbed.append(tf)
                            else:
                                stubbed.append(tf)
                    except Exception:
                        pass

            # Only report as issues if there are true failures (not downstream)
            has_real_issues = bool(missing_on_disk or stubbed)

            if has_real_issues or downstream_stubbed:
                finding: dict[str, Any] = {
                    "task_id": task.task_id,
                    "target_file_count": len(task.target_files),
                    "target_files": task.target_files,
                    "missing_on_disk": missing_on_disk,
                    "stubbed_files": stubbed,
                    "downstream_stubbed": downstream_stubbed,
                    "generation_success": gr.success,
                    "has_real_issues": has_real_issues,
                }
                findings.append(finding)

                if has_real_issues:
                    level = "ERROR" if missing_on_disk else "WARN"
                    logger.warning(
                        "Gate 3 [%s]: task %s multi-file split incomplete — "
                        "%d/%d files verified. Missing: %s. Stubbed: %s",
                        level,
                        task.task_id,
                        len(task.target_files) - len(missing_on_disk) - len(stubbed),
                        len(task.target_files),
                        missing_on_disk or "(none)",
                        stubbed or "(none)",
                    )
                if downstream_stubbed:
                    logger.info(
                        "Gate 3 [OK/downstream]: task %s — %d file(s) are "
                        "expected downstream stubs (pre-created by Gate 2c): %s",
                        task.task_id,
                        len(downstream_stubbed),
                        downstream_stubbed,
                    )
            else:
                logger.info(
                    "Gate 3 [OK]: task %s — all %d target files verified on disk",
                    task.task_id,
                    len(task.target_files),
                )

        return findings

    @staticmethod
    def _ensure_test_scaffolding_for_artifact_tasks(
        tasks: list[SeedTask],
        project_root: Path,
    ) -> None:
        """Ensure test scaffolding exists for artifact generator tasks (Item 12).

        For tasks with artifact_types_addressed, derive the expected test path
        from the first target file and create minimal scaffolding if missing.
        Uses convention: target path/to/foo.py or path/to/foo.yaml → tests/test_foo.py.
        """
        for task in tasks:
            if not task.artifact_types_addressed or not task.target_files:
                continue

            tests_dir = project_root / "tests"
            target = Path(task.target_files[0])
            stem = target.stem.replace("-", "_")
            if not stem:
                continue
            test_path = tests_dir / f"test_{stem}.py"

            if test_path.exists():
                continue

            tests_dir.mkdir(parents=True, exist_ok=True)

            # Minimal scaffolding: test class skeleton
            artifact_label = "_".join(
                t.replace("-", "_") for t in task.artifact_types_addressed[:2]
            )
            class_name = "".join(
                p.capitalize() for p in stem.split("_") if p
            ) or "Artifact"
            content = f'''"""Tests for {artifact_label} — scaffold-first (Item 12)."""

import pytest


class Test{class_name}:
    """Test scaffold for {artifact_label} — implement before generation."""
    pass
'''
            test_path.write_text(content, encoding="utf-8")
            logger.info(
                "IMPLEMENT: scaffolded test file for artifact task %s: %s",
                task.task_id,
                test_path.relative_to(project_root),
            )

    @staticmethod
    def _reconcile_design_downstream(
        tasks: list[SeedTask],
        design_results: dict[str, Any],
        project_root: Path,
    ) -> dict[str, list[str]]:
        """Gate 2c: Reconcile design doc downstream designations with target_files.

        Uses a two-layer detection strategy (defense-in-depth Principle 1):

        **Layer 1 — Contract-level (seed ``_file_scope``):**
        Plan ingestion already classified files as "primary", "shared", or
        "stub" using ContextCore export's ``file_ownership`` and cross-feature
        analysis.  When ``_file_scope`` is present, we trust it as the
        authoritative source — it represents the contract answer to
        "Is the contract complete?" (Principle 6, Question 1).

        **Layer 2 — Runtime fallback (design doc parsing):**
        When ``_file_scope`` is absent (older seeds, manual seeds), falls
        back to scanning the design doc for downstream signals (e.g.
        "F-002+", "implemented by later tasks").

        For downstream/stub files:
        1. **Pre-creates a stub** on disk so downstream tasks have a valid
           import target immediately.
        2. **Returns a mapping** task_id → [downstream_files] so callers can
           shrink the drafter's target list and annotate metadata.

        Args:
            tasks: Parsed seed tasks from the PLAN phase.
            design_results: Per-task design results from the DESIGN phase.
            project_root: Root of the project for writing pre-stubs.

        Returns:
            Dict mapping task_id → list of downstream file paths that were
            pre-stubbed. Empty dict if no downstream files found.
        """
        from startd8.contractors.generators.lead_contractor import (
            _detect_downstream_files,
        )
        from startd8.utils.code_extraction import STUB_SENTINEL

        downstream_map: dict[str, list[str]] = {}

        for task in tasks:
            if len(task.target_files) < 2:
                continue

            downstream: list[str] = []

            # ── Layer 1: contract-level file scope from seed ──────────
            # This is the authoritative source when available.
            if task.file_scope:
                downstream = [
                    f for f in task.target_files
                    if task.file_scope.get(f) in ("stub", "shared")
                ]
                if downstream:
                    logger.info(
                        "Gate 2c [contract]: task %s has %d non-primary files "
                        "from seed _file_scope: %s",
                        task.task_id, len(downstream),
                        {f: task.file_scope[f] for f in downstream},
                    )

            # ── Layer 2: runtime fallback — parse design doc ──────────
            # Only fall through when file_scope is absent (older/manual seeds).
            # If file_scope exists, it's authoritative even if all files are
            # "primary" — that means the contract says to implement everything.
            if not downstream and not task.file_scope:
                task_design = design_results.get(task.task_id, {})
                if task_design.get("status") in ("designed", "adopted"):
                    design_doc = task_design.get("design_document", "")
                    if design_doc:
                        downstream = _detect_downstream_files(
                            task.target_files, design_doc,
                        )
                        if downstream:
                            logger.info(
                                "Gate 2c [runtime]: task %s has %d downstream "
                                "files from design doc parsing: %s",
                                task.task_id, len(downstream), downstream,
                            )

            if not downstream:
                continue

            # Safety: never remove ALL files — at least one must remain for
            # the drafter to implement.
            if len(downstream) >= len(task.target_files):
                logger.warning(
                    "Gate 2c: all %d target files for %s flagged as downstream "
                    "— keeping all to avoid empty task. Files: %s",
                    len(task.target_files), task.task_id, downstream,
                )
                continue

            # Pre-create stubs on disk for downstream files
            for fpath in downstream:
                abs_path = project_root / fpath
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                if not abs_path.exists():
                    # Generate a meaningful stub based on file type
                    module_name = abs_path.stem
                    if module_name == "__init__":
                        stub_content = (
                            f'"""{abs_path.parent.name} package."""\n'
                            f"{STUB_SENTINEL}  # downstream — will be implemented by later tasks\n"
                        )
                    else:
                        stub_content = (
                            f'"""{module_name} module — stub for downstream implementation."""\n'
                            f"{STUB_SENTINEL}  # downstream — will be implemented by later tasks\n"
                        )
                    abs_path.write_text(stub_content, encoding="utf-8")
                    logger.info(
                        "Gate 2c: pre-stubbed downstream file %s for task %s",
                        fpath, task.task_id,
                    )

            downstream_map[task.task_id] = downstream
            logger.info(
                "Gate 2c: task %s has %d downstream files (pre-stubbed): %s. "
                "These will be excluded from drafter targets.",
                task.task_id, len(downstream), downstream,
            )

        return downstream_map

    @staticmethod
    def _tasks_to_chunks(
        tasks: list[SeedTask],
        max_retries: int = 2,
        design_results: dict[str, Any] | None = None,
        calibration_map: dict[str, dict[str, Any]] | None = None,
        downstream_map: dict[str, list[str]] | None = None,
        parameter_sources: dict[str, Any] | None = None,
        semantic_conventions: dict[str, Any] | None = None,
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        """Convert SeedTasks to DevelopmentChunks, pre-filtering env-blocked.

        Args:
            tasks: Parsed seed tasks from the PLAN phase.
            max_retries: Max retry count for each chunk.
            design_results: Per-task design results from the DESIGN phase.
                Maps task_id → dict with 'design_document' key containing the
                raw design document text to inject into implementation prompts.
            calibration_map: Per-task calibration (design_calibration) with
                optional implement_max_output_tokens for per-task token caps.
            downstream_map: Gate 2c output — maps task_id → list of files
                that were pre-stubbed as downstream.  These are excluded
                from the drafter's ``file_targets`` and annotated in
                chunk metadata so retry/review layers can distinguish
                expected stubs from generation failures.

        Returns:
            Tuple of (chunks, skipped_reports). ``skipped_reports`` contains
            task report dicts for env-blocked tasks.
        """
        from startd8.contractors.artisan_phases.development import DevelopmentChunk

        chunks: list[DevelopmentChunk] = []
        skipped: list[dict[str, Any]] = []
        design_results = design_results or {}
        downstream_map = downstream_map or {}
        active_task_ids = {t.task_id for t in tasks}

        env_blocked_ids: set[str] = set()
        for task in tasks:
            env_fails = [
                c for c in task.environment_checks
                if c.get("status") == "fail"
            ]
            if env_fails:
                env_blocked_ids.add(task.task_id)
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "env_blocked",
                    "environment_issues": [
                        c for c in task.environment_checks
                        if c.get("status") in ("fail", "warn")
                    ],
                })

        for task in tasks:
            if task.task_id in env_blocked_ids:
                continue

            blocked_deps = [d for d in task.depends_on if d in env_blocked_ids]
            if blocked_deps:
                skipped.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "status": "dep_blocked_env",
                    "blocked_dependencies": blocked_deps,
                    "depends_on": task.depends_on,
                })
                continue

            # Extract design document from DESIGN phase results (if available).
            # "adopted" status indicates reuse from a prior run (dress-rehearsal).
            design_doc_text = None
            task_design = design_results.get(task.task_id, {})
            if task_design.get("status") in ("designed", "adopted"):
                design_doc_text = task_design.get("design_document")

            # Per-task implement token cap from design_calibration
            task_cal = (calibration_map or {}).get(task.task_id, {})
            max_output_tokens = task_cal.get("implement_max_output_tokens")

            # Initialize env_checks early so LOC mismatch and multi-file
            # checks can both append to it.
            env_checks = list(task.environment_checks)

            # ── Fix 3: LOC estimation mismatch detection ─────────────────
            # If the design doc exists, estimate its implied LOC from code
            # blocks and compare against the seed's estimated_loc.  A large
            # mismatch (>3x) means the depth tier was likely too low, which
            # causes truncation, incomplete output, and wasted retries.
            if design_doc_text and task.estimated_loc:
                _code_line_count = sum(
                    1 for line in design_doc_text.split("\n")
                    if line.strip()
                    and not line.strip().startswith("#")
                    and not line.strip().startswith("```")
                )
                # Rough heuristic: design doc code blocks ≈ 60% of total
                # lines are actual code.  Compare against seed estimate.
                _implied_loc = int(_code_line_count * 0.6)
                if _implied_loc > task.estimated_loc * 3:
                    env_checks.append({
                        "check_name": "loc_estimation_mismatch",
                        "status": "warn",
                        "message": (
                            f"Design doc implies ~{_implied_loc} LOC but seed "
                            f"estimates {task.estimated_loc} LOC (>{3}x mismatch)"
                        ),
                        "detail": (
                            f"The design document for {task.task_id} contains "
                            f"~{_code_line_count} non-empty lines, implying "
                            f"~{_implied_loc} LOC of implementation. The seed "
                            f"estimated {task.estimated_loc} LOC, which placed "
                            f"this task in the '{task_cal.get('depth_tier', 'standard')}' "
                            f"depth tier. Token budget will be auto-recalibrated "
                            f"based on design-implied LOC."
                        ),
                    })
                    logger.warning(
                        "LOC mismatch for task %s: design implies ~%d LOC, "
                        "seed estimates %d LOC (depth_tier=%s). "
                        "Token budget will be auto-recalibrated.",
                        task.task_id,
                        _implied_loc,
                        task.estimated_loc,
                        task_cal.get("depth_tier", "standard"),
                    )

                    # ── Defense-in-depth: auto-recalibrate token budget ────
                    # The design phase expanded scope beyond the seed
                    # estimate.  Bump implement tokens to prevent
                    # truncation rather than just warning about it.
                    # Tiers: <=150 LOC → 32768, <=400 LOC → 49152, >400 → 64000
                    # Cap at 64000: lowest common max across lead (opus)
                    # and drafter (haiku) models in the pipeline.
                    if _implied_loc <= 150:
                        _recal_tokens = 32768
                    elif _implied_loc <= 400:
                        _recal_tokens = 49152
                    else:
                        _recal_tokens = 64000
                    if max_output_tokens is None or _recal_tokens > max_output_tokens:
                        logger.info(
                            "Auto-recalibrating implement tokens for %s: "
                            "%s → %d (design implies ~%d LOC)",
                            task.task_id,
                            max_output_tokens,
                            _recal_tokens,
                            _implied_loc,
                        )
                        max_output_tokens = _recal_tokens

            # ── Multi-file preflight checks ──────────────────────────────
            # Surface risk signals as environment checks so they appear in
            # preflight reports.  These are task-level (not per-file) checks
            # derived from real-world failure patterns (PI-001 post-mortem).
            if len(task.target_files) > 1:
                env_checks.append({
                    "check_name": "multi_file_split_risk",
                    "status": "warn",
                    "message": (
                        f"Task targets {len(task.target_files)} files — "
                        f"LLM may omit some code blocks"
                    ),
                    "detail": (
                        f"Target files: {', '.join(task.target_files)}. "
                        f"Multi-file tasks have higher risk of incomplete output. "
                        f"Defense layers: prompt checklist, __init__.py constraint, "
                        f"content-heuristic extraction, retry with role hints, "
                        f"stub fallback."
                    ),
                })
                init_files = [
                    f for f in task.target_files if f.endswith("__init__.py")
                ]
                if init_files:
                    env_checks.append({
                        "check_name": "init_py_in_multi_file",
                        "status": "warn",
                        "message": (
                            f"__init__.py among {len(task.target_files)} targets — "
                            f"commonly skipped by LLM drafters"
                        ),
                        "detail": (
                            f"Files: {', '.join(init_files)}. "
                            f"Models treat __init__.py as optional because it's "
                            f"'just imports'. Dedicated constraints and extraction "
                            f"heuristics are active."
                        ),
                    })
                # High-LOC multi-file: truncation risk compounds with split risk
                if task.estimated_loc and task.estimated_loc > 200:
                    env_checks.append({
                        "check_name": "multi_file_high_loc",
                        "status": "warn",
                        "message": (
                            f"Multi-file task with {task.estimated_loc} estimated LOC — "
                            f"truncation may compound split failure"
                        ),
                        "detail": (
                            "Consider splitting into single-file tasks, or increase "
                            "implement_max_output_tokens in design_calibration."
                        ),
                    })

            # Multi-file format constraint: ensure LLM produces distinct blocks per file
            prompt_constraints = list(task.prompt_constraints)
            if len(task.target_files) > 1:
                file_list = ", ".join(task.target_files)
                prompt_constraints.append(
                    f"MULTI-FILE OUTPUT REQUIRED — you MUST produce a SEPARATE fenced "
                    f"code block for EACH of these {len(task.target_files)} target files: "
                    f"{file_list}. "
                    f"First line of each block MUST be a comment with the full path "
                    f"(e.g. # src/package/__init__.py). "
                    f"If a file is a shared module implemented by downstream tasks, "
                    f"produce a minimal stub (imports, docstring, empty registrations). "
                    f"Every target file MUST have its own code block — omitting any "
                    f"file will cause the build to fail."
                )
                # Layer 3 (defense-in-depth): dedicated __init__.py constraint.
                # Models commonly skip __init__.py because it's "just imports".
                # This makes the requirement explicit and impossible to miss.
                init_files = [f for f in task.target_files if f.endswith("__init__.py")]
                if init_files:
                    init_list = ", ".join(init_files)
                    prompt_constraints.append(
                        f"PACKAGE __init__.py REQUIRED — {init_list} MUST have "
                        f"its own separate code block. Even a minimal file with "
                        f"imports and __all__ is required. The build will FAIL "
                        f"if any __init__.py is missing its own block."
                    )

                # ── Downstream file detection (Fix 2) ────────────────────
                # If the design doc says a file is for downstream tasks,
                # tell the drafter explicitly to produce a minimal stub for
                # it.  This prevents the drafter from omitting it entirely
                # (thinking "that's someone else's job") and avoids the
                # expensive retry that won't change its mind.
                from startd8.contractors.generators.lead_contractor import (
                    _detect_downstream_files,
                )
                downstream = _detect_downstream_files(
                    task.target_files, design_doc_text or "",
                )
                if downstream:
                    ds_list = ", ".join(downstream)
                    prompt_constraints.append(
                        f"DOWNSTREAM FILE STUBS — the following files are marked "
                        f"as shared/downstream in the design doc: {ds_list}. "
                        f"You MUST still produce a code block for each one, but "
                        f"it can be a MINIMAL stub: module docstring, imports, "
                        f"empty __all__, and placeholder functions/classes. "
                        f"A 5-line stub is acceptable — omitting the file is NOT."
                    )
                    logger.info(
                        "IMPLEMENT: detected %d downstream files for task %s: %s",
                        len(downstream), task.task_id, downstream,
                    )

            # ── Gate 2c: shrink file_targets for downstream files ────────
            # If Gate 2c pre-stubbed some files, remove them from the
            # drafter's target list so it only implements files it's supposed
            # to.  Downstream files are already on disk as stubs.
            task_downstream = downstream_map.get(task.task_id, [])
            effective_targets = [
                f for f in task.target_files
                if f not in task_downstream
            ] if task_downstream else task.target_files

            # Strip dependencies on tasks not in this run (already completed
            # or filtered out by --task-filter).  The plan validator rejects
            # references to non-existent chunks.
            in_scope_deps = [d for d in task.depends_on if d in active_task_ids]

            chunks.append(DevelopmentChunk(
                chunk_id=task.task_id,
                description=task.description,
                dependencies=in_scope_deps,
                file_targets=effective_targets,
                implementation_prompt=task.description,
                test_commands=[],  # Post-gen validation via DomainChecklist
                max_retries=max_retries,
                metadata={
                    "feature_id": task.feature_id,
                    "domain": task.domain,
                    "estimated_loc": task.estimated_loc,
                    "prompt_constraints": prompt_constraints,
                    "environment_checks": env_checks,
                    "post_generation_validators": task.post_generation_validators,
                    "title": task.title,
                    "design_document": design_doc_text,
                    "max_output_tokens": max_output_tokens,
                    "artifact_types_addressed": task.artifact_types_addressed,
                    "downstream_files": task_downstream,
                    "original_target_files": task.target_files if task_downstream else None,
                    # Fix 2d: parameter_sources filtered by task's artifact types
                    "parameter_sources": (
                        (parameter_sources or {}).get(
                            task.artifact_types_addressed[0], {}
                        ) if task.artifact_types_addressed else {}
                    ),
                    # Fix 3c: semantic_conventions for code generation
                    "semantic_conventions": semantic_conventions or {},
                },
            ))

        return chunks, skipped

    def _map_development_result(
        self,
        dev_result: Any,  # DevelopmentResult
        chunks: list[Any],  # list[DevelopmentChunk]
        tasks: list[SeedTask],
        skipped_reports: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, GenerationResult], float]:
        """Map DevelopmentResult back to the output format downstream expects.

        Reconstructs ``generation_results`` (dict[str, GenerationResult])
        from chunk metadata where ``LeadContractorChunkExecutor`` stored them.

        Args:
            dev_result: The DevelopmentResult from DevelopmentPhase.run().
            chunks: The DevelopmentChunk list (with metadata populated).
            tasks: Original SeedTask list for domain grouping.
            skipped_reports: Pre-filtered env-blocked task reports.

        Returns:
            Tuple of (output_dict, generation_results, total_cost).
        """
        from startd8.contractors.artisan_phases.development import ChunkStatus

        chunk_map = {c.chunk_id: c for c in chunks}
        generation_results: dict[str, GenerationResult] = {}
        task_reports: list[dict[str, Any]] = list(skipped_reports)
        total_cost = 0.0

        for chunk_id, state in dev_result.chunk_states.items():
            chunk = chunk_map.get(chunk_id)
            if chunk is None:
                continue

            meta = chunk.metadata
            gen_result = meta.get("_generation_result")

            task_report: dict[str, Any] = {
                "task_id": chunk_id,
                "feature_id": meta.get("feature_id", ""),
                "title": meta.get("title", ""),
                "domain": meta.get("domain", "unknown"),
                "target_files": chunk.file_targets,
                "estimated_loc": meta.get("estimated_loc", 0),
                "depends_on": chunk.dependencies,
                "prompt_constraints_count": len(meta.get("prompt_constraints", [])),
                "validators": meta.get("post_generation_validators", []),
            }

            if state.status == ChunkStatus.PASSED and gen_result is not None:
                task_report["status"] = "generated"
                task_report["cost"] = gen_result.cost_usd
                task_report["tokens"] = {
                    "input": gen_result.input_tokens,
                    "output": gen_result.output_tokens,
                }
                task_report["iterations"] = gen_result.iterations
                generation_results[chunk_id] = gen_result
                total_cost += gen_result.cost_usd
            elif state.status == ChunkStatus.FAILED:
                task_report["status"] = "generation_failed"
                task_report["error"] = state.last_error or "Unknown failure"
                if gen_result is not None:
                    task_report["cost"] = gen_result.cost_usd
                    task_report["tokens"] = {
                        "input": gen_result.input_tokens,
                        "output": gen_result.output_tokens,
                    }
                    task_report["iterations"] = gen_result.iterations
                    generation_results[chunk_id] = gen_result
                    total_cost += gen_result.cost_usd
            elif state.status == ChunkStatus.SKIPPED:
                task_report["status"] = "dep_blocked"
                task_report["error"] = state.last_error or "Dependency not satisfied"
            else:
                task_report["status"] = "unknown"

            task_reports.append(task_report)

        # Domain breakdown
        domain_tasks: dict[str, list[str]] = defaultdict(list)
        for task in tasks:
            domain_tasks[task.domain].append(task.task_id)

        output: dict[str, Any] = {
            "task_reports": task_reports,
            "tasks_processed": len(task_reports),
            "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
            "total_estimated_loc": sum(t.estimated_loc for t in tasks),
            "total_cost": total_cost,
            "generation_results": {
                tid: {"success": r.success, "error": r.error, "cost": r.cost_usd}
                for tid, r in generation_results.items()
            },
            "development_result_summary": dev_result.summary,
            "execution_order": dev_result.execution_order,
        }

        return output, generation_results, total_cost

    @staticmethod
    def _run_development_phase(
        dev_phase: Any,
        plan: Any,
        timeout: Optional[float] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Any:
        """Run DevelopmentPhase in a dedicated thread-owned event loop.

        Using a dedicated thread avoids nested event-loop errors when the
        caller is already inside an async runtime (e.g. notebooks, test
        harnesses, or async servers).

        Args:
            dev_phase: The DevelopmentPhase instance.
            plan: The DevelopmentPlan to execute.
            timeout: Maximum seconds to wait for the thread. ``None``
                means wait indefinitely (the orchestrator's own timeout
                still applies at the outer level).
            cancel_event: Optional :class:`threading.Event` for cooperative
                cancellation. When set after a timeout, signals the background
                thread to stop initiating new LLM calls.
        """
        result_box: dict[str, Any] = {}
        error_box: dict[str, BaseException] = {}

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result_box["result"] = loop.run_until_complete(
                    dev_phase.run(plan)
                )
            except BaseException as exc:  # pragma: no cover - propagated
                error_box["error"] = exc
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # daemon=True is intentional: if the main process exits (e.g.
        # KeyboardInterrupt or SIGTERM), we don't want this thread to keep
        # the process alive indefinitely.  For *cooperative* shutdown the
        # cancel_event is preferred — setting it tells the DevelopmentPhase
        # to stop initiating new LLM calls.  daemon=True is the fallback
        # for uncooperative exits where cancel_event alone isn't enough.
        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            if cancel_event:
                cancel_event.set()
                logger.warning(
                    "Cancel event set — signalling background DevelopmentPhase "
                    "thread to stop initiating new LLM calls",
                )
            logger.error(
                "DevelopmentPhase did not complete within %.0fs — "
                "abandoning background thread (daemon=True)",
                timeout,
            )
            raise TimeoutError(
                f"DevelopmentPhase.run() did not complete within {timeout}s"
            )

        if "error" in error_box:
            raise error_box["error"]
        return result_box["result"]

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

        # --- Pre-IMPLEMENT validation: warn about risky multi-file tasks ---
        self._validate_multi_file_tasks(tasks)

        # --- Dry-run path (unchanged) ---
        if dry_run:
            task_reports: list[dict[str, Any]] = []
            for task in tasks:
                env_checks = self._check_environment(task)
                task_report: dict[str, Any] = {
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
                if env_checks:
                    task_report["environment_issues"] = env_checks
                task_reports.append(task_report)

            domain_tasks: dict[str, list[str]] = defaultdict(list)
            for task in tasks:
                domain_tasks[task.domain].append(task.task_id)

            output = {
                "task_reports": task_reports,
                "tasks_processed": len(task_reports),
                "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
                "total_estimated_loc": sum(t.estimated_loc for t in tasks),
                "total_cost": 0.0,
                "generation_results": {},
            }
            context["implementation"] = output
            context["generation_results"] = {}

            # Context contract: validate IMPLEMENT output model (dry-run path)
            ImplementPhaseOutput(
                implementation=context["implementation"],
                generation_results=context["generation_results"],
            )

            duration = time.monotonic() - start
            logger.info(
                "IMPLEMENT phase complete (dry-run): %d tasks (%.2fs)",
                len(task_reports), duration,
            )
            return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}

        # --- Real-mode path: delegate to DevelopmentPhase ---
        from startd8.contractors.artisan_phases.development import (
            DevelopmentPhase,
            DevelopmentPlan,
            DefaultTestRunner,
            JsonFileStateStore,
            LeadContractorChunkExecutor,
        )

        # --- Resume check: load prior generation results if available ---
        # Skip resume when force_implement is set (ignore cache, always run fresh).
        results_path = project_root / ".startd8" / "state" / "generation_results.json"
        # Backward compat: check legacy location
        if not results_path.exists():
            _legacy = project_root / ".startd8_state" / "generation_results.json"
            if _legacy.exists():
                results_path = _legacy
        resumed = False
        if (
            results_path.exists()
            and not dry_run
            and not self.config.force_implement
        ):
            try:
                with open(results_path) as f:
                    saved = json.load(f)
                generation_results: dict[str, GenerationResult] = {}
                for tid, data in saved.items():
                    generation_results[tid] = GenerationResult(
                        success=data["success"],
                        generated_files=[Path(p) for p in data["generated_files"]],
                        error=data.get("error"),
                        input_tokens=data.get("input_tokens", 0),
                        output_tokens=data.get("output_tokens", 0),
                        cost_usd=data.get("cost_usd", 0.0),
                        iterations=data.get("iterations", 0),
                        model=data.get("model", "unknown"),
                    )

                # Defense Layer 2: validate cached paths match task.target_files.
                # Reject resume if any task has wrong paths (e.g. project_root/__init__.py
                # instead of project_root/src/pkg/__init__.py).
                task_map = {t.task_id: t for t in tasks}
                invalid_tasks: list[str] = []
                for tid, gr in generation_results.items():
                    task = task_map.get(tid)
                    if task is None or not gr.generated_files:
                        continue
                    expected = {
                        str((project_root / tf).resolve())
                        for tf in task.target_files
                    }
                    actual = {str(Path(p).resolve()) for p in gr.generated_files}
                    if actual != expected:
                        invalid_tasks.append(
                            f"{tid} (expected {sorted(expected)}, got {sorted(actual)})"
                        )
                if invalid_tasks:
                    logger.warning(
                        "IMPLEMENT --resume: path mismatch for %s — invalidating cache, re-running",
                        invalid_tasks,
                    )
                    generation_results = {}
                    # Do not resume — fall through to fresh IMPLEMENT
                else:
                    logger.info(
                        "IMPLEMENT --resume: loaded %d generation results from %s",
                        len(generation_results), results_path,
                    )

                # Reconstruct output dict from resumed results (only if we kept cache)
                total_cost = sum(r.cost_usd for r in generation_results.values())
                domain_tasks: dict[str, list[str]] = defaultdict(list)
                for task in tasks:
                    domain_tasks[task.domain].append(task.task_id)

                task_reports: list[dict[str, Any]] = []
                for task in tasks:
                    gr = generation_results.get(task.task_id)
                    report: dict[str, Any] = {
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
                    if gr is not None:
                        report["status"] = "generated" if gr.success else "generation_failed"
                        report["cost"] = gr.cost_usd
                        report["tokens"] = {
                            "input": gr.input_tokens,
                            "output": gr.output_tokens,
                        }
                        report["iterations"] = gr.iterations
                        if gr.error:
                            report["error"] = gr.error
                    else:
                        report["status"] = "not_in_saved_results"
                    task_reports.append(report)

                output: dict[str, Any] = {
                    "task_reports": task_reports,
                    "tasks_processed": len(task_reports),
                    "domain_breakdown": {d: len(ids) for d, ids in domain_tasks.items()},
                    "total_estimated_loc": sum(t.estimated_loc for t in tasks),
                    "total_cost": total_cost,
                    "generation_results": {
                        tid: {"success": r.success, "error": r.error, "cost": r.cost_usd}
                        for tid, r in generation_results.items()
                    },
                }
                # Only resume when we have valid cached results (path validation passed)
                resumed = len(generation_results) > 0
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning(
                    "IMPLEMENT --resume: could not load saved generation results: %s — re-running",
                    exc,
                )

        downstream_map: dict[str, list[str]] = {}

        if not resumed:
            # Item 12: scaffold test files for artifact generator tasks first
            if self.config.scaffold_test_first:
                self._ensure_test_scaffolding_for_artifact_tasks(
                    tasks, project_root
                )

            # Convert SeedTasks → DevelopmentChunks (with env pre-filter)
            # Inject design documents from the DESIGN phase into chunk metadata
            design_results = context.get("design_results", {})
            calibration_map = context.get("design_calibration", {})

            # Gate 2c: Reconcile design doc downstream designations.
            # Pre-stubs downstream files on disk and returns a mapping so
            # _tasks_to_chunks can exclude them from drafter targets.
            downstream_map = self._reconcile_design_downstream(
                tasks, design_results, project_root,
            )

            chunks, skipped_reports = self._tasks_to_chunks(
                tasks,
                max_retries=2,
                design_results=design_results,
                calibration_map=calibration_map,
                downstream_map=downstream_map,
                parameter_sources=context.get("parameter_sources", {}),
                semantic_conventions=context.get("semantic_conventions", {}),
            )

            if not chunks:
                logger.warning("IMPLEMENT: no eligible tasks after env pre-filter")
                output = {
                    "task_reports": skipped_reports,
                    "tasks_processed": len(skipped_reports),
                    "domain_breakdown": {},
                    "total_estimated_loc": 0,
                    "total_cost": 0.0,
                    "generation_results": {},
                }
                context["implementation"] = output
                context["generation_results"] = {}

                # Context contract: validate IMPLEMENT output model (no-chunks path)
                ImplementPhaseOutput(
                    implementation=context["implementation"],
                    generation_results=context["generation_results"],
                )

                duration = time.monotonic() - start
                return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}

            # Build executor (inject pre-configured generator if provided)
            executor = LeadContractorChunkExecutor(
                lead_agent=self.config.lead_agent,
                drafter_agent=self.config.drafter_agent,
                output_dir=project_root,
                max_iterations=self.config.max_iterations,
                pass_threshold=self.config.pass_threshold,
                max_tokens=self.config.max_tokens,
                fail_on_truncation=self.config.fail_on_truncation,
                check_truncation=self.config.check_truncation,
                strict_truncation=self.config.strict_truncation,
            )
            if self._code_generator is not None:
                # _generator is the lazy-init slot on LeadContractorChunkExecutor;
                # setting it skips _resolve_generator() and uses our instance.
                executor._generator = self._code_generator

            # Cooperative cancellation token — set on timeout to signal
            # the background thread to stop initiating new LLM calls.
            cancel_event = threading.Event()

            # Build plan
            plan = DevelopmentPlan(
                plan_id=f"artisan-implement-{int(time.time())}",
                chunks=chunks,
                config={
                    "dry_run": False,
                    "state_dir": str(project_root / ".startd8" / "state"),
                    "cancel_event": cancel_event,
                    "example_artifacts": context.get("example_artifacts", {}),
                },
            )

            # Build phase with test runner (no shell test commands — tests are
            # handled by DomainChecklist and the TEST phase handler)
            state_store = JsonFileStateStore(
                directory=str(project_root / ".startd8" / "state"),
            )
            # --- WCP-006: Wire DomainChecklist to DevelopmentPhase ---
            domain_checklist = None
            enriched_seed_path = (
                self._enriched_seed_path
                or context.get("enriched_seed_path")
            )
            if enriched_seed_path:
                try:
                    from startd8.contractors.artisan_phases.domain_checklist import DomainChecklist
                    domain_checklist = DomainChecklist(
                        project_root=project_root,
                        enriched_seed_path=Path(enriched_seed_path),
                    )
                    logger.info(
                        "IMPLEMENT: DomainChecklist configured (seed=%s)",
                        enriched_seed_path,
                    )
                except Exception as e:
                    logger.warning(
                        "IMPLEMENT: DomainChecklist init failed (non-fatal): %s", e,
                    )

            dev_phase = DevelopmentPhase(
                executor=executor,
                test_runner=DefaultTestRunner(),
                state_store=state_store,
                max_parallel=4,
                domain_checklist=domain_checklist,
            )

            # Bridge sync → async
            logger.info(
                "IMPLEMENT: delegating %d chunks to DevelopmentPhase (plan=%s)",
                len(chunks), plan.plan_id,
            )
            dev_result = self._run_development_phase(
                dev_phase, plan,
                timeout=self.config.development_timeout_seconds,
                cancel_event=cancel_event,
            )

            if dev_result is None or not hasattr(dev_result, "chunk_states"):
                raise RuntimeError(
                    "DevelopmentPhase returned an invalid result "
                    f"(type={type(dev_result).__name__}). "
                    "Expected DevelopmentResult with chunk_states attribute."
                )

            # Map results back to downstream contract
            output, generation_results, total_cost = self._map_development_result(
                dev_result, chunks, tasks, skipped_reports,
            )

            # ── Gate 3: post-IMPLEMENT multi-file split validation ────
            # Per defense-in-depth Principle 1 (validate at every
            # boundary): verify that every multi-file task actually
            # produced all its target files.  This is the last gate
            # before output is accepted.
            gate3 = self._validate_generation_completeness(
                tasks, generation_results, project_root,
                downstream_map=downstream_map,
            )
            if gate3:
                output["_gate3_validation"] = gate3

            # Persist generation_results to disk for crash recovery
            # Always write to the canonical .startd8/state/ location
            save_path = project_root / ".startd8" / "state" / "generation_results.json"
            serializable = {}
            for tid, gr in generation_results.items():
                serializable[tid] = {
                    "success": gr.success,
                    "generated_files": [str(p) for p in gr.generated_files],
                    "error": gr.error,
                    "input_tokens": gr.input_tokens,
                    "output_tokens": gr.output_tokens,
                    "cost_usd": gr.cost_usd,
                    "iterations": gr.iterations,
                    "model": gr.model,
                }
            save_path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_json(save_path, serializable, indent=2)
            logger.info(
                "IMPLEMENT: saved %d generation results to %s",
                len(generation_results), save_path,
            )

        # --- Auto-commit each feature's generated files ---
        if self.config.auto_commit and generation_results:
            self._commit_features(generation_results, tasks, project_root)

        context["implementation"] = output
        context["generation_results"] = generation_results
        # Propagate downstream_map to REVIEW phase so it can distinguish
        # expected downstream stubs from generation failures.
        if downstream_map:
            context["_downstream_map"] = downstream_map

        # Context contract: validate IMPLEMENT output model (normal path)
        ImplementPhaseOutput(
            implementation=context["implementation"],
            generation_results=context["generation_results"],
        )

        duration = time.monotonic() - start

        logger.info(
            "IMPLEMENT phase complete: %d tasks, %d passed, $%.4f cost (%.2fs)",
            len(tasks),
            sum(1 for r in generation_results.values() if r.success),
            total_cost,
            duration,
        )

        return {"output": output, "cost": total_cost, "metadata": {"duration": duration}}

    def _commit_features(
        self,
        generation_results: dict[str, GenerationResult],
        tasks: list[SeedTask],
        project_root: Path,
    ) -> None:
        """Commit each successful feature's generated files to git individually.

        Produces one commit per task, mirroring the PrimeContractor pattern.
        Failures are logged as warnings but do not abort the workflow.
        """
        task_map = {t.task_id: t for t in tasks}
        for task_id, gr in generation_results.items():
            if not gr.success or not gr.generated_files:
                continue
            task = task_map.get(task_id)
            title = task.title if task else task_id
            staged_files: list[str] = []
            for fpath in gr.generated_files:
                add_result = subprocess.run(
                    ["git", "add", str(fpath)],
                    cwd=project_root,
                    capture_output=True,
                    timeout=30,
                )
                if add_result.returncode != 0:
                    stderr = getattr(add_result, "stderr", b"")
                    if isinstance(stderr, bytes):
                        stderr = stderr.decode("utf-8", errors="replace")
                    logger.warning(
                        "git add failed for %s (task %s): %s",
                        fpath,
                        task_id,
                        stderr.strip(),
                    )
                else:
                    staged_files.append(str(fpath))
            if not staged_files:
                logger.warning(
                    "Skipping commit for %s: all git-add calls failed",
                    task_id,
                )
                continue
            msg = (
                f"feat({task_id}): {title}\n\n"
                "Generated by Artisan IMPLEMENT phase"
            )
            # Commit only the specific generated files to avoid capturing
            # unrelated staged changes from the user's working tree.
            files_to_commit = staged_files
            result = subprocess.run(
                ["git", "commit", "-m", msg, "--"] + files_to_commit,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info("Committed %s: %s", task_id, title)
            else:
                logger.warning(
                    "Commit failed for %s: %s",
                    task_id,
                    result.stderr.strip(),
                )


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

    supports_feature_serial: bool = True

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()

    # ------------------------------------------------------------------
    # Validator command mapping
    # ------------------------------------------------------------------

    def _resolve_validator_command(
        self,
        validator_name: str,
        target_files: list[str],
        project_root: Path,
    ) -> Optional[list[str]]:
        """Resolve a validator name to runnable subprocess args.

        Args:
            validator_name: Name from ``task.post_generation_validators``.
            target_files: List of file paths (relative to project_root).
            project_root: The project root directory.

        Returns:
            List of command arguments, or None if validator is unknown.
        """
        py = sys.executable  # use the running interpreter, not "python"
        file_args = [str(project_root / f) for f in target_files]

        if validator_name == "pytest":
            return [py, "-m", "pytest", *file_args, "--tb=short", "-q"]
        if validator_name == "mypy":
            return [py, "-m", "mypy", *file_args, "--ignore-missing-imports"]
        if validator_name == "ruff":
            return [py, "-m", "ruff", "check", *file_args]
        if validator_name == "ruff_format":
            return [py, "-m", "ruff", "format", "--check", *file_args]
        if validator_name == "black":
            return [py, "-m", "black", "--check", *file_args]
        if validator_name == "pylint":
            return [py, "-m", "pylint", *file_args]
        if validator_name == "syntax_check":
            return [py, "-m", "py_compile", *file_args]
        if validator_name == "import_check":
            module_name = self._file_to_module(target_files[0], project_root) if target_files else ""
            if module_name:
                return [py, "-c", f"import {module_name}"]
            return None

        # --- WCP-008: Enrichment-produced domain validators ---
        # These are AST-based validators from domain preflight rules.
        # They run as in-process checks via a wrapper script.
        enrichment_validators = {
            "relative_imports_valid",
            "deps_available",
            "no_circular_imports",
            "no_markdown_fences",
            "merge_damage",
            "no_relative_imports",
            "definition_ordering",
            "test_naming",
            "no_hardcoded_secrets",
            "no_substring_tag_matching",
        }
        if validator_name in enrichment_validators:
            # Run the validator via the preflight rules_validators module
            return [
                py, "-c",
                f"from startd8.workflows.builtin.preflight_rules.rules_validators import run_validator; "
                f"run_validator({validator_name!r}, {file_args!r})",
            ]

        logger.warning("TEST: unknown validator %r — skipping", validator_name)
        return None

    @staticmethod
    def _file_to_module(rel_path: str, project_root: Path) -> str:
        """Convert a relative file path to a Python module name.

        Strips common source prefixes (``src/``) and the ``.py`` extension,
        then validates that the resulting dotted path looks importable.

        Returns:
            Dotted module name (e.g. ``"startd8.contractors.foo"``), or
            empty string if the path cannot be converted.
        """
        # Normalize and strip .py
        p = rel_path.replace("\\", "/")
        if not p.endswith(".py"):
            return ""
        p = p[:-3]  # strip .py

        # Strip common source-tree prefixes
        for prefix in ("src/", "lib/"):
            if p.startswith(prefix):
                p = p[len(prefix):]
                break

        # Convert path separators to dots
        module = p.replace("/", ".")

        # Basic sanity: no leading/trailing dots, no double dots
        if module.startswith(".") or module.endswith(".") or ".." in module:
            return ""
        return module

    @staticmethod
    def _truncate_output(text: str, limit: int = 4000) -> str:
        """Truncate output keeping both head and tail for context.

        When *text* exceeds *limit* characters the middle is replaced with
        a marker showing how many characters were elided.  This preserves
        the first lines (often file paths / summary) **and** the last lines
        (often the actual error message) instead of discarding the head.
        """
        if len(text) <= limit:
            return text
        half = limit // 2
        return (
            text[:half]
            + f"\n\n... [{len(text) - limit} chars truncated] ...\n\n"
            + text[-half:]
        )

    def _run_validator(
        self,
        command: list[str],
        project_root: Path,
        timeout: int,
    ) -> dict[str, Any]:
        """Execute a single validator command as a subprocess.

        Args:
            command: The CLI command args to run.
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
                cwd=str(project_root),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            passed = proc.returncode == 0
            result = {
                "passed": passed,
                "returncode": proc.returncode,
                "stdout": self._truncate_output(proc.stdout) if proc.stdout else "",
                "stderr": self._truncate_output(proc.stderr) if proc.stderr else "",
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
        except (OSError, UnicodeDecodeError) as exc:
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
    ) -> dict[str, Any]:
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

        validator_results: list[dict[str, Any]] = []
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
            result["command"] = " ".join(shlex.quote(part) for part in command)
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
        generation_results: dict[str, GenerationResult] = context.get("generation_results", {})

        logger.info("TEST phase: processing %d tasks (dry_run=%s)", len(tasks), dry_run)

        test_plan: list[dict[str, Any]] = []
        validator_counts: dict[str, int] = defaultdict(int)
        total_passed = 0
        total_failed = 0
        previous_task_started_mono: Optional[float] = None

        for idx, task in enumerate(tasks, start=1):
            previous_task_started_mono = _log_task_timing(
                "TEST",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
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

        per_task: dict[str, Any] = {}
        for entry in test_plan:
            task_id = entry.get("task_id")
            if not task_id:
                continue
            if entry.get("status") == "passed":
                per_task[task_id] = {
                    "status": "passed",
                    "passed": True,
                    "validators_run": entry.get("validators_run", 0),
                }
            elif entry.get("status") == "failed":
                per_task[task_id] = {
                    "status": "failed",
                    "passed": False,
                    "validators_run": entry.get("validators_run", 0),
                    "failures": [
                        r.get("validator")
                        for r in entry.get("results", [])
                        if not r.get("passed", True)
                    ],
                }
            elif entry.get("status") == "skipped_no_generation":
                per_task[task_id] = {
                    "status": "skipped_no_generation",
                    "passed": None,
                    "validators_run": 0,
                }
            else:
                per_task[task_id] = {
                    "status": entry.get("status", "unknown"),
                    "passed": None,
                    "validators_run": entry.get("validators_run", 0),
                }

        output = {
            "test_plan": test_plan,
            "total_validators": sum(len(t.post_generation_validators) for t in tasks),
            "unique_validators": dict(validator_counts),
            "tasks_with_tests": len([t for t in test_plan if t.get("validator_count", 0) > 0 or t.get("validators_run", 0) > 0]),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "per_task": per_task,
        }

        context["test_results"] = output

        # Context contract: validate TEST output model
        ValidationPhaseOutput(test_results=context["test_results"])

        duration = time.monotonic() - start

        logger.info(
            "TEST phase complete: %d validators across %d tasks, %d passed, %d failed (%.2fs)",
            output["total_validators"], len(test_plan), total_passed, total_failed, duration,
        )

        return {"output": output, "cost": 0.0, "metadata": {"duration": duration}}


class ReviewPhaseHandler(AbstractPhaseHandler):
    """REVIEW phase: LLM-based quality review of generated implementations.

    In dry-run mode: reports review checklist (unchanged).
    In real mode: sends generated code to a review agent for
    quality scoring, then aggregates pass/fail verdicts.
    """

    supports_feature_serial: bool = True

    def __init__(self, handler_config: Optional[HandlerConfig] = None) -> None:
        self.config = handler_config or HandlerConfig()
        self._review_agent: Any = None

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
        """
        if self._review_agent is not None:
            return self._review_agent

        from startd8.utils.agent_resolution import resolve_agent_spec

        resolve_kwargs: dict[str, Any] = {
            "name": "context-seed-reviewer",
            "temperature": self.config.review_temperature,
        }
        if self.config.max_tokens is not None:
            resolve_kwargs["max_tokens"] = self.config.max_tokens

        self._review_agent = resolve_agent_spec(
            self.config.lead_agent,
            **resolve_kwargs,
        )
        return self._review_agent

    def _build_review_prompt(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
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

        test_str = json.dumps(test_results, indent=2, default=str) if test_results else "No test results available for this task"

        max_code = self.config.review_max_code_chars
        code_for_prompt = generated_code[:max_code]
        if len(generated_code) > max_code:
            code_for_prompt += f"\n\n# ... [truncated — {len(generated_code) - max_code} chars omitted] ..."

        max_test = 2000
        test_for_prompt = test_str[:max_test]
        if len(test_str) > max_test:
            test_for_prompt += f"\n... [truncated — {len(test_str) - max_test} chars omitted] ..."

        return self.REVIEW_PROMPT_TEMPLATE.format(
            task_id=task.task_id,
            title=task.title,
            domain=task.domain,
            description=task.description,
            constraints=constraints_str,
            generated_code=code_for_prompt,
            test_results=test_for_prompt,
            pass_threshold=self.config.pass_threshold,
        )

    def _parse_review_response(self, response: str) -> dict[str, Any]:
        """Parse score, verdict, and issues from the LLM review response.

        Args:
            response: Raw LLM output.

        Returns:
            Dict with ``score``, ``verdict``, ``strengths``, ``issues``, ``suggestions``.

        """
        import re

        score = 0
        verdict = "FAIL"

        # Extract score
        score_match = re.search(r"###\s*Score:\s*(\d+)", response)
        if score_match:
            score = min(100, max(0, int(score_match.group(1))))
        else:
            # Fallback: try without markdown headers
            score_fallback = re.search(r"(?:^|\n)\s*Score\s*[:=]\s*(\d+)", response, re.IGNORECASE)
            if score_fallback:
                score = min(100, max(0, int(score_fallback.group(1))))
            else:
                logger.warning(
                    "REVIEW: could not extract score from response (defaulting to 0); "
                    "first 200 chars: %s", response[:200],
                )

        # Extract verdict
        verdict_match = re.search(r"###\s*Verdict:\s*(PASS|FAIL)", response, re.IGNORECASE)
        if verdict_match:
            verdict = verdict_match.group(1).upper()
        else:
            # Fallback: try without markdown headers
            verdict_fallback = re.search(r"(?:^|\n)\s*Verdict\s*[:=]\s*(PASS|FAIL)", response, re.IGNORECASE)
            if verdict_fallback:
                verdict = verdict_fallback.group(1).upper()
            else:
                logger.warning(
                    "REVIEW: could not extract verdict from response (defaulting to FAIL)"
                )

        def extract_section(section: str) -> list[str]:
            pattern = rf"###\s*{section}\s*\n(.*?)(?=\n###\s|\Z)"
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if not match:
                return []
            items: list[str] = []
            for line in match.group(1).splitlines():
                cleaned = line.strip()
                if cleaned.startswith("- "):
                    items.append(cleaned[2:].strip())
            return items

        return {
            "score": score,
            "verdict": verdict,
            "passed": verdict == "PASS" and score >= self.config.pass_threshold,
            "raw_response": response[:4000],  # truncate for storage
            "strengths": extract_section("Strengths"),
            "issues": extract_section("Issues"),
            "suggestions": extract_section("Suggestions"),
        }

    _REVIEW_PHASE_SYSTEM_PROMPT = (
        "You are an expert code quality reviewer. Evaluate the implementation "
        "against the design document, checking for correctness, completeness, "
        "and adherence to stated constraints."
    )

    def _review_task(
        self,
        task: SeedTask,
        generated_code: str,
        test_results: dict[str, Any],
    ) -> dict[str, Any]:
        """Conduct LLM review for a single task.

        Args:
            task: The seed task.
            generated_code: Code to review.
            test_results: Test results for context.

        Returns:
            Review result dict with score, verdict, cost.
        """
        try:
            agent = self._resolve_review_agent()
            prompt = self._build_review_prompt(task, generated_code, test_results)
            response_text, _time_ms, token_usage = agent.generate(
                prompt, system_prompt=self._REVIEW_PHASE_SYSTEM_PROMPT,
            )
            review = self._parse_review_response(response_text)
            review["task_id"] = task.task_id
            review["cost"] = token_usage_cost(token_usage)
            review["tokens"] = {
                "input": token_usage_input(token_usage),
                "output": token_usage_output(token_usage),
            }
            review["status"] = "reviewed"
            return review
        except Exception as exc:
            logger.warning("REVIEW: agent error for %s: %s", task.task_id, exc)
            return {
                "task_id": task.task_id,
                "score": 0,
                "verdict": "ERROR",
                "passed": False,
                "cost": 0.0,
                "tokens": {"input": 0, "output": 0},
                "error": str(exc),
                "status": "review_error",
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
        generation_results: dict[str, GenerationResult] = context.get("generation_results", {})
        test_results_ctx: dict[str, Any] = context.get("test_results", {})
        test_plan = test_results_ctx.get("test_plan", [])
        test_by_task = {t["task_id"]: t for t in test_plan if isinstance(t, dict)}

        # Gate 2c downstream map — used to exclude downstream stubs from
        # review scoring so they don't unfairly penalize the task.
        downstream_map: dict[str, list[str]] = context.get("_downstream_map", {})

        logger.info("REVIEW phase: reviewing %d tasks (dry_run=%s)", len(tasks), dry_run)

        review_items: list[dict[str, Any]] = []
        constraint_coverage: dict[str, int] = defaultdict(int)
        total_cost = 0.0
        total_passed = 0
        total_failed = 0
        previous_task_started_mono: Optional[float] = None

        for idx, task in enumerate(tasks, start=1):
            previous_task_started_mono = _log_task_timing(
                "REVIEW",
                task.task_id,
                idx,
                len(tasks),
                start,
                previous_task_started_mono,
            )
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

            # --- Real-mode path ---
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

            # Read generated code for review.
            # Exclude downstream stub files (Gate 2c) from the review body
            # so the reviewer doesn't penalize minimal placeholders that are
            # intentionally deferred to later tasks.
            task_downstream = set(downstream_map.get(task.task_id, []))
            code_parts = []
            excluded_downstream = []
            for fpath in gen_result.generated_files:
                try:
                    if not fpath.exists():
                        continue
                    # Check if this file is a downstream stub
                    rel_path = str(fpath)
                    is_downstream = any(
                        rel_path.endswith(ds) for ds in task_downstream
                    )
                    if is_downstream:
                        excluded_downstream.append(fpath.name)
                        continue

                    content = fpath.read_text(encoding="utf-8")
                    code_parts.append(f"# File: {fpath.name}\n{content}")
                except (OSError, UnicodeDecodeError) as exc:
                    logger.warning("REVIEW: could not read %s: %s", fpath, exc)
            if excluded_downstream:
                code_parts.append(
                    f"# NOTE: {len(excluded_downstream)} file(s) excluded from review "
                    f"(downstream stubs for later tasks): {', '.join(excluded_downstream)}"
                )
                logger.info(
                    "REVIEW: excluded %d downstream stub(s) from review for %s: %s",
                    len(excluded_downstream), task.task_id, excluded_downstream,
                )
            generated_code = "\n\n".join(code_parts)
            if not generated_code.strip():
                review_items.append({
                    "task_id": task.task_id,
                    "title": task.title,
                    "domain": task.domain,
                    "constraint_count": len(task.prompt_constraints),
                    "env_failures": len(env_fails),
                    "env_warnings": len(env_warns),
                    "review_status": "skipped_no_code",
                })
                continue
            task_test = test_by_task.get(task.task_id, {})

            review = self._review_task(task, generated_code, task_test)
            review["title"] = task.title
            review["domain"] = task.domain
            review["constraint_count"] = len(task.prompt_constraints)
            review["env_failures"] = len(env_fails)
            review["env_warnings"] = len(env_warns)
            review["review_status"] = review.get("status", "reviewed")

            total_cost += review.get("cost", 0.0)
            if review.get("passed", False):
                total_passed += 1
            else:
                total_failed += 1

            review_items.append(review)

            # Emit quality gate result (Item 10)
            try:
                gate_result = GateEmitter.from_review_result(
                    task_id=task.task_id,
                    review_dict=review,
                    workflow_id=context.get("workflow_id", "unknown"),
                    trace_id=context.get("trace_id"),
                )
                GateEmitter.emit(gate_result)
            except Exception as e:
                logger.warning("Failed to emit review gate result for %s: %s", task.task_id, e)

        per_task: dict[str, Any] = {}
        for item in review_items:
            task_id = item.get("task_id")
            if not task_id:
                continue
            status = item.get("review_status", "unknown")
            per_task[task_id] = {
                "status": status,
                "passed": item.get("passed") if status == "reviewed" else None,
                "score": item.get("score"),
                "verdict": item.get("verdict"),
            }

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
            "per_task": per_task,
        }

        context["review_results"] = output

        # Context contract: validate REVIEW output model
        ReviewPhaseOutput(review_results=context["review_results"])

        duration = time.monotonic() - start

        logger.info(
            "REVIEW phase complete: %d items, %d passed, %d failed, $%.4f cost (%.2fs)",
            len(review_items), total_passed, total_failed, total_cost, duration,
        )

        # "cost" is the authoritative phase cost; output["total_cost"] is for reporting
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
    # WCP-004: Propagation completeness validation
    # ------------------------------------------------------------------

    REQUIRED_CONTEXT_FIELDS = ["domain", "domain_reasoning", "prompt_constraints"]

    def _validate_propagation_completeness(
        self, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Check that all tasks received expected context fields.

        Attempts to use the contract-based PropagationTracker for chain
        validation with OTel emission.  Falls back to the original inline
        implementation if contextcore propagation module is not available.

        Args:
            context: Workflow context containing ``tasks`` list.

        Returns:
            Dict with ``total``, ``complete``, ``defaulted``, and
            optionally ``defaulted_tasks`` listing task IDs that fell back.
        """
        # Try contract-based validation first
        try:
            from contextcore.contracts.propagation import (
                ContractLoader,
                PropagationTracker,
                emit_propagation_summary,
            )
            from pathlib import Path

            contract_yaml = Path(__file__).parent / "contracts" / "artisan-pipeline.contract.yaml"
            if contract_yaml.exists():
                contract = ContractLoader().load(contract_yaml)
                tracker = PropagationTracker()
                chain_results = tracker.validate_all_chains(contract, context)
                emit_propagation_summary(chain_results)

                # Convert chain results to legacy format for backward compat
                from contextcore.contracts.types import ChainStatus
                intact = sum(1 for r in chain_results if r.status == ChainStatus.INTACT)
                total = len(chain_results)
                return {
                    "total": total,
                    "complete": intact,
                    "defaulted": total - intact,
                    "defaulted_tasks": [
                        r.chain_id for r in chain_results
                        if r.status != ChainStatus.INTACT
                    ],
                }
        except ImportError:
            pass  # contextcore propagation not available — use fallback
        except Exception as exc:
            logger.warning(
                "Contract-based propagation validation failed, using fallback: %s", exc
            )

        # Fallback: original inline implementation
        tasks = context.get("tasks", [])
        results: dict[str, Any] = {
            "total": len(tasks),
            "complete": 0,
            "defaulted": 0,
            "defaulted_tasks": [],
        }

        for task in tasks:
            all_present = True
            for field in self.REQUIRED_CONTEXT_FIELDS:
                value = getattr(task, field, None)
                if value in (None, "", "unknown", []):
                    results["defaulted"] += 1
                    results["defaulted_tasks"].append(
                        getattr(task, "task_id", "?"),
                    )
                    logger.warning(
                        "FINALIZE: context field '%s' not propagated for task %s",
                        field,
                        getattr(task, "task_id", "?"),
                    )
                    all_present = False
                    break
            if all_present:
                results["complete"] += 1

        # Emit span event for propagation summary
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            if span and span.is_recording():
                span.add_event("context.propagation_summary", attributes={
                    "context.total_tasks": results["total"],
                    "context.complete": results["complete"],
                    "context.defaulted": results["defaulted"],
                    "context.completeness_pct": round(
                        results["complete"] / max(results["total"], 1) * 100, 1
                    ),
                })
        except Exception:
            pass  # OTel not available — non-fatal

        return results

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _collect_generated_artifacts(
        self,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
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
        artifacts: list[dict[str, Any]] = []
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )

        # Build task_id → SeedTask lookup for domain metadata
        tasks: list[SeedTask] = context.get("tasks", [])
        id_to_task: dict[str, SeedTask] = {t.task_id: t for t in tasks}

        for task_id, result in generation_results.items():
            if result.success:
                task = id_to_task.get(task_id)
                for fpath in result.generated_files:
                    artifact: dict[str, Any] = {
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

    def _build_cost_summary(self, context: dict[str, Any]) -> dict[str, Any]:
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

        def _safe_cost(d: dict, key: str = "total_cost") -> float:
            try:
                return float(d.get(key, 0.0))
            except (TypeError, ValueError):
                return 0.0

        impl_cost = _safe_cost(implementation)
        test_cost = _safe_cost(test_results)
        review_cost = _safe_cost(review_results)
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
        artifacts: list[dict[str, Any]],
        summary: dict[str, Any],
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
        generation_results: dict[str, GenerationResult] = context.get(
            "generation_results", {}
        )
        test_results_ctx: dict[str, Any] = context.get("test_results", {})
        review_results_ctx: dict[str, Any] = context.get("review_results", {})

        test_results_map: dict[str, Any] = dict(
            test_results_ctx.get("per_task", {}) or {}
        )
        if not test_results_map:
            logger.debug("FINALIZE: rebuilding test_results_map from test_plan entries")
            for entry in test_results_ctx.get("test_plan", []):
                if not isinstance(entry, dict):
                    continue
                task_id = entry.get("task_id")
                if not task_id:
                    continue
                status = entry.get("status", "unknown")
                passed = (
                    True if status == "passed"
                    else False if status == "failed"
                    else None
                )
                validators_run = entry.get("validators_run", 0)
                results = entry.get("results", [])
                failures = [
                    r.get("validator", "unknown")
                    for r in results
                    if isinstance(r, dict) and not r.get("passed", True)
                ]
                test_results_map[task_id] = {
                    "status": status,
                    "passed": passed,
                    "validators_run": validators_run,
                    "failures": failures,
                }

        review_results_map: dict[str, Any] = dict(
            review_results_ctx.get("per_task", {}) or {}
        )
        if not review_results_map:
            logger.debug("FINALIZE: rebuilding review_results_map from review_items entries")
            for entry in review_results_ctx.get("review_items", []):
                if not isinstance(entry, dict):
                    continue
                task_id = entry.get("task_id")
                if not task_id:
                    continue
                review_results_map[task_id] = {
                    "status": entry.get("review_status", "unknown"),
                    "passed": entry.get("passed"),
                    "score": entry.get("score"),
                    "verdict": entry.get("verdict"),
                }

        task_status: dict[str, dict[str, Any]] = {}
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
            # Fix 1b: provenance chain — record source_checksum for Gate 3
            "provenance": {
                "source_checksum": context.get("source_checksum"),
                "enriched_seed_path": str(context.get("enriched_seed_path", "")),
            },
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
            atomic_write_json(manifest_path, manifest, indent=2, default=str)
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
        generation_results: dict[str, GenerationResult] = context.get(
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

        summary: dict[str, Any] = {
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
            atomic_write_json(output_path, summary, indent=2, default=str)
            logger.info("Wrote execution report to %s", output_path)
            summary["report_path"] = str(output_path)

            # Write manifest of generated files
            manifest_path = self._write_manifest(
                artifacts, summary, context, Path(self.output_dir),
            )
            if manifest_path:
                summary["manifest_path"] = str(manifest_path)

        context["workflow_summary"] = summary

        # Context contract: validate FINALIZE output model
        FinalizePhaseOutput(workflow_summary=context["workflow_summary"])

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
            output_dir="out/artifacts",
        )
    """

    @staticmethod
    def create_all(
        enriched_seed_path: str,
        output_dir: Optional[str] = None,
        *,
        # Agent configuration (keyword-only) — all Optional so callers
        # only pass what they explicitly want to override.  Missing keys
        # are resolved via the config-file / env-var / dataclass-default
        # priority chain in HandlerConfig.from_config().
        lead_agent: Optional[str] = None,
        drafter_agent: Optional[str] = None,
        max_iterations: Optional[int] = None,
        pass_threshold: Optional[int] = None,
        max_tokens: Optional[int] = None,
        design_max_tokens: Optional[int] = None,
        fail_on_truncation: Optional[bool] = None,
        check_truncation: Optional[bool] = None,
        strict_truncation: Optional[bool] = None,
        test_timeout_seconds: Optional[int] = None,
        review_temperature: Optional[float] = None,
        review_max_code_chars: Optional[int] = None,
        development_timeout_seconds: Optional[float] = None,
        auto_commit: Optional[bool] = None,
        scaffold_test_first: Optional[bool] = None,
        force_implement: Optional[bool] = None,
        code_generator: Optional[CodeGenerator] = None,
    ) -> dict[WorkflowPhase, AbstractPhaseHandler]:
        """Create handlers for all seven workflow phases.

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
            review_max_code_chars: Max chars of code in review prompt.
            development_timeout_seconds: Timeout for development thread.
            auto_commit: Commit each feature's generated code to git.
            scaffold_test_first: Scaffold test files for artifact tasks before impl.
            code_generator: Optional pre-configured CodeGenerator instance.

        Returns:
            Dict mapping WorkflowPhase → handler instance.
        """
        # Build cli_overrides from non-None kwargs
        cli_overrides: dict[str, Any] = {}
        for name, val in [
            ("lead_agent", lead_agent),
            ("drafter_agent", drafter_agent),
            ("max_iterations", max_iterations),
            ("pass_threshold", pass_threshold),
            ("max_tokens", max_tokens),
            ("design_max_tokens", design_max_tokens),
            ("fail_on_truncation", fail_on_truncation),
            ("check_truncation", check_truncation),
            ("strict_truncation", strict_truncation),
            ("test_timeout_seconds", test_timeout_seconds),
            ("review_temperature", review_temperature),
            ("review_max_code_chars", review_max_code_chars),
            ("development_timeout_seconds", development_timeout_seconds),
            ("auto_commit", auto_commit),
            ("scaffold_test_first", scaffold_test_first),
            ("force_implement", force_implement),
        ]:
            if val is not None:
                cli_overrides[name] = val

        config = HandlerConfig.from_config(cli_overrides or None)

        return {
            WorkflowPhase.PLAN: PlanPhaseHandler(enriched_seed_path),
            WorkflowPhase.SCAFFOLD: ScaffoldPhaseHandler(),
            WorkflowPhase.DESIGN: DesignPhaseHandler(
                handler_config=config,
                output_dir=output_dir,
            ),
            WorkflowPhase.IMPLEMENT: ImplementPhaseHandler(
                handler_config=config,
                code_generator=code_generator,
                enriched_seed_path=Path(enriched_seed_path),
            ),
            WorkflowPhase.TEST: TestPhaseHandler(handler_config=config),
            WorkflowPhase.REVIEW: ReviewPhaseHandler(handler_config=config),
            WorkflowPhase.FINALIZE: FinalizePhaseHandler(
                output_dir=output_dir,
                handler_config=config,
            ),
        }
