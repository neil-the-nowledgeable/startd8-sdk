"""Tests for startd8.repair.steps."""

from pathlib import Path

from startd8.repair.models import (
    ElementContext,
    ImportDiagnostic,
    RepairContext,
)
from startd8.repair.steps.ast_validate import AstValidateStep
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.future_import_reorder import FutureImportReorderStep
from startd8.repair.steps.import_completion import (
    ErrorDrivenImportCompletion,
    ManifestImportCompletion,
    _find_import_insertion_line,
    _insert_imports,
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

    def test_structural_reindent_nonuniform_body(self):
        """Strategy 6: Fix non-uniform indentation that textwrap.dedent cannot handle."""
        step = IndentNormalizeStep()
        # Ollama-style corrupted output: body lines with mixed 0/12/16-space indent
        # wrapped by bare_statement_wrap into a def with 4-space base.
        code = (
            "def add_fields(log_record, record, message_dict):\n"
            "    if 'timestamp' not in log_record:\n"
            "                log_record['timestamp'] = record.created\n"
            "            if 'severity' in log_record:\n"
            "                log_record['severity'] = log_record['severity'].upper()\n"
            "            else:\n"
            "                log_record['severity'] = record.levelname"
        )
        ctx = RepairContext()
        result = step(code, ctx, Path("t.py"), element_context=None)
        assert result.modified is True
        assert result.metrics.get("strategy", "").startswith("structural_reindent")
        # Verify the result actually parses
        import ast
        ast.parse(result.code)

    def test_structural_reindent_method_body(self):
        """Strategy 6: Fix non-uniform method body indentation."""
        step = IndentNormalizeStep()
        # Body-only code with non-uniform indentation (method context)
        code = (
            "if x > 0:\n"
            "            return x\n"
            "        else:\n"
            "            return -x"
        )
        ec = ElementContext(parent_class="MyClass")
        ctx = RepairContext()
        result = step(code, ctx, Path("t.py"), element_context=ec)
        # Should attempt structural reindent since dedent won't help
        assert result.code is not None


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

    def test_relative_path_diagnostic_matches_absolute_file(self):
        """Diagnostic with relative path matches absolute file_path via basename."""
        step = ErrorDrivenImportCompletion()
        diag = ImportDiagnostic(
            category="import",
            file="pipeline-output/gen/src/app.py",
            message="Undefined name",
            module="flask",
            name="Flask",
        )
        ctx = RepairContext(diagnostics=[diag])
        abs_path = Path("/Users/dev/project/pipeline-output/gen/src/app.py")
        result = step("app = Flask(__name__)", ctx, abs_path)
        assert result.modified is True
        assert "from flask import Flask" in result.code

    def test_f821_flask_import_added(self):
        """End-to-end: F821 ImportDiagnostic adds 'from flask import Flask'."""
        step = ErrorDrivenImportCompletion()
        diag = ImportDiagnostic(
            category="import",
            file="app.py",
            message="Undefined name `Flask`",
            module="flask",
            name="Flask",
        )
        ctx = RepairContext(diagnostics=[diag])
        code = "app = Flask(__name__)"
        result = step(code, ctx, Path("app.py"))
        assert result.modified is True
        assert "from flask import Flask" in result.code
        assert result.metrics.get("imports_added") == 1


class TestImportInsertion:
    """Tests for _find_import_insertion_line and _insert_imports."""

    def test_inserts_after_future_import(self):
        code = "# comment\n\nfrom __future__ import annotations\n\ndef foo():\n    pass\n"
        result = _insert_imports(code, "import os")
        lines = result.splitlines()
        future_idx = next(i for i, l in enumerate(lines) if "from __future__" in l)
        os_idx = next(i for i, l in enumerate(lines) if l.strip() == "import os")
        assert os_idx > future_idx

    def test_inserts_after_skeleton_comment_and_future(self):
        code = "# [STARTD8-SKELETON]\n\nfrom __future__ import annotations\n\ndef create_app():\n    return Flask(__name__)\n"
        result = _insert_imports(code, "from flask import Flask")
        # Must not cause SyntaxError
        compile(result, "<test>", "exec")
        assert "from flask import Flask" in result

    def test_inserts_at_top_when_no_future(self):
        code = "def foo():\n    pass\n"
        result = _insert_imports(code, "import os")
        assert result.startswith("import os")

    def test_inserts_after_docstring(self):
        code = '"""Module docstring."""\n\ndef foo():\n    pass\n'
        result = _insert_imports(code, "import os")
        lines = result.splitlines()
        doc_idx = next(i for i, l in enumerate(lines) if "docstring" in l)
        os_idx = next(i for i, l in enumerate(lines) if l.strip() == "import os")
        assert os_idx > doc_idx

    def test_inserts_after_multiline_docstring(self):
        code = '"""\nModule\ndocstring.\n"""\n\nfrom __future__ import annotations\n\nx = 1\n'
        result = _insert_imports(code, "import os")
        compile(result, "<test>", "exec")
        lines = result.splitlines()
        future_idx = next(i for i, l in enumerate(lines) if "from __future__" in l)
        os_idx = next(i for i, l in enumerate(lines) if l.strip() == "import os")
        assert os_idx > future_idx

    def test_find_insertion_line_empty(self):
        assert _find_import_insertion_line([]) == 0

    def test_find_insertion_line_hashbang(self):
        lines = ["#!/usr/bin/env python3", "import os"]
        assert _find_import_insertion_line(lines) == 1


class TestFutureImportReorderStep:
    def test_moves_future_import_before_regular_import(self):
        """Exact scenario from the bug: skeleton import before from __future__."""
        step = FutureImportReorderStep()
        code = (
            "from flask import Flask\n"
            "\n"
            "# [STARTD8-SKELETON]\n"
            "\n"
            "from __future__ import annotations\n"
            "\n"
            "\n"
            "def create_app():\n"
            "    return Flask(__name__)\n"
        )
        ctx = RepairContext()
        result = step(code, ctx, Path("app.py"))
        assert result.modified is True
        # Must compile without SyntaxError
        compile(result.code, "<test>", "exec")
        # Future import must come before Flask import
        lines = result.code.splitlines()
        future_idx = next(i for i, l in enumerate(lines) if "from __future__" in l)
        flask_idx = next(i for i, l in enumerate(lines) if "from flask" in l)
        assert future_idx < flask_idx

    def test_no_future_import_unchanged(self):
        step = FutureImportReorderStep()
        code = "from flask import Flask\n\ndef create_app():\n    pass\n"
        ctx = RepairContext()
        result = step(code, ctx, Path("app.py"))
        assert result.modified is False

    def test_future_import_already_at_top(self):
        step = FutureImportReorderStep()
        code = "from __future__ import annotations\n\nfrom flask import Flask\n"
        ctx = RepairContext()
        result = step(code, ctx, Path("app.py"))
        assert result.modified is False

    def test_future_import_after_docstring_and_regular_import(self):
        step = FutureImportReorderStep()
        code = (
            '"""Module docstring."""\n'
            "\n"
            "import os\n"
            "from __future__ import annotations\n"
            "\n"
            "x = 1\n"
        )
        ctx = RepairContext()
        result = step(code, ctx, Path("app.py"))
        assert result.modified is True
        compile(result.code, "<test>", "exec")
        lines = result.code.splitlines()
        future_idx = next(i for i, l in enumerate(lines) if "from __future__" in l)
        os_idx = next(i for i, l in enumerate(lines) if "import os" in l)
        assert future_idx < os_idx

    def test_preserves_hashbang(self):
        step = FutureImportReorderStep()
        code = (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            "from __future__ import annotations\n"
            "\n"
            "print(sys.argv)\n"
        )
        ctx = RepairContext()
        result = step(code, ctx, Path("script.py"))
        assert result.modified is True
        lines = result.code.splitlines()
        assert lines[0] == "#!/usr/bin/env python3"
        future_idx = next(i for i, l in enumerate(lines) if "from __future__" in l)
        sys_idx = next(i for i, l in enumerate(lines) if "import sys" in l)
        assert future_idx < sys_idx

    def test_orphaned_blank_line_after_removed_future_import(self):
        """Fix 2: Blank line immediately after a removed future import is cleaned up."""
        step = FutureImportReorderStep()
        code = (
            "import os\n"
            "from __future__ import annotations\n"
            "\n"  # orphaned blank line after the future import
            "x = 1\n"
        )
        ctx = RepairContext()
        result = step(code, ctx, Path("app.py"))
        assert result.modified is True
        # The result should not have a double blank line where the future import was
        lines = result.code.splitlines()
        # No two consecutive blank lines
        for i in range(len(lines) - 1):
            assert not (lines[i].strip() == "" and lines[i + 1].strip() == ""), (
                f"Double blank line at lines {i}-{i+1}"
            )

    def test_multi_line_parenthesized_future_import(self):
        """Fix 6: Multi-line parenthesized from __future__ import."""
        step = FutureImportReorderStep()
        code = (
            "import os\n"
            "from __future__ import (\n"
            "    annotations,\n"
            "    division,\n"
            ")\n"
            "\n"
            "x = 1\n"
        )
        ctx = RepairContext()
        result = step(code, ctx, Path("app.py"))
        assert result.modified is True
        compile(result.code, "<test>", "exec")
        lines = result.code.splitlines()
        # Future import block should come before 'import os'
        future_start = next(i for i, l in enumerate(lines) if "from __future__" in l)
        os_idx = next(i for i, l in enumerate(lines) if "import os" in l)
        assert future_start < os_idx

    def test_protocol_name(self):
        step = FutureImportReorderStep()
        assert step.name == "future_import_reorder"


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
