"""Tests for L5: framework import templates."""

import pytest

from startd8.implementation_engine.framework_imports import (
    FRAMEWORK_IMPORTS,
    detect_frameworks,
    get_import_preamble,
)
from startd8.implementation_engine.spec_builder import build_spec_prompt


class TestDetectFrameworks:
    def test_grpc_from_dependencies(self):
        result = detect_frameworks(dependencies=["grpcio==1.76.0"])
        assert "grpc" in result

    def test_locust_from_description(self):
        result = detect_frameworks(task_description="Locust traffic simulation tests")
        assert "locust" in result

    def test_flask_from_dependencies(self):
        result = detect_frameworks(dependencies=["flask>=2.0"])
        assert "flask" in result

    def test_otel_from_dependencies(self):
        result = detect_frameworks(dependencies=["opentelemetry-api", "opentelemetry-sdk"])
        assert "opentelemetry" in result

    def test_multiple_frameworks(self):
        result = detect_frameworks(
            dependencies=["grpcio", "opentelemetry-api"],
        )
        assert "grpc" in result
        assert "opentelemetry" in result

    def test_no_framework_detected(self):
        result = detect_frameworks(
            task_description="Simple utility function",
            dependencies=["requests"],
        )
        assert result == []

    def test_case_insensitive_description(self):
        result = detect_frameworks(task_description="Build a FLASK web server")
        assert "flask" in result

    def test_fastapi_from_dependencies(self):
        result = detect_frameworks(dependencies=["fastapi"])
        assert "fastapi" in result

    def test_empty_inputs(self):
        result = detect_frameworks()
        assert result == []

    def test_sorted_output(self):
        result = detect_frameworks(dependencies=["grpcio", "flask", "opentelemetry-api"])
        assert result == sorted(result)


class TestGetImportPreamble:
    def test_grpc_preamble(self):
        result = get_import_preamble(["grpc"])
        assert "import grpc" in result
        assert "from concurrent import futures" in result

    def test_locust_preamble(self):
        result = get_import_preamble(["locust"])
        assert "FastHttpUser" in result

    def test_flask_preamble(self):
        result = get_import_preamble(["flask"])
        assert "from flask import Flask" in result

    def test_otel_preamble(self):
        result = get_import_preamble(["opentelemetry"])
        assert "TracerProvider" in result

    def test_conditional_imports_included(self):
        """OTel in deps + gRPC detected → OTel conditional imports added."""
        result = get_import_preamble(
            ["grpc"],
            dependencies=["grpcio", "opentelemetry-api"],
        )
        assert "GrpcInstrumentorServer" in result

    def test_conditional_imports_excluded(self):
        """No OTel in deps → OTel conditional imports NOT added."""
        result = get_import_preamble(["grpc"], dependencies=["grpcio"])
        assert "GrpcInstrumentorServer" not in result

    def test_empty_frameworks(self):
        result = get_import_preamble([])
        assert result == ""

    def test_unknown_framework_ignored(self):
        result = get_import_preamble(["nonexistent"])
        # Should not crash, just produce header without content
        assert "Framework Import Templates" in result

    def test_multiple_frameworks_preamble(self):
        result = get_import_preamble(["flask", "opentelemetry"])
        assert "flask" in result.lower()
        assert "opentelemetry" in result.lower()


class TestPreambleNote:
    """REQ-PI-CS-101: preamble_note rendering in get_import_preamble."""

    def test_preamble_note_rendered_after_imports(self):
        """When a framework config has preamble_note, it appears in the output."""
        from startd8.languages.csharp import CSharpLanguageProfile
        profile = CSharpLanguageProfile()
        frameworks = detect_frameworks(
            dependencies=["Grpc.AspNetCore 2.76.0"],
            language_profile=profile,
        )
        preamble = get_import_preamble(
            frameworks,
            dependencies=["Grpc.AspNetCore 2.76.0"],
            language_profile=profile,
        )
        # preamble_note contains ILogger pattern
        assert "ILogger<T>" in preamble or "ILogger<MyService>" in preamble

    def test_no_preamble_note_no_extra_block(self):
        """Python frameworks have no preamble_note — output stays unchanged."""
        preamble = get_import_preamble(["flask"])
        # Count code blocks — should be exactly 1 (the imports block)
        assert preamble.count("```python") == 1
        assert "ILogger" not in preamble

    def test_aspnet_core_preamble_note(self):
        """ASP.NET Core framework includes ILogger preamble_note."""
        from startd8.languages.csharp import CSharpLanguageProfile
        profile = CSharpLanguageProfile()
        frameworks = detect_frameworks(
            task_description="ASP.NET Core web API",
            language_profile=profile,
        )
        assert "aspnet_core" in frameworks
        preamble = get_import_preamble(
            frameworks,
            language_profile=profile,
        )
        assert "ILogger" in preamble
        # Should have two csharp code blocks: imports + preamble_note
        assert preamble.count("```csharp") >= 2


class TestFrameworkImportsInSpecPrompt:
    def test_preamble_injected_into_spec(self):
        """Integration test: framework imports appear in assembled spec prompt."""
        ctx = {
            "runtime_dependencies": ["grpcio==1.76.0", "flask"],
            "target_files": ["server.py"],
        }
        prompt = build_spec_prompt("Build a gRPC server", dict(ctx), None)
        assert "import grpc" in prompt
        assert "Framework Import Templates" in prompt

    def test_no_preamble_without_frameworks(self):
        ctx = {
            "runtime_dependencies": ["requests"],
            "target_files": ["util.py"],
        }
        prompt = build_spec_prompt("Build a utility", dict(ctx), None)
        assert "Framework Import Templates" not in prompt
