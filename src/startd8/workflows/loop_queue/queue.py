# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Workflow Loop Queue orchestration: enqueue, drain hand-off, result, triage.

This module owns durable state transitions. Agent surfaces own only execution
of the emitted VASI hand-off and writing ``drain-result.json``.
"""

from __future__ import annotations

import os
import re
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
    _max_review_round,
)
from ..registry import WorkflowRegistry
from .models import (
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
    looks_like_agent_bundle,
)
from .recipes import get_recipe
from .renderer import render_bundle
from .sdk_executor import map_crp_request_to_workflow_config, run_sdk_crp
from .storage import LoopQueueStorage
from .surfaces import is_known_surface

logger = get_logger(__name__)

_APPENDIX_A = "### Appendix A: Applied Suggestions"
_APPENDIX_B = "### Appendix B: Rejected Suggestions (with Rationale)"
_NORMATIVE_ROUND_RE = re.compile(r"^####\s+Review Round R(\d+)(?:\s|$)", re.MULTILINE)


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

        if job.workflow_id:
            self._validate_workflow(job)

        self.storage.save_job(job)
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

    def status_summary(self) -> Dict[str, object]:
        jobs = self.list_jobs()
        counts = {status.value: 0 for status in LoopJobStatus}
        for job in jobs:
            counts[job.status.value] += 1
        return {
            "queue_root": str(self.storage.queue_root),
            "total_jobs": len(jobs),
            "status_counts": counts,
            "jobs": [j.model_dump(mode="json") for j in jobs],
        }

    def cancel(self, job_id: str) -> WorkflowLoopJob:
        job = self.get(job_id)
        if job.status in (LoopJobStatus.COMPLETED, LoopJobStatus.CANCELLED):
            raise LoopQueueValidationError(
                f"cannot cancel job {job_id!r} in status={job.status.value}"
            )
        return self._transition(job, LoopJobStatus.CANCELLED, "cancelled explicitly")

    def requeue(self, job_id: str) -> WorkflowLoopJob:
        """Interim explicit recovery for abandoned processing/blocked jobs (FR-3)."""
        job = self.get(job_id)
        if job.status not in (
            LoopJobStatus.PROCESSING,
            LoopJobStatus.BLOCKED,
            LoopJobStatus.FAILED,
        ):
            raise LoopQueueValidationError(
                f"cannot requeue job {job_id!r} in status={job.status.value}"
            )
        return self._transition(job, LoopJobStatus.PENDING, None)

    # -- render / drain ----------------------------------------------------

    def render(self, job_id: str) -> Path:
        """Render/reuse the next CRP bundle without changing job status."""
        job = self.get(job_id)
        self._require_agent_crp(job)
        request = job.crp_request()
        self._validate_crp_request(job, request, enqueue=False)
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
        after the surface writes ``drain-result.json`` consumes that write-back
        and moves the job to ``awaiting_triage``.

        For ``executor=sdk-workflow`` CRP jobs this maps
        :class:`CrpReviewRequest` → catalog workflow and runs it in-process
        (Increment 1.1 / FR-9).
        """
        job = self._select_job(job_id)
        if job.status is LoopJobStatus.PROCESSING:
            if job.executor is LoopExecutor.SDK_WORKFLOW:
                raise LoopQueueValidationError(
                    f"sdk-workflow job {job.job_id!r} is stuck processing; "
                    "use requeue/cancel (no VASI write-back path)"
                )
            return self.complete_drain(job.job_id)
        if job.status is not LoopJobStatus.PENDING:
            raise LoopQueueValidationError(
                f"job {job.job_id!r} is not drainable: status={job.status.value}"
            )
        if job.executor is LoopExecutor.SDK_WORKFLOW:
            return self.drain_sdk_workflow(
                job.job_id,
                agents=agents,
                on_progress=on_progress,
                dry_run=dry_run,
            )
        self._require_agent_crp(job)

        request = job.crp_request()
        try:
            self._validate_crp_request(job, request, enqueue=False)
            if job.rounds_completed() >= request.max_rounds:
                return self._transition(
                    job, LoopJobStatus.COMPLETED, "max_rounds exhausted"
                )
            bundle = self.render(job.job_id)
            round_number = self._derive_next_round(request)
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
                    "init_appendix_if_missing": True,
                    "no_triage": True,
                    "dual_doc_coverage_matrix": request.dual_doc,
                },
                status_writeback_path=str(
                    (artifact_dir / "drain-result.json").resolve()
                ),
                budget_warning=self._budget_warning(job, request),
            )
            handoff_path = self.storage.write_json_artifact(
                job.job_id,
                "drain-handoff.json",
                handoff.model_dump(mode="json"),
            )
            job.artifacts["drain_handoff_path"] = str(handoff_path.resolve())
            job.artifacts["status_writeback_path"] = handoff.status_writeback_path
            self._transition(job, LoopJobStatus.PROCESSING, None)
            logger.info(
                "WLQ drain handoff job_id=%s surface_id=%s round=%s bundle=%s",
                job.job_id,
                job.surface_id,
                round_number,
                bundle,
            )
            return handoff
        except LoopQueueBlockedError as e:
            self._transition(job, LoopJobStatus.BLOCKED, str(e))
            raise
        except LoopQueueValidationError as e:
            self._transition(job, LoopJobStatus.FAILED, str(e))
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
                return self._transition(
                    job,
                    LoopJobStatus.AWAITING_TRIAGE,
                    f"sdk-workflow {wid} succeeded; triage deferred",
                )
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

    def complete_drain(self, job_id: str) -> WorkflowLoopJob:
        """Validate a VASI write-back and detect the claimed Appendix C append."""
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
            LoopJobStatus.AWAITING_TRIAGE,
            f"round R{result.round_number} awaits explicit triage",
        )

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
            return self._transition(job, LoopJobStatus.COMPLETED, "final round triaged")
        return self._transition(
            job, LoopJobStatus.PENDING, "round triaged; next round pending"
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

    def _select_job(self, job_id: Optional[str]) -> WorkflowLoopJob:
        if job_id:
            return self.get(job_id)
        jobs = [
            j
            for j in self.list_jobs()
            if j.status in (LoopJobStatus.PENDING, LoopJobStatus.PROCESSING)
        ]
        if not jobs:
            raise LoopQueueError("no pending or processing WLQ jobs")
        return jobs[0]

    @staticmethod
    def _require_agent_crp(job: WorkflowLoopJob) -> None:
        if not (job.loop_id == "crp" and job.executor is LoopExecutor.AGENT_SURFACE):
            raise LoopQueueValidationError(
                "Increment 1 drain supports loop_id=crp + "
                "executor=agent-surface only"
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
        self.storage.save_job(job)
        logger.info(
            "WLQ status job_id=%s %s->%s reason=%s",
            job.job_id,
            previous.value,
            status.value,
            reason,
        )
        return job
