"""Retrospective bookend (REQ-20) — model a construction outcome as a grounded **Lesson** node with a
human-gated **`revises`** feedback edge. The smallest proof the learning loop closes at the IR level:
forward ``derived-from`` (REQ-16) grounds the Lesson in its outcome; backward ``revises`` proposes a fix to
the offending contract node — and the human, not the IR, disposes (accept/reject). PDCA, made IR structure.

Kagami / no fork: a Lesson is a :class:`Node` projection (``category="lesson"`` + typed ``attributes``) —
the REQ-08 Stage pattern, **no new Node field**. ``revises`` is a *relation value* on REQ-16's
:class:`DerivationEdge` (``relation="revises"``) — **no new edge structure**.
"""

from __future__ import annotations

import dataclasses
from typing import List

from .models import DerivationEdge, EdgeRelation, Node, NodeEvidence

LESSON_CATEGORY = "lesson"


class LessonStatus:
    """A Lesson's disposition. ``proposed`` (default) → the revise is INERT; ``accepted`` → the human has
    closed the loop (the revise MAY be applied — but REQ-20 never applies it autonomously); ``rejected`` →
    retained with a ``rationale`` (the cross-model memory keeps *why*), never deleted."""

    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ALL = (PROPOSED, ACCEPTED, REJECTED)


def build_lesson_from_regression(finding) -> Node:
    """FR-5 — the end-to-end proof: a REQ-19 determinism-regression ``Finding`` → a ``proposed`` Lesson
    that ``derives-from`` the regression outcome (its grounding) and ``revises`` the offending contract
    node named in the finding (``finding.fr``). The smallest closure of the retrospective loop."""
    contract_key = (getattr(finding, "fr", "") or getattr(finding, "check", "")).strip() or "unknown"
    outcome_key = f"regression:{contract_key}"
    message = getattr(finding, "message", "")
    return Node(
        key=f"lesson:{contract_key}",
        does=(f"Determinism regression on {contract_key!r} (planned deterministic, realized llm) — "
              f"propose revising the contract's regime plan or generation path."),
        category=LESSON_CATEGORY,
        # FR-2 grounding: `lives` cites the outcome it derived from — a belief is cruft until grounded.
        lives=(NodeEvidence(type="link", ref=outcome_key, note="determinism-regression outcome"),),
        derivation=(
            DerivationEdge(from_key=outcome_key, relation=EdgeRelation.DERIVED_FROM),  # forward grounding
            DerivationEdge(from_key=contract_key, relation=EdgeRelation.REVISES),      # backward proposal
        ),
        attributes={
            "kind": "lesson",
            "status": LessonStatus.PROPOSED,       # FR-4: propose, don't dispose
            "outcome": message,
            "proposes": f"revise {contract_key}: re-examine its regime plan / generation path",
            "section_order": "90",
        },
    )


def nodes_from_retrospective(spec_dir, provenance) -> List[Node]:
    """Project a corpus into Lesson nodes (the live retrospective source, FR-5/FR-6): run REQ-19's
    determinism-regression check over each doc's requirement nodes against the measured ``provenance``,
    and build one grounded, ``proposed`` Lesson per regression. Empty when no regression fires (honest —
    the loop only produces a lesson when construction actually drifted from plan)."""
    from pathlib import Path

    from .govern import check_determinism_regression
    from .sources_requirements import nodes_from_requirements

    lessons: List[Node] = []
    for p in sorted(Path(spec_dir).glob("REQ-*.md")):
        try:
            reqs = nodes_from_requirements(p)
        except Exception:  # pragma: no cover - projection is defensive; a bad doc never aborts the sweep
            continue
        for finding in check_determinism_regression(reqs, provenance, p.name):
            lessons.append(_tag_revise_tier(build_lesson_from_regression(finding)))
    return lessons


def _tag_revise_tier(lesson: Node) -> Node:
    """REQ-21 — tag a Lesson's proposed ``revise_tier``. At projection time the byte-identity of the
    generated product is UNPROVEN (no guard is run here), so every revise defaults to ``human`` (fail-safe,
    the REQ-20 default). The auto-tier is only reached by ``revise_tier.auto_apply_revise`` *through* the
    guard — never at projection. This surfaces the amendment live while keeping the default human."""
    from .revise_tier import ReviseEligibility, classify_revise_tier

    tier = classify_revise_tier(ReviseEligibility(byte_identical=None, reversible=True,
                                                  lesson_confidence=lesson.confidence))
    return dataclasses.replace(lesson, attributes={**lesson.attributes, "revise_tier": tier})


def lesson_status(lesson: Node) -> str:
    return lesson.attributes.get("status", LessonStatus.PROPOSED)


def revises_edges(node: Node) -> List[DerivationEdge]:
    """FR-3 — a node's backward ``revises`` feedback edges (distinct from forward ``derived-from``)."""
    return [e for e in node.derivation if e.relation == EdgeRelation.REVISES]


def derived_from_edges(node: Node) -> List[DerivationEdge]:
    """FR-3 — a node's forward ``derived-from`` grounding edges (distinct from ``revises``)."""
    return [e for e in node.derivation if e.relation == EdgeRelation.DERIVED_FROM]


def is_grounded(lesson: Node) -> bool:
    """FR-2 — a Lesson is grounded iff it carries a ``derived-from`` edge AND ``lives`` evidence citing
    its outcome; otherwise it is an ungrounded belief (cruft), flagged by ``govern``."""
    return bool(derived_from_edges(lesson)) and bool(lesson.lives)


def revise_is_active(lesson: Node) -> bool:
    """FR-4 — the SOLE gate on whether a Lesson's ``revises`` proposal may be applied: only when the human
    has ``accepted`` it. A ``proposed`` or ``rejected`` Lesson is inert. (REQ-20 never *applies* a revise
    at all — it holds the proposal in the IR; this predicate is the boundary a later applier must honour.)"""
    return lesson_status(lesson) == LessonStatus.ACCEPTED


def accept_lesson(lesson: Node) -> Node:
    """Human disposition — accept: the revise becomes active (``revise_is_active`` True). Returns a new
    Node (frozen); the IR never self-accepts (no autonomous path calls this)."""
    return dataclasses.replace(lesson, attributes={**lesson.attributes, "status": LessonStatus.ACCEPTED})


def reject_lesson(lesson: Node, rationale: str) -> Node:
    """Human disposition — reject: RETAINED with its ``rationale`` (not deleted), so the memory keeps *why*
    a proposal was declined (FR-4)."""
    return dataclasses.replace(
        lesson,
        attributes={**lesson.attributes, "status": LessonStatus.REJECTED, "rationale": rationale},
    )
