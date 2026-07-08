# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Orchestrate extract → classify → health into a :class:`TriageReport` (increment 1, ``$0``)."""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .classify import classify, health_check
from .extract import extract_candidates
from .models import TriageReport


def _default_context() -> str:
    """The neutral placeholder objective, for the FR-14 under-grounding check."""
    try:
        from startd8.stakeholder_panel.facilitation import DEFAULT_OBJECTIVE

        return DEFAULT_OBJECTIVE
    except Exception:  # pragma: no cover - facilitation always importable in practice
        return ""


def build_triage(
    transcript: Any,
    *,
    allowed_value_paths: Optional[Iterable[str]] = None,
) -> TriageReport:
    """Triage one facilitated-panel transcript's synthesis.

    ``transcript`` is a ``kickoff_view`` ``KickoffTranscript`` (or any object exposing ``session_id``,
    ``objective``, and ``synthesis.text``). Deterministic and ``$0`` — no LLM, no writes.
    """
    session_id = getattr(transcript, "session_id", "") or ""
    synthesis = getattr(transcript, "synthesis", None)
    synthesis_text = getattr(synthesis, "text", "") if synthesis is not None else ""
    objective = getattr(transcript, "objective", "") or ""

    candidates = classify(extract_candidates(synthesis_text), allowed_value_paths)
    health = health_check(
        synthesis_text=synthesis_text,
        context_summary=objective,
        default_context=_default_context(),
    )
    return TriageReport(session_id=session_id, candidates=candidates, health=health)
