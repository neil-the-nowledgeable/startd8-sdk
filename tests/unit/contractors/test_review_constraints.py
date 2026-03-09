"""Tests for L4: structured constraint checking in review."""

import pytest

from startd8.implementation_engine.spec_builder import (
    build_constraint_block,
    extract_spec_constraints,
)
from startd8.contractors.context_seed.core import ReviewPhaseHandler


# ---------------------------------------------------------------------------
# extract_spec_constraints
# ---------------------------------------------------------------------------

class TestExtractSpecConstraints:
    def test_extract_must_constraint(self):
        text = "The output MUST include all functions."
        result = extract_spec_constraints(text)
        assert len(result) >= 1
        must_items = [c for c in result if c["type"] == "MUST"]
        assert any("include all functions" in c["text"] for c in must_items)

    def test_extract_must_not_constraint(self):
        text = "Do NOT add header comments to the file."
        result = extract_spec_constraints(text)
        must_not_items = [c for c in result if c["type"] == "MUST_NOT"]
        assert len(must_not_items) >= 1
        assert any("add header comments" in c["text"] for c in must_not_items)

    def test_extract_must_not_variant(self):
        text = "The class MUST NOT inherit from BaseClass."
        result = extract_spec_constraints(text)
        must_not_items = [c for c in result if c["type"] == "MUST_NOT"]
        assert any("inherit from BaseClass" in c["text"] for c in must_not_items)

    def test_extract_required(self):
        text = "Required: implement the health check endpoint."
        result = extract_spec_constraints(text)
        must_items = [c for c in result if c["type"] == "MUST"]
        assert len(must_items) >= 1

    def test_extract_constraint_label(self):
        text = "Constraint: use only stdlib modules."
        result = extract_spec_constraints(text)
        assert len(result) >= 1

    def test_no_constraints(self):
        text = "This is a simple utility function that adds two numbers."
        result = extract_spec_constraints(text)
        assert result == []

    def test_deduplication(self):
        text = "MUST include tests. MUST include tests."
        result = extract_spec_constraints(text)
        texts = [c["text"] for c in result]
        assert len(texts) == len(set(texts))

    def test_multiple_constraints(self):
        text = (
            "The file MUST include all imports.\n"
            "Do NOT add pip-compile header comments.\n"
            "Required: implement the health check.\n"
        )
        result = extract_spec_constraints(text)
        assert len(result) >= 3


# ---------------------------------------------------------------------------
# ReviewPhaseHandler constraint checklist
# ---------------------------------------------------------------------------

class TestConstraintChecklist:
    def _make_task(self, constraints):
        """Create a minimal SeedTask-like object with prompt_constraints."""
        class FakeTask:
            prompt_constraints = constraints
        return FakeTask()

    def test_checklist_in_prompt(self):
        handler = ReviewPhaseHandler()
        task = self._make_task(["Use stdlib only", "No pip-compile headers"])
        result = handler._build_constraint_checklist_section(task)
        assert "Constraint Checklist" in result
        assert "Use stdlib only" in result
        assert "No pip-compile headers" in result
        assert "PASS or FAIL" in result

    def test_no_constraints_no_checklist(self):
        handler = ReviewPhaseHandler()
        task = self._make_task([])
        result = handler._build_constraint_checklist_section(task)
        assert result == ""

    def test_none_constraints_no_checklist(self):
        handler = ReviewPhaseHandler()
        task = self._make_task(None)
        result = handler._build_constraint_checklist_section(task)
        assert result == ""

    def test_numbered_constraints(self):
        handler = ReviewPhaseHandler()
        task = self._make_task(["First", "Second", "Third"])
        result = handler._build_constraint_checklist_section(task)
        assert "1." in result
        assert "2." in result
        assert "3." in result


# ---------------------------------------------------------------------------
# Constraint verdict extraction
# ---------------------------------------------------------------------------

class TestExtractConstraintVerdicts:
    def test_all_pass(self):
        review = (
            "### Score: 95\n"
            "### Verdict: PASS\n"
            "## Constraint Verdicts\n"
            "1. PASS\n"
            "2. PASS\n"
        )
        verdicts = ReviewPhaseHandler._extract_constraint_verdicts(review, 2)
        assert len(verdicts) == 2
        assert all(v["verdict"] == "PASS" for v in verdicts)

    def test_one_fail(self):
        review = (
            "## Constraint Verdicts\n"
            "1. PASS\n"
            "2. FAIL: comments were added\n"
        )
        verdicts = ReviewPhaseHandler._extract_constraint_verdicts(review, 2)
        assert len(verdicts) == 2
        assert verdicts[0]["verdict"] == "PASS"
        assert verdicts[1]["verdict"] == "FAIL"
        assert "comments" in verdicts[1]["reason"]

    def test_bold_wrapped_verdicts(self):
        review = (
            "## Constraint Verdicts\n"
            "1. **PASS**\n"
            "2. **FAIL**: wrong import\n"
        )
        verdicts = ReviewPhaseHandler._extract_constraint_verdicts(review, 2)
        assert len(verdicts) == 2
        assert verdicts[0]["verdict"] == "PASS"
        assert verdicts[1]["verdict"] == "FAIL"

    def test_no_constraint_section(self):
        review = "### Score: 90\n### Verdict: PASS\n"
        verdicts = ReviewPhaseHandler._extract_constraint_verdicts(review, 0)
        assert verdicts == []


# ---------------------------------------------------------------------------
# Score capping on constraint failure
# ---------------------------------------------------------------------------

class TestConstraintScoreCapping:
    def test_fail_caps_score(self):
        handler = ReviewPhaseHandler()
        review = (
            "### Score: 95\n"
            "### Verdict: PASS\n"
            "### Strengths\n"
            "- Good code\n"
            "### Issues\n"
            "- None\n"
            "### Suggestions\n"
            "- None\n"
            "## Constraint Verdicts\n"
            "1. PASS\n"
            "2. FAIL: added header comments\n"
        )
        result = handler._parse_review_response(review)
        assert result["score"] == 85  # capped from 95
        assert result.get("quality_failed") is True
        assert "constraint_verdicts" in result

    def test_all_pass_no_cap(self):
        handler = ReviewPhaseHandler()
        review = (
            "### Score: 95\n"
            "### Verdict: PASS\n"
            "### Strengths\n"
            "- Good code\n"
            "### Issues\n"
            "- None\n"
            "### Suggestions\n"
            "- None\n"
            "## Constraint Verdicts\n"
            "1. PASS\n"
            "2. PASS\n"
        )
        result = handler._parse_review_response(review)
        assert result["score"] == 95  # not capped
        assert result.get("quality_failed") is None

    def test_score_below_cap_unchanged(self):
        handler = ReviewPhaseHandler()
        review = (
            "### Score: 70\n"
            "### Verdict: FAIL\n"
            "### Strengths\n"
            "- Some effort\n"
            "### Issues\n"
            "- Many problems\n"
            "### Suggestions\n"
            "- Rewrite\n"
            "## Constraint Verdicts\n"
            "1. FAIL: missing imports\n"
        )
        result = handler._parse_review_response(review)
        assert result["score"] == 70  # already below 85, not changed


# ---------------------------------------------------------------------------
# L4+: Structured constraint emission from spec builder
# ---------------------------------------------------------------------------

class TestBuildConstraintBlock:
    def test_constraints_from_critical_params(self):
        context = {"critical_parameters": ["Use port 8080"]}
        text, constraints = build_constraint_block(context)
        assert len(constraints) == 1
        assert constraints[0]["type"] == "MUST"
        assert constraints[0]["source"] == "critical_parameters"
        assert "8080" in text

    def test_constraints_from_domain_do_not(self):
        context = {"domain_constraints": ["Do not add header comments"]}
        text, constraints = build_constraint_block(context)
        assert len(constraints) == 1
        assert constraints[0]["type"] == "MUST_NOT"
        assert constraints[0]["source"] == "domain_constraints"

    def test_constraints_from_prompt_never(self):
        context = {"prompt_constraints": ["Never use global state"]}
        text, constraints = build_constraint_block(context)
        assert len(constraints) == 1
        assert constraints[0]["type"] == "MUST_NOT"

    def test_empty_constraints_no_block(self):
        context = {}
        text, constraints = build_constraint_block(context)
        assert text == ""
        assert constraints == []

    def test_multiple_sources_combined(self):
        context = {
            "critical_parameters": ["Use stdlib only"],
            "domain_constraints": ["Do not add pip-compile headers"],
            "prompt_constraints": ["Implement health check"],
        }
        text, constraints = build_constraint_block(context)
        assert len(constraints) == 3
        assert "## Constraints" in text
        assert "1." in text
        assert "2." in text
        assert "3." in text

    def test_numbered_formatting(self):
        context = {"critical_parameters": ["A", "B"]}
        text, constraints = build_constraint_block(context)
        assert "1. **[MUST]** A" in text
        assert "2. **[MUST]** B" in text

    def test_constraints_round_trip_to_review(self):
        """Constraints from spec builder can be consumed by review handler."""
        context = {"prompt_constraints": ["Use stdlib only", "No pip-compile headers"]}
        _, constraints = build_constraint_block(context)
        texts = [c["text"] for c in constraints]
        # These can be passed directly to ReviewPhaseHandler
        handler = ReviewPhaseHandler()

        class FakeTask:
            prompt_constraints = texts

        result = handler._build_constraint_checklist_section(FakeTask())
        assert "Constraint Checklist" in result
        assert "Use stdlib only" in result
