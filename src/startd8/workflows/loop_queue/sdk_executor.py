# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""CRP ``sdk-workflow`` executor adapter (FR-9 / Increment 1.1).

Maps a canonical :class:`CrpReviewRequest` onto
``architectural-review-log`` (single-doc) or ``convergent-review`` (dual-doc)
and drains via ``WorkflowRegistry.run_workflow``. Agent-surface review bundles
are never routed through the SDK ``review_template`` ``str.format`` seam (NR-8).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ...agents import BaseAgent
from ...logging_config import get_logger
from ..base import ProgressCallback
from ..models import WorkflowResult
from ..registry import WorkflowRegistry
from .models import (
    CrpReviewRequest,
    LoopQueueValidationError,
    looks_like_agent_bundle,
)

logger = get_logger(__name__)

WORKFLOW_SINGLE = "architectural-review-log"
WORKFLOW_DUAL = "convergent-review"
_SUPPORTED = frozenset({WORKFLOW_SINGLE, WORKFLOW_DUAL})


def resolve_crp_workflow_id(
    request: CrpReviewRequest,
    preferred: Optional[str] = None,
) -> str:
    """Choose the catalog workflow for a CRP request (FR-9)."""
    if preferred:
        wid = preferred.lower()
        if wid not in _SUPPORTED:
            raise LoopQueueValidationError(
                f"CRP sdk-workflow supports {_SUPPORTED}, got {preferred!r}"
            )
        if wid == WORKFLOW_DUAL and not request.dual_doc:
            raise LoopQueueValidationError(
                "convergent-review requires both plan_path and requirements_path"
            )
        return wid
    return WORKFLOW_DUAL if request.dual_doc else WORKFLOW_SINGLE


def map_crp_request_to_workflow_config(
    request: CrpReviewRequest,
    workflow_id: str,
) -> Dict[str, Any]:
    """Map typed CRP intent → catalog workflow config (FR-1a / FR-9).

    Never copies ``agent_template_path`` into ``review_template``. Optional
    SDK-native ``review_template`` is allowed only under the ``str.format``
    contract and is rejected when it looks like an agent-surface bundle.
    """
    wid = resolve_crp_workflow_id(request, workflow_id)
    if request.review_template and looks_like_agent_bundle(request.review_template):
        raise LoopQueueValidationError(
            "SDK review_template contains agent-surface/mustache markers; "
            "do not route an FR-20 bundle through Python str.format (NR-8)"
        )

    if wid == WORKFLOW_DUAL:
        assert request.plan_path and request.requirements_path
        config: Dict[str, Any] = {
            "plan_path": str(Path(request.plan_path).expanduser().resolve()),
            "requirements_path": str(
                Path(request.requirements_path).expanduser().resolve()
            ),
            "enable_triage": request.enable_triage,
            "enable_apply": request.enable_apply,
        }
    else:
        # Single-doc primary target; dual-doc may still use architectural-review-log
        # with feature_requirements for plan+requirements context (FR-9).
        if request.plan_path:
            document_path: str = request.plan_path
            feature = [request.requirements_path] if request.requirements_path else None
        elif request.requirements_path:
            document_path = request.requirements_path
            feature = None
        else:
            raise LoopQueueValidationError(
                "architectural-review-log mapping requires plan_path or requirements_path"
            )
        config = {
            "document_path": str(Path(document_path).expanduser().resolve()),
            "scope": request.scope,
            "max_suggestions": request.max_suggestions,
            "substantially_addressed_threshold": (
                request.substantially_addressed_threshold
            ),
            "enable_triage": request.enable_triage,
            "enable_apply": request.enable_apply,
            "init_if_missing": True,
        }
        if feature:
            config["feature_requirements"] = [
                str(Path(p).expanduser().resolve()) for p in feature if p
            ]
        if request.review_template is not None:
            config["review_template"] = request.review_template

    if request.agents:
        config["agents"] = list(request.agents)
    if request.focus_file:
        # SDK workflow has no focus_file input; surface as context_files.
        config["context_files"] = [str(Path(request.focus_file).expanduser().resolve())]

    # Explicitly never forward agent-surface template paths.
    config.pop("agent_template_path", None)
    config.pop("cursor_template_path", None)
    return config


def run_sdk_crp(
    request: CrpReviewRequest,
    workflow_id: str,
    *,
    agents: Optional[List[BaseAgent]] = None,
    on_progress: Optional[ProgressCallback] = None,
    dry_run: bool = False,
) -> Tuple[str, Dict[str, Any], WorkflowResult]:
    """Drain CRP via the catalog workflow. Returns (workflow_id, config, result)."""
    wid = resolve_crp_workflow_id(request, workflow_id)
    config = map_crp_request_to_workflow_config(request, wid)
    WorkflowRegistry.discover()
    logger.info(
        "WLQ sdk-workflow drain workflow_id=%s dual_doc=%s dry_run=%s",
        wid,
        request.dual_doc,
        dry_run,
    )
    result = WorkflowRegistry.run_workflow(
        wid,
        config=config,
        agents=agents,
        on_progress=on_progress,
        dry_run=dry_run,
    )
    return wid, config, result
