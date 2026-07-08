# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Increment 2 — stage FIELD-LEVEL items and produce the VIPP envelope (FR-4/6/7/8).

Two deterministic (`$0`) stages that compose EXISTING producers — no new envelope/inbox code (NR-7):

1. :func:`stage_recommendations` — turn field-level ``{domain, value_path, value}`` mappings into
   :class:`Recommendation` rows at **``estimate`` provenance** and persist them via the panel
   :class:`ProposalStore` (the FR-6 staging home + FR-7 human-review substrate, keyed by
   ``(domain, value_path)`` with a ``disposition``).

2. :func:`serialize_accepted_to_vipp` — for each **accepted** recommendation, build a ``capture``
   ``ProposedAction`` via :func:`build_proposal` (which enforces the FR-4 allow-list gate through
   ``build_capture_plan`` and stamps ``base_sha``), buffer them, and write the confined VIPP inbox
   via :func:`serialize_buffer`. A value_path the host does not allow-list is **rejected here, not
   dropped** — reported with its reason. The operator then runs ``startd8 vipp negotiate`` / ``apply``.

The LLM step that *derives* those mappings from prose is :mod:`.extract_llm` (paid, OQ-9); this module
is the deterministic spine it feeds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..models import Recommendation
from ..proposals import ProposalStore
from ..recommend_provenance import ESTIMATE_PROVENANCE, panel_origin


def stage_recommendations(
    project_root: Any,
    session_id: str,
    field_mappings: Iterable[Dict[str, Any]],
) -> List[Recommendation]:
    """Persist field-level mappings as ``estimate``-provenance recommendations (FR-6).

    Each mapping: ``{value_path, value, domain?, rationale?, role_id?}``. Returns the recommendations
    (also written to ``ProposalStore`` for review). ``disposition`` defaults to ``"draft"`` — a human
    promotes to ``"accepted"`` (FR-7) before serialization.
    """
    recs: List[Recommendation] = []
    for fm in field_mappings:
        role_id = fm.get("role_id") or "panel"
        recs.append(
            Recommendation(
                domain=fm.get("domain", "") or "",
                value_path=fm["value_path"],
                recommended_value=fm["value"],
                rationale=fm.get("rationale", "") or "",
                role_id=role_id,
                provenance=ESTIMATE_PROVENANCE,
                origin=panel_origin(role_id),
                session_id=session_id,
            )
        )
    ProposalStore(project_root, session_id).save(recs)
    return recs


def serialize_accepted_to_vipp(
    project_root: Any,
    recommendations: Iterable[Recommendation],
    *,
    accepted_only: bool = True,
    config: Optional[Any] = None,
) -> Dict[str, Any]:
    """Turn accepted recommendations into a VIPP ``capture`` envelope (FR-4/FR-8).

    Returns ``{"staged": [value_paths], "rejected": [(value_path, reason)], "write": WriteResult|None,
    "inbox": path|None}``. Composes ``build_proposal`` + ``ProposalBuffer`` + ``serialize_buffer`` —
    writes no envelope bytes itself (NR-7). The FR-4 allow-list gate is enforced by ``build_proposal``.
    """
    # Imported lazily so the deterministic staging half has no hard dependency on kickoff_experience.
    from startd8.kickoff_experience.proposals import ProposalBuffer, build_proposal
    from startd8.kickoff_experience.vipp_seam import serialize_buffer

    buffer = ProposalBuffer()
    staged: List[str] = []
    rejected: List[Tuple[str, str]] = []

    for rec in recommendations:
        if accepted_only and rec.disposition != "accepted":
            continue
        try:
            action = build_proposal(
                {"kind": "capture", "value_path": rec.value_path, "value": str(rec.recommended_value)},
                project_root=project_root,
                config=config,
            )
            buffer.add(action)
            staged.append(rec.value_path)
        except Exception as exc:  # noqa: BLE001 - typed reject (allow-list / round-trip) → report, don't drop
            rejected.append((rec.value_path, f"{type(exc).__name__}: {exc}"))

    write = None
    inbox = None
    if staged:
        write = serialize_buffer(buffer, project_root)
        inbox = str(Path(project_root).expanduser() / ".startd8" / "vipp" / "proposals-inbox.json")
    return {"staged": staged, "rejected": rejected, "write": write, "inbox": inbox}
