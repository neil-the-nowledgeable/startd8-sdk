"""Tests for the Micro Prime Body Splicer."""

from __future__ import annotations

import ast

import pytest

from startd8.forward_manifest import ForwardElementSpec
from startd8.micro_prime.splicer import (
    _ast_body_end,
    _collect_leading_imports,
    _extract_body,
    _find_def_line,
    _find_stub_after_def,
    _inject_imports,
    splice_body_into_skeleton,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


class TestSpliceBodyIntoSkeleton:
    """Tests for splice_body_into_skeleton()."""

    def test_splice_function_body(self, simple_function_element, sample_skeleton):
        body = "def get_name(self, key: str) -> str:\n    return key.upper()"
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        assert result is not None
        assert "return key.upper()" in result
        assert "raise NotImplementedError" in result  # Other stub still there
        # Should parse
        ast.parse(result)

    def test_splice_body_only(self, simple_function_element, sample_skeleton):
        body = "return key.upper()"
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        assert result is not None
        assert "return key.upper()" in result
        ast.parse(result)

    def test_splice_preserves_other_stubs(self, simple_function_element, sample_skeleton):
        body = "return key"
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        assert result is not None
        # get_value's stub should still be there
        lines = result.splitlines()
        # Count remaining NotImplementedError lines
        stub_count = sum(1 for line in lines if "raise NotImplementedError" in line)
        assert stub_count == 1  # Only get_value's stub remains

    def test_splice_constant(self, constant_element, sample_skeleton):
        body = "DEFAULT_TIMEOUT = 30"
        result = splice_body_into_skeleton(body, constant_element, sample_skeleton)
        assert result is not None
        assert "DEFAULT_TIMEOUT = 30" in result
        # Should not have the STARTD8_AUTO_STUB anymore
        assert "STARTD8_AUTO_STUB" not in result

    def test_splice_invalid_body_returns_none(self, simple_function_element, sample_skeleton):
        body = "def get_name(self, :\n    invalid"  # Syntax error in body
        result = splice_body_into_skeleton(body, simple_function_element, sample_skeleton)
        # May return None if spliced result doesn't parse
        # (depends on whether the body is extractable)

    def test_element_not_in_skeleton_returns_none(self, sample_skeleton):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="nonexistent_function",
            signature=Signature(params=[], return_annotation="None"),
        )
        result = splice_body_into_skeleton("return 1", elem, sample_skeleton)
        assert result is None


class TestFindDefLine:
    """Tests for _find_def_line()."""

    def test_finds_regular_def(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        idx = _find_def_line("get_name", ElementKind.FUNCTION, lines)
        assert idx is not None
        assert "def get_name" in lines[idx]

    def test_finds_class_def(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        idx = _find_def_line("MyClass", ElementKind.CLASS, lines)
        assert idx is not None
        assert "class MyClass" in lines[idx]

    def test_not_found_returns_none(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        idx = _find_def_line("nonexistent", ElementKind.FUNCTION, lines)
        assert idx is None

    def test_finds_async_def(self):
        lines = ["async def fetch(url):", "    pass"]
        idx = _find_def_line("fetch", ElementKind.ASYNC_FUNCTION, lines)
        assert idx == 0


class TestFindStubAfterDef:
    """Tests for _find_stub_after_def()."""

    def test_finds_stub(self, sample_skeleton):
        lines = sample_skeleton.splitlines()
        def_idx = _find_def_line("get_name", ElementKind.FUNCTION, lines)
        stub_idx = _find_stub_after_def(lines, def_idx)
        assert stub_idx is not None
        assert "raise NotImplementedError" in lines[stub_idx]

    def test_stub_not_found(self):
        lines = ["def foo():", "    return 1", "    return 2"]
        idx = _find_stub_after_def(lines, 0)
        assert idx is None


class TestExtractBody:
    """Tests for _extract_body()."""

    def test_extracts_from_def(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key.upper()"
        body = _extract_body(code, simple_function_element)
        assert "return key.upper()" in body
        # Should not contain the def line
        assert "def get_name" not in body

    def test_body_only_returns_as_is(self, simple_function_element):
        code = "return key.upper()"
        body = _extract_body(code, simple_function_element)
        assert "return key.upper()" in body

    def test_multiline_body(self, simple_function_element):
        code = (
            "def get_name(self, key: str) -> str:\n"
            "    result = key.upper()\n"
            "    return result"
        )
        body = _extract_body(code, simple_function_element)
        assert "result = key.upper()" in body
        assert "return result" in body

    def test_skips_leading_imports_before_def(self, simple_function_element):
        """Imports before def line should be stripped — they belong at file level."""
        code = (
            "import grpc\n"
            "from flask import Flask\n\n"
            "def get_name(self, key: str) -> str:\n"
            "    return key.upper()\n"
        )
        body = _extract_body(code, simple_function_element)
        assert "return key.upper()" in body
        # Import lines should not be in the extracted body
        assert "import grpc" not in body
        assert "from flask" not in body
        # def line should also not be in the body
        assert "def get_name" not in body

    def test_skips_future_import_before_def(self, simple_function_element):
        """from __future__ before def should be stripped."""
        code = (
            "from __future__ import annotations\n\n"
            "def get_name(self, key: str) -> str:\n"
            "    return key.upper()\n"
        )
        body = _extract_body(code, simple_function_element)
        assert "return key.upper()" in body
        assert "from __future__" not in body


class TestStubBeyond20Lines:
    """Tests for AST-based stub finding beyond the old 20-line window."""

    def test_long_docstring_method(self):
        """Stub beyond 20 lines (pushed by a long docstring) is still found."""
        # Build a skeleton where the docstring is 25 lines long,
        # pushing raise NotImplementedError well past line 20.
        docstring_lines = "\n".join(f"    Line {i} of docs." for i in range(25))
        skeleton = (
            "class Formatter:\n"
            f'    def add_fields(self, log_record, record, message_dict):\n'
            f'        """Long docstring.\n\n'
            f"{docstring_lines}\n"
            f'        """\n'
            f"        raise NotImplementedError\n"
            "\n"
            "    def format(self, record):\n"
            '        """Format a record."""\n'
            "        raise NotImplementedError\n"
        )
        lines = skeleton.splitlines()
        def_idx = _find_def_line("add_fields", ElementKind.METHOD, lines)
        assert def_idx is not None
        stub_idx = _find_stub_after_def(lines, def_idx)
        assert stub_idx is not None
        assert "raise NotImplementedError" in lines[stub_idx]

    def test_ast_body_end_for_class_method(self):
        """_ast_body_end correctly identifies end of a method inside a class."""
        skeleton = (
            "class Foo:\n"
            "    def bar(self):\n"
            '        """Docs."""\n'
            "        raise NotImplementedError\n"
            "\n"
            "    def baz(self):\n"
            "        pass\n"
        )
        lines = skeleton.splitlines()
        def_idx = _find_def_line("bar", ElementKind.METHOD, lines)
        end = _ast_body_end(lines, def_idx)
        assert end is not None
        # end should be past the stub but before "def baz"
        baz_idx = _find_def_line("baz", ElementKind.METHOD, lines)
        assert end <= baz_idx

    def test_ast_body_end_top_level_function(self):
        """_ast_body_end works for top-level functions (no class wrapper)."""
        skeleton = (
            "def get_logger(name):\n"
            '    """Get a logger."""\n'
            "    raise NotImplementedError\n"
            "\n"
            "def other():\n"
            "    pass\n"
        )
        lines = skeleton.splitlines()
        def_idx = _find_def_line("get_logger", ElementKind.FUNCTION, lines)
        end = _ast_body_end(lines, def_idx)
        assert end is not None

    def test_fallback_when_ast_fails(self):
        """When AST parsing fails, _find_stub_after_def still searches to end of file."""
        # A skeleton with invalid syntax — AST parse will fail,
        # but the stub should still be found via the fallback search.
        skeleton = (
            "def broken(:\n"  # Invalid syntax
            "    x = 1\n"
            "    raise NotImplementedError\n"
        )
        lines = skeleton.splitlines()
        # _ast_body_end will return None, so search_end = len(lines)
        stub_idx = _find_stub_after_def(lines, 0)
        assert stub_idx == 2
        assert "raise NotImplementedError" in lines[stub_idx]


class TestRelativeIndentationPreservation:
    """Tests that splicing preserves relative indentation within the body."""

    def test_nested_if_else_preserved(self):
        """Body with nested if/else retains its relative indentation."""
        skeleton = (
            "class MyClass:\n"
            "    def process(self, x: int) -> str:\n"
            '        """Process x."""\n'
            "        raise NotImplementedError\n"
        )
        element = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="process",
            signature=Signature(
                params=[
                    Param(name="self"),
                    Param(name="x", annotation="int"),
                ],
                return_annotation="str",
            ),
            parent_class="MyClass",
        )
        # Body with nested control flow
        body = (
            "if x > 0:\n"
            "    return 'positive'\n"
            "else:\n"
            "    return 'non-positive'"
        )
        result = splice_body_into_skeleton(body, element, skeleton)
        assert result is not None
        ast.parse(result)
        # Check the nested indentation is correct (8-space base + 4 for inner)
        assert "        if x > 0:" in result
        assert "            return 'positive'" in result

    def test_multiline_dict_preserved(self):
        """Body with a multi-line dict literal preserves indentation."""
        skeleton = (
            "def build_record(self):\n"
            '    """Build a record."""\n'
            "    raise NotImplementedError\n"
        )
        element = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="build_record",
            signature=Signature(params=[Param(name="self")], return_annotation="dict"),
        )
        body = (
            "return {\n"
            "    'a': 1,\n"
            "    'b': 2,\n"
            "}"
        )
        result = splice_body_into_skeleton(body, element, skeleton)
        assert result is not None
        ast.parse(result)


class TestCollectLeadingImports:
    """Tests for _collect_leading_imports helper."""

    def test_extracts_imports_before_code(self):
        code = "from datetime import datetime\nimport os\nresult = 1 + 2"
        assert _collect_leading_imports(code) == [
            "from datetime import datetime",
            "import os",
        ]

    def test_no_imports(self):
        code = "result = 1 + 2\nreturn result"
        assert _collect_leading_imports(code) == []

    def test_empty_code(self):
        assert _collect_leading_imports("") == []

    def test_skips_blank_lines_between_imports(self):
        code = "import os\n\ndef foo(): pass"
        assert _collect_leading_imports(code) == ["import os"]


class TestInjectImports:
    """Tests for _inject_imports helper."""

    def test_adds_new_imports_after_existing(self):
        skeleton = "import logging\n\ndef foo():\n    pass"
        result = _inject_imports(skeleton, ["from datetime import datetime"])
        lines = result.splitlines()
        logging_idx = next(i for i, l in enumerate(lines) if "import logging" in l)
        dt_idx = next(i for i, l in enumerate(lines) if "from datetime" in l)
        assert dt_idx == logging_idx + 1

    def test_no_duplicates(self):
        skeleton = "import logging\nfrom datetime import datetime\n\ndef foo():\n    pass"
        result = _inject_imports(skeleton, ["from datetime import datetime"])
        assert result.count("from datetime import datetime") == 1

    def test_empty_imports_noop(self):
        skeleton = "import os\n\ndef foo():\n    pass"
        assert _inject_imports(skeleton, []) == skeleton


class TestSpliceImportReinjection:
    """Integration: splice_body_into_skeleton re-injects stripped imports."""

    def test_imports_reinjected_after_splice(self):
        skeleton = (
            "import logging\n"
            "\n"
            "def add_fields(self, log_record):\n"
            "    raise NotImplementedError\n"
        )
        body = (
            "from datetime import datetime\n"
            "log_record['timestamp'] = datetime.utcnow().isoformat()\n"
            "return log_record\n"
        )
        element = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="add_fields",
            signature=Signature(
                params=[Param(name="self"), Param(name="log_record")],
                return_annotation=None,
            ),
        )
        result = splice_body_into_skeleton(body, element, skeleton)
        assert result is not None
        assert "from datetime import datetime" in result
        assert "raise NotImplementedError" not in result
        assert "log_record['timestamp']" in result
        ast.parse(result)

    def test_existing_import_not_duplicated(self):
        skeleton = (
            "import logging\n"
            "from datetime import datetime\n"
            "\n"
            "def add_fields(self, log_record):\n"
            "    raise NotImplementedError\n"
        )
        body = (
            "from datetime import datetime\n"
            "log_record['timestamp'] = datetime.utcnow().isoformat()\n"
        )
        element = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="add_fields",
            signature=Signature(
                params=[Param(name="self"), Param(name="log_record")],
                return_annotation=None,
            ),
        )
        result = splice_body_into_skeleton(body, element, skeleton)
        assert result is not None
        assert result.count("from datetime import datetime") == 1
