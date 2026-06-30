# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""VIPP ground-truth consumption (FR-7, FR-8) — **consume Sapper, don't re-implement**.

Two distinct Sapper inputs feed the VIPP's OBSERVED(project) evidence (CRP R1 A-F1/S1/S2 — these are
*different* interfaces, not one "consume"):

1. **The live, queryable oracle** — ``oracle_for_project(project_root) -> GroundTruthQuery`` whose
   only method is ``answer(GroundTruthQuestion) -> GroundTruthAnswer`` (VALIDATED/REFUTED/OMIT). The
   oracle returns *answers, not claims*, so this module owns the **net-new** ``answer →
   LabeledClaim(OBSERVED)`` adapter. This is the PRIMARY path: in-process, no disk dependency.
2. **An in-process Sapper ``FrictionReport``** — wrapped through the existing
   ``sapper.fde_bridge.to_observed_claims`` bridge (which skips VALIDATED and sets
   ``claim_id = finding.fingerprint``).

Dependency direction is one-way — ``vipp`` → ``sapper``/``fde`` — never the reverse (FR-8). A
``SAPPER_AVAILABLE`` guard degrades to an **empty** OBSERVED set when Sapper is absent (mirror
``sapper.fde_bridge.FDE_AVAILABLE``). Per Lesson L10-#41 (incomplete-vs-incorrect), absence degrades
the *narrative* only: the VIPP **never fabricates** an OBSERVED claim — an OMIT / timeout / missing
oracle yields **no** claim, and the FR-4 OMIT-default ACCEPT handles the proposal downstream.
"""

from __future__ import annotations

from typing import Any, List, Optional

from .models import ClaimLabel, LabeledClaim, oneline

try:  # Sapper may not be installed in every deployment; degrade gracefully (FR-8).
    from startd8.sapper.fde_bridge import to_observed_claims
    from startd8.sapper.ground_truth import GroundTruthVerdict, oracle_for_project

    SAPPER_AVAILABLE = True
except Exception:  # pragma: no cover - exercised only without the sapper package
    to_observed_claims = None  # type: ignore[assignment]
    GroundTruthVerdict = None  # type: ignore[assignment]
    oracle_for_project = None  # type: ignore[assignment]
    SAPPER_AVAILABLE = False


def answer_to_observed_claim(question: Any, answer: Any) -> Optional[LabeledClaim]:
    """Map one ``GroundTruthAnswer`` → an OBSERVED ``LabeledClaim`` (None for OMIT — never fabricate).

    VALIDATED/REFUTED carry project authority and become claims; **OMIT** means "no ground truth", so
    we emit **nothing** and let the FR-4 OMIT-default ACCEPT handle the proposal (Lesson L10-#41). A
    REFUTED answer is the project's evidence *in conflict* with the proposal — tagged via the claim
    ``qualifier`` so the FDE label vocabulary renders it as ``OBSERVED (project, conflict)``.
    ``claim_id`` reuses the question fingerprint so the same misalignment is stable across runs.
    """
    if GroundTruthVerdict is not None and answer.verdict is GroundTruthVerdict.OMIT:
        return None
    if str(getattr(answer.verdict, "value", answer.verdict)).lower() == "omit":
        return None
    is_refuted = (
        str(getattr(answer.verdict, "value", answer.verdict)).lower() == "refuted"
    )
    verdict_tag = str(getattr(answer.verdict, "value", answer.verdict)).upper()
    text = f"[{verdict_tag}] {question.claim}"
    if getattr(answer, "evidence", ""):
        text += f" — {answer.evidence}"
    # Collapse newlines: question.claim/evidence carry host-controlled symbols; a newline would
    # split this into a second untagged bullet and crash the FR-21 label gate (code-review H1).
    return LabeledClaim(
        label=ClaimLabel.OBSERVED,
        text=oneline(text),
        source=oneline(
            f"sapper:{getattr(answer, 'source', '') or question.kind.value}"
        ),
        claim_id=question.fingerprint(),
        qualifier="conflict" if is_refuted else "",
    )


def observed_from_oracle(oracle: Any, questions: List[Any]) -> List[LabeledClaim]:
    """Answer each question against the live oracle, mapping non-OMIT answers to OBSERVED claims.

    An oracle failure (incl. ``GroundTruthTimeout``) on a single question is degraded to **no claim**
    for that question — distinct from OMIT in origin, but identical in the no-fabrication rule — and
    never propagates as an exception into the negotiation (FR-7).
    """
    claims: List[LabeledClaim] = []
    for q in questions:
        try:
            ans = oracle.answer(q)
        except Exception:
            continue
        claim = answer_to_observed_claim(q, ans)
        if claim is not None:
            claims.append(claim)
    return claims


def observed_from_report(report: Any) -> List[LabeledClaim]:
    """Wrap an in-process Sapper ``FrictionReport`` through the existing OBSERVED bridge (FR-7).

    Thin pass-through to ``sapper.fde_bridge.to_observed_claims`` (skips VALIDATED findings; sets
    ``claim_id = finding.fingerprint``). Returns ``[]`` when Sapper is unavailable.
    """
    if not SAPPER_AVAILABLE or to_observed_claims is None:
        return []
    return list(to_observed_claims(report))


def build_oracle(project_root: Any) -> Optional[Any]:
    """Build the live project ground-truth oracle, or ``None`` when Sapper is unavailable (FR-7/8).

    Returned object satisfies the ``GroundTruthQuery`` contract (``.answer(question)``) — the
    negotiation core (``evaluate.evaluate_envelope``) queries it per proposal. Never raises.
    """
    if not SAPPER_AVAILABLE or oracle_for_project is None:
        return None
    try:
        return oracle_for_project(str(project_root))
    except Exception:
        return None


def load_observed_claims(project_root: Any, questions: List[Any]) -> List[LabeledClaim]:
    """Top-level: build the live oracle for ``project_root`` and answer ``questions`` (FR-7).

    The ``SAPPER_AVAILABLE`` guard degrades to ``[]`` (narrative-only); ``oracle_for_project`` never
    raises into the caller, and a build failure also degrades to ``[]``. The VIPP never fabricates an
    OBSERVED claim when ground truth is unavailable.
    """
    if not SAPPER_AVAILABLE or oracle_for_project is None:
        return []
    try:
        oracle = oracle_for_project(str(project_root))
    except Exception:
        return []
    return observed_from_oracle(oracle, questions)
