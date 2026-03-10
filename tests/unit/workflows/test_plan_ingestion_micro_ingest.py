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
