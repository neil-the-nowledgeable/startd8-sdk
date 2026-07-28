# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Loop recipe registry (FR-7) — thin, not a second WorkflowRegistry (NR-7)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from .models import LoopExecutor


@dataclass(frozen=True)
class LoopRecipe:
    """Declares what a loop needs and which executors can drain it (FR-7)."""

    loop_id: str
    description: str
    executors: Tuple[str, ...]
    #: Which catalog workflow_ids the sdk-workflow executor maps to (cite only).
    workflow_ids: Tuple[str, ...] = ()
    inputs: str = ""
    completion: str = ""
    steps: Tuple[str, ...] = ()


_RECIPES: Dict[str, LoopRecipe] = {}


def register_recipe(recipe: LoopRecipe) -> None:
    _RECIPES[recipe.loop_id] = recipe


def get_recipe(loop_id: str) -> LoopRecipe:
    if loop_id not in _RECIPES:
        raise KeyError(f"unknown loop_id: {loop_id!r}; known: {sorted(_RECIPES)}")
    return _RECIPES[loop_id]


def list_recipes() -> List[LoopRecipe]:
    return sorted(_RECIPES.values(), key=lambda r: r.loop_id)


def known_loop_ids() -> List[str]:
    return sorted(_RECIPES)


# -- built-in recipes ---------------------------------------------------------

register_recipe(
    LoopRecipe(
        loop_id="crp",
        description=(
            "Convergent Review Protocol: multi-round review of a plan and/or "
            "requirements doc; suggestions append to Appendix C, triage records "
            "dispositions in Appendix A/B (schema owned by "
            "docs/design/arc-review/ARCHITECTURAL_REVIEW_REQUIREMENTS.md)."
        ),
        executors=(
            LoopExecutor.AGENT_SURFACE.value,
            LoopExecutor.SDK_WORKFLOW.value,
        ),
        workflow_ids=("convergent-review", "architectural-review-log"),
        inputs="CrpReviewRequest (plan_path/requirements_path, scope, max_rounds, ...)",
        completion="max_rounds review drains done, then auto_accept (or manual) triage",
        steps=(
            "render bundle",
            "review rounds R1..Rmax (Appendix C; pending between rounds)",
            "auto_accept triage into A (default) or manual triage",
        ),
    )
)

#: FR-15 v1 priority family — any registered workflow may be enqueued; these
#: are the first-class review-adjacent targets called out in the plan.
ONE_SHOT_PRIORITY_WORKFLOWS: Tuple[str, ...] = (
    "critical-review",
    "design-polish",
    "doc-enhancement",
    "plain-language",
    "policy-analysis",
)

register_recipe(
    LoopRecipe(
        loop_id="one-shot",
        description=(
            "Single run of any catalog workflow via executor=sdk-workflow "
            "(FR-15). Priority review-adjacent family: "
            + ", ".join(ONE_SHOT_PRIORITY_WORKFLOWS)
            + "."
        ),
        executors=(LoopExecutor.SDK_WORKFLOW.value,),
        workflow_ids=ONE_SHOT_PRIORITY_WORKFLOWS,
        inputs="config matching the workflow's declared WorkflowInputs",
        completion="workflow run succeeded",
        steps=("run workflow",),
    )
)

register_recipe(
    LoopRecipe(
        loop_id="reflective-requirements",
        description=(
            "Agent-surface reflective-requirements loop (OQ-6): draft "
            "requirements + plan, reflect planning insights, harden via "
            "lessons (v0.3) + design principles (v0.3.1), then stop. "
            "Follow-on CRP is a separate queued job (typically depends_on "
            "this job_id)."
        ),
        executors=(LoopExecutor.AGENT_SURFACE.value,),
        inputs=(
            "ReflectiveRequirementsRequest (scope, requirements_path, "
            "plan_path, optional agent_template_path)"
        ),
        completion=(
            "requirements anti-skip hardened through v0.3.1 markers "
            "(plan sync soft / not consume-checked); drain-result ok"
        ),
        steps=("render instruction bundle", "agent writes docs", "confirm"),
    )
)

register_recipe(
    LoopRecipe(
        loop_id="research",
        description=(
            "Agent-surface research loop: read a RESEARCH brief, investigate "
            "(code + optional multi-agent), write FINDINGS. Follow-on CRP on "
            "findings is a separate queued job (typically depends_on)."
        ),
        executors=(LoopExecutor.AGENT_SURFACE.value,),
        inputs=(
            "ResearchRequest (scope, brief_path, findings_path, optional "
            "focus_file / agent_template_path)"
        ),
        completion="findings written; drain-result ok",
        steps=(
            "render instruction bundle",
            "agent researches + writes findings",
            "confirm",
        ),
    )
)
