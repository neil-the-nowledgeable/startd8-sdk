# OWNED — authored for F-304; maintained by the project.

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Literal, Optional, Type

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session, select

# Correctness Rule (1): Import TemplateResponse from the web instance, not starlette.
from .web import templates
from . import completeness
from .db import get_session
from .tables import (
    Differentiator,
    Metric,
    Outcome,
    Profile,
    ProofPoint,
    TargetRole,
    ValueProp,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wizard", tags=["wizard"])


class WizardStepConfig:
    """Configuration for a single wizard step."""

    def __init__(
        self,
        step_key: str,
        title: str,
        instance_loader: Callable[[Session, Optional[Profile], Optional[str]], Any],
        fast_fields: List[str],
        form_model: Type,
        action_url: str,
        ai_url: Optional[str] = None,
    ):
        self.step_key = step_key
        self.title = title
        self.instance_loader = instance_loader
        self.fast_fields = fast_fields
        self.form_model = form_model
        self.action_url = action_url
        self.ai_url = ai_url


# --- Instance Loaders ---
# These functions provide a new, unsaved model instance for the step's form.


def _load_profile(
    db: Session, user: Optional[Profile], entity_id: Optional[str]
) -> Optional[Profile]:
    """Load the user's profile, or create a new blank one if none exists."""
    if user:
        return user
    return Profile(
        name="",
        ownerId="default_owner",  # Placeholder
        source="wizard",
        confirmed=True,
    )


def _load_target_role(
    db: Session, user: Optional[Profile], entity_id: Optional[str]
) -> Optional[TargetRole]:
    """Create a new target role for the user."""
    if not user:
        return None
    return TargetRole(
        name="",
        ownerId=user.ownerId,
        source="wizard",
        confirmed=True,
        profile_id=user.id,
    )


def _load_proof_point(
    db: Session, user: Optional[Profile], entity_id: Optional[str]
) -> Optional[ProofPoint]:
    """Create a new proof point, associating to a target role if specified."""
    if not user:
        return None
    instance = ProofPoint(
        title="",
        ownerId=user.ownerId,
        source="wizard",
        confirmed=True,
        profile_id=user.id,
    )
    if entity_id:  # entity_id is expected to be a target_role_id here
        instance.target_role_id = entity_id
    return instance


def _load_outcome(
    db: Session, user: Optional[Profile], entity_id: Optional[str]
) -> Optional[Outcome]:
    """Create a new outcome for the user."""
    if not user:
        return None
    return Outcome(
        name="",
        ownerId=user.ownerId,
        source="wizard",
        confirmed=True,
        profile_id=user.id,
    )


def _load_metric(
    db: Session, user: Optional[Profile], entity_id: Optional[str]
) -> Optional[Metric]:
    """Create a new metric for the user."""
    if not user:
        return None
    return Metric(
        name="",
        ownerId=user.ownerId,
        source="wizard",
        confirmed=True,
        profile_id=user.id,
    )


def _load_differentiator(
    db: Session, user: Optional[Profile], entity_id: Optional[str]
) -> Optional[Differentiator]:
    """Create a new differentiator for the user."""
    if not user:
        return None
    return Differentiator(
        name="",
        ownerId=user.ownerId,
        source="wizard",
        confirmed=True,
        profile_id=user.id,
    )


def _load_value_prop(
    db: Session, user: Optional[Profile], entity_id: Optional[str]
) -> Optional[ValueProp]:
    """Create a new value proposition for the user."""
    if not user:
        return None
    return ValueProp(
        headline="",
        ownerId=user.ownerId,
        source="wizard",
        confirmed=True,
        profile_id=user.id,
    )


# --- Step Registry ---

STEPS: Dict[str, WizardStepConfig] = {
    "profile_edit": WizardStepConfig(
        step_key="profile_edit",
        title="Create Your Profile",
        instance_loader=_load_profile,
        fast_fields=["name", "title", "company"],
        form_model=Profile,
        action_url="/profile/",
        ai_url=None,  # No AI drafting for the core profile
    ),
    "targetrole_create": WizardStepConfig(
        step_key="targetrole_create",
        title="Add a Target Role",
        instance_loader=_load_target_role,
        fast_fields=["name", "industry"],
        form_model=TargetRole,
        action_url="/targetrole/",
        ai_url="/ai/targetrole/draft",
    ),
    "proofpoint_create": WizardStepConfig(
        step_key="proofpoint_create",
        title="Add a Proof Point",
        instance_loader=_load_proof_point,
        fast_fields=["title", "description"],
        form_model=ProofPoint,
        action_url="/proofpoint/",
        ai_url="/ai/proofpoint/draft",
    ),
    "outcome_create": WizardStepConfig(
        step_key="outcome_create",
        title="Define an Outcome",
        instance_loader=_load_outcome,
        fast_fields=["name"],
        form_model=Outcome,
        action_url="/outcome/",
        ai_url="/ai/outcome/draft",
    ),
    "metric_create": WizardStepConfig(
        step_key="metric_create",
        title="Define a Metric",
        instance_loader=_load_metric,
        fast_fields=["name", "value"],
        form_model=Metric,
        action_url="/metric/",
        ai_url="/ai/metric/draft",
    ),
    "differentiator_create": WizardStepConfig(
        step_key="differentiator_create",
        title="Define a Differentiator",
        instance_loader=_load_differentiator,
        fast_fields=["name"],
        form_model=Differentiator,
        action_url="/differentiator/",
        ai_url="/ai/differentiator/draft",
    ),
    "valueprop_create": WizardStepConfig(
        step_key="valueprop_create",
        title="Craft a Value Proposition",
        instance_loader=_load_value_prop,
        fast_fields=["headline"],
        form_model=ValueProp,
        action_url="/valueprop/",
        ai_url="/ai/valueprop/draft",
    ),
}


def _get_current_user(db: Session) -> Optional[Profile]:
    """Fetch the current user's profile. Hardcoded to first profile for now."""
    return db.exec(select(Profile)).first()


@router.get("/", name="wizard_home")
async def wizard_step(
    request: Request,
    mode: Literal["fast", "deep"] = "fast",
    db: Session = Depends(get_session),
):
    """
    Main wizard endpoint: stateless orchestration.
    Determines the next step via completeness engine and renders the generic step template.
    """
    user = _get_current_user(db)

    # The completeness engine is the "brain" that decides what's next.
    try:
        # Returns (step_key, optional_entity_id) or (None, None) if complete.
        step_key, entity_id = completeness.get_next_step_key(db, user)
    except Exception as exc:
        # Fail safe to the "done" page if the completeness engine errors.
        logger.error(f"Completeness engine failed: {exc}", exc_info=True)
        step_key = None

    if not step_key:
        return templates.TemplateResponse(
            request, "wizard/done.html", {"request": request, "profile": user}
        )

    step_config = STEPS.get(step_key)
    if not step_config:
        logger.error(
            f"Wizard received unknown step key from completeness engine: '{step_key}'"
        )
        return templates.TemplateResponse(
            request, "wizard/done.html", {"request": request, "profile": user}
        )

    instance = step_config.instance_loader(db, user, entity_id)
    if instance is None:
        logger.error(
            f"Failed to load instance for step '{step_key}' with user='{user.id if user else None}' and entity_id='{entity_id}'"
        )
        return templates.TemplateResponse(
            request, "wizard/done.html", {"request": request, "profile": user}
        )

    all_fields = list(step_config.form_model.model_fields.keys())
    fields_to_show = step_config.fast_fields if mode == "fast" else all_fields

    context = {
        "request": request,
        "profile": user,
        "step_title": step_config.title,
        "step_key": step_key,
        "instance": instance,
        "form_model": step_config.form_model,
        "action_url": step_config.action_url,
        "mode": mode,
        "fields_to_show": fields_to_show,
        "has_ai_key": bool(os.getenv("OPENAI_API_KEY")),
        "ai_action_url": step_config.ai_url,
    }
    return templates.TemplateResponse(request, "wizard/step.html", context)