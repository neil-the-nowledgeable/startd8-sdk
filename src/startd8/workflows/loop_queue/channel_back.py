# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Channel-back: implement-tick withdrawal → reflective-requirements enqueue.

When an implement/executor tick **withdraws** because the design premise is
invalid (distinct from a patch-hard / tests-red implementation failure), the
withdrawal verdict must feed *back* into design — not die as a dishonest
terminal close.

This module is the missing enqueue-caller on the already-tested
``reflective-requirements`` wire (``config.scope`` is the pipe; the drained
bundle is the new prompt). It is intentionally ~one function: no new lifecycle
state, no new engine.

Acceptance exercise: the compact-declared-base remand
(``analysis/NEXT_STEPS_channel-back-reflective-requirements_2026-07-27.md``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Union

from .models import (
    LoopExecutor,
    LoopQueueValidationError,
    WorkflowLoopJob,
)
from .queue import WorkflowLoopQueue

PathLike = Union[str, Path]

#: Causes that channel back into design. Anything else is an implementation
#: failure and must NOT silently become a reflective-requirements job.
_CHANNEL_BACK_CAUSES = frozenset({"design_premise_invalid"})


class WithdrawalCause(str, Enum):
    """Why the implement tick withdrew.

    Only ``DESIGN_PREMISE_INVALID`` channels back into
    ``reflective-requirements``. Patch-hard / tests-red stay local to the
    implement tick (retry / escalate / leave as implementing).
    """

    DESIGN_PREMISE_INVALID = "design_premise_invalid"
    #: Implementation failure — NOT a channel-back trigger. Named so callers
    #: can fail closed rather than silently remap.
    IMPLEMENTATION_FAILURE = "implementation_failure"


@dataclass(frozen=True)
class WithdrawalVerdict:
    """The implement tick's withdrawal: cause + free-form corrected premise.

    ``scope`` becomes ``ReflectiveRequirementsRequest.scope`` — the drained
    bundle opens with this text in the ``{{scope}}`` slot.
    """

    cause: WithdrawalCause
    scope: str
    finding_id: Optional[str] = None


def _slug(text: str, *, max_len: int = 48) -> str:
    """Stable job-id fragment from a finding id or path stem."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-._")
    return (cleaned or "anon")[:max_len].rstrip("-._")


def enqueue_withdrawal_remand(
    queue: WorkflowLoopQueue,
    verdict: WithdrawalVerdict,
    *,
    requirements_path: PathLike,
    plan_path: PathLike,
    job_id: Optional[str] = None,
    surface_id: str = "cursor",
) -> WorkflowLoopJob:
    """Enqueue a ``reflective-requirements`` job from an implement-tick withdrawal.

    **Trigger:** ``verdict.cause == DESIGN_PREMISE_INVALID`` (design premise
    factually wrong / unsupported). Other causes raise
    ``LoopQueueValidationError`` — they are not channel-back events.

    **Action:** build ``config`` from the verdict (``scope = verdict.scope``,
    paths = the finding's design dir) and call ``queue.enqueue``.

    Returns the durable pending job. Does **not** drain; does **not** move
    remediation lifecycle state — redesign is out-of-band, lifecycle re-entry
    is the natural next audit / ``accept`` path.
    """
    if verdict.cause.value not in _CHANNEL_BACK_CAUSES:
        raise LoopQueueValidationError(
            f"withdrawal cause {verdict.cause.value!r} does not channel back "
            f"(only {_CHANNEL_BACK_CAUSES!r} enqueue a reflective-requirements "
            "remand; implementation failures stay on the implement tick)"
        )
    scope = (verdict.scope or "").strip()
    if not scope:
        raise LoopQueueValidationError(
            "withdrawal verdict scope is empty — the corrected premise is the "
            "pipe into reflective-requirements; refuse to enqueue a blank prompt"
        )

    reqs = str(Path(requirements_path))
    plan = str(Path(plan_path))
    if job_id is None:
        stem = _slug(verdict.finding_id or Path(reqs).parent.name)
        job_id = f"refl-remand-{stem}"

    job = WorkflowLoopJob(
        job_id=job_id,
        loop_id="reflective-requirements",
        executor=LoopExecutor.AGENT_SURFACE,
        surface_id=surface_id,
        config={
            "scope": scope,
            "requirements_path": reqs,
            "plan_path": plan,
        },
        metadata={
            "channel_back": True,
            "withdrawal_cause": verdict.cause.value,
            "finding_id": verdict.finding_id or "",
            "enqueued_by": "enqueue_withdrawal_remand",
        },
    )
    return queue.enqueue(job)
