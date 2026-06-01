"""Deterministic nearest-match decision core for name repair (Inc 3, FR-3, NFR-3).

Pure functions, no I/O. Given an invented name and the authoritative candidate
set, decide whether to **rewrite** to a single high-confidence match or to
**abstain** — the abstain-default is the load-bearing safety invariant (NFR-3):
a wrong rename produces syntactically-valid, semantically-wrong code, the one
outcome worse than failing honestly.

There is intentionally **no** ``structural`` parameter (R4-S3): nothing in the
detection layer produces a "this is a presumed FK" signal, so a structural
invention like ``Metric.outcomeId`` is handled by the ``no_candidates`` branch
(it has no near-match among the model's real fields) rather than an unwireable
flag.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Iterable, List, Optional

# Abstain reason codes (also emitted as telemetry, FR-9).
NO_CANDIDATES = "no_candidates"
AMBIGUOUS_TIE = "ambiguous_tie"

# OQ-4 tuned against the run-011 set (empirically, see test_name_resolution).
# IMPLEMENTATION FINDING: the run-011 field inventions split into two classes —
#   * typo / substring  (`supportingEvidence`≈`evidence` @0.538, `descriptio`≈
#     `description` @0.95) — repairable by string similarity, and
#   * pure synonym       (`title`→`name`, `aiRefId`, `label`, `outcomeId`) whose
#     nearest real field scores 0.40–0.44 — NOT repairable by string similarity;
#     these correctly abstain (→ FAILED → LLM retry).
# 0.5 is the value that rewrites `supportingEvidence`→`evidence` while still
# abstaining on all four synonyms. Lowering further would risk false rewrites;
# the synonym class needs semantic/embedding matching (out of v1 scope).
DEFAULT_CUTOFF = 0.5
DEFAULT_MARGIN = 0.1


@dataclass(frozen=True)
class MatchDecision:
    """Outcome of a nearest-match decision."""

    decision: str  # "rewrite" | "abstain"
    target: Optional[str]
    similarity: float
    reason: str  # "" when rewrite; an abstain reason code otherwise

    @property
    def is_rewrite(self) -> bool:
        return self.decision == "rewrite"


def _ratio(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()


def best_match(
    invented: str,
    candidates: Iterable[str],
    *,
    cutoff: float = DEFAULT_CUTOFF,
    margin: float = DEFAULT_MARGIN,
) -> MatchDecision:
    """Decide the rewrite target for *invented* against *candidates*.

    Branching is fully determined by the count of candidates that clear *cutoff*:

    * **0** → abstain ``no_candidates`` (covers empty set and all-below-cutoff).
    * **1** → rewrite (no runner-up; the margin test is vacuously satisfied).
    * **2** → rewrite to the top match iff its similarity exceeds the runner-up
      by at least *margin*; otherwise abstain ``ambiguous_tie`` (equal scores,
      ``Δ = 0``, always abstain).
    """
    pool: List[str] = [c for c in candidates if c]
    matches = difflib.get_close_matches(invented, pool, n=2, cutoff=cutoff)

    if not matches:
        return MatchDecision("abstain", None, 0.0, NO_CANDIDATES)

    top = matches[0]
    top_score = _ratio(invented, top)

    if len(matches) == 1:
        return MatchDecision("rewrite", top, top_score, "")

    runner_up_score = _ratio(invented, matches[1])
    if (top_score - runner_up_score) >= margin:
        return MatchDecision("rewrite", top, top_score, "")
    return MatchDecision("abstain", None, top_score, AMBIGUOUS_TIE)
