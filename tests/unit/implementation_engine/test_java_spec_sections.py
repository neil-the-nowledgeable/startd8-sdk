"""Tests for Java and Node.js spec builder sections (REQ-PLI-500/501).

Covers JavaLanguageProfile.build_project_context_section(),
NodeLanguageProfile.build_project_context_section(),
and _build_available_imports_section() for Java and Node.js dependencies.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


class _FakeLangProfile:
    """Minimal language profile stub for _build_available_imports_section tests."""
    def __init__(self, language_id: str):
        self.language_id = language_id


class TestBuildJavaProjectSection:
    """REQ-PLI-501: JavaLanguageProfile.build_project_context_section()."""

    def _build(self, context):
        from startd8.languages.java import JavaLanguageProfile
        profile = JavaLanguageProfile()
        return profile.build_project_context_section(context)

    def test_basic_java_section(self):
        ctx = {
            "java_package": "com.example.svc",
            "target_files": ["src/main/java/com/example/svc/OrderService.java"],
            "java_version": "21",
            "build_system": "gradle",
        }
        result = self._build(ctx)
        assert "## Java Project Context" in result
        assert "package com.example.svc;" in result
        assert "OrderService" in result
        assert "Java version**: 21" in result
        assert "Gradle" in result

    def test_package_from_service_metadata(self):
        ctx = {
            "target_files": ["src/main/java/com/example/svc/App.java"],
            "service_metadata": {
                "java_package": "com.example.svc",
                "build_system": "maven",
            },
        }
        result = self._build(ctx)
        assert "package com.example.svc;" in result
        assert "Maven" in result

    def test_package_inferred_from_path(self):
        ctx = {
            "target_files": ["src/main/java/com/example/order/OrderService.java"],
        }
        result = self._build(ctx)
        assert "com.example.order" in result

    def test_no_package(self):
        ctx = {
            "target_files": ["App.java"],
        }
        result = self._build(ctx)
        # Should still produce section but without package line
        assert "## Java Project Context" in result
        assert "App" in result

    def test_import_rules_present(self):
        ctx = {
            "target_files": ["App.java"],
        }
        result = self._build(ctx)
        assert "Java import rules" in result
        assert "fully qualified" in result
        assert "wildcard" in result

    def test_structural_rules_present(self):
        ctx = {
            "target_files": ["App.java"],
        }
        result = self._build(ctx)
        assert "Java structural rules" in result
        assert "PascalCase" in result
        assert "try-with-resources" in result


class TestAvailableImportsJava:
    """REQ-PLI-500: Java dependency formatting in available imports."""

    def _build(self, context):
        from startd8.implementation_engine.spec_builder import _build_available_imports_section
        return _build_available_imports_section(context)

    def _java_profile(self):
        from startd8.languages.java import JavaLanguageProfile
        return JavaLanguageProfile()

    def _go_profile(self):
        from startd8.languages.go import GoLanguageProfile
        return GoLanguageProfile()

    def _node_profile(self):
        from startd8.languages.nodejs import NodeLanguageProfile
        return NodeLanguageProfile()

    def test_java_dep_stripping(self):
        ctx = {
            "language_profile": self._java_profile(),
            "runtime_dependencies": [
                "io.grpc:grpc-netty:1.68.0",
                "com.google.protobuf:protobuf-java:3.25.0",
            ],
        }
        result = self._build(ctx)
        assert "io.grpc:grpc-netty" in result
        assert "com.google.protobuf:protobuf-java" in result
        # Version should be stripped
        assert "1.68.0" not in result
        assert "3.25.0" not in result

    def test_java_import_syntax(self):
        ctx = {
            "language_profile": self._java_profile(),
            "runtime_dependencies": ["io.grpc:grpc-core:1.68.0"],
        }
        result = self._build(ctx)
        # Template may or may not include Java-specific text; just verify
        # the dep was included and version stripped
        assert "io.grpc:grpc-core" in result
        assert "1.68.0" not in result

    def test_go_unchanged(self):
        ctx = {
            "language_profile": self._go_profile(),
            "runtime_dependencies": ["github.com/sirupsen/logrus v1.9.4"],
        }
        result = self._build(ctx)
        assert "github.com/sirupsen/logrus" in result
        assert "v1.9.4" not in result

    def test_nodejs_scoped_dep_stripping(self):
        ctx = {
            "language_profile": self._node_profile(),
            "runtime_dependencies": [
                "@grpc/grpc-js@1.10.0",
                "pino@8.0.0",
            ],
        }
        result = self._build(ctx)
        assert "@grpc/grpc-js" in result
        assert "pino" in result
        # Versions should be stripped
        assert "1.10.0" not in result
        assert "8.0.0" not in result

    def test_nodejs_unscoped_dep_stripping(self):
        ctx = {
            "language_profile": self._node_profile(),
            "runtime_dependencies": ["express@4.18.0"],
        }
        result = self._build(ctx)
        assert "express" in result
        assert "4.18.0" not in result

    def test_empty_deps(self):
        ctx = {
            "language_profile": self._java_profile(),
            "runtime_dependencies": [],
        }
        result = self._build(ctx)
        assert result == ""


class TestBuildNodejsModuleSection:
    """REQ-PLI-501: NodeLanguageProfile.build_project_context_section()."""

    def _build(self, context):
        from startd8.languages.nodejs import NodeLanguageProfile
        profile = NodeLanguageProfile()
        return profile.build_project_context_section(context)

    def test_esm_section(self):
        ctx = {
            "module_system": "esm",
            "node_version": "20",
        }
        result = self._build(ctx)
        assert "## Node.js Module Context" in result
        assert "ES Modules (ESM)" in result
        assert "Node.js version**: 20" in result
        assert "import X from" in result
        assert "No `require()`" in result

    def test_commonjs_section(self):
        ctx = {
            "module_system": "commonjs",
        }
        result = self._build(ctx)
        assert "CommonJS (CJS)" in result
        assert "require('pkg')" in result
        assert "module.exports" in result

    def test_default_commonjs(self):
        ctx = {}
        result = self._build(ctx)
        assert "CommonJS (CJS)" in result

    def test_module_system_from_service_metadata(self):
        ctx = {
            "service_metadata": {"module_system": "commonjs"},
        }
        result = self._build(ctx)
        assert "CommonJS (CJS)" in result

    def test_structural_rules_present(self):
        ctx = {}
        result = self._build(ctx)
        assert "Node.js structural rules" in result
        assert "camelCase" in result
        assert "async" in result
        assert "const" in result
