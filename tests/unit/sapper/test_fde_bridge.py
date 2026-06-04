"""Sapper → FDE compose-seam tests (Option A reconciliation)."""

from __future__ import annotations

import pytest

from startd8.sapper.fde_bridge import FDE_AVAILABLE, to_observed_claims
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


def _report():
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
                line=5,
                expected="Match in app.tables",
                found="absent",
            ),
        ]
    )


@requires_fde
def test_bridge_maps_findings_to_observed_labeled_claims():
    from startd8.fde.models import ClaimLabel

    claims = to_observed_claims(_report())
    assert len(claims) == 1
    c = claims[0]
    assert c.label is ClaimLabel.OBSERVED
    assert "Match" in c.text
    assert c.source == "sapper:module_source"
    # claim_id reuses the finding fingerprint (stable, no invented claims)
    assert c.claim_id == _report().findings[0].fingerprint


@requires_fde
def test_bridge_skips_validated_findings():
    report = FrictionReport(findings=[])
    assert to_observed_claims(report) == []
