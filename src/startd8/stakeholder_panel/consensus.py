# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""#6 — Consensus / divergence signal over a facilitation's independent R1 answers.

A **deterministic, $0** measure of how much the personas' independent first-take (round R1) answers
*diverge textually*. It is a COARSE, **synthetic** signal — lexical overlap is not semantic agreement
(two personas can agree in different words), so this flags "these takes are worded very differently →
look closer", it does **not** claim the stakeholders agreed. Honest framing is load-bearing (FR-7).

Derived on read from the already-persisted R1 entries (Mottainai — no new persisted field, no drift,
works on old transcripts). Challengers (adversary/skeptic) are *prompted* to diverge, so the headline
is computed over the NON-challenger personas (FR-4).

The scorer is behind a ``method`` seam (FR-9): the ``{label, score, n, basis}`` contract is
method-agnostic, so an embedding-backed semantic method can be added later without changing the poll
payload or the UI. ``basis`` names the method actually used.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

# Lexical bucket thresholds on the consensus SCORE (0–1, higher = more textually convergent). Calibrated
# for the low baseline overlap of short domain answers (plan R2): even convergent takes share few exact
# tokens, so "high" is deliberately not 0.5. Named constants so a future method sets its own thresholds.
_LEXICAL_HIGH = 0.34
_LEXICAL_MIXED = 0.16

# Very common tokens carry no divergence signal — dropped before scoring (a tiny, deterministic list;
# NOT a growing allowlist — it is the standard closed set of English function words for this scorer).
_STOPWORDS = frozenset(
    "a an the and or but if then else of to in on for with without at by from as is are was were be "
    "been being this that these those it its we you they i he she them our your their my me us do does "
    "did not no so than too very can could should would will shall may might must have has had".split()
)
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> List[str]:
    """Lowercased word tokens with stopwords + 1-char noise removed (deterministic)."""
    return [t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) > 1 and t not in _STOPWORDS]


def _cosine(a: Dict[str, int], b: Dict[str, int]) -> float:
    """Cosine similarity of two term-count vectors (0–1). Empty vector → 0."""
    if not a or not b:
        return 0.0
    common = set(a) & set(b)
    dot = sum(a[t] * b[t] for t in common)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _term_counts(text: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for t in _tokens(text):
        counts[t] = counts.get(t, 0) + 1
    return counts


def _lexical_score(texts: Sequence[str]) -> float:
    """Mean pairwise token cosine across the answers (0–1). Order-independent."""
    vecs = [_term_counts(t) for t in texts]
    n = len(vecs)
    if n < 2:
        return 0.0
    sims = [_cosine(vecs[i], vecs[j]) for i in range(n) for j in range(i + 1, n)]
    return sum(sims) / len(sims) if sims else 0.0


def _bucket(score: float) -> str:
    if score >= _LEXICAL_HIGH:
        return "high"
    if score >= _LEXICAL_MIXED:
        return "mixed"
    return "low"


@dataclass(frozen=True)
class ConsensusResult:
    """The consensus signal. ``label`` ∈ {high, mixed, low, n/a}; ``score`` is None when n/a."""

    label: str
    score: Optional[float]
    n: int  # rateable (non-challenger) personas the signal was computed over
    basis: str  # the scorer used, e.g. "lexical-r1" — names the method for auditability (FR-7/FR-9)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "label": self.label,
            "score": (round(self.score, 4) if self.score is not None else None),
            "n": self.n,
            "basis": self.basis,
        }


def _na(n: int, basis: str) -> ConsensusResult:
    return ConsensusResult(label="n/a", score=None, n=n, basis=basis)


def _r1_texts(rounds: Any, exclude_role_ids: frozenset) -> List[str]:
    """Collect the non-challenger R1 answer texts from a transcript's rounds (dicts OR PanelRound)."""
    texts: List[str] = []
    for rnd in rounds or []:
        rid = rnd.get("round_id") if isinstance(rnd, dict) else getattr(rnd, "round_id", "")
        if rid != "R1":
            continue
        entries = rnd.get("entries") if isinstance(rnd, dict) else getattr(rnd, "entries", [])
        for e in entries or []:
            role_id = e.get("role_id") if isinstance(e, dict) else getattr(e, "role_id", "")
            text = e.get("text") if isinstance(e, dict) else getattr(e, "text", "")
            if role_id in exclude_role_ids:
                continue
            if (text or "").strip():
                texts.append(text)
    return texts


def compute_consensus(
    rounds: Any,
    *,
    exclude_role_ids: frozenset = frozenset(),
    method: str = "lexical",
) -> ConsensusResult:
    """Consensus over the R1 (independent) answers, excluding challengers (FR-3/FR-4).

    ``rounds`` accepts either the raw transcript round dicts or typed ``PanelRound`` objects. ``method``
    selects the scorer (FR-9 seam); only ``"lexical"`` is implemented — an unknown method degrades to
    ``n/a`` (never raises). ≤1 rateable answer → ``n/a`` (no divergence is definable)."""
    basis = f"{method}-r1"
    texts = _r1_texts(rounds, exclude_role_ids)
    if len(texts) < 2:
        return _na(len(texts), basis)
    if method != "lexical":  # the seam — future "embedding" method plugs in here
        return _na(len(texts), basis)
    score = _lexical_score(texts)
    return ConsensusResult(label=_bucket(score), score=score, n=len(texts), basis=basis)
