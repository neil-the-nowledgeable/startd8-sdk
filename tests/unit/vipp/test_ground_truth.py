# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""M1 ground-truth consumption tests (FR-7, FR-8).

Covers the two distinct Sapper inputs: the live oracle (net-new answer→claim adapter) and the
in-process FrictionReport (thin to_observed_claims wrapper); OMIT-yields-nothing (never fabricate),
oracle-failure degradation, and the SAPPER_AVAILABLE graceful-degradation guard.
"""

from __future__ import annotations

from startd8.fde.models import ClaimLabel
from startd8.sapper.ground_truth import (
    GroundTruthAnswer,
    GroundTruthQuestion,
    GroundTruthVerdict,
)
from startd8.sapper.models import (
    AssumptionKind,
    AssumptionVerdict,
    AvoidableCostStage,
    FrictionFinding,
    FrictionReport,
    Severity,
)
from startd8.vipp import ground_truth as gt


def _q(
    symbol: str, *, kind: AssumptionKind = AssumptionKind.FIELD_AUTHORITY
) -> GroundTruthQuestion:
    return GroundTruthQuestion(
        assumption_id=symbol, kind=kind, claim=f"{symbol} exists", symbol=symbol
    )


class _ScriptedOracle:
    """A GroundTruthQuery that returns a scripted answer keyed by question.symbol."""

    def __init__(self, by_symbol):
        self._by = by_symbol

    def answer(self, question):
        return self._by[question.symbol]


# --- the net-new oracle → claim adapter (FR-7) ----------------------------------------------------


def test_observed_from_oracle_maps_validated_and_refuted_and_drops_omit():
    qv, qr, qo = _q("Profile.email"), _q("Profile.headlne"), _q("Profile.unknown")
    oracle = _ScriptedOracle(
        {
            "Profile.email": GroundTruthAnswer(
                GroundTruthVerdict.VALIDATED, evidence="exists", source="pk.field_sets"
            ),
            "Profile.headlne": GroundTruthAnswer(
                GroundTruthVerdict.REFUTED,
                evidence="not in fields",
                source="pk.field_sets",
            ),
            "Profile.unknown": GroundTruthAnswer.omit("no field authority"),
        }
    )

    claims = gt.observed_from_oracle(oracle, [qv, qr, qo])

    assert len(claims) == 2  # OMIT yields nothing (never fabricate)
    by_id = {c.claim_id: c for c in claims}
    # claim_id is the stable question fingerprint
    assert set(by_id) == {qv.fingerprint(), qr.fingerprint()}
    validated = by_id[qv.fingerprint()]
    assert validated.label is ClaimLabel.OBSERVED
    assert "VALIDATED" in validated.text and validated.qualifier == ""
    refuted = by_id[qr.fingerprint()]
    assert refuted.label is ClaimLabel.OBSERVED
    assert "REFUTED" in refuted.text and refuted.qualifier == "conflict"
    # The shared FDE tag renders the conflict qualifier.
    assert refuted.tag() == "OBSERVED (project, conflict)"


def test_answer_to_observed_claim_omit_is_none():
    assert gt.answer_to_observed_claim(_q("X.y"), GroundTruthAnswer.omit()) is None


def test_observed_from_oracle_swallows_oracle_failure():
    class _Boom:
        def answer(self, question):
            raise RuntimeError("boom")

    assert gt.observed_from_oracle(_Boom(), [_q("a")]) == []


# --- the in-process FrictionReport bridge (FR-7) --------------------------------------------------


def test_observed_from_report_wraps_to_observed_claims_and_skips_validated():
    refuted = FrictionFinding(
        id="f1",
        kind=AssumptionKind.FIELD_AUTHORITY,
        verdict=AssumptionVerdict.REFUTED,
        severity=Severity.HIGH,
        avoidable_cost_stage=AvoidableCostStage.INTEGRATION,
        fingerprint="fp-deadbeef",
        file="app/models.py",
        line=10,
        expected="Profile.headline",
        found="headlne",
    )
    validated = FrictionFinding(
        id="f2",
        kind=AssumptionKind.FIELD_AUTHORITY,
        verdict=AssumptionVerdict.VALIDATED,
        severity=Severity.LOW,
        avoidable_cost_stage=AvoidableCostStage.INTEGRATION,
        fingerprint="fp-cafef00d",
        file="app/models.py",
        line=11,
        expected="Profile.email",
        found="email",
    )
    claims = gt.observed_from_report(FrictionReport(findings=[refuted, validated]))

    assert len(claims) == 1  # VALIDATED is skipped by the bridge
    assert claims[0].label is ClaimLabel.OBSERVED
    assert claims[0].claim_id == "fp-deadbeef"  # claim_id == finding fingerprint


# --- graceful degradation (FR-8) ------------------------------------------------------------------


def test_degrades_to_empty_when_sapper_absent(monkeypatch):
    monkeypatch.setattr(gt, "SAPPER_AVAILABLE", False)
    assert gt.load_observed_claims("/tmp/whatever", [_q("a")]) == []
    assert gt.observed_from_report(object()) == []


def test_load_observed_claims_on_bare_project_omits_and_fabricates_nothing(tmp_path):
    # A bare dir has no controlled corpus / Prisma authority → oracle OMITs → no OBSERVED claims.
    claims = gt.load_observed_claims(str(tmp_path), [_q("Profile.email")])
    assert claims == []


def test_load_observed_claims_on_missing_dir_degrades(tmp_path):
    # oracle_for_project returns a NullOracle for a non-existent dir → OMIT → [].
    assert gt.load_observed_claims(str(tmp_path / "does-not-exist"), [_q("a")]) == []
