"""Tests for the Micro Prime Engine."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.micro_prime.engine import (
    MicroPrimeEngine,
    _enrich_file_spec_from_skeleton,
    _structural_verify,
)
from startd8.micro_prime.models import (
    EscalationReason,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


class TestMicroPrimeEngine:
    """Tests for MicroPrimeEngine orchestration."""

    def test_init_defaults(self):
        engine = MicroPrimeEngine()
        assert engine.config.model == "startd8-coder"
        assert engine.config.templates_enabled is True

    def test_init_custom_config(self):
        config = MicroPrimeConfig(model="custom", templates_enabled=False)
        engine = MicroPrimeEngine(config=config)
        assert engine.config.model == "custom"

    def test_process_trivial_element(
        self, init_element, sample_file_spec, sample_skeleton,
    ):
        """TRIVIAL elements should use template without LLM."""
        engine = MicroPrimeEngine()
        result = engine.process_element(
            init_element, sample_file_spec, sample_skeleton,
        )
        # __init__ with params matches template
        assert result.tier == TierClassification.TRIVIAL
        assert result.success is True
        assert result.template_used is True
        assert result.code is not None
        assert "self.name = name" in result.code

    def test_classification_reason_populated(
        self, init_element, sample_file_spec, sample_skeleton,
    ):
        """R3-S1: ElementResult must carry a non-empty classification_reason."""
        engine = MicroPrimeEngine()
        result = engine.process_element(
            init_element, sample_file_spec, sample_skeleton,
        )
        assert result.classification_reason != ""
        assert isinstance(result.classification_reason, str)

    def test_classification_reason_on_moderate(
        self, sample_file_spec, sample_skeleton,
    ):
        """R3-S1: MODERATE escalations also carry classification_reason."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="run_server",
            signature=Signature(params=[], return_annotation="None"),
        )
        engine = MicroPrimeEngine()
        result = engine.process_element(
            elem, sample_file_spec, sample_skeleton,
        )
        assert result.tier == TierClassification.MODERATE
        assert result.classification_reason != ""

    def test_process_moderate_element_escalates(
        self, sample_file_spec, sample_skeleton,
    ):
        """MODERATE elements should be escalated."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="run_server",
            signature=Signature(params=[], return_annotation="None"),
        )
        engine = MicroPrimeEngine()
        result = engine.process_element(
            elem, sample_file_spec, sample_skeleton,
        )
        assert result.tier == TierClassification.MODERATE
        assert result.success is False
        assert result.escalation is not None
        assert result.escalation.reason == EscalationReason.TIER_TOO_HIGH

    def test_process_complex_element_escalates(
        self, complex_function_element, sample_file_spec, sample_skeleton,
    ):
        """COMPLEX elements should be escalated."""
        engine = MicroPrimeEngine()
        result = engine.process_element(
            complex_function_element, sample_file_spec, sample_skeleton,
        )
        assert result.tier == TierClassification.COMPLEX
        assert result.success is False
        assert result.escalation is not None

    def test_process_constant_trivial(
        self, constant_element, sample_file_spec, sample_skeleton,
    ):
        """Constants with type annotations should match template."""
        engine = MicroPrimeEngine()
        result = engine.process_element(
            constant_element, sample_file_spec, sample_skeleton,
        )
        # Constants are either TRIVIAL (from template) or SIMPLE
        assert result.success is True or result.tier == TierClassification.SIMPLE

    def test_metrics_collector_records(
        self, init_element, sample_file_spec, sample_skeleton,
    ):
        engine = MicroPrimeEngine()
        engine.process_element(
            init_element, sample_file_spec, sample_skeleton,
        )
        assert len(engine.metrics_collector.metrics) == 1
        m = engine.metrics_collector.metrics[0]
        assert m.element_name == "__init__"

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_process_simple_element_with_mock_ollama(
        self, mock_generate, simple_function_element, sample_file_spec, sample_skeleton,
    ):
        """SIMPLE elements should use Ollama (mocked)."""
        mock_generate.return_value = (
            "def get_name(self, key: str) -> str:\n    return key.upper()",
            50,  # input tokens
            30,  # output tokens
        )

        # Make it classify as SIMPLE by disabling templates
        config = MicroPrimeConfig(templates_enabled=False)
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            simple_function_element, sample_file_spec, sample_skeleton,
        )
        assert result.tier == TierClassification.SIMPLE
        assert result.success is True
        assert result.code is not None
        assert result.input_tokens == 50
        assert result.output_tokens == 30

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_process_simple_empty_response_escalates(
        self, mock_generate, simple_function_element, sample_file_spec, sample_skeleton,
    ):
        """Empty Ollama response should escalate."""
        mock_generate.return_value = ("", 0, 0)
        config = MicroPrimeConfig(templates_enabled=False)
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            simple_function_element, sample_file_spec, sample_skeleton,
        )
        assert result.success is False
        assert result.escalation is not None
        assert result.escalation.reason == EscalationReason.EMPTY_RESPONSE

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_process_simple_syntax_error_escalates(
        self, mock_generate, simple_function_element, sample_file_spec, sample_skeleton,
    ):
        """Syntax error after repair should escalate."""
        mock_generate.return_value = ("def get_name(self, :\n    invalid syntax", 50, 30)
        config = MicroPrimeConfig(templates_enabled=False)
        engine = MicroPrimeEngine(config=config)
        result = engine.process_element(
            simple_function_element, sample_file_spec, sample_skeleton,
        )
        assert result.success is False
        assert result.escalation is not None
        assert result.escalation.reason == EscalationReason.AST_FAILURE


class TestProcessFile:
    """Tests for MicroPrimeEngine.process_file()."""

    def test_process_file_handles_all_elements(self, sample_file_spec, sample_manifest, sample_skeleton):
        engine = MicroPrimeEngine()
        result = engine.process_file(sample_file_spec, sample_manifest, sample_skeleton)
        assert result.file_path == "src/mypackage/utils.py"
        assert len(result.element_results) == 3  # get_name, get_value, DEFAULT_TIMEOUT
        assert result.filled_skeleton is not None


class TestProcessSeed:
    """Tests for MicroPrimeEngine.process_seed()."""

    def test_process_seed(self, sample_manifest, sample_skeleton):
        engine = MicroPrimeEngine()
        skeletons = {"src/mypackage/utils.py": sample_skeleton}
        result = engine.process_seed(sample_manifest, skeletons)
        assert len(result.file_results) == 1
        assert result.total_count > 0

    def test_process_seed_skips_missing_skeleton(self, sample_manifest):
        engine = MicroPrimeEngine()
        result = engine.process_seed(sample_manifest, {})
        assert len(result.file_results) == 0


class TestStructuralVerify:
    """Tests for _structural_verify()."""

    def test_valid_function(self, simple_function_element):
        code = "def get_name(self, key: str) -> str:\n    return key"
        assert _structural_verify(code, simple_function_element)[0] is True

    def test_invalid_syntax(self, simple_function_element):
        code = "def get_name(self, :\n    return"
        assert _structural_verify(code, simple_function_element)[0] is False

    def test_valid_constant(self, constant_element):
        code = "DEFAULT_TIMEOUT = 30"
        assert _structural_verify(code, constant_element)[0] is True

    def test_method_with_indentation(self):
        elem = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="helper",
            parent_class="MyClass",
            signature=Signature(params=[Param(name="self")]),
        )
        code = "    def helper(self):\n        return 1"
        assert _structural_verify(code, elem)[0] is True


class TestCompoundChain:
    """Tests for REQ-MP-704: TRIVIAL→few-shot→SIMPLE compound chain."""

    def test_trivial_results_enter_completed_pool(
        self, init_element, sample_file_spec, sample_skeleton,
    ):
        """TRIVIAL template results must be recorded in _completed."""
        engine = MicroPrimeEngine()
        result = engine.process_element(
            init_element, sample_file_spec, sample_skeleton,
        )
        assert result.tier == TierClassification.TRIVIAL
        assert result.success is True
        assert len(engine._completed) == 1
        entry = engine._completed[0]
        assert entry["element"]["name"] == "__init__"
        assert entry["syntax_valid"] is True
        assert entry["code"] is not None
        assert entry["element"]["kind"] == ElementKind.METHOD

    @patch("startd8.micro_prime.engine.MicroPrimeEngine._generate_ollama")
    def test_trivial_feeds_few_shot_to_simple(self, mock_generate):
        """SIMPLE elements should receive TRIVIAL bodies as few-shot examples.

        Builds a file with __init__ (TRIVIAL) and get_name (SIMPLE),
        processes as a file, and verifies TRIVIAL results feed into the
        few-shot pool before SIMPLE generation runs.
        """
        mock_generate.return_value = (
            "def get_name(self, key: str) -> str:\n    return key.upper()",
            50, 30,
        )

        file_spec = ForwardFileSpec(
            file="src/mypackage/utils.py",
            imports=[
                ForwardImportSpec(kind="from", module="typing", names=["Optional"]),
            ],
            elements=[
                # SIMPLE element listed FIRST in manifest to prove re-ordering works
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="get_name",
                    signature=Signature(
                        params=[Param(name="self"), Param(name="key", annotation="str")],
                        return_annotation="str",
                    ),
                    parent_class="Config",
                ),
                # TRIVIAL element listed SECOND — engine must process it first
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(name="name", annotation="str"),
                            Param(name="value", annotation="int", default="0"),
                        ],
                        return_annotation="None",
                    ),
                    parent_class="Config",
                    docstring_hint="Initialize Config.",
                ),
            ],
        )
        # Skeleton that matches the file_spec elements
        skeleton = '''# [STARTD8-SKELETON]
from __future__ import annotations
from typing import Optional


class Config:
    """Config class."""

    def __init__(self, name: str, value: int = 0) -> None:
        """Initialize Config."""
        raise NotImplementedError

    def get_name(self, key: str) -> str:
        raise NotImplementedError
'''
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/mypackage/utils.py": file_spec},
            contracts=[],
        )

        engine = MicroPrimeEngine()
        file_result = engine.process_file(file_spec, manifest, skeleton)

        # __init__ (TRIVIAL) should be first in results due to tier sorting
        assert file_result.element_results[0].element_name == "__init__"
        assert file_result.element_results[0].tier == TierClassification.TRIVIAL
        assert file_result.element_results[0].success is True

        # get_name (SIMPLE) should be second
        assert file_result.element_results[1].element_name == "get_name"

        # The TRIVIAL body should have been in _completed before SIMPLE ran
        assert len(engine._completed) >= 1
        trivial_entry = next(
            e for e in engine._completed if e["element"]["name"] == "__init__"
        )
        assert trivial_entry["syntax_valid"] is True

        # Verify Ollama was called (SIMPLE path was taken)
        assert mock_generate.called

    def test_process_file_tier_sorted_order(self, sample_manifest, sample_skeleton):
        """Elements must be processed TRIVIAL-first, alphabetical within tier."""
        file_spec = ForwardFileSpec(
            file="src/mypackage/utils.py",
            imports=[
                ForwardImportSpec(kind="from", module="typing", names=["Optional"]),
            ],
            elements=[
                # Alphabetically last, but TRIVIAL — should be processed first
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__repr__",
                    signature=Signature(
                        params=[Param(name="self")],
                        return_annotation="str",
                    ),
                    parent_class="Config",
                ),
                # TRIVIAL, alphabetically first
                ForwardElementSpec(
                    kind=ElementKind.METHOD,
                    name="__init__",
                    signature=Signature(
                        params=[
                            Param(name="self"),
                            Param(name="name", annotation="str"),
                        ],
                        return_annotation="None",
                    ),
                    parent_class="Config",
                    docstring_hint="Initialize Config.",
                ),
            ],
        )
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/mypackage/utils.py": file_spec},
            contracts=[],
        )

        engine = MicroPrimeEngine()
        file_result = engine.process_file(file_spec, manifest, sample_skeleton)

        names = [r.element_name for r in file_result.element_results]
        # Both TRIVIAL — should be alphabetical: __init__ before __repr__
        assert names == ["__init__", "__repr__"]

    def test_zero_trivial_simple_still_processes(self, sample_skeleton):
        """If no TRIVIAL elements, SIMPLE should still work (AC-4)."""
        file_spec = ForwardFileSpec(
            file="src/mypackage/utils.py",
            imports=[
                ForwardImportSpec(kind="from", module="typing", names=["Optional"]),
            ],
            elements=[
                ForwardElementSpec(
                    kind=ElementKind.CONSTANT,
                    name="DEFAULT_TIMEOUT",
                    signature=Signature(params=[], return_annotation="int"),
                    docstring_hint="Default timeout.",
                ),
            ],
        )
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/mypackage/utils.py": file_spec},
            contracts=[],
        )

        engine = MicroPrimeEngine()
        file_result = engine.process_file(file_spec, manifest, sample_skeleton)
        assert len(file_result.element_results) == 1


class TestEnrichFileSpecFromSkeleton:
    """Tests for _enrich_file_spec_from_skeleton (Opportunity 1 fix)."""

    def test_adds_methods_from_skeleton(self):
        """Class element without separate method elements gets enriched."""
        class_element = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="EmailService",
            bases=["demo_pb2_grpc.EmailServiceServicer"],
        )
        file_spec = ForwardFileSpec(
            file="src/email_service.py",
            elements=[class_element],
            imports=[],
        )
        skeleton = '''
class EmailService(demo_pb2_grpc.EmailServiceServicer):
    """Email service implementation."""

    def Send(self, request, context) -> demo_pb2.SendResponse:
        """Send an email."""
        raise NotImplementedError

    def Check(self, request, context) -> demo_pb2.CheckResponse:
        """Check email status."""
        raise NotImplementedError
'''
        enriched = _enrich_file_spec_from_skeleton(class_element, file_spec, skeleton)

        # Should have 3 elements: class + 2 methods
        assert len(enriched.elements) == 3
        method_names = {e.name for e in enriched.elements if e.parent_class == "EmailService"}
        assert method_names == {"Send", "Check"}

        send = next(e for e in enriched.elements if e.name == "Send")
        assert send.kind == ElementKind.METHOD
        assert send.parent_class == "EmailService"
        assert send.signature is not None
        assert len(send.signature.params) == 3  # self, request, context
        assert send.signature.return_annotation == "demo_pb2.SendResponse"
        assert send.docstring_hint == "Send an email."

    def test_does_not_duplicate_existing_methods(self):
        """Methods already in file_spec are not added again."""
        class_element = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="Service",
        )
        existing_method = ForwardElementSpec(
            kind=ElementKind.METHOD,
            name="handle",
            signature=Signature(params=[Param(name="self")]),
            parent_class="Service",
        )
        file_spec = ForwardFileSpec(
            file="src/service.py",
            elements=[class_element, existing_method],
            imports=[],
        )
        skeleton = '''
class Service:
    def handle(self):
        raise NotImplementedError

    def start(self):
        raise NotImplementedError
'''
        enriched = _enrich_file_spec_from_skeleton(class_element, file_spec, skeleton)

        # Should have 3: class + existing handle + new start
        assert len(enriched.elements) == 3
        names = [e.name for e in enriched.elements if e.parent_class == "Service"]
        assert "handle" in names
        assert "start" in names

    def test_returns_unchanged_for_non_class(self):
        """Non-class elements pass through unchanged."""
        func_element = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="helper",
            signature=Signature(params=[]),
        )
        file_spec = ForwardFileSpec(
            file="src/utils.py",
            elements=[func_element],
            imports=[],
        )
        result = _enrich_file_spec_from_skeleton(func_element, file_spec, "def helper(): pass")
        assert result is file_spec  # Same object — no copy

    def test_returns_unchanged_for_empty_skeleton(self):
        """Empty skeleton returns file_spec unchanged."""
        class_element = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="Service",
        )
        file_spec = ForwardFileSpec(
            file="src/service.py",
            elements=[class_element],
            imports=[],
        )
        result = _enrich_file_spec_from_skeleton(class_element, file_spec, "")
        assert result is file_spec

    def test_extracts_async_methods(self):
        """Async methods are extracted with ASYNC_METHOD kind."""
        class_element = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="AsyncService",
        )
        file_spec = ForwardFileSpec(
            file="src/async_service.py",
            elements=[class_element],
            imports=[],
        )
        skeleton = '''
class AsyncService:
    async def fetch(self, url: str) -> bytes:
        """Fetch data from URL."""
        raise NotImplementedError
'''
        enriched = _enrich_file_spec_from_skeleton(class_element, file_spec, skeleton)
        fetch = next(e for e in enriched.elements if e.name == "fetch")
        assert fetch.kind == ElementKind.ASYNC_METHOD
        assert fetch.parent_class == "AsyncService"
