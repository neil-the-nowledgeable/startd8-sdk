"""End-to-end integration tests for the Micro Prime pipeline.

Tests the full flow: manifest → classify → template/generate → repair → splice → validate.
Uses mock Ollama responses for deterministic testing.
"""

from __future__ import annotations

import ast
from unittest.mock import patch

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
)
from startd8.micro_prime import (
    MicroPrimeConfig,
    MicroPrimeEngine,
    TierClassification,
)
from startd8.micro_prime.metrics import MetricsCollector, generate_cost_report
from startd8.utils.code_manifest import ElementKind, Param, Signature


@pytest.fixture
def e2e_manifest():
    """A realistic manifest for E2E testing."""
    return ForwardManifest(
        schema_version="1.0.0",
        file_specs={
            "src/mypackage/models.py": ForwardFileSpec(
                file="src/mypackage/models.py",
                imports=[
                    ForwardImportSpec(kind="from", module="dataclasses", names=["dataclass"]),
                    ForwardImportSpec(kind="from", module="typing", names=["Optional"]),
                ],
                elements=[
                    # TRIVIAL: __init__ (template)
                    ForwardElementSpec(
                        kind=ElementKind.METHOD,
                        name="__init__",
                        signature=Signature(
                            params=[
                                Param(name="self"),
                                Param(name="name", annotation="str"),
                                Param(name="age", annotation="int"),
                            ],
                            return_annotation="None",
                        ),
                        parent_class="Person",
                    ),
                    # TRIVIAL: __repr__ (template)
                    ForwardElementSpec(
                        kind=ElementKind.METHOD,
                        name="__repr__",
                        signature=Signature(
                            params=[Param(name="self")],
                            return_annotation="str",
                        ),
                        parent_class="Person",
                    ),
                    # TRIVIAL: constant (template)
                    ForwardElementSpec(
                        kind=ElementKind.CONSTANT,
                        name="MAX_AGE",
                        signature=Signature(params=[], return_annotation="int"),
                    ),
                    # SIMPLE: property (no LLM needed for classifier, but
                    # would use LLM if templates disabled)
                    ForwardElementSpec(
                        kind=ElementKind.PROPERTY,
                        name="full_name",
                        signature=Signature(
                            params=[Param(name="self")],
                            return_annotation="str",
                        ),
                        parent_class="Person",
                        decorators=["property"],
                    ),
                    # MODERATE: orchestrator (escalated)
                    ForwardElementSpec(
                        kind=ElementKind.FUNCTION,
                        name="run_server",
                        signature=Signature(
                            params=[],
                            return_annotation="None",
                        ),
                        docstring_hint="Bootstrap and start the application server.",
                    ),
                ],
            ),
        },
        contracts=[],
    )


@pytest.fixture
def e2e_skeleton():
    """A matching skeleton for E2E testing."""
    return '''# [STARTD8-SKELETON]
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


MAX_AGE: int = ...  # STARTD8_AUTO_STUB


class Person:
    """A person model."""

    def __init__(self, name: str, age: int) -> None:
        """Initialize Person."""
        raise NotImplementedError

    def __repr__(self) -> str:
        raise NotImplementedError

    @property
    def full_name(self) -> str:
        """Full name."""
        raise NotImplementedError


def run_server() -> None:
    """Bootstrap and start the application server."""
    raise NotImplementedError
'''


class TestE2ETemplateFlow:
    """E2E test: TRIVIAL elements flow through templates without LLM."""

    def test_trivial_elements_handled_by_templates(self, e2e_manifest, e2e_skeleton):
        engine = MicroPrimeEngine()
        skeletons = {"src/mypackage/models.py": e2e_skeleton}
        result = engine.process_seed(e2e_manifest, skeletons)

        assert result.total_count == 5

        # Check individual results
        fr = result.file_results[0]
        results_by_name = {er.element_name: er for er in fr.element_results}

        # __init__ should be TRIVIAL with template
        init_result = results_by_name["__init__"]
        assert init_result.tier == TierClassification.TRIVIAL
        assert init_result.success is True
        assert init_result.template_used is True
        assert "self.name = name" in init_result.code

        # __repr__ should be TRIVIAL with template
        repr_result = results_by_name["__repr__"]
        assert repr_result.tier == TierClassification.TRIVIAL
        assert repr_result.success is True

        # MAX_AGE should be TRIVIAL with template
        const_result = results_by_name["MAX_AGE"]
        assert const_result.tier == TierClassification.TRIVIAL
        assert const_result.success is True
        assert const_result.template_used is True

        # full_name is SIMPLE (property) but template should handle it
        prop_result = results_by_name["full_name"]
        assert prop_result.tier == TierClassification.TRIVIAL
        assert prop_result.success is True

        # run_server should be MODERATE (escalated)
        server_result = results_by_name["run_server"]
        assert server_result.tier == TierClassification.MODERATE
        assert server_result.success is False
        assert server_result.escalation is not None

    def test_filled_skeleton_is_valid_python(self, e2e_manifest, e2e_skeleton):
        engine = MicroPrimeEngine()
        skeletons = {"src/mypackage/models.py": e2e_skeleton}
        result = engine.process_seed(e2e_manifest, skeletons)
        fr = result.file_results[0]

        # The filled skeleton should parse (some stubs remain for escalated elements)
        if fr.filled_skeleton:
            try:
                ast.parse(fr.filled_skeleton)
            except SyntaxError as e:
                pytest.fail(f"Filled skeleton has syntax error: {e}")


class TestE2ECostReport:
    """E2E test: Cost report generation."""

    def test_cost_report_from_seed(self, e2e_manifest, e2e_skeleton):
        config = MicroPrimeConfig()
        engine = MicroPrimeEngine(config=config)
        skeletons = {"src/mypackage/models.py": e2e_skeleton}
        seed_result = engine.process_seed(e2e_manifest, skeletons)

        report = generate_cost_report(seed_result, config)
        assert report.total_elements == 5
        assert report.template_count >= 3  # __init__, __repr__, MAX_AGE
        assert report.escalated_count >= 1  # run_server
        assert report.success_rate > 0.5


class TestE2EMetricsCollection:
    """E2E test: Metrics collection during engine run."""

    def test_metrics_recorded_for_all_elements(self, e2e_manifest, e2e_skeleton):
        collector = MetricsCollector()
        engine = MicroPrimeEngine(metrics_collector=collector)
        skeletons = {"src/mypackage/models.py": e2e_skeleton}
        engine.process_seed(e2e_manifest, skeletons)

        assert len(collector.metrics) == 5
        names = {m.element_name for m in collector.metrics}
        assert "__init__" in names
        assert "__repr__" in names
        assert "MAX_AGE" in names
        assert "full_name" in names
        assert "run_server" in names


@pytest.mark.integration
class TestE2EWithMockOllama:
    """E2E test with mocked Ollama for SIMPLE element generation."""

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_simple_element_full_pipeline(self, mock_generate, e2e_manifest, e2e_skeleton):
        """Test SIMPLE tier through prompt → generate → repair → splice."""
        # Configure the manifest to have a SIMPLE element
        file_spec = e2e_manifest.file_specs["src/mypackage/models.py"]
        simple_elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="get_greeting",
            signature=Signature(
                params=[Param(name="name", annotation="str")],
                return_annotation="str",
            ),
            docstring_hint="Return a greeting for the name.",
        )
        # Add to file spec elements
        new_elements = list(file_spec.elements) + [simple_elem]
        new_file_spec = file_spec.model_copy(update={"elements": new_elements})
        e2e_manifest.file_specs["src/mypackage/models.py"] = new_file_spec

        # Add stub to skeleton
        skeleton = e2e_skeleton + '\ndef get_greeting(name: str) -> str:\n    """Return a greeting for the name."""\n    raise NotImplementedError\n'

        # Mock Ollama response
        mock_generate.return_value = (
            'def get_greeting(name: str) -> str:\n    return f"Hello, {name}!"',
            80,
            40,
            "stop",
        )

        config = MicroPrimeConfig(templates_enabled=True)
        engine = MicroPrimeEngine(config=config)
        skeletons = {"src/mypackage/models.py": skeleton}
        seed_result = engine.process_seed(e2e_manifest, skeletons)

        fr = seed_result.file_results[0]
        results_by_name = {er.element_name: er for er in fr.element_results}

        greeting_result = results_by_name["get_greeting"]
        assert greeting_result.tier == TierClassification.SIMPLE
        assert greeting_result.success is True
        assert greeting_result.input_tokens == 80
        assert greeting_result.output_tokens == 40
