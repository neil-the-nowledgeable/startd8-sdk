"""Tests for Simple → Trivial Decomposer Phase 1 (REQ-MP-1004, 1005, 1006)."""

from __future__ import annotations

from unittest import mock
from unittest.mock import MagicMock

import pytest

from startd8.complexity.models import AssemblyStrategy, RejectionReason
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.micro_prime.decomposer import (
    ClassDecomposeStrategy,
    ModerateDecomposer,
)
from startd8.micro_prime.models import (
    ElementResult,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── Enum Tests (REQ-MP-1004) ─────────────────────────────────────────


class TestAssemblyStrategyEnum:
    """Verify AssemblyStrategy enum has all required values."""

    def test_assembly_strategy_enum_values(self):
        expected = {
            "file_copy",
            "copy_and_modify",
            "template",
            "simple_decompose",
            "llm_simple",
            "llm_moderate",
            "escalate",
        }
        actual = {member.value for member in AssemblyStrategy}
        assert actual == expected

    def test_assembly_strategy_is_str_enum(self):
        assert isinstance(AssemblyStrategy.TEMPLATE, str)
        assert AssemblyStrategy.TEMPLATE == "template"


class TestRejectionReasonEnum:
    """Verify RejectionReason enum has all required values."""

    def test_rejection_reason_enum_values(self):
        expected = {
            "no_template_match",
            "skeleton_mismatch",
            "unsafe_decorator",
            "render_contract_violation",
            "syntax_error",
            "empty_output",
        }
        actual = {member.value for member in RejectionReason}
        assert actual == expected

    def test_rejection_reason_is_str_enum(self):
        assert isinstance(RejectionReason.SYNTAX_ERROR, str)
        assert RejectionReason.SYNTAX_ERROR == "syntax_error"


# ── ClassDecomposeStrategy All-Trivial Tests (REQ-MP-1005) ───────────


def _make_class_file_spec() -> tuple[ForwardElementSpec, ForwardFileSpec, ForwardManifest]:
    """Build a class element + file spec suitable for ClassDecomposeStrategy."""
    class_elem = ForwardElementSpec(
        kind=ElementKind.CLASS,
        name="MyWidget",
        bases=["BaseWidget"],
        docstring_hint="A simple widget.",
    )
    init_elem = ForwardElementSpec(
        kind=ElementKind.METHOD,
        name="__init__",
        signature=Signature(
            params=[Param(name="self"), Param(name="name", annotation="str")],
            return_annotation="None",
        ),
        parent_class="MyWidget",
        docstring_hint="Initialize the widget.",
    )
    file_spec = ForwardFileSpec(
        file="src/widgets.py",
        imports=[ForwardImportSpec(kind="import", module="base")],
        elements=[class_elem, init_elem],
    )
    manifest = ForwardManifest(
        schema_version="1.0.0",
        file_specs={"src/widgets.py": file_spec},
        contracts=[],
    )
    return class_elem, file_spec, manifest


class TestClassDecomposeAllTrivial:
    """Tests for REQ-MP-1005: all-TRIVIAL class decomposition."""

    def test_class_decompose_all_trivial_marks_deterministic(self):
        """When template_registry.is_trivial() returns True for all
        non-deterministic sub-elements, they should all be marked deterministic."""
        class_elem, file_spec, manifest = _make_class_file_spec()

        mock_registry = MagicMock()
        mock_registry.is_trivial.return_value = True

        strategy = ClassDecomposeStrategy(
            config=MicroPrimeConfig(),
            template_registry=mock_registry,
        )
        plan = strategy.plan(
            class_elem, file_spec, manifest,
            classification_reason="class definition",
        )

        assert plan is not None
        # All sub-elements should be deterministic now
        for sub in plan.sub_elements:
            assert sub.deterministic is True, (
                f"Sub-element {sub.name!r} should be deterministic"
            )

    def test_class_decompose_mixed_trivial_not_all_deterministic(self):
        """When is_trivial() returns False for one sub-element,
        non-deterministic sub-elements remain non-deterministic."""
        class_elem, file_spec, manifest = _make_class_file_spec()

        # First call (for __init__) returns False
        mock_registry = MagicMock()
        mock_registry.is_trivial.return_value = False

        strategy = ClassDecomposeStrategy(
            config=MicroPrimeConfig(),
            template_registry=mock_registry,
        )
        plan = strategy.plan(
            class_elem, file_spec, manifest,
            classification_reason="class definition",
        )

        assert plan is not None
        # class_shell is deterministic by default; __init__ should NOT be
        non_det = [s for s in plan.sub_elements if not s.deterministic]
        assert len(non_det) > 0, "At least one sub-element should remain non-deterministic"

    def test_class_decompose_no_template_registry_unchanged(self):
        """When no template_registry is passed, sub-element deterministic
        flags should remain at their default values."""
        class_elem, file_spec, manifest = _make_class_file_spec()

        strategy = ClassDecomposeStrategy(config=MicroPrimeConfig())
        plan = strategy.plan(
            class_elem, file_spec, manifest,
            classification_reason="class definition",
        )

        assert plan is not None
        # class_shell is deterministic; __init__ should NOT be
        shell = next(s for s in plan.sub_elements if s.name == "class_shell")
        assert shell.deterministic is True
        init = next(s for s in plan.sub_elements if s.name == "__init__")
        assert init.deterministic is False


# ── Template Short-Circuit in _handle_simple (REQ-MP-1006) ───────────


class TestTemplateShortCircuit:
    """Tests for template-first short-circuit in _handle_simple."""

    def test_template_short_circuit_in_handle_simple(self):
        """When template_registry.match() returns a match, _handle_simple
        should return an ElementResult with template_used=True and model='template',
        without calling Ollama."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        mock_match = MagicMock()
        mock_match.name = "property_getter"
        mock_match.code = "return self._value"

        mock_registry = MagicMock()
        mock_registry.match.return_value = mock_match

        config = MicroPrimeConfig()
        engine = MicroPrimeEngine(
            config=config,
            template_registry=mock_registry,
        )

        element = ForwardElementSpec(
            kind=ElementKind.PROPERTY,
            name="value",
            signature=Signature(
                params=[Param(name="self")],
                return_annotation="int",
            ),
            parent_class="Config",
            decorators=["property"],
        )
        file_spec = ForwardFileSpec(
            file="src/config.py",
            imports=[],
            elements=[element],
        )
        skeleton = "class Config:\n    @property\n    def value(self) -> int:\n        raise NotImplementedError\n"

        result = engine._handle_simple(
            element=element,
            file_spec=file_spec,
            skeleton=skeleton,
            contracts=[],
            file_path="src/config.py",
            reasoning="property element",
        )

        assert result.success is True
        assert result.template_used is True
        assert result.template_name == "property_getter"
        assert result.model == "template"
        assert result.code == "return self._value"
        # match() was called; no Ollama generation should have happened
        mock_registry.match.assert_called_once()

    def test_template_short_circuit_no_match_proceeds(self):
        """When match() returns None, _handle_simple should proceed to the
        Ollama generation path."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        mock_registry = MagicMock()
        mock_registry.match.return_value = None

        config = MicroPrimeConfig()
        engine = MicroPrimeEngine(
            config=config,
            template_registry=mock_registry,
        )

        element = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="compute",
            signature=Signature(
                params=[Param(name="x", annotation="int")],
                return_annotation="int",
            ),
        )
        file_spec = ForwardFileSpec(
            file="src/math_utils.py",
            imports=[],
            elements=[element],
        )
        skeleton = "def compute(x: int) -> int:\n    raise NotImplementedError\n"

        # Mock _generate_ollama to avoid actual Ollama calls
        with mock.patch.object(
            engine, "_generate_ollama", autospec=True,
            return_value=("return x * 2", 10, 5),
        ):
            result = engine._handle_simple(
                element=element,
                file_spec=file_spec,
                skeleton=skeleton,
                contracts=[],
                file_path="src/math_utils.py",
                reasoning="simple function",
            )

        # Should have proceeded past template check
        mock_registry.match.assert_called_once()
        # Result comes from Ollama path, not template
        assert result.template_used is False


# ── Decomposer Receives template_registry (wiring test) ─────────────


class TestDecomposerWiring:
    """Verify engine passes template_registry to decomposer."""

    def test_decomposer_receives_template_registry(self):
        """MicroPrimeEngine should pass its template_registry to
        ModerateDecomposer, which passes it to ClassDecomposeStrategy."""
        from startd8.micro_prime.engine import MicroPrimeEngine

        mock_registry = MagicMock()
        engine = MicroPrimeEngine(
            config=MicroPrimeConfig(),
            template_registry=mock_registry,
        )

        decomposer = engine._decomposer
        assert getattr(decomposer, "_template_registry", None) is mock_registry

        # Verify it was passed through to ClassDecomposeStrategy
        class_strategy = next(
            (s for s in decomposer._strategies if isinstance(s, ClassDecomposeStrategy)),
            None,
        )
        assert class_strategy is not None
        assert getattr(class_strategy, "_template_registry", None) is mock_registry
