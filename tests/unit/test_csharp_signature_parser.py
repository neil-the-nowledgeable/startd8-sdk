"""Tests for the C# signature string parser (REQ-EE-104)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import ForwardElementSpec, Visibility
from startd8.utils.code_manifest import ElementKind
from startd8.utils.csharp_signature_parser import parse_csharp_signatures

TARGET = "src/Services/CartService/CartService.cs"


class TestClassDeclarations:
    """Class / interface / record / struct / enum parsing."""

    def test_simple_class(self) -> None:
        results = parse_csharp_signatures(["public class CartService"], TARGET)
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "CartService"
        assert spec.bases == []
        assert spec.visibility == Visibility.PUBLIC
        assert spec.is_static is False
        assert spec.is_abstract is False
        assert spec.decomposition_source == "parse-llm"

    def test_class_with_inheritance(self) -> None:
        results = parse_csharp_signatures(
            ["public class CartService : CartServiceBase, IDisposable"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "CartService"
        assert spec.bases == ["CartServiceBase", "IDisposable"]

    def test_class_with_base_and_braces(self) -> None:
        results = parse_csharp_signatures(
            ["public class CartService : Hipstershop.CartService.CartServiceBase"], TARGET
        )
        assert len(results) == 1
        assert results[0].bases == ["Hipstershop.CartService.CartServiceBase"]

    def test_interface(self) -> None:
        results = parse_csharp_signatures(["public interface ICartStore"], TARGET)
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "ICartStore"
        assert spec.is_abstract is True

    def test_record(self) -> None:
        results = parse_csharp_signatures(
            ["public record CartItem(string ProductId, int Quantity)"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "CartItem"

    def test_static_class(self) -> None:
        results = parse_csharp_signatures(
            ["public static class HealthService"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "HealthService"
        assert spec.is_static is True

    def test_enum(self) -> None:
        results = parse_csharp_signatures(
            ["public enum CartStoreType { Redis, Spanner }"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "CartStoreType"

    def test_struct(self) -> None:
        results = parse_csharp_signatures(["public struct Money"], TARGET)
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "Money"

    def test_generic_class_with_constraint(self) -> None:
        results = parse_csharp_signatures(
            ["public class Repository<T> where T : class"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.CLASS
        assert spec.name == "Repository"


class TestMethodDeclarations:
    """Method / function parsing."""

    def test_public_method(self) -> None:
        results = parse_csharp_signatures(
            ["public void AddItem(AddItemRequest request, ServerCallContext context)"],
            TARGET,
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "AddItem"
        assert spec.visibility == Visibility.PUBLIC
        assert spec.signature is not None
        assert spec.signature.return_annotation == "void"

    def test_async_method_with_override(self) -> None:
        results = parse_csharp_signatures(
            [
                "public override async Task<Empty> AddItem("
                "AddItemRequest request, ServerCallContext context)"
            ],
            TARGET,
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "AddItem"

    def test_static_method(self) -> None:
        results = parse_csharp_signatures(
            ["public static void Main(string[] args)"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "Main"
        assert spec.is_static is True

    def test_abstract_method(self) -> None:
        results = parse_csharp_signatures(
            ["public abstract Task<Cart> GetCartAsync(string userId)"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "GetCartAsync"
        assert spec.is_abstract is True

    def test_internal_method(self) -> None:
        results = parse_csharp_signatures(
            ["internal void Configure(IServiceCollection services)"], TARGET
        )
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "Configure"
        # internal maps to PUBLIC for generation purposes
        assert spec.visibility == Visibility.PUBLIC

    def test_private_method(self) -> None:
        results = parse_csharp_signatures(
            ["private bool ValidateCart(Cart cart)"], TARGET
        )
        assert len(results) == 1
        assert results[0].visibility == Visibility.PRIVATE

    def test_protected_method(self) -> None:
        results = parse_csharp_signatures(
            ["protected virtual void OnCartChanged(CartEventArgs e)"], TARGET
        )
        assert len(results) == 1
        assert results[0].visibility == Visibility.PROTECTED


class TestDottedName:
    """Dotted name shorthand: ClassName.MethodName."""

    def test_dotted_name(self) -> None:
        results = parse_csharp_signatures(["CartService.AddItem"], TARGET)
        assert len(results) == 1
        spec = results[0]
        assert spec.kind == ElementKind.METHOD
        assert spec.name == "AddItem"
        assert spec.parent_class == "CartService"
        assert spec.signature is not None


class TestSkipAndEdgeCases:
    """Skipped inputs and edge cases."""

    def test_field_declaration_skipped(self) -> None:
        results = parse_csharp_signatures(
            ["private readonly ICartStore _store"], TARGET
        )
        assert results == []

    def test_empty_input(self) -> None:
        results = parse_csharp_signatures([], TARGET)
        assert results == []

    def test_blank_strings_skipped(self) -> None:
        results = parse_csharp_signatures(["", "  ", "   "], TARGET)
        assert results == []

    def test_unparseable_skipped(self) -> None:
        results = parse_csharp_signatures(["@#$%^&*"], TARGET)
        assert results == []

    def test_mixed_parseable_and_unparseable(self) -> None:
        results = parse_csharp_signatures(
            [
                "public class Foo",
                "private readonly int _x",
                "public void Bar()",
                "@garbage!",
            ],
            TARGET,
        )
        # class Foo + method Bar = 2 results
        assert len(results) == 2
        assert results[0].name == "Foo"
        assert results[1].name == "Bar"

    def test_all_specs_have_decomposition_source(self) -> None:
        results = parse_csharp_signatures(
            [
                "public class Svc",
                "public void Run()",
                "Svc.Run",
            ],
            TARGET,
        )
        assert all(s.decomposition_source == "parse-llm" for s in results)
