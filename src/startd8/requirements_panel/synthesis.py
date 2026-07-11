# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Synthesis pass (FR-RP-3 — fully `$0`/deterministic, no LLM).

Merges the `$0` baseline + role-drafted candidates into **one** requirements doc. Mechanical only
(R1-S6 — synthesis makes no LLM call):

* **dedupe by normalized-slug equality** (R1-F3): identical slugs merge to one; **near-but-not-equal**
  slugs are kept **distinct** — dedupe can never silently drop a real FR;
* a same-slug **conflict** (equal slug, different body) keeps the first FR **and lifts the divergent
  alternative verbatim into an Open Question** — nothing is dropped (R1-F3);
* **stable content-hash FR-IDs** (R1-F4 — see ``models.fr_id``), ordered by area;
* cross-role conflict text is lifted **verbatim** from already-sanitized+grounded candidates — so no
  new prose enters the doc after the sanitize/ground passes (satisfies R2-S6 by construction).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from startd8.requirements_panel.models import RequirementCandidate, RequirementDoc

__all__ = ["synthesize"]


def synthesize(
    baseline: RequirementDoc, candidates: List[RequirementCandidate]
) -> RequirementDoc:
    """Assemble the whole doc from *baseline* + *candidates* (never per-item overwrite, R2-S1)."""
    merged: List[RequirementCandidate] = []
    by_slug: Dict[Tuple[str, str], RequirementCandidate] = {}
    conflicts: List[str] = []

    # baseline stubs first, then role candidates — first-writer-wins per (area, slug).
    for cand in list(baseline.candidates) + list(candidates):
        key = (cand.area, cand.slug)
        existing = by_slug.get(key)
        if existing is None:
            by_slug[key] = cand
            merged.append(cand)
            continue
        # same (area, slug): identical body → true duplicate, drop the copy; different body →
        # a conflict, keep the first and preserve the alternative verbatim in an Open Question.
        if _norm(existing.body) == _norm(cand.body):
            continue
        conflicts.append(
            f"Conflicting requirements for '{cand.title}' ({cand.area}): "
            f"[{existing.role_id or existing.provenance}] {existing.body!r} vs "
            f"[{cand.role_id or cand.provenance}] {cand.body!r}."
        )

    doc = RequirementDoc(
        title=baseline.title,
        problem=baseline.problem,
        candidates=merged,
        non_requirements=list(baseline.non_requirements),
        open_questions=list(baseline.open_questions) + conflicts,
    )
    return doc


def _norm(text: str) -> str:
    return " ".join((text or "").split()).lower()
