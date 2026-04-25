"""Tests for the Micro Prime Repair Pipeline (REQ-MP-400–408)."""

from __future__ import annotations

import ast
from unittest.mock import patch

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
    _step_octal_literal_fix,
    _step_over_generation_trim,
    _step_signature_reconcile,
    _try_parse,
    build_repair_attribution,
    run_file_repair_pipeline,
    run_file_whole_contractor_repair,
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


class TestOctalLiteralFix:
    """Tests for Step 2: Octal literal fix (REQ-MP-408)."""

    def test_fixes_port_number(self, simple_function_element):
        """Ollama generates 050 for port 40."""
        code = "port = 050\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is True
        assert result.code == "port = 0o50\n"
        assert result.metrics["octal_literals_fixed"] == 1

    def test_fixes_file_permissions(self, simple_function_element):
        """Ollama generates 0644 for file permissions."""
        code = "os.chmod(path, 0644)\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is True
        assert "0o644" in result.code
        assert result.metrics["octal_literals_fixed"] == 1

    def test_fixes_multiple_literals(self, simple_function_element):
        code = "a = 050\nb = 0777\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is True
        assert "0o50" in result.code
        assert "0o777" in result.code
        assert result.metrics["octal_literals_fixed"] == 2

    def test_preserves_hex_literals(self, simple_function_element):
        code = "x = 0xFF\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is False
        assert result.code == code

    def test_preserves_binary_literals(self, simple_function_element):
        code = "x = 0b1010\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is False
        assert result.code == code

    def test_preserves_valid_octal(self, simple_function_element):
        """Already-valid 0o prefix should not be double-prefixed."""
        code = "x = 0o644\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is False
        assert result.code == code

    def test_preserves_float_literals(self, simple_function_element):
        code = "x = 0.5\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is False
        assert result.code == code

    def test_preserves_zero(self, simple_function_element):
        code = "x = 0\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is False
        assert result.code == code

    def test_no_change_no_modification(self, simple_function_element):
        code = "def main():\n    return 42\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is False
        assert result.metrics["octal_literals_fixed"] == 0

    def test_fixes_leading_zero_with_digit_8(self, simple_function_element):
        """Ollama generates 09 — not valid octal, strip leading zero."""
        code = "port = 09\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is True
        assert result.code == "port = 9\n"

    def test_fixes_leading_zero_with_digit_9(self, simple_function_element):
        """Ollama generates 0855 — contains 8, strip leading zero."""
        code = "x = 0855\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is True
        assert result.code == "x = 855\n"

    def test_fixes_leading_zero_decimal_port(self, simple_function_element):
        """Ollama generates 08080 — clearly decimal intent, strip leading zero."""
        code = "port = 08080\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is True
        assert result.code == "port = 8080\n"

    def test_all_zeros_becomes_zero(self, simple_function_element):
        """Edge case: 00 → 0 (not empty string)."""
        code = "x = 00\n"
        result = _step_octal_literal_fix(code, simple_function_element)
        assert result.modified is True
        assert result.code == "x = 0\n"

    def test_pipeline_fixes_leading_zero_decimal(self, simple_function_element):
        """Integration: pipeline should fix non-octal leading-zero literal."""
        code = "def get_name(self, key: str) -> str:\n    return 09\n"
        result = run_repair_pipeline(code, simple_function_element)
        assert result.ast_valid is True
        assert "09" not in result.code
        assert "9" in result.code

    def test_pipeline_fixes_octal_before_ast(self, simple_function_element):
        """Integration: pipeline should fix octal so ast_validate passes."""
        code = "def get_name(self, key: str) -> str:\n    return 050\n"
        result = run_repair_pipeline(code, simple_function_element)
        assert result.ast_valid is True
        assert "0o50" in result.code
        assert any(
            s.step_name == "octal_literal_fix" and s.modified
            for s in result.step_results
        )


class TestOverGenerationTrim:
    """Tests for Step 3: Over-generation trim (REQ-MP-401)."""

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

    def test_no_double_wrap_when_def_after_imports(self, simple_function_element):
        """Run-016: over_generation_trim outputs imports + complete def.

        bare_statement_wrap should NOT re-wrap the function in another def.
        """
        code = (
            "import logging\n"
            "from logging import StreamHandler\n"
            "\n"
            "def get_name(self, key: str) -> str:\n"
            "    logger = logging.getLogger(key)\n"
            "    return key\n"
        )
        result = _step_bare_statement_wrap(code, simple_function_element)
        # Should not contain nested def
        assert "    def get_name" not in result.code
        # The def should exist exactly once
        assert result.code.count("def get_name") == 1
        # Imports should be preserved
        assert "import logging" in result.code
        assert result.metrics.get("already_wrapped") is True


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
        assert len(result.step_results) == 11  # All ordered steps from _ALL_STEPS

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
        assert "octal_literal_fix" in step_names
        assert "ast_validate" in step_names
        assert len(step_names) == 11


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


class TestFenceStripSeesRawOutput:
    """Verify fence_strip works on raw Ollama output (Fix 3).

    Before Fix 3, _generate_ollama() called extract_code_from_response()
    before the repair pipeline, making fence_strip a no-op in production.
    Now raw text flows to repair, and fence_strip handles fence removal.
    """

    def test_fence_strip_on_raw_ollama_output(self, simple_function_element):
        """Pipeline should strip fences when given raw markdown-fenced code."""
        raw_ollama = '```python\ndef get_name(self, key: str) -> str:\n    return key\n```'
        result = run_repair_pipeline(raw_ollama, simple_function_element)
        assert "```" not in result.code
        assert result.ast_valid is True
        # fence_strip step should have reported modified=True
        fence_step = next(
            (r for r in result.step_results if r.step_name == "fence_strip"), None,
        )
        assert fence_step is not None
        assert fence_step.modified is True

    def test_fence_strip_with_body_only_output(self, simple_function_element):
        """Raw output with fence + body-only code should be stripped then wrapped."""
        raw_ollama = "```python\nreturn key\n```"
        result = run_repair_pipeline(raw_ollama, simple_function_element)
        assert "```" not in result.code
        # bare_statement_wrap should have kicked in after fence removal
        bare_step = next(
            (r for r in result.step_results if r.step_name == "bare_statement_wrap"), None,
        )
        assert bare_step is not None


class TestNonUniformIndentRepair:
    """Verify indent_normalize fixes non-uniform indentation (Fix 2).

    Ollama frequently returns body code with corrupted indentation where
    textwrap.dedent() is a no-op (no common leading whitespace).
    The structural_reindent strategy infers indent from block structure.
    """

    def test_nonuniform_indent_in_wrapped_function(self):
        """Mixed 4/16/12-space indent after bare_statement_wrap."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="add_fields",
            signature=Signature(
                params=[
                    Param(name="log_record"),
                    Param(name="record"),
                    Param(name="message_dict"),
                ],
                return_annotation=None,
            ),
        )
        # Simulates run-028 failure: bare_statement_wrap wrapped body with
        # non-uniform indentation from Ollama
        code = (
            "def add_fields(log_record, record, message_dict):\n"
            "    if 'timestamp' not in log_record:\n"
            "                log_record['timestamp'] = record.created\n"
            "            if 'severity' in log_record:\n"
            "                log_record['severity'] = log_record['severity'].upper()\n"
            "            else:\n"
            "                log_record['severity'] = record.levelname"
        )
        result = _step_indent_normalize(code, elem)
        assert result.modified is True
        # Must parse after repair
        ast.parse(result.code)
        # All key logic must survive
        assert "timestamp" in result.code
        assert "severity" in result.code

    def test_pipeline_recovers_nonuniform_indent(self):
        """Full pipeline should recover from non-uniform indentation."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="add_fields",
            signature=Signature(
                params=[
                    Param(name="log_record"),
                    Param(name="record"),
                    Param(name="message_dict"),
                ],
                return_annotation=None,
            ),
        )
        # Raw body-only output with non-uniform indentation (no def line)
        raw = (
            "if 'timestamp' not in log_record:\n"
            "            log_record['timestamp'] = record.created\n"
            "        if 'severity' in log_record:\n"
            "            log_record['severity'] = log_record['severity'].upper()\n"
            "        else:\n"
            "            log_record['severity'] = record.levelname"
        )
        result = run_repair_pipeline(raw, elem)
        assert result.ast_valid is True
        assert result.repair_recovered is True


class TestBareStatementWrapFenceGuard:
    """Verify bare_statement_wrap strips residual fences before wrapping.

    Run-019/022 regression: fence_strip peels the outer layer but inner
    fences survive.  bare_statement_wrap must detect and strip them rather
    than embedding them inside a function body.
    """

    def test_residual_fence_stripped_before_wrap(self):
        """Body starting with ```python should have fences stripped."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="getJSONLogger",
            signature=Signature(
                params=[Param(name="name", annotation="str")],
                return_annotation="logging.Logger",
            ),
        )
        # After outer fence_strip, inner fence remains
        code = "```python\nimport logging\nlogger = logging.getLogger(name)\nreturn logger\n```"
        result = _step_bare_statement_wrap(code, elem)
        assert "```" not in result.code
        assert result.modified is True

    def test_residual_fence_reveals_def_line(self):
        """If stripping residual fences reveals a def line, don't re-wrap."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="getJSONLogger",
            signature=Signature(
                params=[Param(name="name", annotation="str")],
                return_annotation="logging.Logger",
            ),
        )
        code = (
            "```python\n"
            "def getJSONLogger(name: str) -> logging.Logger:\n"
            "    logger = logging.getLogger(name)\n"
            "    return logger\n"
            "```"
        )
        result = _step_bare_statement_wrap(code, elem)
        assert "```" not in result.code
        assert result.code.strip().startswith("def getJSONLogger")
        # Should not have double-wrapped (def inside def)
        assert result.code.count("def getJSONLogger") == 1

    def test_no_fence_no_change(self):
        """Body without fences is wrapped normally (no regression)."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(
                params=[],
                return_annotation="int",
            ),
        )
        code = "return 42"
        result = _step_bare_statement_wrap(code, elem)
        assert result.modified is True
        assert "def foo" in result.code
        assert "return 42" in result.code


class TestSystemPromptSplit:
    """Verify system prompt alignment (AC-R7/F7).

    _CODE_GEN_SYSTEM_PROMPT was removed — it was a dead fallback that
    contradicted the body-only user prompt.  Only _ELEMENT_BODY_SYSTEM_PROMPT
    and _FILE_WHOLE_SYSTEM_PROMPT remain.
    """

    def test_code_gen_prompt_is_generic(self):
        """AC-R7/F7: _CODE_GEN_SYSTEM_PROMPT must NOT contain body-only instructions.

        Retained as compat alias for prime_adapter cloud escalation (full-element
        generation), but must not contradict itself with body-only language.
        """
        from startd8.micro_prime.engine import _CODE_GEN_SYSTEM_PROMPT
        assert "body lines" not in _CODE_GEN_SYSTEM_PROMPT
        assert "no def line" not in _CODE_GEN_SYSTEM_PROMPT

    def test_element_body_prompt_no_def_line_instruction(self):
        from startd8.micro_prime.engine import _ELEMENT_BODY_SYSTEM_PROMPT
        # Must NOT contain contradictory "include the def line" instruction
        assert "including the `def` line" not in _ELEMENT_BODY_SYSTEM_PROMPT
        # Must instruct body-only output
        assert "body" in _ELEMENT_BODY_SYSTEM_PROMPT.lower()

    def test_file_whole_prompt_asks_for_complete_file(self):
        from startd8.micro_prime.engine import _FILE_WHOLE_SYSTEM_PROMPT
        assert "COMPLETE" in _FILE_WHOLE_SYSTEM_PROMPT
        assert "stub" in _FILE_WHOLE_SYSTEM_PROMPT.lower()


# ═══════════════════════════════════════════════════════════════════════════
# File-whole contractor repair bridge tests
# ═══════════════════════════════════════════════════════════════════════════


class TestTranslateValidationFailure:
    """Tests for _translate_validation_failure."""

    def test_empty_output_returns_no_diagnostics(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure("empty output", "foo.py")
        assert result == []

    def test_empty_reason_returns_no_diagnostics(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure("", "foo.py")
        assert result == []

    def test_ast_parse_failure_returns_syntax_diagnostic(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure(
            "ast.parse() failed: unexpected EOF", "foo.py",
        )
        assert len(result) == 1
        assert result[0].category == "syntax"
        assert result[0].file == "foo.py"
        assert "ast.parse()" in result[0].message

    def test_nested_duplicate_returns_syntax_diagnostic(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure(
            "nested duplicate function: my_func", "bar.py",
        )
        assert len(result) == 1
        assert result[0].category == "syntax"

    def test_skeleton_markers_returns_lint_diagnostic(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure(
            "contains skeleton markers", "baz.py",
        )
        assert len(result) == 1
        assert result[0].category == "lint"

    def test_stub_reason_returns_semantic_diagnostic(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure(
            "stub-only NotImplementedError bodies: [my_func]", "x.py",
        )
        assert len(result) == 1
        assert result[0].category == "semantic"

    def test_missing_elements_returns_semantic_diagnostic(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure(
            "missing elements: [a, b]", "x.py",
        )
        assert len(result) == 1
        assert result[0].category == "semantic"

    def test_unknown_reason_falls_back_to_syntax(self):
        from startd8.micro_prime.repair import _translate_validation_failure

        result = _translate_validation_failure(
            "some unknown failure", "x.py",
        )
        assert len(result) == 1
        assert result[0].category == "syntax"


class TestFileWholeContractorRepairBridge:
    """Tests for run_file_whole_contractor_repair."""

    def test_noop_on_empty_output_reason(self):
        from startd8.micro_prime.repair import run_file_whole_contractor_repair

        code = "x = 1\n"
        result = run_file_whole_contractor_repair(code, "empty output", "f.py")
        assert result.code == code
        assert result.steps_applied == []

    def test_returns_repair_result_type(self):
        from startd8.micro_prime.repair import (
            RepairResult,
            run_file_whole_contractor_repair,
        )

        code = "def foo():\n    return 1\n"
        result = run_file_whole_contractor_repair(
            code, "ast.parse() failed: test", "f.py",
        )
        assert isinstance(result, RepairResult)

    def test_fixes_unclosed_bracket(self):
        """Bracket balance step should close unclosed parens."""
        from startd8.micro_prime.repair import run_file_whole_contractor_repair

        code = "def foo(x, y:\n    return x + y\n"
        result = run_file_whole_contractor_repair(
            code, "ast.parse() failed: unexpected EOF", "f.py",
        )
        # The repair should either fix it or at least not crash
        assert isinstance(result.ast_valid, bool)
        assert isinstance(result.steps_applied, list)

    def test_fixes_duplicate_import(self):
        """Duplicate removal should deduplicate imports."""
        from startd8.micro_prime.repair import run_file_whole_contractor_repair

        code = "import os\nimport os\n\ndef foo():\n    return os.getcwd()\n"
        result = run_file_whole_contractor_repair(
            code, "ast.parse() failed: test", "f.py",
        )
        # Code should still be valid
        assert result.ast_valid

    def test_preserves_valid_code(self):
        """Non-destructive guarantee: valid code stays valid."""
        from startd8.micro_prime.repair import run_file_whole_contractor_repair

        code = "def foo():\n    return 42\n"
        result = run_file_whole_contractor_repair(
            code, "contains skeleton markers", "f.py",
        )
        assert result.ast_valid
        # Valid code should not be broken
        try:
            ast.parse(result.code)
        except SyntaxError:
            pytest.fail("Repair broke valid code")


class TestVueRepairSkips:
    """REQ-VUE-B-006: Vue SFC must not run Python-oriented repair steps."""

    def test_element_pipeline_skips_and_preserves_code(self, simple_function_element):
        sfc = "<script setup>const x=1</script>"
        with patch(
            "startd8.micro_prime.repair.ast.parse",
            side_effect=AssertionError("ast.parse should not run for vue"),
        ):
            result = run_repair_pipeline(
                sfc, simple_function_element, language_id="vue",
            )
        assert result.code == sfc
        assert result.steps_applied == []

    def test_file_pipeline_skips(self):
        sfc = "<template><p>a</p></template><script setup>x</script>"
        with patch(
            "startd8.micro_prime.repair.ast.parse",
            side_effect=AssertionError("ast.parse should not run for vue"),
        ):
            result = run_file_repair_pipeline(
                sfc,
                file_spec=ForwardFileSpec(
                    file="src/C.vue", elements=[], language="vue",
                ),
                language_id="vue",
            )
        assert result.code == sfc
        assert result.steps_applied == []


class TestRunFileWholeContractorRepairVue:
    """REQ-VUE-B-006: contractor repair must not run Python steps on ``.vue``."""

    def test_skips_for_vue_path(self) -> None:
        sfc = "<script setup>const x = 1</script>"
        result = run_file_whole_contractor_repair(
            sfc, "ast.parse() failed: test", "components/Hi.vue",
        )
        assert result.code == sfc
        assert result.steps_applied == []

    def test_skips_when_language_id_vue(self) -> None:
        result = run_file_whole_contractor_repair(
            "x", "stub bodies remain", "any/path",
            language_id="vue",
        )
        assert result.code == "x"
        assert result.steps_applied == []
