"""Tests for L7: repair marker stripping."""

from startd8.repair.orchestrator import strip_repair_markers


class TestStripSingleMarker:
    def test_removes_repair_marker(self):
        code = "# [REPAIRED BY STARTD8: fence_strip, import_completion]\nimport os\n"
        result = strip_repair_markers(code)
        assert "REPAIRED BY STARTD8" not in result
        assert "import os" in result

    def test_removes_marker_with_one_step(self):
        code = "# [REPAIRED BY STARTD8: ast_validate]\ndef foo():\n    pass\n"
        result = strip_repair_markers(code)
        assert "REPAIRED BY STARTD8" not in result
        assert "def foo():" in result


class TestStripPreservesOtherComments:
    def test_normal_comments_kept(self):
        code = "# Normal comment\nimport os\n# Another comment\n"
        result = strip_repair_markers(code)
        assert result == code

    def test_mixed_comments(self):
        code = (
            "# [REPAIRED BY STARTD8: fence_strip]\n"
            "# Normal comment\n"
            "import os\n"
        )
        result = strip_repair_markers(code)
        assert "REPAIRED BY STARTD8" not in result
        assert "# Normal comment" in result
        assert "import os" in result


class TestStripNoMarkersUnchanged:
    def test_clean_file_unchanged(self):
        code = "import os\n\ndef main():\n    pass\n"
        result = strip_repair_markers(code)
        assert result == code

    def test_empty_string(self):
        assert strip_repair_markers("") == ""


class TestStripLeadingBlankCleaned:
    def test_leading_blank_after_removal(self):
        code = "# [REPAIRED BY STARTD8: fence_strip]\n\nimport os\n"
        result = strip_repair_markers(code)
        # The blank line after the marker should be stripped
        assert result.startswith("import os")
