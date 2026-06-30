# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Deterministic negotiation core (FR-4) — the `$0`, no-LLM rule set.

``evaluate_envelope(envelope, oracle, *, extract=...)`` adjudicates each host proposal against
project ground truth and emits a source-labeled :class:`VippDisposition`. **Per-kind coverage is
honest** (CRP R1 A-S2 — the rule set was over-claimed in v0.1):

- ``capture`` — the ``value_path`` is a structured ``entity.field`` symbol, queried directly
  (FIELD_AUTHORITY). REFUTED → REJECT, or COUNTER when the oracle's evidence names a correction.
- ``schema`` / ``manifest`` — the entity lives in **free-text prose** (``params["brief"]`` /
  ``params["source"]``), so an injectable ``extract`` pulls candidate entity names first, each queried
  (IDENTITY_COLLISION; the Controlled Corpus adjudicates canonical/near-miss).
- ``instantiate`` / ``friction`` / ``brief`` — no entity to adjudicate → ACCEPT with a labeled
  "no adjudicable entity" claim.

OMIT / no-evidence → **ACCEPT** with an ``OBSERVED(…, qualifier="unavailable")`` claim (FR-4 default;
never a silent rubber-stamp, never a block; never fabricate — Lesson L10-#41). A malformed proposal →
REJECT(reason), never a crash (Lesson L13-#103). When Sapper is unavailable the whole envelope ACCEPTs
with a labeled "ground truth unavailable" claim.
"""

from __future__ import annotations

import re
from typing import Any, Callable, List, Optional

from .ground_truth import SAPPER_AVAILABLE, answer_to_observed_claim
from .models import (
    ClaimLabel,
    Decision,
    LabeledClaim,
    ProposalEnvelope,
    VippDisposition,
    oneline,
)

if SAPPER_AVAILABLE:  # pragma: no branch
    from startd8.sapper.ground_truth import GroundTruthQuestion, GroundTruthVerdict
    from startd8.sapper.models import AssumptionKind
else:  # pragma: no cover - only without sapper installed
    GroundTruthQuestion = None  # type: ignore[assignment]
    GroundTruthVerdict = None  # type: ignore[assignment]
    AssumptionKind = None  # type: ignore[assignment]

EntityExtractor = Callable[[str], List[str]]

# A light default entity extractor: PascalCase identifiers, minus common non-entity headers. It is a
# heuristic — inject a precise extractor (e.g. a real entity-graph parser) for production schemas.
_PASCAL = re.compile(r"\b([A-Z][A-Za-z0-9]+)\b")
_NON_ENTITY = frozenset(
    {"Entities", "Entity", "Fields", "Owned", "Coverage", "AI", "The", "PRD"}
)
# The oracle's REFUTED evidence names the correction, e.g. "Match → use Matches" / "closest is 'X'".
_CORRECTION = re.compile(r"(?:use|closest is)\s+['\"`]?([A-Za-z_][A-Za-z0-9_]*)")


def default_entity_extract(text: str) -> List[str]:
    out: List[str] = []
    for name in _PASCAL.findall(text or ""):
        if name not in out and name not in _NON_ENTITY:
            out.append(name)
    return out


def _verdict(answer: Any) -> str:
    return str(getattr(answer.verdict, "value", answer.verdict)).lower()


def _build_questions(proposal: Any, extract: EntityExtractor) -> List[Any]:
    """Per-kind question construction (raises on a malformed proposal → caller REJECTs)."""
    kind = proposal.kind
    params = proposal.params or {}
    if kind == "capture":
        value_path = params.get("value_path")
        if not value_path:
            raise ValueError("capture proposal missing 'value_path'")
        if "." not in str(value_path):
            # A capture value_path is an "entity.field" symbol by convention; a dotless one would
            # partition to an empty field name and yield a bogus REFUTED (code-review L1).
            raise ValueError(
                f"capture 'value_path' is not an entity.field symbol: {value_path!r}"
            )
        return [
            GroundTruthQuestion(
                assumption_id=proposal.id,
                kind=AssumptionKind.FIELD_AUTHORITY,
                claim=oneline(f"{value_path} is a project field"),
                symbol=str(value_path),
            )
        ]
    if kind in ("schema", "manifest"):
        prose = params.get("brief") or params.get("source") or ""
        return [
            GroundTruthQuestion(
                assumption_id=f"{proposal.id}:{entity}",
                kind=AssumptionKind.IDENTITY_COLLISION,
                claim=oneline(f"{entity} is a canonical entity"),
                symbol=entity,
            )
            for entity in extract(prose)
        ]
    # instantiate / friction / brief carry no adjudicable entity.
    return []


def _accept(proposal_id, seq, *, text, source, qualifier="") -> VippDisposition:
    return VippDisposition(
        proposal_id=proposal_id,
        decision=Decision.ACCEPT,
        envelope_seq=seq,
        claims=[
            LabeledClaim(
                label=ClaimLabel.OBSERVED,
                text=oneline(text),
                source=source,
                claim_id=proposal_id,
                qualifier=qualifier,
            )
        ],
    )


def _evaluate_one(
    proposal: Any, oracle: Any, seq: int, extract: EntityExtractor
) -> VippDisposition:
    questions = _build_questions(proposal, extract)
    if not questions:
        return _accept(
            proposal.id,
            seq,
            text=f"{proposal.kind}: no adjudicable entity in project ground truth",
            source="vipp:no-entity",
            qualifier="unavailable",
        )

    claims: List[LabeledClaim] = []
    refuted: List[Any] = []  # (question, answer)
    for q in questions:
        try:
            ans = oracle.answer(q)
        except Exception:
            continue  # oracle failure / timeout → no claim for this question (never fabricate)
        claim = answer_to_observed_claim(q, ans)
        if claim is None:  # OMIT
            continue
        claims.append(claim)
        if _verdict(ans) == "refuted":
            refuted.append((q, ans))

    if not claims:
        return _accept(
            proposal.id,
            seq,
            text=f"{proposal.kind}: no ground truth to adjudicate (all OMIT)",
            source="vipp:omit-default",
            qualifier="unavailable",
        )

    if refuted:
        _q, ans = refuted[0]
        reason = oneline(
            getattr(ans, "evidence", "") or "refuted by project ground truth"
        )
        counter = _try_counter(proposal, ans)
        if counter is not None:
            return VippDisposition(
                proposal_id=proposal.id,
                decision=Decision.COUNTER,
                envelope_seq=seq,
                reason=reason,
                counter_params=counter,
                claims=claims,
            )
        return VippDisposition(
            proposal_id=proposal.id,
            decision=Decision.REJECT,
            envelope_seq=seq,
            reason=reason,
            claims=claims,
        )

    # All non-OMIT answers are VALIDATED → confirmed ACCEPT, carrying the supporting claims.
    return VippDisposition(
        proposal_id=proposal.id,
        decision=Decision.ACCEPT,
        envelope_seq=seq,
        claims=claims,
    )


# Oracle sources that carry real schema/field authority — a COUNTER (which actively proposes a
# rename) must only be sourced from these, NOT from the Controlled Corpus. The CompositeOracle
# consults the corpus FIRST and resolves on the value_path's bare leaf, so a corpus near-miss on a
# field name could otherwise drive a confidently-wrong field rename (code-review M4). A corpus
# REFUTED still REJECTs (with its evidence), but never auto-COUNTERs.
_SCHEMA_AUTHORITY_SOURCES = ("project_knowledge", "field_sets", "interfaces")


def _try_counter(proposal: Any, answer: Any) -> Optional[dict]:
    """Best-effort deterministic COUNTER for ``capture`` when **schema authority** names a correction.

    Only ``capture`` (a structured ``value_path``) supports an amendment, and only when the refuting
    answer came from schema/field authority (not the corpus — M4). The correction is parsed from the
    oracle's REFUTED evidence ("… use X" / "closest is 'X'"). ``base_sha``/``kind`` are never amended
    (FR-5). Returns ``None`` (→ REJECT) when no correction is parseable or the source is not authoritative.
    """
    if proposal.kind != "capture":
        return None
    source = str(getattr(answer, "source", "") or "")
    if not any(tag in source for tag in _SCHEMA_AUTHORITY_SOURCES):
        return None
    m = _CORRECTION.search(getattr(answer, "evidence", "") or "")
    if not m:
        return None
    value_path = str((proposal.params or {}).get("value_path", ""))
    if "." not in value_path:
        return None
    corrected = value_path.rsplit(".", 1)[0] + "." + m.group(1)
    counter = dict(proposal.params or {})
    counter["value_path"] = corrected
    return counter


def evaluate_envelope(
    envelope: ProposalEnvelope,
    oracle: Any,
    *,
    extract: Optional[EntityExtractor] = None,
) -> List[VippDisposition]:
    """Adjudicate every proposal in ``envelope`` against ``oracle`` → source-labeled dispositions."""
    extract = extract or default_entity_extract
    seq = envelope.envelope_seq

    if not SAPPER_AVAILABLE or oracle is None:
        # Degrade: accept everything with a labeled "ground truth unavailable" claim (never fabricate).
        return [
            _accept(
                p.id,
                seq,
                text=f"{p.kind}: project ground truth unavailable",
                source="vipp:no-ground-truth",
                qualifier="unavailable",
            )
            for p in envelope.proposals
        ]

    dispositions: List[VippDisposition] = []
    for p in envelope.proposals:
        try:
            dispositions.append(_evaluate_one(p, oracle, seq, extract))
        except (
            Exception
        ) as exc:  # malformed proposal → REJECT, never crash (Lesson L13-#103)
            dispositions.append(
                VippDisposition(
                    proposal_id=p.id,
                    decision=Decision.REJECT,
                    envelope_seq=seq,
                    reason=f"malformed proposal: {exc}",
                    claims=[
                        LabeledClaim(
                            label=ClaimLabel.OBSERVED,
                            text=f"proposal {p.id!r} ({p.kind}) could not be evaluated",
                            source="vipp:malformed",
                            claim_id=p.id,
                            qualifier="unavailable",
                        )
                    ],
                )
            )
    return dispositions
