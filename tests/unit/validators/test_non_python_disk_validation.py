"""Tests for KZ-Q4 non-Python file format validators.

Covers Go, TypeScript, XML, generic text, Dockerfile, and unknown file
fallback validators added to ``forward_manifest_validator.py``.

All tests use the public ``validate_disk_compliance`` API to ensure
end-to-end coverage of the dispatch logic.
"""

import textwrap

import pytest

from startd8.forward_manifest_validator import (
    DiskComplianceResult,
    validate_disk_compliance,
    _detect_language_mismatch,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_file(tmp_path, name, content):
    """Write a file under tmp_path and return (relative_name, project_root)."""
    f = tmp_path / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, encoding="utf-8")
    return name, str(tmp_path)


# ---------------------------------------------------------------------------
# Go file validation
# ---------------------------------------------------------------------------


class TestGoFileValidation:
    """Test Go file validation via validate_disk_compliance."""

    def test_valid_go_with_package(self, tmp_path):
        content = textwrap.dedent("""\
            package main

            import "fmt"

            func main() {
                fmt.Println("hello")
            }
        """)
        name, root = _write_file(tmp_path, "main.go", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True
        assert result.error is None

    def test_go_missing_package(self, tmp_path):
        content = textwrap.dedent("""\
            func main() {
                fmt.Println("hello")
            }
        """)
        name, root = _write_file(tmp_path, "main.go", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert result.error == "missing_package_declaration"

    def test_go_empty_file(self, tmp_path):
        name, root = _write_file(tmp_path, "main.go", "")
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert result.error == "empty_file"

    def test_go_unbalanced_braces(self, tmp_path):
        content = textwrap.dedent("""\
            package main

            func main() {
                fmt.Println("hello")
        """)
        name, root = _write_file(tmp_path, "main.go", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert result.error == "unbalanced_braces"

    def test_go_package_not_first_line(self, tmp_path):
        """Package declaration after comments is valid."""
        content = textwrap.dedent("""\
            // Copyright 2024
            // Licensed under MIT

            package server

            type Server struct{}
        """)
        name, root = _write_file(tmp_path, "main.go", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_go_python_stub(self, tmp_path):
        """Python stubs in .go files are caught by language mismatch detection."""
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "main.go", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert "language_mismatch" in (result.error or "")
        assert result.contract_compliance == 0.0

    def test_missing_go_file(self, tmp_path):
        result = validate_disk_compliance("missing.go", str(tmp_path))
        assert result.ast_valid is False
        assert result.error == "file_not_found"


# ---------------------------------------------------------------------------
# JSON validation
# ---------------------------------------------------------------------------


class TestJsonValidation:

    def test_valid_json(self, tmp_path):
        content = '{"name": "test", "version": "1.0"}\n'
        name, root = _write_file(tmp_path, "config.json", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_invalid_json_python_stub(self, tmp_path):
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "config.json", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert result.error is not None


# ---------------------------------------------------------------------------
# XML validation
# ---------------------------------------------------------------------------


class TestXmlValidation:

    def test_valid_xml(self, tmp_path):
        content = '<Project Sdk="Microsoft.NET.Sdk">\n  <PropertyGroup/>\n</Project>\n'
        name, root = _write_file(tmp_path, "config.xml", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_invalid_xml(self, tmp_path):
        content = "<Project><unclosed>"
        name, root = _write_file(tmp_path, "config.xml", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert "xml_parse_error" in (result.error or "")

    def test_empty_xml(self, tmp_path):
        name, root = _write_file(tmp_path, "config.xml", "")
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert result.error == "empty_file"

    def test_xml_with_nested_elements(self, tmp_path):
        content = '<configuration>\n  <appSettings>\n    <add key="k" value="v"/>\n  </appSettings>\n</configuration>\n'
        name, root = _write_file(tmp_path, "app.xml", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True


# ---------------------------------------------------------------------------
# TypeScript / TSX dispatched to JS validator
# ---------------------------------------------------------------------------


class TestTypeScriptValidation:

    def test_ts_file_dispatched(self, tmp_path):
        content = textwrap.dedent("""\
            import { Component } from 'react';

            export class App extends Component {
                render() {
                    return null;
                }
            }
        """)
        name, root = _write_file(tmp_path, "app.ts", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_tsx_file_dispatched(self, tmp_path):
        content = textwrap.dedent("""\
            import React from 'react';

            export const App = () => <div>Hello</div>;
        """)
        name, root = _write_file(tmp_path, "App.tsx", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_python_stub_in_ts_file(self, tmp_path):
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "index.ts", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False

    def test_jsx_file_dispatched(self, tmp_path):
        content = "import React from 'react';\nexport const App = () => <div/>;\n"
        name, root = _write_file(tmp_path, "App.jsx", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True


# ---------------------------------------------------------------------------
# Dockerfile validation
# ---------------------------------------------------------------------------


class TestDockerfileValidation:

    def test_valid_dockerfile(self, tmp_path):
        content = "FROM golang:1.23\nCOPY . .\nRUN go build -o app\n"
        name, root = _write_file(tmp_path, "Dockerfile", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_dockerfile_missing_from(self, tmp_path):
        content = "COPY . .\nRUN echo hello\n"
        name, root = _write_file(tmp_path, "Dockerfile", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert "FROM" in (result.error or "")

    def test_python_stub_in_dockerfile(self, tmp_path):
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "Dockerfile", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False


# ---------------------------------------------------------------------------
# Java validation
# ---------------------------------------------------------------------------


class TestJavaValidation:

    def test_valid_java_with_class(self, tmp_path):
        content = textwrap.dedent("""\
            package com.example;

            public class Foo {
                public void bar() {}
            }
        """)
        name, root = _write_file(tmp_path, "Foo.java", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_python_stub_in_java(self, tmp_path):
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "Foo.java", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False


# ---------------------------------------------------------------------------
# C# validation
# ---------------------------------------------------------------------------


class TestCSharpValidation:

    def test_valid_csharp_with_namespace(self, tmp_path):
        content = textwrap.dedent("""\
            namespace Foo;

            public class Bar {
                public void Baz() {}
            }
        """)
        name, root = _write_file(tmp_path, "Bar.cs", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_python_stub_in_csharp(self, tmp_path):
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "Bar.cs", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False


# ---------------------------------------------------------------------------
# Text file validation (.gradle, .properties)
# ---------------------------------------------------------------------------


class TestTextFileValidation:

    def test_properties_file(self, tmp_path):
        content = "server.port=8080\nspring.application.name=demo\n"
        name, root = _write_file(tmp_path, "application.properties", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_gradle_settings(self, tmp_path):
        content = "rootProject.name = 'my-app'\n"
        name, root = _write_file(tmp_path, "settings.gradle", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True

    def test_empty_properties_file(self, tmp_path):
        name, root = _write_file(tmp_path, "app.properties", "")
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert result.error == "empty_file"

    def test_python_stub_in_properties(self, tmp_path):
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "app.properties", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert "language_mismatch" in (result.error or "")


# ---------------------------------------------------------------------------
# Unknown file fallback
# ---------------------------------------------------------------------------


class TestUnknownFileValidation:

    def test_non_empty_unknown(self, tmp_path):
        content = "some binary-like content\n"
        name, root = _write_file(tmp_path, "data.dat", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is True
        assert result.contract_compliance == 1.0

    def test_empty_unknown(self, tmp_path):
        name, root = _write_file(tmp_path, "data.dat", "")
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert result.error == "empty_file"

    def test_python_stub_in_unknown_file(self, tmp_path):
        content = "from __future__ import annotations\n"
        name, root = _write_file(tmp_path, "data.dat", content)
        result = validate_disk_compliance(name, root)
        assert result.ast_valid is False
        assert "language_mismatch" in (result.error or "")


# ---------------------------------------------------------------------------
# Python stub detection (_detect_language_mismatch)
# ---------------------------------------------------------------------------


class TestPythonStubDetection:
    """Verify _detect_language_mismatch catches Python stubs across formats."""

    def test_exact_future_import_in_go(self):
        content = "from __future__ import annotations"
        assert _detect_language_mismatch(content, "main.go") is not None

    def test_future_import_with_newlines(self):
        content = "\nfrom __future__ import annotations\n"
        assert _detect_language_mismatch(content, "main.go") is not None

    def test_multiline_python_imports_in_html(self):
        content = "import os\nimport sys\n"
        assert _detect_language_mismatch(content, "index.html") is not None

    def test_legitimate_go_not_flagged(self):
        content = 'package main\n\nimport "fmt"\n\nfunc main() {}\n'
        assert _detect_language_mismatch(content, "main.go") is None

    def test_legitimate_java_not_flagged(self):
        content = "package com.example;\n\nimport java.util.List;\n\npublic class Foo {}\n"
        assert _detect_language_mismatch(content, "Foo.java") is None

    def test_legitimate_json_not_flagged(self):
        content = '{"name": "test"}\n'
        assert _detect_language_mismatch(content, "config.json") is None

    def test_legitimate_yaml_not_flagged(self):
        content = "name: test\nversion: 1.0\n"
        assert _detect_language_mismatch(content, "config.yaml") is None

    def test_future_import_in_dockerfile(self):
        content = "from __future__ import annotations\n"
        result = _detect_language_mismatch(content, "Dockerfile")
        assert result is not None

    def test_future_import_in_xml(self):
        content = "from __future__ import annotations\n"
        result = _detect_language_mismatch(content, "config.xml")
        assert result is not None

    def test_future_import_in_properties(self):
        content = "from __future__ import annotations\n"
        result = _detect_language_mismatch(content, "app.properties")
        assert result is not None
