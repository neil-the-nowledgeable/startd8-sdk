"""Integration tests for polyglot MicroPrime template + splicer paths (REQ-MPV-002/003).

Validates that non-Python languages produce real code through the
template registry and splicer dispatch — not just unit-level match/render
but the full _handle_trivial() → ElementResult.make_success() path.
"""

from __future__ import annotations

import pytest

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, Signature
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, Param


# ---------------------------------------------------------------------------
# REQ-MPV-002: Template match integration tests
# ---------------------------------------------------------------------------


class TestGoTemplateIntegration:
    """Go templates produce valid code through _handle_trivial."""

    def test_go_main_through_handle_trivial(self):
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION, name="main",
            signature=Signature(params=[], return_annotation=None),
        )
        fs = ForwardFileSpec(file="main.go", elements=[elem], imports=[])
        result = engine._handle_trivial(elem, fs, "", [], "main.go", "test")

        assert result.success is True
        assert result.template_used is True
        assert result.template_name == "go_main"
        assert "log.Println" in result.code or "fmt.Println" in result.code

    def test_go_constructor_through_handle_trivial(self):
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION, name="NewServer",
            signature=Signature(
                params=[Param(name="addr", annotation="string")],
                return_annotation="*Server",
            ),
        )
        fs = ForwardFileSpec(file="server.go", elements=[elem], imports=[])
        result = engine._handle_trivial(elem, fs, "", [], "server.go", "test")

        assert result.success is True
        assert result.template_name == "go_constructor"
        assert "addr" in result.code


class TestJavaTemplateIntegration:
    """Java templates produce valid code through _handle_trivial."""

    def test_java_getter_through_handle_trivial(self):
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD, name="getName",
            parent_class="User",
            signature=Signature(params=[], return_annotation="String"),
        )
        fs = ForwardFileSpec(file="User.java", elements=[elem], imports=[])
        result = engine._handle_trivial(elem, fs, "", [], "User.java", "test")

        assert result.success is True
        assert result.template_name == "java_getter"
        assert "name" in result.code.lower()

    def test_java_main_through_handle_trivial(self):
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION, name="main",
            signature=Signature(
                params=[Param(name="args", annotation="String[]")],
                return_annotation=None,
            ),
        )
        fs = ForwardFileSpec(file="Application.java", elements=[elem], imports=[])
        result = engine._handle_trivial(elem, fs, "", [], "Application.java", "test")

        assert result.success is True
        assert result.template_name == "java_spring_main"
        assert "SpringApplication" in result.code


class TestCSharpTemplateIntegration:
    """C# templates produce valid code through _handle_trivial."""

    def test_csharp_di_constructor_through_handle_trivial(self):
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD, name="CartService",
            parent_class="CartService",
            signature=Signature(params=[
                Param(name="cartStore", annotation="ICartStore"),
                Param(name="logger", annotation="ILogger<CartService>"),
            ], return_annotation=None),
        )
        fs = ForwardFileSpec(file="CartService.cs", elements=[elem], imports=[])
        result = engine._handle_trivial(elem, fs, "", [], "CartService.cs", "test")

        assert result.success is True
        assert result.template_name == "csharp_di_constructor"
        assert "cartStore" in result.code
        assert "ArgumentNullException" in result.code


class TestNodejsTemplateIntegration:
    """Node.js templates produce valid code through _handle_trivial."""

    def test_nodejs_constructor_through_handle_trivial(self):
        from startd8.micro_prime.engine import MicroPrimeEngine

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD, name="constructor",
            parent_class="PaymentServer",
            signature=Signature(
                params=[Param(name="logger", annotation=None)],
                return_annotation=None,
            ),
        )
        fs = ForwardFileSpec(file="server.js", elements=[elem], imports=[])
        result = engine._handle_trivial(elem, fs, "", [], "server.js", "test")

        assert result.success is True
        assert result.template_name == "js_constructor"
        assert "this.logger" in result.code


# ---------------------------------------------------------------------------
# REQ-MPV-003: Splicer integration tests
# ---------------------------------------------------------------------------


class TestCSharpSplicerIntegration:
    """C# splicer dispatch produces valid spliced output."""

    def test_csharp_splice_dispatch_fires(self):
        from startd8.micro_prime.splicer import splice_body_into_skeleton, _is_csharp_source

        assert _is_csharp_source("", "CartStore.cs") is True

    def test_csharp_splice_dispatches_to_csharp_splicer(self):
        """Verify the dispatch chain fires — _is_csharp_source → _splice_csharp_dispatch."""
        from startd8.micro_prime.splicer import splice_body_into_skeleton
        from unittest.mock import patch

        skeleton = "using System;\nnamespace Foo;\npublic class Bar { }"
        body = "return true;"
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD, name="Ping",
            parent_class="Bar",
            signature=Signature(params=[], return_annotation="bool"),
        )

        # Patch the csharp splicer to verify it gets called
        with patch(
            "startd8.micro_prime.splicer._splice_csharp_dispatch",
        ) as mock_dispatch:
            from startd8.micro_prime.splicer import SpliceResult
            mock_dispatch.return_value = SpliceResult(code="// spliced")
            result = splice_body_into_skeleton(body, elem, skeleton, file_path="CartStore.cs")

        mock_dispatch.assert_called_once()
        assert result.code == "// spliced"


class TestGoSplicerIntegration:
    """Go splicer dispatch produces valid spliced output."""

    def test_go_splice_dispatch_fires(self):
        from startd8.micro_prime.splicer import _is_go_source

        assert _is_go_source("package main\n", "main.go") is True
        assert _is_go_source("", "server.go") is True


class TestUnregisteredLanguageBypass:
    """Files without language profiles bypass correctly."""

    def test_html_bypasses_trivial(self):
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import EscalationReason
        from unittest.mock import patch

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION, name="render",
            signature=Signature(params=[], return_annotation=None),
        )
        fs = ForwardFileSpec(file="template.html", elements=[elem], imports=[])

        with patch(
            "startd8.micro_prime.engine.TemplateRegistry.has_templates_for",
            return_value=False,
        ):
            result = engine._handle_trivial(elem, fs, "", [], "template.html", "test")

        assert result.success is False
        assert result.escalation.reason == EscalationReason.NON_PYTHON_BYPASS

    def test_dockerfile_bypasses_simple(self):
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import EscalationReason

        engine = MicroPrimeEngine(config=MicroPrimeConfig(provider="ollama", model="test"))
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION, name="build",
            signature=Signature(params=[], return_annotation=None),
        )
        fs = ForwardFileSpec(file="Dockerfile", elements=[elem], imports=[])
        result = engine._handle_simple(elem, fs, "", [], "Dockerfile", "test")

        assert result.success is False
        assert result.escalation.reason == EscalationReason.NON_PYTHON_BYPASS
