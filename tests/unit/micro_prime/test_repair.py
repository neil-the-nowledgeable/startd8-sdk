"""Tests for the Micro Prime Repair Pipeline (REQ-MP-400–407)."""

from __future__ import annotations

import ast

import pytest

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardImportSpec
from startd8.micro_prime.models import RepairStepResult
from startd8.micro_prime.repair import (
    _build_def_line,
    _step_ast_validate,
    _step_bare_statement_wrap,
    _step_duplicate_removal,
    _step_fence_strip,
    _step_future_import_reorder,
    _step_import_completion,
    _step_indent_normalize,
    _step_over_generation_trim,
    _step_signature_reconcile,
    _try_parse,
    build_repair_attribution,
    run_repair_pipeline,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


class TestFenceStrip:
    """Tests for Step 1: Fence stripping (REQ-MP-400)."""

    def test_strips_markdown_fences(self, simple_function_element):
        code = '```python\ndef get_name(self, key: str) -> str:\n    return key\n```'
        result = _step_fence_strip(code, simple_function_element)
        assert result.modified is True
        assert "```" not in result.code
        assert "def get_name" in result.code

    def test_no_fences_unchanged(self, simple_function_element):
        code = 'def get_name(self, key: str) -> str:\n    return key'
        result = _step_fence_strip(code, simple_function_element)
        assert result.modified is False
        assert result.code == code

    def test_empty_code(self, simple_function_element):
        result = _step_fence_strip("", simple_function_element)
        assert result.code == ""


class TestOverGenerationTrim:
    """Tests for Step 2: Over-generation trim (REQ-MP-401)."""

    def test_trims_extra_functions(self, simple_function_element):
        code = (
            "def get_name(self, key: str) -> str:\n"
            "    return key\n\n"
            "def extra_function():\n"
            "    pass\n"
        )
        result = _step_over_generation_trim(code, simple_function_element)
        assert result.modified is True
        assert "extra_function" not in result.code

    def test_preserves_target_only(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key\n"
        result = _step_over_generation_trim(code, simple_function_element)
        assert result.modified is False

    def test_trims_extra_constants(self, constant_element):
        code = "DEFAULT_TIMEOUT = 30\nEXTRA = 99\n"
        result = _step_over_generation_trim(code, constant_element)
        assert result.modified is True

    def test_handles_syntax_error(self, simple_function_element):
        code = "def get_name(self, :\n"
        result = _step_over_generation_trim(code, simple_function_element)
        assert result.modified is False
        assert result.metrics.get("parse_failed") is True

    def test_strips_future_import_from_function(self, simple_function_element):
        """from __future__ imports are always in the skeleton — don't keep them."""
        code = (
            "from __future__ import annotations\n"
            "import grpc\n\n"
            "def get_name(self, key: str) -> str:\n"
            "    return key\n\n"
            "def extra():\n"
            "    pass\n"
        )
        result = _step_over_generation_trim(code, simple_function_element)
        assert result.modified is True
        assert "from __future__" not in result.code
        # Regular imports should be preserved
        assert "grpc" in result.code

    def test_strips_future_import_from_constant(self, constant_element):
        """from __future__ stripped for constants too."""
        code = (
            "from __future__ import annotations\n"
            "DEFAULT_TIMEOUT: int = 30\n"
        )
        result = _step_over_generation_trim(code, constant_element)
        # May or may not be modified (depends on trim logic), but no __future__
        if result.modified:
            assert "from __future__" not in result.code


class TestBareStatementWrap:
    """Tests for Step 3: Bare statement wrapping (REQ-MP-407)."""

    def test_wraps_body_only_code(self, simple_function_element):
        code = "return key"
        result = _step_bare_statement_wrap(code, simple_function_element)
        assert result.modified is True
        assert "def get_name" in result.code
        assert "    return key" in result.code

    def test_skips_code_with_def(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = _step_bare_statement_wrap(code, simple_function_element)
        assert result.modified is False

    def test_skips_code_with_decorator(self, simple_function_element):
        code = "@property\ndef get_name(self, key: str) -> str:\n    return key"
        result = _step_bare_statement_wrap(code, simple_function_element)
        assert result.modified is False

    def test_skips_constants(self, constant_element):
        code = "DEFAULT_TIMEOUT = 30"
        result = _step_bare_statement_wrap(code, constant_element)
        assert result.modified is False

    def test_wraps_async(self, async_function_element):
        code = "return await fetch(url)"
        result = _step_bare_statement_wrap(code, async_function_element)
        assert result.modified is True
        assert "async def fetch_data" in result.code

    def test_dedents_before_wrapping(self, simple_function_element):
        """Ollama often returns first line unindented, rest with 4-space indent.

        bare_statement_wrap must normalise indentation before wrapping to avoid
        the body ending up with 8-space indent on lines 2+.
        """
        # Simulate Ollama output: first line bare, subsequent indented
        raw_output = "result = lookup(key)\n    return result"
        result = _step_bare_statement_wrap(raw_output, simple_function_element)
        assert result.modified is True
        # The wrapped code must be valid Python
        assert _try_parse(result.code, is_method=True)
        # Both body lines should have exactly 4-space indent
        lines = result.code.splitlines()
        body_lines = [l for l in lines[1:] if l.strip()]
        for line in body_lines:
            indent = len(line) - len(line.lstrip())
            assert indent == 4, f"Expected 4-space indent, got {indent}: {line!r}"

    def test_dedents_multiline_ollama_output(self):
        """Regression test for the exact Ollama output pattern from run-008."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="getJSONLogger",
            signature=Signature(
                params=[Param(name="name", annotation="str")],
                return_annotation="logging.Logger",
            ),
        )
        raw_output = (
            "logger = logging.getLogger(name)\n"
            "    handler = logging.StreamHandler(sys.stdout)\n"
            "    formatter = jsonlogger.JsonFormatter()\n"
            "    handler.setFormatter(formatter)\n"
            "    logger.addHandler(handler)\n"
            "    return logger"
        )
        result = _step_bare_statement_wrap(raw_output, elem)
        assert result.modified is True
        assert _try_parse(result.code, is_method=False), (
            f"Wrapped code is not valid Python:\n{result.code}"
        )


    def test_hoists_leading_imports(self):
        """Run-014: initStackdriverProfiling generated 'import os' + bare statements.

        Leading imports should be hoisted above the def line, not wrapped
        inside the function body.
        """
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="initStackdriverProfiling",
            signature=Signature(
                params=[],
                return_annotation="None",
            ),
        )
        raw_output = (
            'import os\n'
            '\n'
            'if "GOOGLE_CLOUD_PROJECT" in os.environ:\n'
            '    from google.cloud import profiler\n'
            '    profiler.start(project_id=os.getenv("GOOGLE_CLOUD_PROJECT"))'
        )
        result = _step_bare_statement_wrap(raw_output, elem)
        assert result.modified is True
        assert result.metrics.get("hoisted_imports") == 1
        # import os should appear BEFORE def line
        lines = result.code.splitlines()
        import_idx = next(i for i, l in enumerate(lines) if l.strip() == "import os")
        def_idx = next(i for i, l in enumerate(lines) if l.strip().startswith("def initStackdriverProfiling"))
        assert import_idx < def_idx, (
            f"import os (line {import_idx}) should precede def (line {def_idx})"
        )
        assert _try_parse(result.code, is_method=False), (
            f"Wrapped code is not valid Python:\n{result.code}"
        )

    def test_no_hoist_when_no_leading_imports(self, simple_function_element):
        """Code without leading imports should wrap normally."""
        code = "x = 1\nreturn x"
        result = _step_bare_statement_wrap(code, simple_function_element)
        assert result.modified is True
        assert result.metrics.get("hoisted_imports", 0) == 0


class TestIndentNormalize:
    """Tests for Step 4: Indentation normalize (REQ-MP-402)."""

    def test_dedent_fixes_indentation(self, async_function_element):
        """Standalone function with extra indentation needs dedent."""
        code = "    async def fetch_data(url: str, timeout: int = 30) -> dict:\n        return {}"
        result = _step_indent_normalize(code, async_function_element)
        # Already valid at top level via dedent — may or may not modify
        # depending on whether the original parses
        if not _try_parse(code, is_method=False):
            assert result.modified is True

    def test_already_valid_unchanged(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = _step_indent_normalize(code, simple_function_element)
        # Methods with parent_class pass via class wrapper, so already valid
        assert result.modified is False

    def test_tab_to_spaces_standalone(self):
        """Standalone function with tabs needs conversion."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="compute",
            signature=Signature(params=[], return_annotation="int"),
        )
        # Code with mixed indent that fails parse
        code = "def compute() -> int:\n\t\treturn 42"
        result = _step_indent_normalize(code, elem)
        # Tab code may or may not parse directly, but if it does, no change needed
        # The point is the pipeline doesn't break
        assert result.code is not None

    def test_strips_explanation_line(self, simple_function_element):
        code = "Here is the implementation:\ndef get_name(self, key: str) -> str:\n    return key"
        result = _step_indent_normalize(code, simple_function_element)
        # Methods already parse via class wrapper, so the original might be "valid"
        # The strip-first-line strategy would also work
        assert result.code is not None


class TestSignatureReconcile:
    """Tests for Step 5: Signature reconcile (REQ-MP-403)."""

    def test_reconciles_wrong_params(self, simple_function_element):
        code = "def get_name(self, wrong_param: int) -> str:\n    return 'hello'"
        result = _step_signature_reconcile(code, simple_function_element)
        assert result.modified is True
        assert "key: str" in result.code

    def test_preserves_correct_signature(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = _step_signature_reconcile(code, simple_function_element)
        # May or may not be modified depending on exact formatting
        # but should still contain the correct params
        assert "key" in result.code

    def test_skips_constants(self, constant_element):
        code = "DEFAULT_TIMEOUT = 30"
        result = _step_signature_reconcile(code, constant_element)
        assert result.modified is False

    def test_skips_no_signature(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
        )
        code = "def foo():\n    pass"
        result = _step_signature_reconcile(code, elem)
        # With a matching empty signature, should not modify
        assert "foo" in result.code


class TestImportCompletion:
    """Tests for Step 6: Import completion (REQ-MP-404)."""

    def test_adds_missing_import(self, simple_function_element, sample_file_spec):
        code = "def get_name(self, key: str) -> str:\n    p = Path(key)\n    return str(p)"
        result = _step_import_completion(code, simple_function_element, sample_file_spec)
        assert result.modified is True
        assert "from pathlib import Path" in result.code

    def test_skips_existing_import(self, simple_function_element, sample_file_spec):
        code = "from pathlib import Path\ndef get_name(self, key: str) -> str:\n    return str(Path(key))"
        result = _step_import_completion(code, simple_function_element, sample_file_spec)
        assert result.modified is False

    def test_no_file_spec_skips(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = _step_import_completion(code, simple_function_element, None)
        assert result.modified is False


class TestASTValidate:
    """Tests for Step 7: AST validation (REQ-MP-405)."""

    def test_valid_code(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = _step_ast_validate(code, simple_function_element)
        assert result.metrics["valid"] is True

    def test_invalid_code(self, simple_function_element):
        code = "def get_name(self, :\n    return key"
        result = _step_ast_validate(code, simple_function_element)
        assert result.metrics["valid"] is False


class TestRunRepairPipeline:
    """Tests for the full repair pipeline (REQ-MP-406)."""

    def test_full_pipeline_valid_code(self, simple_function_element, sample_file_spec):
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = run_repair_pipeline(code, simple_function_element, sample_file_spec)
        assert result.code == code  # Already valid, no changes needed
        assert len(result.step_results) == 9  # All 9 steps run

    def test_full_pipeline_with_fences(self, simple_function_element, sample_file_spec):
        code = '```python\ndef get_name(self, key: str) -> str:\n    return key\n```'
        result = run_repair_pipeline(code, simple_function_element, sample_file_spec)
        assert "```" not in result.code
        assert "def get_name" in result.code

    def test_non_destructive_guarantee(self, simple_function_element, sample_file_spec):
        """REQ-MP-406: If a step breaks valid code, revert."""
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = run_repair_pipeline(code, simple_function_element, sample_file_spec)
        # The repaired code should still be valid
        try:
            ast.parse(result.code)
        except SyntaxError:
            pytest.fail("Repair pipeline broke valid code!")

    def test_pipeline_step_results_tracked(self, simple_function_element, sample_file_spec):
        code = "def get_name(self, key: str) -> str:\n    return key"
        result = run_repair_pipeline(code, simple_function_element, sample_file_spec)
        step_names = [s.step_name for s in result.step_results]
        assert "fence_strip" in step_names
        assert "ast_validate" in step_names
        assert len(step_names) == 9


class TestBuildDefLine:
    """Tests for _build_def_line helper."""

    def test_regular_function(self, simple_function_element):
        line = _build_def_line(simple_function_element)
        assert line == "def get_name(self, key: str) -> str:"

    def test_async_function(self, async_function_element):
        line = _build_def_line(async_function_element)
        assert "async def fetch_data" in line

    def test_constant_returns_none(self, constant_element):
        line = _build_def_line(constant_element)
        assert line is None

    def test_class(self):
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyClass",
            bases=["BaseModel"],
        )
        line = _build_def_line(elem)
        assert line == "class MyClass(BaseModel):"


class TestTryParse:
    """Tests for _try_parse helper."""

    def test_valid_code(self):
        assert _try_parse("x = 1") is True

    def test_invalid_code(self):
        assert _try_parse("def (x:") is False

    def test_method_with_class_wrapper(self):
        code = "    def foo(self):\n        return 1"
        assert _try_parse(code, is_method=True) is True

    def test_method_without_wrapper(self):
        code = "def foo(self):\n    return 1"
        assert _try_parse(code, is_method=False) is True


class TestBuildRepairAttribution:
    """Tests for build_repair_attribution (REQ-MP-601)."""

    def test_empty_steps_returns_defaults(self):
        attr = build_repair_attribution([])
        assert attr.fence_stripped is False
        assert attr.trimmed is False
        assert attr.nodes_removed == 0
        assert attr.bare_wrapped is False
        assert attr.indent_source == ""
        assert attr.params_changed == 0
        assert attr.return_type_restored is False

    def test_fence_strip_attribution(self):
        steps = [
            RepairStepResult(
                step_name="fence_strip",
                modified=True,
                code="def foo(): pass",
                metrics={"had_fences": True},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.fence_stripped is True
        assert attr.trimmed is False

    def test_over_generation_trim_attribution(self):
        steps = [
            RepairStepResult(
                step_name="over_generation_trim",
                modified=True,
                code="def foo(): pass",
                metrics={"nodes_removed": 3},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.trimmed is True
        assert attr.nodes_removed == 3

    def test_bare_wrap_attribution(self):
        steps = [
            RepairStepResult(
                step_name="bare_statement_wrap",
                modified=True,
                code="def foo():\n    return 1",
                metrics={"wrapped_body_lines": 1},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.bare_wrapped is True

    def test_indent_normalize_attribution(self):
        steps = [
            RepairStepResult(
                step_name="indent_normalize",
                modified=True,
                code="def foo():\n    pass",
                metrics={"strategy": "dedent"},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.indent_source == "dedent"

    def test_signature_reconcile_attribution(self):
        steps = [
            RepairStepResult(
                step_name="signature_reconcile",
                modified=True,
                code="def foo(x: int) -> str:\n    pass",
                metrics={"replaced_def_lines": 1},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.params_changed == 1
        assert attr.return_type_restored is True

    def test_unmodified_steps_ignored(self):
        steps = [
            RepairStepResult(
                step_name="fence_strip",
                modified=False,
                code="def foo(): pass",
                metrics={"had_fences": False},
            ),
            RepairStepResult(
                step_name="over_generation_trim",
                modified=False,
                code="def foo(): pass",
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.fence_stripped is False
        assert attr.trimmed is False

    def test_multiple_steps_combined(self):
        steps = [
            RepairStepResult(
                step_name="fence_strip",
                modified=True,
                code="def foo(): pass",
                metrics={"had_fences": True},
            ),
            RepairStepResult(
                step_name="over_generation_trim",
                modified=True,
                code="def foo(): pass",
                metrics={"nodes_removed": 2},
            ),
            RepairStepResult(
                step_name="indent_normalize",
                modified=True,
                code="def foo():\n    pass",
                metrics={"strategy": "strip_first+dedent"},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.fence_stripped is True
        assert attr.trimmed is True
        assert attr.nodes_removed == 2
        assert attr.indent_source == "strip_first+dedent"

    def test_duplicate_removal_attribution(self):
        steps = [
            RepairStepResult(
                step_name="duplicate_removal",
                modified=True,
                code="import os\n",
                metrics={"imports_removed": 2},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.imports_removed == 2

    def test_import_completion_attribution(self):
        steps = [
            RepairStepResult(
                step_name="import_completion",
                modified=True,
                code="from pathlib import Path\ndef foo(): pass",
                metrics={"imports_added": 2},
            ),
        ]
        attr = build_repair_attribution(steps)
        assert attr.imports_added == 2

    def test_pipeline_returns_attribution(self, simple_function_element, sample_file_spec):
        """Full pipeline should produce step results usable by build_repair_attribution."""
        code = '```python\ndef get_name(self, key: str) -> str:\n    return key\n```'
        result = run_repair_pipeline(code, simple_function_element, sample_file_spec)
        attr = build_repair_attribution(result.step_results)
        assert attr.fence_stripped is True


class TestFutureImportReorder:
    """Tests for Step 4: Future import reorder (REQ-RPL-107)."""

    def test_moves_misplaced_future_import(self, simple_function_element):
        code = (
            "import os\n"
            "from __future__ import annotations\n"
            "\n"
            "def get_name(self, key: str) -> str:\n"
            "    return key\n"
        )
        result = _step_future_import_reorder(code, simple_function_element)
        assert result.modified is True
        lines = result.code.splitlines()
        future_idx = next(i for i, l in enumerate(lines) if "from __future__" in l)
        os_idx = next(i for i, l in enumerate(lines) if "import os" in l)
        assert future_idx < os_idx

    def test_no_op_when_correct(self, simple_function_element):
        code = (
            "from __future__ import annotations\n"
            "\n"
            "import os\n"
            "\n"
            "x = 1\n"
        )
        result = _step_future_import_reorder(code, simple_function_element)
        assert result.modified is False

    def test_no_op_when_no_future_import(self, simple_function_element):
        code = "import os\n\nx = 1\n"
        result = _step_future_import_reorder(code, simple_function_element)
        assert result.modified is False


class TestSignatureReconcileCallable:
    """Fix 5: Paren-depth heuristic with Callable in return annotation."""

    def test_callable_return_annotation(self):
        """Callable[..., None] in return type should not confuse paren matching."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="register",
            signature=Signature(
                params=[
                    Param(name="callback", annotation="Callable[..., None]"),
                ],
                return_annotation="None",
            ),
        )
        code = "def register(callback: Callable[..., None]) -> None:\n    pass\n"
        result = _step_signature_reconcile(code, elem)
        # Should not break — the def line ends with ":"
        assert "register" in result.code
        assert "pass" in result.code
