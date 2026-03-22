"""Tests for Go semantic repair pipeline (REQ-KZ-GO-403d Phase 2).

Covers:
- GoPythonContaminationStripStep
- GoDotImportCleanupStep
- Routing table wiring
- Semantic bridge wiring
- Orchestrator dispatch
"""

from pathlib import Path
from unittest import mock

import pytest

from startd8.repair.models import Diagnostic, RepairContext, SemanticDiagnostic
from startd8.repair.steps.go_contamination_strip import (
    GoPythonContaminationStripStep,
    _strip_contamination,
)
from startd8.repair.steps._go_tool_runner import GoToolResult
from startd8.repair.steps.go_dot_import_cleanup import (
    GoDotImportCleanupStep,
    _is_stdlib_path,
    _remove_dot_imports,
)


# ── Contamination Strip ─────────────────────────────────────────────

class TestContaminationStrip:

    def test_removes_python_def(self):
        code = 'package main\n\ndef main():\n\nfunc main() {}\n'
        cleaned, removed, patterns = _strip_contamination(code)
        assert "def main():" not in cleaned
        assert "func main() {}" in cleaned
        assert len(removed) == 1
        assert "def " in patterns

    def test_removes_from_future(self):
        code = 'from __future__ import annotations\npackage main\n\nfunc main() {}\n'
        cleaned, removed, patterns = _strip_contamination(code)
        assert "from __future__" not in cleaned
        assert "package main" in cleaned

    def test_skips_backtick_raw_string(self):
        code = 'package main\n\nvar help = `\ndef main():\n  pass\n`\n\nfunc main() {}\n'
        cleaned, removed, _ = _strip_contamination(code)
        assert len(removed) == 0, "Should not strip inside backtick strings"
        assert "def main():" in cleaned

    def test_skips_inline_comment(self):
        code = 'package main\n\n// Python uses def to define functions\n\nfunc main() {}\n'
        cleaned, removed, _ = _strip_contamination(code)
        assert len(removed) == 0, "Should not strip after //"
        assert "def to define" in cleaned

    def test_skips_block_comment(self):
        code = 'package main\n\n/*\ndef main():\n  pass\n*/\n\nfunc main() {}\n'
        cleaned, removed, _ = _strip_contamination(code)
        assert len(removed) == 0, "Should not strip inside block comments"

    def test_multiple_fingerprints(self):
        code = 'from __future__ import annotations\nimport os\npackage main\n\nfunc main() {}\n'
        cleaned, removed, patterns = _strip_contamination(code)
        assert len(removed) == 2
        assert "from __future__" in patterns
        assert "import os" in patterns

    def test_step_no_contamination(self):
        step = GoPythonContaminationStripStep()
        code = 'package main\n\nfunc main() {}\n'
        ctx = RepairContext(diagnostics=[], config=None)
        result = step(code, ctx, Path("main.go"))
        assert not result.modified
        assert result.metrics["lines_removed"] == 0

    def test_step_with_contamination(self):
        step = GoPythonContaminationStripStep()
        code = 'from __future__ import annotations\npackage main\n\nfunc main() {}\n'
        ctx = RepairContext(diagnostics=[], config=None)
        # Mock gofmt to succeed
        with mock.patch(
            "startd8.repair.steps.go_contamination_strip.run_go_tool",
            return_value=GoToolResult(
                returncode=0, stdout="", stderr="",
                output_code="", tool_found=True,
            ),
        ):
            result = step(code, ctx, Path("main.go"))
        assert result.modified
        assert result.metrics["lines_removed"] == 1
        assert "from __future__" not in result.code

    def test_step_rollback_on_gofmt_failure(self):
        step = GoPythonContaminationStripStep()
        code = 'from __future__ import annotations\npackage main\n\nfunc main() {}\n'
        ctx = RepairContext(diagnostics=[], config=None)
        with mock.patch(
            "startd8.repair.steps.go_contamination_strip.run_go_tool",
            return_value=GoToolResult(
                returncode=1, stdout="", stderr="syntax error",
                output_code="", tool_found=True,
            ),
        ):
            result = step(code, ctx, Path("main.go"))
        assert not result.modified
        assert result.metrics.get("rollback") is True
        assert result.code == code  # Original preserved


# ── Dot Import Cleanup ───────────────────────────────────────────────

class TestDotImportCleanup:

    def test_is_stdlib_path(self):
        assert _is_stdlib_path("fmt") is True
        assert _is_stdlib_path("net/http") is True
        assert _is_stdlib_path("github.com/pkg/errors") is False
        assert _is_stdlib_path("golang.org/x/tools") is False

    def test_removes_block_dot_import(self):
        code = 'package main\n\nimport (\n\t. "fmt"\n\t"os"\n)\n\nfunc main() {}\n'
        cleaned, count = _remove_dot_imports(code)
        assert count == 1
        assert '. "fmt"' not in cleaned
        assert '"fmt"' in cleaned
        assert '"os"' in cleaned

    def test_removes_single_line_dot_import(self):
        code = 'package main\n\nimport . "fmt"\n\nfunc main() {}\n'
        cleaned, count = _remove_dot_imports(code)
        assert count == 1
        assert 'import "fmt"' in cleaned

    def test_skips_third_party_dot_import(self):
        code = 'package main\n\nimport (\n\t. "github.com/onsi/ginkgo"\n)\n\nfunc main() {}\n'
        cleaned, count = _remove_dot_imports(code)
        assert count == 0
        assert '. "github.com/onsi/ginkgo"' in cleaned

    def test_step_no_dot_imports(self):
        step = GoDotImportCleanupStep()
        code = 'package main\n\nimport "fmt"\n\nfunc main() {}\n'
        ctx = RepairContext(diagnostics=[], config=None)
        result = step(code, ctx, Path("main.go"))
        assert not result.modified

    def test_step_with_dot_import(self):
        step = GoDotImportCleanupStep()
        code = 'package main\n\nimport . "fmt"\n\nfunc main() { Println("hi") }\n'
        qualified = 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("hi") }\n'
        ctx = RepairContext(diagnostics=[], config=None)
        with mock.patch(
            "startd8.repair.steps.go_dot_import_cleanup.run_go_tool",
            return_value=GoToolResult(
                returncode=0, stdout="", stderr="",
                output_code=qualified, tool_found=True,
            ),
        ):
            result = step(code, ctx, Path("main.go"))
        assert result.modified
        assert result.metrics["dot_imports_cleaned"] == 1

    def test_step_rollback_on_goimports_failure(self):
        step = GoDotImportCleanupStep()
        code = 'package main\n\nimport . "fmt"\n\nfunc main() { Println("hi") }\n'
        ctx = RepairContext(diagnostics=[], config=None)
        with mock.patch(
            "startd8.repair.steps.go_dot_import_cleanup.run_go_tool",
            return_value=GoToolResult(
                returncode=1, stdout="", stderr="error",
                output_code=code, tool_found=True,
            ),
        ):
            result = step(code, ctx, Path("main.go"))
        assert not result.modified
        assert result.metrics.get("rollback") is True


# ── Routing ──────────────────────────────────────────────────────────

class TestGoSemanticRouting:

    def test_contamination_route_exists(self):
        from startd8.repair.config import RepairConfig
        from startd8.repair.routing import route_failures

        diag = SemanticDiagnostic(
            category="semantic",
            file="main.go",
            message="Python contamination",
            semantic_category="python_contamination",
            severity="error",
        )
        config = RepairConfig(
            repairable_categories=frozenset({"semantic"}),
            semantic_repair_categories=frozenset({"python_contamination"}),
        )
        route = route_failures([diag], config, language_id="go")
        assert "go_contamination_strip" in route.steps

    def test_dot_import_route_exists(self):
        from startd8.repair.config import RepairConfig
        from startd8.repair.routing import route_failures

        diag = SemanticDiagnostic(
            category="semantic",
            file="main.go",
            message="Dot-import",
            semantic_category="dot_import",
            severity="warning",
        )
        config = RepairConfig(
            repairable_categories=frozenset({"semantic"}),
            semantic_repair_categories=frozenset({"dot_import"}),
        )
        route = route_failures([diag], config, language_id="go")
        assert "go_dot_import_cleanup" in route.steps

    def test_both_routes_ordered_correctly(self):
        """Contamination strip must precede dot-import cleanup."""
        from startd8.repair.config import RepairConfig
        from startd8.repair.routing import route_failures

        diags = [
            SemanticDiagnostic(
                category="semantic", file="main.go", message="",
                semantic_category="python_contamination", severity="error",
            ),
            SemanticDiagnostic(
                category="semantic", file="main.go", message="",
                semantic_category="dot_import", severity="warning",
            ),
        ]
        config = RepairConfig(
            repairable_categories=frozenset({"semantic"}),
            semantic_repair_categories=frozenset({"python_contamination", "dot_import"}),
        )
        route = route_failures(diags, config, language_id="go")
        strip_idx = route.steps.index("go_contamination_strip")
        cleanup_idx = route.steps.index("go_dot_import_cleanup")
        assert strip_idx < cleanup_idx, "Contamination strip must run before dot-import cleanup"


# ── Semantic Bridge ──────────────────────────────────────────────────

class TestGoBridgeWiring:

    def test_dot_import_is_repairable(self):
        from startd8.repair.semantic_bridge import _REPAIRABLE_CATEGORIES
        assert "dot_import" in _REPAIRABLE_CATEGORIES

    def test_python_contamination_is_repairable(self):
        from startd8.repair.semantic_bridge import _REPAIRABLE_CATEGORIES
        assert "python_contamination" in _REPAIRABLE_CATEGORIES

    def test_translate_produces_diagnostics(self):
        from startd8.repair.semantic_bridge import translate_to_diagnostics

        issues = [
            {"category": "dot_import", "severity": "warning", "message": "dot import", "line": 3},
            {"category": "python_contamination", "severity": "error", "message": "contaminated", "line": 1},
            {"category": "unchecked_error", "severity": "warning", "message": "err", "line": 5},
        ]
        diags = translate_to_diagnostics(issues, "main.go")
        # Only repairable categories are translated
        assert len(diags) == 2
        categories = {d.semantic_category for d in diags if isinstance(d, SemanticDiagnostic)}
        assert "dot_import" in categories
        assert "python_contamination" in categories


# ── Orchestrator ─────────────────────────────────────────────────────

class TestGoOrchestrator:

    def test_go_in_semantic_repair_extensions(self):
        from startd8.repair.orchestrator import _SEMANTIC_REPAIR_EXTENSIONS
        assert ".go" in _SEMANTIC_REPAIR_EXTENSIONS
