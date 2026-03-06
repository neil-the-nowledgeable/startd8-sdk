"""Tests for DuplicateRemovalStep (REQ-RPL-104)."""

from pathlib import Path

from startd8.repair.models import RepairContext
from startd8.repair.steps.duplicate_removal import DuplicateRemovalStep


class TestDuplicateRemovalStep:
    """Tests for the duplicate import removal repair step."""

    def setup_method(self):
        self.step = DuplicateRemovalStep()
        self.ctx = RepairContext()
        self.path = Path("<test>")

    def test_no_duplicates(self):
        code = "import os\nfrom pathlib import Path\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_exact_bare_import_duplicate(self):
        code = "import os\nimport os\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.metrics["imports_removed"] == 1
        assert result.code.count("import os") == 1

    def test_semantic_duplicate_from_over_bare(self):
        """First import wins — bare `import demo_pb2` kept, `from pkg import demo_pb2` removed."""
        code = "import demo_pb2\nfrom pkg import demo_pb2\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.metrics["imports_removed"] == 1
        assert "import demo_pb2" in result.code
        lines = [l for l in result.code.splitlines() if l.strip()]
        assert len(lines) == 1

    def test_partial_from_import(self):
        """Only the duplicate name is removed from a multi-name from-import."""
        code = "import A\nfrom X import A, B\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert "from X import B" in result.code
        lines = result.code.strip().splitlines()
        assert any("import A" in l and "from" not in l for l in lines)

    def test_alias_duplicate(self):
        code = "import foo as bar\nimport baz as bar\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.metrics["imports_removed"] == 1
        assert "foo as bar" in result.code
        assert "baz as bar" not in result.code

    def test_future_import_not_duplicate(self):
        """from __future__ imports should never be considered duplicates of regular imports."""
        code = "from __future__ import annotations\nimport annotations\n"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_syntax_error_passthrough(self):
        code = "def (broken"
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False
        assert result.code == code

    def test_protocol_name(self):
        assert self.step.name == "duplicate_removal"


class TestDuplicateDefRemoval:
    """Tests for duplicate function/class definition removal."""

    def setup_method(self):
        self.step = DuplicateRemovalStep()
        self.ctx = RepairContext()
        self.path = Path("<test>")

    def test_duplicate_function_keeps_last(self):
        code = (
            "def foo():\n"
            "    return 1\n"
            "\n"
            "def foo():\n"
            "    return 2\n"
        )
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.metrics["defs_removed"] == 1
        assert result.code.count("def foo():") == 1
        assert "return 2" in result.code
        assert "return 1" not in result.code

    def test_duplicate_class_keeps_last(self):
        code = (
            "class MyClass:\n"
            "    x = 1\n"
            "\n"
            "class MyClass:\n"
            "    x = 2\n"
        )
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.metrics["defs_removed"] == 1
        assert result.code.count("class MyClass:") == 1
        assert "x = 2" in result.code
        assert "x = 1" not in result.code

    def test_no_duplicate_defs_unchanged(self):
        code = (
            "def foo():\n"
            "    return 1\n"
            "\n"
            "def bar():\n"
            "    return 2\n"
        )
        result = self.step(code, self.ctx, self.path)
        assert result.modified is False

    def test_nested_defs_not_touched(self):
        """Only module-level duplicates are removed; nested defs are left alone."""
        code = (
            "class Outer:\n"
            "    def method(self):\n"
            "        return 1\n"
            "    def method(self):\n"
            "        return 2\n"
        )
        result = self.step(code, self.ctx, self.path)
        # Nested defs are inside class body, not in tree.body
        assert result.modified is False

    def test_triple_duplicate_keeps_last(self):
        code = (
            "def foo():\n"
            "    return 1\n"
            "\n"
            "def foo():\n"
            "    return 2\n"
            "\n"
            "def foo():\n"
            "    return 3\n"
        )
        result = self.step(code, self.ctx, self.path)
        assert result.modified is True
        assert result.metrics["defs_removed"] == 2
        assert result.code.count("def foo():") == 1
        assert "return 3" in result.code
