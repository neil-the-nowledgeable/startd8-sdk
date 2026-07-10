# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""F1 — drive the multi-round facilitation over HTTP (fire-and-poll), CRP-hardened.

The facilitation is minutes-long, so — unlike the ask-all `/run` which blocks — a confirmed call
**kicks it off in a background worker thread** (its own event loop) and returns a ``session_id``
immediately; the caller **polls** the persisted transcript for status. This module is the transport +
async orchestration over the existing :class:`KickoffFacilitator` (no new facilitation logic).

Hardening (REQUIREMENTS §2.1): a deterministic ``session_id`` from the ``run_key`` (H-2, so a duplicate
POST resolves to the same run), an atomic idempotency reserve as the single-flight gate (H-1/H-4),
``run_key`` binding ``{posture, tier, cap, roster, budget}`` (H-10, a cheap preview can't authorize a
premium run), a round-weighted dry-run estimate (H-11), a concurrency cap (H-5), a fail-closed budget
check on the dry-run too (H-13), and terminal ``cancelled``/``error`` transcripts (H-7/H-8, in the
facilitator). Cancellation reuses the cross-thread registry (H-9 via the cancel route).
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from startd8.exceptions import Startd8Error
from startd8.stakeholder_panel import facilitation as F

from .stakeholder_run import (
    IdempotencyStore,
    _RUN_REGISTRY,
    cancel_run,
    derive_run_key,
    estimate_cost_per_question,
    roster_version,
)

MAX_CONCURRENT_FACILITATIONS = 4  # H-5 — bound worker threads / event loops / premium fleets
_INFLIGHT_LOCK = threading.Lock()
_INFLIGHT: set[str] = set()  # run_keys with a live worker (in-process; the concurrency cap)
_CANCEL_REQUESTED: set[str] = set()  # session_ids cancelled before the worker registered (race-close)


class FacilitationCapError(Startd8Error):
    """Raised when the concurrent-facilitation cap is hit (→ HTTP 429)."""


# ── run_key + session_id (H-2/H-10) ──────────────────────────────────────────
def facilitate_run_key(*, posture: str, tier: str, cap: Optional[int], budget_usd: float, rv: str) -> str:
    """H-10 — bind posture+tier+budget into the key so a cheap dry-run can't authorize a premium run."""
    return derive_run_key(f"facilitate:{posture}:{tier}:{budget_usd}", cap, rv)


def facilitate_session_id(run_key: str) -> str:
    """Deterministic from the run_key (H-2) — a duplicate POST resolves to the SAME transcript."""
    return f"kp-{run_key[:16]}"


def _params_hash(*, posture: str, tier: str, cap: Optional[int], budget_usd: float, rv: str) -> str:
    blob = json.dumps({"posture": posture, "tier": tier, "cap": cap, "budget": budget_usd, "rv": rv},
                      sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# ── dry-run cost estimate (H-11 round-weighted) ──────────────────────────────
@dataclass(frozen=True)
class FacilitateDryRun:
    run_key: str
    posture: str
    tier: str
    n_participants: int
    projected_calls: int
    estimated_cost: float
    models: Dict[str, str]
    note: str = "round-weighted estimate — real cost is only known after the run"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_key": self.run_key, "posture": self.posture, "tier": self.tier,
            "n_participants": self.n_participants, "projected_calls": self.projected_calls,
            "estimated_cost": round(self.estimated_cost, 6), "models": self.models, "note": self.note,
        }


# Per-round input-weight: R3 (self-excluded digest) and R5 (full-transcript synth) carry far more
# input tokens than a first-round persona call (H-11 — not a flat per-call estimate).
def _round_weighted_units(cfg: "F.FacilitationConfig", n: int) -> float:
    units = 0.0
    prep = int(cfg.ground) + int(cfg.assumptions) + int(cfg.outside_view)
    units += prep * 2.0          # R0 prep (grounding/assumptions/outside-view) — medium
    units += n * 1.0             # R1 individual
    units += n * 1.0             # R2 pre-mortem
    units += n * 2.0             # R3 cross-pollination (digest input)
    if cfg.final_judgment:
        units += n * 1.0         # R4 final judgment
    units += 1 * 5.0             # R5 synthesis — full transcript input
    return units


def facilitate_dry_run(cfg: "F.FacilitationConfig", roster: Any, *, pricing: Any = None) -> FacilitateDryRun:
    """A `$0` round-weighted cost preview + the binding run_key (H-11/H-10). No spend."""
    briefs = F.build_briefs(cfg, roster)
    n = len(briefs)
    fac_spec = F.facilitator_spec_for(cfg.tier)
    per_call = estimate_cost_per_question(fac_spec, pricing)  # facilitator-model per-call baseline
    units = _round_weighted_units(cfg, n)
    rv = roster_version(roster)
    run_key = facilitate_run_key(posture=cfg.posture, tier=cfg.tier, cap=(cfg.cap or None),
                                 budget_usd=cfg.budget_usd, rv=rv)
    specs, _ = F.assign_models(briefs, tier=cfg.tier)
    return FacilitateDryRun(
        run_key=run_key, posture=cfg.posture, tier=cfg.tier, n_participants=n,
        projected_calls=F.projected_calls(cfg, n), estimated_cost=units * per_call,
        models=dict(specs),
    )


# ── kickoff (H-1/H-2/H-3/H-4/H-5) ────────────────────────────────────────────
def _worker(fac: "F.KickoffFacilitator", run_key: str, idem: IdempotencyStore, session_id: str) -> None:
    """Run one facilitation in its own event loop; register for cross-thread cancel; always clean up."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        task = loop.create_task(fac.run())
        # H-9: register under the SESSION_ID (which the poller holds) so cancel-by-session works.
        _RUN_REGISTRY.register(session_id, loop, task)  # cancel via loop.call_soon_threadsafe
        # Race-close (Medium): a cancel that arrived BEFORE we registered is honored now (else it'd
        # 404 at the route and the run would spend on).
        with _INFLIGHT_LOCK:
            wants_cancel = session_id in _CANCEL_REQUESTED
        if wants_cancel:
            task.cancel()
        try:
            loop.run_until_complete(task)
            idem.mark_complete(run_key, session_id)
        except asyncio.CancelledError:
            idem.mark_complete(run_key, session_id)  # terminal (facilitator persisted `cancelled`, H-8)
        except Exception:  # noqa: BLE001 — the facilitator persisted an `error` transcript (H-7)
            idem.mark_complete(run_key, session_id)  # terminal; don't let a retry re-spawn a crashed run
    finally:
        _RUN_REGISTRY.unregister(session_id)
        with _INFLIGHT_LOCK:
            _CANCEL_REQUESTED.discard(session_id)
        try:  # drain any pending child tasks so `loop.close()` doesn't warn (LOW)
            pending = asyncio.all_tasks(loop)
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        except Exception:  # noqa: BLE001 — best-effort drain
            pass
        try:
            loop.close()
        finally:
            with _INFLIGHT_LOCK:
                _INFLIGHT.discard(run_key)


def start_facilitation(
    cfg: "F.FacilitationConfig",
    roster: Any,
    *,
    cost_tracker: Any = None,
    thread_starter: Any = None,
    persona_agent_factory: Any = None,
    facilitator_agent_factory: Any = None,
) -> Dict[str, Any]:
    """Fire-and-poll kickoff. Returns ``{session_id, run_key, status, deduped}`` synchronously.

    ``thread_starter`` (default: a daemon ``threading.Thread``) and the agent factories are injectable so
    tests can run the worker synchronously with `$0` scripted agents (offline).
    """
    rv = roster_version(roster)
    run_key = facilitate_run_key(posture=cfg.posture, tier=cfg.tier, cap=(cfg.cap or None),
                                 budget_usd=cfg.budget_usd, rv=rv)
    session_id = facilitate_session_id(run_key)  # H-2 deterministic
    idem = IdempotencyStore(cfg.project)
    ph = _params_hash(posture=cfg.posture, tier=cfg.tier, cap=(cfg.cap or None),
                      budget_usd=cfg.budget_usd, rv=rv)

    # H-1/H-4 — atomic single-flight gate: reserve; a duplicate/terminal run_key returns its session.
    existing = idem.reserve(run_key, ph, session_id=session_id)  # may raise RunKeyMismatchError (H-10)
    if existing is not None:
        # The transcript may not exist yet (reserved, worker still spinning up) → report the reservation's
        # own status (`started`→`in_progress`), not a misleading `unknown`.
        st = facilitate_status(cfg.project, session_id).get("status", "unknown")
        if st == "unknown":
            st = "in_progress" if existing.get("status") == "started" else "unknown"
        return {"session_id": session_id, "run_key": run_key, "status": st, "deduped": True}

    # From here we OWN a fresh reservation — any failure before the worker takes over MUST roll it back
    # (else a retry dedupes to a run that never executes, until the TTL silently expires — the cap-leak).
    try:
        with _INFLIGHT_LOCK:  # H-5 — concurrency cap
            if len(_INFLIGHT) >= MAX_CONCURRENT_FACILITATIONS:
                raise FacilitationCapError(
                    f"{MAX_CONCURRENT_FACILITATIONS} facilitations already in flight — try again shortly")
            _INFLIGHT.add(run_key)
        fac = F.KickoffFacilitator(
            cfg, roster=roster, session_id=session_id, cost_tracker=cost_tracker,
            persona_agent_factory=persona_agent_factory,
            facilitator_agent_factory=facilitator_agent_factory,
        )
        starter = thread_starter or (lambda target: threading.Thread(target=target, daemon=True).start())
        starter(lambda: _worker(fac, run_key, idem, session_id))
    except BaseException:
        with _INFLIGHT_LOCK:
            _INFLIGHT.discard(run_key)
        idem.release(run_key)  # roll back the orphaned reservation so a retry re-spawns
        raise
    return {"session_id": session_id, "run_key": run_key, "status": "in_progress", "deduped": False}


# ── cancel (H-9) ─────────────────────────────────────────────────────────────
def _live_reservation_sessions(project: Path | str) -> set:
    """session_ids of reservations still ``started`` (reserved; a worker may be spinning up)."""
    try:
        data = IdempotencyStore(project)._load()
    except Exception:  # noqa: BLE001
        return set()
    return {r.get("session_id") for r in data.values() if isinstance(r, dict) and r.get("status") == "started"}


def cancel_facilitation(project: Path | str, session_id: str) -> bool:
    """Signal an in-flight facilitation to abort (H-9, keyed by the session_id the poller holds).

    Records the intent FIRST so a cancel racing a still-spinning-up worker is honored at registration
    (else it would 404 and the run would spend on). Already-completed rounds persist; the facilitator
    ends the transcript `cancelled` (H-8). Returns True if a live/starting run was signalled, else False.
    """
    with _INFLIGHT_LOCK:
        _CANCEL_REQUESTED.add(session_id)
    if cancel_run(session_id):  # a registered task was signalled
        return True
    # Not (yet) registered — is a run genuinely live/starting? then the recorded intent will be honored.
    if facilitate_status(project, session_id).get("status") == "in_progress":
        return True
    if session_id in _live_reservation_sessions(project):
        return True
    with _INFLIGHT_LOCK:  # nothing to cancel — don't leave a stale intent
        _CANCEL_REQUESTED.discard(session_id)
    return False


# ── status poll (H-15) ───────────────────────────────────────────────────────
def facilitate_status(project: Path | str, session_id: str) -> Dict[str, Any]:
    """Read the kickoff-panel transcript (NOT the ask-all store) → the poll payload (FR-3/H-15)."""
    from startd8.kickoff_view import KickoffViewService

    try:
        t = KickoffViewService(str(project)).load(session_id)
    except (FileNotFoundError, KeyError):
        return {"session_id": session_id, "status": "unknown"}
    except Exception as exc:  # noqa: BLE001 — a corrupt/torn transcript degrades to a clean signal, not a 500
        return {"session_id": session_id, "status": "error", "error": f"{type(exc).__name__}: {exc}"}
    synthesis = getattr(t, "synthesis", None)
    return {
        "session_id": session_id,
        "status": t.status or "in_progress",
        "posture": getattr(t, "posture", "scrutiny"),
        "tier": getattr(t, "tier", "premium"),
        "rounds_completed": len(getattr(t, "rounds", []) or []),
        "cost_so_far_usd": round(float(getattr(t, "cost_total_usd", 0.0) or 0.0), 6),
        "synthesis": getattr(synthesis, "text", "") if synthesis is not None else "",
        "halt": getattr(t, "halt", None),
        "is_terminal": bool(getattr(t, "is_done", False)),
    }
