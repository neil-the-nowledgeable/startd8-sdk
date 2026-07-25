# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Workflow Loop Queue (WLQ) experimental public API (FR-19).

WLQ is a durable, vendor-neutral queue for workflow/loop jobs. It is a sibling
of the prompt ``JobQueue`` and is not the agentic tool-use loop.
"""

from .models import (
    JOB_FILE_SUFFIX,
    SCHEMA_VERSION,
    VASI_VERSION,
    CrpReviewRequest,
    DrainHandoff,
    DrainResult,
    LoopExecutor,
    LoopJobStatus,
    LoopQueueBlockedError,
    LoopQueueConfig,
    LoopQueueError,
    LoopQueueValidationError,
    RoundRecord,
    TriageDecision,
    WorkflowLoopJob,
)
from .queue import WorkflowLoopQueue
from .recipes import (
    ONE_SHOT_PRIORITY_WORKFLOWS,
    LoopRecipe,
    get_recipe,
    list_recipes,
)
from .sdk_executor import (
    map_crp_request_to_workflow_config,
    resolve_crp_workflow_id,
    run_sdk_crp,
)
from .surfaces import KnownSurface, list_surfaces

__all__ = [
    "JOB_FILE_SUFFIX",
    "SCHEMA_VERSION",
    "VASI_VERSION",
    "CrpReviewRequest",
    "DrainHandoff",
    "DrainResult",
    "KnownSurface",
    "LoopExecutor",
    "LoopJobStatus",
    "LoopQueueBlockedError",
    "LoopQueueConfig",
    "LoopQueueError",
    "LoopQueueValidationError",
    "LoopRecipe",
    "ONE_SHOT_PRIORITY_WORKFLOWS",
    "RoundRecord",
    "TriageDecision",
    "WorkflowLoopJob",
    "WorkflowLoopQueue",
    "get_recipe",
    "list_recipes",
    "list_surfaces",
    "map_crp_request_to_workflow_config",
    "resolve_crp_workflow_id",
    "run_sdk_crp",
]
