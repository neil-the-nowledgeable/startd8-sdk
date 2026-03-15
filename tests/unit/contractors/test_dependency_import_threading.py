"""Tests for dependency import threading in PrimeContractor and spec_builder.

Verifies that ``_collect_dependency_imports`` extracts modules from dependency
task descriptions and forward manifest base classes, and that
``_build_dependency_imports_section`` renders them into the spec prompt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from startd8.contractors.queue import FeatureSpec
from startd8.implementation_engine.spec_builder import (
    _build_dependency_imports_section,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(
    fid: str,
    description: str = "",
    dependencies: Optional[List[str]] = None,
    target_files: Optional[List[str]] = None,
) -> FeatureSpec:
    return FeatureSpec(
        id=fid,
        name=fid,
        description=description,
        dependencies=dependencies or [],
        target_files=target_files or [],
    )


def _make_forward_manifest(file_specs: dict):
    """Build a minimal ForwardManifest-like object with .file_specs dict."""
    from startd8.forward_manifest import (
        ForwardElementSpec,
        ForwardFileSpec,
        ForwardImportSpec,
        ForwardManifest,
    )

    element_kinds = {"class", "function", "async_function", "method",
                      "async_method", "property", "constant", "variable", "type_alias"}
    specs = {}
    for path, elems_and_imports in file_specs.items():
        elements = []
        imports = []
        for item in elems_and_imports:
            if item.get("kind") in element_kinds:
                elements.append(ForwardElementSpec(**item))
            elif "module" in item:
                imports.append(ForwardImportSpec(**item))
        specs[path] = ForwardFileSpec(file=path, elements=elements, imports=imports)

    return ForwardManifest(file_specs=specs)


def _make_workflow(queue_features, forward_manifest=None):
    """Build a minimal mock that has .queue and ._forward_manifest."""
    wf = MagicMock()
    wf.queue = MagicMock()
    wf.queue.get_feature = lambda fid: queue_features.get(fid)
    wf._forward_manifest = forward_manifest

    # Bind the real method
    from startd8.contractors.prime_contractor import PrimeContractorWorkflow

    wf._collect_dependency_imports = (
        PrimeContractorWorkflow._collect_dependency_imports.__get__(wf)
    )
    return wf


# ---------------------------------------------------------------------------
# _collect_dependency_imports tests
# ---------------------------------------------------------------------------


class TestCollectDependencyImports:
    """Tests for PrimeContractorWorkflow._collect_dependency_imports."""

    def test_no_dependencies_returns_empty(self):
        feature = _make_feature("PI-004", dependencies=[])
        wf = _make_workflow({})
        assert wf._collect_dependency_imports(feature) == {}

    def test_extracts_from_description_backticks(self):
        dep = _make_feature(
            "PI-003",
            description="Implements email server.\n- Imports: `demo_pb2`, `demo_pb2_grpc`",
            target_files=["src/emailservice/email_server.py"],
        )
        feature = _make_feature("PI-004", dependencies=["PI-003"])
        wf = _make_workflow({"PI-003": dep})

        result = wf._collect_dependency_imports(feature)

        assert "PI-003" in result
        assert "demo_pb2" in result["PI-003"]["modules"]
        assert "demo_pb2_grpc" in result["PI-003"]["modules"]
        assert result["PI-003"]["target_files"] == ["src/emailservice/email_server.py"]

    def test_extracts_from_description_bare_names(self):
        dep = _make_feature(
            "PI-003",
            description="- Imports: demo_pb2, demo_pb2_grpc, grpc_health.v1",
        )
        feature = _make_feature("PI-004", dependencies=["PI-003"])
        wf = _make_workflow({"PI-003": dep})

        result = wf._collect_dependency_imports(feature)
        modules = result["PI-003"]["modules"]
        assert "demo_pb2" in modules
        assert "grpc_health.v1" in modules

    def test_extracts_from_forward_manifest_bases(self):
        dep = _make_feature(
            "PI-003",
            description="Implements email server.",
            target_files=["src/emailservice/email_server.py"],
        )
        manifest = _make_forward_manifest({
            "src/emailservice/email_server.py": [
                {"kind": "class", "name": "EmailService", "bases": ["demo_pb2_grpc.EmailServiceServicer"]},
            ],
        })
        feature = _make_feature("PI-004", dependencies=["PI-003"])
        wf = _make_workflow({"PI-003": dep}, forward_manifest=manifest)

        result = wf._collect_dependency_imports(feature)
        assert "demo_pb2_grpc" in result["PI-003"]["modules"]

    def test_extracts_from_forward_manifest_imports(self):
        dep = _make_feature(
            "PI-003",
            description="Implements email server.",
            target_files=["src/emailservice/email_server.py"],
        )
        manifest = _make_forward_manifest({
            "src/emailservice/email_server.py": [
                {"kind": "from", "module": "demo_pb2"},
            ],
        })
        feature = _make_feature("PI-004", dependencies=["PI-003"])
        wf = _make_workflow({"PI-003": dep}, forward_manifest=manifest)

        result = wf._collect_dependency_imports(feature)
        assert "demo_pb2" in result["PI-003"]["modules"]

    def test_merges_description_and_manifest(self):
        dep = _make_feature(
            "PI-003",
            description="- Imports: `demo_pb2`",
            target_files=["src/emailservice/email_server.py"],
        )
        manifest = _make_forward_manifest({
            "src/emailservice/email_server.py": [
                {"kind": "class", "name": "EmailService", "bases": ["demo_pb2_grpc.EmailServiceServicer"]},
            ],
        })
        feature = _make_feature("PI-004", dependencies=["PI-003"])
        wf = _make_workflow({"PI-003": dep}, forward_manifest=manifest)

        result = wf._collect_dependency_imports(feature)
        modules = result["PI-003"]["modules"]
        assert "demo_pb2" in modules
        assert "demo_pb2_grpc" in modules

    def test_missing_dep_in_queue_skipped(self):
        feature = _make_feature("PI-004", dependencies=["PI-999"])
        wf = _make_workflow({})

        result = wf._collect_dependency_imports(feature)
        assert result == {}

    def test_dep_with_no_modules_skipped(self):
        dep = _make_feature("PI-003", description="Simple utility.")
        feature = _make_feature("PI-004", dependencies=["PI-003"])
        wf = _make_workflow({"PI-003": dep})

        result = wf._collect_dependency_imports(feature)
        assert result == {}


# ---------------------------------------------------------------------------
# _build_dependency_imports_section tests
# ---------------------------------------------------------------------------


class TestBuildDependencyImportsSection:
    """Tests for spec_builder._build_dependency_imports_section."""

    def test_empty_when_no_key(self):
        ctx: Dict[str, Any] = {}
        assert _build_dependency_imports_section(ctx) == ""

    def test_renders_modules(self):
        ctx: Dict[str, Any] = {
            "dependency_imports": {
                "PI-003": {
                    "modules": ["demo_pb2", "demo_pb2_grpc"],
                    "target_files": ["src/emailservice/email_server.py"],
                },
            },
        }
        section = _build_dependency_imports_section(ctx)
        assert "## Dependency Task Imports" in section
        assert "PI-003" in section
        assert "`demo_pb2`" in section
        assert "`demo_pb2_grpc`" in section
        assert "src/emailservice/email_server.py" in section
        # Key should be popped from context
        assert "dependency_imports" not in ctx

    def test_multiple_deps(self):
        ctx: Dict[str, Any] = {
            "dependency_imports": {
                "PI-003": {"modules": ["demo_pb2"], "target_files": []},
                "PI-005": {"modules": ["grpc"], "target_files": ["src/server.py"]},
            },
        }
        section = _build_dependency_imports_section(ctx)
        assert "PI-003" in section
        assert "PI-005" in section
        assert "`demo_pb2`" in section
        assert "`grpc`" in section
