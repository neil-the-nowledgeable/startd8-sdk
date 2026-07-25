# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Workflow Loop Queue (WLQ) data models — job envelope, CRP intent, VASI hand-off.

Implements FR-1 / FR-1a / FR-3 of
``docs/design/cursor-workflow-loop/CURSOR_WORKFLOW_LOOP_REQUIREMENTS.md`` and the
Drain Hand-off / status write-back schemas of
``docs/design/cursor-workflow-loop/VENDOR_AGENT_SURFACE_INTERFACE.md`` (VASI 0.1).

Experimental pre-1.0 API (FR-19). Import path: ``startd8.workflows.loop_queue``.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.1.0"
VASI_VERSION = "0.1.0"

#: Filename suffix distinguishing WLQ jobs from prompt JobQueue jobs (FR-1, NR-2).
JOB_FILE_SUFFIX = "_startd8_wloop.json"

# Patterns that mark text as an agent-surface CRP bundle / mustache template —
# both are incompatible with the SDK `review_template` str.format contract
# (spike: KeyError 'n'; NR-8 / FR-9 / FR-20.3).
_AGENT_BUNDLE_MARKERS = re.compile(r"\{\{|\bR\{n\}|\{round\}")


class LoopQueueError(Exception):
    """Base error for WLQ operations (CLI exit code 1)."""


class LoopQueueValidationError(LoopQueueError):
    """Fail-closed validation error at enqueue or triage (CLI exit code 2)."""


class LoopQueueBlockedError(LoopQueueError):
    """Retryable blocked condition, e.g. artifact vanished (CLI exit code 3)."""


class LoopJobStatus(str, Enum):
    """Durable on-disk job status (FR-1 / FR-3)."""

    PENDING = "pending"
    PROCESSING = "processing"
    AWAITING_TRIAGE = "awaiting_triage"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class LoopExecutor(str, Enum):
    """Which side executes a drained job (FR-1)."""

    AGENT_SURFACE = "agent-surface"
    SDK_WORKFLOW = "sdk-workflow"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def looks_like_agent_bundle(text: str) -> bool:
    """True when *text* carries agent-surface bundle / mustache markers.

    Such text must never be fed to the SDK ``review_template`` ``str.format``
    seam (NR-8) — the spike proved it fails with ``KeyError: 'n'``.
    """
    return bool(_AGENT_BUNDLE_MARKERS.search(text))


class CrpReviewRequest(BaseModel):
    """Canonical typed CRP review intent (FR-1a).

    One instance feeds every executor / renderer: the agent-surface bundle
    renderer (FR-20) and, in Increment 1.1, the sdk-workflow mapping (FR-9).
    Unknown keys fail closed.
    """

    model_config = ConfigDict(extra="forbid")

    plan_path: Optional[str] = None
    requirements_path: Optional[str] = None
    scope: str
    max_rounds: int = Field(default=2, ge=1)
    substantially_addressed_threshold: int = Field(default=3, ge=1)
    max_suggestions: int = Field(default=10, ge=1, le=25)
    focus_file: Optional[str] = None
    agents: Optional[List[str]] = None
    enable_triage: bool = False
    enable_apply: bool = False
    #: SDK-executor-only ``str.format`` template customization. Agent-surface
    #: jobs reject this field; it is never populated from ``agent_template_path``.
    review_template: Optional[str] = None
    #: VASI declaration for an unlisted surface (FR-1 / FR-22). Known surfaces
    #: need not repeat the published contract.
    surface_conformance: Optional[Dict[str, Any]] = None
    #: Optional project {{slot}} template override for the agent-surface
    #: renderer (FR-20.2). Alias ``cursor_template_path`` accepted (FR-1a).
    agent_template_path: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def _accept_cursor_template_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "cursor_template_path" in data:
            data = dict(data)
            alias = data.pop("cursor_template_path")
            data.setdefault("agent_template_path", alias)
        return data

    @model_validator(mode="after")
    def _require_at_least_one_source(self) -> "CrpReviewRequest":
        if not self.plan_path and not self.requirements_path:
            raise ValueError(
                "CrpReviewRequest requires plan_path and/or requirements_path"
            )
        return self

    @property
    def source_paths(self) -> List[Path]:
        """Review target documents, plan first (dual-doc order)."""
        return [Path(p) for p in (self.plan_path, self.requirements_path) if p]

    @property
    def dual_doc(self) -> bool:
        return bool(self.plan_path and self.requirements_path)

    def content_hash(self) -> str:
        """Stable hash of the intent — the FR-14 bundle-cache key component."""
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()


class RoundRecord(BaseModel):
    """One completed review round recorded on the job (FR-8d)."""

    model_config = ConfigDict(extra="allow")

    round_number: int
    suggestion_counts: Dict[str, int] = Field(default_factory=dict)
    paths_written: List[str] = Field(default_factory=list)
    completed_at: str = Field(default_factory=_utc_now_iso)


class WorkflowLoopJob(BaseModel):
    """Versioned WLQ job envelope (FR-1)."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["0.1.0"] = "0.1.0"
    job_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    loop_id: str = Field(min_length=1)
    executor: LoopExecutor
    surface_id: Optional[str] = None
    workflow_id: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    status: LoopJobStatus = LoopJobStatus.PENDING
    status_reason: Optional[str] = None
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)
    depends_on: List[str] = Field(default_factory=list)
    budget: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    #: Completed round history (FR-8d / FR-14).
    rounds: List[RoundRecord] = Field(default_factory=list)
    #: Durable artifact pointers (rendered bundle, hand-off path, ...).
    artifacts: Dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _accept_cursor_agent_alias(cls, data: Any) -> Any:
        """FR-1: ``executor=cursor-agent`` is a deprecated synonym."""
        if isinstance(data, dict) and data.get("executor") == "cursor-agent":
            data = dict(data)
            data["executor"] = LoopExecutor.AGENT_SURFACE.value
            if not data.get("surface_id"):
                data["surface_id"] = "cursor"
        return data

    @model_validator(mode="after")
    def _validate_executor_fields(self) -> "WorkflowLoopJob":
        if self.executor is LoopExecutor.AGENT_SURFACE and not self.surface_id:
            raise ValueError("surface_id is required when executor=agent-surface")
        if self.executor is LoopExecutor.SDK_WORKFLOW and not self.workflow_id:
            raise ValueError("workflow_id is required when executor=sdk-workflow")
        return self

    def crp_request(self) -> CrpReviewRequest:
        """Parse ``config`` as the canonical CRP intent (FR-1a). Fail-closed."""
        if self.loop_id != "crp":
            raise LoopQueueValidationError(
                f"job {self.job_id!r} has loop_id={self.loop_id!r}, not 'crp'"
            )
        try:
            return CrpReviewRequest.model_validate(self.config)
        except Exception as e:  # pydantic ValidationError → typed WLQ error
            raise LoopQueueValidationError(
                f"invalid CrpReviewRequest for job {self.job_id!r}: {e}"
            ) from e

    def rounds_completed(self) -> int:
        return len(self.rounds)

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()


class LoopQueueConfig(BaseModel):
    """WLQ configuration (FR-2; OQ-7 lean: dedicated folder)."""

    model_config = ConfigDict(extra="forbid")

    queue_root: Path = Path(".startd8/workflow-loop-queue")
    max_concurrent_jobs: int = 1
    #: Default agent-surface CRP bundle renderer script (FR-20.2). ``None``
    #: falls back to $STARTD8_CRP_RENDERER, then the cap-dev-pipe location.
    renderer_script: Optional[Path] = None


class DrainHandoff(BaseModel):
    """VASI §5 Drain Hand-off — written on ``run-next`` for agent-surface jobs."""

    model_config = ConfigDict(extra="forbid")

    vasi_version: Literal["0.1.0"] = "0.1.0"
    job_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    surface_id: str = Field(min_length=1)
    loop_id: str = Field(min_length=1)
    round_number: int
    bundle_path: str
    source_paths: List[str]
    success_criteria: Dict[str, bool] = Field(
        default_factory=lambda: {
            "append_review_round": True,
            "init_appendix_if_missing": True,
            "no_triage": True,
            "dual_doc_coverage_matrix": True,
        }
    )
    status_writeback_path: str
    budget_warning: Optional[str] = None


class DrainResult(BaseModel):
    """VASI §5 status write-back — written by the surface's agent after drain."""

    model_config = ConfigDict(extra="forbid")

    vasi_version: Literal["0.1.0"] = "0.1.0"
    job_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    surface_id: str = Field(min_length=1)
    ok: bool
    round_number: int
    suggestion_counts: Dict[str, int] = Field(default_factory=dict)
    paths_written: List[str] = Field(default_factory=list)
    error: Optional[str] = None

    @model_validator(mode="after")
    def _validate_counts(self) -> "DrainResult":
        invalid = {
            key: count
            for key, count in self.suggestion_counts.items()
            if key not in {"S", "F"} or count < 0
        }
        if invalid:
            raise ValueError(
                f"suggestion_counts keys must be S/F with non-negative values: {invalid}"
            )
        return self


class TriageDecision(BaseModel):
    """One CRP triage disposition (FR-13). ACCEPT→Appendix A, REJECT→Appendix B."""

    model_config = ConfigDict(extra="forbid")

    id: str
    decision: str  # "ACCEPT" | "REJECT"
    summary: str
    rationale: str
    source: str = ""

    @model_validator(mode="after")
    def _validate_decision(self) -> "TriageDecision":
        if self.decision not in ("ACCEPT", "REJECT"):
            raise ValueError(
                f"decision must be ACCEPT or REJECT, got {self.decision!r}"
            )
        return self
