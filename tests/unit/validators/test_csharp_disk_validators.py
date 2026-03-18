"""Tests for C# disk validators — Phase 2 (REQ-CS-200, 201, 202, 203, 500).

Covers:
- .cs file validation (tree-sitter + text fallback)
- .csproj file validation (XML structure)
- .sln file validation (header + project entries)
- C# fingerprint detection in non-CS files
"""

from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import Any, List, Optional


# ---------------------------------------------------------------------------
# Helper: lightweight DiskComplianceResult (avoids importing the full module
# for unit tests — mirrors the real dataclass shape)
# ---------------------------------------------------------------------------

def _make_result(file_path: str = "test.cs"):
    """Create a DiskComplianceResult for testing."""
    from startd8.forward_manifest_validator import DiskComplianceResult
    return DiskComplianceResult(file_path=file_path)


# ---------------------------------------------------------------------------
# .cs file validation (REQ-CS-200)
# ---------------------------------------------------------------------------

class TestCSharpFileValidator:

    def test_valid_cs_with_tree_sitter(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = """
using System;
using Grpc.Core;

namespace cartservice.services
{
    public class CartService
    {
        public void AddItem() { }
    }
}
"""
        result = _validate_csharp_file(code, _make_result())
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_invalid_syntax(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = "public class { broken syntax here"
        result = _validate_csharp_file(code, _make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0

    def test_empty_file(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        result = _validate_csharp_file("", _make_result())
        assert result.ast_valid is False
        assert result.contract_compliance == 0.0
        assert result.error == "empty_file"

    def test_whitespace_only(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        result = _validate_csharp_file("   \n  \n  ", _make_result())
        assert result.ast_valid is False

    def test_python_fingerprint_def(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = "def hello():\n    pass"
        result = _validate_csharp_file(code, _make_result())
        assert result.ast_valid is False
        assert "Python fingerprint" in (result.error or "")

    def test_python_fingerprint_from_future(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = "from __future__ import annotations\nclass Foo: pass"
        result = _validate_csharp_file(code, _make_result())
        assert result.ast_valid is False

    def test_valid_interface(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = """
namespace cartservice.cartstore
{
    public interface ICartStore
    {
        Task AddItemAsync(string userId);
        bool Ping();
    }
}
"""
        result = _validate_csharp_file(code, _make_result())
        assert result.ast_valid is True

    def test_file_scoped_namespace(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = """namespace cartservice.services;

public class CartService
{
    public void AddItem() { }
}
"""
        result = _validate_csharp_file(code, _make_result())
        assert result.ast_valid is True

    def test_valid_async_method(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = """
using System.Threading.Tasks;

namespace X
{
    public class Svc
    {
        public async Task<bool> CheckAsync()
        {
            await Task.Delay(1);
            return true;
        }
    }
}
"""
        result = _validate_csharp_file(code, _make_result())
        assert result.ast_valid is True


# ---------------------------------------------------------------------------
# .csproj file validation (REQ-CS-201)
# ---------------------------------------------------------------------------

class TestCsprojValidator:

    def test_valid_csproj(self):
        from startd8.forward_manifest_validator import _validate_csproj_file
        content = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Grpc.AspNetCore" Version="2.76.0" />
  </ItemGroup>
</Project>
"""
        result = _validate_csproj_file(content, _make_result("cartservice.csproj"))
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_empty_csproj(self):
        from startd8.forward_manifest_validator import _validate_csproj_file
        result = _validate_csproj_file("", _make_result("cartservice.csproj"))
        assert result.ast_valid is False
        assert result.error == "empty_file"

    def test_invalid_xml(self):
        from startd8.forward_manifest_validator import _validate_csproj_file
        content = "<Project><not closed"
        result = _validate_csproj_file(content, _make_result("cartservice.csproj"))
        assert result.ast_valid is False
        assert "xml_parse_error" in (result.error or "")

    def test_missing_project_root(self):
        from startd8.forward_manifest_validator import _validate_csproj_file
        content = "<Configuration><TargetFramework>net8.0</TargetFramework></Configuration>"
        result = _validate_csproj_file(content, _make_result("cartservice.csproj"))
        assert result.ast_valid is False
        assert result.error == "missing_project_root"

    def test_missing_target_framework(self):
        from startd8.forward_manifest_validator import _validate_csproj_file
        content = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
"""
        result = _validate_csproj_file(content, _make_result("cartservice.csproj"))
        assert result.contract_compliance == 0.3

    def test_package_reference_without_include(self):
        from startd8.forward_manifest_validator import _validate_csproj_file
        content = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Version="2.76.0" />
  </ItemGroup>
</Project>
"""
        result = _validate_csproj_file(content, _make_result("cartservice.csproj"))
        assert any(
            "Include" in str(issue.get("message", ""))
            for issue in result.semantic_issues
            if isinstance(issue, dict)
        )

    def test_csproj_with_protobuf_item(self):
        from startd8.forward_manifest_validator import _validate_csproj_file
        content = """<Project Sdk="Microsoft.NET.Sdk.Web">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <Protobuf Include="protos\\Cart.proto" GrpcServices="Both" />
  </ItemGroup>
</Project>
"""
        result = _validate_csproj_file(content, _make_result("cartservice.csproj"))
        assert result.ast_valid is True


# ---------------------------------------------------------------------------
# .sln file validation (REQ-CS-202)
# ---------------------------------------------------------------------------

class TestSlnValidator:

    VALID_SLN = """
Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio 15
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "cartservice", "src\\cartservice.csproj", "{2348C29F-E8D3-4955-916D-D609CBC97FCB}"
EndProject
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "cartservice.tests", "tests\\cartservice.tests.csproj", "{59825342-CE64-4AFA-8744-781692C0811B}"
EndProject
Global
    GlobalSection(SolutionConfigurationPlatforms) = preSolution
        Debug|Any CPU = Debug|Any CPU
        Release|Any CPU = Release|Any CPU
    EndGlobalSection
EndGlobal
"""

    def test_valid_sln(self):
        from startd8.forward_manifest_validator import _validate_sln_file
        result = _validate_sln_file(self.VALID_SLN, _make_result("cartservice.sln"))
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_empty_sln(self):
        from startd8.forward_manifest_validator import _validate_sln_file
        result = _validate_sln_file("", _make_result("cartservice.sln"))
        assert result.ast_valid is False
        assert result.error == "empty_file"

    def test_missing_header(self):
        from startd8.forward_manifest_validator import _validate_sln_file
        content = "Project(\"X\") = \"foo\"\nEndProject\n"
        result = _validate_sln_file(content, _make_result("cartservice.sln"))
        assert result.ast_valid is False
        assert result.error == "missing_solution_header"

    def test_no_projects(self):
        from startd8.forward_manifest_validator import _validate_sln_file
        content = "Microsoft Visual Studio Solution File, Format Version 12.00\nGlobal\nEndGlobal\n"
        result = _validate_sln_file(content, _make_result("cartservice.sln"))
        assert result.contract_compliance == 0.3

    def test_unbalanced_project_endproject(self):
        from startd8.forward_manifest_validator import _validate_sln_file
        content = """
Microsoft Visual Studio Solution File, Format Version 12.00
Project("{X}") = "foo", "foo.csproj", "{ABC}"
Project("{X}") = "bar", "bar.csproj", "{DEF}"
EndProject
"""
        result = _validate_sln_file(content, _make_result("cartservice.sln"))
        assert result.contract_compliance == 0.5


# ---------------------------------------------------------------------------
# C# fingerprint detection (REQ-CS-203)
# ---------------------------------------------------------------------------

class TestCSharpFingerprintDetection:

    def test_csharp_using_in_html(self):
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "using System;\nnamespace X { class Y {} }"
        result = _detect_language_mismatch(content, "/tmp/index.html")
        assert result is not None
        assert "csharp" in result

    def test_csharp_namespace_in_yaml(self):
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "namespace cartservice.services;\npublic class CartService {}"
        result = _detect_language_mismatch(content, "/tmp/config.yaml")
        assert result is not None
        assert "csharp" in result

    def test_csharp_assembly_attr_in_dockerfile(self):
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "[assembly: System.Reflection.AssemblyVersion(\"1.0\")]"
        result = _detect_language_mismatch(content, "/tmp/Dockerfile")
        assert result is not None
        assert "csharp" in result

    def test_no_false_positive_in_cs_file(self):
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "using System;\nnamespace X { class Y {} }"
        result = _detect_language_mismatch(content, "/tmp/Program.cs")
        assert result is None

    def test_no_false_positive_using_in_python(self):
        """'using' is not a Python keyword — but we guard against it."""
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "using System;\nclass Foo {}"
        result = _detect_language_mismatch(content, "/tmp/test.py")
        # .py files are excluded from C# fingerprint check
        assert result is None

    def test_python_class_not_flagged_in_cs(self):
        """'class ' as first code line should not flag .cs files as Python."""
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "class CartService\n{\n    public void Foo() {}\n}"
        result = _detect_language_mismatch(content, "/tmp/CartService.cs")
        assert result is None

    def test_csharp_using_microsoft_in_json(self):
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "using Microsoft.AspNetCore.Builder;\nnamespace X {}"
        result = _detect_language_mismatch(content, "/tmp/appsettings.json")
        assert result is not None
        assert "csharp" in result

    def test_no_false_positive_plain_using_in_yaml(self):
        """A bare 'using' without System/Microsoft should not trigger."""
        from startd8.forward_manifest_validator import _detect_language_mismatch
        content = "using: some_value\nkey: value"
        result = _detect_language_mismatch(content, "/tmp/config.yaml")
        # YAML 'using:' is not 'using System;' — should not match
        assert result is None


# ---------------------------------------------------------------------------
# Postmortem scoring sanity (REQ-CS-500)
# ---------------------------------------------------------------------------

class TestCSharpPostmortemScoring:
    """Verify C# files don't get default 1.0 scores."""

    def test_empty_cs_scores_zero(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        result = _validate_csharp_file("", _make_result())
        assert result.contract_compliance == 0.0

    def test_valid_cs_scores_one(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = "using System;\nnamespace X {\n    public class Foo {}\n}"
        result = _validate_csharp_file(code, _make_result())
        assert result.contract_compliance == 1.0

    def test_invalid_cs_scores_zero(self):
        from startd8.forward_manifest_validator import _validate_csharp_file
        code = "public class { broken"
        result = _validate_csharp_file(code, _make_result())
        assert result.contract_compliance == 0.0
