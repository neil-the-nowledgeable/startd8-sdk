"""Tests for C# framework detection & system prompts — Phase 3 (REQ-CS-102, 400, 401, 402).

Covers:
- Framework detection for C# dependencies
- Import preamble uses csharp code fence
- System prompt contains C# role and coding standards
- Namespace derivation from file paths
- Project context section generation
- Dependency version stripping
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Framework detection (REQ-CS-400)
# ---------------------------------------------------------------------------

class TestCSharpFrameworkDetection:

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_detect_grpc_from_dependency(self, profile):
        from startd8.implementation_engine.framework_imports import detect_frameworks
        frameworks = detect_frameworks(
            dependencies=["Grpc.AspNetCore 2.76.0"],
            language_profile=profile,
        )
        assert "grpc" in frameworks

    def test_detect_redis_from_dependency(self, profile):
        from startd8.implementation_engine.framework_imports import detect_frameworks
        frameworks = detect_frameworks(
            dependencies=["Microsoft.Extensions.Caching.StackExchangeRedis 10.0.2"],
            language_profile=profile,
        )
        assert "redis" in frameworks

    def test_detect_spanner_from_dependency(self, profile):
        from startd8.implementation_engine.framework_imports import detect_frameworks
        frameworks = detect_frameworks(
            dependencies=["Google.Cloud.Spanner.Data 5.12.0"],
            language_profile=profile,
        )
        assert "spanner" in frameworks

    def test_detect_npgsql_from_dependency(self, profile):
        from startd8.implementation_engine.framework_imports import detect_frameworks
        frameworks = detect_frameworks(
            dependencies=["Npgsql 10.0.1"],
            language_profile=profile,
        )
        assert "npgsql" in frameworks

    def test_detect_xunit_from_description(self, profile):
        from startd8.implementation_engine.framework_imports import detect_frameworks
        frameworks = detect_frameworks(
            task_description="xUnit integration tests for CartService",
            language_profile=profile,
        )
        assert "xunit" in frameworks

    def test_detect_grpc_from_description(self, profile):
        from startd8.implementation_engine.framework_imports import detect_frameworks
        frameworks = detect_frameworks(
            task_description="gRPC service implementing CartService proto",
            language_profile=profile,
        )
        assert "grpc" in frameworks

    def test_detect_multiple_frameworks(self, profile):
        from startd8.implementation_engine.framework_imports import detect_frameworks
        frameworks = detect_frameworks(
            dependencies=[
                "Grpc.AspNetCore 2.76.0",
                "Google.Cloud.Spanner.Data 5.12.0",
                "Npgsql 10.0.1",
            ],
            language_profile=profile,
        )
        assert "grpc" in frameworks
        assert "spanner" in frameworks
        assert "npgsql" in frameworks


# ---------------------------------------------------------------------------
# Import preamble (REQ-CS-401)
# ---------------------------------------------------------------------------

class TestCSharpImportPreamble:

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_preamble_uses_csharp_fence(self, profile):
        from startd8.implementation_engine.framework_imports import (
            detect_frameworks, get_import_preamble,
        )
        frameworks = detect_frameworks(
            dependencies=["Grpc.AspNetCore 2.76.0"],
            language_profile=profile,
        )
        preamble = get_import_preamble(
            frameworks, dependencies=["Grpc.AspNetCore 2.76.0"],
            language_profile=profile,
        )
        assert "```csharp" in preamble
        assert "```python" not in preamble

    def test_preamble_contains_using_directives(self, profile):
        from startd8.implementation_engine.framework_imports import (
            detect_frameworks, get_import_preamble,
        )
        frameworks = detect_frameworks(
            dependencies=["Grpc.AspNetCore 2.76.0"],
            language_profile=profile,
        )
        preamble = get_import_preamble(
            frameworks, dependencies=["Grpc.AspNetCore 2.76.0"],
            language_profile=profile,
        )
        assert "using Grpc.Core;" in preamble

    def test_preamble_redis(self, profile):
        from startd8.implementation_engine.framework_imports import (
            detect_frameworks, get_import_preamble,
        )
        frameworks = detect_frameworks(
            dependencies=["Microsoft.Extensions.Caching.StackExchangeRedis 10.0.2"],
            language_profile=profile,
        )
        preamble = get_import_preamble(
            frameworks,
            dependencies=["Microsoft.Extensions.Caching.StackExchangeRedis 10.0.2"],
            language_profile=profile,
        )
        assert "using Microsoft.Extensions.Caching.Distributed;" in preamble

    def test_preamble_empty_when_no_frameworks(self, profile):
        from startd8.implementation_engine.framework_imports import get_import_preamble
        preamble = get_import_preamble([], language_profile=profile)
        assert preamble == ""


# ---------------------------------------------------------------------------
# System prompt role & coding standards (REQ-CS-102)
# ---------------------------------------------------------------------------

class TestCSharpSystemPrompt:

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_system_prompt_role_contains_csharp(self, profile):
        role = profile.system_prompt_role
        assert "C#" in role or ".NET" in role

    def test_coding_standards_mentions_async(self, profile):
        standards = profile.coding_standards
        assert "async" in standards.lower()

    def test_coding_standards_mentions_pascal_case(self, profile):
        standards = profile.coding_standards
        assert "PascalCase" in standards

    def test_drafter_system_prompt_with_csharp_role(self):
        from startd8.implementation_engine.drafter import get_drafter_system_prompt
        prompt, mode = get_drafter_system_prompt(
            language_role="an expert C# / .NET engineer",
            coding_standards="PascalCase, async/await, DI patterns",
        )
        assert "C# / .NET" in prompt
        assert "PascalCase" in prompt
        assert "python" not in prompt.lower() or "Python" not in prompt

    def test_drafter_defaults_to_python_without_role(self):
        from startd8.implementation_engine.drafter import get_drafter_system_prompt
        prompt, mode = get_drafter_system_prompt()
        assert "Python" in prompt or "python" in prompt.lower()


# ---------------------------------------------------------------------------
# Namespace derivation (REQ-CS-105)
# ---------------------------------------------------------------------------

class TestNamespaceDerivation:

    def test_cartservice_cartstore(self):
        from startd8.languages.csharp import _derive_namespace
        assert _derive_namespace(
            "src/cartservice/src/cartstore/RedisCartStore.cs"
        ) == "cartservice.cartstore"

    def test_cartservice_services(self):
        from startd8.languages.csharp import _derive_namespace
        assert _derive_namespace(
            "src/cartservice/src/services/CartService.cs"
        ) == "cartservice.services"

    def test_root_level_file(self):
        from startd8.languages.csharp import _derive_namespace
        assert _derive_namespace(
            "src/cartservice/src/Program.cs"
        ) == "cartservice"

    def test_no_src_prefix(self):
        from startd8.languages.csharp import _derive_namespace
        assert _derive_namespace("Services/UserService.cs") == "Services"

    def test_bare_file(self):
        from startd8.languages.csharp import _derive_namespace
        assert _derive_namespace("Program.cs") == ""

    def test_multiple_src_dirs(self):
        from startd8.languages.csharp import _derive_namespace
        ns = _derive_namespace("src/myapp/src/models/User.cs")
        assert ns == "myapp.models"
        assert "src" not in ns


# ---------------------------------------------------------------------------
# Project context section (REQ-CS-402)
# ---------------------------------------------------------------------------

class TestProjectContextSection:

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_contains_namespace(self, profile):
        section = profile.build_project_context_section({
            "csharp_namespace": "cartservice.services",
        })
        assert "cartservice.services" in section
        assert "namespace" in section.lower()

    def test_contains_target_framework(self, profile):
        section = profile.build_project_context_section({
            "target_framework": "net10.0",
        })
        assert "net10.0" in section

    def test_contains_using_rules(self, profile):
        section = profile.build_project_context_section({})
        assert "using" in section.lower()
        assert "System" in section

    def test_contains_structural_rules(self, profile):
        section = profile.build_project_context_section({})
        assert "PascalCase" in section
        assert "async" in section.lower()

    def test_derives_namespace_from_target_files(self, profile):
        section = profile.build_project_context_section({
            "target_files": ["src/cartservice/src/cartstore/RedisCartStore.cs"],
        })
        assert "cartservice.cartstore" in section

    def test_uses_service_metadata_fallback(self, profile):
        section = profile.build_project_context_section({
            "service_metadata": {
                "csharp_namespace": "cartservice.services",
                "target_framework": "net10.0",
            },
        })
        assert "cartservice.services" in section
        assert "net10.0" in section


# ---------------------------------------------------------------------------
# Dependency version stripping
# ---------------------------------------------------------------------------

class TestDependencyVersionStripping:

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_slash_format(self, profile):
        assert profile.strip_dependency_version("Grpc.AspNetCore/2.76.0") == "Grpc.AspNetCore"

    def test_space_format(self, profile):
        assert profile.strip_dependency_version("Grpc.AspNetCore 2.76.0") == "Grpc.AspNetCore"

    def test_no_version(self, profile):
        assert profile.strip_dependency_version("Npgsql") == "Npgsql"

    def test_empty(self, profile):
        assert profile.strip_dependency_version("") == ""
