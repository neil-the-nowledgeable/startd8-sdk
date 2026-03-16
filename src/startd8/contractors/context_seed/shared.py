"""Shared helpers for context seed phase handlers."""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from startd8.contractors.artisan_contractor import _SAFE_TASK_ID_PATTERN
from startd8.implementation_engine.package_aliases import (
    _PYPI_TO_IMPORT,
    pypi_to_import,
)
from startd8.logging_config import get_logger
from startd8.seeds.utils import safe_onboarding

logger = get_logger("startd8.contractors.context_seed_handlers")


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
    # Dependency allowlist source and confidence (Gate 5)
    deps_source: Optional[str] = None
    deps_confidence: float = 1.0
    # IMP-1: Verbatim requirements text from plan
    requirements_text: str = ""
    # IMP-4: Extended schema fields from ParsedFeature
    api_signatures: list[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: list[str] = field(default_factory=list)
    negative_scope: list[str] = field(default_factory=list)
    # Wave+Lane execution: dependency-depth wave assignment
    wave_index: Optional[int] = None
    # REQ-CMR-042: Optional seed override of complexity tier
    complexity_tier_override: Optional[str] = None

    @classmethod
    def from_seed_entry(cls, entry: dict[str, Any]) -> "SeedTask":
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
                logger.debug("OTel context not available", exc_info=True)
            logger.debug(
                "SeedTask %s: domain defaulted to 'unknown' (enrichment missing or incomplete)",
                entry.get("task_id", "?"),
            )

        # Compute deps_confidence from deps_source
        deps_source = enrichment.get("deps_source")
        _source_confidence = {
            "pyproject": 1.0,
            "requirements_txt": 0.85,
            "setup_cfg": 0.85,
            "venv_only": 0.5,
            "stdlib_only": 0.2,
        }
        deps_confidence = _source_confidence.get(deps_source, 1.0) if deps_source else 1.0

        # --- Task ID safety validation (defense-in-depth) ---
        raw_task_id = entry.get("task_id", "")
        if raw_task_id and not _SAFE_TASK_ID_PATTERN.match(raw_task_id):
            logger.warning(
                "Task ID %r contains unsafe characters (must match %s) — "
                "this may cause errors in wave computation, checkpoint keys, "
                "or file path construction",
                raw_task_id, _SAFE_TASK_ID_PATTERN.pattern,
            )

        # Validate depends_on entries for safe characters
        raw_depends = entry.get("depends_on") or []
        for dep_id in raw_depends:
            if isinstance(dep_id, str) and dep_id and not _SAFE_TASK_ID_PATTERN.match(dep_id):
                logger.warning(
                    "Task %s: depends_on reference %r contains unsafe characters "
                    "(must match %s)",
                    raw_task_id, dep_id, _SAFE_TASK_ID_PATTERN.pattern,
                )

        # --- Wave index parsing with validation ---
        raw_wave = entry.get("wave_index")
        if raw_wave is not None:
            if not isinstance(raw_wave, int) or isinstance(raw_wave, bool):
                logger.warning(
                    "Task %s: wave_index=%r is not an integer — ignoring",
                    entry.get("task_id"), raw_wave,
                )
                raw_wave = None
            elif raw_wave < 0:
                logger.warning(
                    "Task %s: wave_index=%d is negative — ignoring",
                    entry.get("task_id"), raw_wave,
                )
                raw_wave = None
        wave_index = raw_wave

        _override_raw = (
            context.get("complexity_tier_override")
            or config.get("complexity_tier_override")
            or entry.get("complexity_tier_override")
        )
        complexity_tier_override: Optional[str] = None
        if isinstance(_override_raw, str):
            _normalized = _override_raw.strip().lower()
            if _normalized in {"tier_1", "tier_2", "tier_3"}:
                complexity_tier_override = _normalized
            elif _normalized:
                logger.warning(
                    "Task %s: invalid complexity_tier_override %r (expected tier_1|tier_2|tier_3) — ignoring",
                    entry.get("task_id", "?"),
                    _override_raw,
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
            deps_source=deps_source,
            deps_confidence=deps_confidence,
            requirements_text=config.get("requirements_text", ""),
            api_signatures=context.get("api_signatures", []),
            protocol=context.get("protocol", ""),
            runtime_dependencies=context.get("runtime_dependencies", []),
            negative_scope=context.get("negative_scope", []),
            wave_index=wave_index,
            complexity_tier_override=complexity_tier_override,
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
    context.setdefault("domain_summary", dict(domain_counts))
    context["total_estimated_loc"] = sum(t.estimated_loc for t in tasks)
    context["example_artifacts"] = (seed_data.get("artifacts") or {}).get(
        "example_artifacts", {}
    )

    # Restore Phase 2 data flow keys as defense-in-depth fallback.
    # These originate from PLAN phase (via the enriched seed's artifacts and
    # top-level keys) and are persisted via _CHECKPOINT_CONTEXT_KEYS, but if
    # checkpoint serialization dropped any of them, re-extract from the seed
    # rather than silently losing them.
    _artifacts = seed_data.get("artifacts") or {}
    context.setdefault("source_checksum", _artifacts.get("source_checksum") or "")
    context.setdefault("parameter_sources", _artifacts.get("parameter_sources", {}))
    context.setdefault("semantic_conventions", _artifacts.get("semantic_conventions", {}))
    context.setdefault("output_conventions", _artifacts.get("output_conventions", {}))
    context.setdefault("architectural_context", seed_data.get("architectural_context", {}))
    context.setdefault("design_calibration", seed_data.get("design_calibration", {}))
    context.setdefault("project_metadata", seed_data.get("project_metadata", {}))

    # PCA-201: re-extract onboarding fields as defense-in-depth.
    _onboarding = seed_data.get("onboarding") or {}

    # REQ-GPC-202: restore generation profile on resume
    if "generation_profile" not in context:
        context["generation_profile"] = _onboarding.get("generation_profile", "full")

    # REQ-GPC-201: skip ContextCore profile-omitted markers on resume path
    _pca_fields = {
        "onboarding_derivation_rules": safe_onboarding(_onboarding.get("derivation_rules")),
        "onboarding_resolved_parameters": safe_onboarding(_onboarding.get("resolved_artifact_parameters")),
        "onboarding_output_contracts": safe_onboarding(_onboarding.get("expected_output_contracts")),
        "onboarding_calibration_hints": safe_onboarding(_onboarding.get("design_calibration_hints")),
        "onboarding_open_questions": safe_onboarding(_onboarding.get("open_questions")),
        "onboarding_dependency_graph": safe_onboarding(_onboarding.get("artifact_dependency_graph")),
        "service_metadata": safe_onboarding(_onboarding.get("service_metadata")),
        "onboarding_schema_features": safe_onboarding(
            _onboarding.get("capabilities", {}).get("schema_features")
            or _onboarding.get("schema_features")
        ),
    }
    _restored = 0
    for key, value in _pca_fields.items():
        if key not in context:
            context[key] = value
            _restored += 1
    if _restored:
        logger.info("Restored %d/8 onboarding fields from seed on resume", _restored)

    # IMP-8b: extract structured refine suggestions from onboarding
    if "onboarding_refine_suggestions" not in context:
        _refine_sug = _onboarding.get("refine_suggestions")
        if _refine_sug and isinstance(_refine_sug, list):
            context["onboarding_refine_suggestions"] = _refine_sug
            logger.info(
                "Restored onboarding_refine_suggestions from seed (%d entries)",
                len(_refine_sug),
            )

    # IMP-9c: extract refine provenance from seed artifacts
    if "refine_provenance" not in context:
        _refine_prov = _artifacts.get("refine_provenance")
        if _refine_prov and isinstance(_refine_prov, dict):
            context["refine_provenance"] = _refine_prov
            logger.info("Restored refine_provenance from seed artifacts")

    # R2-D7: Restore forward_manifest from seed on resume so downstream
    # phases can access interface contracts.
    if "forward_manifest" not in context:
        _fm_dict = seed_data.get("forward_manifest")
        if _fm_dict and isinstance(_fm_dict, dict):
            try:
                from startd8.forward_manifest import ForwardManifest
                context["forward_manifest"] = ForwardManifest.model_validate(_fm_dict)
                logger.info("Restored forward_manifest from seed on resume")
            except (ImportError, ValueError, TypeError):
                context["forward_manifest"] = _fm_dict
                logger.debug(
                    "Restored forward_manifest as raw dict (model validation failed)",
                    exc_info=True,
                )

    # PCA-201: re-load plan_document_text from seed artifacts
    if "plan_document_text" not in context:
        plan_doc_path_str = _artifacts.get("plan_document_path")
        if plan_doc_path_str:
            _pdp = Path(plan_doc_path_str)
            if not _pdp.is_absolute():
                _pdp = Path(seed_path).parent / _pdp
            if _pdp.exists():
                try:
                    context["plan_document_text"] = _pdp.read_text(encoding="utf-8")
                    logger.info("Restored plan_document_text from seed on resume")
                except OSError:
                    logger.debug("Could not read file: %s", _pdp, exc_info=True)

    # R2-D4: Restore scaffold data on resume.  The scaffold dict is normally
    # populated by ScaffoldPhaseHandler and persisted via _CHECKPOINT_CONTEXT_KEYS.
    # If it was lost (serialization failure, impl-half standalone execution),
    # reconstruct minimal scaffold from tasks + project_root so that DESIGN
    # can access existing_target_files, file_stubs, and assembly_degraded.
    if "scaffold" not in context:
        _project_root = Path(context.get("project_root", "."))
        _existing_files = []
        _dirs_needed: set[str] = set()
        for _t in tasks:
            for _tf in _t.target_files:
                _tp = _project_root / _tf
                if _tp.exists():
                    _existing_files.append(_tf)
                try:
                    _dirs_needed.add(str(_tp.parent.relative_to(_project_root)))
                except ValueError:
                    pass
        context["scaffold"] = {
            "existing_target_files": _existing_files,
            "file_stubs": [],
            "file_stubs_created": 0,
            "file_stubs_skipped": 0,
            "file_stubs_failed": 0,
            "assembly_degraded": False,
            "directories_needed": sorted(_dirs_needed),
            "directories_exist": [],
            "directories_created": [],
            "directories_missing": [],
            "staleness_classification": {},
            "skipped_targets": [],
            "project_root": str(_project_root),
            "extension_warnings": [],
            "module_inventory": [],
        }
        logger.warning(
            "R2-D4: scaffold data missing on resume — reconstructed minimal "
            "scaffold with %d existing target files",
            len(_existing_files),
        )

    return _apply_runtime_task_selection(tasks)


# PCA-104: project-level context fields for completeness logging.
_PCA_CONTEXT_FIELDS = (
    "project_root", "service_metadata", "plan_document_text",
    "architectural_context", "project_metadata",
    "onboarding_derivation_rules",
    "onboarding_resolved_parameters", "onboarding_output_contracts",
    "onboarding_calibration_hints", "onboarding_open_questions",
    "onboarding_dependency_graph", "onboarding_schema_features",
)


def _log_context_completeness(phase_name: str, context: dict[str, Any]) -> None:
    """PCA-104: Log which project-level context fields are present at phase entry."""
    present = [f for f in _PCA_CONTEXT_FIELDS if context.get(f) is not None]
    count = len(present)
    total = len(_PCA_CONTEXT_FIELDS)
    logger.info(
        "%s: project context %d/%d fields present", phase_name, count, total,
    )
    if count < 3:
        logger.warning(
            "%s: degraded project context — only %d/%d fields available, "
            "code quality may be reduced",
            phase_name, count, total,
        )


def _track_onboarding_consumption(
    context: dict[str, Any], field_name: str, phase_name: str,
) -> None:
    """PCA-402: Record that a phase consumed an onboarding field."""
    audit = context.setdefault("_onboarding_consumption", {})
    # REQ-GPC-700: record generation profile in consumption audit
    if "_generation_profile" not in audit:
        audit["_generation_profile"] = context.get("generation_profile", "full")
    audit.setdefault(field_name, [])
    if phase_name not in audit[field_name]:
        audit[field_name].append(phase_name)


# ---------------------------------------------------------------------------
# L3: Per-service dependency scoping
# ---------------------------------------------------------------------------
# _PYPI_TO_IMPORT is imported from package_aliases.py (single source of truth).


def _strip_version_pin(dep: str) -> str:
    """Strip version pins from a dependency string: ``grpcio==1.76.0`` → ``grpcio``."""
    for sep in ("==", ">=", "<=", "~=", "!=", "<", ">"):
        dep = dep.split(sep)[0]
    return dep.strip()


def _extract_imported_modules(source: str) -> set[str]:
    """Extract top-level imported module names from Python source via AST.

    Returns a set of top-level package names (e.g. ``grpc`` from
    ``import grpc.reflection`` or ``from grpc_health.v1 import ...``).
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def scope_dependencies_to_file(
    file_path: str,
    file_content: str,
    all_dependencies: list[str],
) -> list[str]:
    """Return only the dependencies that *file_path* actually imports.

    Parses *file_content* with ``ast`` to extract top-level import names,
    then intersects with *all_dependencies* (stripping version pins).
    Falls back to *all_dependencies* if parsing fails (e.g. non-Python files).
    """
    if not file_content or not all_dependencies:
        return list(all_dependencies) if all_dependencies else []

    # Non-Python files get the full list
    if not file_path.endswith(".py"):
        return list(all_dependencies)

    imported = _extract_imported_modules(file_content)
    if not imported:
        # AST parsing returned nothing — fallback to full list
        return list(all_dependencies)

    scoped: list[str] = []
    for dep in all_dependencies:
        pkg_name = _strip_version_pin(dep)
        # Direct match: PyPI name == import name (common case: flask, locust)
        if pkg_name.lower().replace("-", "_") in imported:
            scoped.append(dep)
            continue
        # Alias match: PyPI name maps to a different import name
        import_name = pypi_to_import(pkg_name.lower())
        # pypi_to_import returns the input unchanged when no mapping exists,
        # so only match when it actually resolved to something different.
        if import_name != pkg_name.lower() and import_name.split(".")[0] in imported:
            scoped.append(dep)
            continue

    return scoped


__all__ = [
    "SeedTask",
    "_ensure_context_loaded",
    "_load_enriched_seed",
    "_log_context_completeness",
    "_parse_tasks",
    "_topological_sort",
    "_track_onboarding_consumption",
    "scope_dependencies_to_file",
    "_PYPI_TO_IMPORT",
    "_strip_version_pin",
    "_extract_imported_modules",
]
