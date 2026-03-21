"""Tests for C# language support — Phase 1 (REQ-CS-100, 101, 102).

Covers:
- Extension bypass in MicroPrime engine and drafter
- CSharpLanguageProfile protocol conformance
- tree-sitter-c-sharp parser integration
- Language resolution for .cs files
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Extension bypass tests (REQ-CS-100, REQ-CS-101)
# ---------------------------------------------------------------------------

class TestCSharpBypass:
    """Verify .cs, .csproj, .sln bypass Python AST parsing."""

    def test_cs_handled_by_microprime_when_enabled(self):
        """With CSHARP_MICROPRIME_ENABLED=True, .cs is NOT non-Python (MicroPrime handles it)."""
        from startd8.micro_prime.engine import _is_non_python_file, CSHARP_MICROPRIME_ENABLED
        # .cs behavior depends on feature flag — when enabled, MicroPrime handles .cs
        if CSHARP_MICROPRIME_ENABLED:
            assert _is_non_python_file("src/CartService.cs") is False
        else:
            assert _is_non_python_file("src/CartService.cs") is True

    def test_csproj_is_non_python_in_engine(self):
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("cartservice.csproj") is True

    def test_sln_is_non_python_in_engine(self):
        from startd8.micro_prime.engine import _is_non_python_file
        assert _is_non_python_file("cartservice.sln") is True

    def test_cs_is_source_in_drafter(self):
        """REQ-PE-501: .cs is source code, NOT config — gets quality gates."""
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("src/CartService.cs") is False

    def test_csproj_is_config_in_drafter(self):
        """.csproj is a build/project file — skips code heuristics."""
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("cartservice.csproj") is True

    def test_sln_is_config_in_drafter(self):
        """.sln is a solution file — skips code heuristics."""
        from startd8.implementation_engine.drafter import _is_config_or_data_file
        assert _is_config_or_data_file("cartservice.sln") is True

    def test_feature_flag_enabled(self):
        """C# MicroPrime is enabled (was off, now on after language parity work)."""
        from startd8.micro_prime.engine import CSHARP_MICROPRIME_ENABLED
        assert CSHARP_MICROPRIME_ENABLED is True

    def test_cs_bypass_with_flag_on(self, monkeypatch):
        """When CSHARP_MICROPRIME_ENABLED is True, .cs files are NOT non-Python."""
        import startd8.micro_prime.engine as engine
        monkeypatch.setattr(engine, "CSHARP_MICROPRIME_ENABLED", True)
        assert engine._is_non_python_file("src/CartService.cs") is False

    def test_csproj_always_non_python_regardless_of_flag(self, monkeypatch):
        """Build files always bypass, even when MicroPrime is enabled."""
        import startd8.micro_prime.engine as engine
        monkeypatch.setattr(engine, "CSHARP_MICROPRIME_ENABLED", True)
        assert engine._is_non_python_file("cartservice.csproj") is True

    def test_sln_always_non_python_regardless_of_flag(self, monkeypatch):
        import startd8.micro_prime.engine as engine
        monkeypatch.setattr(engine, "CSHARP_MICROPRIME_ENABLED", True)
        assert engine._is_non_python_file("cartservice.sln") is True


# ---------------------------------------------------------------------------
# CSharpLanguageProfile tests (REQ-CS-102)
# ---------------------------------------------------------------------------

class TestCSharpLanguageProfile:
    """Verify CSharpLanguageProfile has all required properties."""

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_language_id(self, profile):
        assert profile.language_id == "csharp"

    def test_display_name(self, profile):
        assert profile.display_name == "C#"

    def test_source_extensions(self, profile):
        assert ".cs" in profile.source_extensions

    def test_build_file_patterns(self, profile):
        patterns = profile.build_file_patterns
        assert any("csproj" in p for p in patterns)
        assert any("sln" in p for p in patterns)

    def test_system_prompt_role(self, profile):
        assert "C#" in profile.system_prompt_role or ".NET" in profile.system_prompt_role

    def test_coding_standards_not_empty(self, profile):
        assert len(profile.coding_standards) > 20

    def test_merge_strategy_simple(self, profile):
        assert profile.merge_strategy_preference == "simple"

    def test_repair_enabled(self, profile):
        assert profile.repair_enabled is True

    def test_docker_images(self, profile):
        assert "dotnet" in profile.docker_base_image
        assert "dotnet" in profile.docker_runtime_image
        assert "10.0" in profile.docker_base_image
        assert "10.0" in profile.docker_runtime_image

    def test_supports_cs_extension(self, profile):
        assert profile.supports_extension(".cs") is True
        assert profile.supports_extension(".CS") is True
        assert profile.supports_extension(".java") is False

    def test_stub_patterns(self, profile):
        import re
        patterns = profile.stub_patterns
        assert len(patterns) >= 2
        # Should match NotImplementedException
        assert any(
            re.search(p, "throw new NotImplementedException();")
            for p in patterns
        )

    def test_import_patterns(self, profile):
        patterns = profile.get_import_patterns("Grpc.Core")
        assert any("using" in p and "Grpc.Core" in p for p in patterns)

    def test_stdlib_prefixes(self, profile):
        prefixes = profile.get_stdlib_prefixes()
        assert "System" in prefixes
        assert "Microsoft" in prefixes

    def test_framework_imports_has_grpc(self, profile):
        assert "grpc" in profile.framework_imports

    def test_framework_imports_has_aspnet(self, profile):
        assert "aspnet_core" in profile.framework_imports

    def test_framework_imports_has_redis(self, profile):
        assert "redis" in profile.framework_imports

    def test_framework_imports_has_xunit(self, profile):
        assert "xunit" in profile.framework_imports

    def test_validate_syntax_valid(self, profile):
        code = "using System;\nnamespace X {\n    public class Foo {}\n}"
        valid, msg = profile.validate_syntax(code)
        assert valid is True
        assert msg == ""

    def test_validate_syntax_invalid(self, profile):
        code = "public class { broken"
        valid, msg = profile.validate_syntax(code)
        assert valid is False
        assert msg  # non-empty error

    def test_validate_syntax_python_fingerprint(self, profile):
        code = "from __future__ import annotations\nclass Foo: pass"
        valid, msg = profile.validate_syntax(code)
        assert valid is False
        assert "Python fingerprint" in msg

    def test_validate_syntax_empty(self, profile):
        valid, msg = profile.validate_syntax("")
        assert valid is False

    def test_generate_dependency_file(self, profile):
        from pathlib import Path
        result = profile.generate_dependency_file(
            project_root=Path("/tmp"),
            service_name="cartservice",
            module_path="",
            dependencies=["Grpc.AspNetCore/2.76.0", "Npgsql/10.0.1"],
            metadata={"target_framework": "net10.0"},
        )
        assert result is not None
        assert "<Project" in result
        assert "net10.0" in result
        assert "Grpc.AspNetCore" in result
        assert "Npgsql" in result


# ---------------------------------------------------------------------------
# tree-sitter parser tests
# ---------------------------------------------------------------------------

class TestCSharpParser:
    """Test csharp_parser.py structure extraction."""

    def test_is_tree_sitter_available(self):
        from startd8.languages.csharp_parser import is_tree_sitter_available
        # Should be True since we installed it
        assert is_tree_sitter_available() is True

    def test_parse_simple_class(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """
using System;

namespace MyApp
{
    public class Foo
    {
        public void Bar() { }
    }
}
"""
        result = parse_csharp(code)
        assert result.parser_used == "tree_sitter"
        assert result.has_error is False
        assert result.namespace == "MyApp"
        assert "System" in result.usings
        # Should find class and method
        names = {e.name for e in result.elements}
        assert "Foo" in names
        assert "Bar" in names

    def test_parse_interface(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """
namespace cartservice.cartstore
{
    public interface ICartStore
    {
        Task AddItemAsync(string userId, string productId, int quantity);
        bool Ping();
    }
}
"""
        result = parse_csharp(code)
        assert result.has_error is False
        kinds = {e.kind for e in result.elements}
        assert "interface" in kinds
        iface = next(e for e in result.elements if e.kind == "interface")
        assert iface.name == "ICartStore"

    def test_parse_async_method(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """
namespace X
{
    public class Svc
    {
        public async Task<Empty> AddItem(AddItemRequest req, ServerCallContext ctx)
        {
            await _store.AddAsync(req);
            return new Empty();
        }
    }
}
"""
        result = parse_csharp(code)
        assert result.has_error is False
        method = next(
            (e for e in result.elements if e.kind == "method"), None,
        )
        assert method is not None
        assert method.name == "AddItem"
        assert "public" in method.modifiers
        assert "async" in method.modifiers
        assert method.parent == "Svc"

    def test_parse_constructor(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """
namespace X
{
    public class CartService
    {
        private readonly ICartStore _cartStore;

        public CartService(ICartStore cartStore)
        {
            _cartStore = cartStore;
        }
    }
}
"""
        result = parse_csharp(code)
        ctor = next(
            (e for e in result.elements if e.kind == "constructor"), None,
        )
        assert ctor is not None
        assert ctor.name == "CartService"
        assert ctor.parent == "CartService"

    def test_parse_property(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """
namespace X
{
    public class Startup
    {
        public IConfiguration Configuration { get; }
    }
}
"""
        result = parse_csharp(code)
        prop = next(
            (e for e in result.elements if e.kind == "property"), None,
        )
        assert prop is not None
        assert prop.name == "Configuration"

    def test_parse_multiple_usings(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """
using System;
using System.Threading.Tasks;
using Grpc.Core;
using Microsoft.Extensions.Configuration;
using cartservice.cartstore;

namespace cartservice.services {}
"""
        result = parse_csharp(code)
        assert len(result.usings) == 5
        assert "System" in result.usings
        assert "System.Threading.Tasks" in result.usings
        assert "Grpc.Core" in result.usings

    def test_parse_file_scoped_namespace(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """
namespace cartservice.services;

public class CartService {}
"""
        result = parse_csharp(code)
        assert result.namespace == "cartservice.services"
        names = {e.name for e in result.elements}
        assert "CartService" in names

    def test_parse_syntax_error_detected(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = "public class { this is broken"
        result = parse_csharp(code)
        assert result.has_error is True

    def test_body_byte_offsets_present(self):
        from startd8.languages.csharp_parser import parse_csharp
        code = """namespace X {
    public class Foo {
        public void Bar() { return; }
    }
}"""
        result = parse_csharp(code)
        method = next(
            (e for e in result.elements if e.kind == "method"), None,
        )
        assert method is not None
        assert method.body_start_byte is not None
        assert method.body_end_byte is not None
        assert method.body_start_byte < method.body_end_byte
        # Verify the body range contains the return statement
        body_text = code.encode("utf-8")[method.body_start_byte:method.body_end_byte]
        assert b"return" in body_text

    def test_validate_csharp_syntax_valid(self):
        from startd8.languages.csharp_parser import validate_csharp_syntax
        valid, msg = validate_csharp_syntax(
            "using System;\nnamespace X { public class Y {} }"
        )
        assert valid is True

    def test_validate_csharp_syntax_invalid(self):
        from startd8.languages.csharp_parser import validate_csharp_syntax
        valid, msg = validate_csharp_syntax("class {{{ broken")
        assert valid is False

    def test_validate_csharp_syntax_empty(self):
        from startd8.languages.csharp_parser import validate_csharp_syntax
        valid, msg = validate_csharp_syntax("   ")
        assert valid is False
        assert "empty" in msg


# ---------------------------------------------------------------------------
# Language resolution tests
# ---------------------------------------------------------------------------

class TestCSharpResolution:
    """Verify resolve_language returns C# for .cs files."""

    def test_resolve_cs_files(self):
        from startd8.languages.registry import LanguageRegistry
        from startd8.languages.resolution import resolve_language
        LanguageRegistry.discover()
        profile = resolve_language(["src/CartService.cs", "src/Startup.cs"])
        assert profile is not None
        assert profile.language_id == "csharp"

    def test_resolve_mixed_cs_and_csproj(self):
        from startd8.languages.registry import LanguageRegistry
        from startd8.languages.resolution import resolve_language
        LanguageRegistry.discover()
        profile = resolve_language([
            "src/CartService.cs", "cartservice.csproj", "Dockerfile",
        ])
        assert profile is not None
        assert profile.language_id == "csharp"

    def test_registry_discovers_csharp(self):
        from startd8.languages.registry import LanguageRegistry
        LanguageRegistry.discover()
        profile = LanguageRegistry.get_by_extension(".cs")
        assert profile is not None
        assert profile.language_id == "csharp"
