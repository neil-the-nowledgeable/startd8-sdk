"""Item 4 wiring: ground-truth oracle factory + SDK-mechanism-FDE compose."""

from __future__ import annotations

import pytest

from startd8.sapper.fde_bridge import FDE_AVAILABLE, compose_with_fde_preflight
from startd8.sapper.ground_truth import (
    GroundTruthQuestion,
    GroundTruthVerdict,
    NullOracle,
    oracle_for_project,
)
from startd8.sapper.models import (
    AssumptionKind,
    AssumptionVerdict,
    FrictionFinding,
    FrictionReport,
    Severity,
    avoidable_cost_stage,
    finding_fingerprint,
)

pytestmark = pytest.mark.unit

requires_fde = pytest.mark.skipif(not FDE_AVAILABLE, reason="startd8.fde package not available")


# --- 4a: oracle factory -------------------------------------------------------


def test_oracle_for_nonexistent_project_falls_back_to_null():
    assert isinstance(oracle_for_project("/no/such/dir"), NullOracle)


def test_oracle_for_python_only_project_omits(tmp_path):
    # A pure-Python project has no Prisma/TS → ProjectKnowledge is omissions-only → OMIT (honest).
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "tables.py").write_text("class Job:\n    id: str = ''\n")
    oracle = oracle_for_project(str(tmp_path))
    ans = oracle.answer(
        GroundTruthQuestion(assumption_id="a", kind=AssumptionKind.MODULE_SOURCE, claim="c", module="app.x")
    )
    assert ans.verdict is GroundTruthVerdict.OMIT


# --- 4c: compose with the SDK-mechanism FDE -----------------------------------


def _sapper_report():
    return FrictionReport(
        findings=[
            FrictionFinding(
                id="f1",
                kind=AssumptionKind.MODULE_SOURCE,
                verdict=AssumptionVerdict.REFUTED,
                severity=Severity.MEDIUM,
                avoidable_cost_stage=avoidable_cost_stage(AssumptionKind.MODULE_SOURCE),
                fingerprint=finding_fingerprint(AssumptionKind.MODULE_SOURCE, "app/jobs.py", "Match"),
                file="app/jobs.py",
                expected="Match in app.tables",
                found="absent",
            )
        ]
    )


@requires_fde
def test_compose_merges_mechanism_and_observed():
    from startd8.fde.models import ClaimLabel, FdePreflightReport, LabeledClaim, Landmine

    fde_report = FdePreflightReport(
        generated_at="2026-01-01T00:00:00Z",
        sdk_version="0.4.0",
        landmines=[
            Landmine(
                landmine_id="lm1",
                track=2,
                severity="high",
                title="routes to micro-prime",
                assumption="plan assumes lead-tier generation",
                mechanism=LabeledClaim(
                    label=ClaimLabel.MECHANISM,
                    text="classify_tier() → micro_prime; convention injection bypassed",
                    source="complexity/classifier.py",
                ),
            )
        ],
    )
    composed = compose_with_fde_preflight(_sapper_report(), fde_report)
    assert composed["kind"] == "fde-sapper-composed"
    assert composed["summary"]["mechanism_count"] == 1     # the FDE landmine (root cause)
    assert composed["summary"]["observed_count"] == 1      # the Sapper refutation (symptom)
    assert "Match" in composed["observed_findings"][0]["text"]
    assert "micro-prime" in composed["mechanism_landmines"][0]["title"]
