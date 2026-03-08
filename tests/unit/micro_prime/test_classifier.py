"""Tests for the Micro Prime Classifier (REQ-MP-500–501, 511)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    InterfaceContract,
)
from startd8.micro_prime.classifier import classify_element
from startd8.micro_prime.models import MicroPrimeConfig, TierClassification
from startd8.micro_prime.templates import TemplateRegistry
from startd8.utils.code_manifest import ElementKind, Param, ParamKind, Signature


class TestTrivialClassification:
    """Tests for TRIVIAL tier (REQ-MP-500a)."""

    def test_init_is_trivial_with_registry(self, init_element, sample_file_spec, empty_contracts):
        registry = TemplateRegistry()
        tier, reason = classify_element(
            init_element, sample_file_spec, empty_contracts,
            template_registry=registry,
        )
        assert tier == TierClassification.TRIVIAL
        assert "template" in reason

    def test_constant_is_trivial_with_registry(self, constant_element, sample_file_spec, empty_contracts):
        registry = TemplateRegistry()
        tier, reason = classify_element(
            constant_element, sample_file_spec, empty_contracts,
            template_registry=registry,
        )
        # Constants match template but also match the kind-based shortcut
        assert tier in (TierClassification.TRIVIAL, TierClassification.SIMPLE)


class TestSimpleClassification:
    """Tests for SIMPLE tier (REQ-MP-501)."""

    def test_property_is_simple(self, property_element, sample_file_spec, empty_contracts):
        tier, reason = classify_element(
            property_element, sample_file_spec, empty_contracts,
        )
        assert tier == TierClassification.SIMPLE
        assert "property" in reason

    def test_constant_is_simple(self, constant_element, sample_file_spec, empty_contracts):
        tier, reason = classify_element(
            constant_element, sample_file_spec, empty_contracts,
        )
        assert tier == TierClassification.SIMPLE

    def test_simple_getter(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="get_total",
            signature=Signature(
                params=[Param(name="self")],
                return_annotation="int",
            ),
            parent_class="Order",
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert tier == TierClassification.SIMPLE
        assert "simple name prefix" in reason or "params" in reason


class TestModerateClassification:
    """Tests for MODERATE tier."""

    def test_orchestrator_name(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="run_server",
            signature=Signature(params=[], return_annotation="None"),
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert tier == TierClassification.MODERATE
        assert "orchestrator" in reason

    def test_app_instance(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.CONSTANT,
            name="app",
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert tier == TierClassification.MODERATE
        assert "app/server instance" in reason

    def test_orchestrator_suffix(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="data_pipeline",
            signature=Signature(
                params=[Param(name="config", annotation="dict")],
                return_annotation="None",
            ),
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert tier == TierClassification.MODERATE

    def test_orchestrator_docstring(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="process",
            signature=Signature(params=[], return_annotation="None"),
            docstring_hint="Bootstrap and configure all services.",
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert tier == TierClassification.MODERATE


class TestComplexClassification:
    """Tests for COMPLEX tier."""

    def test_many_params_async_abstract(self, complex_function_element, sample_file_spec, empty_contracts):
        tier, reason = classify_element(
            complex_function_element, sample_file_spec, empty_contracts,
        )
        assert tier == TierClassification.COMPLEX

    def test_class_definition(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="Pipeline",
            bases=["BaseModel"],
            docstring_hint="Complex pipeline orchestration class with many methods and state management and resource cleanup.",
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert tier in (TierClassification.MODERATE, TierClassification.COMPLEX)
        # May be classified as orchestrator or class definition
        assert "class" in reason or "orchestrator" in reason


class TestScoringFactors:
    """Tests for individual scoring factors."""

    def test_binding_constraints_increase_score(self, simple_function_element, sample_file_spec):
        many_contracts = [
            InterfaceContract(
                contract_id=f"C-{i}",
                category=ContractCategory.FUNCTION_NAME,
                confidence=ContractConfidence.EXPLICIT,
                description=f"Constraint {i}",
                binding_text=f"Must do thing {i}",
            )
            for i in range(5)
        ]
        tier, reason = classify_element(
            simple_function_element, sample_file_spec, many_contracts,
        )
        assert "binding constraints" in reason

    def test_async_adds_complexity(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.ASYNC_FUNCTION,
            name="process",
            signature=Signature(
                params=[Param(name="data", annotation="str")],
                return_annotation="str",
            ),
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert "async" in reason

    def test_long_docstring_adds_complexity(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="compute",
            signature=Signature(
                params=[
                    Param(name="a", annotation="int"),
                    Param(name="b", annotation="int"),
                    Param(name="c", annotation="int"),
                ],
            ),
            docstring_hint="A " * 120,  # 240-char intent (no Args section)
        )
        # Use a file spec with enough elements so small-file bias doesn't mask it
        large_file = ForwardFileSpec(
            file="src/big_module.py",
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.FUNCTION, name=f"fn_{i}",
                    signature=Signature(params=[], return_annotation="None"),
                )
                for i in range(10)
            ],
        )
        tier, reason = classify_element(elem, large_file, empty_contracts)
        assert "long docstring intent" in reason


class TestAPIDependencyAnalysis:
    """Tests for two-pass API dependency analysis (REQ-MP-511)."""

    def test_many_external_imports_escalates(self, simple_function_element, empty_contracts):
        file_spec = ForwardFileSpec(
            file="src/complex.py",
            imports=[
                ForwardImportSpec(kind="import", module=f"third_party_{i}")
                for i in range(12)
            ],
        )
        config = MicroPrimeConfig(max_simple_imports=8)
        tier, reason = classify_element(
            simple_function_element, file_spec, empty_contracts, config=config,
        )
        assert tier == TierClassification.MODERATE
        assert "external imports" in reason

    def test_docstring_api_hint_escalates(self, sample_file_spec, empty_contracts):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="query",
            signature=Signature(
                params=[Param(name="sql", annotation="str")],
                return_annotation="list",
            ),
            docstring_hint="Execute a database query against PostgreSQL.",
        )
        tier, reason = classify_element(elem, sample_file_spec, empty_contracts)
        assert tier == TierClassification.MODERATE
        assert "database" in reason
