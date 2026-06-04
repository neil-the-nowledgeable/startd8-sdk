"""Phase 0 — Sapper model unit tests (FR-SAP-1/2/3). Pure, no external deps."""

from __future__ import annotations

import pytest

from startd8.sapper.models import (
    AVOIDABLE_COST_STAGE,
    Assumption,
    AssumptionKind,
    AssumptionVerdict,
    AvoidableCostStage,
    FrictionFinding,
    FrictionReport,
    Severity,
    UnresolvedReason,
    ValidatorClass,
    avoidable_cost_stage,
    finding_fingerprint,
    rank_findings,
)

pytestmark = pytest.mark.unit


def _finding(
    fid: str,
    kind: AssumptionKind,
    *,
    verdict=AssumptionVerdict.REFUTED,
    severity=Severity.MEDIUM,
    reason=None,
    shared_file=False,
    file="app/x.py",
    symbol="X",
) -> FrictionFinding:
    return FrictionFinding(
        id=fid,
        kind=kind,
        verdict=verdict,
        severity=severity,
        avoidable_cost_stage=avoidable_cost_stage(kind, shared_file=shared_file),
        fingerprint=finding_fingerprint(kind, file, symbol),
        file=file,
        reason=reason,
    )


# --- avoidable-cost mapping (FR-SAP-3, R1-F1/F2) -------------------------------


def test_every_kind_maps_to_exactly_one_stage():
    for kind in AssumptionKind:
        stage = avoidable_cost_stage(kind)
        assert isinstance(stage, AvoidableCostStage)


def test_mapping_table_matches_spec():
    assert AVOIDABLE_COST_STAGE[AssumptionKind.IMPORT_AVAILABILITY] is AvoidableCostStage.REPAIR
    assert AVOIDABLE_COST_STAGE[AssumptionKind.MODULE_SOURCE] is AvoidableCostStage.INTEGRATION
    assert AVOIDABLE_COST_STAGE[AssumptionKind.FRAMEWORK_IDIOM] is AvoidableCostStage.BOOT
    assert AVOIDABLE_COST_STAGE[AssumptionKind.DOMAIN_RULE] is AvoidableCostStage.CROSS_FEATURE_CASCADE


def test_unmapped_kind_defaults_to_integration_not_raises():
    # Simulate a kind absent from the table by clearing one mapping locally.
    # avoidable_cost_stage falls back to INTEGRATION via .get default.
    bogus = AssumptionKind.REACHABILITY
    saved = AVOIDABLE_COST_STAGE.pop(bogus)
    try:
        assert avoidable_cost_stage(bogus) is AvoidableCostStage.INTEGRATION
    finally:
        AVOIDABLE_COST_STAGE[bogus] = saved


def test_shared_file_escalates_to_cross_feature_cascade():
    # A repair-class kind on a shared file escalates (RUN-032 cascade).
    assert avoidable_cost_stage(AssumptionKind.IMPORT_AVAILABILITY) is AvoidableCostStage.REPAIR
    assert (
        avoidable_cost_stage(AssumptionKind.IMPORT_AVAILABILITY, shared_file=True)
        is AvoidableCostStage.CROSS_FEATURE_CASCADE
    )


# --- ranking determinism (FR-SAP-3) -------------------------------------------


def test_rank_orders_by_cost_descending():
    findings = [
        _finding("a", AssumptionKind.IMPORT_AVAILABILITY),       # repair (0)
        _finding("b", AssumptionKind.DOMAIN_RULE),               # cascade (3)
        _finding("c", AssumptionKind.FRAMEWORK_IDIOM),           # boot (2)
        _finding("d", AssumptionKind.MODULE_SOURCE),             # integration (1)
    ]
    ranked = rank_findings(findings)
    assert [f.id for f in ranked] == ["b", "c", "d", "a"]


def test_rank_tiebreak_severity_then_id():
    # All same stage (integration); tie-break by severity desc, then id asc.
    findings = [
        _finding("z", AssumptionKind.MODULE_SOURCE, severity=Severity.LOW),
        _finding("m", AssumptionKind.MODULE_SOURCE, severity=Severity.HIGH),
        _finding("a", AssumptionKind.MODULE_SOURCE, severity=Severity.HIGH),
    ]
    ranked = rank_findings(findings)
    # both HIGH first (a before m by id), then LOW
    assert [f.id for f in ranked] == ["a", "m", "z"]


def test_rank_is_stable_and_deterministic():
    findings = [_finding(f"f{i}", AssumptionKind.MODULE_SOURCE) for i in range(5)]
    r1 = [f.id for f in rank_findings(findings)]
    r2 = [f.id for f in rank_findings(findings)]
    assert r1 == r2 == ["f0", "f1", "f2", "f3", "f4"]


# --- fingerprint stability (R3-F3) --------------------------------------------


def test_fingerprint_stable_across_calls_independent_of_line():
    fp1 = finding_fingerprint(AssumptionKind.MODULE_SOURCE, "app/jobs.py", "Match")
    fp2 = finding_fingerprint(AssumptionKind.MODULE_SOURCE, "app/jobs.py", "Match")
    assert fp1 == fp2
    # Different symbol → different fingerprint.
    assert fp1 != finding_fingerprint(AssumptionKind.MODULE_SOURCE, "app/jobs.py", "Other")


# --- UNRESOLVED reason invariant (FR-SAP-2) -----------------------------------


def test_unresolved_requires_reason():
    with pytest.raises(ValueError):
        _finding("x", AssumptionKind.FRAMEWORK_IDIOM, verdict=AssumptionVerdict.UNRESOLVED)


def test_non_unresolved_must_not_carry_reason():
    with pytest.raises(ValueError):
        _finding(
            "x",
            AssumptionKind.FRAMEWORK_IDIOM,
            verdict=AssumptionVerdict.REFUTED,
            reason=UnresolvedReason.NEEDS_RULING,
        )


def test_input_absent_and_authority_absent_are_distinct():
    assert UnresolvedReason.INPUT_ABSENT != UnresolvedReason.AUTHORITY_ABSENT
    f = _finding(
        "x",
        AssumptionKind.FRAMEWORK_IDIOM,
        verdict=AssumptionVerdict.UNRESOLVED,
        reason=UnresolvedReason.INPUT_ABSENT,
    )
    assert f.to_dict()["reason"] == "input_absent"


# --- report aggregation (FR-SAP-3/12) -----------------------------------------


def test_report_counts_rate_and_breakdown():
    report = FrictionReport(
        findings=[
            _finding("a", AssumptionKind.IMPORT_AVAILABILITY),  # refuted
            _finding(
                "b",
                AssumptionKind.FRAMEWORK_IDIOM,
                verdict=AssumptionVerdict.UNRESOLVED,
                reason=UnresolvedReason.NEEDS_RULING,
            ),
            _finding(
                "c",
                AssumptionKind.ORM_IDIOM,
                verdict=AssumptionVerdict.UNRESOLVED,
                reason=UnresolvedReason.BORE_DEGRADED,
            ),
        ]
    )
    assert report.counts() == {"validated": 0, "refuted": 1, "unresolved": 2}
    assert report.unresolved_rate() == round(2 / 3, 4)
    assert report.reason_breakdown() == {"needs_ruling": 1, "bore_degraded": 1}


def test_empty_report_rate_zero_and_markdown_clean():
    report = FrictionReport()
    assert report.unresolved_rate() == 0.0
    assert "No friction findings" in report.to_markdown()


def test_report_json_roundtrip_has_schema_version():
    import json

    report = FrictionReport(findings=[_finding("a", AssumptionKind.MODULE_SOURCE)])
    data = json.loads(report.to_json())
    assert data["schema_version"] == "1.0.0"
    assert data["findings"][0]["fingerprint"]
    assert "validator_class" not in data["findings"][0] or data["findings"][0].get("validator_class")
