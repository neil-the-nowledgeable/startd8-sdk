"""Data models for the Controlled Corpus (CONTROLLED_CORPUS_REQUIREMENTS FR-2/3/7/8).

Design for an idempotent, order-independent merge (the success criterion):
  - set-valued accumulators (surface_forms, source_run_ids)
  - dict-valued determinism observations keyed by run_id (re-merge overwrites its own key)
  - binding upgrade by a total SOURCE_PRECEDENCE order (max is order-independent)
  - maturity + determinism aggregates are PURE FUNCTIONS of the final accumulated state
So the corpus is byte-identical regardless of merge order, and re-merging a run is a no-op.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "Binding",
    "Determinism",
    "CorpusTerm",
    "TermObservation",
    "SCHEMA_VERSION",
    "MAX_CORPUS_SIZE",
    "SOURCE_PRECEDENCE",
    "CONFIDENCE_PRECEDENCE",
    "term_id_for",
    "classify_determinism",
]

SCHEMA_VERSION = "1.0.0"
MAX_CORPUS_SIZE = 5000

# R3-S1: EXTEND the canonical forward_manifest precedence rather than fork it, so
# corpus-sourced and manifest-sourced bindings resolve consistently. We import the
# base and add corpus-only labels; shared keys keep forward_manifest's values.
try:
    from startd8.forward_manifest_extractor import _SOURCE_PRECEDENCE as _FM_PREC
except Exception:  # pragma: no cover - defensive: never hard-fail corpus on FM import
    _FM_PREC = {"source-ast": 0, "deterministic": 1, "reference-ast": 2, "proto": 2, "human-yaml": 3}

SOURCE_PRECEDENCE: Dict[str, int] = {
    **_FM_PREC,                    # shared base (do NOT change shared values)
    "inferred": 1,                 # corpus extension: deterministically-observed
    "framework-conventions": 1,    # corpus extension
    "human": 3,                    # corpus extension: alias of human-yaml tier
}
# Invariant (R3-S1): every forward_manifest key keeps its value in the corpus table.
assert all(SOURCE_PRECEDENCE[k] == v for k, v in _FM_PREC.items())
CONFIDENCE_PRECEDENCE: Dict[str, int] = {"advisory": 0, "inferred": 1, "explicit": 2}

# Two-axis determinism thresholds (FR-8). Module constants (R1-F5: a single config
# point; externally tunable by patching these in one place).
_STABILITY_HIGH = 0.95
_REQSCORE_HIGH = 0.9
_REQSCORE_LOW = 0.7
_STABILITY_LOW = 0.7
_MIN_SAMPLES = 2   # R1-F5: a single observation is not evidence of determinism


def term_id_for(kind: str, canonical_key: str) -> str:
    """Stable id from the semantic key (kind, canonical_key)."""
    h = hashlib.sha256(f"{kind}::{canonical_key}".encode()).hexdigest()[:12]
    return f"{kind}:{h}"


def classify_determinism(
    stability: Optional[float], req_score: Optional[float], n_observations: Optional[int] = None,
) -> str:
    """Two-axis class (FR-8): structural stability AND semantic compliance.

    Refined per CRP R1 (rounds R1-F1/F5, R2-F2):
      - unobserved                       — no determinism signal yet
      - insufficient_samples             — observed but < _MIN_SAMPLES (R1-F5)
      - deterministic_candidate          — stable AND semantically compliant
      - deterministic_candidate_unscored — stable but NO requirement_score (R1-F1)
      - false_pass_risk                  — stable build, unmet requirement (SCR target)
      - needs_semantic_review            — stable build, mid requirement_score (R2-F2 split)
      - residue_corpus_gap               — structurally unstable
      - needs_more_runs                  — mid stability, more samples needed (R2-F2 split)
    """
    if stability is None:
        return "unobserved"
    if n_observations is not None and n_observations < _MIN_SAMPLES:
        return "insufficient_samples"
    if stability >= _STABILITY_HIGH:
        if req_score is None:
            return "deterministic_candidate_unscored"
        if req_score >= _REQSCORE_HIGH:
            return "deterministic_candidate"
        if req_score < _REQSCORE_LOW:
            return "false_pass_risk"
        return "needs_semantic_review"
    if stability < _STABILITY_LOW:
        return "residue_corpus_gap"
    return "needs_more_runs"


@dataclass
class Binding:
    """One language-specific code-construct realization of a term."""

    language: str
    construct_kind: str          # class | function | endpoint | config_key | file | ...
    construct_ref: str           # e.g. "src/emailservice/logger.py" or "EmailService.SendOrderConfirmation"
    source_reference: str = "inferred"  # for SOURCE_PRECEDENCE conflict resolution

    def key(self) -> tuple:
        return (self.language, self.construct_kind, self.construct_ref)

    def to_dict(self) -> Dict[str, Any]:
        return dict(language=self.language, construct_kind=self.construct_kind,
                    construct_ref=self.construct_ref, source_reference=self.source_reference)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Binding":
        return cls(language=d["language"], construct_kind=d["construct_kind"],
                   construct_ref=d["construct_ref"], source_reference=d.get("source_reference", "inferred"))


@dataclass
class Determinism:
    """Two-axis determinism, accumulated per-run (FR-7/8).

    observations: run_id -> {"success": bool, "requirement_score": float|None}
    Keyed by run_id so re-merging a run is idempotent and merge order is irrelevant.
    """

    observations: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def observe(self, run_id: str, success: bool, requirement_score: Optional[float],
                input_scope_id: str = "") -> None:
        self.observations[run_id] = {
            "success": bool(success), "requirement_score": requirement_score,
            "input_scope_id": input_scope_id,
        }

    @property
    def n_observations(self) -> int:
        return len(self.observations)

    def scopes(self) -> List[str]:
        return sorted({o.get("input_scope_id", "") for o in self.observations.values()})

    def _dominant_scope_obs(self) -> List[Dict[str, Any]]:
        """R4-F1: stability is only valid WITHIN an input-scope cluster. Compute over
        the dominant scope (most observations; ties broken by sorted scope id) so mixing
        e.g. 7-feature and 17-feature runs cannot poison a term's stability. Deterministic
        (count then sorted id) → order-independent."""
        if not self.observations:
            return []
        by_scope: Dict[str, List[Dict[str, Any]]] = {}
        for o in self.observations.values():
            by_scope.setdefault(o.get("input_scope_id", ""), []).append(o)
        dominant = max(sorted(by_scope), key=lambda s: len(by_scope[s]))
        return by_scope[dominant]

    @property
    def success_stability(self) -> Optional[float]:
        obs = self._dominant_scope_obs()
        if not obs:
            return None
        return round(sum(1 for o in obs if o["success"]) / len(obs), 4)

    @property
    def mean_requirement_score(self) -> Optional[float]:
        xs = [o["requirement_score"] for o in self._dominant_scope_obs()
              if isinstance(o["requirement_score"], (int, float))]
        return round(sum(xs) / len(xs), 4) if xs else None

    @property
    def last_slope(self) -> Optional[float]:
        """Stability trend over runs (deterministic: sorted by run_id)."""
        if len(self.observations) < 2:
            return None
        from startd8.utils.trend_math import linear_slope
        ordered = [1.0 if self.observations[r]["success"] else 0.0 for r in sorted(self.observations)]
        return linear_slope(ordered)

    @property
    def corpus_class(self) -> str:
        # min-sample guard applies to the dominant scope (where stability is computed)
        return classify_determinism(
            self.success_stability, self.mean_requirement_score, len(self._dominant_scope_obs()))

    def to_dict(self) -> Dict[str, Any]:
        return {"observations": self.observations}

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Determinism":
        return cls(observations=dict(d.get("observations", {})))


@dataclass
class TermObservation:
    """What an extractor emits for ONE term seen in ONE run (input to merge_run)."""

    kind: str
    canonical_key: str
    surface_form: str = ""
    bindings: List[Binding] = field(default_factory=list)
    confidence: str = "inferred"
    success: Optional[bool] = None            # determinism axis 1 (structural)
    requirement_score: Optional[float] = None  # determinism axis 2 (semantic)
    input_scope_id: str = ""                   # R4-F1: scope cluster for determinism


@dataclass
class CorpusTerm:
    """An accumulated controlled-vocabulary term (FR-2)."""

    term_id: str
    kind: str
    canonical_key: str
    surface_forms: List[str] = field(default_factory=list)
    bindings: List[Binding] = field(default_factory=list)
    confidence: str = "inferred"
    maturity: int = 1
    source_run_ids: List[str] = field(default_factory=list)
    determinism: Determinism = field(default_factory=Determinism)

    # ----- pure maturity function (FR-3): depends only on accumulated state -----
    def recompute_maturity(self) -> None:
        n_runs = len(set(self.source_run_ids))
        stab = self.determinism.success_stability
        req = self.determinism.mean_requirement_score
        # R1-F2/R1-S4: L3+ require OBSERVED stability (≥θ). A term with recurrence but
        # no determinism observations (e.g. a proto service term) caps at L2 — recurrence
        # validates that the term exists across runs, not that its binding generates stably.
        if self.confidence == "explicit" and n_runs >= 3 and stab == 1.0 and (req is None or req >= _REQSCORE_HIGH):
            self.maturity = 4  # canonical
        elif n_runs >= 3 and stab is not None and stab >= _STABILITY_HIGH:
            self.maturity = 3  # stable (requires observed stability)
        elif n_runs >= 2:
            self.maturity = 2  # cross-run-validated (recurrence only)
        else:
            self.maturity = 1  # extracted-once

    def to_dict(self) -> Dict[str, Any]:
        # R3-F2: canonical storage holds only DURABLE state. Derived fields
        # (corpus_class) are recomputed on load — never persisted (else they go
        # stale when thresholds change). Use as_debug_dict() for human inspection.
        return {
            "term_id": self.term_id,
            "kind": self.kind,
            "canonical_key": self.canonical_key,
            "surface_forms": sorted(self.surface_forms),
            "bindings": [b.to_dict() for b in sorted(self.bindings, key=lambda b: b.key())],
            "confidence": self.confidence,
            "maturity": self.maturity,
            "source_run_ids": sorted(set(self.source_run_ids)),
            "determinism": self.determinism.to_dict(),
        }

    def as_debug_dict(self) -> Dict[str, Any]:
        """Human-readable view incl. derived fields (NOT the canonical format)."""
        d = self.to_dict()
        d["corpus_class_computed"] = self.determinism.corpus_class
        d["_note"] = "corpus_class is a derived field — recomputed on load, not stored"
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CorpusTerm":
        t = cls(
            term_id=d["term_id"], kind=d["kind"], canonical_key=d["canonical_key"],
            surface_forms=list(d.get("surface_forms", [])),
            bindings=[Binding.from_dict(b) for b in d.get("bindings", [])],
            confidence=d.get("confidence", "inferred"),
            maturity=int(d.get("maturity", 1)),
            source_run_ids=list(d.get("source_run_ids", [])),
            determinism=Determinism.from_dict(d.get("determinism", {})),
        )
        return t
