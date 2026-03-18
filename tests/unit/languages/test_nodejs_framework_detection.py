"""Tests for Node.js framework detection and prompt wiring (Phase 2).

Covers REQ-NODE-102 (system prompt injection), REQ-NODE-400 (extended framework
imports), and REQ-NODE-401 (framework preamble).
"""

import pytest

from startd8.languages.nodejs import NodeLanguageProfile
from startd8.implementation_engine.framework_imports import (
    detect_frameworks,
    get_import_preamble,
)


@pytest.fixture
def node_profile():
    return NodeLanguageProfile()


# ---------------------------------------------------------------------------
# REQ-NODE-400: Extended framework imports
# ---------------------------------------------------------------------------


class TestNodejsFrameworkDetection:
    """Test framework detection using NodeLanguageProfile.framework_imports."""

    def test_detect_grpc_from_deps(self, node_profile):
        result = detect_frameworks(
            dependencies=["@grpc/grpc-js@1.14.3"],
            language_profile=node_profile,
        )
        assert "grpc" in result

    def test_detect_otel_from_deps(self, node_profile):
        result = detect_frameworks(
            dependencies=["@opentelemetry/sdk-node@0.57.0"],
            language_profile=node_profile,
        )
        assert "otel" in result

    def test_detect_otel_from_api_dep(self, node_profile):
        result = detect_frameworks(
            dependencies=["@opentelemetry/api@1.9.0"],
            language_profile=node_profile,
        )
        assert "otel" in result

    def test_detect_profiler_from_deps(self, node_profile):
        result = detect_frameworks(
            dependencies=["@google-cloud/profiler@6.0.3"],
            language_profile=node_profile,
        )
        assert "profiler" in result

    def test_detect_uuid_from_deps(self, node_profile):
        result = detect_frameworks(
            dependencies=["uuid@^13.0.0"],
            language_profile=node_profile,
        )
        assert "uuid" in result

    def test_detect_express_from_deps(self, node_profile):
        result = detect_frameworks(
            dependencies=["express@4.18.0"],
            language_profile=node_profile,
        )
        assert "express" in result

    def test_detect_pino_from_deps(self, node_profile):
        result = detect_frameworks(
            dependencies=["pino@10.3.0"],
            language_profile=node_profile,
        )
        assert "logging" in result

    def test_detect_otel_from_description(self, node_profile):
        result = detect_frameworks(
            task_description="Add OpenTelemetry tracing to the service",
            language_profile=node_profile,
        )
        assert "otel" in result

    def test_detect_profiler_from_description(self, node_profile):
        result = detect_frameworks(
            task_description="Initialize cloud profiler at startup",
            language_profile=node_profile,
        )
        assert "profiler" in result

    def test_no_detection_unrelated_deps(self, node_profile):
        result = detect_frameworks(
            dependencies=["lodash@4.17.21"],
            language_profile=node_profile,
        )
        assert result == []

    def test_online_boutique_currency_deps(self, node_profile):
        """Full dependency list from currencyservice detects expected frameworks."""
        deps = [
            "@google-cloud/profiler@6.0.3",
            "@grpc/grpc-js@1.14.3",
            "@grpc/proto-loader@0.8.0",
            "@opentelemetry/api@1.9.0",
            "@opentelemetry/sdk-node@0.57.0",
            "pino@10.3.0",
        ]
        result = detect_frameworks(dependencies=deps, language_profile=node_profile)
        assert "grpc" in result
        assert "otel" in result
        assert "profiler" in result
        assert "logging" in result


# ---------------------------------------------------------------------------
# REQ-NODE-401: Import preamble uses javascript fence
# ---------------------------------------------------------------------------


class TestNodejsImportPreamble:
    """Test import preamble formatting for Node.js."""

    def test_preamble_uses_javascript_fence(self, node_profile):
        """Import preamble should use ```javascript fence, not ```python."""
        preamble = get_import_preamble(
            frameworks=["grpc"],
            language_profile=node_profile,
        )
        assert "```javascript" in preamble
        assert "```python" not in preamble

    def test_preamble_contains_require(self, node_profile):
        preamble = get_import_preamble(
            frameworks=["grpc"],
            language_profile=node_profile,
        )
        assert "require('@grpc/grpc-js')" in preamble

    def test_otel_preamble_contains_sdk_node(self, node_profile):
        preamble = get_import_preamble(
            frameworks=["otel"],
            language_profile=node_profile,
        )
        assert "@opentelemetry/sdk-node" in preamble


# ---------------------------------------------------------------------------
# REQ-NODE-102: System prompt wiring
# ---------------------------------------------------------------------------


class TestNodejsSystemPromptWiring:
    """Test that NodeLanguageProfile properties are correct for prompt injection."""

    def test_system_prompt_role(self, node_profile):
        assert node_profile.system_prompt_role == "an expert Node.js engineer"

    def test_coding_standards_mention_async(self, node_profile):
        assert "async/await" in node_profile.coding_standards

    def test_coding_standards_mention_const(self, node_profile):
        assert "const" in node_profile.coding_standards

    def test_coding_standards_mention_no_var(self, node_profile):
        assert "var" in node_profile.coding_standards.lower()


# ---------------------------------------------------------------------------
# Module section defaults to CommonJS
# ---------------------------------------------------------------------------


class TestNodejsModuleSection:
    """Test NodeLanguageProfile.build_project_context_section defaults."""

    def test_defaults_to_commonjs(self, node_profile):
        section = node_profile.build_project_context_section({})
        assert "CommonJS" in section
        assert "require(" in section

    def test_esm_when_specified(self, node_profile):
        section = node_profile.build_project_context_section({
            "module_system": "esm",
        })
        assert "ES Modules" in section or "ESM" in section
        assert "import" in section.lower()
