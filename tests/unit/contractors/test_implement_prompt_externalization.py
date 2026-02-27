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
        "coding_standards",
        "output_format_single",
        "output_format_multi",
        "critical_parameters",
        "forward_contracts",
        "completeness_warning",
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
        """implement.yaml contains exactly 24 prompt entries (18 original + 6 IMP quality templates)."""
        from startd8.contractors.artisan_phases.prompts import _load_file

        data = _load_file("implement")
        assert len(data["prompts"]) == 24


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


# ============================================================================
# Part 5: Design doc target-file filtering (DF-1)
# ============================================================================


class TestDesignDocTargetFiltering:
    """DF-1: Design doc code blocks are filtered to only include target files.

    _filter_design_doc_for_targets() redacts fenced code blocks in
    ``### <filepath>`` sections when the file is not in file_targets, while
    preserving all prose context.
    """

    @staticmethod
    def _filter(doc: str, targets: List[str]) -> str:
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )
        return LeadContractorChunkExecutor._filter_design_doc_for_targets(doc, targets)

    # -- basic filtering behaviour ------------------------------------------

    def test_non_target_code_block_replaced_with_placeholder(self):
        """Code block under ### <non-target-file> is replaced."""
        doc = (
            "## Overview\nSome prose.\n"
            "### src/target.py\n"
            "```python\ndef target(): pass\n```\n"
            "### src/other.py\n"
            "```python\ndef other(): pass\n```\n"
        )
        result = self._filter(doc, ["src/target.py"])
        # Target file's code is preserved
        assert "def target(): pass" in result
        # Non-target file's code is redacted
        assert "def other(): pass" not in result
        assert "not a target file" in result
        assert "`src/other.py`" in result

    def test_target_code_block_preserved(self):
        """Code block under ### <target-file> is kept verbatim."""
        doc = (
            "### pyproject.toml\n"
            "```toml\n[build-system]\nrequires = [\"setuptools\"]\n```\n"
        )
        result = self._filter(doc, ["pyproject.toml"])
        assert "[build-system]" in result
        assert "not a target file" not in result

    def test_all_targets_match_no_filtering(self):
        """When every ### file section is a target, doc is returned unchanged."""
        doc = (
            "### src/a.py\n```python\npass\n```\n"
            "### src/b.py\n```python\npass\n```\n"
        )
        result = self._filter(doc, ["src/a.py", "src/b.py"])
        assert result == doc

    def test_empty_targets_returns_unchanged(self):
        """Empty file_targets list means no filtering."""
        doc = "### src/x.py\n```python\ncode\n```\n"
        assert self._filter(doc, []) == doc

    # -- prose preservation -------------------------------------------------

    def test_prose_in_non_target_section_preserved(self):
        """Prose under a non-target ### section is kept; only code is redacted."""
        doc = (
            "### tests/__init__.py\n"
            "This file marks the test package.\n"
            "```python\n# empty\n```\n"
            "It should be committed.\n"
        )
        result = self._filter(doc, ["src/main.py"])
        assert "marks the test package" in result
        assert "should be committed" in result
        assert "# empty" not in result

    def test_top_level_sections_always_preserved(self):
        """## sections (non-file) are never filtered."""
        doc = (
            "## Architecture\nImportant design context.\n"
            "```\ndiagram here\n```\n"
            "### src/other.py\n"
            "```python\ndef x(): pass\n```\n"
        )
        result = self._filter(doc, ["src/main.py"])
        assert "Important design context" in result
        assert "diagram here" in result
        # Non-target file section code is redacted
        assert "def x(): pass" not in result

    def test_non_file_subsections_preserved(self):
        """### headings that don't look like file paths are kept intact."""
        doc = (
            "### Build System & Dependencies\n"
            "```toml\n[build-system]\nrequires = [\"setuptools\"]\n```\n"
            "### Developer Setup\n"
            "```bash\npip install -e .\n```\n"
        )
        result = self._filter(doc, ["src/main.py"])
        # These aren't file-path headings, so nothing is filtered
        assert "[build-system]" in result
        assert "pip install -e ." in result

    # -- normalisation and edge cases ---------------------------------------

    def test_basename_matching(self):
        """Target 'src/hybrid_scaffold.py' matches heading 'src/hybrid_scaffold.py'."""
        doc = "### src/hybrid_scaffold.py\n```python\ncode\n```\n"
        result = self._filter(doc, ["src/hybrid_scaffold.py"])
        assert "code" in result
        assert "not a target file" not in result

    def test_leading_dot_slash_stripped(self):
        """./src/x.py in targets matches src/x.py in heading."""
        doc = "### src/x.py\n```python\ncode\n```\n"
        result = self._filter(doc, ["./src/x.py"])
        assert "code" in result
        assert "not a target file" not in result

    def test_backtick_wrapped_heading(self):
        """### `src/x.py` (backtick-wrapped) is recognised as a file path."""
        doc = "### `src/x.py`\n```python\ncode\n```\n"
        result = self._filter(doc, ["src/other.py"])
        assert "code" not in result
        assert "not a target file" in result

    def test_multiple_code_blocks_in_non_target_section(self):
        """All code blocks within a non-target section are redacted."""
        doc = (
            "### tests/test_main.py\n"
            "First block:\n"
            "```python\ndef test_a(): pass\n```\n"
            "Second block:\n"
            "```python\ndef test_b(): pass\n```\n"
        )
        result = self._filter(doc, ["src/main.py"])
        assert "def test_a" not in result
        assert "def test_b" not in result
        assert "First block:" in result
        assert "Second block:" in result

    def test_section_reset_at_h2(self):
        """## heading resets the non-target state."""
        doc = (
            "### src/other.py\n"
            "```python\nhidden\n```\n"
            "## Testing Strategy\n"
            "```python\n# test example - should survive\n```\n"
        )
        result = self._filter(doc, ["src/main.py"])
        assert "hidden" not in result
        assert "# test example - should survive" in result

    # -- integration with _build_design_framing ----------------------------

    def test_build_design_framing_uses_filtered_doc(self):
        """_build_design_framing injects the filtered doc, not the raw one."""
        executor = _make_executor()
        doc = (
            "## Overview\nContext.\n"
            "### src/widget.py\n```python\ndef widget(): pass\n```\n"
            "### tests/test_widget.py\n```python\ndef test_it(): pass\n```\n"
        )
        chunk = _FakeChunk(
            file_targets=["src/widget.py"],
            metadata={"design_document": doc},
        )
        result = executor._build_task_description(chunk, {})
        assert "def widget(): pass" in result
        assert "def test_it(): pass" not in result
        assert "not a target file" in result

    def test_scope_metrics_reflect_filtered_doc(self):
        """Design Scope line counts reflect the filtered doc, not the raw one."""
        executor = _make_executor()
        # 2-line code block in non-target section will be replaced by 1 placeholder line
        doc = (
            "## Overview\nLine.\n"
            "### src/removed.py\n"
            "```python\nline1\nline2\nline3\nline4\nline5\n```\n"
        )
        chunk = _FakeChunk(
            file_targets=["src/other.py"],
            metadata={"design_document": doc},
        )
        result = executor._build_task_description(chunk, {})
        # The raw doc has 10 lines; filtered should be fewer
        assert "Design Scope:" in result


# ============================================================================
# Part 6: IMP quality improvements (coding standards, output format, etc.)
# ============================================================================


def _make_artisan_executor():
    """Create an ArtisanChunkExecutor with mocked dependencies."""
    from startd8.contractors.artisan_phases.development import (
        ArtisanChunkExecutor,
    )

    with patch.object(
        ArtisanChunkExecutor, "__init__", lambda self, **kw: None
    ):
        executor = ArtisanChunkExecutor.__new__(ArtisanChunkExecutor)
    return executor


class TestCodingStandards:
    """IMP-CS: Coding standards section appears in task description."""

    def test_coding_standards_section_present(self):
        """Coding standards section is always present in artisan output."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(metadata={})
        result = executor._build_task_description(chunk, {})
        assert "Coding Standards" in result
        assert "ruff" in result.lower() or "E741" in result


class TestOutputFormat:
    """IMP-OF: Structured output format section."""

    def test_output_format_single_file(self):
        """Single-file tasks get single-format output instructions."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(
            file_targets=["src/widget.py"],
            metadata={},
        )
        result = executor._build_task_description(chunk, {})
        assert "## Output Format" in result
        assert "single" in result.lower() or "fenced code block" in result.lower()

    def test_output_format_multi_file(self):
        """Multi-file tasks get multi-format output with verification checklist."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(
            file_targets=["src/widget.py", "src/__init__.py", "src/utils.py"],
            metadata={},
        )
        result = executor._build_task_description(chunk, {})
        assert "## Output Format" in result
        assert "MULTIPLE" in result or "REQUIRED files" in result
        assert "VERIFICATION CHECKLIST" in result
        # All files appear in the checklist
        assert "src/widget.py" in result
        assert "src/__init__.py" in result
        assert "src/utils.py" in result

    def test_no_output_format_without_targets(self):
        """No output format section when file_targets is empty."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(file_targets=[], metadata={})
        result = executor._build_task_description(chunk, {})
        # Should not have output format section (may have other sections)
        sections = [s for s in result.split("## ") if s.startswith("Output Format")]
        assert len(sections) == 0


class TestCriticalParameters:
    """IMP-CP: Critical parameter elevation."""

    def test_critical_parameters_elevated(self):
        """Critical params from metadata appear in task description."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(
            metadata={
                "critical_parameters": [
                    "api_key: str (required, from env WAYFINDER_API_KEY)",
                    "timeout_ms: int (default 5000)",
                ],
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "Critical Parameters" in result
        assert "api_key" in result
        assert "timeout_ms" in result

    def test_no_critical_params_when_absent(self):
        """No critical parameters section when metadata is empty."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(metadata={})
        result = executor._build_task_description(chunk, {})
        assert "Critical Parameters" not in result


class TestForwardContractsImplement:
    """IMP-FC: Forward contract bindings in implement phase."""

    def test_forward_contracts_in_implement(self):
        """Forward contracts from metadata appear in implement prompt."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(
            metadata={
                "forward_contracts": [
                    "generate_manifests(ctx: GenerationContext) -> List[ArtifactManifest]",
                    "validate_template(path: Path) -> ValidationResult",
                ],
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "Interface Contract Bindings" in result
        assert "generate_manifests" in result
        assert "validate_template" in result

    def test_no_forward_contracts_when_absent(self):
        """No contracts section when metadata is empty."""
        executor = _make_artisan_executor()
        chunk = _FakeChunk(metadata={})
        result = executor._build_task_description(chunk, {})
        assert "Interface Contract Bindings" not in result


class TestRequirementsTextFraming:
    """IMP-R1: Requirements text uses authoritative framing."""

    def test_requirements_text_verbatim_framing(self):
        """Requirements section uses 'verbatim — authoritative' label."""
        executor = _make_executor()
        chunk = _FakeChunk(
            metadata={
                "requirements_text": "The ingestion engine SHALL parse all YAML files.",
            },
        )
        result = executor._build_task_description(chunk, {})
        assert "authoritative" in result.lower()
        assert "SHALL parse all YAML" in result
