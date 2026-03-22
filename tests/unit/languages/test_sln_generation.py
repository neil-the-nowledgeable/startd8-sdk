"""Tests for .sln deterministic generation routing (REQ-PLI-CS-404).

Validates that:
- CSharpLanguageProfile.generate_solution_file() produces valid .sln content
- _try_generate_sln() routes correctly in the prime adapter
- _try_generate_csproj() routes correctly in the prime adapter
- Deterministic UUIDs are reproducible
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from startd8.languages.csharp import CSharpLanguageProfile


# ---------------------------------------------------------------------------
# generate_solution_file() tests
# ---------------------------------------------------------------------------


class TestGenerateSolutionFile:
    """Test CSharpLanguageProfile.generate_solution_file()."""

    def setup_method(self):
        self.profile = CSharpLanguageProfile()

    def test_single_project(self):
        projects = [{
            "name": "CartService",
            "path": "src/CartService/CartService.csproj",
            "guid": "{11111111-1111-1111-1111-111111111111}",
        }]
        content = self.profile.generate_solution_file("CartService", projects)

        assert "Microsoft Visual Studio Solution File" in content
        assert "CartService" in content
        assert "{11111111-1111-1111-1111-111111111111}" in content
        assert "src/CartService/CartService.csproj" in content
        assert "EndProject" in content
        assert "Global" in content
        assert "EndGlobal" in content

    def test_multi_project(self):
        projects = [
            {
                "name": "Api",
                "path": "src/Api/Api.csproj",
                "guid": "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}",
            },
            {
                "name": "Core",
                "path": "src/Core/Core.csproj",
                "guid": "{BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB}",
            },
        ]
        content = self.profile.generate_solution_file("MySolution", projects)

        assert content.count("EndProject") == 2
        assert "Api.csproj" in content
        assert "Core.csproj" in content
        # Should have config platforms for both projects
        assert "{AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA}" in content
        assert "{BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB}" in content

    def test_visual_studio_format_header(self):
        projects = [{
            "name": "Test",
            "path": "Test.csproj",
            "guid": "{00000000-0000-0000-0000-000000000000}",
        }]
        content = self.profile.generate_solution_file("Test", projects)

        lines = content.split("\n")
        # First non-empty line should be the format header
        non_empty = [l for l in lines if l.strip()]
        assert non_empty[0] == "Microsoft Visual Studio Solution File, Format Version 12.00"
        assert non_empty[1] == "# Visual Studio 15"

    def test_guid_format_in_output(self):
        """GUIDs in .sln should be wrapped in braces."""
        guid = "{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}"
        projects = [{
            "name": "Test",
            "path": "Test.csproj",
            "guid": "{12345678-1234-1234-1234-123456789ABC}",
        }]
        content = self.profile.generate_solution_file("Test", projects)

        # C# project type GUID should be present
        assert guid in content
        # Project GUID should be present
        assert "{12345678-1234-1234-1234-123456789ABC}" in content

    def test_configuration_platforms(self):
        """Should contain Debug and Release configuration platforms."""
        projects = [{
            "name": "Test",
            "path": "Test.csproj",
            "guid": "{00000000-0000-0000-0000-000000000000}",
        }]
        content = self.profile.generate_solution_file("Test", projects)

        assert "Debug|Any CPU" in content
        assert "Release|Any CPU" in content
        assert "SolutionConfigurationPlatforms" in content
        assert "ProjectConfigurationPlatforms" in content


# ---------------------------------------------------------------------------
# _try_generate_sln() routing tests
# ---------------------------------------------------------------------------


class TestSlnRouting:
    """Test _try_generate_sln() routing in MicroPrimeCodeGenerator."""

    def _make_gen(self, output_dir):
        """Create a minimal MicroPrimeCodeGenerator for testing."""
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        gen = MicroPrimeCodeGenerator(output_dir=output_dir)
        return gen

    def test_non_sln_returns_none(self, tmp_path):
        gen = self._make_gen(tmp_path)
        result = gen._try_generate_sln("foo.cs", None, {})
        assert result is None

    def test_sln_with_no_csproj_returns_none(self, tmp_path):
        gen = self._make_gen(tmp_path)
        context = {"target_files": ["foo.cs", "bar.cs"]}
        result = gen._try_generate_sln("MySolution.sln", None, context)
        assert result is None

    def test_sln_with_csproj_generates_content(self, tmp_path):
        gen = self._make_gen(tmp_path)
        context = {
            "all_target_files": [
                "src/CartService/CartService.csproj",
                "src/CartService/CartStore.cs",
            ],
            "service_name": "CartService",
        }
        result = gen._try_generate_sln("CartService.sln", None, context)
        assert result is not None
        assert "Microsoft Visual Studio Solution File" in result
        assert "CartService" in result

    def test_sln_deterministic_guids(self, tmp_path):
        """GUIDs should be deterministic (uuid5-based) and reproducible."""
        gen = self._make_gen(tmp_path)
        context = {
            "all_target_files": ["src/Api/Api.csproj"],
        }
        result1 = gen._try_generate_sln("App.sln", None, context)
        result2 = gen._try_generate_sln("App.sln", None, context)
        assert result1 == result2

    def test_sln_multi_csproj(self, tmp_path):
        gen = self._make_gen(tmp_path)
        context = {
            "all_target_files": [
                "src/Api/Api.csproj",
                "src/Core/Core.csproj",
                "src/Tests/Tests.csproj",
            ],
        }
        result = gen._try_generate_sln("MySolution.sln", None, context)
        assert result is not None
        assert result.count("EndProject") == 3


# ---------------------------------------------------------------------------
# _try_generate_csproj() routing tests
# ---------------------------------------------------------------------------


class TestCsprojRouting:
    """Test _try_generate_csproj() routing in MicroPrimeCodeGenerator."""

    def _make_gen(self, output_dir):
        from startd8.micro_prime.prime_adapter import MicroPrimeCodeGenerator

        return MicroPrimeCodeGenerator(output_dir=output_dir)

    def test_non_csproj_returns_none(self, tmp_path):
        gen = self._make_gen(tmp_path)
        result = gen._try_generate_csproj("foo.cs", None, {})
        assert result is None

    def test_csproj_generates_xml(self, tmp_path):
        gen = self._make_gen(tmp_path)
        context = {
            "dependencies": ["Grpc.AspNetCore/2.76.0", "Google.Protobuf"],
            "target_framework": "net8.0",
        }
        result = gen._try_generate_csproj(
            "src/CartService/CartService.csproj", None, context,
        )
        assert result is not None
        assert "<Project" in result
        assert "Grpc.AspNetCore" in result
        assert "net8.0" in result

    def test_csproj_empty_deps(self, tmp_path):
        gen = self._make_gen(tmp_path)
        context: dict = {}
        result = gen._try_generate_csproj(
            "src/Service/Service.csproj", None, context,
        )
        # Should still generate a valid csproj even without deps
        assert result is not None
        assert "<Project" in result
