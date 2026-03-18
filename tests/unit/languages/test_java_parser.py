"""Tests for Java parser (Phase 2)."""

import pytest
from startd8.languages.java_parser import (
    JavaElement,
    parse_java_source,
    parse_java_imports,
    parse_java_package,
    find_element,
    _parse_with_regex,
)


SAMPLE_CLASS = """\
package com.example;

import java.util.List;
import java.util.Map;

@Entity
public class User {
    private String name;
    private int age;

    public User(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return this.name;
    }

    public void setName(String name) {
        this.name = name;
    }

    @Override
    public String toString() {
        return "User{" + name + "}";
    }
}
"""

SAMPLE_INTERFACE = """\
package com.example.service;

public interface UserService {
    User findById(long id);
    List<User> findAll();
    void save(User user);
}
"""

SAMPLE_ENUM = """\
package com.example;

public enum Status {
    ACTIVE, INACTIVE, PENDING;
}
"""


class TestParseJavaSource:
    def test_parse_class(self):
        elements = parse_java_source(SAMPLE_CLASS)
        class_elem = next((e for e in elements if e.kind == "class"), None)
        assert class_elem is not None
        assert class_elem.name == "User"

    def test_parse_methods(self):
        elements = parse_java_source(SAMPLE_CLASS)
        method_names = {e.name for e in elements if e.kind == "method"}
        assert "getName" in method_names
        assert "setName" in method_names

    def test_parse_interface(self):
        elements = parse_java_source(SAMPLE_INTERFACE)
        iface = next((e for e in elements if e.kind == "interface"), None)
        assert iface is not None
        assert iface.name == "UserService"

    def test_parse_enum(self):
        elements = parse_java_source(SAMPLE_ENUM)
        enum_elem = next((e for e in elements if e.kind == "enum"), None)
        assert enum_elem is not None
        assert enum_elem.name == "Status"

    def test_parse_annotations(self):
        elements = parse_java_source(SAMPLE_CLASS)
        class_elem = next((e for e in elements if e.kind == "class"), None)
        assert class_elem is not None
        assert "Entity" in class_elem.annotations

    def test_line_numbers_nonzero(self):
        elements = parse_java_source(SAMPLE_CLASS)
        for e in elements:
            if e.kind in ("class", "method"):
                assert e.line_number > 0


class TestParseJavaImports:
    def test_imports(self):
        imports = parse_java_imports(SAMPLE_CLASS)
        assert "java.util.List" in imports
        assert "java.util.Map" in imports

    def test_no_imports(self):
        code = "package com.example;\npublic class Empty {}\n"
        assert parse_java_imports(code) == []


class TestParseJavaPackage:
    def test_package(self):
        assert parse_java_package(SAMPLE_CLASS) == "com.example"

    def test_nested_package(self):
        assert parse_java_package(SAMPLE_INTERFACE) == "com.example.service"

    def test_no_package(self):
        assert parse_java_package("public class NoPackage {}") is None


class TestFindElement:
    def test_find_class(self):
        elem = find_element(SAMPLE_CLASS, "User")
        assert elem is not None
        assert elem.kind == "class"

    def test_find_method(self):
        elem = find_element(SAMPLE_CLASS, "getName", "method")
        assert elem is not None
        assert elem.kind == "method"

    def test_find_missing(self):
        assert find_element(SAMPLE_CLASS, "nonExistent") is None


class TestRegexFallback:
    def test_regex_parses_class(self):
        elements = _parse_with_regex(SAMPLE_CLASS)
        class_names = {e.name for e in elements if e.kind == "class"}
        assert "User" in class_names

    def test_regex_parses_methods(self):
        elements = _parse_with_regex(SAMPLE_CLASS)
        method_names = {e.name for e in elements if e.kind == "method"}
        assert "getName" in method_names
