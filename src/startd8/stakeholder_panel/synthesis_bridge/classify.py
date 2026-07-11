# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Deterministic ($0) lane + input_kind classification + context health check (FR-3/FR-4/FR-5/FR-9).

Every candidate gets: a **lane** (FIELD_LEVEL / NON_DECIDABLE / UNSTRUCTURED) and an **input_kind**
(the type of role-based input, FR-4 — orthogonal to lane). A candidate is FIELD-LEVEL only if it names
an allow-listed ``entity.field`` value_path; UNSTRUCTURED items (residual, set by the extractor) keep
that lane and are preserved + typed, never promoted (NR-2). Nothing is dropped.
"""

from __future__ import annotations

import re
from typing import FrozenSet, Iterable, List, Optional

from .models import Candidate, InputKind, Lane

# An ``Entity.field`` token: Capitalised entity, dot, snake/camel field.
_VALUE_PATH_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+\.[a-z][A-Za-z0-9_]*)\b")

# Section → (reason, suggested owner) for NON-DECIDABLE items. H-8 adds the prototype sections so their
# lane reason reads as "design work → backlog", not the generic "not reducible to a single field value".
_SECTION_ROUTING = {
    "Open Questions": ("human decision (only the operator can resolve)", "human"),
    "Risk Register": ("risk / governance — mitigate via design or controls", "human / requirements"),
    "Tensions": ("unresolved tension between roles", "human"),
    "Recommendations": ("governance / schema / feature work", "requirements-build"),
    "UX Improvements": ("design recommendation → requirements backlog", "requirements-build"),
    "Quick Wins": ("design recommendation → requirements backlog", "requirements-build"),
    "Bigger Bets": ("design recommendation → requirements backlog", "requirements-build"),
}

# Section → input_kind (FR-4). Sections not here fall to the keyword heuristic.
_KIND_BY_SECTION = {
    "Recommendations": InputKind.recommendation,
    "Open Questions": InputKind.question,
    "Risk Register": InputKind.risk,
    "Tensions": InputKind.tension,
    "UX Improvements": InputKind.suggestion,
    "Quick Wins": InputKind.suggestion,
    "Bigger Bets": InputKind.suggestion,
}

# Recommendation keywords that clearly mean "engineering work", not a field edit.
_BUILD_HINTS = ("build ", "add a ", "convert ", "design ", "implement ", "create ", "state machine",
                "schema", "entity", "endpoint", "migration", "pipeline", "lock ", "enforce ")

# H-7: word-boundary matching (never a bare substring — `only` must not fire inside `commonly`).
# Precedence (first match wins): question > suggestion > decision > constraint > content. Advisory
# framing ("should / recommend / consider") dominates a mentioned limit; a bare limit → constraint.
_SUGGESTION_RE = re.compile(r"\b(suggest|suggests|recommend|recommends|should|could|consider|propose)\b", re.I)
_DECISION_RE = re.compile(r"\b(decided|chosen|ratified|agreed|adopt|adopted|selected|approved)\b", re.I)
_CONSTRAINT_RE = re.compile(r"\b(must|never|cannot|only|limit|required|forbidden|mandatory)\b", re.I)


def _infer_kind(text: str) -> InputKind:
    """Deterministic residual/heuristic input_kind (H-7). Never None → falls to ``content``."""
    t = text.strip()
    if t.endswith("?"):
        return InputKind.question
    if _SUGGESTION_RE.search(t):
        return InputKind.suggestion
    if _DECISION_RE.search(t):
        return InputKind.decision
    if _CONSTRAINT_RE.search(t):
        return InputKind.constraint
    return InputKind.content


def _kind_for(candidate: Candidate) -> InputKind:
    """FR-4 — section map where known, else the keyword heuristic (residual / unknown sections)."""
    mapped = _KIND_BY_SECTION.get(candidate.source_section)
    return mapped if mapped is not None else _infer_kind(candidate.raw_text)


def _detect_value_path(text: str, allowed: FrozenSet[str]) -> Optional[str]:
    """Return the first allow-listed ``entity.field`` token in *text*, if any.

    An empty allow-list confirms nothing capturable, so nothing matches and everything stays
    NON-DECIDABLE — the read-only triage's normal state (the real prose→value_path mapping is the LLM
    step in :mod:`.extract_llm`, increment 2). Coarse literal-token heuristic: fires only when the
    synthesis writes an allow-listed value_path verbatim.
    """
    for match in _VALUE_PATH_RE.findall(text):
        if match in allowed:
            return match
    return None


def classify(candidates: Iterable[Candidate], allowed_value_paths: Optional[Iterable[str]] = None) -> List[Candidate]:
    """Assign lane + reason + owner + input_kind to each candidate (mutates and returns the list)."""
    allowed: FrozenSet[str] = frozenset(allowed_value_paths or ())
    result: List[Candidate] = []
    for c in candidates:
        c.input_kind = _kind_for(c)  # FR-4 — every candidate, all lanes

        if c.lane is Lane.UNSTRUCTURED:
            # Residual: preserved + typed, never promoted to FIELD_LEVEL (NR-2). Keep the lane.
            c.reason = "unstructured — preserved for a human (received but not previously accounted for)"
            c.suggested_owner = "human / requirements"
            result.append(c)
            continue

        vp = _detect_value_path(c.raw_text, allowed)
        if vp is not None:
            c.lane = Lane.FIELD_LEVEL
            c.value_path = vp
            c.reason = "names an allow-listed field"
            c.suggested_owner = "VIPP capture (increment 2)"
        else:
            c.lane = Lane.NON_DECIDABLE
            reason, owner = _SECTION_ROUTING.get(
                c.source_section, ("not reducible to a single field value", "human")
            )
            # A recommendation that reads as engineering work → requirements-build regardless.
            if c.source_section == "Recommendations" and any(
                h in c.raw_text.lower() for h in _BUILD_HINTS
            ):
                reason, owner = ("schema / feature work — not a field edit", "requirements-build")
            c.reason = reason
            c.suggested_owner = owner
        result.append(c)
    return result


def health_check(
    *,
    synthesis_text: str,
    context_summary: str,
    default_context: str,
    posture: str = "scrutiny",
) -> List[str]:
    """Non-blocking context/health warnings (FR-9/FR-14).

    Flags: an empty/absent synthesis; an under-grounded session (context still the neutral default);
    and — for the ``prototype`` posture (H-9) — the honest routing note that these are design
    recommendations bound for the requirements backlog, not the VIPP apply pipeline.
    """
    warnings: List[str] = []
    if not (synthesis_text or "").strip():
        warnings.append("synthesis is empty — no items to triage (was the panel run with --run?)")
    if context_summary and default_context and context_summary.strip() == default_context.strip():
        warnings.append(
            "session context is the neutral default placeholder (not resolved from the project's "
            "kickoff inputs / requirements) — the synthesis may be under-grounded"
        )
    if posture == "prototype":
        warnings.append(
            "prototype/UX synthesis — items are design recommendations, not entity.field values; "
            "expected to route to the requirements backlog, not the VIPP apply pipeline "
            "(field-level detection may still fire if the synthesis names an allow-listed field)."
        )
    return warnings
