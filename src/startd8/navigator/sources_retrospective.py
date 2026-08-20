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
from typing import List, Optional

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


def build_lesson_from_regression(finding, *, confidence=None) -> Node:
    """FR-5 — the end-to-end proof: a REQ-19 determinism-regression ``Finding`` → a ``proposed`` Lesson
    that ``derives-from`` the regression outcome (its grounding) and ``revises`` the offending contract
    node named in the finding (``finding.fr``). The smallest closure of the retrospective loop.

    ``confidence`` (REQ-21 FR-4): the Lesson's grounding confidence = the measured join confidence of the
    regression (how confidently the drift was measured). It gates the auto-tier — ``None`` or below the
    floor → the revise stays ``human``. Set live by :func:`nodes_from_retrospective`."""
    contract_key = (getattr(finding, "fr", "") or getattr(finding, "check", "")).strip() or "unknown"
    outcome_key = f"regression:{contract_key}"
    message = getattr(finding, "message", "")
    return Node(
        key=f"lesson:{contract_key}",
        does=(f"Determinism regression on {contract_key!r} (planned deterministic, realized llm) — "
              f"propose revising the contract's regime plan or generation path."),
        category=LESSON_CATEGORY,
        confidence=confidence,   # REQ-21 FR-4: grounding confidence = the measured regression confidence
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


def build_lesson_from_liveness_gap(finding, *, confidence=None) -> Node:
    """REQ-22 FR-6 — route a verify-liveness GAP (a present-but-dead gate) to a grounded, human-gated
    retrospective Lesson: it ``derives-from`` the liveness finding and ``revises`` the requirement whose
    verify went dead, proposing a fix. Same structure as :func:`build_lesson_from_regression` (propose,
    don't dispose) — retiring/repairing the invariant requires an explicit human accept (REQ-20)."""
    req_key = (getattr(finding, "fr", "") or getattr(finding, "check", "")).strip() or "unknown"
    outcome_key = f"verify-liveness:{req_key}"
    return Node(
        key=f"lesson:{req_key}",
        does=(f"Verify-liveness gap on {req_key!r}: its verify gate is present but DEAD (a durable green "
              f"carrying no truth) — propose revising the requirement's verify to a live gate."),
        category=LESSON_CATEGORY,
        confidence=confidence,
        lives=(NodeEvidence(type="link", ref=outcome_key, note="verify-liveness gap outcome"),),
        derivation=(
            DerivationEdge(from_key=outcome_key, relation=EdgeRelation.DERIVED_FROM),
            DerivationEdge(from_key=req_key, relation=EdgeRelation.REVISES),
        ),
        attributes={
            "kind": "lesson",
            "status": LessonStatus.PROPOSED,
            "outcome": getattr(finding, "message", ""),
            "proposes": f"revise {req_key}: repair or retire the dead verify gate (human sign-off required)",
            "section_order": "90",
        },
    )


def build_lesson_from_runtime_emission_gap(finding, *, confidence=None) -> Node:
    """REQ-28 FR-5 — route a RUNTIME emission gap (a declared feature whose live signal the territory does
    not carry) to a grounded, human-gated Lesson. Same propose-don't-dispose structure as
    :func:`build_lesson_from_liveness_gap`, one altitude deeper: that one fires when an authoring-time gate
    went dead, this one when the *deployed* feature emits nothing. Its proposal names the two human routes
    REQ-28 offers — generate the instrumentation that makes it emit, or revise the claim."""
    req_key = (getattr(finding, "fr", "") or getattr(finding, "check", "")).strip() or "unknown"
    outcome_key = f"runtime-emission:{req_key}"
    return Node(
        key=f"lesson:{req_key}",
        does=(f"Runtime emission gap on {req_key!r}: it binds a live signal the territory does not emit "
              f"(runtime present-but-dead) — propose instrumenting the feature or revising the claim."),
        category=LESSON_CATEGORY,
        confidence=confidence,
        lives=(NodeEvidence(type="link", ref=outcome_key, note="runtime emission gap outcome"),),
        derivation=(
            DerivationEdge(from_key=outcome_key, relation=EdgeRelation.DERIVED_FROM),
            DerivationEdge(from_key=req_key, relation=EdgeRelation.REVISES),
        ),
        attributes={
            "kind": "lesson",
            "status": LessonStatus.PROPOSED,
            "outcome": getattr(finding, "message", ""),
            "proposes": (f"ground {req_key} in the territory: generate the instrumentation that makes its "
                         f"signal emit, or revise the claim (human sign-off required — nothing is applied)"),
            "section_order": "90",
        },
    )


def build_lesson_from_mechanical_gateless(finding, *, confidence=None) -> Node:
    """REQ-27 FR-5 — route a mechanically-attestable-but-GATELESS FR (its verify names a runnable check
    but carries no ``Gate:``) to a human TRIAGE decision: adopt a gate, or mark the verify ``Manual:``.
    Same propose-don't-dispose structure as :func:`build_lesson_from_liveness_gap`, one polarity earlier —
    that one fires on a gate that went dead, this one on a claim that never had a gate at all. Advisory by
    construction: the Lesson is ``proposed``, so it neither blocks the build nor passes as a silent green."""
    req_key = (getattr(finding, "fr", "") or getattr(finding, "check", "")).strip() or "unknown"
    outcome_key = f"self-dogfood:{req_key}"
    return Node(
        key=f"lesson:{req_key}",
        does=(f"Mechanical-but-gateless verify on {req_key!r}: it claims a runnable check yet carries no "
              f"gate — propose a triage: adopt a `Gate:` for that check, or mark the verify `Manual:`."),
        category=LESSON_CATEGORY,
        confidence=confidence,
        lives=(NodeEvidence(type="link", ref=outcome_key, note="self-dogfood mechanical-gateless outcome"),),
        derivation=(
            DerivationEdge(from_key=outcome_key, relation=EdgeRelation.DERIVED_FROM),
            DerivationEdge(from_key=req_key, relation=EdgeRelation.REVISES),
        ),
        attributes={
            "kind": "lesson",
            "status": LessonStatus.PROPOSED,
            "outcome": getattr(finding, "message", ""),
            "proposes": (f"triage {req_key}: adopt a `Gate:` binding the check its verify names, OR mark it "
                         f"`Manual:` with the reason a human is the real checker (human sign-off required)"),
            "section_order": "90",
        },
    )


def build_lesson_from_description_clarification(
    req_key: str, *, path: str, before: str, after: str, confidence=None, outcome: str = "",
) -> Node:
    """REQ-24 H1 — a Lesson whose proposed ``revises`` IS a concrete, mechanical contract-text edit:
    clarify an ambiguous/stale *description* in the contract. This is the honest fuel the retrospective
    loop was missing — a prose clarification changes only source-comment text, so the generated ``$0``
    product stays byte-identical (modulo the source-fingerprint stamp, per REQ-24), which is exactly the
    class the REQ-21 auto-tier can safely apply through the byte-identity guard.

    Unlike a determinism-regression Lesson (whose fix is a *plan re-examination*, not a text edit), this
    Lesson carries a concrete ``revise_edit`` payload in its attributes so
    :func:`revise_tier.revise_edit_from_lesson` can extract a :class:`ReviseEdit` — no edit is invented for
    Lessons that don't carry one."""
    key = (req_key or "").strip() or "unknown"
    outcome_key = f"description-clarification:{key}"
    return Node(
        key=f"lesson:{key}",
        does=(f"Description clarification for {key!r}: the contract text is ambiguous/stale — propose a "
              f"prose edit that leaves the generated product byte-identical (auto-tier-eligible)."),
        category=LESSON_CATEGORY,
        confidence=confidence,
        lives=(NodeEvidence(type="link", ref=outcome_key, note="description-clarification outcome"),),
        derivation=(
            DerivationEdge(from_key=outcome_key, relation=EdgeRelation.DERIVED_FROM),  # forward grounding
            DerivationEdge(from_key=key, relation=EdgeRelation.REVISES),               # backward proposal
        ),
        attributes={
            "kind": "lesson",
            "status": LessonStatus.PROPOSED,
            "outcome": outcome,
            "proposes": f"clarify the description of {key} in {path}",
            # the CONCRETE edit the producer extracts — the payload distinguishes a mechanically-appliable
            # Lesson from a plan-re-examination one (which carries no `revise_edit`).
            "revise_edit": {"target": key, "path": path, "before": before, "after": after},
            "section_order": "90",
        },
    )


def _measured_confidence(node: Node, provenance) -> Optional[float]:
    """REQ-21 FR-4 — the measured join confidence for a node's regime (its Lesson's grounding
    confidence): the provenance match on the node's derivation edges, else its lives; ``None`` when no
    match. A high-confidence measured regression yields a high-confidence lesson (auto-eligible); a
    low-confidence one stays below the floor (``human``)."""
    if provenance is None:
        return None
    for e in getattr(node, "derivation", ()) or ():
        match = provenance.regime_for(node, e)
        if match is not None:
            return match[1]
    match = provenance.regime_for(node, None)  # edge-less lives join
    return match[1] if match is not None else None


def nodes_from_retrospective(spec_dir, provenance, *, include_pipeline: bool = True) -> List[Node]:
    """Project a corpus into Lesson nodes (the live retrospective source, FR-5/FR-6): run REQ-19's
    determinism-regression check against the measured ``provenance`` and build one grounded, ``proposed``
    Lesson per regression, its grounding **confidence** carried from the measured match (so the REQ-21
    auto-tier is reachable). A regression fires only on nodes that carry a DECLARED (planned) regime — the
    pipeline stages (``include_pipeline``, the natural declared-regime source) and any requirement node
    that declares one — so the loop produces a lesson exactly when construction drifted from plan."""
    from pathlib import Path

    from .govern import check_determinism_regression
    from .sources_requirements import nodes_from_requirements

    lessons: List[Node] = []

    def _harvest(nodes: List[Node], doc: str) -> None:
        by_key = {n.key: n for n in nodes}
        for finding in check_determinism_regression(nodes, provenance, doc):
            node = by_key.get(getattr(finding, "fr", ""))
            conf = _measured_confidence(node, provenance) if node is not None else None
            lessons.append(_tag_revise_tier(build_lesson_from_regression(finding, confidence=conf)))

    if include_pipeline:
        from .sources_pipeline import nodes_from_pipeline
        _harvest(nodes_from_pipeline(), "pipeline")

    for p in sorted(Path(spec_dir).glob("REQ-*.md")):
        try:
            reqs = nodes_from_requirements(p)
        except Exception:  # pragma: no cover - projection is defensive; a bad doc never aborts the sweep
            continue
        _harvest(reqs, p.name)
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
