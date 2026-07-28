# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Workflow Loop Queue orchestration: enqueue, drain hand-off, result, triage.

This module owns durable state transitions. Agent surfaces own only execution
of the emitted VASI hand-off and writing ``drain-result.json``.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from pydantic import ValidationError

from ...agents import BaseAgent
from ...logging_config import get_logger
from ..base import ProgressCallback
from ..builtin.architectural_review_log_constants import _ensure_appendix_exists
from ..builtin.architectural_review_log_helpers import (
    _apply_triage_decisions,
    _extract_table_ids,
    _extract_untriaged_suggestions,
    _max_review_round,
)
from ..registry import WorkflowRegistry
from .handoff import persist_drain_handoff
from .reflective_hardening import reflective_hardening_gaps
from .models import (
    AssignedReviewer,
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
    ResearchRequest,
    RoundRecord,
    TriageDecision,
    WorkflowLoopJob,
    looks_like_agent_bundle,
)
from .observability import set_span_status, wlq_span
from .recipes import get_recipe
from .renderer import render_bundle, render_reflective_bundle, render_research_bundle
from .scaffold import ensure_source_scaffolds
from .sdk_executor import map_crp_request_to_workflow_config, run_sdk_crp
from .storage import LoopQueueStorage
from .surfaces import is_known_surface

logger = get_logger(__name__)

_APPENDIX_A = "### Appendix A: Applied Suggestions"
_APPENDIX_B = "### Appendix B: Rejected Suggestions (with Rationale)"
_APPENDIX_C = "### Appendix C: Incoming Suggestions"
_NORMATIVE_ROUND_RE = re.compile(r"^####\s+Review Round R(\d+)(?:\s|$)", re.MULTILINE)
_SUGGESTION_ID_RE = re.compile(r"\b(R\d+-[SF]\d+)\b")
_AUTO_TRIAGE_RATIONALE = "WLQ auto-triage after max_rounds (triage_policy=auto_accept)"
_AUTO_TRIAGE_SOURCE = "wlq-auto"


def _max_crp_round(doc: str) -> int:
    """Recognize both legacy exact and normative attributed round headings.

    The shared helper currently accepts only ``#### Review Round R1`` exactly;
    the CRP agent guide's wire shape is ``R1 — model — date``. WLQ must derive
    the round from either shape (FR-11) without asking the surface to invent it.
    """
    attributed = [int(value) for value in _NORMATIVE_ROUND_RE.findall(doc)]
    return max([_max_review_round(doc), *attributed])


class WorkflowLoopQueue:
    """Durable vendor-neutral workflow/loop job queue (experimental, FR-19)."""

    def __init__(self, config: Optional[LoopQueueConfig] = None):
        self.config = config or LoopQueueConfig()
        self.storage = LoopQueueStorage(self.config)

    # -- enqueue / status --------------------------------------------------

    def enqueue(self, job: WorkflowLoopJob) -> WorkflowLoopJob:
        """Validate and persist a new pending job; fail closed (FR-5/FR-6)."""
        if self.storage.job_exists(job.job_id):
            raise LoopQueueValidationError(f"job_id already exists: {job.job_id!r}")
        if job.status is not LoopJobStatus.PENDING:
            raise LoopQueueValidationError(
                "new jobs must have status='pending'; only drain owns processing"
            )

        try:
            recipe = get_recipe(job.loop_id)
        except KeyError as e:
            raise LoopQueueValidationError(str(e)) from e
        if job.executor.value not in recipe.executors:
            raise LoopQueueValidationError(
                f"loop {job.loop_id!r} does not support executor={job.executor.value!r}"
            )

        if job.loop_id == "crp":
            request = job.crp_request()
            self._validate_crp_request(job, request, enqueue=True)
            if job.executor is LoopExecutor.SDK_WORKFLOW and job.workflow_id:
                # Fail closed on FR-9 mapping before the job is durable.
                map_crp_request_to_workflow_config(request, job.workflow_id)
        elif job.loop_id == "reflective-requirements":
            reflective = job.reflective_request()
            self._validate_reflective_request(job, reflective, enqueue=True)
        elif job.loop_id == "research":
            research = job.research_request()
            self._validate_research_request(job, research, enqueue=True)

        if job.workflow_id:
            self._validate_workflow(job)

        self._validate_dependencies(job)
        self._check_sdk_budget(job, at="enqueue")

        with wlq_span(
            "wlq.enqueue",
            {
                "wlq.job_id": job.job_id,
                "wlq.loop_id": job.loop_id,
                "wlq.executor": job.executor.value,
                "wlq.surface_id": job.surface_id,
                "wlq.workflow_id": job.workflow_id,
            },
        ) as span:
            self.storage.save_job(job)
            set_span_status(span, ok=True)
        logger.info(
            "WLQ enqueue job_id=%s loop_id=%s executor=%s surface_id=%s",
            job.job_id,
            job.loop_id,
            job.executor.value,
            job.surface_id,
        )
        return job

    def enqueue_dict(self, data: Dict[str, object]) -> WorkflowLoopJob:
        try:
            job = WorkflowLoopJob.model_validate(data)
        except ValidationError as e:
            raise LoopQueueValidationError(f"invalid WLQ job envelope: {e}") from e
        return self.enqueue(job)

    def get(self, job_id: str) -> WorkflowLoopJob:
        return self.storage.load_job(job_id)

    def list_jobs(self) -> List[WorkflowLoopJob]:
        return self.storage.list_jobs()

    def status_summary(self, *, reclaim_leases: bool = True) -> Dict[str, object]:
        reclaimed = self.reclaim_expired_leases() if reclaim_leases else 0
        jobs = self.list_jobs()
        counts = {status.value: 0 for status in LoopJobStatus}
        for job in jobs:
            counts[job.status.value] += 1
        return {
            "queue_root": str(self.storage.queue_root),
            "total_jobs": len(jobs),
            "status_counts": counts,
            "reclaimed_leases": reclaimed,
            "lease_ttl_seconds": self.config.lease_ttl_seconds,
            "jobs": [j.model_dump(mode="json") for j in jobs],
        }

    def pilot_projection(
        self,
        pilot_id: str,
        *,
        history_limit: int = 50,
        reclaim_leases: bool = False,
        include_full_jobs: bool = False,
    ) -> Dict[str, object]:
        """Pilot-filtered status + contents + history (REQ_PILOT_QUEUE_OBSERVABILITY).

        Read-mostly: lease reclaim is off by default (FR-12).
        """
        from .pilot_affiliation import (
            compact_job_row,
            count_by_status,
            partition_pilot_jobs,
        )

        reclaimed = self.reclaim_expired_leases() if reclaim_leases else 0
        all_jobs = self.list_jobs()
        in_flight, history = partition_pilot_jobs(all_jobs, pilot_id)
        history_trimmed = history[: max(0, history_limit)]
        root = str(self.storage.queue_root)

        def rows(jobs: List[WorkflowLoopJob]) -> List[Dict[str, object]]:
            out: List[Dict[str, object]] = []
            for job in jobs:
                dr = self.storage.result_path(job.job_id).exists()
                out.append(
                    compact_job_row(
                        job, queue_root=root, drain_result_exists=dr
                    )
                )
            return out

        matched = in_flight + history
        payload: Dict[str, object] = {
            "schema_version": "1.0.0",
            "pilot_id": (pilot_id or "").strip().lower(),
            "queue_root": root,
            "reclaimed_leases": reclaimed,
            "lease_ttl_seconds": self.config.lease_ttl_seconds,
            "total_jobs_in_root": len(all_jobs),
            "matched_jobs": len(matched),
            "status_counts": count_by_status(matched),
            "in_flight": rows(in_flight),
            "history": rows(history_trimmed),
            "history_truncated": len(history) > len(history_trimmed),
            "history_total": len(history),
        }
        if include_full_jobs:
            payload["jobs"] = [j.model_dump(mode="json") for j in matched]
        return payload

    def cancel(self, job_id: str) -> WorkflowLoopJob:
        job = self.get(job_id)
        if job.status in (LoopJobStatus.COMPLETED, LoopJobStatus.CANCELLED):
            raise LoopQueueValidationError(
                f"cannot cancel job {job_id!r} in status={job.status.value}"
            )
        return self._transition(job, LoopJobStatus.CANCELLED, "cancelled explicitly")

    def requeue(self, job_id: str) -> WorkflowLoopJob:
        """Interim explicit recovery for abandoned processing/blocked jobs (FR-3).

        Also allows ``awaiting_triage → pending`` when CRP review rounds remain
        (deferred-triage resume / policy migration).
        """
        job = self.get(job_id)
        if job.status is LoopJobStatus.AWAITING_TRIAGE and job.loop_id == "crp":
            request = job.crp_request()
            if job.rounds_completed() < request.max_rounds:
                job.lease_expires_at = None
                return self._transition(
                    job,
                    LoopJobStatus.PENDING,
                    "requeued from awaiting_triage; continue remaining review rounds",
                )
        if job.status not in (
            LoopJobStatus.PROCESSING,
            LoopJobStatus.BLOCKED,
            LoopJobStatus.FAILED,
        ):
            raise LoopQueueValidationError(
                f"cannot requeue job {job_id!r} in status={job.status.value}"
            )
        job.lease_expires_at = None
        return self._transition(job, LoopJobStatus.PENDING, "requeued explicitly")

    # -- render / drain ----------------------------------------------------

    def render(self, job_id: str) -> Path:
        """Render/reuse the next CRP bundle without changing job status.

        Before rendering, ensures each source doc has the Appendix A/B/C
        scaffold (same contract as ``new-cnvrg-rvw-prmpt.sh``), so reviewers
        only append a Review Round under Appendix C.
        """
        job = self.get(job_id)
        self._require_agent_crp(job)
        request = job.crp_request()
        self._validate_crp_request(job, request, enqueue=False)
        initialized = ensure_source_scaffolds(request.source_paths)
        if initialized:
            job.artifacts["scaffold_initialized"] = ",".join(str(p) for p in initialized)
            self.storage.save_job(job)
        round_number = self._derive_next_round(request)
        applied, rejected = self._derive_disposition_ids(request)
        bundle = render_bundle(
            request=request,
            round_number=round_number,
            artifact_dir=self.storage.artifact_dir(job.job_id),
            applied_ids=applied,
            rejected_ids=rejected,
            renderer_script=self.config.renderer_script,
        )
        job.artifacts["bundle_path"] = str(bundle.resolve())
        self.storage.save_job(job)
        return bundle.resolve()

    def run_next(
        self,
        job_id: Optional[str] = None,
        *,
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> Union[DrainHandoff, WorkflowLoopJob]:
        """Advance one queue step.

        For a pending agent-surface CRP job this emits and persists a VASI
        Drain Hand-off and leaves the job ``processing``. A subsequent call
        after the surface writes ``drain-result.json`` consumes that write-back:
        non-final rounds return to ``pending``; after ``max_rounds``,
        ``triage_policy=auto_accept`` (default) batch-ACCEPTS untriaged
        Appendix C items and completes; ``manual`` leaves ``awaiting_triage``.

        For ``executor=sdk-workflow`` CRP jobs this maps
        :class:`CrpReviewRequest` → catalog workflow and runs it in-process
        (Increment 1.1 / FR-9).
        """
        self.reclaim_expired_leases()
        job = self._select_job(job_id)
        if job.status is LoopJobStatus.PROCESSING:
            if job.executor is LoopExecutor.SDK_WORKFLOW:
                raise LoopQueueValidationError(
                    f"sdk-workflow job {job.job_id!r} is stuck processing; "
                    "use requeue/cancel (no VASI write-back path)"
                )
            return self.complete_drain(job.job_id)
        if (
            job.status is LoopJobStatus.AWAITING_TRIAGE
            and job.loop_id == "crp"
            and job.crp_request().triage_policy == "auto_accept"
        ):
            return self._auto_triage_accept_all(job)
        if job.status is not LoopJobStatus.PENDING:
            raise LoopQueueValidationError(
                f"job {job.job_id!r} is not drainable: status={job.status.value}"
            )
        if job.executor is LoopExecutor.SDK_WORKFLOW:
            unmet = self._unmet_dependencies(job)
            if unmet:
                raise LoopQueueValidationError(
                    f"job {job.job_id!r} blocked by unfinished depends_on: {unmet}"
                )
            self._check_sdk_budget(job, at="drain")
            with wlq_span(
                "wlq.drain",
                {
                    "wlq.job_id": job.job_id,
                    "wlq.loop_id": job.loop_id,
                    "wlq.executor": job.executor.value,
                    "wlq.workflow_id": job.workflow_id,
                    "wlq.dry_run": dry_run,
                },
            ) as span:
                try:
                    if job.loop_id == "crp":
                        result = self.drain_sdk_workflow(
                            job.job_id,
                            agents=agents,
                            on_progress=on_progress,
                            dry_run=dry_run,
                        )
                    elif job.loop_id == "one-shot":
                        result = self.drain_one_shot(
                            job.job_id,
                            agents=agents,
                            on_progress=on_progress,
                            dry_run=dry_run,
                        )
                    else:
                        raise LoopQueueValidationError(
                            f"no sdk-workflow drain for loop_id={job.loop_id!r}"
                        )
                    set_span_status(span, ok=result.status is not LoopJobStatus.FAILED)
                    return result
                except Exception as e:
                    set_span_status(span, ok=False, description=str(e))
                    raise
        unmet = self._unmet_dependencies(job)
        if unmet:
            raise LoopQueueValidationError(
                f"job {job.job_id!r} blocked by unfinished depends_on: {unmet}"
            )
        if job.loop_id == "reflective-requirements":
            return self._drain_reflective_agent_surface(job)
        if job.loop_id == "research":
            return self._drain_research_agent_surface(job)
        self._require_agent_crp(job)

        request = job.crp_request()
        with wlq_span(
            "wlq.drain",
            {
                "wlq.job_id": job.job_id,
                "wlq.loop_id": job.loop_id,
                "wlq.executor": job.executor.value,
                "wlq.surface_id": job.surface_id,
            },
        ) as span:
            try:
                self._validate_crp_request(job, request, enqueue=False)
                if job.rounds_completed() >= request.max_rounds:
                    completed = self._transition(
                        job, LoopJobStatus.COMPLETED, "max_rounds exhausted"
                    )
                    set_span_status(span, ok=True)
                    return completed
                bundle = self.render(job.job_id)
                round_number = self._derive_next_round(request)
                assigned = request.assigned_reviewer_for_round(round_number)
                artifact_dir = self.storage.artifact_dir(job.job_id).resolve()
                handoff = DrainHandoff(
                    job_id=job.job_id,
                    surface_id=job.surface_id or "",
                    loop_id=job.loop_id,
                    round_number=round_number,
                    bundle_path=str(bundle),
                    source_paths=[str(p.resolve()) for p in request.source_paths],
                    success_criteria={
                        "append_review_round": True,
                        # WLQ (and new-cnvrg-rvw-prmpt) pre-initialize A/B/C —
                        # reviewers must append only; never create the scaffold.
                        "init_appendix_if_missing": False,
                        "appendix_scaffold_ensured": True,
                        "no_triage": True,
                        "dual_doc_coverage_matrix": request.dual_doc,
                    },
                    status_writeback_path=str(
                        (artifact_dir / "drain-result.json").resolve()
                    ),
                    budget_warning=self._budget_warning(job, request),
                    assigned_reviewer=assigned,
                )
                handoff = persist_drain_handoff(self.storage, job.job_id, handoff)
                job.artifacts["drain_handoff_path"] = str(
                    self.storage.handoff_path(job.job_id).resolve()
                )
                if handoff.markdown_card_path:
                    job.artifacts["markdown_card_path"] = handoff.markdown_card_path
                job.artifacts["status_writeback_path"] = handoff.status_writeback_path
                if assigned.mode == "blind_rotate" and assigned.model:
                    job.artifacts["assigned_reviewer_model"] = assigned.model
                    job.artifacts["assigned_reviewer_mode"] = assigned.mode
                self._transition(job, LoopJobStatus.PROCESSING, None)
                logger.info(
                    "WLQ drain handoff job_id=%s surface_id=%s round=%s bundle=%s",
                    job.job_id,
                    job.surface_id,
                    round_number,
                    bundle,
                )
                set_span_status(span, ok=True)
                return handoff
            except LoopQueueBlockedError as e:
                self._transition(job, LoopJobStatus.BLOCKED, str(e))
                set_span_status(span, ok=False, description=str(e))
                raise
            except LoopQueueValidationError as e:
                self._transition(job, LoopJobStatus.FAILED, str(e))
                set_span_status(span, ok=False, description=str(e))
                raise

    def _drain_reflective_agent_surface(
        self, job: WorkflowLoopJob
    ) -> DrainHandoff:
        """Emit VASI hand-off for reflective-requirements (OQ-6)."""
        if job.executor is not LoopExecutor.AGENT_SURFACE:
            raise LoopQueueValidationError(
                "reflective-requirements requires executor=agent-surface"
            )
        request = job.reflective_request()
        with wlq_span(
            "wlq.drain",
            {
                "wlq.job_id": job.job_id,
                "wlq.loop_id": job.loop_id,
                "wlq.executor": job.executor.value,
                "wlq.surface_id": job.surface_id,
            },
        ) as span:
            try:
                self._validate_reflective_request(job, request, enqueue=False)
                bundle = render_reflective_bundle(
                    request, self.storage.artifact_dir(job.job_id)
                )
                artifact_dir = self.storage.artifact_dir(job.job_id).resolve()
                handoff = DrainHandoff(
                    job_id=job.job_id,
                    surface_id=job.surface_id or "",
                    loop_id=job.loop_id,
                    round_number=1,
                    bundle_path=str(bundle),
                    source_paths=[str(p.resolve()) for p in request.source_paths],
                    success_criteria={
                        "write_requirements": True,
                        "write_plan": True,
                        "harden_lessons_v03": True,
                        "harden_design_principles_v031": True,
                        "no_crp": True,
                        "no_implementation": True,
                    },
                    status_writeback_path=str(
                        (artifact_dir / "drain-result.json").resolve()
                    ),
                )
                handoff = persist_drain_handoff(self.storage, job.job_id, handoff)
                job.artifacts["drain_handoff_path"] = str(
                    self.storage.handoff_path(job.job_id).resolve()
                )
                if handoff.markdown_card_path:
                    job.artifacts["markdown_card_path"] = handoff.markdown_card_path
                job.artifacts["status_writeback_path"] = handoff.status_writeback_path
                job.artifacts["bundle_path"] = str(bundle)
                self._transition(job, LoopJobStatus.PROCESSING, None)
                set_span_status(span, ok=True)
                return handoff
            except LoopQueueBlockedError as e:
                self._transition(job, LoopJobStatus.BLOCKED, str(e))
                set_span_status(span, ok=False, description=str(e))
                raise
            except LoopQueueValidationError as e:
                self._transition(job, LoopJobStatus.FAILED, str(e))
                set_span_status(span, ok=False, description=str(e))
                raise

    def _drain_research_agent_surface(self, job: WorkflowLoopJob) -> DrainHandoff:
        """Emit VASI hand-off for research (brief → findings)."""
        if job.executor is not LoopExecutor.AGENT_SURFACE:
            raise LoopQueueValidationError(
                "research requires executor=agent-surface"
            )
        request = job.research_request()
        with wlq_span(
            "wlq.drain",
            {
                "wlq.job_id": job.job_id,
                "wlq.loop_id": job.loop_id,
                "wlq.executor": job.executor.value,
                "wlq.surface_id": job.surface_id,
            },
        ) as span:
            try:
                self._validate_research_request(job, request, enqueue=False)
                bundle = render_research_bundle(
                    request, self.storage.artifact_dir(job.job_id)
                )
                artifact_dir = self.storage.artifact_dir(job.job_id).resolve()
                handoff = DrainHandoff(
                    job_id=job.job_id,
                    surface_id=job.surface_id or "",
                    loop_id=job.loop_id,
                    round_number=1,
                    bundle_path=str(bundle),
                    source_paths=[str(p.resolve()) for p in request.source_paths],
                    success_criteria={
                        "write_findings": True,
                        "read_brief": True,
                        "no_crp": True,
                        "no_implementation_unless_brief_spike": True,
                    },
                    status_writeback_path=str(
                        (artifact_dir / "drain-result.json").resolve()
                    ),
                )
                handoff = persist_drain_handoff(self.storage, job.job_id, handoff)
                job.artifacts["drain_handoff_path"] = str(
                    self.storage.handoff_path(job.job_id).resolve()
                )
                if handoff.markdown_card_path:
                    job.artifacts["markdown_card_path"] = handoff.markdown_card_path
                job.artifacts["status_writeback_path"] = handoff.status_writeback_path
                job.artifacts["bundle_path"] = str(bundle)
                self._transition(job, LoopJobStatus.PROCESSING, None)
                set_span_status(span, ok=True)
                return handoff
            except LoopQueueBlockedError as e:
                self._transition(job, LoopJobStatus.BLOCKED, str(e))
                set_span_status(span, ok=False, description=str(e))
                raise
            except LoopQueueValidationError as e:
                self._transition(job, LoopJobStatus.FAILED, str(e))
                set_span_status(span, ok=False, description=str(e))
                raise

    def drain_sdk_workflow(
        self,
        job_id: str,
        *,
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WorkflowLoopJob:
        """Run CRP via ``WorkflowRegistry.run_workflow`` (FR-9)."""
        job = self.get(job_id)
        if job.loop_id != "crp" or job.executor is not LoopExecutor.SDK_WORKFLOW:
            raise LoopQueueValidationError(
                "drain_sdk_workflow requires loop_id=crp + executor=sdk-workflow"
            )
        if job.status is not LoopJobStatus.PENDING:
            raise LoopQueueValidationError(
                f"job {job_id!r} is not pending (status={job.status.value})"
            )
        if not job.workflow_id:
            raise LoopQueueValidationError("workflow_id is required for sdk-workflow")

        request = job.crp_request()
        try:
            self._validate_crp_request(job, request, enqueue=False)
            # Fail-closed mapping before spend (also rejects agent bundles).
            map_crp_request_to_workflow_config(request, job.workflow_id)
            if job.rounds_completed() >= request.max_rounds:
                return self._transition(
                    job, LoopJobStatus.COMPLETED, "max_rounds exhausted"
                )

            self._transition(job, LoopJobStatus.PROCESSING, None)
            wid, config, result = run_sdk_crp(
                request,
                job.workflow_id,
                agents=agents,
                on_progress=on_progress,
                dry_run=dry_run,
            )
            job.artifacts["sdk_workflow_id"] = wid
            self.storage.write_json_artifact(
                job.job_id,
                "sdk-run-config.json",
                config,
            )
            self.storage.write_json_artifact(
                job.job_id,
                "sdk-run-result.json",
                {
                    "success": result.success,
                    "error": result.error,
                    "output": result.output if isinstance(result.output, dict) else {},
                    "dry_run": dry_run,
                },
            )

            if dry_run:
                return self._transition(
                    job, LoopJobStatus.PENDING, "sdk-workflow dry-run complete"
                )
            if not result.success:
                return self._transition(
                    job,
                    LoopJobStatus.FAILED,
                    result.error or "sdk-workflow drain failed",
                )

            round_numbers = []
            output = result.output if isinstance(result.output, dict) else {}
            if "round_numbers" in output:
                round_numbers = list(output.get("round_numbers") or [])
            elif "plan_review" in output or "requirements_review" in output:
                for key in ("requirements_review", "plan_review"):
                    nested = output.get(key) or {}
                    if isinstance(nested, dict):
                        round_numbers.extend(nested.get("round_numbers") or [])
            if not round_numbers:
                observed = 0
                for path in request.source_paths:
                    if path.is_file():
                        observed = max(
                            observed,
                            _max_crp_round(path.read_text(encoding="utf-8")),
                        )
                round_numbers = [observed or 1]

            job.rounds.append(
                RoundRecord(
                    round_number=max(int(n) for n in round_numbers),
                    suggestion_counts={},
                    paths_written=[str(p.resolve()) for p in request.source_paths],
                )
            )
            if not request.enable_triage:
                # Same deferred-triage policy as agent-surface: all rounds first.
                if job.rounds_completed() < request.max_rounds:
                    return self._transition(
                        job,
                        LoopJobStatus.PENDING,
                        f"sdk-workflow {wid} succeeded; "
                        f"next round pending ({job.rounds_completed()}/{request.max_rounds})",
                    )
                return self._finish_review_phase(job, request)
            if job.rounds_completed() >= request.max_rounds:
                return self._transition(
                    job,
                    LoopJobStatus.COMPLETED,
                    f"sdk-workflow {wid} succeeded; rounds complete",
                )
            return self._transition(
                job,
                LoopJobStatus.PENDING,
                f"sdk-workflow {wid} succeeded; next round pending",
            )
        except LoopQueueBlockedError as e:
            self._transition(job, LoopJobStatus.BLOCKED, str(e))
            raise
        except LoopQueueValidationError as e:
            # Prefer FAILED once drain has begun.
            current = self.get(job_id)
            if current.status is LoopJobStatus.PROCESSING:
                self._transition(current, LoopJobStatus.FAILED, str(e))
            raise
        except Exception as e:
            current = self.get(job_id)
            self._transition(current, LoopJobStatus.FAILED, f"sdk-workflow error: {e}")
            raise LoopQueueError(f"sdk-workflow drain failed: {e}") from e

    def drain_one_shot(
        self,
        job_id: str,
        *,
        agents: Optional[List[BaseAgent]] = None,
        on_progress: Optional[ProgressCallback] = None,
        dry_run: bool = False,
    ) -> WorkflowLoopJob:
        """Run a catalog workflow once via the registry (FR-15)."""
        job = self.get(job_id)
        if job.loop_id != "one-shot" or job.executor is not LoopExecutor.SDK_WORKFLOW:
            raise LoopQueueValidationError(
                "drain_one_shot requires loop_id=one-shot + executor=sdk-workflow"
            )
        if job.status is not LoopJobStatus.PENDING:
            raise LoopQueueValidationError(
                f"job {job_id!r} is not pending (status={job.status.value})"
            )
        if not job.workflow_id:
            raise LoopQueueValidationError("workflow_id is required for one-shot")

        self._validate_workflow(job)
        self._transition(job, LoopJobStatus.PROCESSING, None)
        try:
            WorkflowRegistry.discover()
            result = WorkflowRegistry.run_workflow(
                job.workflow_id,
                config=dict(job.config),
                agents=agents,
                on_progress=on_progress,
                dry_run=dry_run,
            )
            self.storage.write_json_artifact(
                job.job_id,
                "sdk-run-result.json",
                {
                    "success": result.success,
                    "error": result.error,
                    "output": result.output if isinstance(result.output, dict) else {},
                    "dry_run": dry_run,
                    "workflow_id": job.workflow_id,
                },
            )
            if dry_run:
                return self._transition(
                    job, LoopJobStatus.PENDING, "one-shot dry-run complete"
                )
            if not result.success:
                return self._transition(
                    job,
                    LoopJobStatus.FAILED,
                    result.error or f"one-shot {job.workflow_id} failed",
                )
            return self._transition(
                job,
                LoopJobStatus.COMPLETED,
                f"one-shot {job.workflow_id} succeeded",
            )
        except LoopQueueValidationError:
            current = self.get(job_id)
            if current.status is LoopJobStatus.PROCESSING:
                self._transition(
                    current, LoopJobStatus.FAILED, "one-shot validation failed"
                )
            raise
        except Exception as e:
            current = self.get(job_id)
            self._transition(current, LoopJobStatus.FAILED, f"one-shot error: {e}")
            raise LoopQueueError(f"one-shot drain failed: {e}") from e

    def complete_drain(self, job_id: str) -> WorkflowLoopJob:
        """Validate a VASI write-back after an agent-surface drain."""
        job = self.get(job_id)
        if job.status is not LoopJobStatus.PROCESSING:
            raise LoopQueueValidationError(
                f"job {job_id!r} is not processing (status={job.status.value})"
            )
        result_path = self.storage.result_path(job_id)
        if not result_path.is_file():
            raise LoopQueueValidationError(
                f"surface write-back missing: {result_path}; job remains processing"
            )
        try:
            result = DrainResult.model_validate_json(
                result_path.read_text(encoding="utf-8")
            )
        except Exception as e:
            self._transition(job, LoopJobStatus.FAILED, f"invalid drain result: {e}")
            raise LoopQueueValidationError(f"invalid drain result: {e}") from e

        expected_round = self._handoff_round(job)
        errors: List[str] = []
        if result.job_id != job.job_id:
            errors.append(f"job_id {result.job_id!r} != {job.job_id!r}")
        if result.surface_id != job.surface_id:
            errors.append(f"surface_id {result.surface_id!r} != {job.surface_id!r}")
        if result.round_number != expected_round:
            errors.append(
                f"round_number {result.round_number} != expected {expected_round}"
            )
        if not result.ok:
            errors.append(result.error or "surface reported ok=false")

        if job.loop_id == "reflective-requirements":
            request_r = job.reflective_request()
            expected_paths = {str(p.resolve()) for p in request_r.source_paths}
            written_paths = {str(Path(p).resolve()) for p in result.paths_written}
            if written_paths != expected_paths:
                errors.append(
                    f"paths_written must exactly match source_paths: "
                    f"expected {sorted(expected_paths)}, got {sorted(written_paths)}"
                )
            for path in request_r.source_paths:
                if not path.is_file():
                    errors.append(f"expected written file missing: {path}")
                elif path.stat().st_size == 0:
                    errors.append(f"expected written file is empty: {path}")
                elif path.suffix.lower() != ".md":
                    errors.append(f"expected markdown file: {path}")
            req_path = Path(request_r.requirements_path)
            if req_path.is_file() and req_path.stat().st_size > 0:
                errors.extend(
                    reflective_hardening_gaps(
                        req_path.read_text(encoding="utf-8")
                    )
                )
            if errors:
                reason = "; ".join(errors)
                self._transition(job, LoopJobStatus.FAILED, reason)
                raise LoopQueueValidationError(reason)
            job.rounds.append(
                RoundRecord(
                    round_number=result.round_number,
                    suggestion_counts=result.suggestion_counts,
                    paths_written=sorted(written_paths),
                )
            )
            self.storage.consume_drain_result(job_id, result.round_number)
            return self._transition(
                job,
                LoopJobStatus.COMPLETED,
                "reflective-requirements docs hardened through v0.3.1",
            )

        if job.loop_id == "research":
            request_res = job.research_request()
            expected_paths = {str(p.resolve()) for p in request_res.source_paths}
            written_paths = {str(Path(p).resolve()) for p in result.paths_written}
            if written_paths != expected_paths:
                errors.append(
                    f"paths_written must exactly match source_paths: "
                    f"expected {sorted(expected_paths)}, got {sorted(written_paths)}"
                )
            for path in request_res.source_paths:
                if not path.is_file():
                    errors.append(f"expected written file missing: {path}")
                elif path.stat().st_size == 0:
                    errors.append(f"expected written file is empty: {path}")
                elif path.suffix.lower() != ".md":
                    errors.append(f"expected markdown file: {path}")
            if not request_res.brief.is_file():
                errors.append(f"research brief vanished: {request_res.brief}")
            if errors:
                reason = "; ".join(errors)
                self._transition(job, LoopJobStatus.FAILED, reason)
                raise LoopQueueValidationError(reason)
            job.rounds.append(
                RoundRecord(
                    round_number=result.round_number,
                    suggestion_counts=result.suggestion_counts,
                    paths_written=sorted(written_paths),
                )
            )
            self.storage.consume_drain_result(job_id, result.round_number)
            return self._transition(
                job,
                LoopJobStatus.COMPLETED,
                "research findings written",
            )

        request = job.crp_request()
        expected_paths = {str(p.resolve()) for p in request.source_paths}
        written_paths = {str(Path(p).resolve()) for p in result.paths_written}
        if written_paths != expected_paths:
            errors.append(
                f"paths_written must exactly match source_paths: "
                f"expected {sorted(expected_paths)}, got {sorted(written_paths)}"
            )
        for path in request.source_paths:
            if not path.is_file():
                errors.append(f"source path vanished after drain: {path}")
                continue
            observed = _max_crp_round(path.read_text(encoding="utf-8"))
            if observed < expected_round:
                errors.append(
                    f"append not detected in {path}: expected Review Round "
                    f"R{expected_round}, highest is R{observed}"
                )

        assigned = self._assigned_reviewer_from_handoff(job)
        if assigned is None:
            assigned = request.assigned_reviewer_for_round(expected_round)
        if assigned.mode == "blind_rotate":
            expected_model = assigned.model
            if not expected_model:
                errors.append("blind_rotate hand-off missing assigned model")
            elif not result.reviewer_model:
                errors.append(
                    "blind_rotate requires drain-result.reviewer_model "
                    f"(expected {expected_model!r})"
                )
            elif result.reviewer_model != expected_model:
                errors.append(
                    f"reviewer_model {result.reviewer_model!r} != assigned "
                    f"{expected_model!r}"
                )

        if errors:
            reason = "; ".join(errors)
            self._transition(job, LoopJobStatus.FAILED, reason)
            raise LoopQueueValidationError(reason)

        job.rounds.append(
            RoundRecord(
                round_number=result.round_number,
                suggestion_counts=result.suggestion_counts,
                paths_written=sorted(written_paths),
            )
        )
        self.storage.consume_drain_result(job_id, result.round_number)
        # FR-13: all review rounds first; then auto or manual batch triage.
        if job.rounds_completed() < request.max_rounds:
            return self._transition(
                job,
                LoopJobStatus.PENDING,
                f"round R{result.round_number} complete; "
                f"next round pending ({job.rounds_completed()}/{request.max_rounds})",
            )
        return self._finish_review_phase(job, request)

    def _finish_review_phase(
        self, job: WorkflowLoopJob, request: CrpReviewRequest
    ) -> WorkflowLoopJob:
        """After all review rounds: auto-accept triage or await manual triage."""
        if request.triage_policy == "auto_accept":
            self._transition(
                job,
                LoopJobStatus.AWAITING_TRIAGE,
                f"all {request.max_rounds} review rounds complete; auto-triaging",
            )
            return self._auto_triage_accept_all(self.get(job.job_id))
        return self._transition(
            job,
            LoopJobStatus.AWAITING_TRIAGE,
            f"all {request.max_rounds} review rounds complete; await batch triage",
        )

    def _collect_auto_triage_decisions(
        self, request: CrpReviewRequest
    ) -> List[TriageDecision]:
        """Build ACCEPT decisions for every untriaged suggestion id across sources."""
        by_id: Dict[str, TriageDecision] = {}
        for path in request.source_paths:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            applied = _extract_table_ids(text, _APPENDIX_A)
            rejected = _extract_table_ids(text, _APPENDIX_B)
            triaged = set(applied) | set(rejected)
            table_items, _ = _extract_untriaged_suggestions(text, applied, rejected)
            for item in table_items:
                sid = item["id"]
                if sid in by_id:
                    continue
                summary = str(item.get("suggestion") or sid).strip()
                if len(summary) > 160:
                    summary = summary[:157] + "..."
                by_id[sid] = TriageDecision(
                    id=sid,
                    decision="ACCEPT",
                    summary=summary or sid,
                    rationale=_AUTO_TRIAGE_RATIONALE,
                    source=_AUTO_TRIAGE_SOURCE,
                )
            # Freeform Appendix C (numbered lists) — catch IDs tables miss.
            c_idx = text.find(_APPENDIX_C)
            appendix_c = text[c_idx:] if c_idx >= 0 else ""
            for sid in _SUGGESTION_ID_RE.findall(appendix_c):
                if sid in triaged or sid in by_id:
                    continue
                summary = sid
                for line in appendix_c.splitlines():
                    if sid in line and "#### Review Round" not in line:
                        cleaned = line.strip().lstrip("1234567890.-) ").strip()
                        cleaned = cleaned.replace(f"**{sid}**", "").strip(" —-")
                        if cleaned:
                            summary = cleaned[:160]
                        break
                by_id[sid] = TriageDecision(
                    id=sid,
                    decision="ACCEPT",
                    summary=summary or sid,
                    rationale=_AUTO_TRIAGE_RATIONALE,
                    source=_AUTO_TRIAGE_SOURCE,
                )
        return list(by_id.values())

    def _auto_triage_accept_all(self, job: WorkflowLoopJob) -> WorkflowLoopJob:
        """ACCEPT all untriaged Appendix C ids, then complete (FR-13 auto_accept)."""
        if job.status is not LoopJobStatus.AWAITING_TRIAGE:
            raise LoopQueueValidationError(
                f"job {job.job_id!r} is not awaiting triage "
                f"(status={job.status.value})"
            )
        request = job.crp_request()
        decisions = self._collect_auto_triage_decisions(request)
        if not decisions:
            return self._transition(
                job,
                LoopJobStatus.COMPLETED,
                "all review rounds complete; auto-triage found nothing untriaged",
            )
        return self.triage(job.job_id, decisions)

    # -- CRP triage --------------------------------------------------------

    def triage(
        self,
        job_id: str,
        decisions: Iterable[Union[TriageDecision, Dict[str, str]]],
    ) -> WorkflowLoopJob:
        """Record explicit ACCEPT/REJECT decisions in A/B; preserve C (FR-13)."""
        job = self.get(job_id)
        if job.status is not LoopJobStatus.AWAITING_TRIAGE:
            raise LoopQueueValidationError(
                f"job {job_id!r} is not awaiting triage " f"(status={job.status.value})"
            )
        request = job.crp_request()
        parsed: List[TriageDecision] = []
        try:
            for item in decisions:
                parsed.append(
                    item
                    if isinstance(item, TriageDecision)
                    else TriageDecision.model_validate(item)
                )
        except Exception as e:
            raise LoopQueueValidationError(f"invalid triage decisions: {e}") from e
        if not parsed:
            raise LoopQueueValidationError("triage requires at least one decision")

        for path in request.source_paths:
            if not path.is_file():
                self._transition(job, LoopJobStatus.BLOCKED, f"path vanished: {path}")
                raise LoopQueueBlockedError(f"path vanished: {path}")
            text = _ensure_appendix_exists(path.read_text(encoding="utf-8"))
            before_c = text[text.find("### Appendix C:") :]
            doc_decisions = self._decisions_for_path(parsed, request, path)
            if not doc_decisions:
                continue
            rows = [d.model_dump() for d in doc_decisions]
            sources = {d.id: d.source for d in doc_decisions}
            updated = _apply_triage_decisions(text, rows, sources)
            after_c = updated[updated.find("### Appendix C:") :]
            if before_c != after_c:
                raise LoopQueueError(
                    f"triage invariant violated: Appendix C changed in {path}"
                )
            path.write_text(updated, encoding="utf-8")

        if job.rounds_completed() >= request.max_rounds:
            return self._transition(
                job, LoopJobStatus.COMPLETED, "batch triage complete; all rounds done"
            )
        # Should not normally happen under deferred-triage (awaiting only after
        # max_rounds), but keep a safe resume path if status was forced early.
        return self._transition(
            job, LoopJobStatus.PENDING, "partial triage; next round pending"
        )

    # -- validation / derivation ------------------------------------------

    def _validate_crp_request(
        self,
        job: WorkflowLoopJob,
        request: CrpReviewRequest,
        *,
        enqueue: bool,
    ) -> None:
        if job.executor is LoopExecutor.AGENT_SURFACE:
            if request.review_template is not None:
                raise LoopQueueValidationError(
                    "review_template is SDK-executor-only; agent-surface uses "
                    "agent_template_path / a pre-rendered FR-20 bundle"
                )
            if not is_known_surface(job.surface_id or ""):
                conformance = request.surface_conformance or {}
                capabilities = set(conformance.get("capabilities", []))
                if not conformance.get("vasi_version") or not {
                    "status",
                    "drain",
                }.issubset(capabilities):
                    raise LoopQueueValidationError(
                        f"unknown surface_id {job.surface_id!r} must declare "
                        "surface_conformance with vasi_version and capabilities "
                        "including status + drain"
                    )
        if (
            job.executor is LoopExecutor.SDK_WORKFLOW
            and request.review_template
            and looks_like_agent_bundle(request.review_template)
        ):
            raise LoopQueueValidationError(
                "SDK review_template contains agent-surface/mustache markers; "
                "do not route an FR-20 bundle through Python str.format"
            )

        paths = list(request.source_paths)
        if request.focus_file:
            paths.append(Path(request.focus_file))
        if request.agent_template_path:
            paths.append(Path(request.agent_template_path))
        for path in paths:
            if not path.exists():
                message = f"required path {'does not exist' if enqueue else 'vanished'}: {path}"
                if enqueue:
                    raise LoopQueueValidationError(message)
                raise LoopQueueBlockedError(message)
            if not path.is_file():
                raise LoopQueueValidationError(f"required path is not a file: {path}")
            if path.suffix.lower() != ".md":
                raise LoopQueueValidationError(
                    f"CRP paths must be markdown (.md): {path}"
                )
            if not os.access(path, os.R_OK):
                raise LoopQueueValidationError(f"required path is unreadable: {path}")

    def _validate_reflective_request(
        self,
        job: WorkflowLoopJob,
        request: ReflectiveRequirementsRequest,
        *,
        enqueue: bool,
    ) -> None:
        if job.executor is not LoopExecutor.AGENT_SURFACE:
            raise LoopQueueValidationError(
                "reflective-requirements requires executor=agent-surface"
            )
        if not is_known_surface(job.surface_id or ""):
            conformance = request.surface_conformance or {}
            capabilities = set(conformance.get("capabilities", []))
            if not conformance.get("vasi_version") or not {
                "status",
                "drain",
            }.issubset(capabilities):
                raise LoopQueueValidationError(
                    f"unknown surface_id {job.surface_id!r} must declare "
                    "surface_conformance with vasi_version and capabilities "
                    "including status + drain"
                )
        for path in request.source_paths:
            parent = path.expanduser().resolve().parent
            if not parent.is_dir():
                message = (
                    f"parent directory for write target "
                    f"{'does not exist' if enqueue else 'vanished'}: {parent}"
                )
                if enqueue:
                    raise LoopQueueValidationError(message)
                raise LoopQueueBlockedError(message)
            if path.suffix.lower() != ".md":
                raise LoopQueueValidationError(
                    f"reflective-requirements paths must be markdown (.md): {path}"
                )
        if request.agent_template_path:
            template = Path(request.agent_template_path)
            if not template.is_file():
                message = (
                    f"agent_template_path "
                    f"{'does not exist' if enqueue else 'vanished'}: {template}"
                )
                if enqueue:
                    raise LoopQueueValidationError(message)
                raise LoopQueueBlockedError(message)

    def _validate_research_request(
        self,
        job: WorkflowLoopJob,
        request: ResearchRequest,
        *,
        enqueue: bool,
    ) -> None:
        if job.executor is not LoopExecutor.AGENT_SURFACE:
            raise LoopQueueValidationError(
                "research requires executor=agent-surface"
            )
        if not is_known_surface(job.surface_id or ""):
            conformance = request.surface_conformance or {}
            capabilities = set(conformance.get("capabilities", []))
            if not conformance.get("vasi_version") or not {
                "status",
                "drain",
            }.issubset(capabilities):
                raise LoopQueueValidationError(
                    f"unknown surface_id {job.surface_id!r} must declare "
                    "surface_conformance with vasi_version and capabilities "
                    "including status + drain"
                )
        brief = request.brief.expanduser().resolve()
        if not brief.is_file():
            message = (
                f"research brief_path "
                f"{'does not exist' if enqueue else 'vanished'}: {brief}"
            )
            if enqueue:
                raise LoopQueueValidationError(message)
            raise LoopQueueBlockedError(message)
        if brief.suffix.lower() != ".md":
            raise LoopQueueValidationError(
                f"research brief_path must be markdown (.md): {brief}"
            )
        if not os.access(brief, os.R_OK):
            raise LoopQueueValidationError(f"research brief is unreadable: {brief}")

        findings = Path(request.findings_path).expanduser().resolve()
        parent = findings.parent
        if not parent.is_dir():
            message = (
                f"parent directory for findings_path "
                f"{'does not exist' if enqueue else 'vanished'}: {parent}"
            )
            if enqueue:
                raise LoopQueueValidationError(message)
            raise LoopQueueBlockedError(message)
        if findings.suffix.lower() != ".md":
            raise LoopQueueValidationError(
                f"research findings_path must be markdown (.md): {findings}"
            )
        if request.focus_file:
            focus = Path(request.focus_file).expanduser().resolve()
            if not focus.is_file():
                message = (
                    f"focus_file "
                    f"{'does not exist' if enqueue else 'vanished'}: {focus}"
                )
                if enqueue:
                    raise LoopQueueValidationError(message)
                raise LoopQueueBlockedError(message)
        if request.agent_template_path:
            template = Path(request.agent_template_path)
            if not template.is_file():
                message = (
                    f"agent_template_path "
                    f"{'does not exist' if enqueue else 'vanished'}: {template}"
                )
                if enqueue:
                    raise LoopQueueValidationError(message)
                raise LoopQueueBlockedError(message)

    def reclaim_expired_leases(self) -> List[str]:
        """OQ-5: reclaim abandoned ``processing`` jobs whose lease expired."""
        if self.config.lease_ttl_seconds <= 0:
            return []
        reclaimed: List[str] = []
        now = datetime.now(timezone.utc)
        for job in self.list_jobs():
            if job.status is not LoopJobStatus.PROCESSING:
                continue
            if not job.lease_expired(now=now):
                continue
            job.lease_expires_at = None
            self._transition(
                job,
                LoopJobStatus.PENDING,
                "lease expired; reclaimed for drain (OQ-5)",
            )
            reclaimed.append(job.job_id)
            logger.info("WLQ reclaimed expired lease job_id=%s", job.job_id)
        return reclaimed

    @staticmethod
    def _check_sdk_budget(job: WorkflowLoopJob, *, at: str) -> None:
        """Fail closed on zero/negative $ budgets for spending executors (FR-18)."""
        if job.executor is not LoopExecutor.SDK_WORKFLOW:
            return
        if "max_cost_usd" not in job.budget:
            return
        try:
            cap = float(job.budget["max_cost_usd"])
        except (TypeError, ValueError) as e:
            raise LoopQueueValidationError(
                f"budget.max_cost_usd must be a number ({at}): {e}"
            ) from e
        if cap <= 0:
            raise LoopQueueValidationError(
                f"sdk-workflow refuses to {at} with max_cost_usd={cap} "
                "(FR-18 zero-dollar budget fail-closed)"
            )

    def _validate_workflow(self, job: WorkflowLoopJob) -> None:
        WorkflowRegistry.discover()
        info = WorkflowRegistry.get_workflow_info(job.workflow_id or "")
        if info is None:
            raise LoopQueueValidationError(f"unknown workflow_id: {job.workflow_id!r}")
        # CRP's config is intentionally canonical review intent, not the direct
        # catalog config; Increment 1.1 owns that mapping (FR-1a / FR-9).
        if job.loop_id == "crp":
            return
        validation = WorkflowRegistry.validate_config(job.workflow_id or "", job.config)
        if not validation.valid:
            raise LoopQueueValidationError(
                f"invalid config for workflow {job.workflow_id!r}: "
                f"{'; '.join(validation.errors)}"
            )

    @staticmethod
    def _derive_next_round(request: CrpReviewRequest) -> int:
        highest = 0
        for path in request.source_paths:
            highest = max(highest, _max_crp_round(path.read_text(encoding="utf-8")))
        return highest + 1

    @staticmethod
    def _derive_disposition_ids(
        request: CrpReviewRequest,
    ) -> tuple[List[str], List[str]]:
        applied: List[str] = []
        rejected: List[str] = []
        for path in request.source_paths:
            doc = path.read_text(encoding="utf-8")
            applied.extend(_extract_table_ids(doc, _APPENDIX_A))
            rejected.extend(_extract_table_ids(doc, _APPENDIX_B))
        return sorted(set(applied)), sorted(set(rejected))

    def _validate_dependencies(self, job: WorkflowLoopJob) -> None:
        """Fail closed on missing deps and cycles (FR-16)."""
        if not job.depends_on:
            return
        if job.job_id in job.depends_on:
            raise LoopQueueValidationError(
                f"job {job.job_id!r} cannot depend on itself"
            )
        for dep in job.depends_on:
            if not self.storage.job_exists(dep):
                raise LoopQueueValidationError(
                    f"depends_on unknown job_id: {dep!r} "
                    "(enqueue the dependency first)"
                )
        # Graph of all known jobs plus the candidate.
        adj: Dict[str, List[str]] = {}
        for existing in self.list_jobs():
            adj[existing.job_id] = list(existing.depends_on)
        adj[job.job_id] = list(job.depends_on)
        cycle = self._find_dependency_cycle(adj)
        if cycle:
            raise LoopQueueValidationError(
                "depends_on cycle detected: " + " → ".join(cycle)
            )

    @staticmethod
    def _find_dependency_cycle(adj: Dict[str, List[str]]) -> Optional[List[str]]:
        """Return one cycle path (first == last) or None."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {node: WHITE for node in adj}
        parent: Dict[str, Optional[str]] = {node: None for node in adj}

        def dfs(node: str) -> Optional[List[str]]:
            color[node] = GRAY
            for neighbor in adj.get(node, []):
                if neighbor not in color:
                    continue  # unknown edge ignored; enqueue validates existence
                if color[neighbor] is GRAY:
                    path = [neighbor, node]
                    cursor: Optional[str] = node
                    while cursor is not None and cursor != neighbor:
                        cursor = parent[cursor]
                        if cursor is not None:
                            path.append(cursor)
                    path.append(neighbor)
                    path.reverse()
                    return path
                if color[neighbor] is WHITE:
                    parent[neighbor] = node
                    found = dfs(neighbor)
                    if found:
                        return found
            color[node] = BLACK
            return None

        for node in adj:
            if color[node] is WHITE:
                found = dfs(node)
                if found:
                    return found
        return None

    def _unmet_dependencies(self, job: WorkflowLoopJob) -> List[str]:
        unmet: List[str] = []
        for dep in job.depends_on:
            try:
                dep_job = self.get(dep)
            except LoopQueueError:
                unmet.append(dep)
                continue
            if dep_job.status is not LoopJobStatus.COMPLETED:
                unmet.append(dep)
        return unmet

    def _select_job(self, job_id: Optional[str]) -> WorkflowLoopJob:
        if job_id:
            return self.get(job_id)
        candidates = [
            j
            for j in self.list_jobs()
            if j.status in (LoopJobStatus.PENDING, LoopJobStatus.PROCESSING)
            and not self._unmet_dependencies(j)
        ]
        if not candidates:
            pending = [
                j.job_id for j in self.list_jobs() if j.status is LoopJobStatus.PENDING
            ]
            if pending:
                raise LoopQueueError(
                    "no drainable WLQ jobs; pending jobs are waiting on depends_on: "
                    + ", ".join(pending)
                )
            raise LoopQueueError("no pending or processing WLQ jobs")
        return candidates[0]

    @staticmethod
    def _require_agent_crp(job: WorkflowLoopJob) -> None:
        if not (job.loop_id == "crp" and job.executor is LoopExecutor.AGENT_SURFACE):
            raise LoopQueueValidationError(
                "this drain path requires loop_id=crp + executor=agent-surface"
            )

    def _handoff_round(self, job: WorkflowLoopJob) -> int:
        path = self.storage.handoff_path(job.job_id)
        if not path.is_file():
            raise LoopQueueValidationError(f"drain hand-off missing: {path}")
        try:
            return DrainHandoff.model_validate_json(
                path.read_text(encoding="utf-8")
            ).round_number
        except Exception as e:
            raise LoopQueueValidationError(f"invalid drain hand-off {path}: {e}") from e

    def _assigned_reviewer_from_handoff(
        self, job: WorkflowLoopJob
    ) -> Optional[AssignedReviewer]:
        path = self.storage.handoff_path(job.job_id)
        if not path.is_file():
            return None
        try:
            handoff = DrainHandoff.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        except Exception:
            return None
        return handoff.assigned_reviewer

    @staticmethod
    def _decisions_for_path(
        decisions: List[TriageDecision],
        request: CrpReviewRequest,
        path: Path,
    ) -> List[TriageDecision]:
        if not request.dual_doc:
            return decisions
        if request.plan_path and path.resolve() == Path(request.plan_path).resolve():
            return [d for d in decisions if "-S" in d.id]
        return [d for d in decisions if "-F" in d.id]

    @staticmethod
    def _budget_warning(
        job: WorkflowLoopJob, request: CrpReviewRequest
    ) -> Optional[str]:
        cap = job.budget.get("max_rounds")
        if cap is not None and int(cap) < request.max_rounds:
            return (
                f"Queue budget caps this job at {int(cap)} rounds while "
                f"CrpReviewRequest asks for {request.max_rounds}."
            )
        return None

    def _transition(
        self,
        job: WorkflowLoopJob,
        status: LoopJobStatus,
        reason: Optional[str],
    ) -> WorkflowLoopJob:
        previous = job.status
        job.status = status
        job.status_reason = reason
        if status is LoopJobStatus.PROCESSING and self.config.lease_ttl_seconds > 0:
            job.lease_expires_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=self.config.lease_ttl_seconds)
            ).isoformat()
        elif status is not LoopJobStatus.PROCESSING:
            job.lease_expires_at = None
        self.storage.save_job(job)
        logger.info(
            "WLQ status job_id=%s %s->%s reason=%s",
            job.job_id,
            previous.value,
            status.value,
            reason,
        )
        return job
