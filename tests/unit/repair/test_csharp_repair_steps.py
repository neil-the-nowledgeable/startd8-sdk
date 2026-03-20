"""Tests for C# repair pipeline (Phase CS1)."""

from pathlib import Path

import pytest

from startd8.repair.config import RepairConfig
from startd8.repair.models import Diagnostic, RepairContext
from startd8.repair.routing import create_steps_from_route, route_failures
from startd8.repair.steps.csharp_syntax_validate import CSharpSyntaxValidateStep
from startd8.repair.steps.fence_strip import FenceStripStep


VALID_CSHARP = """\
using System;

namespace Example
{
    public class Greeter
    {
        public string Greet(string name) => $"Hello, {name}!";
    }
}
"""

INVALID_CSHARP_BRACES = """\
using System;

public class Bad {
    public void DoWork() {
"""


class TestCSharpSyntaxValidateStep:
    def test_valid_csharp_passes(self):
        step = CSharpSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(VALID_CSHARP, ctx, Path("Greeter.cs"))
        assert result.step_name == "csharp_syntax_validate"
        assert result.metrics["valid"] is True

    def test_invalid_csharp_fails(self):
        step = CSharpSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(INVALID_CSHARP_BRACES, ctx, Path("Bad.cs"))
        assert result.metrics["valid"] is False

    def test_python_content_fails(self):
        code = "def hello():\n    print('hi')\n"
        step = CSharpSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(code, ctx, Path("wrong.cs"))
        assert result.metrics["valid"] is False


class TestCSharpRoutingEntries:
    def test_csharp_syntax_route(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="Test.cs", message="syntax error"),
        ]
        route = route_failures(diagnostics, config)
        assert "fence_strip" in route.steps
        assert "csharp_syntax_validate" in route.steps

    def test_csharp_syntax_validate_in_factories(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="Test.cs", message="error"),
        ]
        route = route_failures(diagnostics, config)
        steps = create_steps_from_route(route)
        step_names = [s.name for s in steps]
        assert "csharp_syntax_validate" in step_names


class TestCSharpRepairEnabled:
    def test_repair_enabled(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        profile = CSharpLanguageProfile()
        assert profile.repair_enabled is True
