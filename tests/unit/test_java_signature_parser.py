"""Tests for Java signature string parser (REQ-EE-102)."""

from __future__ import annotations

import pytest

from startd8.forward_manifest import Visibility
from startd8.utils.code_manifest import ElementKind
from startd8.utils.java_signature_parser import parse_java_signatures


TARGET = "src/main/java/com/example/AdService.java"


class TestClassSignatures:
    def test_simple_class(self):
        specs = parse_java_signatures(["public class AdService"], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "AdService"
        assert s.bases == []
        assert s.visibility == Visibility.PUBLIC
        assert s.decomposition_source == "parse-llm"

    def test_class_with_extends_and_implements(self):
        sig = "public class AdService extends Base implements Serializable, Closeable"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "AdService"
        assert s.bases == ["Base", "Serializable", "Closeable"]

    def test_class_with_generic_extends(self):
        sig = "public class AdService extends AdServiceGrpc.AdServiceImplBase"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        assert specs[0].bases == ["AdServiceGrpc.AdServiceImplBase"]

    def test_interface(self):
        specs = parse_java_signatures(["interface CartStore"], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "CartStore"
        assert s.is_abstract is True

    def test_public_interface(self):
        specs = parse_java_signatures(["public interface CartStore"], TARGET)
        assert len(specs) == 1
        assert specs[0].is_abstract is True
        assert specs[0].visibility == Visibility.PUBLIC

    def test_record(self):
        specs = parse_java_signatures(
            ["public record Ad(String redirectUrl, String text)"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "Ad"

    def test_enum(self):
        specs = parse_java_signatures(
            ["public enum Category { CLOTHING, ACCESSORIES }"], TARGET
        )
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.CLASS
        assert s.name == "Category"

    def test_enum_bare(self):
        specs = parse_java_signatures(["enum Category { CLOTHING }"], TARGET)
        assert len(specs) == 1
        assert specs[0].name == "Category"


class TestMethodSignatures:
    def test_public_method_with_generics_in_params(self):
        sig = "public void getAds(AdRequest request, StreamObserver<AdResponse> responseObserver)"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.METHOD
        assert s.name == "getAds"
        assert s.visibility == Visibility.PUBLIC
        assert s.is_static is False
        assert s.is_abstract is False
        assert s.signature is not None

    def test_static_method(self):
        sig = "public static void main(String[] args)"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.METHOD
        assert s.name == "main"
        assert s.is_static is True

    def test_abstract_method(self):
        sig = "protected abstract void process()"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.METHOD
        assert s.name == "process"
        assert s.visibility == Visibility.PROTECTED
        assert s.is_abstract is True

    def test_private_method(self):
        sig = "private int getPort()"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.METHOD
        assert s.name == "getPort"
        assert s.visibility == Visibility.PRIVATE

    def test_generic_method(self):
        sig = "public <T> List<T> filter(List<T> items, Predicate<T> p)"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.METHOD
        assert s.name == "filter"

    def test_generic_method_with_bounds(self):
        sig = "public <T extends Comparable<T>> void sort(List<T> items)"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        assert specs[0].name == "sort"

    def test_synchronized_method(self):
        sig = "public synchronized void update()"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        assert specs[0].name == "update"

    def test_final_method(self):
        sig = "public final String getName()"
        specs = parse_java_signatures([sig], TARGET)
        assert len(specs) == 1
        assert specs[0].name == "getName"


class TestDottedName:
    def test_dotted_name_pattern(self):
        specs = parse_java_signatures(["AdService.getAds"], TARGET)
        assert len(specs) == 1
        s = specs[0]
        assert s.kind == ElementKind.METHOD
        assert s.name == "getAds"
        assert s.parent_class == "AdService"
        assert s.visibility == Visibility.PUBLIC
        assert s.decomposition_source == "parse-llm"


class TestEdgeCases:
    def test_empty_input(self):
        assert parse_java_signatures([], TARGET) == []

    def test_empty_strings(self):
        assert parse_java_signatures(["", "  "], TARGET) == []

    def test_unparseable_garbage(self):
        specs = parse_java_signatures(["@#$% not a signature"], TARGET)
        assert specs == []

    def test_multiple_mixed_signatures(self):
        sigs = [
            "public class AdService extends Base",
            "public void getAds(AdRequest req)",
            "AdService.getAds",
            "not a signature ???",
            "private static int count()",
            "public interface Store",
        ]
        specs = parse_java_signatures(sigs, TARGET)
        assert len(specs) == 5  # garbage skipped
        assert specs[0].kind == ElementKind.CLASS
        assert specs[0].name == "AdService"
        assert specs[1].kind == ElementKind.METHOD
        assert specs[1].name == "getAds"
        assert specs[2].kind == ElementKind.METHOD
        assert specs[2].parent_class == "AdService"
        assert specs[3].kind == ElementKind.METHOD
        assert specs[3].name == "count"
        assert specs[3].is_static is True
        assert specs[3].visibility == Visibility.PRIVATE
        assert specs[4].kind == ElementKind.CLASS
        assert specs[4].name == "Store"
        assert specs[4].is_abstract is True

    def test_all_specs_have_decomposition_source(self):
        sigs = [
            "public class Foo",
            "public void bar()",
            "Baz.qux",
        ]
        specs = parse_java_signatures(sigs, TARGET)
        assert all(s.decomposition_source == "parse-llm" for s in specs)
