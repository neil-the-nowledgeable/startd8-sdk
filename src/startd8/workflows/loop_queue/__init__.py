# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Workflow Loop Queue (WLQ) experimental public API (FR-19).

WLQ is a durable, vendor-neutral queue for workflow/loop jobs. It is a sibling
of the prompt ``JobQueue`` and is not the agentic tool-use loop.

**Experimental pre-1.0.** Import from this package; CLI ops live under
``startd8 wloop``. VASI contract:
``docs/design/cursor-workflow-loop/VENDOR_AGENT_SURFACE_INTERFACE.md``.

Quick start::

    from startd8.workflows.loop_queue import (
        LoopQueueConfig,
        WorkflowLoopJob,
        WorkflowLoopQueue,
    )

    queue = WorkflowLoopQueue(
        LoopQueueConfig(queue_root=".startd8/workflow-loop-queue")
    )
    queue.enqueue(WorkflowLoopJob.model_validate({...}))
    handoff_or_job = queue.run_next()
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
    ReflectiveRequirementsRequest,
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
    "ReflectiveRequirementsRequest",
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
