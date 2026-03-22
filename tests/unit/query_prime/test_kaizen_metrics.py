"""Tests for query_prime.kaizen_metrics — L1 report builder + L3 scoring."""

from __future__ import annotations

import pytest

from startd8.complexity.models import ComplexityTier
from startd8.query_prime.kaizen_metrics import (
    QueryScoreWeights,
    build_verification_report,
    compute_query_security_score,
)
from startd8.query_prime.models import (
    QueryResult,
    SecurityCheckType,
    SecurityFinding,
    SecurityVerdict,
    SecurityVerificationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    work_item_id: str = "wi-1",
    verdict: SecurityVerdict = SecurityVerdict.PASS,
    findings: list | None = None,
    tier: ComplexityTier = ComplexityTier.SIMPLE,
    model: str = "template",
    cost: float = 0.0,
    escalations: int = 0,
) -> QueryResult:
    vr = SecurityVerificationResult(
        file_path="test.cs",
        verdict=verdict,
        checks_passed=3 if verdict == SecurityVerdict.PASS else 2,
        checks_failed=1 if verdict == SecurityVerdict.FAIL else 0,
        checks_warned=1 if verdict == SecurityVerdict.WARN else 0,
        findings=findings or [],
    )
    return QueryResult(
        work_item_id=work_item_id,
        code="SELECT 1",
        verification=vr,
        tier_used=tier,
        model_used=model,
        cost_usd=cost,
        escalations=escalations,
    )


def _injection_finding(db: str = "postgresql") -> SecurityFinding:
    return SecurityFinding(
        check_type=SecurityCheckType.INJECTION,
        severity="error",
        message="String interpolation in SQL",
        database=db,
        pattern_hash="abc123",
    )


def _credential_finding() -> SecurityFinding:
    return SecurityFinding(
        check_type=SecurityCheckType.CREDENTIAL_LEAKAGE,
        severity="error",
        message="Connection string logged",
        pattern_hash="def456",
    )


def _lifecycle_finding() -> SecurityFinding:
    return SecurityFinding(
        check_type=SecurityCheckType.LIFECYCLE,
        severity="warning",
        message="Per-request connection creation",
        pattern_hash="ghi789",
    )


# ---------------------------------------------------------------------------
# L3: Scoring tests
# ---------------------------------------------------------------------------


class TestComputeQuerySecurityScore:
    """Tests for compute_query_security_score."""

    def test_perfect_score(self):
        result = _make_result()
        score = compute_query_security_score(result)
        assert score == 1.0

    def test_injection_short_circuits_to_zero(self):
        result = _make_result(
            verdict=SecurityVerdict.FAIL,
            findings=[_injection_finding()],
        )
        score = compute_query_security_score(result)
        assert score == 0.0

    def test_credential_finding_reduces_score(self):
        result = _make_result(
            verdict=SecurityVerdict.FAIL,
            findings=[_credential_finding()],
        )
        score = compute_query_security_score(result)
        assert 0.0 < score < 1.0
        # Should lose credential_safety (0.25) and verification_pass (0.15) weights
        assert score == pytest.approx(0.60, abs=0.01)

    def test_lifecycle_finding_reduces_score(self):
        result = _make_result(
            verdict=SecurityVerdict.WARN,
            findings=[_lifecycle_finding()],
        )
        score = compute_query_security_score(result)
        assert 0.0 < score < 1.0
        # Loses lifecycle_compliance weight (0.15)
        assert score == pytest.approx(0.85, abs=0.01)

    def test_escalation_reduces_tier_score(self):
        result = _make_result(escalations=2)
        score = compute_query_security_score(result)
        # tier_efficiency: max(0, 1.0 - 2*0.33) = 0.34 → 0.10 * 0.34 = 0.034
        expected = 0.35 + 0.25 + 0.15 + 0.15 + 0.10 * max(0.0, 1.0 - 2 * 0.33)
        assert score == pytest.approx(expected, abs=0.01)

    def test_no_verification_returns_zero(self):
        result = QueryResult(work_item_id="wi-1")
        score = compute_query_security_score(result)
        assert score == 0.0

    def test_custom_weights(self):
        result = _make_result()
        weights = QueryScoreWeights(
            parameterization=1.0,
            credential_safety=0.0,
            lifecycle_compliance=0.0,
            verification_pass=0.0,
            tier_efficiency=0.0,
        )
        score = compute_query_security_score(result, weights)
        assert score == 1.0

    def test_custom_weights_zero_credential(self):
        result = _make_result(
            verdict=SecurityVerdict.FAIL,
            findings=[_credential_finding()],
        )
        weights = QueryScoreWeights(credential_safety=0.0)
        score = compute_query_security_score(result, weights)
        # No credential penalty, but verification_pass still penalized
        assert score > 0.0


# ---------------------------------------------------------------------------
# L1: Report builder tests
# ---------------------------------------------------------------------------


class TestBuildVerificationReport:
    """Tests for build_verification_report."""

    def test_empty_results(self):
        report = build_verification_report([], "run-001")
        assert report["run_id"] == "run-001"
        assert report["total_work_items"] == 0
        assert report["mean_score"] == 0.0
        assert report["pass_rate"] == 0.0
        assert report["items"] == []

    def test_single_clean_result(self):
        results = [_make_result()]
        report = build_verification_report(results, "run-002")
        assert report["total_work_items"] == 1
        assert report["mean_score"] == 1.0
        assert report["pass_rate"] == 1.0
        assert report["injection_total"] == 0
        assert len(report["items"]) == 1
        assert report["items"][0]["work_item_id"] == "wi-1"
        assert report["items"][0]["score"] == 1.0

    def test_mixed_results(self):
        results = [
            _make_result(work_item_id="wi-1"),
            _make_result(
                work_item_id="wi-2",
                verdict=SecurityVerdict.FAIL,
                findings=[_injection_finding("postgresql")],
            ),
        ]
        report = build_verification_report(results, "run-003")
        assert report["total_work_items"] == 2
        assert report["mean_score"] == pytest.approx(0.5, abs=0.01)
        assert report["injection_total"] == 1

    def test_by_database_grouping(self):
        results = [
            _make_result(work_item_id="wi-1"),
            _make_result(
                work_item_id="wi-2",
                verdict=SecurityVerdict.WARN,
                findings=[
                    SecurityFinding(
                        check_type=SecurityCheckType.LIFECYCLE,
                        severity="warning",
                        message="test",
                        database="spanner",
                        pattern_hash="x",
                    ),
                ],
            ),
        ]
        report = build_verification_report(results, "run-004")
        assert "spanner" in report["by_database"]

    def test_by_tier_grouping(self):
        results = [
            _make_result(tier=ComplexityTier.SIMPLE),
            _make_result(
                work_item_id="wi-2",
                tier=ComplexityTier.MODERATE,
                escalations=1,
            ),
        ]
        report = build_verification_report(results, "run-005")
        assert "simple" in report["by_tier"]
        assert "moderate" in report["by_tier"]
        assert report["by_tier"]["moderate"]["escalation_rate"] == 1.0

    def test_timestamp_default(self):
        report = build_verification_report([], "run-006")
        assert "timestamp" in report
        assert len(report["timestamp"]) > 0

    def test_custom_timestamp(self):
        report = build_verification_report(
            [], "run-007", run_timestamp="2026-03-21T00:00:00Z",
        )
        assert report["timestamp"] == "2026-03-21T00:00:00Z"

    def test_cost_aggregation(self):
        results = [
            _make_result(cost=0.001),
            _make_result(work_item_id="wi-2", cost=0.002),
        ]
        report = build_verification_report(results, "run-008")
        assert report["total_cost_usd"] == pytest.approx(0.003, abs=0.0001)

    def test_verdict_in_items(self):
        results = [_make_result()]
        report = build_verification_report(results, "run-009")
        assert report["items"][0]["verdict"] == "pass"


# ---------------------------------------------------------------------------
# QueryScoreWeights dataclass tests
# ---------------------------------------------------------------------------


class TestQueryScoreWeights:
    """Tests for QueryScoreWeights defaults."""

    def test_default_weights_sum_to_one(self):
        w = QueryScoreWeights()
        total = (
            w.parameterization + w.credential_safety
            + w.lifecycle_compliance + w.verification_pass
            + w.tier_efficiency
        )
        assert total == pytest.approx(1.0)

    def test_custom_weights(self):
        w = QueryScoreWeights(parameterization=0.5, credential_safety=0.5)
        assert w.parameterization == 0.5
        assert w.credential_safety == 0.5
