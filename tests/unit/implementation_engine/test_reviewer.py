"""Tests for implementation_engine.reviewer — review, enrichment, convergent review, feedback."""

import pytest
from unittest.mock import Mock

from startd8.implementation_engine.reviewer import (
    build_enrichment_sections,
    build_prior_issues_section,
    compute_issue_coverage,
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

    def test_enrichment_kwargs_accepted(self):
        """review_draft accepts enrichment kwargs without error."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        result = review_draft(
            agent, "task", self._make_spec(), "code",
            design_document="## Design\nBuild widget",
            parameter_sources={"port": "req.md:5"},
            semantic_conventions="use_snake_case",
            manifest_context="### app.py\nclass App",
            call_graph_context="main -> run",
            call_graph_callers=[{"fqn": "app.main", "blast_radius": 3}],
        )
        assert result.score == 85

    def test_enrichment_sections_in_prompt(self):
        """Enrichment kwargs appear in the review prompt."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        review_draft(
            agent, "task", self._make_spec(), "code",
            design_document="## Design\nBuild a CRM widget",
        )
        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "CRM widget" in prompt

    def test_prior_review_creates_issues_section(self):
        """prior_review generates issue resolution section in prompt."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)

        prior = ReviewResult(
            review_id="r-prior", iteration=1, passed=False, score=60,
            blocking_issues=["Missing import for datetime"],
            issues=["Missing type hint"],
        )
        review_draft(
            agent, "task", self._make_spec(), "code",
            iteration=2, prior_review=prior,
        )

        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "Issue Resolution Status" in prompt
        assert "[B1]" in prompt
        assert "datetime" in prompt

    def test_convergence_instructions_in_prompt(self):
        """Convergence criteria appear in prompt for iteration > 1."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)

        prior = ReviewResult(
            review_id="r-prior", iteration=1, passed=False, score=60,
        )
        review_draft(
            agent, "task", self._make_spec(), "code",
            iteration=2, prior_review=prior,
        )

        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "Convergence Criteria" in prompt

    def test_system_prompt_sent(self):
        """Reviewer sends a system prompt to the agent."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        review_draft(agent, "task", self._make_spec(), "code")

        call_args = agent.generate.call_args
        # system_prompt should be passed as kwarg
        if "system_prompt" in (call_args.kwargs or {}):
            sys_prompt = call_args.kwargs["system_prompt"]
            assert "senior" in sys_prompt.lower() or "reviewing" in sys_prompt.lower()

    def test_flcm_contract_validation_detects_missing_element(self):
        """FLCM now runs the REAL validator (FR-3 repair, no phantom method).

        A spec element absent from the drafted code yields a violation; a
        present element yields none. This proves the path is no longer dormant.
        """
        from startd8.implementation_engine.reviewer import _validate_against_manifest
        from startd8.forward_manifest import ForwardFileSpec, ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind

        fm = Mock()
        fm.contracts = []
        fm.file_specs = {
            "mod.py": ForwardFileSpec(
                file="mod.py",
                elements=[
                    ForwardElementSpec(kind=ElementKind.CONSTANT, name="EXPECTED_CONST")
                ],
            )
        }

        # Missing the prescribed constant -> one violation.
        viols = _validate_against_manifest(fm, "x = 1\n", target_files=["mod.py"])
        assert len(viols) == 1
        assert viols[0]["violation_type"] == "missing_constant"
        assert viols[0]["severity"] == "error"

        # Present -> no violation.
        ok = _validate_against_manifest(
            fm, "EXPECTED_CONST = 1\n", target_files=["mod.py"]
        )
        assert ok == []

    def test_flcm_no_contracts_attr_skipped(self):
        """FLCM validation skipped when manifest has no contracts."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)

        fm = Mock(spec=[])  # No `contracts` attribute
        del fm.contracts

        result = review_draft(
            agent, "task", self._make_spec(), "code",
            forward_manifest=fm,
        )
        assert result.passed is True

    def test_manifest_context_in_review(self):
        """Manifest context appears in the review prompt."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        review_draft(
            agent, "task", self._make_spec(), "code",
            manifest_context="### app.py\nclass WidgetService: ...",
        )
        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "WidgetService" in prompt

    def test_call_graph_callers_in_review(self):
        """Call graph callers data appears in the review prompt."""
        review_text = "### Score: 85\n### Verdict: PASS\n"
        agent = self._make_agent(review_text)
        review_draft(
            agent, "task", self._make_spec(), "code",
            call_graph_callers=[
                {"fqn": "app.main", "blast_radius": 7, "direct_callers": ["x"]},
            ],
        )
        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "app.main" in prompt or "Backward" in prompt


# ---------------------------------------------------------------------------
# build_enrichment_sections
# ---------------------------------------------------------------------------

class TestBuildEnrichmentSections:
    def test_empty_returns_empty(self):
        assert build_enrichment_sections() == ""
        assert build_enrichment_sections(None) == ""

    def test_design_document_rendered(self):
        result = build_enrichment_sections(
            design_document="## Design\nBuild a widget",
        )
        assert "Design Document" in result
        assert "Build a widget" in result

    def test_semantic_conventions_rendered(self):
        result = build_enrichment_sections(
            semantic_conventions="use_snake_case for functions",
        )
        assert "Semantic Conventions" in result
        assert "snake_case" in result

    def test_context_shared_sections(self):
        ctx = {
            "critical_parameters": ["port=8080"],
            "manifest_context": "### app.py\nclass App",
        }
        result = build_enrichment_sections(context=ctx)
        assert "port=8080" in result

    def test_all_sections_combined(self):
        ctx = {"critical_parameters": ["port=8080"]}
        result = build_enrichment_sections(
            context=ctx,
            design_document="## Design\nWidget",
            semantic_conventions="use_snake_case",
        )
        assert "port=8080" in result
        assert "Widget" in result
        assert "snake_case" in result


# ---------------------------------------------------------------------------
# build_prior_issues_section
# ---------------------------------------------------------------------------

class TestBuildPriorIssuesSection:
    def test_first_iteration_returns_empty(self):
        assert build_prior_issues_section(iteration=1) == ""
        assert build_prior_issues_section(None, iteration=2) == ""

    def test_no_issues_returns_empty(self):
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
        )
        assert build_prior_issues_section(prior, iteration=2) == ""

    def test_blocking_issues_labeled(self):
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            blocking_issues=["Missing import", "Syntax error"],
        )
        result = build_prior_issues_section(prior, iteration=2)
        assert "Issue Resolution Status" in result
        assert "[B1]" in result
        assert "[B2]" in result
        assert "Missing import" in result
        assert "Syntax error" in result

    def test_other_issues_labeled(self):
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            issues=["Missing type hint", "Poor naming"],
        )
        result = build_prior_issues_section(prior, iteration=2)
        assert "[I1]" in result
        assert "[I2]" in result

    def test_iteration_number_shown(self):
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            blocking_issues=["Bug"],
        )
        result = build_prior_issues_section(prior, iteration=3, max_iterations=5)
        assert "iteration 3 of 5" in result


# ---------------------------------------------------------------------------
# compute_issue_coverage
# ---------------------------------------------------------------------------

class TestComputeIssueCoverage:
    def test_no_issues_empty(self):
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
        )
        coverage = compute_issue_coverage(prior)
        assert coverage["addressed"] == []
        assert coverage["outstanding"] == []

    def test_blocking_issues_without_review_text(self):
        """Without review text, all issues are classified as outstanding."""
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            blocking_issues=["Missing import for datetime"],
        )
        coverage = compute_issue_coverage(prior)
        assert len(coverage["outstanding"]) == 1
        assert coverage["outstanding"][0]["label"] == "B1"

    def test_blocking_issues_addressed_when_not_in_text(self):
        """Issues whose key terms are absent from review text are addressed."""
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            blocking_issues=["Missing import for datetime"],
        )
        coverage = compute_issue_coverage(
            prior,
            current_review_text="Good code. No issues found.",
        )
        assert len(coverage["addressed"]) == 1
        assert coverage["addressed"][0]["label"] == "B1"

    def test_issues_labeled_correctly(self):
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            blocking_issues=["Bug A"],
            issues=["Style B", "Naming C"],
        )
        coverage = compute_issue_coverage(prior)
        labels = [e["label"] for e in coverage["outstanding"]]
        assert "B1" in labels
        assert "I1" in labels
        assert "I2" in labels


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

    def test_convergence_format_with_prior_review(self):
        """With prior_review, produces convergence-aware format."""
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            blocking_issues=["Missing import"],
            issues=["Bad naming"],
        )
        current = ReviewResult(
            review_id="r2", iteration=2, passed=False, score=75,
            blocking_issues=[],
            issues=["Unused variable"],
            review_text="Better but still has issues",
        )
        result = format_review_feedback(current, prior_review=prior)

        assert "Convergent Review" in result
        assert "Score: 75/100" in result
        assert "Convergence Status" in result

    def test_convergence_shows_resolved_issues(self):
        """Convergence format shows resolved issues."""
        prior = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            blocking_issues=["Missing import for datetime"],
            issues=["Bad naming convention"],
        )
        current = ReviewResult(
            review_id="r2", iteration=2, passed=False, score=75,
            blocking_issues=[],
            issues=[],
            review_text="All prior issues fixed",
        )
        result = format_review_feedback(current, prior_review=prior)

        assert "Resolved Since Prior Review" in result

    def test_backward_compat_no_prior(self):
        """Without prior_review, produces flat format (backward compat)."""
        review = ReviewResult(
            review_id="r1", iteration=1, passed=False, score=60,
            issues=["Bug A"],
            review_text="Review text",
        )
        result = format_review_feedback(review, prior_review=None)

        # Should be the flat format, not convergence format
        assert "Convergent Review" not in result
        assert "Score: 60/100" in result
