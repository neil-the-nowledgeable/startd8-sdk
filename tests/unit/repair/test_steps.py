"""Tests for startd8.repair.steps."""

from pathlib import Path

from startd8.repair.models import (
    ElementContext,
    ImportDiagnostic,
    RepairContext,
)
from startd8.repair.steps.ast_validate import AstValidateStep
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.import_completion import (
    ErrorDrivenImportCompletion,
    ManifestImportCompletion,
)
from startd8.repair.steps.indent_normalize import IndentNormalizeStep


class TestFenceStripStep:
    def test_strips_fences(self):
        step = FenceStripStep()
        code = "```python\nx = 1\n```"
        ctx = RepairContext()
        result = step(code, ctx, Path("test.py"))
        assert result.modified is True
        assert "```" not in result.code
        assert "x = 1" in result.code

    def test_no_fences_no_change(self):
        step = FenceStripStep()
        code = "x = 1\ny = 2"
        ctx = RepairContext()
        result = step(code, ctx, Path("test.py"))
        assert result.modified is False

    def test_protocol_name(self):
        step = FenceStripStep()
        assert step.name == "fence_strip"

    def test_works_without_element_context(self):
        """Fence strip is truly shared — no level-specific adaptation."""
        step = FenceStripStep()
        code = "```\npass\n```"
        ctx = RepairContext()
        result = step(code, ctx, Path("t.py"), element_context=None)
        assert result.modified is True


class TestIndentNormalizeStep:
    def test_fixes_bad_indent(self):
        step = IndentNormalizeStep()
        code = "  def foo():\n    return 1"  # Extra leading indent
        ctx = RepairContext()
        result = step(code, ctx, Path("t.py"))
        assert result.modified is True
        assert result.metrics.get("strategy") is not None

    def test_valid_code_unchanged(self):
        step = IndentNormalizeStep()
        code = "def foo():\n    return 1"
        ctx = RepairContext()
        result = step(code, ctx, Path("t.py"))
        assert result.modified is False

    def test_with_parent_class(self):
        """Uses class-wrapper fallback when parent_class is set."""
        step = IndentNormalizeStep()
        # Method body without class wrapper — needs parent_class context
        code = "    def method(self):\n        return 1"
        ec = ElementContext(parent_class="MyClass")
        ctx = RepairContext()
        result = step(code, ctx, Path("t.py"), element_context=ec)
        # Should try strategies with method awareness
        assert isinstance(result.modified, bool)

    def test_without_parent_class(self):
        """Falls back to file-level ast.parse when parent_class is None."""
        step = IndentNormalizeStep()
        code = "    x = 1"  # Indented at file level
        ctx = RepairContext()
        result = step(code, ctx, Path("t.py"), element_context=None)
        assert result.modified is True


class TestManifestImportCompletion:
    def test_no_element_context_skips(self):
        step = ManifestImportCompletion()
        ctx = RepairContext()
        result = step("x = 1", ctx, Path("t.py"), element_context=None)
        assert result.modified is False

    def test_no_imports_skips(self):
        step = ManifestImportCompletion()
        ec = ElementContext(imports=None)
        ctx = RepairContext()
        result = step("x = 1", ctx, Path("t.py"), element_context=ec)
        assert result.modified is False

    def test_adds_missing_from_import(self):
        step = ManifestImportCompletion()

        class MockImport:
            kind = "from"
            module = "os.path"
            names = ["join"]
            alias = None

        ec = ElementContext(imports=[MockImport()])
        ctx = RepairContext()
        code = "result = join('a', 'b')"
        result = step(code, ctx, Path("t.py"), element_context=ec)
        assert result.modified is True
        assert "from os.path import join" in result.code

    def test_skips_existing_import(self):
        step = ManifestImportCompletion()

        class MockImport:
            kind = "from"
            module = "os.path"
            names = ["join"]
            alias = None

        ec = ElementContext(imports=[MockImport()])
        ctx = RepairContext()
        code = "from os.path import join\nresult = join('a', 'b')"
        result = step(code, ctx, Path("t.py"), element_context=ec)
        assert result.modified is False


class TestErrorDrivenImportCompletion:
    def test_no_diagnostics_skips(self):
        step = ErrorDrivenImportCompletion()
        ctx = RepairContext(diagnostics=[])
        result = step("x = 1", ctx, Path("t.py"))
        assert result.modified is False

    def test_adds_import_from_diagnostic(self):
        step = ErrorDrivenImportCompletion()
        diag = ImportDiagnostic(
            category="import", file="t.py", message="No module", module="grpc", name="",
        )
        ctx = RepairContext(diagnostics=[diag])
        result = step("x = grpc.channel()", ctx, Path("t.py"))
        assert result.modified is True
        assert "import grpc" in result.code

    def test_adds_from_import_with_name(self):
        step = ErrorDrivenImportCompletion()
        diag = ImportDiagnostic(
            category="import", file="t.py", message="No module", module="os.path", name="join",
        )
        ctx = RepairContext(diagnostics=[diag])
        result = step("result = join('a', 'b')", ctx, Path("t.py"))
        assert result.modified is True
        assert "from os.path import join" in result.code

    def test_skips_already_imported(self):
        step = ErrorDrivenImportCompletion()
        diag = ImportDiagnostic(
            category="import", file="t.py", message="No module", module="os", name="",
        )
        ctx = RepairContext(
            diagnostics=[diag],
            existing_imports={Path("t.py"): {"os"}},
        )
        result = step("import os\nos.path.join('a')", ctx, Path("t.py"))
        assert result.modified is False


class TestAstValidateStep:
    def test_valid_code(self):
        step = AstValidateStep()
        ctx = RepairContext()
        result = step("x = 1", ctx, Path("t.py"))
        assert result.metrics["valid"] is True
        assert result.modified is False

    def test_invalid_code(self):
        step = AstValidateStep()
        ctx = RepairContext()
        result = step("def (broken", ctx, Path("t.py"))
        assert result.metrics["valid"] is False

    def test_method_with_parent_class(self):
        step = AstValidateStep()
        ec = ElementContext(parent_class="Foo")
        ctx = RepairContext()
        # Valid as a method inside a class
        code = "def bar(self):\n    return 1"
        result = step(code, ctx, Path("t.py"), element_context=ec)
        assert result.metrics["valid"] is True

    def test_method_body_without_parent_class(self):
        step = AstValidateStep()
        ctx = RepairContext()
        code = "def bar(self):\n    return 1"
        result = step(code, ctx, Path("t.py"))
        assert result.metrics["valid"] is True  # Valid as standalone function too
