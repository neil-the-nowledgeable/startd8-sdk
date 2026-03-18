"""Tests for C# Phase 5 (post-gen, postmortem) and Phase 6 (splicer).

Phase 5 (REQ-CS-300, 501, 502):
- dotnet format post-generation cleanup (best-effort)
- Language mismatch postmortem pattern (pre-existing, verify)
- .csproj <-> using dependency cross-check

Phase 6 (MicroPrime splicer):
- Body splicing via tree-sitter byte offsets
- Stub detection
- Multi-method splice
- Syntax validation after splice
- Keyword reserves and literal coercion
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Phase 5: Post-generation cleanup (REQ-CS-300)
# ---------------------------------------------------------------------------

class TestPostGenerationCleanup:

    @pytest.fixture
    def profile(self):
        from startd8.languages.csharp import CSharpLanguageProfile
        return CSharpLanguageProfile()

    def test_returns_empty_when_no_dotnet(self, profile, monkeypatch):
        import shutil
        monkeypatch.setattr(shutil, "which", lambda _: None)
        from pathlib import Path
        result = profile.post_generation_cleanup(
            [Path("/tmp/CartService.cs")], Path("/tmp"),
        )
        assert result == []

    def test_returns_empty_when_no_csproj(self, profile, tmp_path):
        cs_file = tmp_path / "CartService.cs"
        cs_file.write_text("using System; class X {}")
        result = profile.post_generation_cleanup([cs_file], tmp_path)
        assert result == []

    def test_returns_empty_for_non_cs_files(self, profile, tmp_path):
        csproj = tmp_path / "test.csproj"
        csproj.write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>')
        json_file = tmp_path / "appsettings.json"
        json_file.write_text("{}")
        result = profile.post_generation_cleanup([json_file], tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# Phase 5: Language mismatch postmortem (REQ-CS-501)
# ---------------------------------------------------------------------------

class TestLanguageMismatchPostmortem:

    def test_pattern_exists_in_cause_to_suggestion(self):
        from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION
        assert "language_mismatch_in_generation" in CAUSE_TO_SUGGESTION

    def test_pattern_hint_mentions_non_python(self):
        from startd8.contractors.prime_postmortem import CAUSE_TO_SUGGESTION
        hint = CAUSE_TO_SUGGESTION["language_mismatch_in_generation"]["hint"]
        assert "Non-Python" in hint or "non-Python" in hint


# ---------------------------------------------------------------------------
# Phase 5: .csproj <-> using cross-check (REQ-CS-502)
# ---------------------------------------------------------------------------

class TestUsingDependencyCrossCheck:

    def test_stdlib_not_flagged(self):
        from startd8.languages.csharp_splicer import check_using_coverage
        cs = "using System;\nusing System.Threading.Tasks;\nnamespace X { class Y {} }"
        csproj = '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>'
        issues = check_using_coverage(cs, csproj)
        assert len(issues) == 0

    def test_microsoft_not_flagged(self):
        from startd8.languages.csharp_splicer import check_using_coverage
        cs = "using Microsoft.AspNetCore.Builder;\nnamespace X { class Y {} }"
        csproj = '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>'
        issues = check_using_coverage(cs, csproj)
        assert len(issues) == 0

    def test_matched_package_not_flagged(self):
        from startd8.languages.csharp_splicer import check_using_coverage
        cs = "using Grpc.Core;\nnamespace X { class Y {} }"
        csproj = '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup><ItemGroup><PackageReference Include="Grpc.AspNetCore" Version="2.76.0" /></ItemGroup></Project>'
        issues = check_using_coverage(cs, csproj)
        # Grpc.Core starts with "Grpc" and PackageReference has "Grpc.AspNetCore"
        # Root namespace "Grpc" matches package root "grpc"
        assert len(issues) == 0

    def test_missing_package_flagged(self):
        from startd8.languages.csharp_splicer import check_using_coverage
        cs = "using Npgsql;\nnamespace X { class Y {} }"
        csproj = '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>'
        issues = check_using_coverage(cs, csproj)
        assert len(issues) == 1
        assert issues[0]["symbol"] == "Npgsql"

    def test_project_internal_not_flagged(self):
        from startd8.languages.csharp_splicer import check_using_coverage
        cs = "using cartservice.cartstore;\nnamespace X { class Y {} }"
        csproj = '<Project Sdk="Microsoft.NET.Sdk.Web"><PropertyGroup><TargetFramework>net8.0</TargetFramework></PropertyGroup></Project>'
        issues = check_using_coverage(cs, csproj)
        # "cartservice" starts lowercase — treated as project-internal
        assert len(issues) == 0

    def test_invalid_csproj_returns_empty(self):
        from startd8.languages.csharp_splicer import check_using_coverage
        cs = "using Npgsql;\nnamespace X { class Y {} }"
        issues = check_using_coverage(cs, "<broken xml")
        assert issues == []


# ---------------------------------------------------------------------------
# Phase 6: Splicer — stub detection
# ---------------------------------------------------------------------------

class TestCSharpStubDetection:

    def test_not_implemented_is_stub(self):
        from startd8.languages.csharp_splicer import _is_stub_body
        assert _is_stub_body("{ throw new NotImplementedException(); }") is True

    def test_not_supported_is_stub(self):
        from startd8.languages.csharp_splicer import _is_stub_body
        assert _is_stub_body("{ throw new NotSupportedException(); }") is True

    def test_todo_comment_is_stub(self):
        from startd8.languages.csharp_splicer import _is_stub_body
        assert _is_stub_body("{ // TODO: implement }") is True

    def test_empty_body_is_stub(self):
        from startd8.languages.csharp_splicer import _is_stub_body
        assert _is_stub_body("{ }") is True
        assert _is_stub_body("{}") is True

    def test_real_body_is_not_stub(self):
        from startd8.languages.csharp_splicer import _is_stub_body
        assert _is_stub_body("{ return 42; }") is False

    def test_async_body_is_not_stub(self):
        from startd8.languages.csharp_splicer import _is_stub_body
        body = "{ await _store.AddAsync(req); return new Empty(); }"
        assert _is_stub_body(body) is False


# ---------------------------------------------------------------------------
# Phase 6: Splicer — body extraction
# ---------------------------------------------------------------------------

class TestBodyExtraction:

    def test_extract_method_bodies(self):
        from startd8.languages.csharp_splicer import _extract_method_bodies_ts
        code = """
namespace X
{
    public class Svc
    {
        public void Foo() { return; }
        public int Bar() { return 42; }
    }
}
"""
        bodies = _extract_method_bodies_ts(code)
        assert "Foo" in bodies
        assert "Bar" in bodies
        # Check body text contains the return statement
        assert "return" in bodies["Foo"][2]
        assert "42" in bodies["Bar"][2]

    def test_extract_constructor(self):
        from startd8.languages.csharp_splicer import _extract_method_bodies_ts
        code = """
namespace X
{
    public class CartService
    {
        private readonly ICartStore _store;
        public CartService(ICartStore store) { _store = store; }
    }
}
"""
        bodies = _extract_method_bodies_ts(code)
        assert "CartService" in bodies
        assert "_store" in bodies["CartService"][2]


# ---------------------------------------------------------------------------
# Phase 6: Splicer — full splice
# ---------------------------------------------------------------------------

class TestCSharpSplice:

    def test_splice_single_method(self):
        from startd8.languages.csharp_splicer import splice_csharp_bodies
        skeleton = """namespace X
{
    public class Svc
    {
        public void Foo()
        {
            throw new NotImplementedException();
        }
    }
}
"""
        generated = """namespace X
{
    public class Svc
    {
        public void Foo()
        {
            Console.WriteLine("hello");
            return;
        }
    }
}
"""
        result = splice_csharp_bodies(skeleton, {"Foo": generated})
        assert result.methods_spliced == 1
        assert result.methods_skipped == 0
        assert result.code is not None
        assert "Console.WriteLine" in result.code
        assert "NotImplementedException" not in result.code

    def test_splice_multiple_methods(self):
        from startd8.languages.csharp_splicer import splice_csharp_bodies
        skeleton = """namespace X
{
    public class Svc
    {
        public void Foo()
        {
            throw new NotImplementedException();
        }

        public int Bar()
        {
            throw new NotImplementedException();
        }
    }
}
"""
        gen_foo = """namespace X { public class Svc { public void Foo() { DoWork(); } } }"""
        gen_bar = """namespace X { public class Svc { public int Bar() { return 42; } } }"""

        result = splice_csharp_bodies(skeleton, {"Foo": gen_foo, "Bar": gen_bar})
        assert result.methods_spliced == 2
        assert result.code is not None
        assert "DoWork" in result.code
        assert "return 42" in result.code
        assert "NotImplementedException" not in result.code

    def test_splice_skips_non_stub(self):
        from startd8.languages.csharp_splicer import splice_csharp_bodies
        skeleton = """namespace X
{
    public class Svc
    {
        public void Foo()
        {
            Console.WriteLine("already implemented");
        }
    }
}
"""
        generated = """namespace X { public class Svc { public void Foo() { DoOther(); } } }"""
        result = splice_csharp_bodies(skeleton, {"Foo": generated})
        assert result.methods_spliced == 0
        assert result.methods_skipped == 1
        assert "already implemented" in result.code

    def test_splice_warns_on_missing_method(self):
        from startd8.languages.csharp_splicer import splice_csharp_bodies
        skeleton = """namespace X { public class Svc { public void Foo() { throw new NotImplementedException(); } } }"""
        generated = """namespace X { public class Svc { public void Bar() { return; } } }"""
        result = splice_csharp_bodies(skeleton, {"Bar": generated})
        # Bar is in generated but not in skeleton as target
        # Wait — Bar IS the method name we're trying to splice, but skeleton has Foo
        # The skeleton doesn't have Bar, so it should be skipped
        assert result.methods_skipped == 1
        assert any("not found" in w for w in result.warnings)

    def test_splice_validates_result(self):
        from startd8.languages.csharp_splicer import splice_csharp_bodies
        skeleton = """namespace X
{
    public class Svc
    {
        public void Foo()
        {
            throw new NotImplementedException();
        }
    }
}
"""
        generated = """namespace X { public class Svc { public void Foo() { return; } } }"""
        result = splice_csharp_bodies(skeleton, {"Foo": generated})
        assert result.has_syntax_error is False

    def test_splice_empty_generated_bodies(self):
        from startd8.languages.csharp_splicer import splice_csharp_bodies
        skeleton = "namespace X { public class Svc { } }"
        result = splice_csharp_bodies(skeleton, {})
        assert result.code == skeleton
        assert result.methods_spliced == 0


# ---------------------------------------------------------------------------
# Phase 6: Keyword reserves and literal coercion
# ---------------------------------------------------------------------------

class TestCSharpKeywordsAndLiterals:

    def test_reserved_keywords_count(self):
        from startd8.languages.csharp import _CSHARP_RESERVED
        assert len(_CSHARP_RESERVED) >= 80

    def test_common_keywords_present(self):
        from startd8.languages.csharp import _CSHARP_RESERVED
        for kw in ("class", "namespace", "using", "public", "private",
                    "async", "await", "void", "return", "if", "else",
                    "true", "false", "null", "var", "record", "sealed"):
            assert kw in _CSHARP_RESERVED, f"{kw} not in reserved set"

    def test_literal_coerce_true(self):
        from startd8.languages.csharp import _csharp_literal_coerce
        assert _csharp_literal_coerce(True) == "true"

    def test_literal_coerce_false(self):
        from startd8.languages.csharp import _csharp_literal_coerce
        assert _csharp_literal_coerce(False) == "false"

    def test_literal_coerce_none(self):
        from startd8.languages.csharp import _csharp_literal_coerce
        assert _csharp_literal_coerce(None) == "null"

    def test_literal_coerce_string(self):
        from startd8.languages.csharp import _csharp_literal_coerce
        assert _csharp_literal_coerce("hello") == '"hello"'

    def test_literal_coerce_int(self):
        from startd8.languages.csharp import _csharp_literal_coerce
        assert _csharp_literal_coerce(42) == "42"

    def test_literal_coerce_list(self):
        from startd8.languages.csharp import _csharp_literal_coerce
        result = _csharp_literal_coerce([1, 2, 3])
        assert "new[]" in result
        assert "1, 2, 3" in result

    def test_literal_coerce_dict(self):
        from startd8.languages.csharp import _csharp_literal_coerce
        result = _csharp_literal_coerce({"key": "val"})
        assert "Dictionary" in result
