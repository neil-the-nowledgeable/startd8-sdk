"""Tests for implementation_engine.reviewer — review and feedback formatting."""

import pytest
from unittest.mock import Mock

from startd8.implementation_engine.reviewer import (
    format_review_feedback,
    review_draft,
)
from startd8.implementation_engine.models import ReviewResult


# ---------------------------------------------------------------------------
# review_draft
# ---------------------------------------------------------------------------

class TestReviewDraft:
    def _make_agent(self, review_text):
        agent = Mock()
        agent.model = "test-reviewer"
        token_usage = Mock()
        token_usage.input = 500
        token_usage.output = 300
        token_usage.was_truncated = False
        agent.generate.return_value = (review_text, 800, token_usage)
        return agent

    def _make_spec(self):
        spec = Mock()
        spec.raw_spec = "Build a widget that does X."
        return spec

    def test_pass_with_high_score_and_verdict(self):
        review_text = (
            "### Score: 92\n### Verdict: PASS\n"
            "### Strengths\n- Good structure\n"
            "### Issues\n- Minor style issue\n"
        )
        agent = self._make_agent(review_text)
        result = review_draft(agent, "Build widget", self._make_spec(), "def foo(): pass")

        assert result.passed is True
        assert result.score == 92
        assert result.strengths == ["Good structure"]
        assert result.issues == ["Minor style issue"]

    def test_fail_low_score(self):
        review_text = "### Score: 40\n### Verdict: FAIL\n"
        agent = self._make_agent(review_text)
        result = review_draft(agent, "task", self._make_spec(), "code")

        assert result.passed is False
        assert result.score == 40

    def test_fail_no_pass_verdict(self):
        # High score but no PASS keyword
        review_text = "### Score: 95\n### Verdict: FAIL\n"
        agent = self._make_agent(review_text)
        result = review_draft(agent, "task", self._make_spec(), "code")

        assert result.passed is False
        assert result.score == 95

    def test_requires_both_score_and_verdict(self):
        # Has PASS but score below threshold
        review_text = "### Score: 50\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        result = review_draft(agent, "task", self._make_spec(), "code")

        assert result.passed is False
        assert result.score == 50

    def test_custom_threshold(self):
        review_text = "### Score: 60\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        result = review_draft(agent, "task", self._make_spec(), "code", pass_threshold=50)

        assert result.passed is True

    def test_blocking_issues_parsed(self):
        review_text = (
            "### Score: 70\n### Verdict: FAIL\n"
            "### Blocking Issues\n- Missing import\n- Syntax error\n"
        )
        agent = self._make_agent(review_text)
        result = review_draft(agent, "task", self._make_spec(), "code")

        assert result.blocking_issues == ["Missing import", "Syntax error"]

    def test_suggestions_parsed(self):
        review_text = (
            "### Score: 85\n### Verdict: PASS\n"
            "### Suggestions\n- Add type hints\n"
        )
        agent = self._make_agent(review_text)
        result = review_draft(agent, "task", self._make_spec(), "code")

        assert result.suggestions == ["Add type hints"]

    def test_duck_typed_spec_no_raw_spec(self):
        review_text = "### Score: 80\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        spec = "Just a string spec"

        result = review_draft(agent, "task", spec, "code")
        assert result.score == 80

    def test_iteration_tracked(self):
        review_text = "### Score: 80\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        result = review_draft(
            agent, "task", self._make_spec(), "code", iteration=3,
        )
        assert result.iteration == 3

    def test_no_score_in_review(self):
        review_text = "This review has no score pattern"
        agent = self._make_agent(review_text)
        result = review_draft(agent, "task", self._make_spec(), "code")

        assert result.score == 0
        assert result.passed is False


# ---------------------------------------------------------------------------
# format_review_feedback
# ---------------------------------------------------------------------------

class TestFormatReviewFeedback:
    def test_basic_formatting(self):
        review = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            issues=["Bug A", "Bug B"],
            blocking_issues=["Critical C"],
            suggestions=["Try D"],
            review_text="Full review text here",
        )
        result = format_review_feedback(review)

        assert "Score: 60/100" in result
        assert "Bug A" in result
        assert "Bug B" in result
        assert "Critical C" in result
        assert "Try D" in result
        assert "Full review text here" in result

    def test_empty_lists(self):
        review = ReviewResult(
            review_id="r2", iteration=1, passed=True, score=90,
            review_text="Looks good",
        )
        result = format_review_feedback(review)

        assert "None listed" in result
        assert "None" in result

    def test_issues_formatted_as_bullets(self):
        review = ReviewResult(
            review_id="r3", iteration=1, passed=False, score=50,
            issues=["Issue 1"],
        )
        result = format_review_feedback(review)
        assert "- Issue 1" in result
