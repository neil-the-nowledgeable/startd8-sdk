"""Tests for C# file-scoped namespace detection (REQ-KZ-CS-500b)."""

import pytest

from startd8.validators.semantic_checks import (
    SemanticIssue,
    check_block_scoped_namespace,
)


# ---------------------------------------------------------------------------
# check_block_scoped_namespace (semantic_checks.py)
# ---------------------------------------------------------------------------


class TestBlockScopedNamespace:
    """Verify block-scoped namespace detection in C# files."""

    def test_block_scoped_detected(self):
        source = (
            "using System;\n"
            "\n"
            "namespace cartservice.cartstore {\n"
            "    public class RedisCartStore { }\n"
            "}\n"
        )
        issues = check_block_scoped_namespace(source, file_path="RedisCartStore.cs")
        assert len(issues) == 1
        issue = issues[0]
        assert issue.check == "block_scoped_namespace"
        assert issue.severity == "info"
        assert "file-scoped" in issue.message
        assert issue.line == 3
        assert issue.file_path == "RedisCartStore.cs"

    def test_file_scoped_clean(self):
        source = (
            "using System;\n"
            "\n"
            "namespace cartservice.cartstore;\n"
            "\n"
            "public class RedisCartStore { }\n"
        )
        issues = check_block_scoped_namespace(source, file_path="RedisCartStore.cs")
        assert issues == []

    def test_non_csharp_file_skipped(self):
        source = "namespace foo {\n}\n"
        issues = check_block_scoped_namespace(source, file_path="main.py")
        assert issues == []

    def test_no_namespace_at_all(self):
        source = "public class Foo { }\n"
        issues = check_block_scoped_namespace(source, file_path="Foo.cs")
        assert issues == []


# ---------------------------------------------------------------------------
# CSharpLanguageProfile.build_project_context_section
# ---------------------------------------------------------------------------


class TestCSharpProjectContext:
    """Verify file-scoped namespace hint in build_project_context_section."""

    def test_context_mentions_file_scoped_namespaces(self):
        from startd8.languages.csharp import CSharpLanguageProfile

        profile = CSharpLanguageProfile()
        section = profile.build_project_context_section({
            "target_files": ["src/Foo/Bar.cs"],
            "target_framework": "net8.0",
        })
        assert "file-scoped namespaces" in section
        assert "`namespace Foo.Bar;`" in section


# ---------------------------------------------------------------------------
# _validate_csharp_file namespace hint wiring
# ---------------------------------------------------------------------------


class TestDiskValidationNamespaceHint:
    """Verify the namespace hint surfaces in disk validation results."""

    def test_block_scoped_produces_info_issue(self):
        from startd8.forward_manifest_validator import (
            DiskComplianceResult,
            _validate_csharp_file,
        )

        content = (
            "using System;\n"
            "\n"
            "namespace cartservice.services {\n"
            "    public class CartService { }\n"
            "}\n"
        )
        result = DiskComplianceResult(file_path="CartService.cs")
        result = _validate_csharp_file(content, result)

        ns_issues = [
            i for i in result.semantic_issues
            if isinstance(i, dict) and i.get("category") == "block_scoped_namespace"
        ]
        assert len(ns_issues) == 1
        assert ns_issues[0]["severity"] == "info"

    def test_file_scoped_no_issue(self):
        from startd8.forward_manifest_validator import (
            DiskComplianceResult,
            _validate_csharp_file,
        )

        content = (
            "using System;\n"
            "\n"
            "namespace cartservice.services;\n"
            "\n"
            "public class CartService { }\n"
        )
        result = DiskComplianceResult(file_path="CartService.cs")
        result = _validate_csharp_file(content, result)

        ns_issues = [
            i for i in result.semantic_issues
            if isinstance(i, dict) and i.get("category") == "block_scoped_namespace"
        ]
        assert ns_issues == []
