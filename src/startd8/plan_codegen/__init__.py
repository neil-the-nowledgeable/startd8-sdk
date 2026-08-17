"""``$0`` det-req → det-plan/0.1 projector (REQ-29).

The "generate plan" analog of "generate backend": a deterministic, LLM-free projector that reads a
det-req and projects a ``det-plan/0.1`` document — a pure function of the requirement. The kit
(``SCHEMA_det-plan-0.1``) owns the format; this package is the cited generator, registered as a
deterministic provider like ``backend_codegen``.
"""

from __future__ import annotations

from .conformance import findings_to_sarif, validate_plan
from .models import DetPlan, GateClause, Iteration, PlanFinding
from .projector import (
    NotPlanOwedError,
    PlanDependencyCycleError,
    is_plan_owed,
    project_plan,
)
from .provider import DetPlanProjectorProvider
from .render import GENERATED_MARKER, render_plan

__all__ = [
    "DetPlan",
    "GateClause",
    "Iteration",
    "PlanFinding",
    "NotPlanOwedError",
    "PlanDependencyCycleError",
    "is_plan_owed",
    "project_plan",
    "render_plan",
    "GENERATED_MARKER",
    "validate_plan",
    "findings_to_sarif",
    "DetPlanProjectorProvider",
]
