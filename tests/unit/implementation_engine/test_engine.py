"""Tests for implementation_engine.engine — DefaultImplementationEngine orchestrator."""

import pytest
from unittest.mock import Mock, patch, MagicMock

from startd8.implementation_engine.engine import (
    DefaultImplementationEngine,
    _TRUNCATION_CONTINUATION_FEEDBACK,
)
from startd8.implementation_engine.models import (
    DraftResult,
    EngineRequest,
    EngineResult,
    ReviewResult,
    SpecResult,
)


def _make_spec():
    return SpecResult(
        spec_id="spec-test",
        task_summary="Test task",
        requirements=["R1"],
        technical_approach="Approach",
        acceptance_criteria=["AC1"],
        raw_spec="Full spec text",
        input_tokens=100,
        output_tokens=200,
        cost=0.01,
        time_ms=500,
    )


def _make_draft(iteration=1, was_truncated=False, truncation_source=None):
    return DraftResult(
        draft_id=f"draft-{iteration}",
        iteration=iteration,
        implementation=f"def func_{iteration}(): pass",
        input_tokens=50,
        output_tokens=100,
        cost=0.005,
        time_ms=300,
        was_truncated=was_truncated,
        truncation_source=truncation_source,
        raw_response=f"```python\ndef func_{iteration}(): pass\n```",
    )


def _make_review(iteration=1, passed=False, score=60):
    return ReviewResult(
        review_id=f"review-{iteration}",
        iteration=iteration,
        passed=passed,
        score=score,
        issues=["Issue A"] if not passed else [],
        blocking_issues=["Blocking B"] if not passed else [],
        review_text=f"Score: {score}\nVerdict: {'PASS' if passed else 'FAIL'}",
        input_tokens=200,
        output_tokens=150,
        cost=0.008,
        time_ms=600,
    )


class TestDefaultImplementationEngine:

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_single_iteration_pass(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.return_value = _make_draft(iteration=1)
        mock_review_draft.return_value = _make_review(iteration=1, passed=True, score=90)

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
        )
        result = engine.build_and_execute(request)

        assert result.passed is True
        assert result.iterations_used == 1
        assert len(result.drafts) == 1
        assert len(result.reviews) == 1
        assert result.final_code == "def func_1(): pass"
        assert result.error is None

    @patch("startd8.implementation_engine.engine.format_review_feedback")
    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_three_iterations_exhaust(
        self, mock_resolve, mock_build_spec, mock_create_draft,
        mock_review_draft, mock_format_feedback,
    ):
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.side_effect = [
            _make_draft(1), _make_draft(2), _make_draft(3),
        ]
        mock_review_draft.side_effect = [
            _make_review(1, passed=False, score=40),
            _make_review(2, passed=False, score=60),
            _make_review(3, passed=False, score=70),
        ]
        mock_format_feedback.return_value = "Fix issues"

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
            max_iterations=3,
        )
        result = engine.build_and_execute(request)

        assert result.passed is False
        assert result.iterations_used == 3
        assert len(result.drafts) == 3
        assert len(result.reviews) == 3
        assert result.final_code == "def func_3(): pass"

    @patch("startd8.implementation_engine.engine.format_review_feedback")
    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_pass_on_second_iteration(
        self, mock_resolve, mock_build_spec, mock_create_draft,
        mock_review_draft, mock_format_feedback,
    ):
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.side_effect = [_make_draft(1), _make_draft(2)]
        mock_review_draft.side_effect = [
            _make_review(1, passed=False, score=50),
            _make_review(2, passed=True, score=85),
        ]
        mock_format_feedback.return_value = "Fix issues"

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
        )
        result = engine.build_and_execute(request)

        assert result.passed is True
        assert result.iterations_used == 2

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_truncation_auto_retry(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()

        # First draft truncated, second draft OK
        mock_create_draft.side_effect = [
            _make_draft(1, was_truncated=True, truncation_source="api"),
            _make_draft(2),
        ]
        mock_review_draft.return_value = _make_review(2, passed=True, score=90)

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
            max_iterations=3,
            fail_on_api_truncation=True,
        )
        result = engine.build_and_execute(request)

        assert result.passed is True
        assert len(result.drafts) == 2
        assert len(result.reviews) == 1  # First review skipped (truncation retry)
        assert len(result.truncation_events) == 1
        assert result.truncation_events[0]["source"] == "api"

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_truncation_at_final_iteration(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.return_value = _make_draft(
            1, was_truncated=True, truncation_source="api",
        )
        mock_review_draft.return_value = _make_review(1, passed=False, score=50)

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
            max_iterations=1,
            fail_on_api_truncation=True,
        )
        result = engine.build_and_execute(request)

        # At final iteration, truncation doesn't retry — proceeds to review
        assert len(result.truncation_events) == 1

    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_error_handling(self, mock_resolve, mock_build_spec):
        mock_resolve.return_value = Mock()
        mock_build_spec.side_effect = RuntimeError("Spec generation failed")

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
        )
        result = engine.build_and_execute(request)

        assert result.error == "Spec generation failed"
        assert result.error_type == "RuntimeError"
        assert result.passed is False

    def test_resolve_agent_none_raises(self):
        engine = DefaultImplementationEngine()
        with pytest.raises(ValueError, match="must not be None"):
            engine._resolve_agent(None)

    def test_resolve_agent_empty_raises(self):
        engine = DefaultImplementationEngine()
        with pytest.raises(ValueError, match="must not be None"):
            engine._resolve_agent("")

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_cost_accumulation(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        mock_resolve.return_value = Mock()

        spec = _make_spec()
        spec.cost = 0.01
        mock_build_spec.return_value = spec

        draft = _make_draft(1)
        draft.cost = 0.005
        mock_create_draft.return_value = draft

        review = _make_review(1, passed=True, score=90)
        review.cost = 0.008
        mock_review_draft.return_value = review

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
        )
        result = engine.build_and_execute(request)

        assert result.spec_cost == 0.01
        assert result.draft_cost == 0.005
        assert result.review_cost == 0.008
        assert result.total_cost == pytest.approx(0.023, abs=0.001)

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_last_raw_response_captured(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.return_value = _make_draft(1)
        mock_review_draft.return_value = _make_review(1, passed=True, score=90)

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
        )
        result = engine.build_and_execute(request)

        assert result.last_raw_response != ""

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_heuristic_truncation_non_fail(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        """When fail_on_heuristic_truncation=False, truncation is logged but review proceeds."""
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.return_value = _make_draft(
            1, was_truncated=True, truncation_source="heuristic",
        )
        mock_review_draft.return_value = _make_review(1, passed=True, score=85)

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
            fail_on_heuristic_truncation=False,
        )
        result = engine.build_and_execute(request)

        # Review should proceed even with heuristic truncation
        assert len(result.reviews) == 1
        assert len(result.truncation_events) == 1

    # --- New tests: context threading + convergent review ---

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_context_threaded_to_create_draft(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        """Engine threads request.context to create_draft."""
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.return_value = _make_draft(1)
        mock_review_draft.return_value = _make_review(1, passed=True, score=90)

        engine = DefaultImplementationEngine()
        ctx = {"design_document": "Design doc text", "critical_parameters": ["p=1"]}
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
            context=ctx,
        )
        engine.build_and_execute(request)

        # Verify context was passed to create_draft
        call_kwargs = mock_create_draft.call_args.kwargs
        assert call_kwargs.get("context") is ctx

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_enrichment_context_threaded_to_review_draft(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        """Engine threads enrichment context to review_draft."""
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.return_value = _make_draft(1)
        mock_review_draft.return_value = _make_review(1, passed=True, score=90)

        engine = DefaultImplementationEngine()
        ctx = {
            "design_document": "Design doc text",
            "parameter_sources": {"port": "req.md"},
            "semantic_conventions": "use_snake_case",
            "manifest_context": "### app.py\nclass App",
            "call_graph_context": "main -> run",
            "call_graph_callers": [{"fqn": "app.main", "blast_radius": 3}],
        }
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
            context=ctx,
        )
        engine.build_and_execute(request)

        call_kwargs = mock_review_draft.call_args.kwargs
        assert call_kwargs.get("design_document") == "Design doc text"
        assert call_kwargs.get("manifest_context") == "### app.py\nclass App"
        assert call_kwargs.get("call_graph_callers") is not None

    @patch("startd8.implementation_engine.engine.format_review_feedback")
    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_prior_review_threaded_across_iterations(
        self, mock_resolve, mock_build_spec, mock_create_draft,
        mock_review_draft, mock_format_feedback,
    ):
        """Engine tracks prior_review and passes it to subsequent review_draft calls."""
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.side_effect = [_make_draft(1), _make_draft(2)]

        review1 = _make_review(1, passed=False, score=50)
        review2 = _make_review(2, passed=True, score=85)
        mock_review_draft.side_effect = [review1, review2]
        mock_format_feedback.return_value = "Fix issues"

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
        )
        engine.build_and_execute(request)

        # First call: no prior_review
        first_call_kwargs = mock_review_draft.call_args_list[0].kwargs
        assert first_call_kwargs.get("prior_review") is None

        # Second call: prior_review is review1
        second_call_kwargs = mock_review_draft.call_args_list[1].kwargs
        assert second_call_kwargs.get("prior_review") is review1

    @patch("startd8.implementation_engine.engine.format_review_feedback")
    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_format_feedback_receives_prior_review(
        self, mock_resolve, mock_build_spec, mock_create_draft,
        mock_review_draft, mock_format_feedback,
    ):
        """Engine passes prior_review to format_review_feedback."""
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.side_effect = [_make_draft(1), _make_draft(2)]

        review1 = _make_review(1, passed=False, score=50)
        review2 = _make_review(2, passed=True, score=85)
        mock_review_draft.side_effect = [review1, review2]
        mock_format_feedback.return_value = "Fix issues"

        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
        )
        engine.build_and_execute(request)

        # format_review_feedback called once (review1 didn't pass)
        assert mock_format_feedback.call_count == 1
        call_kwargs = mock_format_feedback.call_args.kwargs
        # First call: prior_review=None (no prior review yet)
        assert call_kwargs.get("prior_review") is None

    @patch("startd8.implementation_engine.engine.review_draft")
    @patch("startd8.implementation_engine.engine.create_draft")
    @patch("startd8.implementation_engine.engine.build_spec")
    @patch("startd8.implementation_engine.engine.resolve_agent_spec")
    def test_forward_manifest_threaded_to_review(
        self, mock_resolve, mock_build_spec, mock_create_draft, mock_review_draft,
    ):
        """Engine threads forward_manifest from context to review_draft."""
        mock_resolve.return_value = Mock()
        mock_build_spec.return_value = _make_spec()
        mock_create_draft.return_value = _make_draft(1)
        mock_review_draft.return_value = _make_review(1, passed=True, score=90)

        fm = Mock()
        engine = DefaultImplementationEngine()
        request = EngineRequest(
            task_description="Build widget",
            drafter_agent_spec="mock:drafter",
            reviewer_agent_spec="mock:reviewer",
            context={"forward_manifest": fm},
            target_files=["app.py"],
        )
        engine.build_and_execute(request)

        call_kwargs = mock_review_draft.call_args.kwargs
        assert call_kwargs.get("forward_manifest") is fm
        assert call_kwargs.get("target_files") == ["app.py"]


class TestTruncationContinuationFeedback:
    def test_feedback_is_string(self):
        assert isinstance(_TRUNCATION_CONTINUATION_FEEDBACK, str)
        assert "TRUNCATED" in _TRUNCATION_CONTINUATION_FEEDBACK
        assert "COMPLETE" in _TRUNCATION_CONTINUATION_FEEDBACK
