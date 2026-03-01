"""Pure extraction functions: enriched seed -> module data.

Each function extracts data for one prompt module. No LLM calls, no side
effects, no conditional injection logic. Just data extraction with None
for missing fields (Mottainai rule 3: degrade gracefully).
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from startd8.logging_config import get_logger

if TYPE_CHECKING:
    from startd8.contractors.context_seed_handlers import SeedTask

logger = get_logger(__name__)


def extract_identity(
    task: SeedTask,
    *,
    existing_files: list[str] | None = None,
) -> dict[str, Any]:
    """Extract identity fields from a SeedTask. Always succeeds."""
    return {
        "task_id": task.task_id,
        "title": task.title,
        "description": task.description,
        "target_files": task.target_files or [],
        "feature_id": task.feature_id,
        "file_scope": task.file_scope or {},
        "existing_files": existing_files or [],
    }


def extract_constraints(
    task: SeedTask,
    architectural_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract binding constraints. Forwards plan data verbatim (Mottainai rule 2)."""
    return {
        "prompt_constraints": list(task.prompt_constraints),
        "api_signatures": task.api_signatures,
        "protocol": task.protocol,
        "negative_scope": task.negative_scope,
        "arch_constraints": (architectural_context or {}).get("constraints", []),
    }


def extract_prior_art(
    task: SeedTask,
    *,
    prior_design_summaries: list[str] | None = None,
    dependency_designs: dict[str, str] | None = None,
    scaffold_existing_files: list[str] | None = None,
    staleness_classification: dict[str, str] | None = None,
    file_stubs: list[dict[str, Any]] | None = None,
    assembly_degraded: bool = False,
) -> dict[str, Any] | None:
    """Extract prior art context. Returns None if nothing exists."""
    result: dict[str, Any] = {}

    if file_stubs:
        result["file_stubs"] = file_stubs
    if assembly_degraded:
        result["assembly_degraded"] = assembly_degraded

    if prior_design_summaries:
        result["summaries"] = prior_design_summaries[-5:]

    if dependency_designs:
        result["dependency_designs"] = dependency_designs

    if scaffold_existing_files and task.target_files:
        existing_set = set(scaffold_existing_files)
        existing = [f for f in task.target_files if f in existing_set]
        if existing:
            result["existing_files"] = existing

    if staleness_classification and task.target_files:
        stale = {
            f: staleness_classification[f]
            for f in task.target_files
            if f in staleness_classification
        }
        if stale:
            result["staleness"] = stale

    if not result:
        # file_stubs alone is sufficient prior art (scaffold skeletons are
        # binding) — only return None when truly empty.
        if file_stubs:
            return {"file_stubs": file_stubs}
        logger.debug(
            "extract_prior_art: no prior art for task %s", task.task_id,
        )
        return None
    return result


def extract_scope(
    task: SeedTask,
    *,
    calibration: dict[str, Any] | None = None,
    design_max_tokens_override: int | None = None,
    wave_index: int | None = None,
    wave_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract scope boundaries. Always succeeds (has defaults)."""
    cal = calibration or {}
    return {
        "estimated_loc": task.estimated_loc,
        "depth_tier": cal.get("depth_tier", "standard"),
        "sections": cal.get("sections"),
        "max_output_tokens": (
            design_max_tokens_override
            if design_max_tokens_override is not None
            else cal.get("max_output_tokens")
        ),
        "wave_index": wave_index,
        "wave_count": (wave_metadata or {}).get("wave_count"),
    }


def extract_guidance(
    task: SeedTask,
    *,
    plan_goals: list[str] | None = None,
    refine_suggestions: str | list[dict[str, Any]] | None = None,
    open_questions: list[dict[str, Any]] | None = None,
    calibration_hints: dict[str, Any] | None = None,
    complexity_dimensions: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Extract advisory guidance. Returns None if nothing available."""
    result: dict[str, Any] = {}

    if task.domain and task.domain != "unknown":
        result["domain"] = task.domain

    if plan_goals:
        result["plan_goals"] = plan_goals[:5]

    if refine_suggestions:
        result["refine_suggestions"] = refine_suggestions

    if open_questions:
        result["open_questions"] = open_questions[:5]

    # Extract depth hint from calibration hints for this task's artifact types
    if calibration_hints and task.artifact_types_addressed:
        for atype in task.artifact_types_addressed:
            hint = calibration_hints.get(atype)
            if isinstance(hint, dict) and hint.get("expected_depth"):
                result["depth_hint"] = hint["expected_depth"]
                break

    if complexity_dimensions:
        high = {
            k: v
            for k, v in complexity_dimensions.items()
            if isinstance(v, (int, float)) and v > 70
        }
        if high:
            result["complexity_alerts"] = high

    if not result:
        logger.debug(
            "extract_guidance: no guidance for task %s", task.task_id,
        )
        return None
    return result


def extract_manifest_context(
    task: SeedTask,
    *,
    manifest_registry: Any = None,
    manifest_context_budget: int = 2000,
    enable_introspect: bool = False,
) -> dict[str, Any] | None:
    """Extract structural context from the code manifest registry.

    For each target file in the task, queries the manifest registry for
    element summaries (classes, functions, imports). Returns None when
    no registry is available or no files have manifest entries.

    Args:
        task: The seed task with target_files.
        manifest_registry: A ManifestRegistry instance (or None).
        manifest_context_budget: Max chars per file element summary.
        enable_introspect: When True, include module_version (PI-1) and
            prefer resolved signatures in file summaries (PI-2). When False,
            behavior is identical to pre-Phase-5 (PI-3 graceful degradation).

    Returns:
        Dict with ``file_summaries`` and optional ``dependency_context``,
        ``module_versions`` (when enable_introspect), or None if no manifest
        data is available.
    """
    if manifest_registry is None:
        return None

    file_summaries: dict[str, str] = {}
    for tf in getattr(task, "target_files", []) or []:
        try:
            summary = manifest_registry.file_element_summary(
                tf,
                manifest_context_budget,
                include_resolved_types=enable_introspect,
            )
            if summary:
                file_summaries[tf] = summary
        except Exception:
            logger.debug(
                "extract_manifest_context: lookup failed for %s",
                tf, exc_info=True,
            )

    if not file_summaries:
        logger.debug(
            "extract_manifest_context: no manifest data for task %s",
            task.task_id,
        )
        return None

    result: dict[str, Any] = {"file_summaries": file_summaries}

    # PI-1: module_version in compatibility context when enable_introspect
    if enable_introspect:
        module_versions: dict[str, str] = {}
        for tf in file_summaries:
            try:
                ver = manifest_registry.module_version_for(tf)
                if ver:
                    module_versions[tf] = ver
            except Exception:
                pass
        if module_versions:
            result["module_versions"] = module_versions

    # Optionally extract dependency context
    try:
        dep_graph = manifest_registry.dependency_graph()
        if dep_graph and isinstance(dep_graph, dict):
            task_deps = {
                f: dep_graph[f]
                for f in file_summaries
                if f in dep_graph
            }
            if task_deps:
                result["dependency_context"] = task_deps
    except Exception:
        pass  # dependency_graph() is optional

    # Phase 6: Call graph context per file
    try:
        cg_parts: list[str] = []
        for tf in file_summaries:
            cg_summary = manifest_registry.call_graph_summary(tf, manifest_context_budget)
            if cg_summary:
                cg_parts.append(f"### {tf}\n{cg_summary}")
        if cg_parts:
            result["call_graph_context"] = "\n\n".join(cg_parts)
    except Exception:
        pass  # call_graph_summary() is optional

    return result


def extract_enrichment(
    task: SeedTask,
    *,
    parameter_sources: dict[str, Any] | None = None,
    semantic_conventions: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Extract parameter provenance and naming conventions (Mottainai rules 2, 5).

    These are deterministic values resolved by the pipeline — the LLM should
    use them verbatim rather than inventing alternatives.

    Returns None if neither field is populated.
    """
    result: dict[str, Any] = {}

    if parameter_sources:
        result["parameter_sources"] = parameter_sources

    if semantic_conventions:
        result["semantic_conventions"] = semantic_conventions

    if not result:
        logger.debug(
            "extract_enrichment: no provenance data for task %s", task.task_id,
        )
        return None
    return result

def map_forward_contracts_for_task(
    task: SeedTask,
    *,
    forward_manifest: Any = None,
) -> dict[str, Any] | None:
    """Extract forward interface contracts applicable to this task.

    Args:
        task: The seed task being processed.
        forward_manifest: A hydrated ForwardManifest model instance (or None).

    Returns:
        Dict matching the schema required by ContractModule, or None if
        no manifest exists or no contracts apply to this task (Mottainai rule 3).
    """
    if forward_manifest is None:
        logger.debug(
            "map_forward_contracts_for_task: no forward_manifest provided for %s",
            task.task_id,
        )
        return None

    try:
        contracts = forward_manifest.contracts_for_task(task.task_id)
        if not contracts:
            logger.debug(
                "map_forward_contracts_for_task: no applicable contracts for %s",
                task.task_id,
            )
            return None

        # Resolve file specs matching this task's target files
        file_specs = forward_manifest.file_specs_for_task(
            task.task_id,
            getattr(task, "target_files", []) or [],
        )

        return {
            "contracts": [c.model_dump() for c in contracts],
            "file_specs": {path: spec.model_dump() for path, spec in file_specs.items()},
        }
    except Exception:
        logger.warning(
            "map_forward_contracts_for_task: failed to extract contracts for %s",
            task.task_id,
            exc_info=True,
        )
        return None
