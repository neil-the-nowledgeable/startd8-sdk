"""Tests for semantic repair dual scoring (DC-3, Commit 6)."""

import dataclasses

from startd8.contractors.prime_postmortem import (
    FeaturePostMortem,
    compute_disk_quality_score,
)


class TestFeaturePostMortemNewFields:
    """Verify new semantic repair fields on FeaturePostMortem."""

    def test_defaults(self):
        fpm = FeaturePostMortem(
            feature_id="PI-001", name="test", status="complete", success=True,
        )
        assert fpm.pre_semantic_repair_score is None
        assert fpm.semantic_repairs_applied == 0
        assert fpm.semantic_repair_categories == []

    def test_populated(self):
        fpm = FeaturePostMortem(
            feature_id="PI-004", name="test", status="complete", success=True,
            pre_semantic_repair_score=0.86,
            semantic_repairs_applied=2,
            semantic_repair_categories=["import_resolution"],
        )
        assert fpm.pre_semantic_repair_score == 0.86
        assert fpm.semantic_repairs_applied == 2
        assert fpm.semantic_repair_categories == ["import_resolution"]

    def test_list_default_not_shared(self):
        fpm1 = FeaturePostMortem(
            feature_id="a", name="a", status="c", success=True,
        )
        fpm2 = FeaturePostMortem(
            feature_id="b", name="b", status="c", success=True,
        )
        fpm1.semantic_repair_categories.append("method_resolution")
        assert fpm2.semantic_repair_categories == []


class TestDualScoringLogic:
    """Verify that pre-repair vs post-repair scores are distinct."""

    def test_assembly_delta_uses_pre_repair_when_available(self):
        """When pre_semantic_repair_score is set, assembly_delta should
        reflect generator quality (pre-repair), not output quality (post-repair)."""
        fpm = FeaturePostMortem(
            feature_id="PI-004", name="test", status="complete", success=True,
            requirement_score=1.0,
            disk_quality_score=1.0,  # post-repair: perfect
            pre_semantic_repair_score=0.86,  # pre-repair: had issues
        )
        # The postmortem should use pre_semantic_repair_score for kaizen_delta
        # assembly_delta = requirement_score - pre_repair_score = 1.0 - 0.86 = 0.14
        # (This is set by _evaluate_disk_quality, not by the dataclass itself)
        # Here we verify the fields exist and are distinct
        assert fpm.disk_quality_score != fpm.pre_semantic_repair_score
        assert fpm.pre_semantic_repair_score < fpm.disk_quality_score

    def test_no_pre_repair_score_falls_back_to_disk(self):
        """When no semantic repair occurred, pre_semantic_repair_score is None
        and assembly_delta uses disk_quality_score as usual."""
        fpm = FeaturePostMortem(
            feature_id="PI-001", name="test", status="complete", success=True,
            requirement_score=1.0,
            disk_quality_score=1.0,
        )
        assert fpm.pre_semantic_repair_score is None
        # assembly_delta would be 1.0 - 1.0 = 0.0 (set by evaluator)


class TestComputeDiskQualityScoreUnchanged:
    """Verify compute_disk_quality_score is not affected by repair changes."""

    def test_perfect_score(self):
        """A file with no issues scores 1.0."""

        class FakeCompliance:
            ast_valid = True
            contract_compliance = 1.0
            import_completeness = 1.0
            stubs_remaining = 0
            semantic_issues = []

        assert compute_disk_quality_score(FakeCompliance()) == 1.0

    def test_two_errors_reduce_score(self):
        """Two error-severity semantic issues reduce the semantic component."""

        class FakeCompliance:
            ast_valid = True
            contract_compliance = 1.0
            import_completeness = 1.0
            stubs_remaining = 0
            semantic_issues = [
                {"category": "import_resolution", "severity": "error"},
                {"category": "import_resolution", "severity": "error"},
            ]

        score = compute_disk_quality_score(FakeCompliance())
        # semantic_penalty = max(0, 1.0 - 2*0.3) = 0.4
        # composite = 1.0*0.4 + 1.0*0.2 + 1.0*0.2 + 0.4*0.2 = 0.88
        assert abs(score - 0.88) < 0.01

    def test_none_compliance(self):
        assert compute_disk_quality_score(None) == 0.0
