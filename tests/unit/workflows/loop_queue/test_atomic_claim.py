# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""REQ-24 It-2 — the atomic-claim contention suite that proves the TOCTOU is closed.

Every FR gets an executable acceptance check. The cross-process race tests use real
``multiprocessing.Process`` workers held at a ``Barrier`` so both hit the acquire at the same instant —
an unbarriered race would let one finish before the other starts and never exercise the window
(a structural false green — R1-S1).
"""

from __future__ import annotations

import multiprocessing as mp
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from startd8.workflows.loop_queue import (
    LoopClaimHeld,
    LoopJobStatus,
    LoopQueueConfig,
    LoopQueueValidationError,
    WorkflowLoopJob,
    WorkflowLoopQueue,
)


def _make_queue(root: Path, ttl: int = 60) -> WorkflowLoopQueue:
    return WorkflowLoopQueue(LoopQueueConfig(queue_root=root, lease_ttl_seconds=ttl))


def _enqueue_pending(queue: WorkflowLoopQueue, tmp_path: Path, job_id: str) -> None:
    plan = tmp_path / f"{job_id}-PLAN.md"
    plan.write_text("# Plan\n", encoding="utf-8")
    template = tmp_path / f"{job_id}-t.md"
    template.write_text("{{scope}} {{plan_path}} {{round_number}}", encoding="utf-8")
    queue.enqueue(
        WorkflowLoopJob(
            job_id=job_id,
            loop_id="crp",
            executor="agent-surface",
            surface_id="cursor",
            config={
                "plan_path": str(plan),
                "scope": "claim test",
                "agent_template_path": str(template),
            },
        )
    )


# --- module-level workers (spawn-picklable) --------------------------------

def _claim_worker(root: str, job_id: str, surface: str, barrier, out) -> None:
    queue = _make_queue(Path(root))
    barrier.wait(timeout=10)
    try:
        queue.claim(job_id, surface)
        out.put(("won", surface))
    except LoopClaimHeld:
        out.put(("held", surface))
    except Exception as e:  # pragma: no cover - defensive
        out.put(("err", repr(e)))


def _run_next_worker(root: str, job_id: str, surface: str, barrier, out) -> None:
    queue = _make_queue(Path(root))
    barrier.wait(timeout=10)
    try:
        result = queue.run_next(job_id, surface=surface)
        out.put(("drained" if result is not None else "none", surface))
    except Exception as e:  # pragma: no cover - defensive
        out.put(("err", repr(e)))


def _race(worker, root: Path, job_id: str, surfaces):
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(len(surfaces))
    out = ctx.Queue()
    procs = [
        ctx.Process(target=worker, args=(str(root), job_id, s, barrier, out))
        for s in surfaces
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    results = [out.get(timeout=5) for _ in surfaces]
    return results


# --- FR-1 / FR-2 / FR-6: the race is closed --------------------------------

def test_two_processes_race_one_claim_exactly_one_wins(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "race")
    results = _race(_claim_worker, tmp_path / "q", "race", ["surfA", "surfB"])
    outcomes = sorted(tag for tag, _ in results)
    assert outcomes == ["held", "won"], results  # exactly one won, one held (FR-1/FR-2)
    # exactly one sentinel on disk, owned by the winner
    assert queue.storage.claim_lock_path("race").exists()
    winner = next(who for tag, who in results if tag == "won")
    assert queue.storage.sentinel_owner("race") == winner
    assert queue.get("race").lease_owner == winner


def test_two_processes_race_run_next_one_drains(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "rn")
    results = _race(_run_next_worker, tmp_path / "q", "rn", ["surfA", "surfB"])
    outcomes = sorted(tag for tag, _ in results)
    assert outcomes == ["drained", "none"], results  # FR-6: loser gets None, no double-drain


def test_single_holder_second_claim_is_held(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "solo")
    queue.claim("solo", "surfA")
    with pytest.raises(LoopClaimHeld):
        queue.claim("solo", "surfB")


def test_claim_requires_surface(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "nosurf")
    with pytest.raises(LoopQueueValidationError):
        queue.claim("nosurf", "")


# --- FR-3: stale reclaim + crash-orphan sweep ------------------------------

def test_expired_lease_reclaimed_and_sentinel_removed(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "exp")
    queue.claim("exp", "surfA")
    assert queue.storage.claim_lock_path("exp").exists()
    job = queue.get("exp")
    job.lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    queue.storage.save_job(job)
    assert queue.reclaim_expired_leases() == ["exp"]
    assert not queue.storage.claim_lock_path("exp").exists()  # sentinel swept
    assert queue.get("exp").status is LoopJobStatus.PENDING
    assert queue.get("exp").lease_owner is None
    queue.claim("exp", "surfB")  # next claim wins


def test_crash_orphan_sentinel_on_pending_job_is_swept(tmp_path: Path):
    """The permanent-wedge case (R1-F1/R1-S4): crash between O_EXCL and save_job leaves a sentinel
    on a still-PENDING job; lease_expired() returns False on a None lease, so only the orphan sweep
    recovers it."""
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "orphan")
    # simulate the crash: sentinel exists, job never left PENDING, no lease stamped
    assert queue.storage.try_acquire_sentinel("orphan", "deadproc")
    assert queue.get("orphan").status is LoopJobStatus.PENDING
    queue.reclaim_expired_leases()
    assert not queue.storage.claim_lock_path("orphan").exists()
    queue.claim("orphan", "surfB")  # no longer wedged


# --- FR-2 / R1-S6: dry-run must not leak a sentinel ------------------------

def test_dry_run_acquire_leaves_no_sentinel(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    assert queue.storage.try_acquire_sentinel("probe", "surfA", dry_run=True) is True
    assert not queue.storage.claim_lock_path("probe").exists()


# --- FR-4 / R1-S5: release authority + takeover TOCTOU ---------------------

def test_non_owner_release_rejected(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "auth")
    queue.claim("auth", "surfA")
    with pytest.raises(LoopQueueValidationError):
        queue.release("auth", "surfB")
    # owner can release
    queue.release("auth", "surfA")
    assert queue.get("auth").status is LoopJobStatus.PENDING
    assert not queue.storage.claim_lock_path("auth").exists()


def test_late_release_after_takeover_leaves_new_holder_intact(tmp_path: Path):
    """R1-S5: A's lease expires, B takes over; A's late release must not unlink B's fresh sentinel."""
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "take")
    queue.claim("take", "surfA")
    # expire A and reclaim
    job = queue.get("take")
    job.lease_expires_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    queue.storage.save_job(job)
    queue.reclaim_expired_leases()
    queue.claim("take", "surfB")  # B now holds a fresh sentinel
    with pytest.raises(LoopQueueValidationError):
        queue.release("take", "surfA")  # A is late — refused
    assert queue.storage.sentinel_owner("take") == "surfB"  # B intact


# --- FR-6 / R1-S2: non-owner cannot consume a held job ---------------------

def test_non_owner_run_next_cannot_consume(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "consume")
    queue.run_next("consume", surface="surfA")  # A acquires (PROCESSING, owned by A)
    assert queue.get("consume").status is LoopJobStatus.PROCESSING
    assert queue.get("consume").lease_owner == "surfA"
    with pytest.raises(LoopQueueValidationError):
        queue.run_next("consume", surface="surfB")  # B cannot consume A's in-flight job


# --- FR-7: recovery verbs are honest overrides (warn on displacement) ------

def test_requeue_displacing_held_job_warns(tmp_path: Path, caplog):
    import logging

    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "override")
    queue.claim("override", "surfA")
    with caplog.at_level(logging.WARNING):
        queue.requeue("override")  # operator override succeeds
    assert any("displacing live claim" in r.message for r in caplog.records)
    assert queue.get("override").status is LoopJobStatus.PENDING


# --- FR-8: the holder is observable ----------------------------------------

def test_holder_is_observable_via_job_state(tmp_path: Path):
    queue = _make_queue(tmp_path / "q")
    _enqueue_pending(queue, tmp_path, "obs")
    queue.claim("obs", "surfA")
    job = queue.get("obs")  # what `wloop status --job-id` serializes
    assert job.lease_owner == "surfA"
    assert job.lease_expires_at is not None
    info = queue.storage.read_sentinel("obs")
    assert info and info.get("owner") == "surfA" and info.get("acquired_at")
