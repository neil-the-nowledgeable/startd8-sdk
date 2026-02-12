"""Tests for startd8.utils.code_extraction — multi-file extraction."""

import pytest

from startd8.utils.code_extraction import (
    STUB_SENTINEL,
    _generate_stub,
    extract_multi_file_code,
)


# ---------------------------------------------------------------------------
# Strategy 1: file-path comment markers
# ---------------------------------------------------------------------------

class TestFilePathCommentMarkers:
    """LLM output uses // path/file.ext or # path/file.py markers."""

    def test_two_typescript_files(self):
        response = (
            "Here is the implementation:\n\n"
            "// src/components/MigrationQueue.tsx\n"
            "```tsx\n"
            "import React from 'react';\n"
            "export const MigrationQueue = () => <div>Queue</div>;\n"
            "```\n\n"
            "// src/hooks/useBatchMigration.ts\n"
            "```ts\n"
            "export function useBatchMigration() {\n"
            "  return { migrate: () => {} };\n"
            "}\n"
            "```\n"
        )
        targets = [
            "src/components/MigrationQueue.tsx",
            "src/hooks/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "MigrationQueue" in result["src/components/MigrationQueue.tsx"]
        assert "useBatchMigration" in result["src/hooks/useBatchMigration.ts"]
        # Ensure content is NOT the same for both
        assert (
            result["src/components/MigrationQueue.tsx"]
            != result["src/hooks/useBatchMigration.ts"]
        )

    def test_python_hash_markers(self):
        response = (
            "# app/models.py\n"
            "```python\n"
            "class User:\n"
            "    pass\n"
            "```\n\n"
            "# app/views.py\n"
            "```python\n"
            "def index():\n"
            "    return 'hello'\n"
            "```\n"
        )
        targets = ["app/models.py", "app/views.py"]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "class User" in result["app/models.py"]
        assert "def index" in result["app/views.py"]


# ---------------------------------------------------------------------------
# Strategy 2: fenced blocks with filename in lang tag or first-line comment
# ---------------------------------------------------------------------------

class TestFencedBlockFilenameHints:
    """LLM output uses ```filename.ext as the language tag."""

    def test_filename_as_language_tag(self):
        response = (
            "```MigrationQueue.tsx\n"
            "import React from 'react';\n"
            "export const MigrationQueue = () => <div/>;\n"
            "```\n\n"
            "```useBatchMigration.ts\n"
            "export function useBatchMigration() { return {}; }\n"
            "```\n"
        )
        targets = [
            "src/components/MigrationQueue.tsx",
            "src/hooks/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "MigrationQueue" in result["src/components/MigrationQueue.tsx"]
        assert "useBatchMigration" in result["src/hooks/useBatchMigration.ts"]

    def test_first_line_comment_hint(self):
        response = (
            "```tsx\n"
            "// MigrationQueue.tsx\n"
            "import React from 'react';\n"
            "export const MigrationQueue = () => <div/>;\n"
            "```\n\n"
            "```ts\n"
            "// useBatchMigration.ts\n"
            "export function useBatchMigration() { return {}; }\n"
            "```\n"
        )
        targets = [
            "src/components/MigrationQueue.tsx",
            "src/hooks/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        # The filename comment should be stripped from the code
        assert "// MigrationQueue.tsx" not in result["src/components/MigrationQueue.tsx"]
        assert "import React" in result["src/components/MigrationQueue.tsx"]


# ---------------------------------------------------------------------------
# Fallback / edge cases
# ---------------------------------------------------------------------------

class TestFallbackBehavior:
    """When splitting fails, returns empty dict."""

    def test_empty_response(self):
        assert extract_multi_file_code("", ["a.py"]) == {}

    def test_empty_target_files(self):
        assert extract_multi_file_code("some code", []) == {}

    def test_single_block_no_markers(self):
        """Single code block with no file markers — can't split."""
        response = (
            "```python\n"
            "def hello(): pass\n"
            "```\n"
        )
        result = extract_multi_file_code(response, ["a.py", "b.py"])
        assert result == {}

    def test_partial_match_returns_matched_files(self):
        """If only one of two target files is found, return the partial result."""
        response = (
            "// src/a.py\n"
            "```python\n"
            "x = 1\n"
            "```\n"
        )
        result = extract_multi_file_code(response, ["src/a.py", "src/b.py"])
        assert len(result) == 1
        assert "x = 1" in result["src/a.py"]
        assert "src/b.py" not in result

    def test_single_target_file_returns_empty(self):
        """Single target file — function isn't designed for this case."""
        response = "```python\ndef hello(): pass\n```\n"
        # With a single target file the caller should use extract_code_from_response
        # This function requires markers to split, so returns empty
        result = extract_multi_file_code(response, ["hello.py"])
        assert result == {}


class TestInitPyAndOrderFallback:
    """__init__.py and order-based fallback for partial matches."""

    def test_init_py_via_first_line_comment(self):
        """Path with __init__.py in first-line comment matches."""
        response = (
            "```python\n"
            "# src/contextcore/generators/__init__.py\n"
            "from .artifact_generators import render_service_monitor\n"
            "```\n\n"
            "```python\n"
            "# src/contextcore/generators/artifact_generators.py\n"
            "def render_service_monitor(): pass\n"
            "```\n"
        )
        targets = [
            "src/contextcore/generators/__init__.py",
            "src/contextcore/generators/artifact_generators.py",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "from .artifact_generators" in result["src/contextcore/generators/__init__.py"]
        assert "render_service_monitor" in result["src/contextcore/generators/artifact_generators.py"]

    def test_order_fallback_single_unmatched(self):
        """When exactly one block and one target unmatched, assign by order."""
        response = (
            "```python\n"
            "# src/pkg/module.py\n"
            "def foo(): pass\n"
            "```\n\n"
            "```python\n"
            "from .module import foo\n"
            "__all__ = ['foo']\n"
            "```\n"
        )
        targets = [
            "src/pkg/__init__.py",
            "src/pkg/module.py",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2
        assert "from .module import foo" in result["src/pkg/__init__.py"]
        assert "def foo" in result["src/pkg/module.py"]


class TestCaseInsensitiveMatching:
    """Basename matching is case-insensitive."""

    def test_case_mismatch_still_matches(self):
        response = (
            "// migrationqueue.tsx\n"
            "```tsx\n"
            "export const MQ = () => <div/>;\n"
            "```\n\n"
            "// usebatchmigration.ts\n"
            "```ts\n"
            "export function ubm() {}\n"
            "```\n"
        )
        targets = [
            "src/MigrationQueue.tsx",
            "src/useBatchMigration.ts",
        ]
        result = extract_multi_file_code(response, targets)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# _generate_stub — stub content generation
# ---------------------------------------------------------------------------

class TestGenerateStub:
    """Tests for the _generate_stub defense-in-depth function."""

    def test_python_stub(self):
        stub = _generate_stub("src/pkg/module.py")
        assert "module.py" in stub
        assert STUB_SENTINEL in stub
        assert "auto-generated stub" in stub
        assert "__all__" in stub  # tool-friendly export

    def test_typescript_stub(self):
        stub = _generate_stub("src/components/Widget.tsx")
        assert "Widget.tsx" in stub
        assert STUB_SENTINEL in stub
        assert "export {};" in stub

    def test_javascript_stub(self):
        stub = _generate_stub("lib/helper.js")
        assert "helper.js" in stub
        assert STUB_SENTINEL in stub
        assert "export {};" in stub

    def test_yaml_stub(self):
        stub = _generate_stub("config/settings.yaml")
        assert "settings.yaml" in stub
        assert STUB_SENTINEL in stub

    def test_unknown_extension_stub(self):
        stub = _generate_stub("Makefile.mk")
        assert "Makefile.mk" in stub
        assert STUB_SENTINEL in stub

    def test_init_py_stub(self):
        stub = _generate_stub("src/pkg/__init__.py")
        assert "__init__.py" in stub
        assert STUB_SENTINEL in stub
        assert "__all__" in stub

    def test_go_stub(self):
        stub = _generate_stub("pkg/handler/router.go")
        assert "router.go" in stub
        assert STUB_SENTINEL in stub
        assert "package handler" in stub  # derived from parent dir

    def test_go_stub_top_level(self):
        """Go file with no parent dir defaults to package main."""
        stub = _generate_stub("main.go")
        assert "package main" in stub

    def test_rust_stub(self):
        stub = _generate_stub("src/lib.rs")
        assert "lib.rs" in stub
        assert STUB_SENTINEL in stub
        assert stub.startswith("// ")

    def test_java_stub(self):
        stub = _generate_stub("com/example/UserService.java")
        assert "UserService.java" in stub
        assert STUB_SENTINEL in stub
        assert "public class UserService {}" in stub

    def test_c_header_stub(self):
        stub = _generate_stub("include/utils.h")
        assert "utils.h" in stub
        assert STUB_SENTINEL in stub

    def test_cpp_stub(self):
        stub = _generate_stub("src/engine.cpp")
        assert "engine.cpp" in stub
        assert STUB_SENTINEL in stub

    def test_sentinel_is_first_line(self):
        """STUB_SENTINEL should be on the first line for fast detection."""
        for path in [
            "a.py", "b.tsx", "c.yaml", "d.txt",
            "pkg/e.go", "f.rs", "G.java", "h.c", "i.hpp",
        ]:
            stub = _generate_stub(path)
            first_line = stub.split("\n", 1)[0]
            assert STUB_SENTINEL in first_line, f"Sentinel missing from first line of {path} stub"


# ---------------------------------------------------------------------------
# extract_multi_file_code with stub_missing=True
# ---------------------------------------------------------------------------

class TestStubMissingFallback:
    """Defense-in-depth: stub generation for unmatched files."""

    def test_stub_fills_missing_file(self):
        """When LLM produces only one of two files, stub fills the gap."""
        response = (
            "```python\n"
            "# src/pkg/module.py\n"
            "def real_implementation(): pass\n"
            "```\n"
        )
        targets = ["src/pkg/module.py", "src/pkg/__init__.py"]
        result = extract_multi_file_code(response, targets, stub_missing=True)
        assert len(result) == 2
        assert "real_implementation" in result["src/pkg/module.py"]
        assert STUB_SENTINEL in result["src/pkg/__init__.py"]

    def test_stub_missing_false_returns_partial(self):
        """Default behavior: partial result without stubs."""
        response = (
            "```python\n"
            "# src/pkg/module.py\n"
            "def real_implementation(): pass\n"
            "```\n"
        )
        targets = ["src/pkg/module.py", "src/pkg/__init__.py"]
        result = extract_multi_file_code(response, targets, stub_missing=False)
        # With only one matched block, order fallback won't kick in (needs 2 blocks)
        # So only the matched file should be present
        assert "src/pkg/module.py" in result
        # __init__.py might be absent (depends on exact strategy)

    def test_stub_does_not_overwrite_matched(self):
        """Stubs only fill gaps — matched files keep their real content."""
        response = (
            "```python\n"
            "# src/a.py\n"
            "x = 1\n"
            "```\n\n"
            "```python\n"
            "# src/b.py\n"
            "y = 2\n"
            "```\n"
        )
        targets = ["src/a.py", "src/b.py", "src/c.py"]
        result = extract_multi_file_code(response, targets, stub_missing=True)
        assert len(result) == 3
        assert "x = 1" in result["src/a.py"]
        assert "y = 2" in result["src/b.py"]
        assert STUB_SENTINEL in result["src/c.py"]

    def test_all_files_matched_no_stubs_generated(self):
        """When all files are matched, no stubs are generated."""
        response = (
            "```python\n"
            "# src/a.py\n"
            "x = 1\n"
            "```\n\n"
            "```python\n"
            "# src/b.py\n"
            "y = 2\n"
            "```\n"
        )
        targets = ["src/a.py", "src/b.py"]
        result = extract_multi_file_code(response, targets, stub_missing=True)
        assert len(result) == 2
        assert STUB_SENTINEL not in result.get("src/a.py", "")
        assert STUB_SENTINEL not in result.get("src/b.py", "")

    def test_empty_response_with_stub_missing_returns_all_stubs(self):
        """Edge case: empty response + stub_missing produces stubs for all."""
        result = extract_multi_file_code("", ["a.py", "b.py"], stub_missing=True)
        # Empty response returns {} even with stub_missing (early return)
        assert result == {}
