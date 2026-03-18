"""Tests for Node.js seed enrichment and template wiring (Phase 3).

Covers REQ-NODE-103 (package.json template), REQ-NODE-104 (module system
detection), REQ-NODE-600 (project context in seeds), and REQ-NODE-601
(Dockerfile context enrichment).
"""

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from startd8.languages.nodejs import NodeLanguageProfile, detect_module_system


@pytest.fixture
def node_profile():
    return NodeLanguageProfile()


# ---------------------------------------------------------------------------
# REQ-NODE-104: CommonJS vs ESM detection from package.json
# ---------------------------------------------------------------------------


class TestDetectModuleSystem:
    """Test detect_module_system() reads package.json type field."""

    def test_commonjs_when_no_type_field(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "test", "version": "1.0.0"}))
        assert detect_module_system(tmp_path) == "commonjs"

    def test_esm_when_type_module(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "test", "type": "module"}))
        assert detect_module_system(tmp_path) == "esm"

    def test_commonjs_when_type_commonjs(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text(json.dumps({"name": "test", "type": "commonjs"}))
        assert detect_module_system(tmp_path) == "commonjs"

    def test_commonjs_when_no_package_json(self, tmp_path):
        assert detect_module_system(tmp_path) == "commonjs"

    def test_commonjs_on_invalid_json(self, tmp_path):
        pkg = tmp_path / "package.json"
        pkg.write_text("{broken json")
        assert detect_module_system(tmp_path) == "commonjs"


# ---------------------------------------------------------------------------
# REQ-NODE-103: package.json template generation
# ---------------------------------------------------------------------------


class TestGenerateDependencyFile:
    """Test NodeLanguageProfile.generate_dependency_file() output."""

    def test_basic_package_json(self, node_profile, tmp_path):
        content = node_profile.generate_dependency_file(
            project_root=tmp_path,
            service_name="currencyservice",
            module_path="",
            dependencies=[
                "@grpc/grpc-js@1.14.3",
                "pino@10.3.0",
            ],
        )
        assert content is not None
        data = json.loads(content)
        assert data["name"] == "currencyservice"
        assert "@grpc/grpc-js" in data["dependencies"]
        assert data["dependencies"]["@grpc/grpc-js"] == "1.14.3"
        assert data["dependencies"]["pino"] == "10.3.0"

    def test_scoped_package_versioning(self, node_profile, tmp_path):
        content = node_profile.generate_dependency_file(
            project_root=tmp_path,
            service_name="test-svc",
            module_path="",
            dependencies=["@opentelemetry/sdk-node@0.57.0"],
        )
        data = json.loads(content)
        assert "@opentelemetry/sdk-node" in data["dependencies"]
        assert data["dependencies"]["@opentelemetry/sdk-node"] == "0.57.0"

    def test_empty_deps_returns_minimal(self, node_profile, tmp_path):
        content = node_profile.generate_dependency_file(
            project_root=tmp_path,
            service_name="minimal",
            module_path="",
            dependencies=[],
        )
        data = json.loads(content)
        assert data["name"] == "minimal"
        assert "dependencies" not in data

    def test_semver_range_preserved(self, node_profile, tmp_path):
        """Semver ranges like ^1.1.0 should be preserved."""
        content = node_profile.generate_dependency_file(
            project_root=tmp_path,
            service_name="svc",
            module_path="",
            dependencies=["uuid@^13.0.0"],
        )
        data = json.loads(content)
        assert data["dependencies"]["uuid"] == "^13.0.0"


# ---------------------------------------------------------------------------
# REQ-NODE-601: Dockerfile context enrichment
# ---------------------------------------------------------------------------


class TestDockerfileContextEnrichment:
    """Test that build_project_context_section includes Dockerfile hints."""

    def test_dockerfile_hints_when_target_is_dockerfile(self, node_profile):
        section = node_profile.build_project_context_section({
            "target_files": ["src/currencyservice/Dockerfile"],
        })
        assert "Multi-stage build" in section
        assert "npm install" in section
        assert "ENTRYPOINT" in section

    def test_no_dockerfile_hints_for_js_files(self, node_profile):
        section = node_profile.build_project_context_section({
            "target_files": ["src/currencyservice/server.js"],
        })
        assert "Multi-stage build" not in section
        assert "ENTRYPOINT" not in section

    def test_dockerfile_uses_custom_entry_point(self, node_profile):
        section = node_profile.build_project_context_section({
            "target_files": ["Dockerfile"],
            "service_metadata": {"entry_point": "server.js"},
        })
        assert 'server.js' in section

    def test_dockerfile_default_entry_point(self, node_profile):
        section = node_profile.build_project_context_section({
            "target_files": ["Dockerfile"],
        })
        assert 'index.js' in section


# ---------------------------------------------------------------------------
# REQ-NODE-600: derive_service_metadata
# ---------------------------------------------------------------------------


class TestDeriveServiceMetadata:
    """Test NodeLanguageProfile.derive_service_metadata()."""

    def test_infers_esm_from_mjs(self, node_profile):
        class FakeFeature:
            target_files = ["app.mjs"]
            module_system = ""
            node_version = ""

        meta = node_profile.derive_service_metadata([FakeFeature()])
        assert meta["module_system"] == "esm"

    def test_infers_commonjs_from_cjs(self, node_profile):
        class FakeFeature:
            target_files = ["app.cjs"]
            module_system = ""
            node_version = ""

        meta = node_profile.derive_service_metadata([FakeFeature()])
        assert meta["module_system"] == "commonjs"

    def test_explicit_module_system_wins(self, node_profile):
        class FakeFeature:
            target_files = ["app.mjs"]
            module_system = "commonjs"
            node_version = ""

        meta = node_profile.derive_service_metadata([FakeFeature()])
        assert meta["module_system"] == "commonjs"

    def test_node_version_from_onboarding(self, node_profile):
        class FakeFeature:
            target_files = ["app.js"]
            module_system = ""
            node_version = ""

        meta = node_profile.derive_service_metadata(
            [FakeFeature()],
            onboarding={"node_version": "22"},
        )
        assert meta["node_version"] == "22"
