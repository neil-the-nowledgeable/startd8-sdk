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

#: REQ-02 (contextcore Workflow Dry-Run) — the GUARDED MIRROR of contextcore's ``WouldAct`` vocabulary.
#: The AUTHORITATIVE enum lives in contextcore (``contracts.dry_run.WouldAct``); startd8 must NOT import
#: contextcore (mirroring the ``admit_from_wlq`` "read WLQ JSON, don't import" seam). This tuple is the
#: startd8-side mirror of the ``would_act`` values that ride in ``WorkflowLoopJob.dry_run_trace`` verdicts.
#: ``tests/.../test_dry_run_parity.py`` asserts this == contextcore's ``WOULD_ACT_VALUES`` (fails on drift in
#: EITHER direction) — the single-source-vocabulary triad guard.
DRY_RUN_WOULD_ACT_VALUES: tuple[str, ...] = ("yes", "no", "not-mine")

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


def _parse_utc(iso: str) -> datetime:
    value = datetime.fromisoformat(iso)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def looks_like_agent_bundle(text: str) -> bool:
    """True when *text* carries agent-surface bundle / mustache markers.

    Such text must never be fed to the SDK ``review_template`` ``str.format``
    seam (NR-8) — the spike proved it fails with ``KeyError: 'n'``.
    """
    return bool(_AGENT_BUNDLE_MARKERS.search(text))


class AssignedReviewer(BaseModel):
    """Per-drain reviewer assignment for agent-surface CRP (blind_rotate roster)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["current", "blind_rotate"]
    model: Optional[str] = None
    roster_index: Optional[int] = None
    roster: List[str] = Field(default_factory=list)
    #: FR-23 tier that expanded the roster, when applicable.
    reviewer_tier: Optional[Literal["flagship", "mid_tier"]] = None


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
    #: Agent-surface CRP: ``current`` (default chat) or ``blind_rotate`` (Task
    #: subagent with ``reviewer_roster[(round-1) % len]``). Distinct from
    #: ``agents`` (sdk-workflow provider specs).
    reviewer_mode: Literal["current", "blind_rotate"] = "current"
    #: Cursor Task model slugs for ``blind_rotate`` (e.g. claude-opus-…, gpt-…).
    #: When omitted and ``reviewer_tier`` is set, expanded from FR-23 presets.
    reviewer_roster: Optional[List[str]] = None
    #: FR-23: ``flagship`` or ``mid_tier`` → cross-vendor Anthropic/OpenAI/Google
    #: Cursor Task roster. Coerces ``blind_rotate``; explicit roster overrides.
    reviewer_tier: Optional[Literal["flagship", "mid_tier"]] = None
    #: After all ``max_rounds`` review drains: ``auto_accept`` ACCEPTs every
    #: untriaged Appendix C id into A and completes the job; ``manual`` leaves
    #: ``awaiting_triage`` for an explicit ``triage`` call.
    triage_policy: Literal["auto_accept", "manual"] = "auto_accept"

    @model_validator(mode="before")
    @classmethod
    def _accept_cursor_template_alias(cls, data: Any) -> Any:
        if isinstance(data, dict) and "cursor_template_path" in data:
            data = dict(data)
            alias = data.pop("cursor_template_path")
            data.setdefault("agent_template_path", alias)
        return data

    @model_validator(mode="before")
    @classmethod
    def _coerce_roster_or_tier_to_blind_rotate(cls, data: Any) -> Any:
        """Non-empty roster or reviewer_tier with omitted mode → ``blind_rotate``."""
        if isinstance(data, dict):
            data = dict(data)
            roster = data.get("reviewer_roster")
            tier = data.get("reviewer_tier")
            if (roster or tier) and "reviewer_mode" not in data:
                data["reviewer_mode"] = "blind_rotate"
        return data

    @model_validator(mode="after")
    def _require_at_least_one_source(self) -> "CrpReviewRequest":
        if not self.plan_path and not self.requirements_path:
            raise ValueError(
                "CrpReviewRequest requires plan_path and/or requirements_path"
            )
        return self

    @model_validator(mode="after")
    def _validate_reviewer_roster(self) -> "CrpReviewRequest":
        from .reviewer_presets import resolve_reviewer_tier_roster

        if self.reviewer_tier and self.reviewer_mode == "current":
            raise ValueError(
                "reviewer_tier requires reviewer_mode=blind_rotate "
                "(omit reviewer_mode to coerce)"
            )

        roster = self.reviewer_roster
        if self.reviewer_tier and not roster:
            self.reviewer_roster = resolve_reviewer_tier_roster(self.reviewer_tier)
            roster = self.reviewer_roster

        if self.reviewer_mode == "blind_rotate":
            if not roster:
                raise ValueError(
                    "reviewer_mode=blind_rotate requires a non-empty "
                    "reviewer_roster or reviewer_tier=flagship|mid_tier"
                )
            cleaned = [entry.strip() for entry in roster if entry and str(entry).strip()]
            if len(cleaned) != len(roster) or not cleaned:
                raise ValueError(
                    "reviewer_roster entries must be non-empty Cursor Task model slugs"
                )
            self.reviewer_roster = cleaned
        elif roster is not None:
            cleaned = [entry.strip() for entry in roster if entry and str(entry).strip()]
            self.reviewer_roster = cleaned or None
        return self

    @property
    def source_paths(self) -> List[Path]:
        """Review target documents, plan first (dual-doc order)."""
        return [Path(p) for p in (self.plan_path, self.requirements_path) if p]

    @property
    def dual_doc(self) -> bool:
        return bool(self.plan_path and self.requirements_path)

    def assigned_reviewer_for_round(self, round_number: int) -> AssignedReviewer:
        """Resolve the VASI assigned_reviewer for drain round ``round_number``."""
        if round_number < 1:
            raise ValueError(f"round_number must be >= 1, got {round_number}")
        if self.reviewer_mode != "blind_rotate" or not self.reviewer_roster:
            return AssignedReviewer(mode="current", model=None, roster_index=None, roster=[])
        index = (round_number - 1) % len(self.reviewer_roster)
        return AssignedReviewer(
            mode="blind_rotate",
            model=self.reviewer_roster[index],
            roster_index=index,
            roster=list(self.reviewer_roster),
            reviewer_tier=self.reviewer_tier,
        )

    def content_hash(self) -> str:
        """Stable hash of the intent — the FR-14 bundle-cache key component."""
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()


class ReflectiveRequirementsRequest(BaseModel):
    """Agent-surface reflective-requirements intent (OQ-6 settled: first-class recipe).

    Paths are write targets (may be created on drain). Parent directories must
    exist at enqueue. Unknown keys fail closed.
    """

    model_config = ConfigDict(extra="forbid")

    scope: str
    requirements_path: str
    plan_path: str
    agent_template_path: Optional[str] = None
    surface_conformance: Optional[Dict[str, Any]] = None

    @property
    def source_paths(self) -> List[Path]:
        return [Path(self.requirements_path), Path(self.plan_path)]

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode("utf-8")
        ).hexdigest()


class ResearchRequest(BaseModel):
    """Agent-surface research-job intent (brief → findings).

    ``brief_path`` must exist at enqueue (the investigation brief).
    ``findings_path`` is the write target (may be created on drain); its parent
    directory must exist. Unknown keys fail closed.
    """

    model_config = ConfigDict(extra="forbid")

    scope: str
    brief_path: str
    findings_path: str
    agent_template_path: Optional[str] = None
    surface_conformance: Optional[Dict[str, Any]] = None
    #: Optional absolute path to a focus file the researcher should prioritize.
    focus_file: Optional[str] = None

    @property
    def source_paths(self) -> List[Path]:
        """Paths the drain must leave as non-empty markdown (findings only)."""
        return [Path(self.findings_path)]

    @property
    def brief(self) -> Path:
        return Path(self.brief_path)

    def content_hash(self) -> str:
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

    # REQ-02 (contextcore Workflow Dry-Run): bumped 0.1.0 → 0.1.1 to carry the ADDITIVE dry_run fields below.
    # Both are accepted so a pre-existing "0.1.0" job file still validates under ``extra="forbid"`` (the new
    # fields default, so old jobs are unaffected — NR-4). A "0.1.0" file simply lacks dry_run (defaults False).
    schema_version: Literal["0.1.0", "0.1.1"] = "0.1.1"
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
    #: OQ-5: UTC ISO expiry while ``status=processing``; cleared on leave.
    lease_expires_at: Optional[str] = None
    #: REQ-02 FR-1: the propagating dry-run flag. When True this is a trace/probe job — the wloop persist
    #: chokepoint (``LoopQueueStorage.save_job``) describes the would-be enqueue/claim/complete WITHOUT
    #: writing job-state. Additive, default-False → ZERO effect on live jobs (NR-4). The AUTHORITATIVE schema
    #: for the verdicts this flag produces lives in contextcore (``contracts.dry_run``); startd8 carries only
    #: this plain flag + a JSON-shaped trace (no contextcore import) — the single-source-vocabulary triad
    #: seam, held in sync by ``tests/.../test_dry_run_parity.py`` (OQ-1). See ``dry_run_would_act_values``.
    dry_run: bool = False
    #: REQ-02 FR-3a: the ordered carried trace — a list of JSON-shaped ``DryRunVerdict`` dicts (contextcore's
    #: ``DryRunVerdict.to_dict()`` shape), accumulated as the job flows so it arrives at the terminus with the
    #: full path. Kept as untyped dicts here (no contextcore import); the parity test guards the shape.
    dry_run_trace: List[Dict[str, Any]] = Field(default_factory=list)

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

    def reflective_request(self) -> ReflectiveRequirementsRequest:
        """Parse ``config`` as reflective-requirements intent (OQ-6)."""
        if self.loop_id != "reflective-requirements":
            raise LoopQueueValidationError(
                f"job {self.job_id!r} has loop_id={self.loop_id!r}, "
                "not 'reflective-requirements'"
            )
        try:
            return ReflectiveRequirementsRequest.model_validate(self.config)
        except Exception as e:
            raise LoopQueueValidationError(
                f"invalid ReflectiveRequirementsRequest for job {self.job_id!r}: {e}"
            ) from e

    def research_request(self) -> ResearchRequest:
        """Parse ``config`` as research-job intent (brief → findings)."""
        if self.loop_id != "research":
            raise LoopQueueValidationError(
                f"job {self.job_id!r} has loop_id={self.loop_id!r}, not 'research'"
            )
        try:
            return ResearchRequest.model_validate(self.config)
        except Exception as e:
            raise LoopQueueValidationError(
                f"invalid ResearchRequest for job {self.job_id!r}: {e}"
            ) from e

    def rounds_completed(self) -> int:
        return len(self.rounds)

    def touch(self) -> None:
        self.updated_at = _utc_now_iso()

    def lease_expired(self, *, now: Optional[datetime] = None) -> bool:
        if not self.lease_expires_at:
            return False
        current = now or datetime.now(timezone.utc)
        return _parse_utc(self.lease_expires_at) <= current


class LoopQueueConfig(BaseModel):
    """WLQ configuration (FR-2; OQ-7 settled: dedicated folder)."""

    model_config = ConfigDict(extra="forbid")

    queue_root: Path = Path(".startd8/workflow-loop-queue")
    max_concurrent_jobs: int = 1
    #: Default agent-surface CRP bundle renderer script (FR-20.2). ``None``
    #: falls back to $STARTD8_CRP_RENDERER, then the cap-dev-pipe location.
    renderer_script: Optional[Path] = None
    #: OQ-5 settled: abandoned ``processing`` jobs reclaim to ``pending`` after
    #: this many seconds. ``0`` disables automatic reclaim (explicit requeue only).
    lease_ttl_seconds: int = Field(default=3600, ge=0)


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
            # False: WLQ ensures the A/B/C scaffold (like new-cnvrg-rvw-prmpt).
            "init_appendix_if_missing": False,
            "appendix_scaffold_ensured": True,
            "no_triage": True,
            "dual_doc_coverage_matrix": True,
        }
    )
    status_writeback_path: str
    budget_warning: Optional[str] = None
    #: OQ-11: optional human markdown card path alongside the JSON hand-off.
    markdown_card_path: Optional[str] = None
    #: Blind-rotate roster assignment for this drain (agent-surface CRP).
    assigned_reviewer: Optional[AssignedReviewer] = None


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
    #: Required when hand-off ``assigned_reviewer.mode`` is ``blind_rotate``.
    reviewer_model: Optional[str] = None

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
