"""Modular design prompt assembly (v2).

Replaces the 536-line monolithic ``_task_to_feature_context()`` with 5
composable modules and a simple budget enforcement policy.

Usage::

    from startd8.contractors.artisan_phases.design_prompts import assemble_design_prompt

    system_prompt, user_prompt, max_tokens = assemble_design_prompt(
        task,
        plan_goals=["goal1"],
        calibration={"depth_tier": "standard"},
    )
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, TYPE_CHECKING

import yaml
from startd8.logging_config import get_logger

from .modules import (
    PromptFragment,
    IdentityModule,
    ConstraintsModule,
    EnrichmentModule,
    ManifestModule,
    PriorArtModule,
    ScopeModule,
    GuidanceModule,
    ContractModule,
)
from .seed_mapping import (
    extract_identity,
    extract_constraints,
    extract_enrichment,
    extract_manifest_context,
    extract_prior_art,
    extract_scope,
    extract_guidance,
    map_forward_contracts_for_task,
)
from .budget import enforce_budget, DEFAULT_PROMPT_TOKEN_BUDGET

if TYPE_CHECKING:
    from startd8.contractors.context_seed_handlers import SeedTask

__all__ = [
    "assemble_design_prompt",
    "PromptFragment",
    "DEFAULT_PROMPT_TOKEN_BUDGET",
]

logger = get_logger(__name__)

_TEMPLATES_DIR = Path(__file__).parent


@lru_cache(maxsize=4)
def _load_templates() -> dict[str, Any]:
    """Load and cache the v2 YAML templates."""
    path = _TEMPLATES_DIR / "templates.yaml"
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["prompts"]


def _get_system_prompt(*, refine: bool = False) -> str:
    """Return the v2 system prompt template."""
    templates = _load_templates()
    key = "design_system_v2_refine" if refine else "design_system_v2"
    return templates[key]["template"]


def _get_user_template(*, refine: bool = False) -> str:
    """Return the v2 user prompt template."""
    templates = _load_templates()
    key = "design_user_v2_refine" if refine else "design_user_v2"
    return templates[key]["template"]


# The 7 module instances (stateless, reusable)
_MODULES = [
    IdentityModule(),
    ConstraintsModule(),
    EnrichmentModule(),
    ManifestModule(),
    PriorArtModule(),
    ScopeModule(),
    GuidanceModule(),
    ContractModule(),
]


def assemble_design_prompt(
    task: SeedTask,
    *,
    plan_goals: list[str] | None = None,
    architectural_context: dict[str, Any] | None = None,
    prior_design_summaries: list[str] | None = None,
    calibration: dict[str, Any] | None = None,
    design_max_tokens_override: int | None = None,
    # Bridge context
    dependency_designs: dict[str, str] | None = None,
    scaffold_existing_files: list[str] | None = None,
    staleness_classification: dict[str, str] | None = None,
    wave_index: int | None = None,
    wave_metadata: dict[str, Any] | None = None,
    # Onboarding inventory
    parameter_sources: dict[str, Any] | None = None,
    semantic_conventions: dict[str, Any] | None = None,
    refine_suggestions: str | list[dict[str, Any]] | None = None,
    open_questions: list[dict[str, Any]] | None = None,
    calibration_hints: dict[str, Any] | None = None,
    complexity_dimensions: dict[str, Any] | None = None,
    # Refine path
    prior_design_text: str | None = None,
    # Budget
    token_budget: int = DEFAULT_PROMPT_TOKEN_BUDGET,
    manifest_registry: Any = None,
    manifest_context_budget: int = 2000,
    enable_introspect: bool = False,
    # Phase 4: Forward interfaces
    forward_manifest: Any = None,
) -> tuple[str, str, int | None]:
    """Assemble the v2 design phase system prompt and user prompt.

    Args:
        task: The SeedTask to design for.
        plan_goals: Project-level goals.
        architectural_context: Shared context from manifest.
        prior_design_summaries: Summaries of earlier design docs.
        calibration: Per-task calibration dict.
        design_max_tokens_override: Override max_output_tokens.
        dependency_designs: Designs of upstream dependency tasks.
        scaffold_existing_files: Files that already exist on disk.
        staleness_classification: Per-file staleness (current/stale).
        wave_index: This task's wave index.
        wave_metadata: Wave-level metadata (wave_count, etc).
        parameter_sources: Resolved parameter names and origins (Mottainai rule 5).
        semantic_conventions: Naming convention rules from the pipeline.
        refine_suggestions: REFINE phase suggestions.
        open_questions: Flagged uncertainties.
        calibration_hints: Per-artifact-type calibration from export.
        complexity_dimensions: Scored complexity dimensions.
        prior_design_text: Existing design doc for refine path.
        token_budget: Soft token budget for user prompt.

    Returns:
        (system_prompt, user_prompt, max_output_tokens)
    """
    is_refine = prior_design_text is not None

    # 1. Extract data per module
    identity_data = extract_identity(
        task, existing_files=scaffold_existing_files,
    )
    constraints_data = extract_constraints(task, architectural_context)
    enrichment_data = extract_enrichment(
        task,
        parameter_sources=parameter_sources,
        semantic_conventions=semantic_conventions,
    )
    prior_art_data = extract_prior_art(
        task,
        prior_design_summaries=prior_design_summaries,
        dependency_designs=dependency_designs,
        scaffold_existing_files=scaffold_existing_files,
        staleness_classification=staleness_classification,
    )
    scope_data = extract_scope(
        task,
        calibration=calibration,
        design_max_tokens_override=design_max_tokens_override,
        wave_index=wave_index,
        wave_metadata=wave_metadata,
    )
    guidance_data = extract_guidance(
        task,
        plan_goals=plan_goals,
        refine_suggestions=refine_suggestions,
        open_questions=open_questions,
        calibration_hints=calibration_hints,
        complexity_dimensions=complexity_dimensions,
    )
    manifest_data = extract_manifest_context(
        task,
        manifest_registry=manifest_registry,
        manifest_context_budget=manifest_context_budget,
        enable_introspect=enable_introspect,
    )
    contract_data = map_forward_contracts_for_task(
        task,
        forward_manifest=forward_manifest,
    )

    # 2. Map categories to extracted data
    category_data: dict[str, dict[str, Any] | None] = {
        "identity": identity_data,
        "constraints": constraints_data,
        "enrichment": enrichment_data,
        "manifest": manifest_data,
        "prior_art": prior_art_data,
        "scope": scope_data,
        "guidance": guidance_data,
        "contracts": contract_data,
    }

    # 3. Render each module
    fragments: list[PromptFragment] = []
    for mod in _MODULES:
        data = category_data.get(mod.category)
        if data is not None:
            fragment = mod.render(data)
            if fragment.text:  # Skip empty renders
                fragments.append(fragment)

    # 4. Enforce token budget
    fragments = enforce_budget(fragments, token_budget)

    # 5. Assemble user prompt
    fragment_text = "\n\n".join(f.text for f in fragments)
    user_template = _get_user_template(refine=is_refine)

    if is_refine:
        user_prompt = user_template.format(
            fragments=fragment_text,
            prior_design=prior_design_text,
        )
    else:
        user_prompt = user_template.format(fragments=fragment_text)

    # 6. System prompt
    system_prompt = _get_system_prompt(refine=is_refine)

    # 7. Max output tokens from scope
    max_tokens = scope_data.get("max_output_tokens")

    logger.info(
        "Assembled v2 design prompt for %s: %d fragments, ~%d tokens, refine=%s",
        task.task_id,
        len(fragments),
        sum(f.token_estimate for f in fragments),
        is_refine,
    )

    return system_prompt, user_prompt, max_tokens
