"""Tests for IMPLEMENT phase prompt externalization and edit-vs-create bias fixes.

Verifies:
1. implement.yaml loads correctly for all 10 templates
2. All templates have correct placeholders that str.format() can fill
3. _build_task_description() with edit mode produces "update" not "generate"
4. _build_task_description() with create mode produces "generate" not "update"
5. Edit Mode Classification appears for BOTH edit and create modes (B-3 fix)
6. Greenfield design framing does NOT appear when _existing_file_contents is present (B-5 fix)
7. Edit design framing says "CHANGES to apply" when _existing_file_contents is present
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Minimal chunk dataclass (avoids importing the full development module
# which pulls in optional OTel dependencies)
# ---------------------------------------------------------------------------

@dataclass
class _FakeChunk:
    """Mirrors DevelopmentChunk fields used by _build_task_description helpers."""

    chunk_id: str = "chunk-1"
    description: str = "Implement the widget module"
    dependencies: List[str] = field(default_factory=list)
    file_targets: List[str] = field(default_factory=lambda: ["src/widget.py"])
    implementation_prompt: str = ""
    test_commands: List[str] = field(default_factory=list)
    max_retries: int = 5
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Part 1: YAML template loading
# ============================================================================


class TestImplementYamlLoading:
    """Verify implement.yaml loads without error and all templates are valid."""

    TEMPLATE_NAMES = [
        "project_identity",
        "target_files_edit",
        "target_files_create",
        "existing_files",
        "edit_first_directive",
        "edit_mode_classification",
        "design_doc_edit",
        "design_doc_create",
        "task_summary_label",
        "retry_feedback",
    ]

    def test_all_templates_load(self):
        """All 10 templates load without error."""
        from startd8.contractors.artisan_phases.prompts import get_template

        for name in self.TEMPLATE_NAMES:
            tmpl = get_template("implement", name)
            assert isinstance(tmpl, str), f"{name} should return a string"
            assert len(tmpl) > 10, f"{name} template is suspiciously short"

    @pytest.mark.parametrize("name", TEMPLATE_NAMES)
    def test_template_is_formattable(self, name):
        """Each template can be passed through str.format() without KeyError."""
        from startd8.contractors.artisan_phases.prompts import get_template

        tmpl = get_template("implement", name)
        # Build a kwargs dict that maps every {placeholder} to a test value
        import re
        placeholders = set(re.findall(r"\{(\w+)\}", tmpl))
        kwargs = {p: f"TEST_{p}" for p in placeholders}
        result = tmpl.format(**kwargs)
        assert isinstance(result, str)
        # Should not contain unfilled placeholders
        for p in placeholders:
            assert f"TEST_{p}" in result

    def test_template_count(self):
        """implement.yaml contains exactly 15 prompt entries."""
        from startd8.contractors.artisan_phases.prompts import _load_file

        data = _load_file("implement")
        assert len(data["prompts"]) == 15


# ============================================================================
# Part 2: _build_task_description integration tests
# ============================================================================


def _make_executor():
    """Create a LeadContractorChunkExecutor with mocked dependencies."""
    from startd8.contractors.artisan_phases.development import (
        LeadContractorChunkExecutor,
    )

    with patch.object(
        LeadContractorChunkExecutor, "__init__", lambda self, **kw: None
    ):
        executor = LeadContractorChunkExecutor.__new__(
            LeadContractorChunkExecutor
        )
    return executor


class TestTargetFilesVerb:
    """B-1/B-7: Target files section uses mode-appropriate verb."""

    def test_edit_mode_uses_update_verb(self):
        """When existing files are present, use 'update' not 'generate'."""
        executor = _make_executor()
        chunk = _FakeChunk(
            file_targets=["src/widget.py"],
            metadata={
                "_existing_file_contents": {"src/widget.py": "class Widget:\n    pass\n"},
            },
        )
        result = executor._build_task_description(chunk, {})
        target_section = result.split("## Target Files")[1].split("---")[0]
        assert "update" in target_section.lower()
        # Should NOT contain "generate" in the target files section
        assert "generate" not in target_section.lower()

    def test_create_mode_uses_generate_verb(self):
        """When no existing files, use 'generate' not 'update'."""
        executor = _make_executor()
        chunk = _FakeChunk(
            file_targets=["src/new_widget.py"],
            metadata={},
        )
        result = executor._build_task_description(chunk, {})
        target_section = result.split("## Target Files")[1].split("---")[0]
        assert "generate" in target_section.lower()

    def test_edit_mode_from_classification_only(self):
        """Edit mode classification without existing contents still uses 'update'."""
        executor = _make_executor()
        chunk = _FakeChunk(
            file_targets=["src/widget.py"],
            metadata={
                "_edit_mode": {"mode": "edit", "confidence": "high"},
            },
        )
        result = executor._build_task_description(chunk, {})
        target_section = result.split("## Target Files")[1].split("---")[0]
        assert "update" in target_section.lower()


class TestEditModeClassificationVisibility:
    """B-3: Edit Mode Classification section appears for ALL modes."""

    def test_edit_mode_classification_shown_for_edit(self):
        """Classification section rendered when mode is 'edit'."""
        executor = _make_executor()
        chunk = _FakeChunk(
            metadata={
                "_edit_mode": {
                    "mode": "edit",
                    "confidence": "high",
                    "per_file": {
                        "src/widget.py": {"mode": "edit", "staleness": "low"},
                    },
                },
                "_existing_file_contents": {"src/widget.py": "pass\n"},
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "## Edit Mode Classification" in result
        assert "EDIT" in result.split("## Edit Mode Classification")[1].split("---")[0]
        assert "MINIMUM OUTPUT" in result

    def test_edit_mode_classification_shown_for_create(self):
        """B-3 fix: Classification section rendered when mode is 'create'."""
        executor = _make_executor()
        chunk = _FakeChunk(
            metadata={
                "_edit_mode": {"mode": "create", "confidence": "high"},
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "## Edit Mode Classification" in result
        assert "CREATE" in result.split("## Edit Mode Classification")[1].split("---")[0]
        assert "NEW FILE" in result

    def test_no_classification_when_absent(self):
        """No classification section when _edit_mode is not set."""
        executor = _make_executor()
        chunk = _FakeChunk(metadata={})
        result = executor._build_task_description(chunk, {})
        assert "## Edit Mode Classification" not in result


class TestDesignFraming:
    """B-5: Design framing conditioned on existing files."""

    def test_edit_framing_with_existing_files(self):
        """When existing files present, use edit framing ('CHANGES to apply')."""
        executor = _make_executor()
        chunk = _FakeChunk(
            metadata={
                "_existing_file_contents": {
                    "src/widget.py": "class Widget:\n    pass\n"
                },
                "design_document": "## Overview\nAdd a new method.\n## API\ndef foo(): ...\n",
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "AUTHORITATIVE Design Changes" in result
        assert "CHANGES to apply" in result
        # Should NOT contain greenfield framing
        assert "FULL scope" not in result
        assert "MUST appear in your output" not in result

    def test_greenfield_framing_without_existing_files(self):
        """When no existing files, use greenfield framing."""
        executor = _make_executor()
        chunk = _FakeChunk(
            metadata={
                "design_document": "## Overview\nBuild widget.\n## API\ndef foo(): ...\n",
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "AUTHORITATIVE Design Document" in result
        assert "FULL scope" in result

    def test_design_scope_shown_in_both_modes(self):
        """Design Scope line appears regardless of edit/create framing."""
        executor = _make_executor()
        design = "## Overview\nContent here.\n## API\nMore content.\n"

        # Edit mode
        chunk_edit = _FakeChunk(
            metadata={
                "_existing_file_contents": {"src/x.py": "pass\n"},
                "design_document": design,
            },
        )
        result_edit = executor._build_task_description(chunk_edit, {})
        assert "Design Scope:" in result_edit

        # Create mode
        chunk_create = _FakeChunk(
            metadata={"design_document": design},
        )
        result_create = executor._build_task_description(chunk_create, {})
        assert "Design Scope:" in result_create

    def test_task_summary_label_demoted_when_design_present(self):
        """Task Summary section is labeled as 'label only' when design doc exists."""
        executor = _make_executor()
        chunk = _FakeChunk(
            metadata={
                "design_document": "## Overview\nSome design.\n",
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "Task Summary (label only" in result


class TestRetryFeedback:
    """Retry feedback section rendering."""

    def test_retry_feedback_with_error(self):
        executor = _make_executor()
        chunk = _FakeChunk(metadata={})
        result = executor._build_task_description(
            chunk, {"last_error": "SyntaxError: unexpected indent"}
        )
        assert "Retry Feedback" in result
        assert "SyntaxError" in result

    def test_no_retry_section_when_no_errors(self):
        executor = _make_executor()
        chunk = _FakeChunk(metadata={})
        result = executor._build_task_description(chunk, {})
        assert "Retry Feedback" not in result


class TestEditFirstDirective:
    """Edit-First Directive with size constraint."""

    def test_size_constraint_calculated_correctly(self):
        """80% minimum line count is calculated from existing files."""
        executor = _make_executor()
        existing_content = "\n".join(f"line {i}" for i in range(100))  # 100 lines
        chunk = _FakeChunk(
            metadata={
                "_existing_file_contents": {"src/big.py": existing_content},
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "Edit-First Directive" in result
        assert "100 lines" in result
        assert "80 lines" in result

    def test_no_directive_without_existing(self):
        """No Edit-First Directive when no existing files."""
        executor = _make_executor()
        chunk = _FakeChunk(metadata={})
        result = executor._build_task_description(chunk, {})
        assert "Edit-First Directive" not in result
