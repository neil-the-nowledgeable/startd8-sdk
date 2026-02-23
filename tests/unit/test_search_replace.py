"""Tests for startd8.utils.search_replace — edit block parser and applicator."""

from __future__ import annotations

import pytest

from startd8.utils.search_replace import (
    EditBlock,
    EditResult,
    apply_edit_blocks,
    has_edit_markers,
    parse_edit_blocks,
)


# =====================================================================
# has_edit_markers
# =====================================================================


class TestHasEditMarkers:
    def test_present(self):
        text = "<<<<<<< SEARCH\nfoo\n=======\nbar\n>>>>>>> REPLACE"
        assert has_edit_markers(text) is True

    def test_absent(self):
        assert has_edit_markers("just some code") is False

    def test_partial_only_search(self):
        assert has_edit_markers("<<<<<<< SEARCH\nfoo") is False

    def test_partial_only_replace(self):
        assert has_edit_markers(">>>>>>> REPLACE") is False


# =====================================================================
# parse_edit_blocks
# =====================================================================


class TestParseEditBlocks:
    def test_returns_none_when_no_markers(self):
        assert parse_edit_blocks("regular code\nno markers") is None

    def test_single_block(self):
        response = (
            "Here is the edit:\n"
            "<<<<<<< SEARCH\n"
            "old line\n"
            "=======\n"
            "new line\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_edit_blocks(response)
        assert blocks is not None
        assert len(blocks) == 1
        assert blocks[0].search_text == "old line"
        assert blocks[0].replace_text == "new line"
        assert blocks[0].block_index == 0

    def test_multiple_blocks(self):
        response = (
            "<<<<<<< SEARCH\n"
            "alpha\n"
            "=======\n"
            "ALPHA\n"
            ">>>>>>> REPLACE\n"
            "\n"
            "<<<<<<< SEARCH\n"
            "beta\n"
            "=======\n"
            "BETA\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_edit_blocks(response)
        assert blocks is not None
        assert len(blocks) == 2
        assert blocks[0].search_text == "alpha"
        assert blocks[0].replace_text == "ALPHA"
        assert blocks[1].search_text == "beta"
        assert blocks[1].replace_text == "BETA"

    def test_multiline_search_and_replace(self):
        response = (
            "<<<<<<< SEARCH\n"
            "line one\n"
            "line two\n"
            "line three\n"
            "=======\n"
            "LINE ONE\n"
            "LINE TWO\n"
            "LINE THREE\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_edit_blocks(response)
        assert blocks is not None
        assert len(blocks) == 1
        assert "line one\nline two\nline three" == blocks[0].search_text
        assert "LINE ONE\nLINE TWO\nLINE THREE" == blocks[0].replace_text

    def test_empty_replace_for_deletion(self):
        response = (
            "<<<<<<< SEARCH\n"
            "delete this line\n"
            "=======\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_edit_blocks(response)
        assert blocks is not None
        assert len(blocks) == 1
        assert blocks[0].search_text == "delete this line"
        assert blocks[0].replace_text == ""

    def test_malformed_missing_divider(self):
        response = (
            "<<<<<<< SEARCH\n"
            "old line\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_edit_blocks(response)
        assert blocks is not None
        assert len(blocks) == 0  # malformed → skipped

    def test_malformed_missing_replace_marker(self):
        response = (
            "<<<<<<< SEARCH\n"
            "old line\n"
            "=======\n"
            "new line\n"
            # Missing >>>>>>> REPLACE
        )
        # No REPLACE marker means has_edit_markers() is False → returns None
        blocks = parse_edit_blocks(response)
        assert blocks is None


# =====================================================================
# apply_edit_blocks
# =====================================================================


class TestApplyEditBlocks:
    def test_single_exact_replacement(self):
        content = "line one\nline two\nline three\n"
        blocks = [EditBlock(search_text="line two", replace_text="LINE TWO", block_index=0)]
        result = apply_edit_blocks(content, blocks)
        assert result.success is True
        assert result.applied == 1
        assert result.failed == []
        assert "LINE TWO" in result.content
        assert "line one" in result.content
        assert "line three" in result.content

    def test_multiple_replacements_sequential(self):
        content = "aaa\nbbb\nccc\n"
        blocks = [
            EditBlock(search_text="aaa", replace_text="AAA", block_index=0),
            EditBlock(search_text="ccc", replace_text="CCC", block_index=1),
        ]
        result = apply_edit_blocks(content, blocks)
        assert result.success is True
        assert result.applied == 2
        assert "AAA" in result.content
        assert "bbb" in result.content
        assert "CCC" in result.content

    def test_deletion(self):
        content = "keep\nremove this\nkeep too\n"
        blocks = [EditBlock(search_text="remove this\n", replace_text="", block_index=0)]
        result = apply_edit_blocks(content, blocks)
        assert result.success is True
        assert "remove this" not in result.content
        assert "keep" in result.content

    def test_insertion_via_context(self):
        content = "def foo():\n    pass\n"
        blocks = [
            EditBlock(
                search_text="def foo():\n    pass",
                replace_text="def foo():\n    return 42",
                block_index=0,
            ),
        ]
        result = apply_edit_blocks(content, blocks)
        assert result.success is True
        assert "return 42" in result.content

    def test_no_match_reports_failure(self):
        content = "hello world\n"
        blocks = [EditBlock(search_text="goodbye world", replace_text="x", block_index=0)]
        result = apply_edit_blocks(content, blocks)
        assert result.success is False
        assert result.applied == 0
        assert len(result.failed) == 1
        assert result.failed[0][0].block_index == 0

    def test_partial_failure(self):
        content = "alpha\nbeta\ngamma\n"
        blocks = [
            EditBlock(search_text="alpha", replace_text="ALPHA", block_index=0),
            EditBlock(search_text="MISSING", replace_text="X", block_index=1),
        ]
        result = apply_edit_blocks(content, blocks)
        assert result.success is False
        assert result.applied == 1
        assert len(result.failed) == 1
        assert "ALPHA" in result.content  # first block still applied

    def test_whitespace_normalized_match(self):
        # Original has trailing spaces; search does not
        content = "def foo():   \n    pass   \n"
        blocks = [
            EditBlock(
                search_text="def foo():\n    pass",
                replace_text="def foo():\n    return 1",
                block_index=0,
            ),
        ]
        result = apply_edit_blocks(content, blocks)
        assert result.success is True
        assert "return 1" in result.content

    def test_empty_blocks_list(self):
        content = "unchanged\n"
        result = apply_edit_blocks(content, [])
        assert result.success is True
        assert result.applied == 0
        assert result.content == content

    def test_preserves_surrounding_content(self):
        content = (
            "import os\n"
            "import sys\n"
            "\n"
            "def main():\n"
            "    print('hello')\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        )
        blocks = [
            EditBlock(
                search_text="    print('hello')",
                replace_text="    print('goodbye')\n    print('world')",
                block_index=0,
            ),
        ]
        result = apply_edit_blocks(content, blocks)
        assert result.success is True
        assert "import os" in result.content
        assert "import sys" in result.content
        assert "print('goodbye')" in result.content
        assert "print('world')" in result.content
        assert "__name__" in result.content


# =====================================================================
# Integration: parse → apply
# =====================================================================


class TestParseAndApply:
    def test_round_trip(self):
        existing = "class Foo:\n    def bar(self):\n        return 1\n"
        llm_response = (
            "Here are the changes:\n\n"
            "<<<<<<< SEARCH\n"
            "    def bar(self):\n"
            "        return 1\n"
            "=======\n"
            "    def bar(self):\n"
            "        return 42\n"
            "\n"
            "    def baz(self):\n"
            "        return 'new'\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_edit_blocks(llm_response)
        assert blocks is not None
        result = apply_edit_blocks(existing, blocks)
        assert result.success is True
        assert "return 42" in result.content
        assert "def baz" in result.content
        assert "class Foo" in result.content

    def test_multiple_edits_round_trip(self):
        existing = (
            "# Header\n"
            "VERSION = '1.0'\n"
            "\n"
            "def old_func():\n"
            "    pass\n"
        )
        llm_response = (
            "<<<<<<< SEARCH\n"
            "VERSION = '1.0'\n"
            "=======\n"
            "VERSION = '2.0'\n"
            ">>>>>>> REPLACE\n"
            "\n"
            "<<<<<<< SEARCH\n"
            "def old_func():\n"
            "    pass\n"
            "=======\n"
            "def new_func():\n"
            "    return True\n"
            ">>>>>>> REPLACE\n"
        )
        blocks = parse_edit_blocks(llm_response)
        assert blocks is not None
        assert len(blocks) == 2
        result = apply_edit_blocks(existing, blocks)
        assert result.success is True
        assert "VERSION = '2.0'" in result.content
        assert "def new_func" in result.content
        assert "return True" in result.content
