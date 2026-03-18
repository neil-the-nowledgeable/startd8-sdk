"""Tests for C# template generation & seed enrichment — Phase 4 (REQ-CS-103, 104, 105, 600, 601, 602).

Covers:
- .csproj template generation (dependency formats, sdk_type, protobuf)
- .sln template generation (header, GUIDs, project entries)
- Dockerfile context in project context section
- Proto context in project context section
- derive_service_metadata for C# projects
"""

from __future__ import annotations

import pytest
from pathlib import Path


@pytest.fixture
def profile():
    from startd8.languages.csharp import CSharpLanguageProfile
    return CSharpLanguageProfile()


# ---------------------------------------------------------------------------
# .csproj template generation (REQ-CS-103)
# ---------------------------------------------------------------------------

class TestCsprojTemplateGeneration:

    def test_basic_csproj(self, profile):
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=[],
        )
        assert '<Project Sdk="Microsoft.NET.Sdk.Web">' in result
        assert "<TargetFramework>" in result
        assert "</Project>" in result

    def test_custom_target_framework(self, profile):
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=[],
            metadata={"target_framework": "net10.0"},
        )
        assert "<TargetFramework>net10.0</TargetFramework>" in result

    def test_custom_sdk_type(self, profile):
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice.tests",
            module_path="",
            dependencies=[],
            metadata={"sdk_type": "Microsoft.NET.Sdk"},
        )
        assert '<Project Sdk="Microsoft.NET.Sdk">' in result

    def test_slash_version_deps(self, profile):
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=["Grpc.AspNetCore/2.76.0", "Npgsql/10.0.1"],
        )
        assert 'Include="Grpc.AspNetCore" Version="2.76.0"' in result
        assert 'Include="Npgsql" Version="10.0.1"' in result

    def test_space_version_deps(self, profile):
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=["Grpc.AspNetCore 2.76.0", "Npgsql 10.0.1"],
        )
        assert 'Include="Grpc.AspNetCore" Version="2.76.0"' in result
        assert 'Include="Npgsql" Version="10.0.1"' in result

    def test_no_version_deps(self, profile):
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=["Grpc.AspNetCore"],
        )
        assert 'Include="Grpc.AspNetCore"' in result
        assert 'Version=' not in result.split("Grpc.AspNetCore")[1].split("/>")[0] or \
               'Version="' not in result  # no version attribute

    def test_protobuf_items(self, profile):
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=["Grpc.AspNetCore/2.76.0"],
            metadata={"protobuf_items": ["protos\\Cart.proto"]},
        )
        assert 'Protobuf Include="protos\\Cart.proto"' in result
        assert 'GrpcServices="Both"' in result

    def test_full_cartservice_csproj(self, profile):
        """Full cartservice .csproj matching requirements."""
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=[
                "Grpc.AspNetCore 2.76.0",
                "Grpc.HealthCheck 2.76.0",
                "Microsoft.Extensions.Caching.StackExchangeRedis 10.0.2",
                "Google.Cloud.Spanner.Data 5.12.0",
                "Npgsql 10.0.1",
                "Google.Cloud.SecretManager.V1 2.7.0",
            ],
            metadata={
                "target_framework": "net10.0",
                "sdk_type": "Microsoft.NET.Sdk.Web",
                "protobuf_items": ["protos\\Cart.proto"],
            },
        )
        assert "<TargetFramework>net10.0</TargetFramework>" in result
        assert 'Include="Grpc.AspNetCore" Version="2.76.0"' in result
        assert 'Include="Npgsql" Version="10.0.1"' in result
        assert 'Protobuf Include="protos\\Cart.proto"' in result
        assert '<Project Sdk="Microsoft.NET.Sdk.Web">' in result


# ---------------------------------------------------------------------------
# .sln template generation (REQ-CS-104)
# ---------------------------------------------------------------------------

class TestSlnTemplateGeneration:

    def test_basic_sln(self, profile):
        result = profile.generate_solution_file(
            solution_name="cartservice",
            projects=[
                {
                    "name": "cartservice",
                    "path": "src\\cartservice.csproj",
                    "guid": "{2348C29F-E8D3-4955-916D-D609CBC97FCB}",
                },
            ],
        )
        assert "Microsoft Visual Studio Solution File" in result
        assert "Format Version 12.00" in result
        assert '"cartservice"' in result
        assert "{2348C29F-E8D3-4955-916D-D609CBC97FCB}" in result
        assert "EndProject" in result

    def test_sln_two_projects(self, profile):
        result = profile.generate_solution_file(
            solution_name="cartservice",
            projects=[
                {
                    "name": "cartservice",
                    "path": "src\\cartservice.csproj",
                    "guid": "{2348C29F-E8D3-4955-916D-D609CBC97FCB}",
                },
                {
                    "name": "cartservice.tests",
                    "path": "tests\\cartservice.tests.csproj",
                    "guid": "{59825342-CE64-4AFA-8744-781692C0811B}",
                },
            ],
        )
        assert result.count("Project(") == 2
        assert result.count("EndProject") == 2
        assert "cartservice.tests" in result
        assert "{59825342-CE64-4AFA-8744-781692C0811B}" in result

    def test_sln_contains_config_platforms(self, profile):
        result = profile.generate_solution_file(
            solution_name="test",
            projects=[{"name": "p", "path": "p.csproj", "guid": "{A}"}],
        )
        assert "SolutionConfigurationPlatforms" in result
        assert "Debug|Any CPU" in result
        assert "Release|Any CPU" in result

    def test_sln_contains_project_config_platforms(self, profile):
        result = profile.generate_solution_file(
            solution_name="test",
            projects=[{"name": "p", "path": "p.csproj", "guid": "{A}"}],
        )
        assert "ProjectConfigurationPlatforms" in result
        assert "{A}.Debug|Any CPU.ActiveCfg" in result
        assert "{A}.Debug|Any CPU.Build.0" in result

    def test_sln_uses_csharp_project_type_guid(self, profile):
        result = profile.generate_solution_file(
            solution_name="test",
            projects=[{"name": "p", "path": "p.csproj", "guid": "{A}"}],
        )
        assert "FAE04EC0-301F-11D3-BF4B-00C04F79EFBC" in result

    def test_sln_header_format(self, profile):
        result = profile.generate_solution_file(
            solution_name="test",
            projects=[{"name": "p", "path": "p.csproj", "guid": "{A}"}],
        )
        assert "EndGlobal" in result
        lines = result.strip().splitlines()
        assert lines[-1] == "EndGlobal"


# ---------------------------------------------------------------------------
# Dockerfile context (REQ-CS-601)
# ---------------------------------------------------------------------------

class TestDockerfileContext:

    def test_dockerfile_context_included(self, profile):
        section = profile.build_project_context_section({
            "target_files": ["src/Dockerfile"],
        })
        assert "Dockerfile" in section
        assert "dotnet" in section.lower()
        assert "dotnet restore" in section or "dotnet publish" in section
        assert "USER 1000" in section

    def test_dockerfile_context_not_included_without_dockerfile(self, profile):
        section = profile.build_project_context_section({
            "target_files": ["src/CartService.cs"],
        })
        assert "Dockerfile patterns" not in section

    def test_dockerfile_context_includes_csproj_name(self, profile):
        section = profile.build_project_context_section({
            "target_files": ["src/Dockerfile"],
            "service_metadata": {"csproj_name": "cartservice.csproj"},
        })
        assert "cartservice.csproj" in section


# ---------------------------------------------------------------------------
# Proto context (REQ-CS-602)
# ---------------------------------------------------------------------------

class TestProtoContext:

    def test_proto_context_included(self, profile):
        section = profile.build_project_context_section({
            "target_files": ["src/protos/Cart.proto"],
        })
        assert "proto" in section.lower()
        assert "proto3" in section
        assert "snake_case" in section

    def test_proto_context_not_included_without_proto(self, profile):
        section = profile.build_project_context_section({
            "target_files": ["src/CartService.cs"],
        })
        assert "Proto file patterns" not in section


# ---------------------------------------------------------------------------
# derive_service_metadata (REQ-CS-600)
# ---------------------------------------------------------------------------

class TestDeriveServiceMetadata:

    def test_default_target_framework(self, profile):
        from types import SimpleNamespace
        features = [SimpleNamespace(target_files=["CartService.cs"])]
        meta = profile.derive_service_metadata(features)
        assert "target_framework" in meta

    def test_explicit_target_framework(self, profile):
        from types import SimpleNamespace
        features = [SimpleNamespace(
            target_files=["CartService.cs"],
            target_framework="net10.0",
        )]
        meta = profile.derive_service_metadata(features)
        assert meta["target_framework"] == "net10.0"

    def test_sdk_type_web_for_grpc_deps(self, profile):
        from types import SimpleNamespace
        features = [SimpleNamespace(target_files=["CartService.cs"])]
        meta = profile.derive_service_metadata(
            features,
            runtime_dependencies=["Grpc.AspNetCore 2.76.0"],
        )
        assert meta.get("sdk_type") == "Microsoft.NET.Sdk.Web"

    def test_sdk_type_web_for_startup_file(self, profile):
        from types import SimpleNamespace
        features = [SimpleNamespace(
            target_files=["Startup.cs", "Program.cs"],
        )]
        meta = profile.derive_service_metadata(features)
        assert meta.get("sdk_type") == "Microsoft.NET.Sdk.Web"

    def test_namespace_derived_from_file_path(self, profile):
        from types import SimpleNamespace
        features = [SimpleNamespace(
            target_files=["src/cartservice/src/services/CartService.cs"],
        )]
        meta = profile.derive_service_metadata(features)
        assert meta.get("csharp_namespace") == "cartservice.services"
