"""Tests for implementation_engine.prompts — YAML loader + fallback templates."""

import pytest

from startd8.implementation_engine.prompts import format_prompt, get_template


class TestGetTemplate:
    def test_spec_template_exists(self):
        template = get_template("spec")
        assert isinstance(template, str)
        assert "{task_description}" in template

    def test_spec_from_design_template_exists(self):
        template = get_template("spec_from_design")
        assert isinstance(template, str)
        assert "{design_document}" in template

    def test_draft_template_exists(self):
        template = get_template("draft")
        assert isinstance(template, str)
        assert "{spec}" in template

    def test_draft_edit_template_exists(self):
        template = get_template("draft_edit")
        assert isinstance(template, str)
        assert "{spec}" in template

    def test_draft_system_create(self):
        template = get_template("draft_system_create")
        assert isinstance(template, str)
        assert "implement" in template.lower() or "engineer" in template.lower()

    def test_draft_system_edit(self):
        template = get_template("draft_system_edit")
        assert isinstance(template, str)
        assert "edit" in template.lower() or "existing" in template.lower()

    def test_draft_system_search_replace(self):
        template = get_template("draft_system_search_replace")
        assert isinstance(template, str)

    def test_review_template_exists(self):
        template = get_template("review")
        assert isinstance(template, str)
        assert "{pass_threshold}" in template

    def test_missing_template_raises(self):
        with pytest.raises(KeyError, match="No template found"):
            get_template("nonexistent_template")


class TestFormatPrompt:
    def test_format_review(self):
        result = format_prompt(
            "review",
            task_description="Build widget",
            spec="Full spec",
            implementation="def foo(): pass",
            pass_threshold=80,
            enrichment_sections="",
            prior_issues_section="",
            convergence_instructions="",
        )
        assert "Build widget" in result
        assert "Full spec" in result
        assert "80" in result

    def test_format_missing_placeholder_raises(self):
        with pytest.raises(KeyError, match="missing placeholder"):
            format_prompt("review", task_description="t")

    def test_format_draft_system_no_placeholders(self):
        # System prompts have no placeholders
        result = format_prompt("draft_system_create")
        assert isinstance(result, str)
        assert len(result) > 0
