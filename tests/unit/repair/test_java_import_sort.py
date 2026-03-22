"""Tests for JavaImportSortStep (REQ-KZ-JV-402e Phase 2)."""

from pathlib import Path

from startd8.repair.models import RepairContext, RepairStepResult
from startd8.repair.steps.java_import_sort import JavaImportSortStep


def _run(code: str, filename: str = "Foo.java") -> RepairStepResult:
    step = JavaImportSortStep()
    return step(code, RepairContext(), Path(filename))


class TestJavaImportSortStep:
    def test_expand_wildcard_util(self):
        code = (
            "import java.util.*;\n"
            "\n"
            "public class Foo {\n"
            "    List<String> items = new ArrayList<>();\n"
            "    Map<String, Object> cache = new HashMap<>();\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is True
        assert "import java.util.ArrayList;" in result.code
        assert "import java.util.HashMap;" in result.code
        assert "import java.util.List;" in result.code
        assert "import java.util.Map;" in result.code
        assert "import java.util.*;" not in result.code
        assert result.metrics["wildcards_expanded"] == 1

    def test_expand_wildcard_io(self):
        code = (
            "import java.io.*;\n"
            "\n"
            "public class Reader {\n"
            "    File f = new File(\"test.txt\");\n"
            "    BufferedReader br;\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is True
        assert "import java.io.BufferedReader;" in result.code
        assert "import java.io.File;" in result.code
        assert "import java.io.*;" not in result.code

    def test_no_change_explicit_imports(self):
        code = (
            "import java.util.List;\n"
            "import java.util.Map;\n"
            "\n"
            "public class Foo {\n"
            "    List<String> items;\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is False
        assert result.code == code

    def test_unknown_package_preserved(self):
        code = (
            "import com.example.custom.*;\n"
            "\n"
            "public class Foo {\n"
            "    CustomService svc;\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is False
        assert "import com.example.custom.*;" in result.code

    def test_static_import_unaffected(self):
        code = (
            "import static org.junit.Assert.*;\n"
            "\n"
            "public class FooTest {\n"
            "    void test() { assertEquals(1, 1); }\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is False
        assert "import static org.junit.Assert.*;" in result.code

    def test_multiple_wildcards(self):
        code = (
            "import java.util.*;\n"
            "import java.io.*;\n"
            "\n"
            "public class Foo {\n"
            "    List<String> items;\n"
            "    File f;\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is True
        assert "import java.util.List;" in result.code
        assert "import java.io.File;" in result.code
        assert result.metrics["wildcards_expanded"] == 2

    def test_non_java_file_skipped(self):
        code = "import java.util.*;\npublic class Foo { List x; }\n"
        result = _run(code, filename="Foo.py")
        assert result.modified is False

    def test_preserves_non_import_lines(self):
        code = (
            "package com.example;\n"
            "\n"
            "import java.util.*;\n"
            "\n"
            "// A comment\n"
            "public class Foo {\n"
            "    List<String> items;\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is True
        assert "package com.example;" in result.code
        assert "// A comment" in result.code

    def test_wildcard_with_no_usage_preserved(self):
        """If no classes from the known package are used, keep the wildcard."""
        code = (
            "import java.math.*;\n"
            "\n"
            "public class Foo {\n"
            "    int x = 42;\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is False

    def test_sorted_explicit_imports(self):
        """Expanded imports should be alphabetically sorted."""
        code = (
            "import java.util.*;\n"
            "\n"
            "public class Foo {\n"
            "    Map<String, List<Set<String>>> x;\n"
            "}\n"
        )
        result = _run(code)
        assert result.modified is True
        lines = [l for l in result.code.splitlines() if l.startswith("import ")]
        import_names = [l.split()[-1].rstrip(";") for l in lines]
        assert import_names == sorted(import_names)
