# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Data contracts for the synthesis→VIPP triage (increment 1).

The unit is a **candidate** — one discrete item pulled from a synthesis, *before* any staging. It is
deliberately NOT called a "proposal" (that name is already tri-loaded: the panel ``ProposalStore``
record, the host ``ProposedAction``, and the VIPP ``EnvelopedProposal`` — NR-8). A candidate becomes
one of those only in increment 2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class Lane(str, Enum):
    """The triage lanes (FR-3). Three: FIELD_LEVEL / NON_DECIDABLE / UNSTRUCTURED."""

    FIELD_LEVEL = "FIELD_LEVEL"  # maps to an ``entity.field`` value_path — candidate for VIPP (incr. 2)
    NON_DECIDABLE = "NON_DECIDABLE"  # narrative / governance / schema-change / open-question
    UNSTRUCTURED = "UNSTRUCTURED"  # residual content the structured pass didn't claim — preserved + typed (E)


class InputKind(str, Enum):
    """The *type of input received* (orthogonal to :class:`Lane`) — FR-4, 10-kind closed taxonomy.

    Lane = *which pipeline*; ``input_kind`` = *what type of role-based input this is*. Every candidate
    carries one so nothing is merely dropped: it is preserved AND typed.
    """

    recommendation = "recommendation"
    suggestion = "suggestion"
    question = "question"
    risk = "risk"
    tension = "tension"
    feedback = "feedback"
    content = "content"
    decision = "decision"
    constraint = "constraint"
    uncategorized = "uncategorized"


@dataclass
class Candidate:
    """One extracted synthesis item + its triage disposition."""

    title: str  # short human label
    source_section: str  # e.g. "Recommendations", "Open Questions", "Risk Register", "Tensions"
    raw_text: str  # the (``_clean``-normalized) item text (bounded)
    lane: Lane = Lane.NON_DECIDABLE
    reason: str = ""  # why this lane (e.g. "human decision", "governance/schema work")
    suggested_owner: str = ""  # who acts on it (human / requirements-build / VIPP)
    value_path: Optional[str] = None  # set only if a FIELD-LEVEL ``entity.field`` was detected
    input_kind: InputKind = InputKind.uncategorized  # FR-4 — type of input (orthogonal to lane)
    role: str = ""  # FR-4 (ask-all) — the persona that voiced it (provenance); "" for synthesis items

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "source_section": self.source_section,
            "raw_text": self.raw_text,
            "lane": self.lane.value,
            "reason": self.reason,
            "suggested_owner": self.suggested_owner,
            "value_path": self.value_path,
            "input_kind": self.input_kind.value,
            "role": self.role,
        }


@dataclass
class TriageReport:
    """The full triage of a session's synthesis (FR-5: nothing dropped)."""

    session_id: str
    candidates: List[Candidate] = field(default_factory=list)
    health: List[str] = field(default_factory=list)  # FR-14 context/health warnings (non-blocking)

    def by_lane(self, lane: Lane) -> List[Candidate]:
        return [c for c in self.candidates if c.lane is lane]

    def counts(self) -> Dict[str, int]:
        # H-12: stays ``Dict[str, int]`` (per-lane + total) — the per-kind breakdown is a SEPARATE
        # accessor so ``sum(counts().values())`` / all-int consumers never break.
        out = {lane.value: 0 for lane in Lane}
        for c in self.candidates:
            out[c.lane.value] += 1
        out["total"] = len(self.candidates)
        return out

    def kind_counts(self) -> Dict[str, int]:
        """Per-``input_kind`` breakdown (FR-11 / H-12) — a sibling of :meth:`counts`, all-int."""
        out = {k.value: 0 for k in InputKind}
        for c in self.candidates:
            out[c.input_kind.value] += 1
        return out

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": "panel-synthesis-triage",  # report-type label (NOT a candidate's input_kind)
            "session_id": self.session_id,
            "counts": self.counts(),
            "kind_counts": self.kind_counts(),
            "health": list(self.health),
            "candidates": [c.to_dict() for c in self.candidates],
        }

    def to_markdown(self) -> str:
        c = self.counts()
        lines = [
            f"# Panel synthesis triage — {self.session_id}",
            "",
            "> Synthetic, unratified panel input. This routes the synthesis's items; it does not "
            "decide anything. FIELD-LEVEL items are *candidates* for a VIPP `capture` proposal "
            "(increment 2); NON-DECIDABLE items are for a human / the requirements backlog.",
            "",
            f"**Counts:** {c['total']} items · FIELD_LEVEL {c['FIELD_LEVEL']} · "
            f"NON_DECIDABLE {c['NON_DECIDABLE']} · UNSTRUCTURED {c['UNSTRUCTURED']}",
            "",
            "**By kind:** " + (" · ".join(
                f"{k} {n}" for k, n in self.kind_counts().items() if n) or "(none)"),
        ]
        if self.health:
            lines += ["", "**⚠ Health:**"] + [f"- {h}" for h in self.health]

        field_level = self.by_lane(Lane.FIELD_LEVEL)
        if field_level:
            lines += ["", "## FIELD-LEVEL candidates (→ VIPP `capture`, increment 2)", ""]
            for cand in field_level:
                lines.append(f"- **{cand.title}** — `value_path={cand.value_path}` "
                             f"(owner: {cand.suggested_owner}) — _{cand.source_section}_")

        lines += ["", "## NON-DECIDABLE (route to a human / requirements — not a VIPP proposal)", ""]
        nd = self.by_lane(Lane.NON_DECIDABLE)
        if not nd:
            lines.append("_(none)_")
        for cand in nd:
            lines.append(f"- **{cand.title}** — {cand.reason} → owner: {cand.suggested_owner} "
                         f"— _{cand.source_section} · {cand.input_kind.value}_")

        # H-5: residual content — received but not previously accounted for (preserved verbatim + typed).
        lines += ["", "## UNSTRUCTURED (preserved — received but not previously accounted for)", ""]
        us = self.by_lane(Lane.UNSTRUCTURED)
        if not us:
            lines.append("_(none)_")
        for cand in us:
            lines.append(f"- **{cand.title}** — _{cand.source_section} · {cand.input_kind.value}_")
        return "\n".join(lines) + "\n"
