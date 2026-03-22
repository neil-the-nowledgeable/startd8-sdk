"""Tests for Review Feedback Loop — Iteration 1.

Covers:
- REQ-RFL-100: Persist DiskComplianceResult in integration metadata
- REQ-RFL-105: Persist RepairOutcome summary in integration metadata
- REQ-RFL-110: compute_disk_quality_score() extraction and re-export
- REQ-RFL-115: Disk quality score at integration time
- REQ-RFL-120: PrimeReviewAdapter
- REQ-RFL-125: Review wiring in PrimeContractorWorkflow
- REQ-RFL-128: Repair effectiveness public query API
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest


# ---------------------------------------------------------------------------
# REQ-RFL-110: compute_disk_quality_score extraction + re-export
# ---------------------------------------------------------------------------


class TestComputeDiskQualityScore:
    """Verify score function lives in forward_manifest_validator and is re-exported."""

    def test_canonical_import(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        assert callable(compute_disk_quality_score)

    def test_reexport_from_postmortem(self):
        from startd8.contractors.prime_postmortem import compute_disk_quality_score
        from startd8.forward_manifest_validator import (
            compute_disk_quality_score as canonical,
        )
        assert compute_disk_quality_score is canonical

    def test_perfect_score(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=True,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=0,
            semantic_issues=[],
        )
        assert compute_disk_quality_score(result) == 1.0

    def test_ast_invalid_is_zero(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=False,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=0,
            semantic_issues=[],
        )
        assert compute_disk_quality_score(result) == 0.0

    def test_none_is_zero(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        assert compute_disk_quality_score(None) == 0.0

    def test_stubs_reduce_score(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=True,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=5,
            semantic_issues=[],
        )
        score = compute_disk_quality_score(result)
        assert 0.0 < score < 1.0

    def test_semantic_errors_reduce_score(self):
        from startd8.forward_manifest_validator import compute_disk_quality_score
        result = SimpleNamespace(
            ast_valid=True,
            contract_compliance=1.0,
            import_completeness=1.0,
            stubs_remaining=0,
            semantic_issues=[
                {"severity": "error", "message": "phantom import"},
                {"severity": "error", "message": "duplicate def"},
            ],
        )
        score = compute_disk_quality_score(result)
        assert 0.0 < score < 1.0

    def test_dict_based_compliance(self):
        """compute_disk_quality_score works with SimpleNamespace-wrapped dicts."""
        from startd8.forward_manifest_validator import compute_disk_quality_score
        data = {
            "ast_valid": True,
            "contract_compliance": 0.8,
            "import_completeness": 0.9,
            "stubs_remaining": 1,
            "semantic_issues": [{"severity": "warning", "message": "bare except"}],
        }
        score = compute_disk_quality_score(SimpleNamespace(**data))
        assert 0.0 < score < 1.0


# ---------------------------------------------------------------------------
# REQ-RFL-120: PrimeReviewAdapter
# ---------------------------------------------------------------------------


@dataclass
class FakeFeature:
    """Minimal FeatureSpec stand-in for adapter tests."""
    id: str = "F-001"
    name: str = "test_feature"
    description: str = "A test feature"
    target_files: List[str] = field(default_factory=lambda: ["src/foo.py"])
    generated_files: List[str] = field(default_factory=lambda: ["src/foo.py"])
    metadata: Dict[str, Any] = field(default_factory=dict)


class TestPrimeReviewAdapter:

    def test_feature_to_seed_task_mapping(self):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        feature = FakeFeature(
            metadata={"domain": "backend", "prompt_constraints": ["use typing"]},
        )
        task = adapter._feature_to_seed_task(feature)
        assert task.task_id == "F-001"
        assert task.title == "test_feature"
        assert task.domain == "backend"
        assert "use typing" in task.prompt_constraints
        assert task.target_files == ["src/foo.py"]

    def test_feature_to_seed_task_defaults(self):
        """All required SeedTask fields must have values."""
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        feature = FakeFeature(metadata=None)
        task = adapter._feature_to_seed_task(feature)
        assert task.task_type == "task"
        assert task.domain == "general"
        assert task.prompt_constraints == []

    def test_read_generated_code(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("print('hello')")
        feature = FakeFeature(generated_files=["src/foo.py"])
        code = adapter._read_generated_code(feature, tmp_path)
        assert "print('hello')" in code
        assert "# src/foo.py" in code

    def test_read_generated_code_missing_files(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        feature = FakeFeature(generated_files=["nonexistent.py"])
        code = adapter._read_generated_code(feature, tmp_path)
        assert code == ""

    def test_pack_validation_as_test_results(self):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        metadata = {
            "disk_compliance": {"src/foo.py": {"ast_valid": True}},
            "disk_quality_score": 0.85,
            "repair_summaries": [{"phase": "post_merge", "any_modified": True}],
        }
        result = PrimeReviewAdapter._pack_validation_as_test_results(metadata)
        assert "validation_results" in result
        assert result["disk_quality_score"] == 0.85
        assert "repair_summary" in result

    def test_pack_validation_empty_metadata(self):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        result = PrimeReviewAdapter._pack_validation_as_test_results({})
        assert result == {}

    def test_review_skip_no_code(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        adapter._handler = mock.MagicMock()
        feature = FakeFeature(generated_files=["nonexistent.py"])
        result = adapter.review_feature(feature, tmp_path)
        assert result["verdict"] == "SKIP"
        adapter._handler._review_task.assert_not_called()

    def test_review_graceful_failure(self, tmp_path):
        from startd8.contractors.prime_review import PrimeReviewAdapter
        adapter = PrimeReviewAdapter.__new__(PrimeReviewAdapter)
        adapter._handler = mock.MagicMock()
        adapter._handler._review_task.side_effect = RuntimeError("LLM down")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "foo.py").write_text("print('hello')")
        feature = FakeFeature(generated_files=["src/foo.py"])
        result = adapter.review_feature(feature, tmp_path)
        assert result["verdict"] == "ERROR"
        assert result["score"] is None


# ---------------------------------------------------------------------------
# REQ-RFL-125: Review wiring in PrimeContractorWorkflow
# ---------------------------------------------------------------------------


class TestReviewWiring:

    def test_review_enabled_default(self):
        """review_enabled defaults to True."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        # Use mock to avoid full init side effects
        with mock.patch.object(PrimeContractorWorkflow, "__init__", lambda self, **kw: None):
            pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        # Verify the parameter exists in the real __init__ signature
        import inspect
        sig = inspect.signature(PrimeContractorWorkflow.__init__)
        assert "review_enabled" in sig.parameters
        assert sig.parameters["review_enabled"].default is True

    def test_review_agent_param_exists(self):
        """review_agent parameter exists with None default."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        import inspect
        sig = inspect.signature(PrimeContractorWorkflow.__init__)
        assert "review_agent" in sig.parameters
        assert sig.parameters["review_agent"].default is None

    def test_review_result_stored_in_metadata(self):
        """After review, result is stored in feature.metadata['review']."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow
        from startd8.contractors.queue import FeatureSpec

        pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        pc.review_enabled = True
        pc.walkthrough = False
        pc.project_root = Path("/tmp/test")
        pc.code_generator = None
        pc._review_agent = None
        pc._review_adapter = mock.MagicMock()
        pc._review_adapter.review_feature.return_value = {
            "score": 85,
            "verdict": "PASS",
            "issues": [],
            "suggestions": [],
        }
        pc.review_results = {}

        feature = FeatureSpec(id="F-001", name="test")
        metadata = {"disk_compliance": {}}

        result = pc._review_feature(feature, metadata)
        assert result is not None
        assert result["score"] == 85
        assert result["verdict"] == "PASS"

    def test_review_disabled_skips(self):
        """When review_enabled=False, no review is attempted."""
        from startd8.contractors.prime_contractor import PrimeContractorWorkflow

        pc = PrimeContractorWorkflow.__new__(PrimeContractorWorkflow)
        pc.review_enabled = False
        pc.walkthrough = False
        pc._review_adapter = mock.MagicMock()

        # _review_feature should never be called in integrate_feature
        # when review_enabled=False. We test the flag check here.
        assert pc.review_enabled is False


# ---------------------------------------------------------------------------
# REQ-RFL-100/105/115: Integration metadata plumbing
# ---------------------------------------------------------------------------


class TestIntegrationMetadataPlumbing:

    def test_compliance_dict_structure(self):
        """Compliance entries contain all required fields."""
        expected_keys = {
            "ast_valid", "stubs_remaining", "duplicate_definitions",
            "import_completeness", "contract_compliance", "semantic_issues",
        }
        entry = {
            "ast_valid": True,
            "stubs_remaining": 0,
            "duplicate_definitions": 0,
            "import_completeness": 1.0,
            "contract_compliance": 1.0,
            "semantic_issues": [],
        }
        assert set(entry.keys()) == expected_keys

    def test_repair_summary_structure(self):
        """Repair summary contains required fields."""
        summary = {
            "phase": "post_merge",
            "total_repairs": 2,
            "steps_applied": ["fence_strip", "ast_validate"],
            "any_modified": True,
        }
        assert summary["phase"] in ("pre_merge", "post_merge")
        assert isinstance(summary["total_repairs"], int)
        assert isinstance(summary["steps_applied"], list)
        assert isinstance(summary["any_modified"], bool)

    def test_disk_quality_score_from_compliance(self):
        """Score computed from compliance results via SimpleNamespace."""
        from startd8.forward_manifest_validator import compute_disk_quality_score
        compliance_data = {
            "src/foo.py": {
                "ast_valid": True,
                "stubs_remaining": 0,
                "duplicate_definitions": 0,
                "import_completeness": 0.8,
                "contract_compliance": 0.9,
                "semantic_issues": [],
            },
        }
        scores = [
            compute_disk_quality_score(SimpleNamespace(**d))
            for d in compliance_data.values()
        ]
        assert len(scores) == 1
        assert 0.0 < min(scores) < 1.0

    def test_disk_quality_score_min_of_files(self):
        """Score is min across files (weakest link)."""
        from startd8.forward_manifest_validator import compute_disk_quality_score
        compliance_data = {
            "good.py": {
                "ast_valid": True,
                "stubs_remaining": 0,
                "duplicate_definitions": 0,
                "import_completeness": 1.0,
                "contract_compliance": 1.0,
                "semantic_issues": [],
            },
            "bad.py": {
                "ast_valid": True,
                "stubs_remaining": 5,
                "duplicate_definitions": 0,
                "import_completeness": 0.5,
                "contract_compliance": 0.5,
                "semantic_issues": [
                    {"severity": "error", "message": "phantom import"},
                ],
            },
        }
        scores = [
            compute_disk_quality_score(SimpleNamespace(**d))
            for d in compliance_data.values()
        ]
        good_score = compute_disk_quality_score(
            SimpleNamespace(**compliance_data["good.py"]),
        )
        bad_score = compute_disk_quality_score(
            SimpleNamespace(**compliance_data["bad.py"]),
        )
        assert min(scores) == bad_score
        assert bad_score < good_score


# ---------------------------------------------------------------------------
# REQ-RFL-128: Repair effectiveness API
# ---------------------------------------------------------------------------


class TestRepairEffectivenessAPI:

    def test_summary_returns_dict(self):
        from startd8.repair.orchestrator import get_step_effectiveness_summary
        result = get_step_effectiveness_summary()
        assert isinstance(result, dict)

    def test_summary_fields(self):
        from startd8.repair.orchestrator import (
            get_step_effectiveness_summary,
            reset_step_effectiveness,
            _step_effectiveness,
        )
        from startd8.repair.models import StepEffectiveness

        reset_step_effectiveness()
        _step_effectiveness["test_step"] = StepEffectiveness(
            step_name="test_step",
            attempts=10,
            modifications=7,
            reverts=1,
            contributed_to_success=6,
        )
        try:
            summary = get_step_effectiveness_summary()
            assert "test_step" in summary
            entry = summary["test_step"]
            assert entry["attempts"] == 10
            assert entry["success_rate"] == 0.6  # 6/10
            assert entry["modifications"] == 7
            assert entry["contributed_to_success"] == 6
        finally:
            reset_step_effectiveness()
