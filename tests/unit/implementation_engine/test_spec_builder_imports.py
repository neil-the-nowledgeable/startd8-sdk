"""Tests for L1: available imports section in spec builder."""

import pytest

from startd8.implementation_engine.spec_builder import (
    _build_available_imports_section,
    build_spec_prompt,
)


class TestBuildAvailableImportsSection:
    def test_populated_with_deps(self):
        ctx = {"runtime_dependencies": ["flask", "grpcio==1.76.0", "locust>=2.0"]}
        result = _build_available_imports_section(ctx)
        assert "flask" in result
        assert "grpcio" in result
        assert "locust" in result
        assert "Available Imports" in result

    def test_empty_when_no_deps(self):
        ctx = {"runtime_dependencies": []}
        result = _build_available_imports_section(ctx)
        assert result == ""

    def test_empty_when_key_missing(self):
        result = _build_available_imports_section({})
        assert result == ""

    def test_version_pin_stripped_equals(self):
        ctx = {"runtime_dependencies": ["grpcio==1.76.0"]}
        result = _build_available_imports_section(ctx)
        assert "- grpcio" in result
        assert "1.76.0" not in result

    def test_version_pin_stripped_gte(self):
        ctx = {"runtime_dependencies": ["flask>=2.0.0"]}
        result = _build_available_imports_section(ctx)
        assert "- flask" in result
        assert "2.0.0" not in result

    def test_version_pin_stripped_tilde(self):
        ctx = {"runtime_dependencies": ["requests~=2.28"]}
        result = _build_available_imports_section(ctx)
        assert "- requests" in result
        assert "2.28" not in result

    def test_sorted_output(self):
        ctx = {"runtime_dependencies": ["zebra", "alpha", "middle"]}
        result = _build_available_imports_section(ctx)
        alpha_pos = result.index("alpha")
        middle_pos = result.index("middle")
        zebra_pos = result.index("zebra")
        assert alpha_pos < middle_pos < zebra_pos

    def test_import_instruction_text(self):
        ctx = {"runtime_dependencies": ["flask"]}
        result = _build_available_imports_section(ctx)
        assert "ONLY" in result
        assert "stdlib" in result


class TestAvailableImportsInSpecPrompt:
    def test_survives_in_spec_prompt(self):
        """Available imports should appear at P1 in the assembled spec prompt."""
        ctx = {
            "runtime_dependencies": ["flask", "grpcio"],
            "target_files": ["app.py"],
        }
        prompt = build_spec_prompt("Build a web server", dict(ctx), None)
        assert "flask" in prompt
        assert "grpcio" in prompt
        assert "Available Imports" in prompt

    def test_absent_when_no_deps(self):
        ctx = {"target_files": ["app.py"]}
        prompt = build_spec_prompt("Build a utility", dict(ctx), None)
        assert "Available Imports" not in prompt
