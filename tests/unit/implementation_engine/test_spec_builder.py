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


# ---------------------------------------------------------------------------
# Phase 2 REQ-PE-200–302: Multi-language prompt parameterization
# ---------------------------------------------------------------------------

class _MockLanguageProfile:
    """Minimal mock for language profile in spec builder tests."""

    def __init__(self, language_id="go", source_extensions=None,
                 system_prompt_role="an expert Go engineer",
                 coding_standards="Idiomatic Go."):
        self.language_id = language_id
        self.source_extensions = source_extensions or [".go"]
        self.system_prompt_role = system_prompt_role
        self.coding_standards = coding_standards

    def get_import_syntax_guidance(self):
        return (
            "Use ONLY the packages listed above plus Go stdlib. "
            "Every import must appear in an import block at the top of the file."
        )

    def strip_dependency_version(self, dep):
        return dep.split(" ")[0] if " " in dep else dep


class TestMultiLanguageSpecBuilder:
    """REQ-PE-200–302: Spec builder language parameterization."""

    def test_reference_impl_fence_uses_go(self):
        """REQ-PE-200: Go reference implementation fenced as ```go."""
        from startd8.implementation_engine.spec_builder import build_spec_prompt
        ctx = {
            "reference_implementation": "func main() { fmt.Println(\"hello\") }",
            "language_profile": _MockLanguageProfile(language_id="go"),
            "target_files": ["main.go"],
        }
        result = build_spec_prompt("Implement main", ctx, None)
        assert "```go" in result
        assert "```python" not in result

    def test_reference_impl_fence_uses_java(self):
        """REQ-PE-200: Java reference implementation fenced as ```java."""
        from startd8.implementation_engine.spec_builder import build_spec_prompt
        ctx = {
            "reference_implementation": "public class Main {}",
            "language_profile": _MockLanguageProfile(language_id="java"),
            "target_files": ["Main.java"],
        }
        result = build_spec_prompt("Implement Main", ctx, None)
        assert "```java" in result

    def test_reference_impl_fence_no_profile(self):
        """REQ-PE-200: No profile → unlabeled fence (not ```python)."""
        from startd8.implementation_engine.spec_builder import build_spec_prompt
        ctx = {
            "reference_implementation": "some code here",
            "target_files": ["unknown.txt"],
        }
        result = build_spec_prompt("Implement something", ctx, None)
        # Should not have ```python when no profile
        assert "```python" not in result

    def test_available_imports_go_syntax(self):
        """REQ-PE-300: Go import syntax replaces 'Python stdlib' text."""
        from startd8.implementation_engine.spec_builder import _build_available_imports_section
        ctx = {
            "runtime_dependencies": ["github.com/sirupsen/logrus v1.9.4"],
            "language_profile": _MockLanguageProfile(language_id="go"),
        }
        result = _build_available_imports_section(ctx)
        assert "Go stdlib" in result or "import block" in result
        assert "Python stdlib" not in result

    def test_anti_pattern_skipped_for_go(self):
        """REQ-PE-202: Go tasks should not get Python os.getenv examples."""
        from startd8.implementation_engine.spec_builder import _build_anti_pattern_section
        ctx = {"language_profile": _MockLanguageProfile(language_id="go")}
        result = _build_anti_pattern_section(ctx, "configure environment variables")
        assert result == ""

    def test_anti_pattern_still_works_for_python(self):
        """REQ-PE-202: Python tasks should still get anti-pattern section."""
        from startd8.implementation_engine.spec_builder import _build_anti_pattern_section
        ctx = {"language_profile": _MockLanguageProfile(language_id="python")}
        result = _build_anti_pattern_section(ctx, "configure os.getenv variables")
        assert "os.getenv" in result

    def test_import_conventions_skipped_for_go(self):
        """REQ-PE-401: Go tasks should not get Python import convention guidance."""
        from startd8.implementation_engine.spec_builder import _build_import_conventions_section
        ctx = {
            "existing_files_content": {"src/main.py": "import os\n"},
            "target_files": ["src/main.go"],
            "language_profile": _MockLanguageProfile(language_id="go"),
        }
        result = _build_import_conventions_section(ctx)
        assert result == ""

    def test_sibling_imports_fence_uses_language(self):
        """REQ-PE-201: Sibling imports section uses target language fence."""
        from startd8.implementation_engine.spec_builder import _build_sibling_imports_section

        class GoProfile(_MockLanguageProfile):
            def extract_import_lines(self, source):
                lines = []
                for line in source.splitlines():
                    if line.strip().startswith('"') and line.strip().endswith('"'):
                        lines.append(f'import {line.strip()}')
                return lines

        ctx = {
            "existing_files_content": {
                "src/service/server.go": 'package main\n\nimport (\n\t"fmt"\n\t"net"\n)\n',
            },
            "target_files": ["src/service/handler.go"],
            "language_profile": GoProfile(),
        }
        result = _build_sibling_imports_section(ctx)
        if result:  # May be empty if extract_import_lines doesn't match
            assert "```go" in result
            assert "```python" not in result


class TestDrafterStubMarker:
    """REQ-PE-301: Skeleton fill stub marker parameterization."""

    def test_skeleton_fill_go_stub_marker(self):
        """Go skeleton fill should reference panic, not raise NotImplementedError."""
        from startd8.implementation_engine.drafter import get_drafter_system_prompt
        from startd8.languages.go import GoLanguageProfile
        prompt, mode = get_drafter_system_prompt(
            skeleton_fill=True,
            language_role="an expert Go engineer",
            coding_standards="Idiomatic Go.",
            language_profile=GoLanguageProfile(),
        )
        assert mode == "skeleton_fill"
        assert "panic" in prompt
        assert "NotImplementedError" not in prompt

    def test_skeleton_fill_java_stub_marker(self):
        """Java skeleton fill should reference UnsupportedOperationException."""
        from startd8.implementation_engine.drafter import get_drafter_system_prompt
        from startd8.languages.java import JavaLanguageProfile
        prompt, _ = get_drafter_system_prompt(
            skeleton_fill=True,
            language_role="an expert Java engineer",
            coding_standards="Standard Java conventions.",
            language_profile=JavaLanguageProfile(),
        )
        assert "UnsupportedOperationException" in prompt

    def test_skeleton_fill_python_default(self):
        """Python skeleton fill should still use raise NotImplementedError."""
        from startd8.implementation_engine.drafter import get_drafter_system_prompt
        from startd8.languages.python import PythonLanguageProfile
        prompt, _ = get_drafter_system_prompt(
            skeleton_fill=True,
            language_role="an expert Python engineer",
            coding_standards="PEP 8.",
            language_profile=PythonLanguageProfile(),
        )
        assert "NotImplementedError" in prompt

    def test_skeleton_fill_no_profile_defaults_to_python(self):
        """Without language_profile, stub marker defaults to Python."""
        from startd8.implementation_engine.drafter import get_drafter_system_prompt
        prompt, _ = get_drafter_system_prompt(
            skeleton_fill=True,
            language_role="an expert Go engineer",
            coding_standards="Idiomatic Go.",
        )
        # No language_profile → falls back to Python default
        assert "NotImplementedError" in prompt


# ---------------------------------------------------------------------------
# Phase 3 REQ-PE-501, PE-600, PE-601
# ---------------------------------------------------------------------------

class TestExtractImportLines:
    """REQ-PE-400: Language profile extract_import_lines implementations."""

    def test_go_extract_single_import(self):
        from startd8.languages.go import GoLanguageProfile
        profile = GoLanguageProfile()
        source = 'package main\n\nimport "fmt"\n\nfunc main() {}\n'
        result = profile.extract_import_lines(source)
        assert any("fmt" in line for line in result)

    def test_go_extract_block_import(self):
        from startd8.languages.go import GoLanguageProfile
        profile = GoLanguageProfile()
        source = 'package main\n\nimport (\n\t"fmt"\n\t"net/http"\n)\n'
        result = profile.extract_import_lines(source)
        assert len(result) >= 2
        assert any("fmt" in line for line in result)
        assert any("net/http" in line for line in result)

    def test_java_extract_imports(self):
        from startd8.languages.java import JavaLanguageProfile
        profile = JavaLanguageProfile()
        source = (
            "package hipstershop;\n\n"
            "import io.grpc.Server;\n"
            "import io.grpc.ServerBuilder;\n"
            "import static org.junit.Assert.assertEquals;\n\n"
            "public class AdService {}\n"
        )
        result = profile.extract_import_lines(source)
        assert len(result) == 3
        assert any("io.grpc.Server" in line for line in result)
        assert any("static" in line for line in result)

    def test_nodejs_extract_esm(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        profile = NodeLanguageProfile()
        source = (
            'import express from "express";\n'
            'import { Router } from "express";\n'
            "const app = express();\n"
        )
        result = profile.extract_import_lines(source)
        assert len(result) == 2

    def test_nodejs_extract_commonjs(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        profile = NodeLanguageProfile()
        source = (
            'const express = require("express");\n'
            'const { join } = require("path");\n'
            "app.listen(3000);\n"
        )
        result = profile.extract_import_lines(source)
        assert len(result) == 2

    def test_python_extract_via_ast(self):
        from startd8.languages.python import PythonLanguageProfile
        profile = PythonLanguageProfile()
        source = "import os\nfrom pathlib import Path\n\nx = 1\n"
        result = profile.extract_import_lines(source)
        assert len(result) == 2
        assert any("os" in line for line in result)
        assert any("Path" in line for line in result)

    def test_csharp_extract_using(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        profile = CSharpLanguageProfile()
        source = "using System;\nusing System.Collections.Generic;\n\nnamespace X {}\n"
        result = profile.extract_import_lines(source)
        assert len(result) == 2


class TestStubMarkerText:
    """REQ-PE-301: stub_marker_text property on language profiles."""

    def test_python_stub_marker(self):
        from startd8.languages.python import PythonLanguageProfile
        assert "NotImplementedError" in PythonLanguageProfile().stub_marker_text

    def test_go_stub_marker(self):
        from startd8.languages.go import GoLanguageProfile
        assert "panic" in GoLanguageProfile().stub_marker_text

    def test_java_stub_marker(self):
        from startd8.languages.java import JavaLanguageProfile
        assert "UnsupportedOperationException" in JavaLanguageProfile().stub_marker_text

    def test_nodejs_stub_marker(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        assert "Error" in NodeLanguageProfile().stub_marker_text

    def test_csharp_stub_marker(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        assert "NotImplementedException" in CSharpLanguageProfile().stub_marker_text

    def test_drafter_uses_profile_stub_marker(self):
        """Drafter should use profile.stub_marker_text when available."""
        from startd8.implementation_engine.drafter import get_drafter_system_prompt
        from startd8.languages.go import GoLanguageProfile
        profile = GoLanguageProfile()
        prompt, _ = get_drafter_system_prompt(
            skeleton_fill=True,
            language_role="an expert Go engineer",
            coding_standards="Idiomatic Go.",
            language_profile=profile,
        )
        assert "panic" in prompt
        assert "NotImplementedError" not in prompt


class TestConfigDataFileDetection:
    """REQ-PE-501: Source code files get quality gates, config/data files skip."""

    def test_go_source_is_not_config(self):
        """Go source files must NOT be in the skip list."""
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("main.go") is False

    def test_java_source_is_not_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("AdService.java") is False

    def test_typescript_source_is_not_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("index.ts") is False

    def test_javascript_source_is_not_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("app.js") is False

    def test_python_source_is_not_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("main.py") is False

    def test_yaml_is_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("config.yaml") is True

    def test_dockerfile_is_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("Dockerfile") is True

    def test_gradle_is_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("build.gradle") is True

    def test_go_mod_is_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("go.mod") is True

    def test_properties_is_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("gradle-wrapper.properties") is True

    def test_json_is_config(self):
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("package.json") is True

    def test_size_regression_applies_to_go(self):
        """Go source files should get size regression checks."""
        from startd8.implementation_engine.drafter import _all_files_config_or_data
        assert _all_files_config_or_data(target_files=["main.go"]) is False

    def test_size_regression_skipped_for_yaml(self):
        """YAML files should skip size regression checks."""
        from startd8.implementation_engine.drafter import _all_files_config_or_data
        assert _all_files_config_or_data(target_files=["config.yaml"]) is True

    def test_mixed_source_and_config(self):
        """Mixed targets: if any file is source, quality gates apply."""
        from startd8.implementation_engine.drafter import _all_files_config_or_data
        assert _all_files_config_or_data(target_files=["main.go", "Dockerfile"]) is False


class TestExtractCodeLanguagePreference:
    """REQ-PE-600: extract_code_from_response prefers matching language blocks."""

    def test_prefers_java_block_over_python(self):
        from startd8.utils.code_extraction import extract_code_from_response
        response = (
            "Here's the implementation:\n\n"
            "```python\n"
            "# This is a helper script\nimport os\nprint('hello')\n"
            "```\n\n"
            "And the Java file:\n\n"
            "```java\n"
            "package hipstershop;\n\n"
            "public class AdService {\n"
            "    public static void main(String[] args) {\n"
            "        System.out.println(\"hello\");\n"
            "    }\n"
            "}\n"
            "```\n"
        )
        result = extract_code_from_response(response, language="java")
        assert "package hipstershop" in result
        assert "import os" not in result

    def test_prefers_go_block(self):
        from startd8.utils.code_extraction import extract_code_from_response
        response = (
            "```python\nprint('explanation')\n```\n\n"
            "```go\npackage main\n\nfunc main() {}\n```\n"
        )
        result = extract_code_from_response(response, language="go")
        assert "package main" in result

    def test_falls_back_to_largest_when_no_match(self):
        from startd8.utils.code_extraction import extract_code_from_response
        response = (
            "```python\nshort\n```\n\n"
            "```python\nthis is a much longer block of code\nwith multiple lines\nand more content\n```\n"
        )
        result = extract_code_from_response(response, language="java")
        assert "much longer" in result

    def test_no_language_hint_uses_largest(self):
        from startd8.utils.code_extraction import extract_code_from_response
        response = (
            "```\nsmall\n```\n\n"
            "```\nthis is the larger block\nwith more lines\n```\n"
        )
        result = extract_code_from_response(response, language=None)
        assert "larger block" in result
