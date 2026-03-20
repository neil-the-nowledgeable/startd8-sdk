"""Tests for Java repair pipeline (Phase J1)."""

from pathlib import Path

import pytest

from startd8.repair.config import RepairConfig
from startd8.repair.models import Diagnostic, RepairContext
from startd8.repair.routing import create_steps_from_route, route_failures
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.bracket_balance import BracketBalanceStep
from startd8.repair.steps.java_syntax_validate import JavaSyntaxValidateStep


VALID_JAVA = """\
package com.example;

public class Example {
    private String name;

    public Example(String name) {
        this.name = name;
    }
}
"""

INVALID_JAVA_BRACES = """\
package com.example;

public class Bad {
    public void doWork() {
"""

FENCED_JAVA = """\
```java
package com.example;

public class Fenced {
    public void hello() {}
}
```
"""


class TestJavaSyntaxValidateStep:
    def test_valid_java_passes(self):
        step = JavaSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(VALID_JAVA, ctx, Path("Example.java"))
        assert result.step_name == "java_syntax_validate"
        assert result.modified is False
        assert result.metrics["valid"] is True

    def test_invalid_java_fails(self):
        step = JavaSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(INVALID_JAVA_BRACES, ctx, Path("Bad.java"))
        assert result.metrics["valid"] is False
        assert "error" in result.metrics

    def test_no_type_declaration_fails(self):
        code = "package com.example;\n// just a comment\n"
        step = JavaSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(code, ctx, Path("Empty.java"))
        assert result.metrics["valid"] is False

    def test_code_unchanged(self):
        step = JavaSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(VALID_JAVA, ctx, Path("Example.java"))
        assert result.code == VALID_JAVA


class TestJavaRepairPipeline:
    """Integration: fence_strip + bracket_balance + java_syntax_validate."""

    def test_fence_strip_then_validate(self):
        fence_step = FenceStripStep()
        validate_step = JavaSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        fp = Path("Fenced.java")

        # Step 1: strip fences
        r1 = fence_step(FENCED_JAVA, ctx, fp)
        assert r1.modified is True

        # Step 2: validate stripped code
        r2 = validate_step(r1.code, ctx, fp)
        assert r2.metrics["valid"] is True

    def test_bracket_balance_then_validate(self):
        balance_step = BracketBalanceStep()
        validate_step = JavaSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        fp = Path("Bad.java")

        # bracket_balance may or may not fix the issue
        r1 = balance_step(INVALID_JAVA_BRACES, ctx, fp)
        # validate should report on the result
        r2 = validate_step(r1.code, ctx, fp)
        # We mainly verify the pipeline runs without error
        assert r2.step_name == "java_syntax_validate"


class TestJavaRoutingEntries:
    """Java routes are registered and produce correct step sequences."""

    def test_java_syntax_route(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="Test.java", message="syntax error"),
        ]
        route = route_failures(diagnostics, config)
        assert "fence_strip" in route.steps
        assert "bracket_balance" in route.steps
        # java_syntax_validate is in the route (via union with Python syntax route)
        assert "java_syntax_validate" in route.steps

    def test_java_import_route(self):
        config = RepairConfig(repairable_categories={"import"})
        diagnostics = [
            Diagnostic(category="import", file="Test.java", message="import error"),
        ]
        route = route_failures(diagnostics, config)
        assert "fence_strip" in route.steps
        assert "java_syntax_validate" in route.steps

    def test_java_syntax_validate_in_step_factories(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="Test.java", message="syntax error"),
        ]
        route = route_failures(diagnostics, config)
        steps = create_steps_from_route(route)
        step_names = [s.name for s in steps]
        assert "java_syntax_validate" in step_names

    def test_java_syntax_validate_after_ast_validate_in_canonical_order(self):
        """java_syntax_validate should appear after ast_validate in canonical order."""
        from startd8.repair.routing import _CANONICAL_ORDER
        ast_idx = _CANONICAL_ORDER.index("ast_validate")
        java_idx = _CANONICAL_ORDER.index("java_syntax_validate")
        assert java_idx > ast_idx


class TestJavaRepairEnabled:
    """Java language profile has repair_enabled=True."""

    def test_repair_enabled(self):
        from startd8.languages.java import JavaLanguageProfile
        profile = JavaLanguageProfile()
        assert profile.repair_enabled is True
