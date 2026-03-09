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
# check_known_bad_imports (L2+ — replaces check_import_symbols)
# ---------------------------------------------------------------------------

class TestCheckKnownBadImports:
    def test_known_bad_jsonlogger(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "import jsonlogger\n")
        result = checkpoint.check_known_bad_imports([f])
        assert result.status == CheckpointStatus.WARNING
        assert "jsonlogger" in result.warnings[0]
        assert "pythonjsonlogger" in result.warnings[0]

    def test_known_bad_vectordb(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "from google.cloud.vectordb import Client\n")
        result = checkpoint.check_known_bad_imports([f])
        assert result.status == CheckpointStatus.WARNING
        assert "no PyPI replacement" in result.warnings[0]

    def test_valid_import_not_flagged(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "import os\nimport json\n")
        result = checkpoint.check_known_bad_imports([f])
        assert result.status == CheckpointStatus.PASSED

    def test_denylist_extensible(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "import fake_hallucinated_pkg\n")
        result = checkpoint.check_known_bad_imports(
            [f],
            extra_denylist={"fake_hallucinated_pkg": "real_pkg"},
        )
        assert result.status == CheckpointStatus.WARNING
        assert "real_pkg" in result.warnings[0]

    def test_from_import_variant(self, tmp_path, checkpoint):
        f = _write_py(tmp_path, "a.py", "from jsonlogger import JsonFormatter\n")
        result = checkpoint.check_known_bad_imports([f])
        assert result.status == CheckpointStatus.WARNING


class TestStubDetectionWithSentinel:
    """L2+: STUB_SENTINEL-aware stub detection."""

    def test_pipeline_stub_is_not_warning(self, tmp_path, checkpoint):
        """File with STUB_SENTINEL should not trigger LLM stub warning."""
        from startd8.utils.code_extraction import STUB_SENTINEL

        content = (
            f"# {STUB_SENTINEL}\n"
            '"""module — stub."""\n'
            "\n"
            "def placeholder():\n"
            "    pass\n"
        )
        f = _write_py(tmp_path, "a.py", content)
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.PASSED
        assert result.details.get("pipeline_stubs") == 1

    def test_llm_stub_detected(self, tmp_path, checkpoint):
        """File without STUB_SENTINEL but with pass body → LLM stub warning."""
        f = _write_py(tmp_path, "a.py", "def foo():\n    pass\n")
        result = checkpoint.check_stubs([f])
        assert result.status == CheckpointStatus.WARNING
        assert "LLM stubs" in result.warnings[0]

    def test_mixed_pipeline_and_llm_stubs(self, tmp_path, checkpoint):
        """Pipeline stubs don't count toward LLM stub ratio."""
        from startd8.utils.code_extraction import STUB_SENTINEL

        # File 1: pipeline stub (expected)
        f1 = _write_py(tmp_path, "stub.py", f"# {STUB_SENTINEL}\ndef a(): pass\n")
        # File 2: real code
        f2 = _write_py(tmp_path, "real.py", "def b():\n    return 42\n")
        result = checkpoint.check_stubs([f1, f2])
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
        assert "Known Bad Import Check" in names

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
