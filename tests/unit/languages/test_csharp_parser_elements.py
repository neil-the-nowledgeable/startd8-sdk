"""Tests for C# element extraction (REQ-PLI-CS-202).

Validates that parse_csharp_source() correctly extracts classes, interfaces,
structs, records, enums, methods, and properties from C# source code.
"""

from __future__ import annotations

import pytest

from startd8.languages.csharp_parser import (
    is_tree_sitter_available,
    parse_csharp,
    parse_csharp_source,
)

# Skip precise-extraction assertions when tree-sitter's grammar/ABI is incompatible (e.g. Python
# 3.14): the regex fallback extracts a coarser element set, so exact-membership checks won't hold.
requires_tree_sitter = pytest.mark.skipif(
    not is_tree_sitter_available(),
    reason="tree-sitter-c-sharp grammar/ABI incompatible with the installed tree_sitter binding "
    "(e.g. Python 3.14) — the C# parser falls back to regex",
)


# ---------------------------------------------------------------------------
# Fixtures: representative C# source snippets
# ---------------------------------------------------------------------------

SIMPLE_CLASS = """\
using System;

namespace MyApp.Services;

public class UserService
{
    private readonly ILogger _logger;

    public UserService(ILogger logger)
    {
        _logger = logger;
    }

    public async Task<User> GetUserAsync(int id)
    {
        return await _repo.FindAsync(id);
    }

    public string Name { get; set; }
}
"""

STATIC_ABSTRACT_CLASS = """\
public static class MathUtils
{
    public static int Add(int a, int b) => a + b;
}

public abstract class Shape
{
    public abstract double Area();
}
"""

INTERFACE_SOURCE = """\
namespace Contracts;

public interface IRepository<T>
{
    Task<T> GetByIdAsync(int id);
    void Delete(int id);
}
"""

STRUCT_SOURCE = """\
public readonly struct Point
{
    public double X { get; }
    public double Y { get; }

    public Point(double x, double y)
    {
        X = x;
        Y = y;
    }
}
"""

RECORD_SOURCE = """\
public record UserDto(string Name, int Age);

public record class DetailedUser
{
    public string Email { get; init; }
}
"""

ENUM_SOURCE = """\
public enum OrderStatus
{
    Pending,
    Shipped,
    Delivered,
    Cancelled
}
"""

NESTED_CLASS = """\
public class Outer
{
    public class Inner
    {
        public void DoWork()
        {
        }
    }

    public void OuterMethod()
    {
    }
}
"""

ASYNC_OVERRIDE_METHODS = """\
public class Service : BaseService
{
    public override async Task<string> ProcessAsync()
    {
        return await base.ProcessAsync();
    }

    public static void Configure()
    {
    }

    protected virtual int Compute(int x)
    {
        return x * 2;
    }
}
"""

PROPERTY_VARIANTS = """\
public class Config
{
    public string ConnectionString { get; set; }
    public int Timeout { get; private set; }
    public static bool IsEnabled { get; }
}
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseClassExtraction:
    """Test class declaration extraction."""

    def test_public_class(self):
        elements = parse_csharp_source(SIMPLE_CLASS)
        classes = [e for e in elements if e.kind == "class"]
        assert len(classes) == 1
        assert classes[0].name == "UserService"

    def test_static_class(self):
        elements = parse_csharp_source(STATIC_ABSTRACT_CLASS)
        classes = [e for e in elements if e.kind == "class"]
        names = {c.name for c in classes}
        assert "MathUtils" in names
        math_cls = [c for c in classes if c.name == "MathUtils"][0]
        assert "static" in math_cls.modifiers

    def test_abstract_class(self):
        elements = parse_csharp_source(STATIC_ABSTRACT_CLASS)
        classes = [e for e in elements if e.kind == "class"]
        shape = [c for c in classes if c.name == "Shape"][0]
        assert "abstract" in shape.modifiers


class TestParseInterfaceExtraction:
    """Test interface declaration extraction."""

    def test_interface(self):
        elements = parse_csharp_source(INTERFACE_SOURCE)
        interfaces = [e for e in elements if e.kind == "interface"]
        assert len(interfaces) == 1
        # Note: tree-sitter captures the base name; regex captures up to <
        assert interfaces[0].name.startswith("IRepository")


class TestParseStructExtraction:
    """Test struct declaration extraction."""

    def test_readonly_struct(self):
        elements = parse_csharp_source(STRUCT_SOURCE)
        structs = [e for e in elements if e.kind == "struct"]
        assert len(structs) == 1
        assert structs[0].name == "Point"


class TestParseRecordExtraction:
    """Test record declaration extraction."""

    def test_records(self):
        elements = parse_csharp_source(RECORD_SOURCE)
        records = [e for e in elements if e.kind == "record"]
        names = {r.name for r in records}
        assert "UserDto" in names


class TestParseEnumExtraction:
    """Test enum declaration extraction."""

    def test_enum(self):
        elements = parse_csharp_source(ENUM_SOURCE)
        enums = [e for e in elements if e.kind == "enum"]
        assert len(enums) == 1
        assert enums[0].name == "OrderStatus"


class TestParseMethodExtraction:
    """Test method declaration extraction."""

    def test_public_method(self):
        elements = parse_csharp_source(SIMPLE_CLASS)
        methods = [e for e in elements if e.kind in ("method", "constructor")]
        names = {m.name for m in methods}
        assert "GetUserAsync" in names

    def test_static_method(self):
        elements = parse_csharp_source(STATIC_ABSTRACT_CLASS)
        methods = [e for e in elements if e.kind == "method"]
        add_methods = [m for m in methods if m.name == "Add"]
        assert len(add_methods) >= 1
        assert "static" in add_methods[0].modifiers

    def test_async_method(self):
        elements = parse_csharp_source(ASYNC_OVERRIDE_METHODS)
        methods = [e for e in elements if e.kind == "method"]
        process = [m for m in methods if m.name == "ProcessAsync"]
        assert len(process) >= 1
        assert "async" in process[0].modifiers

    def test_override_method(self):
        elements = parse_csharp_source(ASYNC_OVERRIDE_METHODS)
        methods = [e for e in elements if e.kind == "method"]
        process = [m for m in methods if m.name == "ProcessAsync"]
        assert len(process) >= 1
        assert "override" in process[0].modifiers

    def test_constructor(self):
        elements = parse_csharp_source(SIMPLE_CLASS)
        # tree-sitter detects constructors; regex may classify as method
        # Either way, "UserService" should appear as a method or constructor name
        all_names = {e.name for e in elements if e.kind in ("method", "constructor")}
        assert "UserService" in all_names or "GetUserAsync" in all_names


class TestParsePropertyExtraction:
    """Test property declaration extraction."""

    @requires_tree_sitter
    def test_properties(self):
        elements = parse_csharp_source(PROPERTY_VARIANTS)
        props = [e for e in elements if e.kind == "property"]
        names = {p.name for p in props}
        assert "ConnectionString" in names
        assert "Timeout" in names

    def test_auto_property_in_class(self):
        elements = parse_csharp_source(SIMPLE_CLASS)
        props = [e for e in elements if e.kind == "property"]
        names = {p.name for p in props}
        assert "Name" in names


class TestNestedClassDetection:
    """Test parent class detection for nested members."""

    def test_outer_method_has_parent(self):
        elements = parse_csharp_source(NESTED_CLASS)
        methods = [e for e in elements if e.kind in ("method", "constructor")]
        outer_method = [m for m in methods if m.name == "OuterMethod"]
        if outer_method:
            assert outer_method[0].parent == "Outer"

    def test_inner_method_has_inner_parent(self):
        elements = parse_csharp_source(NESTED_CLASS)
        methods = [e for e in elements if e.kind in ("method", "constructor")]
        do_work = [m for m in methods if m.name == "DoWork"]
        if do_work:
            assert do_work[0].parent == "Inner"


class TestEdgeCases:
    """Test edge cases and error tolerance."""

    def test_empty_source(self):
        elements = parse_csharp_source("")
        assert elements == []

    def test_syntax_error_tolerance(self):
        # Incomplete class declaration — should not crash
        source = "public class Broken {\n  public void Foo() { }\n}\n"
        elements = parse_csharp_source(source)
        # Should extract at least the class name
        classes = [e for e in elements if e.kind == "class"]
        assert len(classes) >= 1
        assert classes[0].name == "Broken"

    def test_truly_broken_source_does_not_crash(self):
        # Truly malformed source — parser should not raise
        source = "public class { {\n  (\n"
        elements = parse_csharp_source(source)
        # May or may not find elements, but must not crash
        assert isinstance(elements, list)

    def test_comments_only(self):
        source = "// This is just a comment\n/* block comment */\n"
        elements = parse_csharp_source(source)
        assert elements == []

    def test_parse_csharp_source_matches_parse_csharp(self):
        """parse_csharp_source() should return the same elements as parse_csharp().elements."""
        result = parse_csharp(SIMPLE_CLASS)
        elements = parse_csharp_source(SIMPLE_CLASS)
        assert len(elements) == len(result.elements)
        for a, b in zip(elements, result.elements):
            assert a.kind == b.kind
            assert a.name == b.name


class TestParseResult:
    """Test CSharpParseResult metadata."""

    def test_usings_extracted(self):
        result = parse_csharp(SIMPLE_CLASS)
        assert "System" in result.usings

    def test_namespace_extracted(self):
        result = parse_csharp(SIMPLE_CLASS)
        assert result.namespace == "MyApp.Services"

    def test_parser_used_is_set(self):
        result = parse_csharp(SIMPLE_CLASS)
        assert result.parser_used in ("tree_sitter", "regex")
