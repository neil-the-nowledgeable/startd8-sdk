"""Tests for TodoUncommentStep repair step (REQ-TCW-253)."""

from pathlib import Path

import pytest

from startd8.repair.models import ElementContext, RepairContext
from startd8.repair.steps.todo_uncomment import TodoUncommentStep
from startd8.validators.todo_scanner import uncomment_block


# ---------------------------------------------------------------------------
# uncomment_block() utility tests
# ---------------------------------------------------------------------------

class TestUncommentBlock:
    """Test the shared uncomment_block() utility."""

    def test_python_comment_block(self):
        code = (
            "def setup():\n"
            "    # TODO: uncomment when ready\n"
            "    # import otel\n"
            "    # metrics = otel.get_metrics()\n"
            "    # metrics.init()\n"
            "    pass\n"
        )
        result, count = uncomment_block(code, language="python")
        assert count == 1
        assert "import otel" in result
        assert "metrics = otel.get_metrics()" in result
        assert "metrics.init()" in result
        assert "# TODO" not in result

    def test_go_comment_block(self):
        code = (
            "func initMetrics() {\n"
            "    // TODO: uncomment instrumentation\n"
            "    // stats := otel.NewMeterProvider()\n"
            "    // stats.RegisterCallback(callback)\n"
            "    // meter := stats.Meter(\"service\")\n"
            "}\n"
        )
        result, count = uncomment_block(code, language="go")
        assert count == 1
        assert 'stats := otel.NewMeterProvider()' in result
        assert "// TODO" not in result

    def test_java_comment_block(self):
        code = (
            "public void initTracing() {\n"
            "    // TODO: enable tracing\n"
            "    // Tracer tracer = GlobalTracer.get();\n"
            "    // Span span = tracer.buildSpan(\"op\").start();\n"
            "    // span.finish();\n"
            "}\n"
        )
        result, count = uncomment_block(code, language="java")
        assert count == 1
        assert "Tracer tracer = GlobalTracer.get();" in result

    def test_no_blocks_found(self):
        code = "def foo():\n    # TODO: implement later\n    pass\n"
        result, count = uncomment_block(code, language="python")
        assert count == 0
        assert result == code

    def test_short_block_not_uncommented(self):
        """Blocks with < 3 lines should not be uncommented."""
        code = (
            "def foo():\n"
            "    # TODO: fix\n"
            "    # return 42\n"
            "    pass\n"
        )
        result, count = uncomment_block(code, language="python")
        assert count == 0

    def test_non_code_comments_not_uncommented(self):
        """Comment blocks without code-like content should be skipped."""
        code = (
            "def foo():\n"
            "    # TODO: think about this\n"
            "    # This is just a note\n"
            "    # about how things work\n"
            "    # in the system design\n"
            "    pass\n"
        )
        result, count = uncomment_block(code, language="python")
        assert count == 0

    def test_preserves_surrounding_code(self):
        code = (
            "import os\n"
            "\n"
            "def before():\n"
            "    return 1\n"
            "\n"
            "def setup():\n"
            "    # TODO: uncomment\n"
            "    # x = create_thing()\n"
            "    # y = x.configure(a=1)\n"
            "    # z = y.start()\n"
            "    pass\n"
            "\n"
            "def after():\n"
            "    return 2\n"
        )
        result, count = uncomment_block(code, language="python")
        assert count == 1
        assert "import os" in result
        assert "def before():" in result
        assert "def after():" in result
        assert "return 2" in result

    def test_multiple_blocks_in_same_file(self):
        """R1 regression: multi-block files must not corrupt indices."""
        code = (
            "def init_metrics():\n"
            "    # TODO: enable metrics\n"
            "    # meter = get_meter()\n"
            "    # meter.register(cb)\n"
            "    # meter.start()\n"
            "    pass\n"
            "\n"
            "def init_tracing():\n"
            "    # TODO: enable tracing\n"
            "    # tracer = get_tracer()\n"
            "    # tracer.configure(opt)\n"
            "    # tracer.start()\n"
            "    pass\n"
        )
        result, count = uncomment_block(code, language="python")
        assert count == 2
        assert "meter = get_meter()" in result
        assert "tracer = get_tracer()" in result
        assert "# TODO" not in result
        # Both functions should still be present
        assert "def init_metrics():" in result
        assert "def init_tracing():" in result


# ---------------------------------------------------------------------------
# TodoUncommentStep repair step tests
# ---------------------------------------------------------------------------

class TestTodoUncommentStep:
    """Test the repair step wrapper."""

    def test_step_name(self):
        step = TodoUncommentStep()
        assert step.name == "todo_uncomment"

    def test_step_uncomments_python(self):
        step = TodoUncommentStep()
        code = (
            "def setup():\n"
            "    # TODO: uncomment\n"
            "    # metrics = get_metrics()\n"
            "    # metrics.register(callback)\n"
            "    # metrics.start()\n"
            "    pass\n"
        )
        ctx = RepairContext(config=None, element_context=None)
        result = step(code, ctx, Path("test.py"))
        assert result.modified
        assert result.metrics["blocks_uncommented"] == 1
        assert "metrics = get_metrics()" in result.code

    def test_step_uncomments_go(self):
        step = TodoUncommentStep()
        code = (
            "func init() {\n"
            "    // TODO: enable\n"
            "    // provider := otel.NewProvider()\n"
            "    // provider.Set(option)\n"
            "    // provider.Start()\n"
            "}\n"
        )
        ctx = RepairContext(config=None, element_context=None)
        result = step(code, ctx, Path("main.go"))
        assert result.modified
        assert result.metrics["blocks_uncommented"] == 1

    def test_step_no_op_when_no_todos(self):
        step = TodoUncommentStep()
        code = "def foo():\n    return 42\n"
        ctx = RepairContext(config=None, element_context=None)
        result = step(code, ctx, Path("test.py"))
        assert not result.modified
        assert result.metrics["blocks_uncommented"] == 0
        assert result.code == code

    def test_step_infers_language_from_extension(self):
        step = TodoUncommentStep()
        code = (
            "public void init() {\n"
            "    // TODO: enable\n"
            "    // Tracer t = GlobalTracer.get();\n"
            "    // Span s = t.buildSpan(\"x\").start();\n"
            "    // s.finish();\n"
            "}\n"
        )
        ctx = RepairContext(config=None, element_context=None)
        result = step(code, ctx, Path("Service.java"))
        assert result.modified
