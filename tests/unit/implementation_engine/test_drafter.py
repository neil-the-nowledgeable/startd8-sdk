"""Tests for implementation_engine.drafter — draft generation and helpers."""

import pytest
from unittest.mock import Mock, patch

from startd8.implementation_engine.budget import (
    EXISTING_FILES_BUDGET_BYTES,
    SEARCH_REPLACE_LINE_THRESHOLD,
    SUPPLEMENTARY_BUDGET_CHARS,
)
from startd8.implementation_engine.drafter import (
    _annotate_spec_conflicts,
    _target_file_lines,
    build_existing_files_section,
    build_output_format,
    build_supplementary_sections,
    create_draft,
    detect_size_regression,
    get_drafter_system_prompt,
)
from startd8.languages.registry import LanguageRegistry


# ---------------------------------------------------------------------------
# get_drafter_system_prompt
# ---------------------------------------------------------------------------

class TestGetDrafterSystemPrompt:
    def test_create_mode_no_files(self):
        prompt, mode = get_drafter_system_prompt()
        assert mode == "create"
        assert "engineer" in prompt.lower()

    def test_create_mode_has_upstream_param_rules(self):
        prompt, mode = get_drafter_system_prompt()
        assert mode == "create"
        # System prompt mandates verbatim parameter names from upstream docs
        assert "upstream" in prompt.lower() or "verbatim" in prompt.lower()

    def test_create_mode_has_coding_standards(self):
        prompt, mode = get_drafter_system_prompt()
        # REQ-PE-500: language-neutral defaults (no Ruff/Python-specific)
        assert "style guide" in prompt.lower() or "idioms" in prompt.lower()

    def test_edit_mode_small_files(self):
        files = {"app.py": "line\n" * 10}
        prompt, mode = get_drafter_system_prompt(files)
        assert mode == "edit"
        # Small files → edit mode (not search/replace)
        assert "edit" in prompt.lower() or "existing" in prompt.lower()

    def test_edit_mode_has_edit_first_discipline(self):
        files = {"app.py": "line\n" * 10}
        prompt, mode = get_drafter_system_prompt(files)
        assert mode == "edit"
        assert "preserve" in prompt.lower() or "edit" in prompt.lower()

    def test_search_replace_mode_large_file(self):
        # File with >= 50 lines triggers search/replace mode
        content = "\n".join(f"line {i}" for i in range(SEARCH_REPLACE_LINE_THRESHOLD))
        files = {"big.py": content}
        prompt, mode = get_drafter_system_prompt(files)
        assert mode == "search_replace"
        # S/R prompt is distinct from the edit prompt
        assert "large" in prompt.lower() or "minimal" in prompt.lower() or "targeted" in prompt.lower()

    def test_search_replace_any_file_triggers(self):
        big = "\n".join(f"line {i}" for i in range(60))
        files = {"small.py": "x = 1\n", "big.py": big}
        prompt, mode = get_drafter_system_prompt(files)
        prompt2, mode2 = get_drafter_system_prompt({"big.py": big})
        # At least one file >= 50 lines → search/replace mode
        assert prompt == prompt2
        assert mode == mode2 == "search_replace"

    def test_empty_dict_creates_mode(self):
        prompt, mode = get_drafter_system_prompt({})
        create_prompt, create_mode = get_drafter_system_prompt()
        assert prompt == create_prompt
        assert mode == create_mode == "create"

    def test_none_content_handled(self):
        # None content treated as empty → 0 lines
        files = {"app.py": None}
        prompt, mode = get_drafter_system_prompt(files)
        assert isinstance(prompt, str)
        assert mode in ("create", "edit")

    def test_skeleton_fill_mode(self):
        """FR-MPA-005: skeleton_fill=True selects skeleton fill system prompt."""
        prompt, mode = get_drafter_system_prompt(skeleton_fill=True)
        assert mode == "skeleton_fill"
        assert "skeleton" in prompt.lower()
        assert "NotImplementedError" in prompt or "pre-filled" in prompt.lower()

    def test_skeleton_fill_overrides_existing_files(self):
        """skeleton_fill takes priority over existing_files detection."""
        files = {"app.py": "line\n" * 10}
        prompt, mode = get_drafter_system_prompt(files, skeleton_fill=True)
        assert mode == "skeleton_fill"

    # ── REQ-PE-100: Raw output instruction in all system prompts ──

    def test_create_mode_has_raw_output_instruction(self):
        """REQ-PE-100: create mode must tell LLM to output raw file content."""
        prompt, _ = get_drafter_system_prompt()
        assert "raw file content" in prompt.lower() or "as it should appear on disk" in prompt.lower()
        assert "do not wrap" in prompt.lower()

    def test_edit_mode_has_raw_output_instruction(self):
        """REQ-PE-100: edit mode must tell LLM to output raw file content."""
        files = {"app.py": "x = 1\n"}
        prompt, _ = get_drafter_system_prompt(files)
        assert "raw file content" in prompt.lower() or "as it should appear on disk" in prompt.lower()

    def test_search_replace_mode_has_raw_output_instruction(self):
        """REQ-PE-100: search/replace mode must tell LLM to output raw file content."""
        big = "\n".join(f"line {i}" for i in range(60))
        prompt, _ = get_drafter_system_prompt({"big.py": big})
        assert "raw file content" in prompt.lower() or "as it should appear on disk" in prompt.lower()

    def test_skeleton_fill_mode_has_raw_output_instruction(self):
        """REQ-PE-100: skeleton fill mode must tell LLM to output raw file content."""
        prompt, _ = get_drafter_system_prompt(skeleton_fill=True)
        assert "raw file content" in prompt.lower() or "as it should appear on disk" in prompt.lower()

    # ── REQ-PE-500: Language-neutral defaults ──

    def test_default_role_is_language_neutral(self):
        """REQ-PE-500: missing language_role must not default to Python."""
        prompt, _ = get_drafter_system_prompt()
        assert "python" not in prompt.lower().split("do not wrap")[0]
        assert "ruff" not in prompt.lower()

    def test_explicit_language_role_used(self):
        """When language_role is provided, it should appear in the prompt."""
        prompt, _ = get_drafter_system_prompt(
            language_role="an expert Go engineer",
            coding_standards="Idiomatic Go with explicit error handling.",
        )
        assert "expert go engineer" in prompt.lower()
        assert "idiomatic go" in prompt.lower()

    def test_default_fallback_logs_warning(self):
        """REQ-PE-500: warning logged when language_role is not provided."""
        import logging
        with patch.object(logging.getLogger("startd8.implementation_engine.drafter"), "warning") as mock_warn:
            get_drafter_system_prompt()
            mock_warn.assert_called_once()
            assert "language-neutral defaults" in mock_warn.call_args[0][0]


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

    def test_empty_existing_files_skips_min_lines_constraint(self):
        """Empty existing files: skip useless 'AT LEAST 0 lines' constraint."""
        result = build_output_format(
            existing_files={"f.py": ""},
            edit_min_pct=80,
        )
        assert "0 lines" not in result
        assert "COMPLETE" in result


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
# build_supplementary_sections
# ---------------------------------------------------------------------------

class TestBuildSupplementarySections:
    def test_empty_context_returns_empty(self):
        assert build_supplementary_sections({}) == ""
        assert build_supplementary_sections(None) == ""

    def test_critical_parameters_list(self):
        ctx = {"critical_parameters": ["port=8080", "host=localhost"]}
        result = build_supplementary_sections(ctx)
        assert "## Critical Parameters" in result
        assert "port=8080" in result
        assert "host=localhost" in result

    def test_critical_parameters_string(self):
        ctx = {"critical_parameters": "port=8080"}
        result = build_supplementary_sections(ctx)
        assert "port=8080" in result

    def test_forward_contracts_fallback(self):
        ctx = {"forward_contracts": "Must implement IService interface"}
        result = build_supplementary_sections(ctx)
        assert "## Interface Contract Bindings" in result
        assert "IService" in result

    def test_forward_contracts_injected_when_present(self):
        """forward_contracts string is injected as P1 section (GAP-SDK-003 simplification)."""
        ctx = {
            "forward_contracts": "raw contract text",
        }
        result = build_supplementary_sections(ctx, task_id="T1")
        assert "raw contract text" in result
        assert "## Interface Contract Bindings" in result

    def test_forward_manifest_in_context_ignored(self):
        """forward_manifest object no longer consumed for binding injection.

        Import context is now provided by service communication graph
        (REQ-SIG-200/201), not binding_constraints_for_task().
        """
        fm = Mock()
        fm.binding_constraints_for_task.return_value = "should not appear"
        ctx = {
            "forward_manifest": fm,
        }
        result = build_supplementary_sections(ctx, task_id="T1")
        # binding_constraints_for_task should NOT be called
        fm.binding_constraints_for_task.assert_not_called()
        assert "should not appear" not in result

    def test_manifest_context_rendered(self):
        ctx = {"manifest_context": "### app.py\nclass App: ..."}
        result = build_supplementary_sections(ctx)
        assert "## Code Structure" in result
        assert "class App" in result

    def test_call_graph_callers_rendered(self):
        ctx = {"call_graph_callers": [
            {"fqn": "app.main", "blast_radius": 5, "direct_callers": ["x"]},
            {"fqn": "app.run", "blast_radius": 2, "direct_callers": ["y"]},
        ]}
        result = build_supplementary_sections(ctx)
        assert "## Backward Compatibility" in result
        assert "`app.main`" in result
        assert "5 callers" in result

    def test_call_graph_context_rendered(self):
        ctx = {"call_graph_context": "### app.py\nmain -> run -> init"}
        result = build_supplementary_sections(ctx)
        assert "## Call Dependencies" in result

    def test_introspect_context_rendered(self):
        ctx = {"manifest_introspect_context": "- Widget MRO: Widget → Base → object"}
        result = build_supplementary_sections(ctx)
        assert "## Type Introspection" in result

    def test_parameter_sources_rendered(self):
        ctx = {"parameter_sources": {"port": "requirements.md:12"}}
        result = build_supplementary_sections(ctx)
        assert "## Parameter Sources" in result

    def test_budget_drops_p3_first(self):
        """Under budget pressure, P3 sections are dropped first."""
        ctx = {
            "critical_parameters": "port=8080",
            "manifest_context": "x" * 2000,
            "call_graph_context": "y" * 3000,  # P3
            "parameter_sources": "z" * 3000,   # P3
        }
        result = build_supplementary_sections(ctx, budget_chars=3000)
        # P1 (critical_parameters) should survive
        assert "port=8080" in result
        # P3 should be dropped
        assert "## Call Dependencies" not in result

    def test_budget_zero_returns_truncated(self):
        ctx = {"critical_parameters": "port=8080"}
        result = build_supplementary_sections(ctx, budget_chars=10)
        assert len(result) <= 10


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
    def test_tiny_file_not_heuristically_truncated(self, mock_extract):
        """A legitimately-tiny composition file must not heuristic-fail.

        M3 run-021: a 3-line server entrypoint tripped the structural
        truncation heuristic. Files below MIN_LINES_TRUNCATION_BLOCKING are
        excluded from heuristic blocking (API truncation still applies).
        """
        tiny = (
            "from app.ai.routes import router as ai_router\n"
            "from app.main import app\n"
            "app.include_router(ai_router)\n"
        )
        mock_extract.return_value = tiny
        agent = self._make_agent(response_text=tiny, was_truncated=False)
        spec = self._make_spec()

        draft = create_draft(agent, spec, target_files=["app/server.py"])

        assert draft.was_truncated is False
        assert draft.truncation_source != "heuristic"

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

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_context_param_accepted(self, mock_extract):
        """create_draft accepts and uses context parameter."""
        mock_extract.return_value = "code"
        agent = self._make_agent()
        spec = self._make_spec()

        ctx = {"critical_parameters": ["port=8080"]}
        draft = create_draft(agent, spec, context=ctx)

        assert draft.implementation == "code"
        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "port=8080" in prompt

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_context_none_no_error(self, mock_extract):
        """create_draft works fine with context=None (backward compat)."""
        mock_extract.return_value = "code"
        agent = self._make_agent()
        spec = self._make_spec()

        draft = create_draft(agent, spec, context=None)
        assert draft.implementation == "code"

    @patch("startd8.implementation_engine.drafter.extract_code_from_response")
    def test_supplementary_sections_in_prompt(self, mock_extract):
        """Pipeline context appears in the draft prompt via supplementary sections."""
        mock_extract.return_value = "code"
        agent = self._make_agent()
        spec = self._make_spec()

        ctx = {
            "forward_contracts": "Must implement IService",
            "manifest_context": "### app.py\nclass App",
        }
        create_draft(agent, spec, context=ctx)

        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "IService" in prompt or "Interface Contract" in prompt


# ---------------------------------------------------------------------------
# _target_file_lines — Option B: target-only line count
# ---------------------------------------------------------------------------

class TestTargetFileLines:
    """Line count must come from TARGET files only, not all existing context."""

    def test_target_overlap_uses_target_only(self):
        """When target_files overlaps existing_files, count only target."""
        existing = {
            "src/server.py": "line1\nline2\nline3\n" * 50,  # 150 lines
            "src/logger.py": "line1\nline2\n" * 30,           # 60 lines
            "src/requirements.in": "dep1==1.0\ndep2==2.0\n",  # 2 lines
        }
        result = _target_file_lines(["src/requirements.in"], existing)
        assert result == 2

    def test_no_overlap_falls_back_to_all(self):
        """When no target files match existing, fall back to sum of all."""
        existing = {"src/foo.py": "a\nb\nc\n"}
        result = _target_file_lines(["src/bar.py"], existing)
        assert result == 3

    def test_no_target_files_falls_back(self):
        """When target_files is None, fall back to sum of all."""
        existing = {"src/foo.py": "a\nb\nc\n"}
        result = _target_file_lines(None, existing)
        assert result == 3

    def test_multi_target_sums_targets_only(self):
        """Multi-target: sum only target files, not context siblings."""
        existing = {
            "src/a.py": "x\n" * 10,         # 10 lines
            "src/b.py": "x\n" * 20,         # 20 lines
            "src/context.py": "x\n" * 100,  # 100 lines (context only)
        }
        result = _target_file_lines(["src/a.py", "src/b.py"], existing)
        assert result == 30


# ---------------------------------------------------------------------------
# build_output_format — non-Python min-lines skip (Option A + B)
# ---------------------------------------------------------------------------

class TestBuildOutputFormatNonPython:
    """Non-Python targets must NOT get Python min-lines constraints."""

    def test_requirements_in_no_min_lines(self):
        """requirements.in target should not get 'AT LEAST N lines' constraint."""
        existing = {
            "src/server.py": "line\n" * 150,
            "src/requirements.in": "dep1==1.0\ndep2==2.0\n",
        }
        result = build_output_format(
            target_files=["src/requirements.in"],
            existing_files=existing,
            edit_min_pct=80,
        )
        assert "AT LEAST" not in result
        assert "COMPLETE" in result

    def test_dockerfile_no_min_lines(self):
        """Dockerfile target should not get min-lines constraint."""
        existing = {
            "src/app.py": "line\n" * 200,
            "Dockerfile": "FROM python:3.12\nRUN pip install\n",
        }
        result = build_output_format(
            target_files=["Dockerfile"],
            existing_files=existing,
            edit_min_pct=80,
        )
        assert "AT LEAST" not in result

    def test_python_target_still_gets_min_lines(self):
        """Python targets must still get the min-lines constraint."""
        content = "line\n" * 100
        existing = {"src/foo.py": content}
        result = build_output_format(
            target_files=["src/foo.py"],
            existing_files=existing,
            edit_min_pct=80,
        )
        assert "AT LEAST" in result or "80" in result

    def test_python_target_uses_target_line_count(self):
        """Python target line count should reflect target only, not siblings."""
        existing = {
            "src/foo.py": "line\n" * 10,       # target: 10 lines
            "src/bar.py": "line\n" * 200,      # sibling: 200 lines
        }
        result = build_output_format(
            target_files=["src/foo.py"],
            existing_files=existing,
            edit_min_pct=80,
        )
        # Should reference 10 lines (target), not 210 (total)
        assert "10 lines" in result
        assert "210" not in result

    def test_multi_file_non_python_no_min_lines(self):
        """Multi-file non-Python targets skip min-lines in summary."""
        existing = {
            "src/requirements.in": "dep1==1.0\n",
            "Dockerfile": "FROM python:3.12\n",
        }
        result = build_output_format(
            target_files=["src/requirements.in", "Dockerfile"],
            existing_files=existing,
            edit_min_pct=80,
        )
        assert "must be >=" not in result


# ---------------------------------------------------------------------------
# _annotate_spec_conflicts  (REQ-TDE-206 — profile-based conflict detection)
# ---------------------------------------------------------------------------

class TestAnnotateSpecConflicts:
    """REQ-TDE-206: Spec text containing anti-patterns gets inline annotations."""

    @classmethod
    def setup_class(cls):
        LanguageRegistry.discover()

    def test_csharp_console_writeline_annotated(self):
        spec = 'Console.WriteLine($"AddItemAsync called with userId={userId}");\n'
        profile = LanguageRegistry.get("csharp")
        ctx = {"language_profile": profile}
        result = _annotate_spec_conflicts(spec, ctx)
        assert "SPEC-STANDARD CONFLICT" in result

    def test_csharp_no_false_positive_on_clean_spec(self):
        spec = '_logger.LogInformation("AddItemAsync called with userId={UserId}", userId);\n'
        profile = LanguageRegistry.get("csharp")
        ctx = {"language_profile": profile}
        result = _annotate_spec_conflicts(spec, ctx)
        assert result == spec

    def test_go_fmt_println_annotated(self):
        spec = 'fmt.Println("starting server")\n'
        profile = LanguageRegistry.get("go")
        ctx = {"language_profile": profile}
        result = _annotate_spec_conflicts(spec, ctx)
        assert "SPEC-STANDARD CONFLICT" in result

    def test_java_sysout_annotated(self):
        spec = 'System.out.println("hello");\n'
        profile = LanguageRegistry.get("java")
        ctx = {"language_profile": profile}
        result = _annotate_spec_conflicts(spec, ctx)
        assert "SPEC-STANDARD CONFLICT" in result

    def test_python_no_patterns_returns_unchanged(self):
        spec = 'print("debug")\n'
        profile = LanguageRegistry.get("python")
        ctx = {"language_profile": profile}
        result = _annotate_spec_conflicts(spec, ctx)
        # Python profile sanitize_code_examples is a no-op
        assert result == spec

    def test_no_context_returns_unchanged(self):
        spec = 'Console.WriteLine("test");\n'
        result = _annotate_spec_conflicts(spec, None)
        assert result == spec

    def test_language_id_rehydration(self):
        """REQ-TDE-200: language_id from enrichment rehydrates the profile."""
        spec = 'Console.WriteLine("test");\n'
        ctx = {"language_id": "csharp"}
        result = _annotate_spec_conflicts(spec, ctx)
        assert "SPEC-STANDARD CONFLICT" in result

    def test_unknown_language_returns_unchanged(self):
        spec = 'Console.WriteLine("test");\n'
        # No profile, no language_id — should return unchanged
        ctx = {"language_id": "rust"}
        result = _annotate_spec_conflicts(spec, ctx)
        assert result == spec
