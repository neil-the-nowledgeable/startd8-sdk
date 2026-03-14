"""Tests for implementation_engine.spec_builder — spec prompt assembly."""

import pytest
from unittest.mock import Mock

from startd8.implementation_engine.spec_builder import (
    build_spec,
    build_spec_arch_section,
    build_spec_context_section,
    build_spec_conventions_section,
    build_spec_objectives_section,
    build_spec_plan_section,
    build_spec_prompt,
    format_context_value,
)


# ---------------------------------------------------------------------------
# format_context_value
# ---------------------------------------------------------------------------

class TestFormatContextValue:
    def test_list_to_bullets(self):
        result = format_context_value(["A", "B", "C"])
        assert "- A" in result
        assert "- B" in result
        assert "- C" in result

    def test_dict_to_bold_keys(self):
        result = format_context_value({"key1": "val1", "key2": "val2"})
        assert "**key1**" in result
        assert "val1" in result

    def test_string_passthrough(self):
        assert format_context_value("hello") == "hello"

    def test_int_to_string(self):
        assert format_context_value(42) == "42"


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

class TestBuildSpecContextSection:
    def test_basic_context(self):
        ctx = {"key": "value"}
        result = build_spec_context_section(ctx, None, None)
        assert "Context" in result
        assert "value" in result

    def test_output_format_appended(self):
        ctx = {}
        result = build_spec_context_section(ctx, "JSON output", None)
        assert "JSON output" in result

    def test_multi_file_manifest(self):
        ctx = {}
        files = ["a.py", "b.py"]
        result = build_spec_context_section(ctx, None, files)
        assert "a.py" in result
        assert "b.py" in result
        assert "MULTIPLE files" in result

    def test_single_file_no_manifest(self):
        ctx = {}
        result = build_spec_context_section(ctx, None, ["only.py"])
        assert "MULTIPLE" not in result


class TestBuildSpecPlanSection:
    def test_empty_returns_empty(self):
        assert build_spec_plan_section(None) == ""
        assert build_spec_plan_section("") == ""
        assert build_spec_plan_section("   ") == ""

    def test_plan_included(self):
        result = build_spec_plan_section("Build the thing")
        assert "Plan Context" in result
        assert "Build the thing" in result

    def test_edit_mode_framing(self):
        result = build_spec_plan_section("Changes to apply", is_edit=True)
        assert "Plan Context" in result

    def test_long_plan_truncated(self):
        long_plan = "x" * 50000
        result = build_spec_plan_section(long_plan)
        assert len(result) < 50000


class TestBuildSpecArchSection:
    def test_empty_returns_empty(self):
        assert build_spec_arch_section(None) == ""
        assert build_spec_arch_section("") == ""

    def test_string_arch(self):
        result = build_spec_arch_section("Use microservices")
        assert "Architecture" in result
        assert "microservices" in result

    def test_dict_arch(self):
        ctx = {"objectives": ["Obj 1"], "constraints": ["Con 1"]}
        result = build_spec_arch_section(ctx)
        assert "Architecture" in result

    def test_edit_mode_framing(self):
        result = build_spec_arch_section("Arch ctx", is_edit=True)
        assert "Architecture" in result


class TestBuildSpecObjectivesSection:
    def test_empty_returns_empty(self):
        assert build_spec_objectives_section(None) == ""
        assert build_spec_objectives_section("") == ""

    def test_with_objectives(self):
        result = build_spec_objectives_section(["Obj A", "Obj B"])
        assert "Objectives" in result
        assert "Obj A" in result


class TestBuildSpecConventionsSection:
    def test_empty_returns_empty(self):
        assert build_spec_conventions_section(None) == ""

    def test_with_conventions(self):
        result = build_spec_conventions_section({"naming": "snake_case"})
        assert "Conventions" in result
        assert "snake_case" in result


# ---------------------------------------------------------------------------
# build_spec_prompt
# ---------------------------------------------------------------------------

class TestBuildSpecPrompt:
    def test_basic_prompt(self):
        ctx = {}
        result = build_spec_prompt("Build a widget", ctx, None)
        assert "Build a widget" in result
        assert isinstance(result, str)

    def test_design_document_selects_template(self):
        ctx = {"design_document": "Design doc content"}
        result = build_spec_prompt("Task", ctx, None)
        assert "Design doc content" in result

    def test_explicit_template_key(self):
        ctx = {}
        result = build_spec_prompt("Task", ctx, None, template_key="spec")
        assert isinstance(result, str)

    def test_context_keys_popped(self):
        ctx = {
            "plan_context": "Plan",
            "architectural_context": "Arch",
            "project_objectives": ["Obj"],
            "semantic_conventions": {"c": "v"},
            "domain_constraints": ["Constraint 1"],
            "requirements_text": "Req text",
            "forward_contracts": "Contract text",
            "critical_parameters": ["Param 1"],
        }
        ctx_copy = dict(ctx)
        build_spec_prompt("Task", ctx_copy, None)
        # Structured keys should be popped
        assert "plan_context" not in ctx_copy
        assert "architectural_context" not in ctx_copy
        assert "project_objectives" not in ctx_copy
        assert "domain_constraints" not in ctx_copy

    def test_edit_mode_preamble(self):
        ctx = {"existing_files": {"f.py": "x = 1\n" * 100}}
        result = build_spec_prompt("Edit task", ctx, None)
        assert "EDIT MODE" in result or "edit" in result.lower()

    def test_requirements_text_forwarded(self):
        ctx = {"requirements_text": "Must support Python 3.9+"}
        result = build_spec_prompt("Task", ctx, None)
        assert "Python 3.9+" in result

    def test_forward_contracts_forwarded(self):
        ctx = {"forward_contracts": "API returns JSON"}
        result = build_spec_prompt("Task", ctx, None)
        assert "API returns JSON" in result

    def test_critical_parameters_list(self):
        ctx = {"critical_parameters": ["max_retries=3", "timeout=30"]}
        result = build_spec_prompt("Task", ctx, None)
        assert "max_retries=3" in result

    def test_critical_parameters_string(self):
        ctx = {"critical_parameters": "max_retries=3"}
        result = build_spec_prompt("Task", ctx, None)
        assert "max_retries=3" in result

    def test_domain_constraints_list(self):
        ctx = {"domain_constraints": ["No external deps", "Python only"]}
        result = build_spec_prompt("Task", ctx, None)
        assert "No external deps" in result

    def test_domain_constraints_string(self):
        ctx = {"domain_constraints": "Must be pure Python"}
        result = build_spec_prompt("Task", ctx, None)
        assert "pure Python" in result


# ---------------------------------------------------------------------------
# build_spec (integration with mock agent)
# ---------------------------------------------------------------------------

class TestBuildSpec:
    def _make_agent(self, response_text="## Requirements\n- R1\n## Acceptance Criteria\n- AC1\n"):
        agent = Mock()
        agent.model = "test-model"
        token_usage = Mock()
        token_usage.input = 200
        token_usage.output = 400
        agent.generate.return_value = (response_text, 1000, token_usage)
        return agent

    def test_basic_spec_creation(self):
        agent = self._make_agent()
        result = build_spec(agent, "Build widget", {})

        assert result.spec_id.startswith("spec-")
        assert result.task_summary == "Build widget"
        assert result.raw_spec != ""
        assert result.input_tokens == 200
        assert result.output_tokens == 400
        assert result.time_ms == 1000

    def test_requirements_parsed(self):
        agent = self._make_agent("## Requirements\n- Req A\n- Req B\n")
        result = build_spec(agent, "Task", {})
        assert result.requirements == ["Req A", "Req B"]

    def test_acceptance_criteria_parsed(self):
        agent = self._make_agent(
            "## Requirements\n- R1\n## Acceptance Criteria\n- AC1\n- AC2\n"
        )
        result = build_spec(agent, "Task", {})
        assert result.acceptance_criteria == ["AC1", "AC2"]

    def test_context_not_mutated(self):
        agent = self._make_agent()
        ctx = {"plan_context": "Plan", "extra_key": "value"}
        build_spec(agent, "Task", ctx)
        # Original context should NOT be mutated (build_spec copies it)
        assert "plan_context" in ctx

    def test_design_document_template(self):
        agent = self._make_agent()
        ctx = {"design_document": "Design content here"}
        build_spec(agent, "Task", ctx)

        call_args = agent.generate.call_args
        prompt = call_args[0][0]
        assert "Design content here" in prompt


# ---------------------------------------------------------------------------
# Spec edit mode — non-Python targets and target-only line count
# ---------------------------------------------------------------------------

class TestSpecEditModeNonPython:
    """Spec builder must skip quantitative constraints for non-Python targets."""

    def test_non_python_target_no_min_lines(self):
        """requirements.in target: no 'AT LEAST N lines' in spec preamble."""
        ctx = {
            "existing_files": {
                "src/server.py": "line\n" * 150,
                "src/requirements.in": "dep1==1.0\ndep2==2.0\n",
            },
            "target_files": ["src/requirements.in"],
        }
        result = build_spec_prompt("Update deps", ctx, None)
        assert "EDIT MODE" in result
        # Must NOT include quantitative line constraint
        assert "AT LEAST" not in result
        assert "220 lines" not in result

    def test_python_target_uses_target_line_count(self):
        """Python target: line count reflects target file only, not siblings."""
        ctx = {
            "existing_files": {
                "src/foo.py": "line\n" * 10,
                "src/bar.py": "line\n" * 200,
            },
            "target_files": ["src/foo.py"],
        }
        result = build_spec_prompt("Edit foo", ctx, None)
        assert "EDIT MODE" in result
        # Should reference 10 lines (target), not 210 (total)
        assert "10 lines" in result
        assert "210" not in result

    def test_python_target_still_gets_constraint(self):
        """Python target must still get the quantitative line constraint."""
        ctx = {
            "existing_files": {"src/main.py": "line\n" * 50},
            "target_files": ["src/main.py"],
        }
        result = build_spec_prompt("Refactor main", ctx, None)
        assert "50 lines" in result
        assert "AT LEAST" in result or "40 lines" in result
