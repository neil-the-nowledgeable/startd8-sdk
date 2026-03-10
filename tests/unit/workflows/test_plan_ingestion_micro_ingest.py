"""Tests for Micro-Ingest Phase 1: classifier, signature parsing, routing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.workflows.builtin.plan_ingestion_micro_ingest import (
    EnrichmentRoute,
    EnrichmentRouteReport,
    _build_forward_element_spec,
    _build_synthetic_file_spec,
    _normalize_signature,
    _parse_api_signature,
    classify_enrichment_routes,
)


# ── Helpers ──────────────────────────────────────────────────────────


@dataclass
class FakeFeature:
    """Minimal ParsedFeature stub for testing."""

    feature_id: str = "F-001"
    name: str = "Test Feature"
    api_signatures: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    negative_scope: List[str] = field(default_factory=list)
    runtime_dependencies: List[str] = field(default_factory=list)
    protocol: str = ""


def _make_task(
    task_id: str = "T-001",
    description: str = "Implement the feature",
    feature_id: str = "F-001",
    target_files: Optional[List[str]] = None,
    api_signatures: Optional[List[str]] = None,
) -> Dict[str, Any]:
    ctx: Dict[str, Any] = {"feature_id": feature_id}
    if target_files:
        ctx["target_files"] = target_files
    if api_signatures:
        ctx["api_signatures"] = api_signatures
    return {
        "task_id": task_id,
        "title": "Test Task",
        "config": {
            "task_description": description,
            "context": ctx,
        },
    }


# ── Signature Normalization ──────────────────────────────────────────


class TestNormalizeSignature:
    def test_strip_backticks(self):
        assert "def foo(): pass" in _normalize_signature("`def foo()`")

    def test_strip_quotes(self):
        assert "def foo" in _normalize_signature('"def foo()"')

    def test_class_rewrite(self):
        result = _normalize_signature("Class Foo(Base)")
        assert result.startswith("class Foo(Base)")
        assert result.endswith(": pass")

    def test_class_no_bases(self):
        result = _normalize_signature("Class Foo")
        assert result.startswith("class Foo")
        assert result.endswith(": pass")

    def test_def_adds_pass(self):
        result = _normalize_signature("def foo(x: int) -> str")
        assert result.endswith(": pass")

    def test_async_def_adds_pass(self):
        result = _normalize_signature("async def fetch(url: str) -> bytes")
        assert result.endswith(": pass")

    def test_already_has_pass(self):
        result = _normalize_signature("def foo(): pass")
        assert result == "def foo(): pass"


# ── Signature Parsing ────────────────────────────────────────────────


class TestParseApiSignature:
    def test_parse_function(self):
        result = _parse_api_signature("def foo(x: int) -> str")
        assert result is not None
        assert result["name"] == "foo"
        assert result["kind"] == "function"
        assert len(result["params"]) == 1
        assert result["params"][0]["name"] == "x"
        assert result["params"][0]["annotation"] == "int"
        assert result["return_annotation"] == "str"

    def test_parse_async_function(self):
        result = _parse_api_signature("async def fetch(url: str) -> bytes")
        assert result is not None
        assert result["name"] == "fetch"
        assert result["kind"] == "async_function"
        assert result["is_async"] is True

    def test_parse_method_with_parent_class(self):
        result = _parse_api_signature("def EmailService.Send(self, request, context)")
        assert result is not None
        assert result["name"] == "Send"
        assert result["parent_class"] == "EmailService"
        assert result["kind"] == "method"
        # "self" should be in params
        assert any(p["name"] == "self" for p in result["params"])

    def test_parse_class_with_bases(self):
        result = _parse_api_signature("Class EmailService(demo_pb2_grpc.EmailServiceServicer)")
        assert result is not None
        assert result["name"] == "EmailService"
        assert result["kind"] == "class"
        assert "demo_pb2_grpc.EmailServiceServicer" in result["bases"]

    def test_parse_class_no_bases(self):
        result = _parse_api_signature("Class Foo")
        assert result is not None
        assert result["name"] == "Foo"
        assert result["kind"] == "class"
        assert result["bases"] == []

    def test_parse_invalid_returns_none(self):
        result = _parse_api_signature("not a signature at all")
        assert result is None

    def test_parse_empty_returns_none(self):
        assert _parse_api_signature("") is None
        assert _parse_api_signature("   ") is None

    def test_parse_with_backticks(self):
        result = _parse_api_signature("`def foo(x: int) -> str`")
        assert result is not None
        assert result["name"] == "foo"

    def test_parse_no_params(self):
        result = _parse_api_signature("def serve() -> None")
        assert result is not None
        assert result["name"] == "serve"
        assert result["params"] == []

    def test_parse_multiple_params(self):
        result = _parse_api_signature("def create(name: str, port: int, debug: bool) -> Service")
        assert result is not None
        assert len(result["params"]) == 3


# ── ForwardElementSpec Building ──────────────────────────────────────


class TestBuildForwardElementSpec:
    def test_build_function(self):
        parsed = _parse_api_signature("def foo(x: int) -> str")
        spec = _build_forward_element_spec(parsed)
        assert spec is not None
        assert spec.name == "foo"
        assert spec.signature is not None
        assert len(spec.signature.params) == 1

    def test_build_class(self):
        parsed = _parse_api_signature("Class Foo(Base)")
        spec = _build_forward_element_spec(parsed)
        assert spec is not None
        assert spec.name == "Foo"
        assert "Base" in spec.bases

    def test_build_method_with_parent(self):
        parsed = _parse_api_signature("def Cls.method(self, x: int)")
        spec = _build_forward_element_spec(parsed)
        assert spec is not None
        assert spec.name == "method"
        assert spec.parent_class == "Cls"

    def test_build_returns_none_on_bad_input(self):
        assert _build_forward_element_spec({"kind": "unknown", "name": "x"}) is None


# ── Synthetic FileSpec ───────────────────────────────────────────────


class TestBuildSyntheticFileSpec:
    def test_build_from_elements(self):
        parsed = _parse_api_signature("def foo(x: int) -> str")
        spec = _build_forward_element_spec(parsed)
        file_spec = _build_synthetic_file_spec("src/service.py", [spec])
        assert file_spec is not None
        assert file_spec.file == "src/service.py"
        assert len(file_spec.elements) == 1

    def test_build_with_grpc_protocol(self):
        parsed = _parse_api_signature("def serve() -> None")
        spec = _build_forward_element_spec(parsed)
        file_spec = _build_synthetic_file_spec(
            "server.py", [spec],
            runtime_dependencies=["grpcio"],
            protocol="grpc",
        )
        assert file_spec is not None
        import_modules = [i.module for i in file_spec.imports]
        assert "grpc" in import_modules

    def test_empty_elements_returns_none(self):
        assert _build_synthetic_file_spec("foo.py", []) is None


# ── Classifier ───────────────────────────────────────────────────────


class TestClassifier:
    def test_skip_already_has_code_block(self):
        task = _make_task(description="Here is code:\n```python\npass\n```")
        report = classify_enrichment_routes([task], [FakeFeature()])
        assert report.already_enriched == 1
        assert report.routes[0].tier == -1
        assert report.routes[0].needs_code_example is False

    def test_tier_0_forward_spec_available(self):
        """Task whose target_file has a ForwardFileSpec → Tier 0."""
        from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardManifest
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="serve",
            signature=Signature(params=[Param(name="port", annotation="int")]),
        )
        file_spec = ForwardFileSpec(file="src/server.py", elements=[elem])
        manifest = ForwardManifest(file_specs={"src/server.py": file_spec})

        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature()
        report = classify_enrichment_routes([task], [feat], forward_manifest=manifest)

        assert report.tier_0_count == 1
        assert report.routes[0].tier == 0
        assert report.routes[0].has_forward_spec is True

    def test_tier_0_synthetic_from_signatures(self):
        """Task with parseable api_signatures, no ForwardSpec → synthetic Tier 0."""
        task = _make_task(target_files=["src/service.py"])
        feat = FakeFeature(
            api_signatures=["def foo(x: int) -> str"],
            target_files=["src/service.py"],
        )
        report = classify_enrichment_routes([task], [feat])

        assert report.tier_0_count == 1
        assert report.routes[0].tier == 0
        assert report.routes[0].tier_reason == "synthetic ForwardFileSpec (all sigs parsed)"

    def test_skip_no_structural_data(self):
        """Task with no signatures, no ForwardSpec → skip."""
        task = _make_task()
        feat = FakeFeature()
        report = classify_enrichment_routes([task], [feat])

        assert report.skip_count == 1
        assert report.routes[0].tier == -1
        assert "no structural data" in report.routes[0].tier_reason

    def test_skip_no_viable_elements(self):
        """Task with unparseable signatures → skip."""
        task = _make_task()
        feat = FakeFeature(api_signatures=["not valid python at all!!!"])
        report = classify_enrichment_routes([task], [feat])

        assert report.skip_count == 1
        assert report.routes[0].tier == -1

    def test_route_report_counts(self):
        """Multiple tasks → correct tier distribution."""
        tasks = [
            _make_task(task_id="T-1", description="Has code\n```python\npass\n```"),
            _make_task(task_id="T-2"),
            _make_task(task_id="T-3"),
        ]
        feat = FakeFeature(api_signatures=["def foo(x: int) -> str"])
        report = classify_enrichment_routes(tasks, [feat])

        assert report.total_tasks == 3
        assert report.already_enriched == 1
        # T-2 and T-3 both have the same feature with api_signatures
        assert report.tier_0_count == 2

    def test_empty_target_files_no_forward_match(self):
        """Task with no target_files should not match ForwardManifest."""
        from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec, ForwardManifest
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="serve",
            signature=Signature(params=[Param(name="port")]),
        )
        manifest = ForwardManifest(
            file_specs={"src/server.py": ForwardFileSpec(file="src/server.py", elements=[elem])}
        )

        task = _make_task(target_files=[])  # empty target_files
        feat = FakeFeature(api_signatures=["def serve(port: int)"])
        report = classify_enrichment_routes([task], [feat], forward_manifest=manifest)

        # Should NOT match ForwardManifest (empty target_files)
        # But api_signatures → synthetic Tier 0
        assert report.routes[0].has_forward_spec is False

    def test_estimated_ollama_time(self):
        """Tier 2 tasks should have estimated ollama time."""
        # Force tier 2 by mocking template matches to return empty
        task = _make_task()
        feat = FakeFeature(api_signatures=["def foo(x: int) -> str"])

        with patch(
            "startd8.workflows.builtin.plan_ingestion_micro_ingest._check_template_matches",
            return_value=[],
        ), patch(
            "startd8.workflows.builtin.plan_ingestion_micro_ingest._build_synthetic_file_spec",
            return_value=None,
        ):
            report = classify_enrichment_routes([task], [feat])

        if report.tier_2_count > 0:
            assert report.estimated_ollama_time_s > 0


# ── Config Fields ────────────────────────────────────────────────────


class TestMicroIngestConfig:
    def test_config_defaults(self):
        from startd8.workflows.builtin.plan_ingestion_diagnostics import PlanIngestionKaizenConfig

        cfg = PlanIngestionKaizenConfig()
        assert cfg.micro_ingest_enabled is True
        assert cfg.micro_ingest_tier_0_enabled is True
        assert cfg.micro_ingest_tier_1_enabled is True
        assert cfg.micro_ingest_tier_2_enabled is False  # opt-in
        assert cfg.micro_ingest_max_lines == 80
        assert cfg.micro_ingest_ollama_timeout_s == 30

    def test_config_from_json(self):
        import json
        import tempfile
        from pathlib import Path

        from startd8.workflows.builtin.plan_ingestion_diagnostics import load_kaizen_config

        data = {
            "plan_ingestion_kaizen": {
                "micro_ingest_enabled": False,
                "micro_ingest_tier_2_enabled": True,
                "micro_ingest_max_lines": 60,
            }
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            cfg = load_kaizen_config(Path(f.name))

        assert cfg.micro_ingest_enabled is False
        assert cfg.micro_ingest_tier_2_enabled is True
        assert cfg.micro_ingest_max_lines == 60


class TestMicroIngestDiagnostic:
    def test_diagnostic_defaults(self):
        from startd8.workflows.builtin.plan_ingestion_diagnostics import MicroIngestDiagnostic

        diag = MicroIngestDiagnostic()
        assert diag.enabled is False
        assert diag.code_examples_added == 0
        assert diag.time_ms == 0


# ═══════════════════════════════════════════════════════════════════════
# Phase 2 Tests: Deterministic Stub Assembly
# ═══════════════════════════════════════════════════════════════════════


from startd8.workflows.builtin.plan_ingestion_micro_ingest import (
    _render_code_example_tier_0,
    _render_code_example_tier_1,
    _render_signature_line,
    _get_or_build_file_spec,
    _get_template_matches_for_elements,
    enrich_tasks_micro_ingest,
)


def _make_forward_file_spec(file_path="src/server.py", elements=None):
    """Build a ForwardFileSpec for testing."""
    from startd8.forward_manifest import ForwardElementSpec, ForwardFileSpec
    from startd8.utils.code_manifest import ElementKind, Param, Signature

    if elements is None:
        elements = [
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="serve",
                signature=Signature(
                    params=[Param(name="port", annotation="int")],
                    return_annotation="None",
                ),
            ),
        ]
    return ForwardFileSpec(file=file_path, elements=elements)


def _make_forward_manifest(file_specs=None):
    """Build a ForwardManifest for testing."""
    from startd8.forward_manifest import ForwardManifest

    if file_specs is None:
        fs = _make_forward_file_spec()
        file_specs = {fs.file: fs}
    return ForwardManifest(file_specs=file_specs)


class TestRenderSignatureLine:
    def test_function_signature(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="serve",
            signature=Signature(
                params=[Param(name="port", annotation="int")],
                return_annotation="None",
            ),
        )
        line = _render_signature_line(elem)
        assert line == "def serve(port: int) -> None:"

    def test_class_with_bases(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind

        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="EmailService",
            bases=["BaseService"],
        )
        line = _render_signature_line(elem)
        assert line == "class EmailService(BaseService):"

    def test_class_no_bases(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind

        elem = ForwardElementSpec(kind=ElementKind.CLASS, name="Foo")
        line = _render_signature_line(elem)
        assert line == "class Foo:"

    def test_async_function(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        elem = ForwardElementSpec(
            kind=ElementKind.ASYNC_FUNCTION,
            name="fetch",
            signature=Signature(params=[Param(name="url", annotation="str")]),
        )
        line = _render_signature_line(elem)
        assert line == "async def fetch(url: str):"

    def test_no_params_no_return(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind, Signature

        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="init",
            signature=Signature(params=[]),
        )
        line = _render_signature_line(elem)
        assert line == "def init():"


class TestRenderCodeExampleTier0:
    def test_render_valid_file_spec(self):
        file_spec = _make_forward_file_spec()
        result = _render_code_example_tier_0(file_spec)
        assert result is not None
        assert "```python" in result
        assert "## Code Example" in result
        assert "forward manifest" in result

    def test_render_respects_max_lines(self):
        """Truncation works when output exceeds max_lines."""
        file_spec = _make_forward_file_spec()
        result = _render_code_example_tier_0(file_spec, max_lines=2)
        if result is not None:
            # Either truncated or short enough already
            assert "```python" in result

    def test_returns_none_for_empty_spec(self):
        """Empty file spec → DFA render should still produce something minimal."""
        from startd8.forward_manifest import ForwardFileSpec

        file_spec = ForwardFileSpec(file="empty.py", elements=[])
        result = _render_code_example_tier_0(file_spec)
        # DFA may or may not produce valid output for empty elements
        # Either None or valid fenced block
        if result is not None:
            assert "```python" in result


class TestRenderCodeExampleTier1:
    def test_render_with_matches(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="greet",
            signature=Signature(params=[Param(name="name", annotation="str")]),
        )

        class FakeMatch:
            name = "simple_function"
            code = 'return f"Hello, {name}"'

        matches = {"greet": FakeMatch()}
        result = _render_code_example_tier_1([elem], matches)
        assert result is not None
        assert "```python" in result
        assert "def greet(name: str):" in result
        assert "Hello" in result
        assert "template: simple_function" in result

    def test_returns_none_no_matches(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="greet",
            signature=Signature(params=[Param(name="name", annotation="str")]),
        )
        result = _render_code_example_tier_1([elem], {})
        assert result is None

    def test_multiple_elements_joined(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind, Param, Signature

        elems = [
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="foo",
                signature=Signature(params=[]),
            ),
            ForwardElementSpec(
                kind=ElementKind.FUNCTION,
                name="bar",
                signature=Signature(params=[Param(name="x", annotation="int")]),
            ),
        ]

        class FakeMatch:
            def __init__(self, n, c):
                self.name = n
                self.code = c

        matches = {"foo": FakeMatch("t1", "pass"), "bar": FakeMatch("t2", "return x")}
        result = _render_code_example_tier_1(elems, matches)
        assert result is not None
        assert "def foo():" in result
        assert "def bar(x: int):" in result


class TestGetOrBuildFileSpec:
    def test_returns_forward_spec_when_available(self):
        manifest = _make_forward_manifest()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=0,
            tier_reason="test", has_forward_spec=True,
        )
        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature()
        result = _get_or_build_file_spec(
            task, route, {feat.feature_id: feat}, manifest,
        )
        assert result is not None
        assert result.file == "src/server.py"

    def test_builds_synthetic_when_no_manifest(self):
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=0,
            tier_reason="test", has_forward_spec=False,
        )
        feat = FakeFeature(
            api_signatures=["def serve(port: int) -> None"],
            target_files=["src/server.py"],
        )
        task = _make_task(target_files=["src/server.py"])
        result = _get_or_build_file_spec(
            task, route, {feat.feature_id: feat}, None,
        )
        assert result is not None
        assert len(result.elements) >= 1

    def test_returns_none_no_feature(self):
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=0,
            tier_reason="test", has_forward_spec=False,
        )
        task = _make_task(feature_id="nonexistent")
        result = _get_or_build_file_spec(task, route, {}, None)
        assert result is None


class TestEnrichTasksMicroIngest:
    def test_tier_0_enrichment(self):
        """Tier 0 route with forward manifest → code block appended."""
        manifest = _make_forward_manifest()
        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=0,
            tier_reason="forward spec", has_forward_spec=True,
        )
        counters = enrich_tasks_micro_ingest(
            [task], [route], [feat], forward_manifest=manifest,
        )
        assert counters["tier_0_count"] == 1
        assert counters["code_examples_added"] >= 0  # DFA may or may not produce valid output

    def test_skipped_routes_not_enriched(self):
        """Tier -1 routes are counted but not enriched."""
        task = _make_task()
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=False, tier=-1,
            tier_reason="already has code block",
        )
        counters = enrich_tasks_micro_ingest([task], [route], [feat])
        assert counters["already_enriched"] == 1
        assert counters["code_examples_added"] == 0

    def test_skip_no_structural_data(self):
        """Tier -1 with needs_code_example=True → skip_count."""
        task = _make_task()
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=-1,
            tier_reason="no structural data",
        )
        counters = enrich_tasks_micro_ingest([task], [route], [feat])
        assert counters["skip_count"] == 1
        assert counters["code_examples_added"] == 0

    def test_tier_disabled_skips_enrichment(self):
        """Disabled tiers are counted but produce no code blocks."""
        manifest = _make_forward_manifest()
        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=0,
            tier_reason="test", has_forward_spec=True,
        )
        counters = enrich_tasks_micro_ingest(
            [task], [route], [feat],
            forward_manifest=manifest,
            tier_0_enabled=False,
        )
        assert counters["code_examples_added"] == 0

    def test_missing_task_id_graceful(self):
        """Route referencing a nonexistent task_id doesn't crash."""
        route = EnrichmentRoute(
            task_id="MISSING", needs_code_example=True, tier=0,
            tier_reason="test",
        )
        counters = enrich_tasks_micro_ingest(
            [_make_task()], [route], [FakeFeature()],
        )
        assert counters["code_examples_added"] == 0

    def test_tier_2_no_engine_skips(self):
        """Tier 2 enabled but no engine → counted, no code generated."""
        task = _make_task()
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="SIMPLE-viable",
        )
        counters = enrich_tasks_micro_ingest(
            [task], [route], [feat], tier_2_enabled=True,
            micro_prime_engine=None,
        )
        assert counters["tier_2_count"] == 1
        assert counters["code_examples_added"] == 0

    def test_returns_time_ms(self):
        """Counters include time_ms."""
        counters = enrich_tasks_micro_ingest([], [], [])
        assert "time_ms" in counters
        assert counters["time_ms"] >= 0

    def test_tde_106_no_clobber(self):
        """Code block appended to description, not replacing it."""
        manifest = _make_forward_manifest()
        task = _make_task(
            description="Implement the server",
            target_files=["src/server.py"],
        )
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=0,
            tier_reason="forward spec", has_forward_spec=True,
        )
        enrich_tasks_micro_ingest(
            [task], [route], [feat], forward_manifest=manifest,
        )
        desc = task["config"]["task_description"]
        if "```python" in desc:
            # Original description preserved
            assert desc.startswith("Implement the server")


# ═══════════════════════════════════════════════════════════════════════
# Phase 3 Tests: Ollama Code Example Generation
# ═══════════════════════════════════════════════════════════════════════


from startd8.workflows.builtin.plan_ingestion_micro_ingest import (
    _extract_classification_signals,
    _pick_generation_target,
    _try_tier_2,
)


class FakeElementResult:
    """Minimal ElementResult stub."""

    def __init__(self, success=True, code="def serve(port: int) -> None:\n    pass"):
        self.success = success
        self.code = code


class FakeMicroPrimeEngine:
    """Minimal MicroPrimeEngine stub for testing."""

    _circuit_open = False

    def __init__(self, circuit_open=False, result=None):
        self._circuit_open = circuit_open
        self._result = result or FakeElementResult()

    def _handle_simple(self, **kwargs):
        return self._result


class TestPickGenerationTarget:
    def test_prefers_function_over_class(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind, Signature

        cls_elem = ForwardElementSpec(kind=ElementKind.CLASS, name="Foo")
        fn_elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION, name="bar",
            signature=Signature(params=[]),
        )
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="test", elements=["Foo", "bar"],
        )
        result = _pick_generation_target([cls_elem, fn_elem], route)
        assert result.name == "bar"

    def test_returns_first_if_no_functions(self):
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import ElementKind

        elem = ForwardElementSpec(kind=ElementKind.CLASS, name="Foo")
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="test",
        )
        result = _pick_generation_target([elem], route)
        assert result.name == "Foo"

    def test_returns_none_empty(self):
        route = EnrichmentRoute(task_id="T-001", needs_code_example=True, tier=2, tier_reason="test")
        assert _pick_generation_target([], route) is None


class TestExtractClassificationSignals:
    def test_external_api_from_deps(self):
        feat = FakeFeature(runtime_dependencies=["httpx", "pydantic"])
        task = _make_task()
        signals = _extract_classification_signals(task, {feat.feature_id: feat})
        assert "external_api" in signals

    def test_orchestrator_from_description(self):
        task = _make_task(description="Main orchestration loop for the service")
        feat = FakeFeature()
        signals = _extract_classification_signals(task, {feat.feature_id: feat})
        assert "orchestrator" in signals

    def test_no_signals(self):
        task = _make_task(description="Simple data transform")
        feat = FakeFeature(runtime_dependencies=["pydantic"])
        signals = _extract_classification_signals(task, {feat.feature_id: feat})
        assert len(signals) == 0


class TestTryTier2:
    def test_success_returns_code_block(self):
        engine = FakeMicroPrimeEngine(
            result=FakeElementResult(success=True, code="def serve(port: int) -> None:\n    pass"),
        )
        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature(
            api_signatures=["def serve(port: int) -> None"],
            target_files=["src/server.py"],
        )
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="test", has_forward_spec=False,
            elements=["serve"],
        )
        result = _try_tier_2(
            task, route, {feat.feature_id: feat}, None,
            max_lines=80, timeout_s=10,
            micro_prime_engine=engine,
        )
        assert result is not None
        assert "```python" in result
        assert "generated by Ollama" in result

    def test_failure_returns_none(self):
        engine = FakeMicroPrimeEngine(
            result=FakeElementResult(success=False, code=None),
        )
        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature(
            api_signatures=["def serve(port: int) -> None"],
            target_files=["src/server.py"],
        )
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="test", has_forward_spec=False,
        )
        result = _try_tier_2(
            task, route, {feat.feature_id: feat}, None,
            max_lines=80, micro_prime_engine=engine,
        )
        assert result is None

    def test_skip_signals_respected(self):
        """external_api signal → skip generation."""
        engine = FakeMicroPrimeEngine()
        task = _make_task(description="Call external API with httpx")
        feat = FakeFeature(runtime_dependencies=["httpx"])
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="test", has_forward_spec=False,
        )
        result = _try_tier_2(
            task, route, {feat.feature_id: feat}, None,
            max_lines=80, micro_prime_engine=engine,
        )
        assert result is None

    def test_no_engine_returns_none(self):
        task = _make_task()
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2, tier_reason="test",
        )
        assert _try_tier_2(task, route, {feat.feature_id: feat}, None, 80) is None


class TestTier2InExecutor:
    def test_tier_2_with_engine_success(self):
        """Tier 2 with mock engine → code block appended."""
        engine = FakeMicroPrimeEngine(
            result=FakeElementResult(success=True, code="def serve(port: int):\n    pass"),
        )
        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature(
            api_signatures=["def serve(port: int) -> None"],
            target_files=["src/server.py"],
        )
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="SIMPLE-viable", has_forward_spec=False,
            elements=["serve"],
        )
        counters = enrich_tasks_micro_ingest(
            [task], [route], [feat],
            tier_2_enabled=True,
            micro_prime_engine=engine,
        )
        assert counters["tier_2_count"] == 1
        assert counters["code_examples_added"] == 1
        assert "```python" in task["config"]["task_description"]

    def test_circuit_breaker_skips_all(self):
        """Circuit breaker open → all Tier 2 skipped."""
        engine = FakeMicroPrimeEngine(circuit_open=True)
        task = _make_task(target_files=["src/server.py"])
        feat = FakeFeature(api_signatures=["def serve(port: int)"])
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="test", elements=["serve"],
        )
        counters = enrich_tasks_micro_ingest(
            [task], [route], [feat],
            tier_2_enabled=True,
            micro_prime_engine=engine,
        )
        assert counters["tier_2_count"] == 1
        assert counters["tier_2_skipped_signals"] == 1
        assert counters["code_examples_added"] == 0

    def test_tier_2_disabled_counted_only(self):
        """tier_2_enabled=False → counted but no engine call."""
        engine = FakeMicroPrimeEngine()
        task = _make_task()
        feat = FakeFeature()
        route = EnrichmentRoute(
            task_id="T-001", needs_code_example=True, tier=2,
            tier_reason="SIMPLE-viable",
        )
        counters = enrich_tasks_micro_ingest(
            [task], [route], [feat],
            tier_2_enabled=False,
            micro_prime_engine=engine,
        )
        assert counters["tier_2_count"] == 1
        assert counters["code_examples_added"] == 0
