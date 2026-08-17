"""Guarded `revises` auto-tier (REQ-21) — auto-apply ONLY a provably-no-downside revise; gate the rest.

Amends REQ-20's absolute human gate (NR-1): a ``revises`` edge may auto-apply WITHOUT human accept **iff
ALL** of — byte-identity-provable on the generated product, reversible (git-tracked, no spend / outward
publish / external ship), and drawn from an **above-confidence-floor** Lesson. Two integrity anchors:

- **Enforce, don't declare (FR-2).** The auto path applies the revise *through* the byte-identity guard;
  a mis-classification that would change the product is caught by the guard and downgraded to ``human`` —
  never shipped (fail-closed).
- **Fail-safe to human (FR-5).** Every eligibility property must be affirmatively ``True``; any unresolved
  (``None``) or failing property → ``human``. Auto is opt-in-**by-proof**, human-gated-by-default.

The default stays human; every product-changing (consequential) revise remains human-gated (REQ-20). The
gate is the OBJECTIVE byte-identity guard, not a "trivial complexity" judgment (which erodes — NR-2).
"""

from __future__ import annotations

import dataclasses
from typing import Callable, Iterable, Optional

from .models import Node
from .sources_retrospective import revises_edges

# FR-4 — the grounding-confidence floor; a weakly-grounded belief never auto-modifies.
CONFIDENCE_FLOOR = 0.8

TIER_AUTO = "auto"
TIER_HUMAN = "human"

# FR-3 — effects that make a revise irreversible (any present → not auto-eligible). An empty effect set
# is a pure git-tracked IR/description change = reversible.
IRREVERSIBLE_EFFECTS = frozenset({
    "spend", "regenerate_with_spend", "outward_publish", "external_ship", "not_git_tracked",
})


def is_reversible(effects: Iterable[str] = ()) -> bool:
    """FR-3 — reversible iff the revise touches only git-tracked artifacts and triggers NO irreversible
    side effect (LLM spend / regeneration-with-spend / outward publish / external ship)."""
    return not (set(effects or ()) & IRREVERSIBLE_EFFECTS)


class ReviseEditError(ValueError):
    """A malformed revise edit — named so a bad edit fails loud, never silently no-ops."""


@dataclasses.dataclass(frozen=True)
class ReviseEdit:
    """REQ-24 FR-1 — the CONCRETE contract mutation a revise applies (distinct from REQ-20's prose
    proposal, which carries no edit): the ``target`` contract node key, the contract ``path``, and the
    exact ``before`` text and its ``after`` replacement. Pure data (no construction import) — the applier
    (``revise_apply.py``) proves it byte-identical by regenerating the product."""

    target: str
    path: str
    before: str
    after: str


def parse_revise_edit(raw) -> ReviseEdit:
    """Validate + build a :class:`ReviseEdit`, raising a named :class:`ReviseEditError` on any missing
    field (``target``/``path``/``before`` must be non-empty; ``after`` may be empty for a deletion)."""
    if not isinstance(raw, dict):
        raise ReviseEditError(f"revise edit must be a mapping, got {type(raw).__name__}")
    for key in ("target", "path", "before"):
        if not str(raw.get(key, "")).strip():
            raise ReviseEditError(f"revise edit missing required non-empty {key!r}")
    return ReviseEdit(target=str(raw["target"]), path=str(raw["path"]),
                      before=str(raw["before"]), after=str(raw.get("after", "")))


def lesson_confidence(lesson: Node) -> Optional[float]:
    """The Lesson's grounding confidence (FR-4) — its ``confidence`` field, else a ``confidence``
    attribute; ``None`` when absent or unparseable (→ ``human``, fail-safe)."""
    if lesson.confidence is not None:
        return lesson.confidence
    raw = lesson.attributes.get("confidence")
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


@dataclasses.dataclass(frozen=True)
class ReviseEligibility:
    """The properties an auto-eligible revise must ALL affirmatively prove. Any ``None`` (unresolved) or
    ``False`` → ``human`` (fail-safe, FR-5). ``byte_identical`` is the *claimed/expected* proof that the
    auto path re-enforces through the guard (FR-2) — never trusted on its own."""

    byte_identical: Optional[bool] = None
    reversible: Optional[bool] = None
    lesson_confidence: Optional[float] = None


def eligibility_of(lesson: Node, *, byte_identical: Optional[bool], effects: Iterable[str] = ()) -> ReviseEligibility:
    """Assemble a :class:`ReviseEligibility` from a Lesson + the caller's byte-identity expectation +
    the revise's known side effects (reversibility + confidence are derived here)."""
    return ReviseEligibility(
        byte_identical=byte_identical,
        reversible=is_reversible(effects),
        lesson_confidence=lesson_confidence(lesson),
    )


def classify_revise_tier(elig: ReviseEligibility) -> str:
    """FR-1/FR-4/FR-5 — ``auto`` iff byte-identity-provable AND reversible AND at/above the confidence
    floor, each affirmatively ``True``; any unresolved/failing property → ``human`` (un-erodable, fail-safe)."""
    if elig.byte_identical is not True:
        return TIER_HUMAN
    if elig.reversible is not True:
        return TIER_HUMAN
    if elig.lesson_confidence is None or elig.lesson_confidence < CONFIDENCE_FLOOR:
        return TIER_HUMAN
    return TIER_AUTO


@dataclasses.dataclass(frozen=True)
class ReviseAudit:
    """FR-6 — the auditable, reversible record of an auto-applied revise: the Lesson, the target node it
    revised, the byte-identity guard result, a timestamp, and a git revert reference. Autonomy with a trail."""

    lesson: str
    target: str
    guard_result: bool
    timestamp: str
    revert_ref: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


def auto_apply_revise(
    lesson: Node,
    elig: ReviseEligibility,
    guard: Callable[[], bool],
    *,
    timestamp: str,
    revert_ref: str,
) -> Optional[ReviseAudit]:
    """FR-2/FR-6 — apply an ``auto``-classified revise **through** the byte-identity ``guard`` (fail-closed).

    ``guard`` applies the revise and returns whether the generated product is proven byte-identical.
    Returns a :class:`ReviseAudit` ONLY when the tier is ``auto`` AND the guard proves the product
    unchanged; otherwise ``None`` (→ human proposal) — a mis-classification whose application changes the
    product is caught by the guard and downgraded, never shipped. This function never mutates the product
    itself; the guard owns the apply, so auto-apply is impossible without passing the guard.
    """
    if classify_revise_tier(elig) != TIER_AUTO:
        return None                                    # FR-5 fail-safe → human
    if guard() is not True:                            # FR-2 enforce, not declare: apply THROUGH the guard
        return None                                    # fail-closed: product changed → downgrade to human
    edges = revises_edges(lesson)
    target = edges[0].from_key if edges else ""
    return ReviseAudit(lesson=lesson.key, target=target, guard_result=True,
                       timestamp=timestamp, revert_ref=revert_ref)
