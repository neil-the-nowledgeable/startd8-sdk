"""Next-action ranking (R2-S3 / FR-11) — a deterministic function of M1/M2 state.

Both surfaces (web M4, TUI M5) call this, so they recommend the **same** next action — the parity
guarantee for the guided experience. The ranking is:

  1. readiness blockers          (a gap the cascade itself reports — highest leverage)
  2. author-actionable gaps      (BLOCKED extraction fields — required, not yet satisfiable as-is)
  3. defaulted values to review  (REVIEW — provenance-critical estimates, FR-NEW-5)
  4. done                        (no blocking gaps remain)

Ties within a tier break by the canonical, byte-stable field-identity order (and readiness blockers
arrive pre-ordered by the wireframe's section order).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from .readiness import ReadinessView
from .state import Attention, KickoffState

KIND_BLOCKER = "resolve_blocker"
KIND_FILL = "fill_field"
KIND_REVIEW = "review_default"
KIND_DONE = "done"

# ── Shared subject vocabulary (FR-NU-4 / CRP R1-S2) ────────────────────────────────────────────────
# ONE set of subject constants that both `blocker_subject` (readiness sections) and `subject_for_stage`
# (RedCarpet gates/stages) resolve to, so the two crosswalks cannot drift apart in vocabulary.
SUBJECT_DATA_MODEL = "data_model"
SUBJECT_MANIFESTS = "manifests"
SUBJECT_VALUE_INPUTS = "value_inputs"
SUBJECTS = (SUBJECT_DATA_MODEL, SUBJECT_MANIFESTS, SUBJECT_VALUE_INPUTS)

# RedCarpet stage / cascade-gate → subject (the playbook side of the crosswalk).
_STAGE_SUBJECT: dict = {
    "schema": SUBJECT_DATA_MODEL, "data_model": SUBJECT_DATA_MODEL,
    "app": SUBJECT_MANIFESTS, "pages": SUBJECT_MANIFESTS, "views": SUBJECT_MANIFESTS,
    "manifests": SUBJECT_MANIFESTS,
    "value_inputs": SUBJECT_VALUE_INPUTS,
}

# The generic non-empty detail fallback (was concierge's fixed blocker copy) — CRP R1-S3.
_BLOCKER_DETAIL_FALLBACK = "Fill the kickoff inputs the cascade still needs."


def _normalize_blockers(readiness: Any) -> tuple:
    """Accept a ``ReadinessView`` (``.blockers``), a raw ``{"blockers": [...]}`` Mapping, or ``None``
    (CRP R1-S6). Returns the blockers tuple, or ``()`` — never raises."""
    if readiness is None:
        return ()
    blockers = getattr(readiness, "blockers", None)
    if blockers is None and isinstance(readiness, Mapping):
        blockers = readiness.get("blockers")
    return tuple(blockers or ())


def blocker_cta(readiness: Any) -> Optional[NextAction]:
    """The single Tier-1 readiness-blocker → CTA formatter (FR-NU-2). The two CTA recommenders
    (`next_action` Tier-1 and the concierge blocker branch) call this so a blocker reads identically.
    Returns ``None`` when there are no blockers (callers fall through to their no-blocker branch)."""
    blockers = _normalize_blockers(readiness)
    if not blockers:
        return None
    b = dict(blockers[0])
    section = str(b.get("section") or "unknown")
    detail = str(b.get("consequence") or b.get("status") or "") or _BLOCKER_DETAIL_FALLBACK
    return NextAction(kind=KIND_BLOCKER, title=f"Resolve readiness blocker: {section}", detail=detail)


def _readiness_map(readiness: Any) -> dict:
    """The raw per-generator readiness map from a ``ReadinessView`` (``.readiness``) or a raw dict."""
    if readiness is None:
        return {}
    m = getattr(readiness, "readiness", None)
    if m is None and isinstance(readiness, Mapping):
        m = readiness.get("readiness")
    return dict(m or {}) if isinstance(m, Mapping) else {}


def not_buildable_cta(readiness: Any) -> Optional[NextAction]:
    """Blocker reframe: when a cascade GENERATOR is blocked (e.g. a missing/invalid schema), the
    project isn't buildable yet — resolve the root before anything downstream matters. Returns
    ``None`` when buildable (all generators ready), so callers fall through to the build-ready branch.
    Distinct from ``blocker_cta`` (which fires on invalid-manifest hard blockers)."""
    m = _readiness_map(readiness)
    blocked = {g: v for g, v in m.items() if str(v).strip() != "ready"}
    if not blocked:
        return None
    detail = "; ".join(f"{g}: {v}" for g, v in blocked.items())
    return NextAction(kind=KIND_BLOCKER, title="Not yet buildable — resolve the root", detail=detail)


def blocker_subject(cta_or_section: Any) -> Optional[str]:
    """Normalize a blocker to a shared subject (FR-NU-4), keying on the **root cause** — a schema-absent
    project fans out into Services/Entities/Forms/Views blockers whose consequence is "no contract → …",
    so those resolve to ``data_model`` (matching the playbook), not to their section name. Accepts a
    ``NextAction`` (blocker CTA — reads title+detail) or a raw section string. Returns a `SUBJECTS` value
    or ``None``."""
    if isinstance(cta_or_section, NextAction):
        section = cta_or_section.title.split(":", 1)[-1]
        text = f"{section} {cta_or_section.detail}"
    else:
        text = str(cta_or_section or "")
    t = text.lower()
    if any(k in t for k in ("no contract", "no schema", "data model", "schema", "entit")):
        return SUBJECT_DATA_MODEL
    if any(k in t for k in ("page", "nav", "view", "form", "manifest", "service")):
        return SUBJECT_MANIFESTS
    if any(k in t for k in ("content", "value input", "convention", "observability", "target")):
        return SUBJECT_VALUE_INPUTS
    return None


def subject_for_stage(stage: Optional[str]) -> Optional[str]:
    """RedCarpet stage/gate → shared subject (the playbook side, FR-NU-4). ``None`` if not a gate stage."""
    return _STAGE_SUBJECT.get(stage or "")


@dataclass(frozen=True)
class NextAction:
    kind: str
    title: str
    detail: str
    value_path: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "title": self.title, "detail": self.detail}
        if self.value_path is not None:
            d["value_path"] = self.value_path
        return d


def next_action(
    state: KickoffState,
    readiness: Optional[ReadinessView] = None,
) -> NextAction:
    """The single deterministic recommendation both surfaces render (R2-S3)."""
    # Tier 1 — readiness blockers (cascade-level gaps). FR-NU-2: via the shared formatter, so the
    # concierge blocker branch phrases this identically.
    cta = blocker_cta(readiness)
    if cta is not None:
        return cta

    # Tier 1.5 — not yet buildable (a generator is blocked, e.g. missing schema): resolve the root
    # before the author gaps below, which are downstream of it.
    nb = not_buildable_cta(readiness)
    if nb is not None:
        return nb

    # Tier 2 — author-actionable extraction gaps (already identity-sorted).
    blocked = state.blocked_fields()
    if blocked:
        f = blocked[0]
        return NextAction(
            kind=KIND_FILL,
            title=f"Fix {f.value_path}",
            detail=f.reason or f"{f.ambiguity}",
            value_path=f.value_path,
        )

    # Tier 3 — defaulted values that need human review (provenance-critical).
    review = [f for f in state.fields if f.attention == Attention.REVIEW]
    if review:
        f = review[0]
        return NextAction(
            kind=KIND_REVIEW,
            title=f"Review defaulted value: {f.value_path}",
            detail=f"current value: {f.value!r} (defaulted — confirm or change)",
            value_path=f.value_path,
        )

    return NextAction(
        kind=KIND_DONE, title="Ready to build",
        detail="Run `startd8 generate backend` — the $0 cascade can generate the app now.",
    )
