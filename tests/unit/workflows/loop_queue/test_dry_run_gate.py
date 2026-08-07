"""REQ-02 I5 — the wloop job-state chokepoint gate (Boundary 3 / FR-5) in startd8-sdk.

``LoopQueueStorage.save_job`` is the single persist chokepoint. On a ``dry_run`` job it must write NO
job-state file — instead recording the would-be enqueue on the job's carried ``dry_run_trace``. A live job
persists normally (NR-4: no-op on the live path).
"""

from __future__ import annotations

from pathlib import Path

from startd8.workflows.loop_queue.handoff import persist_drain_handoff
from startd8.workflows.loop_queue.models import (
    DrainHandoff,
    LoopExecutor,
    LoopQueueConfig,
    WorkflowLoopJob,
)
from startd8.workflows.loop_queue.storage import LoopQueueStorage


def _storage(tmp_path) -> LoopQueueStorage:
    return LoopQueueStorage(LoopQueueConfig(queue_root=str(tmp_path / "wlq")))


def _job(dry_run: bool, job_id: str = "j") -> WorkflowLoopJob:
    return WorkflowLoopJob(
        job_id=job_id, loop_id="l", executor=LoopExecutor.SDK_WORKFLOW, workflow_id="w", dry_run=dry_run
    )


def _snapshot(d: Path):
    if not d.exists():
        return {}
    return {p.name: p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}


def test_save_job_dry_run_writes_no_job_state(tmp_path):
    st = _storage(tmp_path)
    job = _job(dry_run=True, job_id="dry")
    before = _snapshot(st.queue_root)
    st.save_job(job)
    after = _snapshot(st.queue_root)
    assert before == after == {}  # byte-identical: zero job-state files
    assert len(job.dry_run_trace) == 1
    v = job.dry_run_trace[0]
    assert v["would_act"] == "yes" and v["stage_id"].startswith("wloop.save_job")


def test_save_job_live_persists(tmp_path):
    st = _storage(tmp_path)
    job = _job(dry_run=False, job_id="live")
    st.save_job(job)
    assert st.job_exists("live")
    assert job.dry_run_trace == []  # no verdict on the live path


def test_write_json_artifact_dry_run_writes_nothing(tmp_path):
    st = _storage(tmp_path)
    path = st.write_json_artifact("j", "art.json", {"k": "v"}, dry_run=True)
    assert not path.exists()  # returns the would-be path, creates nothing
    # live path writes
    live_path = st.write_json_artifact("j", "art.json", {"k": "v"})
    assert live_path.exists()


def test_persist_drain_handoff_dry_run_writes_nothing(tmp_path):
    st = _storage(tmp_path)
    handoff = DrainHandoff(
        job_id="j", loop_id="l", round_number=1, surface_id="s",
        bundle_path="bundle.md", source_paths=["a.md"], status_writeback_path="wb.json",
    )
    before = _snapshot(st.queue_root)
    out = persist_drain_handoff(st, "j", handoff, dry_run=True)
    after = _snapshot(st.queue_root)
    assert before == after == {}  # a drain hand-off is an action artifact — none written on a dry-run
    assert out.markdown_card_path  # but the would-be path is described
