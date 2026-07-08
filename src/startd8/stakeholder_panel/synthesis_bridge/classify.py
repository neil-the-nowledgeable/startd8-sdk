# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Deterministic ($0) lane classification + context health check (FR-3/FR-4/FR-5/FR-14).

Increment 1 assigns each candidate a lane and, for NON-DECIDABLE items, a reason + suggested owner so
nothing is dropped. A candidate is FIELD-LEVEL only if it names a concrete ``entity.field`` value_path
that is in the host's allow-list (``allowed_value_paths``) — on a brownfield app with no kickoff
manifest that set is empty, so everything routes NON-DECIDABLE (the plan's expected yield). Increment 1
does NOT stage FIELD-LEVEL items; it only labels them for increment 2.
"""

from __future__ import annotations

import re
from typing import FrozenSet, Iterable, List, Optional

from .models import Candidate, Lane

# An ``Entity.field`` token: Capitalised entity, dot, snake/camel field.
_VALUE_PATH_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+\.[a-z][A-Za-z0-9_]*)\b")

# Section → (reason, suggested owner) for NON-DECIDABLE items.
_SECTION_ROUTING = {
    "Open Questions": ("human decision (only the operator can resolve)", "human"),
    "Risk Register": ("risk / governance — mitigate via design or controls", "human / requirements"),
    "Tensions": ("unresolved tension between roles", "human"),
    "Recommendations": ("governance / schema / feature work", "requirements-build"),
}
# Recommendation keywords that clearly mean "engineering work", not a field edit.
_BUILD_HINTS = ("build ", "add a ", "convert ", "design ", "implement ", "create ", "state machine",
                "schema", "entity", "endpoint", "migration", "pipeline", "lock ", "enforce ")


def _detect_value_path(text: str, allowed: FrozenSet[str]) -> Optional[str]:
    """Return the first allow-listed ``entity.field`` token in *text*, if any."""
    for match in _VALUE_PATH_RE.findall(text):
        if not allowed or match in allowed:
            # With no allow-list we cannot confirm a field is real/capturable → treat as non-field.
            if allowed and match in allowed:
                return match
    return None


def classify(candidates: Iterable[Candidate], allowed_value_paths: Optional[Iterable[str]] = None) -> List[Candidate]:
    """Assign a lane + reason + owner to each candidate (mutates and returns the list)."""
    allowed: FrozenSet[str] = frozenset(allowed_value_paths or ())
    result: List[Candidate] = []
    for c in candidates:
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


def health_check(*, synthesis_text: str, context_summary: str, default_context: str) -> List[str]:
    """Non-blocking context/health warnings (FR-14).

    Flags the two things that make a triage untrustworthy: an empty/absent synthesis, and a session
    whose context (``objective``/``strategy``, the persisted comparable fields) was never resolved
    from real inputs — it still equals the neutral default placeholder, a sign the panel ran without
    project context.
    """
    warnings: List[str] = []
    if not (synthesis_text or "").strip():
        warnings.append("synthesis is empty — no items to triage (was the panel run with --run?)")
    if context_summary and default_context and context_summary.strip() == default_context.strip():
        warnings.append(
            "session context is the neutral default placeholder (not resolved from the project's "
            "kickoff inputs / requirements) — the synthesis may be under-grounded"
        )
    return warnings
