# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Durable on-disk storage for WLQ jobs and per-job artifacts (FR-2 / FR-3).

Layout (default root ``.startd8/workflow-loop-queue/`` — OQ-7 lean):

    <queue_root>/
      jobs/<job_id>_startd8_wloop.json     # job envelope incl. status
      <job_id>/                            # per-job artifact dir (VASI §5)
        drain-handoff.json
        drain-result.json                  # written by the surface's agent
        drain-result-r{n}.json             # consumed write-backs (Mottainai)
        bundle-r{n}-<hash>.md              # cached rendered bundles (FR-14)

Reuses ``utils.file_operations.atomic_write_json`` so a job file is never
observed in a partially-written state across agent sessions (Mujō / FR-3).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from ...logging_config import get_logger
from ...utils.file_operations import atomic_write_json
from .models import (
    DRY_RUN_WOULD_ACT_VALUES,
    JOB_FILE_SUFFIX,
    LoopQueueConfig,
    LoopQueueError,
    WorkflowLoopJob,
)

logger = get_logger(__name__)


class LoopQueueStorage:
    """File-based persistence for the Workflow Loop Queue."""

    def __init__(self, config: Optional[LoopQueueConfig] = None):
        self.config = config or LoopQueueConfig()
        self.queue_root = Path(self.config.queue_root).resolve()

    # -- layout -------------------------------------------------------------

    @property
    def jobs_dir(self) -> Path:
        return self.queue_root / "jobs"

    def job_path(self, job_id: str) -> Path:
        return self.jobs_dir / f"{job_id}{JOB_FILE_SUFFIX}"

    def artifact_dir(self, job_id: str) -> Path:
        return self.queue_root / job_id

    def handoff_path(self, job_id: str) -> Path:
        return self.artifact_dir(job_id) / "drain-handoff.json"

    def result_path(self, job_id: str) -> Path:
        return self.artifact_dir(job_id) / "drain-result.json"

    # -- job persistence ----------------------------------------------------

    def save_job(self, job: WorkflowLoopJob) -> Path:
        """Persist the job envelope — EXCEPT on a dry-run job (REQ-02 Boundary 3 / FR-5).

        ``save_job`` is the single persist chokepoint (``queue.py`` never writes directly — it calls here),
        so one guard covers the whole wloop write surface. On a ``job.dry_run=True`` job we write **no**
        job-state file; instead we record the would-be enqueue/claim/complete as a JSON-shaped verdict on the
        job's carried ``dry_run_trace`` (FR-3a) and return the path the file *would* have been written to
        (without creating it). The verdict shape mirrors contextcore's ``DryRunVerdict.to_dict()`` — the
        ``would_act`` value is drawn from ``DRY_RUN_WOULD_ACT_VALUES`` (parity-guarded)."""
        path = self.job_path(job.job_id)
        if getattr(job, "dry_run", False):
            status = job.status.value if hasattr(job.status, "value") else str(job.status)
            job.dry_run_trace.append(
                {
                    "stage_id": f"wloop.save_job:{status}",
                    "received": True,
                    "would_act": DRY_RUN_WOULD_ACT_VALUES[0],  # "yes"
                    "what_change": f"persist wloop job {job.job_id} (loop={job.loop_id}, status={status})",
                    "inputs": [f"job:{job.job_id}"],
                    "outputs": [str(path)],
                    "downstream_handoff": None,
                    "why": "dry-run: describe the would-be wloop job-state write; nothing persisted",
                }
            )
            return path
        job.touch()
        atomic_write_json(path, job.model_dump(mode="json"), indent=2)
        return path

    def load_job(self, job_id: str) -> WorkflowLoopJob:
        path = self.job_path(job_id)
        if not path.exists():
            raise LoopQueueError(f"unknown job_id: {job_id!r} (no file at {path})")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkflowLoopJob.model_validate(data)
        except LoopQueueError:
            raise
        except Exception as e:
            raise LoopQueueError(f"corrupt job file {path}: {e}") from e

    def job_exists(self, job_id: str) -> bool:
        return self.job_path(job_id).exists()

    def list_jobs(self) -> List[WorkflowLoopJob]:
        """All jobs, highest priority first, then oldest first."""
        if not self.jobs_dir.exists():
            return []
        jobs: List[WorkflowLoopJob] = []
        for path in sorted(self.jobs_dir.glob(f"*{JOB_FILE_SUFFIX}")):
            try:
                jobs.append(
                    WorkflowLoopJob.model_validate(
                        json.loads(path.read_text(encoding="utf-8"))
                    )
                )
            except Exception as e:
                logger.warning("Skipping unreadable WLQ job file %s: %s", path, e)
        jobs.sort(key=lambda j: (-j.priority, j.created_at))
        return jobs

    # -- artifacts ----------------------------------------------------------

    def write_json_artifact(self, job_id: str, name: str, data: dict, *, dry_run: bool = False) -> Path:
        """Write a per-job JSON artifact — EXCEPT when ``dry_run`` (REQ-02 Boundary 3/4). On a dry-run the
        path the artifact *would* occupy is returned WITHOUT creating it (the caller records the would-be
        write on the job's ``dry_run_trace``)."""
        path = self.artifact_dir(job_id) / name
        if dry_run:
            return path
        atomic_write_json(path, data, indent=2)
        return path

    def consume_drain_result(self, job_id: str, round_number: int) -> Path:
        """Rename the pending write-back so it is preserved but not re-consumed."""
        src = self.result_path(job_id)
        dst = self.artifact_dir(job_id) / f"drain-result-r{round_number}.json"
        src.replace(dst)
        return dst
