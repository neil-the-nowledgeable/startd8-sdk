"""Tests for Phase 3: Function-body decomposition via clause-to-template mapping."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, InterfaceContract
from startd8.micro_prime.clause_mapper import (
    ClauseMapping,
    FunctionBodyDecomposer,
    map_all_clauses,
    map_clause_to_template,
)
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


# ── Helpers ──────────────────────────────────────────────────────────


def _make_element(
    name: str = "my_func",
    kind: ElementKind = ElementKind.FUNCTION,
    docstring_hint: str | None = None,
    parent_class: str | None = None,
    decorators: list[str] | None = None,
    params: list[Param] | None = None,
) -> ForwardElementSpec:
    # ForwardElementSpec requires signature for FUNCTION/METHOD kinds
    if params is not None:
        sig = Signature(params=params, return_annotation=None)
    elif kind in (
        ElementKind.FUNCTION, ElementKind.METHOD,
        ElementKind.ASYNC_FUNCTION, ElementKind.ASYNC_METHOD,
    ):
        sig = Signature(params=[], return_annotation=None)
    else:
        sig = None
    return ForwardElementSpec(
        kind=kind,
        name=name,
        signature=sig,
        docstring_hint=docstring_hint,
        parent_class=parent_class,
        decorators=decorators or [],
    )


def _make_file_spec(elements: list[ForwardElementSpec] | None = None) -> ForwardFileSpec:
    return ForwardFileSpec(
        file="test.py",
        elements=elements or [],
    )


# ── Clause Mapper Tests ─────────────────────────────────────────────


class TestMapClauseToTemplate:
    """Tests for individual clause-to-template mapping."""

    def test_validate_clause_maps_to_simple_validation(self) -> None:
        element = _make_element(name="process", parent_class=None)
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        result = map_clause_to_template(
            "validate the input parameter before processing",
            element, file_spec, registry,
        )

        assert result is not None
        assert result.template_name == "simple_validation"
        assert result.synthetic_spec.name == "validate_input"
        assert result.confidence > 0

    def test_check_clause_maps_to_simple_validation(self) -> None:
        element = _make_element(name="process")
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        result = map_clause_to_template(
            "check the value is not empty before use",
            element, file_spec, registry,
        )

        assert result is not None
        assert result.template_name == "simple_validation"
        assert result.synthetic_spec.name == "validate_value"

    def test_init_clause_maps_to_dunder_init(self) -> None:
        element = _make_element(
            name="__init__",
            kind=ElementKind.METHOD,
            parent_class="MyClass",
            params=[
                Param(name="self", kind=ParamKind.POSITIONAL),
                Param(name="name", kind=ParamKind.POSITIONAL),
            ],
        )
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        result = map_clause_to_template(
            "initialize and store the name parameter",
            element, file_spec, registry,
        )

        assert result is not None
        assert result.template_name == "dunder___init__"
        assert result.synthetic_spec.name == "__init__"

    def test_repr_clause_maps_to_dunder_repr(self) -> None:
        element = _make_element(
            name="display",
            kind=ElementKind.METHOD,
            parent_class="MyClass",
        )
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        result = map_clause_to_template(
            "return string representation of the object",
            element, file_spec, registry,
        )

        assert result is not None
        assert result.template_name == "dunder___repr__"

    def test_unknown_clause_returns_none(self) -> None:
        element = _make_element(name="process")
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        result = map_clause_to_template(
            "do something complex with external API and retry logic",
            element, file_spec, registry,
        )

        assert result is None

    def test_unsafe_synthetic_name_rejected(self) -> None:
        """Clause producing a name with non-identifier chars → None."""
        element = _make_element(name="process")
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        # "for" is a Python keyword — _is_safe_identifier rejects it
        result = map_clause_to_template(
            "validate for correctness in all cases",
            element, file_spec, registry,
        )

        # "for" is extracted as param name but is a keyword → rejected
        assert result is None


class TestMapAllClauses:
    """Tests for all-or-nothing clause mapping."""

    def test_all_clauses_map_successfully(self) -> None:
        element = _make_element(
            name="process",
            params=[
                Param(name="value", kind=ParamKind.POSITIONAL),
            ],
        )
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        clauses = [
            "validate the value before processing",
            "check the input is not empty",
        ]

        result = map_all_clauses(clauses, element, file_spec, registry)
        assert result is not None
        assert len(result) == 2
        assert all(isinstance(m, ClauseMapping) for m in result)

    def test_one_unmappable_clause_returns_none(self) -> None:
        element = _make_element(name="process")
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        clauses = [
            "validate the input parameter for safety",
            "do something complex with external API and retry logic",
        ]

        result = map_all_clauses(clauses, element, file_spec, registry)
        assert result is None

    def test_empty_clauses_returns_none(self) -> None:
        element = _make_element(name="process")
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)

        result = map_all_clauses([], element, file_spec, registry)
        # Empty list → all succeeded (vacuously), returns empty list
        assert result is not None
        assert len(result) == 0


# ── FunctionBodyDecomposer Tests ─────────────────────────────────────


class TestFunctionBodyDecomposer:
    """Tests for FunctionBodyDecomposer.try_decompose."""

    def test_decompose_two_clause_function(self) -> None:
        element = _make_element(
            name="process_data",
            kind=ElementKind.FUNCTION,
            docstring_hint=(
                "1. validate the input parameter before processing; "
                "2. verify the data is not corrupted"
            ),
            params=[
                Param(name="input", kind=ParamKind.POSITIONAL),
                Param(name="data", kind=ParamKind.POSITIONAL),
            ],
        )
        file_spec = _make_file_spec()
        registry = TemplateRegistry(enabled=True)
        decomposer = FunctionBodyDecomposer(
            template_registry=registry,
            confidence_threshold=0.5,
        )

        result = decomposer.try_decompose(element, file_spec, [])

        assert result is not None
        assert "raise ValueError" in result
        assert "input" in result

    def test_decompose_non_function_rejected(self) -> None:
        element = _make_element(
            name="MyClass",
            kind=ElementKind.CLASS,
            docstring_hint="1. validate input; 2. check output",
        )
        file_spec = _make_file_spec()
        decomposer = FunctionBodyDecomposer(
            template_registry=TemplateRegistry(enabled=True),
        )

        result = decomposer.try_decompose(element, file_spec, [])
        assert result is None

    def test_decompose_no_docstring_rejected(self) -> None:
        element = _make_element(
            name="my_func",
            kind=ElementKind.FUNCTION,
            docstring_hint=None,
        )
        file_spec = _make_file_spec()
        decomposer = FunctionBodyDecomposer(
            template_registry=TemplateRegistry(enabled=True),
        )

        result = decomposer.try_decompose(element, file_spec, [])
        assert result is None

    def test_decompose_single_clause_rejected(self) -> None:
        element = _make_element(
            name="my_func",
            kind=ElementKind.FUNCTION,
            docstring_hint="validate the input parameter for safety",
        )
        file_spec = _make_file_spec()
        decomposer = FunctionBodyDecomposer(
            template_registry=TemplateRegistry(enabled=True),
        )

        result = decomposer.try_decompose(element, file_spec, [])
        assert result is None

    def test_decompose_decorated_function_rejected(self) -> None:
        element = _make_element(
            name="my_func",
            kind=ElementKind.FUNCTION,
            docstring_hint=(
                "1. validate the input parameter before processing; "
                "2. check the output for correctness and validity"
            ),
            decorators=["@app.route('/api')"],
        )
        file_spec = _make_file_spec()
        decomposer = FunctionBodyDecomposer(
            template_registry=TemplateRegistry(enabled=True),
        )

        result = decomposer.try_decompose(element, file_spec, [])
        assert result is None

    def test_decompose_safe_decorator_allowed(self) -> None:
        element = _make_element(
            name="process",
            kind=ElementKind.FUNCTION,
            docstring_hint=(
                "1. validate the input parameter before processing; "
                "2. verify the data is not corrupted"
            ),
            decorators=["@staticmethod"],
            params=[
                Param(name="input", kind=ParamKind.POSITIONAL),
                Param(name="data", kind=ParamKind.POSITIONAL),
            ],
        )
        file_spec = _make_file_spec()
        decomposer = FunctionBodyDecomposer(
            template_registry=TemplateRegistry(enabled=True),
            confidence_threshold=0.5,
        )

        result = decomposer.try_decompose(element, file_spec, [])
        assert result is not None

    def test_decompose_unmappable_clause_returns_none(self) -> None:
        element = _make_element(
            name="my_func",
            kind=ElementKind.FUNCTION,
            docstring_hint=(
                "1. validate the input parameter for safety; "
                "2. do something complex with external API retry"
            ),
        )
        file_spec = _make_file_spec()
        decomposer = FunctionBodyDecomposer(
            template_registry=TemplateRegistry(enabled=True),
        )

        result = decomposer.try_decompose(element, file_spec, [])
        assert result is None

    def test_decompose_result_is_valid_python(self) -> None:
        """Assembled output must pass ast.parse."""
        import ast

        element = _make_element(
            name="process_data",
            kind=ElementKind.FUNCTION,
            docstring_hint=(
                "1. validate the input parameter before processing; "
                "2. verify the data is not corrupted"
            ),
            params=[
                Param(name="input", kind=ParamKind.POSITIONAL),
                Param(name="data", kind=ParamKind.POSITIONAL),
            ],
        )
        file_spec = _make_file_spec()
        decomposer = FunctionBodyDecomposer(
            template_registry=TemplateRegistry(enabled=True),
            confidence_threshold=0.5,
        )

        result = decomposer.try_decompose(element, file_spec, [])
        assert result is not None

        # Wrap in function def to validate as body
        code = f"def _check():\n    {result.replace(chr(10), chr(10) + '    ')}"
        ast.parse(code)


# ── Engine Integration Tests ─────────────────────────────────────────


class TestEngineIntegration:
    """Tests for FunctionBodyDecomposer integration in MicroPrimeEngine."""

    def test_simple_function_body_decompose_zero_llm(self) -> None:
        """With enable_simple_decomposer=True, decomposable SIMPLE functions
        should produce code with zero Ollama calls."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig

        config = MicroPrimeConfig(
            enable_simple_decomposer=True,
            simple_decomposer_confidence_threshold=0.5,
            templates_enabled=True,
        )
        engine = MicroPrimeEngine(config=config)

        element = _make_element(
            name="process_data",
            kind=ElementKind.FUNCTION,
            docstring_hint=(
                "1. validate the input parameter before processing; "
                "2. verify the data is not corrupted"
            ),
            params=[
                Param(name="input", kind=ParamKind.POSITIONAL),
                Param(name="data", kind=ParamKind.POSITIONAL),
            ],
        )
        file_spec = _make_file_spec([element])

        # Mock Ollama so we can verify it's NOT called
        with patch.object(engine, "_generate_ollama", autospec=True) as mock_ollama:
            result = engine._handle_simple(
                element, file_spec, "def process_data(input, data):\n    raise NotImplementedError",
                [], "test.py", "simple",
            )

        assert result.success is True
        assert result.template_used is True
        assert result.template_name == "function_body_decompose"
        assert result.model == "template"
        mock_ollama.assert_not_called()

    def test_simple_function_body_decompose_disabled(self) -> None:
        """With enable_simple_decomposer=False, decomposer is not invoked."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig

        config = MicroPrimeConfig(
            enable_simple_decomposer=False,
            templates_enabled=True,
        )
        engine = MicroPrimeEngine(config=config)

        assert getattr(engine, "_function_body_decomposer", None) is None

    def test_simple_function_body_decompose_fallback_to_ollama(self) -> None:
        """When decomposer returns None, Ollama should be called."""
        from startd8.micro_prime.engine import MicroPrimeEngine
        from startd8.micro_prime.models import MicroPrimeConfig

        config = MicroPrimeConfig(
            enable_simple_decomposer=True,
            simple_decomposer_confidence_threshold=0.5,
            templates_enabled=True,
        )
        engine = MicroPrimeEngine(config=config)

        # Element with unmappable clauses — decomposer will return None
        element = _make_element(
            name="complex_func",
            kind=ElementKind.FUNCTION,
            docstring_hint=(
                "1. validate the input parameter for safety; "
                "2. do something complex with external API retry logic"
            ),
        )
        file_spec = _make_file_spec([element])

        # Mock Ollama to return code
        with patch.object(
            engine, "_generate_ollama", autospec=True,
            return_value=("return True", 10, 5, "stop"),
        ) as mock_ollama:
            result = engine._handle_simple(
                element, file_spec,
                "def complex_func():\n    raise NotImplementedError",
                [], "test.py", "simple",
            )

        # Decomposer failed → Ollama was called
        mock_ollama.assert_called_once()
        assert result.template_name != "function_body_decompose"
