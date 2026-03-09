"""Tests for L2: semantic validation checks in checkpoint (stubs, duplicates, import symbols)."""

import textwrap
from pathlib import Path

import pytest

from startd8.contractors.checkpoint import (
    CheckpointStatus,
    IntegrationCheckpoint,
)


@pytest.fixture
def checkpoint(tmp_path):
    return IntegrationCheckpoint(project_root=tmp_path, run_tests=False)


def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    """Write a Python file to tmp_path and return its path."""
    p = tmp_path / name
    p.write_text(textwrap.dedent(content))
    return p


# ---------------------------------------------------------------------------
# check_stubs
# ---------------------------------------------------------------------------

class TestCheckStubs:
    def test_stub_detection_pass_body(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                pass
        """)
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.WARNING
        assert "stubs" in result.warnings[0].lower() or "stub" in result.warnings[0].lower()

    def test_stub_detection_ellipsis(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                ...
        """)
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.WARNING

    def test_stub_detection_not_implemented(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                raise NotImplementedError
        """)
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.WARNING

    def test_stub_detection_not_implemented_call(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                raise NotImplementedError("todo")
        """)
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.WARNING

    def test_stub_with_docstring(self, tmp_path, checkpoint):
        """Docstring + pass should still count as stub."""
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                \"\"\"A docstring.\"\"\"
                pass
        """)
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.WARNING

    def test_stub_ratio_below_threshold(self, tmp_path, checkpoint):
        funcs = "\n".join(f"def f{i}():\n    return {i}\n" for i in range(10))
        funcs += "\ndef stub():\n    pass\n"
        f = _write_py(tmp_path, "a.py", funcs)
        result = checkpoint.check_stubs([f])
        # 1/11 = 9% < 30% threshold
        assert result.status == CheckpointStatus.PASSED

    def test_stub_ratio_above_threshold(self, tmp_path, checkpoint):
        funcs = "def real():\n    return 42\n\n"
        funcs += "\n".join(f"def stub{i}():\n    pass\n" for i in range(5))
        f = _write_py(tmp_path, "a.py", funcs)
        result = checkpoint.check_stubs([f])
        # 5/6 = 83% > 30% threshold
        assert result.status == CheckpointStatus.WARNING

    def test_real_implementation_not_flagged(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                return 42

            def bar():
                x = 1 + 2
                return x
        """)
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.PASSED

    def test_no_python_files(self, tmp_path, checkpoint):
        f = tmp_path / "readme.md"
        f.write_text("# Hello")
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.PASSED

    def test_custom_threshold(self, tmp_path, checkpoint):
        """Custom max_stub_ratio is respected."""
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                pass

            def bar():
                return 1
        """)
        # 1/2 = 50% — default 30% would warn
        result_default = checkpoint.check_stubs([f])
        assert result_default.status == CheckpointStatus.WARNING
        # But 60% threshold should pass
        result_lenient = checkpoint.check_stubs([f], max_stub_ratio=0.6)
        assert result_lenient.status == CheckpointStatus.PASSED


# ---------------------------------------------------------------------------
# check_duplicates
# ---------------------------------------------------------------------------

class TestCheckDuplicates:
    def test_duplicate_class_detected(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            class Foo:
                pass

            class Foo:
                x = 1
        """)
        result = checkpoint.check_duplicates([f])
        assert result.status == CheckpointStatus.WARNING
        assert "Foo" in result.warnings[0]

    def test_duplicate_function_detected(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            def bar():
                return 1

            def bar():
                return 2
        """)
        result = checkpoint.check_duplicates([f])
        assert result.status == CheckpointStatus.WARNING
        assert "bar" in result.warnings[0]

    def test_no_duplicates(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            class Foo:
                pass

            def bar():
                return 1
        """)
        result = checkpoint.check_duplicates([f])
        assert result.status == CheckpointStatus.PASSED

    def test_nested_same_name_not_flagged(self, tmp_path, checkpoint):
        """Same name at different scope levels is NOT a duplicate."""
        f = _write_py(tmp_path, "a.py", """\
            class Foo:
                def helper(self):
                    pass

            def helper():
                pass
        """)
        # "helper" at class method level vs top-level — only top-level counts
        # The class method is NOT a top-level def, so no duplicate
        result = checkpoint.check_duplicates([f])
        assert result.status == CheckpointStatus.PASSED

    def test_syntax_error_skipped(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "def broken(\n")
        result = checkpoint.check_duplicates([f])
        assert result.status == CheckpointStatus.PASSED


# ---------------------------------------------------------------------------
# check_import_symbols
# ---------------------------------------------------------------------------

class TestCheckImportSymbols:
    def test_valid_import_symbol(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "from os.path import join\n")
        result = checkpoint.check_import_symbols([f])
        assert result.status == CheckpointStatus.PASSED

    def test_invalid_import_symbol(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "from os.path import nonexistent_xyz\n")
        result = checkpoint.check_import_symbols([f])
        assert result.status == CheckpointStatus.WARNING
        assert "nonexistent_xyz" in result.warnings[0]

    def test_skips_local_modules(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "from demo_pb2 import SomeMessage\n")
        result = checkpoint.check_import_symbols(
            [f], known_local_modules={"demo_pb2"}
        )
        assert result.status == CheckpointStatus.PASSED

    def test_unimportable_module_skipped(self, tmp_path, checkpoint):
        """Modules that can't be imported at all are skipped (covered by check_imports)."""
        f = _write_py(tmp_path, "a.py", "from nonexistent_module_xyz import Foo\n")
        result = checkpoint.check_import_symbols([f])
        # Module itself not importable — should be PASSED (not our job to flag)
        assert result.status == CheckpointStatus.PASSED

    def test_star_import_skipped(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "from os.path import *\n")
        result = checkpoint.check_import_symbols([f])
        assert result.status == CheckpointStatus.PASSED


# ---------------------------------------------------------------------------
# Integration: semantic checks in run_all_checkpoints
# ---------------------------------------------------------------------------

class TestSemanticChecksInRunAll:
    def test_semantic_checks_called(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                return 42
        """)
        results = checkpoint.run_all_checkpoints([f], "test-feature")
        names = [r.name for r in results]
        assert "Stub Detection" in names
        assert "Duplicate Detection" in names

    def test_semantic_warnings_dont_block(self, tmp_path, checkpoint):
        """Semantic check warnings should not prevent overall pass."""
        # File with a stub — will warn but not fail
        f = _write_py(tmp_path, "a.py", """\
            def foo():
                pass
        """)
        results = checkpoint.run_all_checkpoints([f], "test-feature")
        stub_result = next(r for r in results if r.name == "Stub Detection")
        assert stub_result.status == CheckpointStatus.WARNING
        # WARNING is considered "passed" (not blocking)
        assert stub_result.passed
