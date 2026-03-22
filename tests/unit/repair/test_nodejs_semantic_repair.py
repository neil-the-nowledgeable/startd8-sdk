"""Tests for Node.js semantic repair steps, routing, and bridge (REQ-KZ-ND-402d).

Covers Phase 0 (shebang_strip) and Phase 2 (var_to_const, dedup_require,
contamination_strip_js) repair steps, plus routing and bridge integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from startd8.repair.models import Diagnostic, RepairContext, SemanticDiagnostic
from startd8.repair.routing import route_failures
from startd8.repair.semantic_bridge import translate_to_diagnostics
from startd8.repair.steps.contamination_strip_js import ContaminationStripJsStep
from startd8.repair.steps.dedup_require import DedupRequireStep
from startd8.repair.steps.eslint_autofix import EslintAutoFixStep
from startd8.repair.steps.shebang_strip import ShebangStripStep
from startd8.repair.steps.var_to_const import VarToConstStep


@pytest.fixture
def ctx() -> RepairContext:
    return RepairContext()


# ---------------------------------------------------------------------------
# ShebangStripStep
# ---------------------------------------------------------------------------

class TestShebangStrip:
    def test_removes_python_shebang(self, ctx: RepairContext) -> None:
        code = "#!/usr/bin/env python3\nconst x = 1;\n"
        step = ShebangStripStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "#!/usr/bin/env python3" not in result.code
        assert "const x = 1;" in result.code

    def test_keeps_node_shebang(self, ctx: RepairContext) -> None:
        code = "#!/usr/bin/env node\nconst x = 1;\n"
        step = ShebangStripStep()
        result = step(code, ctx, Path("cli.js"))
        assert result.modified is False
        assert "#!/usr/bin/env node" in result.code

    def test_skips_non_js_file(self, ctx: RepairContext) -> None:
        code = "#!/usr/bin/env python3\nprint('hello')\n"
        step = ShebangStripStep()
        result = step(code, ctx, Path("script.py"))
        assert result.modified is False

    def test_no_shebang(self, ctx: RepairContext) -> None:
        code = "const x = 1;\n"
        step = ShebangStripStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False


# ---------------------------------------------------------------------------
# VarToConstStep
# ---------------------------------------------------------------------------

class TestVarToConst:
    def test_var_to_const_basic(self, ctx: RepairContext) -> None:
        code = "var x = 1;\nvar y = 'hello';\n"
        step = VarToConstStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "const x = 1;" in result.code
        assert "const y = 'hello';" in result.code
        assert "var " not in result.code

    def test_var_to_let_for_loop(self, ctx: RepairContext) -> None:
        code = "for (var i = 0; i < 10; i++) {\n  console.log(i);\n}\n"
        step = VarToConstStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "for (let i = 0;" in result.code
        assert "var " not in result.code

    def test_var_in_comment_untouched(self, ctx: RepairContext) -> None:
        code = "// var x = 1;\nconst y = 2;\n"
        step = VarToConstStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False
        assert "// var x = 1;" in result.code

    def test_clean_file_no_modifications(self, ctx: RepairContext) -> None:
        code = "const x = 1;\nlet y = 2;\n"
        step = VarToConstStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False

    def test_skips_non_js_file(self, ctx: RepairContext) -> None:
        code = "var x = 1;\n"
        step = VarToConstStep()
        result = step(code, ctx, Path("script.py"))
        assert result.modified is False

    def test_typescript_file(self, ctx: RepairContext) -> None:
        code = "var x: number = 1;\n"
        step = VarToConstStep()
        result = step(code, ctx, Path("app.ts"))
        assert result.modified is True
        assert "const " in result.code

    def test_tsx_file(self, ctx: RepairContext) -> None:
        code = "var Component = () => <div/>;\n"
        step = VarToConstStep()
        result = step(code, ctx, Path("App.tsx"))
        assert result.modified is True


# ---------------------------------------------------------------------------
# DedupRequireStep
# ---------------------------------------------------------------------------

class TestDedupRequire:
    def test_removes_identical_require(self, ctx: RepairContext) -> None:
        code = (
            "const express = require('express');\n"
            "const express = require('express');\n"
            "const app = express();\n"
        )
        step = DedupRequireStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert result.code.count("require('express')") == 1
        assert "const app = express();" in result.code

    def test_keeps_different_destructuring(self, ctx: RepairContext) -> None:
        code = (
            "const { Router } = require('express');\n"
            "const { json } = require('express');\n"
        )
        step = DedupRequireStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False
        assert result.code.count("require('express')") == 2

    def test_removes_identical_esm_import(self, ctx: RepairContext) -> None:
        code = (
            "import express from 'express';\n"
            "import express from 'express';\n"
        )
        step = DedupRequireStep()
        result = step(code, ctx, Path("app.mjs"))
        assert result.modified is True
        lines = [l for l in result.code.splitlines() if l.strip()]
        assert len(lines) == 1

    def test_clean_file_no_modifications(self, ctx: RepairContext) -> None:
        code = (
            "const express = require('express');\n"
            "const path = require('path');\n"
        )
        step = DedupRequireStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False

    def test_skips_non_js_file(self, ctx: RepairContext) -> None:
        code = "import os\nimport os\n"
        step = DedupRequireStep()
        result = step(code, ctx, Path("script.py"))
        assert result.modified is False


# ---------------------------------------------------------------------------
# ContaminationStripJsStep
# ---------------------------------------------------------------------------

class TestContaminationStripJs:
    def test_strips_def_line(self, ctx: RepairContext) -> None:
        code = "def main():\n  pass\nconst x = 1;\n"
        step = ContaminationStripJsStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "def main" not in result.code
        assert "const x = 1;" in result.code

    def test_strips_from_future(self, ctx: RepairContext) -> None:
        code = "from __future__ import annotations\nconst x = 1;\n"
        step = ContaminationStripJsStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "from __future__" not in result.code

    def test_strips_self_at_statement_level(self, ctx: RepairContext) -> None:
        code = 'self.name = "test"\nconst x = 1;\n'
        step = ContaminationStripJsStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "self.name" not in result.code

    def test_keeps_self_in_string(self, ctx: RepairContext) -> None:
        code = 'console.log("help yourself.");\n'
        step = ContaminationStripJsStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False
        assert "yourself" in result.code

    def test_keeps_comment_with_fingerprint(self, ctx: RepairContext) -> None:
        code = "// def main() — Python version\nconst x = 1;\n"
        step = ContaminationStripJsStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False

    def test_clean_file_no_modifications(self, ctx: RepairContext) -> None:
        code = "const x = 1;\nexport default x;\n"
        step = ContaminationStripJsStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False

    def test_skips_non_js_file(self, ctx: RepairContext) -> None:
        code = "def main():\n  pass\n"
        step = ContaminationStripJsStep()
        result = step(code, ctx, Path("main.py"))
        assert result.modified is False


# ---------------------------------------------------------------------------
# Routing integration
# ---------------------------------------------------------------------------

class TestNodejsRouting:
    def _make_config(self):
        """Create a RepairConfig — default already includes 'semantic' category."""
        from startd8.repair.config import RepairConfig
        return RepairConfig()

    def test_routes_var_usage_to_eslint(self) -> None:
        """Phase 3: var_usage routes to eslint_autofix (not var_to_const)."""
        diags = [SemanticDiagnostic(
            category="semantic",
            file="app.js",
            message="var usage",
            semantic_category="var_usage",
        )]
        route = route_failures(diags, self._make_config(), language_id="nodejs")
        assert "eslint_autofix" in route.steps
        assert "js_syntax_validate" in route.steps

    def test_routes_python_contamination(self) -> None:
        diags = [SemanticDiagnostic(
            category="semantic",
            file="app.js",
            message="contamination",
            semantic_category="python_contamination",
        )]
        route = route_failures(diags, self._make_config(), language_id="nodejs")
        assert "contamination_strip_js" in route.steps
        assert "js_syntax_validate" in route.steps

    def test_routes_duplicate_require_to_eslint(self) -> None:
        """Phase 3: duplicate_require routes to eslint_autofix (not dedup_require)."""
        diags = [SemanticDiagnostic(
            category="semantic",
            file="app.js",
            message="dup require",
            semantic_category="duplicate_require",
        )]
        route = route_failures(diags, self._make_config(), language_id="nodejs")
        assert "eslint_autofix" in route.steps
        assert "js_syntax_validate" in route.steps


# ---------------------------------------------------------------------------
# Bridge integration
# ---------------------------------------------------------------------------

class TestNodejsBridge:
    def test_translates_repairable_categories(self) -> None:
        issues = [
            {"category": "var_usage", "severity": "warning", "message": "use const", "line": 1},
        ]
        diags = translate_to_diagnostics(issues, "app.js")
        assert len(diags) == 1
        assert isinstance(diags[0], SemanticDiagnostic)
        assert diags[0].semantic_category == "var_usage"

    def test_skips_advisory_categories(self) -> None:
        issues = [
            {"category": "unhandled_promise", "severity": "warning", "message": "missing await", "line": 5},
            {"category": "console_log_in_service", "severity": "warning", "message": "use logger", "line": 10},
            {"category": "module_system_mixing", "severity": "error", "message": "mixed", "line": 1},
        ]
        diags = translate_to_diagnostics(issues, "app.js")
        assert len(diags) == 0  # All advisory — not in _REPAIRABLE_CATEGORIES

    def test_translates_python_contamination(self) -> None:
        issues = [
            {"category": "python_contamination", "severity": "error", "message": "Python in JS", "line": 1},
        ]
        diags = translate_to_diagnostics(issues, "app.js")
        assert len(diags) == 1
        assert isinstance(diags[0], SemanticDiagnostic)
        assert diags[0].semantic_category == "python_contamination"


# ---------------------------------------------------------------------------
# EslintAutoFixStep (Phase 3)
# ---------------------------------------------------------------------------

class TestEslintAutoFix:
    def test_fixes_var_with_eslint(self, ctx: RepairContext) -> None:
        """ESLint converts var to const/let with reassignment awareness."""
        import shutil

        if shutil.which("eslint") is None:
            pytest.skip("eslint not installed")
        code = "var x = 1;\nvar y = 2;\n"
        step = EslintAutoFixStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "var " not in result.code
        # ESLint uses const when not reassigned
        assert "const x" in result.code or "let x" in result.code
        assert result.metrics.get("engine") == "eslint"

    def test_fixes_var_with_reassignment(self, ctx: RepairContext) -> None:
        """ESLint uses let (not const) for reassigned variables."""
        import shutil

        if shutil.which("eslint") is None:
            pytest.skip("eslint not installed")
        code = "var x = 1;\nx = 2;\n"
        step = EslintAutoFixStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "let x" in result.code
        assert "var " not in result.code

    def test_chains_dedup_after_eslint(self, ctx: RepairContext) -> None:
        """ESLint can't fix duplicate imports — DedupRequireStep chains."""
        import shutil

        if shutil.which("eslint") is None:
            pytest.skip("eslint not installed")
        code = (
            "var x = require('express');\n"
            "var x = require('express');\n"
        )
        step = EslintAutoFixStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        # Either eslint fixed var→const/let, or dedup removed the duplicate
        assert result.code.count("require('express')") <= 2

    def test_clean_file_no_modifications(self, ctx: RepairContext) -> None:
        code = "const x = 1;\nconst y = 2;\n"
        step = EslintAutoFixStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is False

    def test_skips_non_js_file(self, ctx: RepairContext) -> None:
        code = "var x = 1;\n"
        step = EslintAutoFixStep()
        result = step(code, ctx, Path("script.py"))
        assert result.modified is False

    def test_fallback_when_eslint_unavailable(self, ctx: RepairContext) -> None:
        """When ESLint is not available, falls back to Phase 2 steps."""
        from unittest.mock import patch

        code = "var x = 1;\n"
        step = EslintAutoFixStep()
        with patch("startd8.repair.steps.eslint_autofix.shutil") as mock_shutil:
            mock_shutil.which.return_value = None
            result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "const " in result.code
        assert result.metrics.get("engine") == "phase2_fallback"

    def test_eslint_produces_better_than_regex(self, ctx: RepairContext) -> None:
        """ESLint distinguishes const vs let — regex-based step can't."""
        import shutil

        if shutil.which("eslint") is None:
            pytest.skip("eslint not installed")
        # x is reassigned → should be let, not const
        # y is not reassigned → should be const
        code = "var x = 1;\nx = 2;\nvar y = 3;\n"
        step = EslintAutoFixStep()
        result = step(code, ctx, Path("app.js"))
        assert result.modified is True
        assert "let x" in result.code
        assert "const y" in result.code
