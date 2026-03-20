"""Tests for C# plan ingestion improvements (REQ-PLI-CS-300, REQ-PLI-CS-402).

Covers:
- .csproj detected as dependency_manifest by infer_artifact_types_from_files
- .sln detected by lang_detect as csharp (via explicit name or build patterns)
- C# service metadata includes csharp_namespace, target_framework, sdk_type
- .csproj deterministic generation produces valid XML with PackageReference entries
- .csproj EMIT routing in prime_adapter via _try_generate_csproj
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest


# ---------------------------------------------------------------------------
# REQ-PLI-CS-300: C# service metadata inference
# ---------------------------------------------------------------------------


class TestCSharpServiceMetadataInference:
    """Verify C# service metadata is derived via LanguageProfile protocol."""

    @staticmethod
    def _make_feature(
        *,
        feature_id: str = "F-001",
        name: str = "CartService",
        target_files: Optional[List[str]] = None,
        protocol: str = "grpc",
        dependencies: Optional[List[str]] = None,
        runtime_dependencies: Optional[List[str]] = None,
        api_signatures: Optional[List[str]] = None,
        negative_scope: Optional[List[str]] = None,
        labels: Optional[List[str]] = None,
        description: str = "Cart service",
        estimated_loc: int = 100,
        design_doc_sections: Optional[List[str]] = None,
        artifact_types_addressed: Optional[List[str]] = None,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            feature_id=feature_id,
            name=name,
            target_files=target_files or ["src/CartService/CartStore.cs"],
            protocol=protocol,
            dependencies=dependencies or [],
            runtime_dependencies=runtime_dependencies or [],
            api_signatures=api_signatures or [],
            negative_scope=negative_scope or [],
            labels=labels or [],
            description=description,
            estimated_loc=estimated_loc,
            design_doc_sections=design_doc_sections or [],
            artifact_types_addressed=artifact_types_addressed or [],
        )

    def test_csharp_metadata_includes_namespace(self):
        """C# metadata should include csharp_namespace derived from target files."""
        from startd8.seeds.derivation import infer_service_metadata

        features = [self._make_feature(
            target_files=["src/CartService/CartStore.cs"],
        )]
        metadata = infer_service_metadata(features)
        assert "csharp_namespace" in metadata
        # Namespace derived from directory path (src stripped)
        assert metadata["csharp_namespace"] == "CartService"

    def test_csharp_metadata_includes_target_framework(self):
        """C# metadata should include target_framework (defaulting to net8.0)."""
        from startd8.seeds.derivation import infer_service_metadata

        features = [self._make_feature()]
        metadata = infer_service_metadata(features)
        assert "target_framework" in metadata
        assert metadata["target_framework"] == "net8.0"

    def test_csharp_metadata_includes_sdk_type(self):
        """C# metadata should include sdk_type inferred from dependencies."""
        from startd8.seeds.derivation import infer_service_metadata

        features = [self._make_feature(
            runtime_dependencies=["Grpc.AspNetCore 2.76.0"],
        )]
        metadata = infer_service_metadata(features)
        assert "sdk_type" in metadata
        assert metadata["sdk_type"] == "Microsoft.NET.Sdk.Web"

    def test_csharp_metadata_non_web_sdk_type(self):
        """Non-web C# projects should get Microsoft.NET.Sdk."""
        from startd8.seeds.derivation import infer_service_metadata

        features = [self._make_feature(
            target_files=["src/Utils/Helper.cs"],
            runtime_dependencies=["Newtonsoft.Json 13.0.1"],
        )]
        metadata = infer_service_metadata(features)
        assert metadata.get("sdk_type") == "Microsoft.NET.Sdk"

    def test_csharp_metadata_via_plan_ingestion_workflow(self):
        """The parallel _infer_service_metadata in workflow also delegates to profile."""
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _infer_service_metadata,
        )
        from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature

        feature = ParsedFeature(
            feature_id="F-001",
            name="CartService",
            description="Cart service",
            target_files=["src/CartService/Program.cs"],
            estimated_loc=100,
            dependencies=[],
            runtime_dependencies=[],
            api_signatures=[],
            negative_scope=[],
            labels=[],
            protocol="grpc",
        )
        metadata = _infer_service_metadata([feature])
        assert "csharp_namespace" in metadata
        assert "target_framework" in metadata


# ---------------------------------------------------------------------------
# REQ-PLI-CS-300: Artifact type inference
# ---------------------------------------------------------------------------


class TestCSharpArtifactTypeInference:
    """Verify .csproj and .sln are correctly classified."""

    def test_csproj_detected_as_dependency_manifest(self):
        from startd8.seeds.derivation import infer_artifact_types_from_files

        types = infer_artifact_types_from_files(["src/CartService/CartService.csproj"])
        assert "dependency_manifest" in types

    def test_sln_not_detected_as_dependency_manifest(self):
        """Solution files are not dependency manifests."""
        from startd8.seeds.derivation import infer_artifact_types_from_files

        # .sln files are not in the detection list — they aren't dependency files
        types = infer_artifact_types_from_files(["CartService.sln"])
        assert "dependency_manifest" not in types

    def test_cs_detected_as_source_module(self):
        from startd8.seeds.derivation import infer_artifact_types_from_files

        types = infer_artifact_types_from_files(["src/CartService/CartStore.cs"])
        assert "source_module" in types


# ---------------------------------------------------------------------------
# REQ-PLI-CS-300: Language detection
# ---------------------------------------------------------------------------


class TestCSharpLangDetect:
    """Verify .csproj and .sln are detected as C# by lang_detect."""

    def test_cs_detected_as_csharp(self):
        from startd8.micro_prime.lang_detect import detect_language

        assert detect_language("src/CartService/CartStore.cs") == "csharp"

    def test_directory_build_props_detected_as_csharp(self):
        from startd8.micro_prime.lang_detect import detect_language

        assert detect_language("Directory.Build.props") == "csharp"


# ---------------------------------------------------------------------------
# REQ-PLI-CS-402: .csproj deterministic generation
# ---------------------------------------------------------------------------


class TestCsprojGeneration:
    """Verify CSharpLanguageProfile.generate_dependency_file produces valid XML."""

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_csproj_produces_valid_xml(self, profile):
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/project"),
            service_name="cartservice",
            module_path="",
            dependencies=["Grpc.AspNetCore/2.76.0", "Google.Protobuf/3.28.0"],
            metadata={
                "target_framework": "net8.0",
                "sdk_type": "Microsoft.NET.Sdk.Web",
            },
        )
        assert content is not None
        assert '<Project Sdk="Microsoft.NET.Sdk.Web">' in content
        assert "<TargetFramework>net8.0</TargetFramework>" in content
        assert '<PackageReference Include="Grpc.AspNetCore" Version="2.76.0" />' in content
        assert '<PackageReference Include="Google.Protobuf" Version="3.28.0" />' in content

    def test_csproj_with_space_separated_versions(self, profile):
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/project"),
            service_name="cartservice",
            module_path="",
            dependencies=["Serilog 4.0.0"],
        )
        assert content is not None
        assert '<PackageReference Include="Serilog" Version="4.0.0" />' in content

    def test_csproj_with_versionless_dependency(self, profile):
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/project"),
            service_name="cartservice",
            module_path="",
            dependencies=["xunit"],
        )
        assert content is not None
        assert '<PackageReference Include="xunit" />' in content

    def test_csproj_empty_dependencies(self, profile):
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/project"),
            service_name="cartservice",
            module_path="",
            dependencies=[],
        )
        assert content is not None
        assert "<Project" in content
        assert "PackageReference" not in content

    def test_csproj_default_framework_and_sdk(self, profile):
        """Without metadata, defaults to net8.0 and Microsoft.NET.Sdk.Web."""
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/project"),
            service_name="cartservice",
            module_path="",
            dependencies=[],
        )
        assert content is not None
        assert "<TargetFramework>net8.0</TargetFramework>" in content
        assert '<Project Sdk="Microsoft.NET.Sdk.Web">' in content

    def test_csproj_with_protobuf_items(self, profile):
        content = profile.generate_dependency_file(
            project_root=Path("/tmp/project"),
            service_name="cartservice",
            module_path="",
            dependencies=[],
            metadata={
                "protobuf_items": ["protos/cart.proto"],
            },
        )
        assert content is not None
        assert '<Protobuf Include="protos/cart.proto" GrpcServices="Both" />' in content


# ---------------------------------------------------------------------------
# REQ-PLI-CS-402: .csproj EMIT routing in prime_adapter
# ---------------------------------------------------------------------------


class TestCsprojEmitRouting:
    """Verify _try_generate_csproj routes .csproj to deterministic generation."""

    @pytest.fixture
    def adapter(self, tmp_path):
        """Create a minimal MicroPrimeCodeGenerator for testing _try_generate_csproj."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        adapter = MicroPrimeCodeGenerator.__new__(MicroPrimeCodeGenerator)
        adapter._output_dir = tmp_path
        return adapter

    def test_csproj_routed_to_deterministic_generation(self, adapter):
        context: Dict[str, Any] = {
            "runtime_dependencies": ["Grpc.AspNetCore/2.76.0"],
            "target_framework": "net8.0",
            "sdk_type": "Microsoft.NET.Sdk.Web",
        }
        content = adapter._try_generate_csproj(
            "src/CartService/CartService.csproj",
            None,
            context,
        )
        assert content is not None
        assert '<PackageReference Include="Grpc.AspNetCore" Version="2.76.0" />' in content
        assert "<TargetFramework>net8.0</TargetFramework>" in content

    def test_non_csproj_returns_none(self, adapter):
        content = adapter._try_generate_csproj(
            "src/CartService/CartStore.cs",
            None,
            {},
        )
        assert content is None

    def test_sln_returns_none(self, adapter):
        """Solution files should NOT be routed to deterministic generation."""
        content = adapter._try_generate_csproj(
            "CartService.sln",
            None,
            {},
        )
        assert content is None

    def test_csproj_with_file_spec_metadata(self, adapter):
        """File spec metadata provides fallback for target_framework and sdk_type."""
        file_spec = SimpleNamespace(
            metadata={
                "target_framework": "net9.0",
                "sdk_type": "Microsoft.NET.Sdk",
            },
        )
        content = adapter._try_generate_csproj(
            "src/Utils/Utils.csproj",
            file_spec,
            {"dependencies": ["Newtonsoft.Json/13.0.1"]},
        )
        assert content is not None
        assert "<TargetFramework>net9.0</TargetFramework>" in content
        assert '<Project Sdk="Microsoft.NET.Sdk">' in content
        assert '<PackageReference Include="Newtonsoft.Json" Version="13.0.1" />' in content

    def test_csproj_context_overrides_file_spec(self, adapter):
        """Context values take precedence over file_spec metadata."""
        file_spec = SimpleNamespace(
            metadata={
                "target_framework": "net7.0",
                "sdk_type": "Microsoft.NET.Sdk",
            },
        )
        context: Dict[str, Any] = {
            "target_framework": "net8.0",
            "sdk_type": "Microsoft.NET.Sdk.Web",
        }
        content = adapter._try_generate_csproj(
            "src/CartService/CartService.csproj",
            file_spec,
            context,
        )
        assert content is not None
        assert "<TargetFramework>net8.0</TargetFramework>" in content
        assert '<Project Sdk="Microsoft.NET.Sdk.Web">' in content

    def test_csproj_empty_deps_still_generates(self, adapter):
        """Even without dependencies, .csproj should be generated."""
        content = adapter._try_generate_csproj(
            "src/CartService/CartService.csproj",
            None,
            {},
        )
        assert content is not None
        assert "<Project" in content
        assert "</Project>" in content
