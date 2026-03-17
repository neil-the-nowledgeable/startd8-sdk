"""REQ-MLT-102: Python-stub cross-language guard tests.

Validates that ``_detect_python_stub_in_non_python`` correctly blocks Python
stubs from being written into non-Python target files while allowing
legitimate content through.
"""

from __future__ import annotations

import pytest

from startd8.contractors.integration_engine import _detect_python_stub_in_non_python


# ---------------------------------------------------------------------------
# Allow-through cases
# ---------------------------------------------------------------------------


class TestPythonStubGuardAllows:
    """Cases where the guard should return None (allow the write)."""

    def test_python_stub_guard_allows_python_files(self) -> None:
        """A .py target with __future__ import is perfectly fine."""
        content = "from __future__ import annotations\n\nclass Foo:\n    pass\n"
        assert _detect_python_stub_in_non_python(content, "src/foo.py") is None

    def test_python_stub_guard_allows_valid_go_content(self) -> None:
        """Legitimate Go code should pass through."""
        content = "package main\n\nfunc main() {\n\tfmt.Println(\"hello\")\n}\n"
        assert _detect_python_stub_in_non_python(content, "cmd/main.go") is None

    def test_python_stub_guard_allows_valid_html_content(self) -> None:
        """Legitimate HTML should pass through."""
        content = "<html>\n<head><title>Test</title></head>\n<body></body>\n</html>\n"
        assert _detect_python_stub_in_non_python(content, "templates/index.html") is None

    def test_python_stub_guard_allows_go_mod(self) -> None:
        """go.mod file with module declaration should pass through."""
        content = "module example.com\n\ngo 1.22\n"
        assert _detect_python_stub_in_non_python(content, "go.mod") is None


# ---------------------------------------------------------------------------
# Block cases
# ---------------------------------------------------------------------------


class TestPythonStubGuardBlocks:
    """Cases where the guard should return an error string (block the write)."""

    def test_python_stub_guard_blocks_future_import_in_go(self) -> None:
        """A .go file with only __future__ import is a Python stub."""
        content = "from __future__ import annotations\n"
        result = _detect_python_stub_in_non_python(content, "pkg/server.go")
        assert result is not None
        assert "future" in result.lower() or "stub" in result.lower()

    def test_python_stub_guard_blocks_future_import_in_html(self) -> None:
        """An .html file with __future__ import is a Python stub."""
        content = "from __future__ import annotations\n"
        result = _detect_python_stub_in_non_python(content, "templates/index.html")
        assert result is not None
        assert "future" in result.lower() or "stub" in result.lower()

    def test_python_stub_guard_blocks_skeleton_stub_in_go(self) -> None:
        """A .go file with __future__ + raise NotImplementedError is a skeleton."""
        content = (
            "from __future__ import annotations\n"
            "\n"
            "raise NotImplementedError\n"
        )
        result = _detect_python_stub_in_non_python(content, "pkg/handler.go")
        assert result is not None
        assert "stub" in result.lower() or "skeleton" in result.lower()

    def test_python_stub_guard_blocks_future_import_with_real_code_in_go(self) -> None:
        """A .go file that has __future__ import mixed with other Python code."""
        content = (
            "from __future__ import annotations\n"
            "\n"
            "def main():\n"
            "    print('hello')\n"
        )
        result = _detect_python_stub_in_non_python(content, "cmd/main.go")
        assert result is not None
        assert "future" in result.lower()
