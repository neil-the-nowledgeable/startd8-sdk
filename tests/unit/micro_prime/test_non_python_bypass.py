"""Tests for REQ-MLT-100/101: Non-Python file bypass in MicroPrime.

Non-Python files (Go, HTML, YAML, Dockerfile, etc.) must bypass
MicroPrime element-by-element generation and escalate to file-whole
LLM generation via the fallback code generator.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    InterfaceContract,
)
from startd8.micro_prime.engine import _is_non_python_file
from startd8.micro_prime.models import (
    EscalationReason,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── _is_non_python_file tests ──


class TestIsNonPythonFile:
    """Verify _is_non_python_file classification."""

    def test_is_non_python_file_go_not_bypassed(self) -> None:
        """Go files flow through MicroPrime (MP-P6), not bypassed."""
        assert _is_non_python_file("main.go") is False

    def test_is_non_python_file_html(self) -> None:
        assert _is_non_python_file("home.html") is True

    def test_is_non_python_file_go_mod(self) -> None:
        assert _is_non_python_file("go.mod") is True

    def test_is_non_python_file_dockerfile(self) -> None:
        assert _is_non_python_file("Dockerfile") is True

    def test_is_non_python_file_python(self) -> None:
        assert _is_non_python_file("main.py") is False

    def test_is_non_python_file_yaml(self) -> None:
        assert _is_non_python_file("config.yaml") is True

    def test_is_non_python_file_yml(self) -> None:
        assert _is_non_python_file("docker-compose.yml") is True

    def test_is_non_python_file_json(self) -> None:
        assert _is_non_python_file("package.json") is True

    def test_is_non_python_file_toml(self) -> None:
        assert _is_non_python_file("pyproject.toml") is True

    def test_is_non_python_file_makefile(self) -> None:
        assert _is_non_python_file("Makefile") is True

    def test_is_non_python_file_go_sum(self) -> None:
        assert _is_non_python_file("go.sum") is True

    def test_is_non_python_file_go_with_path_not_bypassed(self) -> None:
        """Go files flow through MicroPrime (MP-P6), not bypassed."""
        assert _is_non_python_file("src/server/main.go") is False

    def test_is_non_python_file_python_with_path(self) -> None:
        assert _is_non_python_file("src/mypackage/main.py") is False

    def test_is_non_python_file_typescript(self) -> None:
        """TypeScript has a registered NodeLanguageProfile — MicroPrime-compatible."""
        assert _is_non_python_file("index.ts") is False

    def test_is_non_python_file_proto(self) -> None:
        assert _is_non_python_file("service.proto") is True

    def test_is_non_python_file_unknown_extension(self) -> None:
        """Unknown extensions are treated as non-Python to prevent Python stub emission."""
        assert _is_non_python_file("data.xyz") is True

    def test_is_non_python_file_no_extension(self) -> None:
        """Files without extension and not in known filenames → non-Python."""
        assert _is_non_python_file("README") is True

    def test_is_non_python_file_gradle(self) -> None:
        """Gradle build files are non-Python."""
        assert _is_non_python_file("build.gradle") is True

    def test_is_non_python_file_gradle_kts(self) -> None:
        """Kotlin script Gradle files are non-Python."""
        assert _is_non_python_file("build.gradle.kts") is True

    def test_is_non_python_file_requirements_in(self) -> None:
        assert _is_non_python_file("requirements.in") is True

    def test_is_non_python_file_case_insensitive_extension(self) -> None:
        """Extensions are lowercased before comparison."""
        assert _is_non_python_file("style.CSS") is True


# ── _handle_trivial bypass tests ──


def _make_element(name: str = "main") -> ForwardElementSpec:
    """Create a minimal ForwardElementSpec for testing."""
    return ForwardElementSpec(
        kind=ElementKind.FUNCTION,
        name=name,
        signature=Signature(params=[], return_annotation="None"),
        docstring_hint="Entry point.",
    )


def _make_file_spec(file_path: str) -> ForwardFileSpec:
    """Create a minimal ForwardFileSpec."""
    return ForwardFileSpec(
        file=file_path,
        elements=[_make_element()],
    )


class TestHandleTrivialBypass:
    """Verify _handle_trivial returns escalation for non-Python files."""

    def test_trivial_non_python_returns_escalation(self) -> None:
        """Non-Python file (HTML) in _handle_trivial should not call template matching."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config)

        element = _make_element()
        file_spec = _make_file_spec("home.html")

        with patch.object(engine, "_templates") as mock_templates:
            result = engine._handle_trivial(
                element, file_spec, "", [], "home.html", "test",
            )

        # Template matching should never be called for non-Python files
        mock_templates.match.assert_not_called()

        # Result should be an escalation with NON_PYTHON_BYPASS reason
        assert result.success is False
        assert result.escalation is not None
        assert result.escalation.reason == EscalationReason.NON_PYTHON_BYPASS
        assert result.generation_strategy == "non_python_bypass"

    def test_trivial_python_still_uses_templates(self) -> None:
        """Python files should still go through template matching."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config)

        element = _make_element()
        file_spec = _make_file_spec("main.py")

        with patch.object(engine, "_templates") as mock_templates:
            # Make template match return None so it escalates to simple
            mock_templates.match.return_value = None
            with patch.object(engine, "_handle_simple") as mock_simple:
                mock_simple.return_value = MagicMock()
                engine._handle_trivial(
                    element, file_spec, "", [], "main.py", "test",
                )

        # Template matching SHOULD be called for Python files
        mock_templates.match.assert_called_once()


class TestHandleSimpleBypass:
    """Verify _handle_simple returns escalation for non-Python/non-Go files."""

    def test_simple_non_python_returns_escalation(self) -> None:
        """HTML files should still bypass MicroPrime."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config)

        element = _make_element()
        file_spec = _make_file_spec("index.html")

        result = engine._handle_simple(
            element, file_spec, "", [], "index.html", "test",
        )

        assert result.success is False
        assert result.escalation is not None
        assert result.escalation.reason == EscalationReason.NON_PYTHON_BYPASS
        assert result.generation_strategy == "non_python_bypass"
        assert result.tier == TierClassification.SIMPLE

    def test_simple_dockerfile_returns_escalation(self) -> None:
        from startd8.micro_prime.engine import MicroPrimeEngine

        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config)

        element = _make_element()
        file_spec = _make_file_spec("Dockerfile")

        result = engine._handle_simple(
            element, file_spec, "", [], "Dockerfile", "test",
        )

        assert result.success is False
        assert result.escalation is not None
        assert result.escalation.reason == EscalationReason.NON_PYTHON_BYPASS


class TestTrySimpleShortcircuitBypass:
    """Verify _try_simple_shortcircuit returns None for non-Python files."""

    def test_shortcircuit_non_python_returns_none(self) -> None:
        """Non-Python files should return None (no short-circuit), letting
        _handle_simple's own guard handle the bypass."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        config = MicroPrimeConfig(provider="ollama", model="test")
        engine = MicroPrimeEngine(config=config)

        element = _make_element()
        file_spec = _make_file_spec("config.yaml")

        with patch.object(engine, "_templates") as mock_templates:
            result = engine._try_simple_shortcircuit(
                element, file_spec, [], "config.yaml", "test",
            )

        # Should return None without calling templates
        assert result is None
        mock_templates.match.assert_not_called()


# ── _try_generate_go_mod tests ──


class TestTryGenerateGoMod:
    """Tests for REQ-MLT-103: deterministic go.mod generation."""

    def _make_generator(self, output_dir="/tmp/test-output"):
        """Create a MicroPrimeCodeGenerator with minimal config."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        config = MicroPrimeConfig(provider="ollama", model="test")
        gen = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        gen._config = config
        gen._output_dir = Path(output_dir)
        return gen

    def test_go_mod_returns_content(self):
        """go.mod file should produce valid go.mod content."""
        gen = self._make_generator()
        result = gen._try_generate_go_mod(
            "src/shippingservice/go.mod", None, {},
        )
        assert result is not None
        assert result.startswith("module ")
        assert "\ngo " in result

    def test_go_mod_infers_module_path(self):
        """Module path should be inferred from directory structure."""
        gen = self._make_generator()
        result = gen._try_generate_go_mod(
            "src/shippingservice/go.mod", None, {},
        )
        assert result is not None
        assert "src/shippingservice" in result

    def test_non_go_mod_returns_none(self):
        """Non-go.mod files should return None."""
        gen = self._make_generator()
        result = gen._try_generate_go_mod(
            "src/main.go", None, {},
        )
        assert result is None

    def test_go_mod_with_go_version(self):
        """go_version from context should be used."""
        gen = self._make_generator()
        result = gen._try_generate_go_mod(
            "src/service/go.mod", None, {"go_version": "1.22"},
        )
        assert result is not None
        assert "go 1.22" in result

    def test_html_returns_none(self):
        """HTML files should return None (not go.mod)."""
        gen = self._make_generator()
        result = gen._try_generate_go_mod(
            "templates/home.html", None, {},
        )
        assert result is None
