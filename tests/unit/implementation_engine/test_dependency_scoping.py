"""Tests for L3: per-service dependency scoping."""

import pytest

from startd8.contractors.context_seed.shared import (
    _extract_imported_modules,
    _strip_version_pin,
    scope_dependencies_to_file,
)


class TestStripVersionPin:
    def test_equals(self):
        assert _strip_version_pin("grpcio==1.76.0") == "grpcio"

    def test_gte(self):
        assert _strip_version_pin("flask>=2.0") == "flask"

    def test_lte(self):
        assert _strip_version_pin("requests<=2.28") == "requests"

    def test_tilde(self):
        assert _strip_version_pin("httpx~=0.24") == "httpx"

    def test_no_pin(self):
        assert _strip_version_pin("flask") == "flask"

    def test_lt(self):
        assert _strip_version_pin("numpy<2") == "numpy"


class TestExtractImportedModules:
    def test_import_statement(self):
        source = "import grpc\nimport os\n"
        result = _extract_imported_modules(source)
        assert "grpc" in result
        assert "os" in result

    def test_from_import(self):
        source = "from flask import Flask, request\n"
        result = _extract_imported_modules(source)
        assert "flask" in result

    def test_dotted_import(self):
        source = "from google.cloud.secretmanager import SecretManagerServiceClient\n"
        result = _extract_imported_modules(source)
        assert "google" in result

    def test_syntax_error_returns_empty(self):
        source = "def broken(\n"
        result = _extract_imported_modules(source)
        assert result == set()

    def test_empty_source(self):
        result = _extract_imported_modules("")
        assert result == set()


class TestScopeDependencies:
    ALL_DEPS = [
        "flask>=2.0",
        "grpcio==1.76.0",
        "locust>=2.0",
        "langchain",
        "pyyaml",
    ]

    def test_basic_scoping(self):
        source = "import flask\nimport grpc\n"
        result = scope_dependencies_to_file("app.py", source, self.ALL_DEPS)
        assert "flask>=2.0" in result
        assert "grpcio==1.76.0" in result
        assert "locust>=2.0" not in result
        assert "langchain" not in result

    def test_alias_mapping_pyyaml(self):
        source = "import yaml\n"
        result = scope_dependencies_to_file("config.py", source, self.ALL_DEPS)
        assert "pyyaml" in result

    def test_alias_mapping_grpcio(self):
        source = "import grpc\n"
        result = scope_dependencies_to_file("server.py", source, ["grpcio==1.76.0"])
        assert "grpcio==1.76.0" in result

    def test_no_imports_returns_full_list(self):
        """Empty AST result (no imports found) falls back to full list."""
        source = "x = 1\n"
        result = scope_dependencies_to_file("util.py", source, self.ALL_DEPS)
        # No imports at all → fallback to full list
        assert result == self.ALL_DEPS

    def test_empty_file_returns_full_list(self):
        result = scope_dependencies_to_file("empty.py", "", self.ALL_DEPS)
        assert result == self.ALL_DEPS

    def test_ast_failure_falls_back(self):
        """Syntax errors → full list returned (non-Python-looking content)."""
        source = "{{invalid python}}"
        # _extract_imported_modules returns empty set on SyntaxError
        # scope_dependencies_to_file falls back to full list
        result = scope_dependencies_to_file("broken.py", source, self.ALL_DEPS)
        assert result == self.ALL_DEPS

    def test_nested_import(self):
        source = "from google.cloud.secretmanager import SecretManagerServiceClient\n"
        deps = ["google-cloud-secret-manager>=2.0"]
        result = scope_dependencies_to_file("secrets.py", source, deps)
        assert "google-cloud-secret-manager>=2.0" in result

    def test_non_python_file_returns_full_list(self):
        result = scope_dependencies_to_file(
            "requirements.in", "flask\ngrpcio\n", self.ALL_DEPS
        )
        assert result == self.ALL_DEPS

    def test_no_deps_returns_empty(self):
        result = scope_dependencies_to_file("app.py", "import flask\n", [])
        assert result == []

    def test_underscore_hyphen_normalization(self):
        """PyPI names with hyphens should match underscore imports."""
        source = "import python_dateutil\n"
        # This won't match because python-dateutil maps to "dateutil", not "python_dateutil"
        # But if someone has a package named "some-pkg" and imports "some_pkg", it should match
        deps = ["some-pkg"]
        source2 = "import some_pkg\n"
        result = scope_dependencies_to_file("app.py", source2, deps)
        assert "some-pkg" in result
