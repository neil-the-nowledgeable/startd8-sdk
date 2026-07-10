"""Decision log + retrospective (roadmap Tier C2/C3) — the "how this project got ready" story.

Two read-only views assembled from data the single oracle already folds ($0, deterministic, no LLM):

- **Decision log (C2)** — :func:`decision_log`: what the concierge proposed and what was *adjudicated*
  (ACCEPT / REJECT / COUNTER, with the reason and by-whom the VIPP report records), plus what is
  still pending. Source: the oracle payload's ``pipeline.dispositions`` (the persisted VIPP report)
  cross-referenced with the live ``proposals`` inbox.

- **Retrospective (C3)** — :func:`build_retrospective`: the journey from first-touch to ready-state,
  reconstructed from the Tier-B activation ledger's transition history — readiness start→now,
  blockers cleared, proposals applied, snapshot promoted — as an ordered list of **milestones**. The
  ledger is exactly the event stream this needs, so no separate snapshot history is required.

:func:`kickoff_retrospective` is the one MCP/CLI-agnostic callable (schema
``startd8.kickoff.retrospective.v1``); it is a *separate* surface from ``status.v1`` so the status
payload stays lean.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import schemas

RETROSPECTIVE_SCHEMA = schemas.RETROSPECTIVE


def decision_log(status: Dict[str, Any]) -> Dict[str, Any]:
    """The adjudicated + pending proposal decisions, from the oracle ``status`` payload.

    Degrades cleanly: no dispositions ⇒ empty adjudicated set; the pending count still reflects the
    live inbox."""
    pipeline = status.get("pipeline") or {}
    disp = (pipeline.get("dispositions") or {}) if isinstance(pipeline, dict) else {}
    items: List[Dict[str, Any]] = list(disp.get("items") or []) if disp.get("present") else []
    counts = dict(disp.get("counts") or {}) if disp.get("present") else {}

    adjudicated_ids = {str(i.get("proposal_id")) for i in items}
    pending = [
        {"proposal_id": p.get("id"), "kind": p.get("kind"), "target": p.get("target")}
        for p in (status.get("proposals") or [])
        if str(p.get("id")) not in adjudicated_ids
    ]
    return {
        "counts": counts,
        "adjudicated": len(items),
        "pending": len(pending),
        "items": items,
        "pending_items": pending,
    }


def _milestones(entries: Sequence[dict]) -> List[str]:
    """Derive the ordered 'how it got ready' milestones from consecutive ledger transitions."""
    from .activation import LR_BLOCKED, LR_PROPOSALS, LR_READINESS, LR_SNAPSHOT

    out: List[str] = []
    prev: Optional[dict] = None
    for e in entries or ():
        if not isinstance(e, dict):
            continue
        if prev is not None:
            pr, cur = prev.get(LR_READINESS), e.get(LR_READINESS)
            if pr is not None and cur is not None and cur != pr:
                out.append(f"readiness {pr}% → {cur}%")
            pb, cb = int(prev.get(LR_BLOCKED, 0) or 0), int(e.get(LR_BLOCKED, 0) or 0)
            if pb > 0 and cb == 0:
                out.append("cleared all blockers")
            pp, cp = int(prev.get(LR_PROPOSALS, 0) or 0), int(e.get(LR_PROPOSALS, 0) or 0)
            if cp < pp:
                out.append(f"{pp - cp} proposal(s) applied")
            if prev.get(LR_SNAPSHOT) != "present" and e.get(LR_SNAPSHOT) == "present":
                out.append("session snapshot promoted")
        prev = e
    return out


def build_retrospective(status: Dict[str, Any], ledger_entries: Sequence[dict]) -> Dict[str, Any]:
    """Assemble the journey (from the ledger) + the decision log (from dispositions) into one story."""
    from .activation import LR_TS, readiness_readings

    entries = [e for e in (ledger_entries or ()) if isinstance(e, dict)]
    readings = readiness_readings(entries)
    start = readings[0] if readings else None
    now = readings[-1] if readings else status.get("readiness_percent")
    delta = (now - start) if (start is not None and now is not None) else None
    journey = {
        "transitions": len(entries),
        "readiness_start": start,
        "readiness_now": now,
        "readiness_delta": delta,
        "started_at": entries[0].get(LR_TS) if entries else None,
        "updated_at": entries[-1].get(LR_TS) if entries else None,
        "milestones": _milestones(entries),
    }
    decisions = decision_log(status)

    # One-line human summary, built from whatever signals are available (ledger OR dispositions).
    bits = []
    if delta is not None and delta != 0:
        bits.append(f"readiness {start}% → {now}% ({'+' if delta > 0 else ''}{delta})")
    elif now is not None:
        bits.append(f"readiness {now}%")
    adj = decisions["adjudicated"]
    if adj:
        c = decisions["counts"]
        bits.append(
            f"{adj} decision(s) [{c.get('ACCEPT', 0)}✓ {c.get('REJECT', 0)}✗ {c.get('COUNTER', 0)}~]"
        )
    if decisions["pending"]:
        bits.append(f"{decisions['pending']} pending")
    if bits:
        summary = " · ".join(bits)
    elif not entries:
        summary = "No activation history yet — run `startd8 kickoff check --record` to start the ledger."
    else:
        summary = f"{len(entries)} transition(s) recorded"

    return {
        "schema": RETROSPECTIVE_SCHEMA,
        "project_root": status.get("project_root", ""),
        "journey": journey,
        "decisions": decisions,
        "summary": summary,
    }


def kickoff_retrospective(project_root: str | Path) -> dict:
    """The MCP/CLI-agnostic retrospective — decision log + journey — from the single oracle. Read-only, $0."""
    from .agentic_view import build_agentic_view

    view = build_agentic_view(project_root)
    return build_retrospective(view.to_dict(), view.ledger_entries)
