# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Q1 — triage the single-question **ask-all** into the same typed :class:`TriageReport`.

The ask-all artifact (``.startd8/stakeholder-panel/<sid>.json``) is a flat list of per-persona answers
(``role_id``, ``text``, ``cost_usd``, …) — one answer per persona to ONE question — with no synthesis
and no sections. So it can't go through :func:`route.build_triage` (which needs ``synthesis.text``).
This adapter maps **one answer → one role-tagged candidate**, typed by the existing ``input_kind``
heuristic and rendered by the same backlog/report surfaces — making the cheap, Grafana-drivable survey a
first-class, typed input source. Deterministic, ``$0``, no writes. Per-item **role provenance** falls
out for free (FR-4).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

from ..models import PanelAnswer
from ..transcript import TRANSCRIPT_DIR, TranscriptStore
from .classify import _infer_kind
from .extract import MIN_ITEM_CHARS, _clean, _title_of
from .models import Candidate, InputKind, Lane, TriageReport


def triage_ask_all(answers: List[PanelAnswer], *, session_id: str = "", question: str = "") -> TriageReport:
    """Map an ask-all answer list into a typed, role-tagged :class:`TriageReport` (FR-1/FR-2/FR-4)."""
    candidates: List[Candidate] = []
    skipped = 0
    total_cost = 0.0
    q = question or (answers[0].question if answers else "")
    for a in answers:
        total_cost += float(getattr(a, "cost_usd", 0.0) or 0.0)
        text = _clean(getattr(a, "text", "") or "")
        role = getattr(a, "role_id", "") or ""
        if len(text) < MIN_ITEM_CHARS:  # empty / deferred / trivial answer — never silently dropped
            skipped += 1
            continue
        candidates.append(Candidate(
            title=_title_of(text),
            source_section=role or "ask-all",
            raw_text=text,
            lane=Lane.NON_DECIDABLE,  # NR-3 — an answer is input, never auto FIELD_LEVEL
            reason="stakeholder answer (synthetic, unratified)",
            suggested_owner="human / requirements",
            input_kind=_infer_kind(text),
            role=role,
        ))
    health: List[str] = []
    if q:
        health.append(f"ask-all question: {q}")
    if total_cost:
        health.append(f"ask-all spend: ${total_cost:.4f} across {len(answers)} persona(s)")
    if skipped:
        health.append(f"{skipped} persona(s) gave an empty/deferred answer (skipped, not dropped)")
    return TriageReport(session_id=session_id, candidates=candidates, health=health)


# ─────────────────────────── loader (FR-5) ───────────────────────────
def _store_dir(project: Path | str) -> Path:
    return Path(project).expanduser() / TRANSCRIPT_DIR


def list_ask_all_sessions(project: Path | str) -> List[str]:
    """Ask-all session ids, newest first ($0, read-only)."""
    d = _store_dir(project)
    if not d.is_dir():
        return []
    return [p.stem for p in sorted(d.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)]


def is_ask_all_session(project: Path | str, session_id: str) -> bool:
    """True iff ``session_id`` names an existing ask-all session file."""
    return bool(session_id) and (_store_dir(project) / f"{session_id}.json").is_file()


def load_ask_all_session(
    project: Path | str, session_id: Optional[str] = None
) -> Tuple[List[PanelAnswer], str]:
    """Load one ask-all session's answers + its question (newest if ``session_id`` is None)."""
    sid = session_id
    if not sid:
        sessions = list_ask_all_sessions(project)
        if not sessions:
            return [], ""
        sid = sessions[0]
    answers = TranscriptStore(project, sid).load()
    question = answers[0].question if answers else ""
    return answers, question
