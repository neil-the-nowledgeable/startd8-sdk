"""Tests for Node.js plan ingestion improvements (REQ-PLI-NODE-103, REQ-PLI-NODE-104)."""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List
from unittest.mock import patch

from startd8.implementation_engine.spec_builder import _build_typescript_guidance_section


# ---------------------------------------------------------------------------
# REQ-PLI-NODE-103: TypeScript guidance in spec builder
# ---------------------------------------------------------------------------


class TestTypescriptGuidanceSection:
    """TypeScript detection injects guidance when .ts/.tsx files are targeted."""

    def test_ts_files_trigger_guidance(self):
        context = {"target_files": ["src/index.ts", "src/utils.ts"]}
        result = _build_typescript_guidance_section(context)
        assert "## TypeScript Conventions" in result
        assert "`unknown` over `any`" in result
        assert "import type" in result

    def test_tsx_files_trigger_guidance(self):
        context = {"target_files": ["src/App.tsx"]}
        result = _build_typescript_guidance_section(context)
        assert "## TypeScript Conventions" in result

    def test_mixed_ts_js_triggers_guidance(self):
        context = {"target_files": ["src/main.js", "src/types.ts"]}
        result = _build_typescript_guidance_section(context)
        assert "## TypeScript Conventions" in result

    def test_js_only_no_guidance(self):
        context = {"target_files": ["src/index.js", "src/utils.js"]}
        result = _build_typescript_guidance_section(context)
        assert result == ""

    def test_no_target_files_no_guidance(self):
        context = {}
        result = _build_typescript_guidance_section(context)
        assert result == ""

    def test_empty_target_files_no_guidance(self):
        context = {"target_files": []}
        result = _build_typescript_guidance_section(context)
        assert result == ""

    def test_python_files_no_guidance(self):
        context = {"target_files": ["src/main.py", "src/utils.py"]}
        result = _build_typescript_guidance_section(context)
        assert result == ""

    def test_strict_mode_mentioned(self):
        context = {"target_files": ["src/server.ts"]}
        result = _build_typescript_guidance_section(context)
        assert "strict: true" in result


# ---------------------------------------------------------------------------
# REQ-PLI-NODE-104: Framework detection from plan text
# ---------------------------------------------------------------------------


@dataclass
class _FakeFeature:
    """Minimal stand-in for ParsedFeature."""
    description: str = ""
    api_signatures: List[str] = field(default_factory=list)
    protocol: str = ""
    runtime_dependencies: List[str] = field(default_factory=list)
    target_files: List[str] = field(default_factory=list)
    negative_scope: List[str] = field(default_factory=list)
    module_system: str = ""
    node_version: str = ""


def _make_node_features(
    descriptions: List[str],
    api_signatures: List[List[str]] | None = None,
) -> List[_FakeFeature]:
    """Create fake features with .js target files (Node.js primary language)."""
    sigs = api_signatures or [[] for _ in descriptions]
    return [
        _FakeFeature(
            description=desc,
            api_signatures=sig,
            target_files=["src/index.js"],
        )
        for desc, sig in zip(descriptions, sigs)
    ]


def _stub_language_registry():
    """Patch LanguageRegistry so _infer_service_metadata doesn't require real profiles."""
    return patch.multiple(
        "startd8.languages.registry.LanguageRegistry",
        get_extension_map=lambda: {".js": "nodejs", ".ts": "nodejs", ".py": "python"},
        get=lambda lang_id: None,
    )


class TestNodejsFrameworkDetection:
    """Node.js framework detection from plan text (REQ-PLI-NODE-104)."""

    def test_express_detected(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata

        features = _make_node_features(
            ["Build an Express HTTP server with REST endpoints"]
        )
        with _stub_language_registry():
            metadata = _infer_service_metadata(features)
        assert "express" in metadata.get("detected_frameworks", [])

    def test_grpc_detected(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata

        features = _make_node_features(
            ["Implement gRPC service using @grpc/grpc-js and proto-loader"]
        )
        with _stub_language_registry():
            metadata = _infer_service_metadata(features)
        assert "grpc" in metadata.get("detected_frameworks", [])

    def test_grpc_from_api_signatures(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata

        features = _make_node_features(
            ["Implement product catalog service"],
            api_signatures=[["@grpc/grpc-js server.addService()"]],
        )
        with _stub_language_registry():
            metadata = _infer_service_metadata(features)
        assert "grpc" in metadata.get("detected_frameworks", [])

    def test_multiple_frameworks_detected(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata

        features = _make_node_features(
            ["Express REST API gateway with gRPC backend communication"]
        )
        with _stub_language_registry():
            metadata = _infer_service_metadata(features)
        frameworks = metadata.get("detected_frameworks", [])
        assert "express" in frameworks
        assert "grpc" in frameworks

    def test_no_framework_detected(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata

        features = _make_node_features(
            ["Simple Node.js utility script that reads files"]
        )
        with _stub_language_registry():
            metadata = _infer_service_metadata(features)
        assert "detected_frameworks" not in metadata

    def test_react_detected(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata

        features = _make_node_features(
            ["Build a React component with useState and useEffect hooks"]
        )
        with _stub_language_registry():
            metadata = _infer_service_metadata(features)
        assert "react" in metadata.get("detected_frameworks", [])

    def test_non_nodejs_no_framework_detection(self):
        """Framework detection only runs for Node.js primary language."""
        from startd8.workflows.builtin.plan_ingestion_workflow import _infer_service_metadata

        features = [
            _FakeFeature(
                description="Express-like Python web framework",
                target_files=["src/main.py"],
            )
        ]
        with patch.multiple(
            "startd8.languages.registry.LanguageRegistry",
            get_extension_map=lambda: {".py": "python", ".js": "nodejs"},
            get=lambda lang_id: None,
        ):
            metadata = _infer_service_metadata(features)
        assert "detected_frameworks" not in metadata


class TestNodejsFrameworkDetectionDerivation:
    """Framework detection in seeds/derivation.py (parallel implementation)."""

    def test_express_detected_in_derivation(self):
        from startd8.seeds.derivation import infer_service_metadata

        features = _make_node_features(
            ["Build Express middleware for authentication"]
        )
        with _stub_language_registry():
            metadata = infer_service_metadata(features)
        assert "express" in metadata.get("detected_frameworks", [])

    def test_no_framework_in_derivation(self):
        from startd8.seeds.derivation import infer_service_metadata

        features = _make_node_features(
            ["Simple file processing script"]
        )
        with _stub_language_registry():
            metadata = infer_service_metadata(features)
        assert "detected_frameworks" not in metadata
