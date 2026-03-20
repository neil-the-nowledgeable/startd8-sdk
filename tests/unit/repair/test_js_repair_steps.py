"""Tests for Node.js repair pipeline (Phase N1)."""

from pathlib import Path

import pytest

from startd8.repair.config import RepairConfig
from startd8.repair.models import Diagnostic, RepairContext
from startd8.repair.routing import create_steps_from_route, route_failures
from startd8.repair.steps.fence_strip import FenceStripStep
from startd8.repair.steps.js_syntax_validate import JsSyntaxValidateStep


VALID_JS = """\
const express = require('express');

const app = express();

app.get('/', (req, res) => {
    res.send('Hello World');
});

module.exports = app;
"""

INVALID_JS_BRACES = """\
const app = express();

app.get('/', (req, res) => {
    res.send('Hello');
"""

FENCED_JS = """\
```javascript
const express = require('express');
const app = express();
module.exports = app;
```
"""


class TestJsSyntaxValidateStep:
    def test_valid_js_passes(self):
        step = JsSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(VALID_JS, ctx, Path("app.js"))
        assert result.step_name == "js_syntax_validate"
        assert result.metrics["valid"] is True

    def test_invalid_js_fails(self):
        step = JsSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(INVALID_JS_BRACES, ctx, Path("bad.js"))
        assert result.metrics["valid"] is False

    def test_python_content_fails(self):
        code = "def hello():\n    print('hi')\n"
        step = JsSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(code, ctx, Path("wrong.js"))
        assert result.metrics["valid"] is False

    def test_code_unchanged(self):
        step = JsSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        result = step(VALID_JS, ctx, Path("app.js"))
        assert result.code == VALID_JS


class TestJsRepairPipeline:
    def test_fence_strip_then_validate(self):
        fence_step = FenceStripStep()
        validate_step = JsSyntaxValidateStep()
        ctx = RepairContext(config=RepairConfig())
        fp = Path("app.js")

        r1 = fence_step(FENCED_JS, ctx, fp)
        assert r1.modified is True

        r2 = validate_step(r1.code, ctx, fp)
        assert r2.metrics["valid"] is True


class TestJsRoutingEntries:
    def test_js_syntax_route(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="app.js", message="syntax error"),
        ]
        route = route_failures(diagnostics, config)
        assert "fence_strip" in route.steps
        assert "js_syntax_validate" in route.steps

    def test_js_syntax_validate_in_factories(self):
        config = RepairConfig(repairable_categories={"syntax"})
        diagnostics = [
            Diagnostic(category="syntax", file="app.js", message="error"),
        ]
        route = route_failures(diagnostics, config)
        steps = create_steps_from_route(route)
        step_names = [s.name for s in steps]
        assert "js_syntax_validate" in step_names


class TestNodejsRepairEnabled:
    def test_repair_enabled(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        profile = NodeLanguageProfile()
        assert profile.repair_enabled is True
