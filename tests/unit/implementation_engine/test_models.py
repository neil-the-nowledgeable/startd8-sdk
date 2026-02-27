"""Tests for implementation_engine.models — data model validation."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock

from startd8.implementation_engine.models import (
    DraftResult,
    EngineRequest,
    EngineResult,
    ReviewResult,
    SpecResult,
)


# ---------------------------------------------------------------------------
# SpecResult
# ---------------------------------------------------------------------------

class TestSpecResult:
    def test_basic_creation(self):
        spec = SpecResult(
            spec_id="spec-abc",
            task_summary="Build a widget",
            requirements=["Req 1"],
            technical_approach="Use factory",
            acceptance_criteria=["Test 1"],
        )
        assert spec.spec_id == "spec-abc"
        assert spec.task_summary == "Build a widget"
        assert spec.requirements == ["Req 1"]
        assert spec.raw_spec == ""
        assert spec.cost == 0.0

    def test_defaults(self):
        spec = SpecResult(
            spec_id="s1", task_summary="t", requirements=[], technical_approach="",
            acceptance_criteria=[],
        )
        assert spec.edge_cases == []
        assert spec.constraints == []
        assert spec.examples == []
        assert spec.input_tokens == 0
        assert spec.output_tokens == 0
        assert spec.code_structure is None
        assert isinstance(spec.created_at, datetime)

    def test_to_implementation_spec_round_trip(self):
        spec = SpecResult(
            spec_id="spec-123",
            task_summary="Test task",
            requirements=["R1", "R2"],
            technical_approach="Approach",
            acceptance_criteria=["AC1"],
            code_structure="Structure",
            edge_cases=["EC1"],
            constraints=["C1"],
            raw_spec="Raw",
            input_tokens=100,
            output_tokens=200,
            cost=0.05,
            time_ms=500,
        )
        impl_spec = spec.to_implementation_spec()
        assert impl_spec.spec_id == "spec-123"
        assert impl_spec.requirements == ["R1", "R2"]
        assert impl_spec.input_tokens == 100

    def test_from_implementation_spec(self):
        mock_spec = Mock()
        mock_spec.spec_id = "spec-456"
        mock_spec.task_summary = "Mock task"
        mock_spec.requirements = ["MR1"]
        mock_spec.technical_approach = "Mock approach"
        mock_spec.acceptance_criteria = ["MAC1"]
        mock_spec.code_structure = None
        mock_spec.edge_cases = []
        mock_spec.constraints = []
        mock_spec.examples = ["Ex1"]
        mock_spec.raw_spec = "raw"
        mock_spec.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
        mock_spec.input_tokens = 50
        mock_spec.output_tokens = 100
        mock_spec.cost = 0.01
        mock_spec.time_ms = 200

        result = SpecResult.from_implementation_spec(mock_spec)
        assert result.spec_id == "spec-456"
        assert result.requirements == ["MR1"]
        assert result.examples == ["Ex1"]

    def test_from_implementation_spec_missing_examples(self):
        mock_spec = Mock(spec=["no examples attr"])
        mock_spec.spec_id = "s1"
        mock_spec.task_summary = "t"
        mock_spec.requirements = []
        mock_spec.technical_approach = ""
        mock_spec.acceptance_criteria = []
        mock_spec.code_structure = None
        mock_spec.edge_cases = []
        mock_spec.constraints = []
        mock_spec.raw_spec = ""
        mock_spec.created_at = datetime.now(timezone.utc)
        mock_spec.input_tokens = 0
        mock_spec.output_tokens = 0
        mock_spec.cost = 0.0
        mock_spec.time_ms = 0
        del mock_spec.examples  # getattr fallback should handle this

        result = SpecResult.from_implementation_spec(mock_spec)
        assert result.examples == []


# ---------------------------------------------------------------------------
# DraftResult
# ---------------------------------------------------------------------------

class TestDraftResult:
    def test_basic_creation(self):
        draft = DraftResult(
            draft_id="draft-abc",
            iteration=1,
            implementation="def foo(): pass",
        )
        assert draft.draft_id == "draft-abc"
        assert draft.iteration == 1
        assert draft.implementation == "def foo(): pass"
        assert draft.was_truncated is False
        assert draft.truncation_source is None

    def test_truncation_fields(self):
        draft = DraftResult(
            draft_id="d1", iteration=1, implementation="code",
            was_truncated=True, truncation_source="api",
        )
        assert draft.was_truncated is True
        assert draft.truncation_source == "api"


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------

class TestReviewResult:
    def test_basic_creation(self):
        review = ReviewResult(
            review_id="rev-abc",
            iteration=1,
            passed=True,
            score=90,
        )
        assert review.review_id == "rev-abc"
        assert review.passed is True
        assert review.score == 90

    def test_defaults(self):
        review = ReviewResult(review_id="r", iteration=1, passed=False, score=50)
        assert review.issues == []
        assert review.blocking_issues == []
        assert review.suggestions == []
        assert review.strengths == []
        assert review.review_text == ""


# ---------------------------------------------------------------------------
# EngineRequest
# ---------------------------------------------------------------------------

class TestEngineRequest:
    def test_defaults(self):
        req = EngineRequest(task_description="Build it")
        assert req.task_description == "Build it"
        assert req.max_iterations == 3
        assert req.pass_threshold == 80
        assert req.check_truncation is True
        assert req.strict_truncation is False
        assert req.fail_on_api_truncation is True
        assert req.fail_on_heuristic_truncation is False
        assert req.edit_min_pct == 80
        assert req.context == {}
        assert req.existing_files is None
        assert req.target_files is None

    def test_edit_min_pct_is_int(self):
        req = EngineRequest(task_description="t", edit_min_pct=90)
        assert isinstance(req.edit_min_pct, int)


# ---------------------------------------------------------------------------
# EngineResult
# ---------------------------------------------------------------------------

class TestEngineResult:
    def test_defaults(self):
        result = EngineResult()
        assert result.spec is None
        assert result.drafts == []
        assert result.reviews == []
        assert result.final_code == ""
        assert result.passed is False
        assert result.iterations_used == 0
        assert result.error is None
        assert result.error_type is None

    def test_to_serializable_summary(self):
        spec = SpecResult(
            spec_id="spec-1", task_summary="t",
            requirements=[], technical_approach="",
            acceptance_criteria=[],
        )
        review = ReviewResult(
            review_id="r1", iteration=1, passed=True, score=85,
        )
        result = EngineResult(
            spec=spec,
            reviews=[review],
            passed=True,
            iterations_used=1,
            total_cost=0.05,
            truncation_events=[{"iteration": 1, "source": "api"}],
        )
        summary = result.to_serializable_summary()
        assert summary["spec_id"] == "spec-1"
        assert summary["passed"] is True
        assert summary["review_scores"] == [85]
        assert summary["iterations_used"] == 1
        assert len(summary["truncation_events"]) == 1

    def test_to_serializable_summary_no_spec(self):
        result = EngineResult()
        summary = result.to_serializable_summary()
        assert summary["spec_id"] is None

    def test_error_type_field(self):
        result = EngineResult(error="boom", error_type="ValueError")
        assert result.error_type == "ValueError"
