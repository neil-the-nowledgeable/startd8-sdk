"""Tests for Go repair pipeline (Phase G1)."""

from pathlib import Path

import pytest

from startd8.repair.config import RepairConfig
from startd8.repair.models import Diagnostic, RepairContext
from startd8.repair.routing import create_steps_from_route, route_failures
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.go_syntax_validate import GoSyntaxValidateStep


VALID_GO = """\
package main

import "fmt"

func main() {
    fmt.Println("hello")
}
"""

INVALID_GO_BRACES = """\
package main

func main() {
    fmt.Println("hello")
"""

FENCED_GO = """\
```go
package main

import "fmt"

func main() {
    fmt.Println("hello")
}
```
"""

NO_PACKAGE_GO = """\
func main() {
    fmt.Println("hello")
}
"""


class TestGoSyntaxValidateStep:
    def test_valid_go_passes(self):
        step = GoSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(VALID_GO, ctx, Path("main.go"))
        assert result.step_name == "go_syntax_validate"
        assert result.modified is False
        assert result.metrics["valid"] is True

    def test_invalid_go_fails(self):
        step = GoSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(INVALID_GO_BRACES, ctx, Path("bad.go"))
        assert result.metrics["valid"] is False
        assert "error" in result.metrics

    def test_no_package_fails(self):
        step = GoSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(NO_PACKAGE_GO, ctx, Path("nopkg.go"))
        assert result.metrics["valid"] is False

    def test_python_content_fails(self):
        code = "def hello():\n    print('hi')\n"
        step = GoSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(code, ctx, Path("wrong.go"))
        assert result.metrics["valid"] is False

    def test_code_unchanged(self):
        step = GoSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(VALID_GO, ctx, Path("main.go"))
        assert result.code == VALID_GO


class TestGoRepairPipeline:
    def test_fence_strip_then_validate(self):
        fence_step = FenceStripStep()
        validate_step = GoSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        fp = Path("main.go")

        r1 = fence_step(FENCED_GO, ctx, fp)
        assert r1.modified is True

        r2 = validate_step(r1.code, ctx, fp)
        assert r2.metrics["valid"] is True


class TestGoRoutingEntries:
    def test_go_syntax_route(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="main.go", message="syntax error"),
        ]
        route = route_failures(diagnostics, config)
        assert "fence_strip" in route.steps
        assert "bracket_balance" in route.steps
        assert "go_syntax_validate" in route.steps

    def test_go_import_route(self):
        config = RepairConfig(repairable_categories={"import"})
        diagnostics = [
            Diagnostic(category="import", file="main.go", message="import error"),
        ]
        route = route_failures(diagnostics, config)
        assert "fence_strip" in route.steps
        assert "go_syntax_validate" in route.steps

    def test_go_syntax_validate_in_step_factories(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="main.go", message="syntax error"),
        ]
        route = route_failures(diagnostics, config)
        steps = create_steps_from_route(route)
        step_names = [s.name for s in steps]
        assert "go_syntax_validate" in step_names


class TestGoRepairEnabled:
    def test_repair_enabled(self):
        from startd8.languages.go import GoLanguageProfile
        profile = GoLanguageProfile()
        assert profile.repair_enabled is True
