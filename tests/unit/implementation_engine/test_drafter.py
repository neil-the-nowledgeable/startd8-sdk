"""Tests for implementation_engine.drafter — draft generation and helpers."""

import pytest
from unittest.mock import Mock, patch

from startd8.implementation_engine.budget import (
    EXISTING_FILES_BUDGET_BYTES,
    SEARCH_REPLACE_LINE_THRESHOLD,
)
from startd8.implementation_engine.drafter import (
    build_existing_files_section,
    build_output_format,
    create_draft,
    detect_size_regression,
    get_drafter_system_prompt,
)


# ---------------------------------------------------------------------------
# get_drafter_system_prompt
# ---------------------------------------------------------------------------

class TestGetDrafterSystemPrompt:
    def test_create_mode_no_files(self):
        prompt = get_drafter_system_prompt()
        assert "implement" in prompt.lower() or "engineer" in prompt.lower()

    def test_edit_mode_small_files(self):
        files = {"app.py": "line\n" * 10}
        prompt = get_drafter_system_prompt(files)
        # Small files → edit mode (not search/replace)
        assert "edit" in prompt.lower() or "existing" in prompt.lower()

    def test_search_replace_mode_large_file(self):
        # File with >= 50 lines triggers search/replace
        content = "\n".join(f"line {i}" for i in range(SEARCH_REPLACE_LINE_THRESHOLD))
        files = {"big.py": content}
        prompt = get_drafter_system_prompt(files)
        assert "search" in prompt.lower() or "replace" in prompt.lower() or "large" in prompt.lower()

    def test_search_replace_any_file_triggers(self):
        big = "\n".join(f"line {i}" for i in range(60))
        files = {"small.py": "x = 1\n", "big.py": big}
        prompt = get_drafter_system_prompt(files)
        # At least one file >= 50 lines → search/replace mode
        assert prompt == get_drafter_system_prompt({"big.py": big})

    def test_empty_dict_creates_mode(self):
        prompt = get_drafter_system_prompt({})
        create_prompt = get_drafter_system_prompt()
        assert prompt == create_prompt

    def test_none_content_handled(self):
        # None content treated as empty → 0 lines
        files = {"app.py": None}
        prompt = get_drafter_system_prompt(files)
        assert isinstance(prompt, str)


# ---------------------------------------------------------------------------
# build_existing_files_section
# ---------------------------------------------------------------------------

class TestBuildExistingFilesSection:
    def test_empty_returns_empty(self):
        assert build_existing_files_section() == ""
        assert build_existing_files_section({}) == ""
        assert build_existing_files_section(None) == ""

    def test_single_file_included(self):
        files = {"app.py": "def main():\n    pass\n"}
        result = build_existing_files_section(files)
        assert "app.py" in result
        assert "def main()" in result
        assert "EDIT MODE" in result

    def test_budget_enforcement(self):
        # Create files exceeding budget
        content = "x" * (EXISTING_FILES_BUDGET_BYTES + 1000)
        files = {"huge.py": content}
        result = build_existing_files_section(files)
        assert "TRUNCATED" in result

    def test_multiple_files_sorted(self):
        files = {
            "small.py": "x = 1\n",
            "big.py": "y = 2\n" * 100,
        }
        result = build_existing_files_section(files)
        assert "small.py" in result
        assert "big.py" in result

    def test_edit_mode_files_first(self):
        files = {
            "create.py": "new = 1\n",
            "edit.py": "old = 2\n",
        }
        edit_mode = {
            "per_file": {
                "edit.py": {"mode": "edit"},
                "create.py": {"mode": "create"},
            }
        }
        result = build_existing_files_section(files, edit_mode)
        edit_pos = result.index("edit.py")
        create_pos = result.index("create.py")
        assert edit_pos < create_pos

    def test_omitted_files_listed(self):
        # First file fills the budget
        big_content = "x\n" * (EXISTING_FILES_BUDGET_BYTES // 2 + 1)
        files = {
            "big1.py": big_content,
            "big2.py": big_content,
            "omitted.py": big_content,
        }
        result = build_existing_files_section(files)
        # At least one file should be omitted
        if "Omitted Files" in result:
            assert "preserved as-is" in result

    def test_edit_confidence_displayed(self):
        files = {"f.py": "code\n"}
        edit_mode = {"confidence": "high"}
        result = build_existing_files_section(files, edit_mode)
        assert "high" in result


# ---------------------------------------------------------------------------
# build_output_format
# ---------------------------------------------------------------------------

class TestBuildOutputFormat:
    def test_single_file_create(self):
        result = build_output_format()
        assert "implementation" in result.lower() or "code" in result.lower()

    def test_single_file_edit(self):
        result = build_output_format(existing_files={"f.py": "x\n" * 10})
        assert "EDIT" in result or "edit" in result or "modified" in result.lower()

    def test_multi_file_create(self):
        result = build_output_format(target_files=["a.py", "b.py"])
        assert "a.py" in result
        assert "b.py" in result

    def test_multi_file_edit(self):
        result = build_output_format(
            target_files=["a.py", "b.py"],
            existing_files={"a.py": "code\n"},
        )
        assert "a.py" in result

    def test_init_py_sorted_first(self):
        result = build_output_format(target_files=["z.py", "__init__.py"])
        init_pos = result.index("__init__.py")
        z_pos = result.index("z.py")
        assert init_pos < z_pos

    def test_single_target_file(self):
        result = build_output_format(target_files=["only.py"])
        # Single file → simple format
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# detect_size_regression
# ---------------------------------------------------------------------------

class TestDetectSizeRegression:
    def test_no_existing_files(self):
        assert detect_size_regression(None, "code") is False
        assert detect_size_regression({}, "code") is False

    def test_no_implementation(self):
        assert detect_size_regression({"f.py": "x\n" * 100}, "") is False

    def test_existing_below_minimum(self):
        # 10 lines, below DRAFT_SIZE_REGRESSION_MIN_LINES (50)
        files = {"f.py": "line\n" * 10}
        assert detect_size_regression(files, "x\n") is False

    def test_normal_size_no_regression(self):
        # 100 existing lines, 50 extracted → 50% > 20% threshold
        files = {"f.py": "line\n" * 100}
        code = "line\n" * 50
        assert detect_size_regression(files, code) is False

    def test_regression_detected(self):
        # 100 existing lines, 5 extracted → 5% < 20% threshold
        files = {"f.py": "line\n" * 100}
        code = "line\n" * 5
        assert detect_size_regression(files, code) is True

    def test_zero_existing_lines(self):
        files = {"f.py": ""}
        assert detect_size_regression(files, "code\n") is False

    def test_boundary_at_threshold(self):
        # Exactly at threshold: 20 lines out of 100 = 20%
        files = {"f.py": "line\n" * 100}
        code = "line\n" * 20
        # 20/100 = 0.20, not < 0.20
        assert detect_size_regression(files, code) is False

    def test_just_below_threshold(self):
        # 19 lines out of 100 = 19% < 20%
        files = {"f.py": "line\n" * 100}
        code = "line\n" * 19
        assert detect_size_regression(files, code) is True


# ---------------------------------------------------------------------------
# create_draft
# ---------------------------------------------------------------------------

class TestCreateDraft:
    def _make_agent(self, response_text="def foo(): pass", was_truncated=False):
        agent = Mock()
        agent.name = "test-drafter"
        agent.model = "test-model"
        token_usage = Mock()
        token_usage.input = 100
        token_usage.output = 200
        token_usage.was_truncated = was_truncated
        agent.generate.return_value = (response_text, 500, token_usage)
        return agent

    def _make_spec(self, raw_spec="Build a function"):
        spec = Mock()
        spec.raw_spec = raw_spec
        spec.spec_id = "spec-test"
        return spec

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_basic_draft(self, mock_extract):
        mock_extract.return_value = "def foo(): pass"
        agent = self._make_agent()
        spec = self._make_spec()

        draft = create_draft(agent, spec)

        assert draft.implementation == "def foo(): pass"
        assert draft.iteration == 1
        assert draft.spec_id == "spec-test"
        assert draft.agent_name == "test-drafter"
        assert draft.model == "test-model"
        assert draft.was_truncated is False
        agent.generate.assert_called_once()

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_api_truncation_detected(self, mock_extract):
        mock_extract.return_value = "partial code"
        agent = self._make_agent(was_truncated=True)
        spec = self._make_spec()

        draft = create_draft(agent, spec)

        assert draft.was_truncated is True
        assert draft.truncation_source == "api"

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_feedback_passed_to_prompt(self, mock_extract):
        mock_extract.return_value = "code"
        agent = self._make_agent()
        spec = self._make_spec()

        create_draft(agent, spec, feedback="Fix the bug", iteration=2)

        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "Fix the bug" in prompt

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_duck_typed_spec_no_raw_spec(self, mock_extract):
        mock_extract.return_value = "code"
        agent = self._make_agent()
        spec = "Just a string spec"

        draft = create_draft(agent, spec)

        assert draft.implementation == "code"

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_existing_files_edit_mode(self, mock_extract):
        mock_extract.return_value = "modified code"
        agent = self._make_agent()
        spec = self._make_spec()
        existing = {"app.py": "original = True\n"}

        draft = create_draft(agent, spec, existing_files=existing)

        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        # Should use edit template
        assert "app.py" in prompt or "existing" in prompt.lower()

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_truncation_check_disabled(self, mock_extract):
        mock_extract.return_value = "code"
        agent = self._make_agent()
        spec = self._make_spec()

        draft = create_draft(agent, spec, check_truncation=False)

        assert draft.was_truncated is False

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_cost_calculated(self, mock_extract):
        mock_extract.return_value = "code"
        agent = self._make_agent()
        spec = self._make_spec()

        draft = create_draft(agent, spec)

        # Cost should be set (may be 0.0 for unknown models)
        assert isinstance(draft.cost, float)
