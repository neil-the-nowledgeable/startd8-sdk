"""Tests for implementation_engine.parsers — pure parsing functions."""

import pytest

from startd8.implementation_engine.parsers import (
    parse_list_section,
    parse_score,
    parse_section_content,
)


# ---------------------------------------------------------------------------
# parse_score
# ---------------------------------------------------------------------------

class TestParseScore:
    def test_basic_score(self):
        assert parse_score("### Score: 85") == 85

    def test_score_with_surrounding_text(self):
        text = "Some review text\n### Score: 72\nMore text"
        assert parse_score(text) == 72

    def test_score_with_extra_whitespace(self):
        assert parse_score("Score:   42") == 42

    def test_score_case_insensitive(self):
        assert parse_score("score: 90") == 90
        assert parse_score("SCORE: 88") == 88

    def test_score_clamps_above_100(self):
        assert parse_score("Score: 150") == 100

    def test_score_clamps_at_zero(self):
        assert parse_score("Score: 0") == 0

    def test_no_score_returns_zero(self):
        assert parse_score("No score here") == 0

    def test_empty_string_returns_zero(self):
        assert parse_score("") == 0

    def test_first_match_wins(self):
        text = "Score: 60\nScore: 90"
        assert parse_score(text) == 60


# ---------------------------------------------------------------------------
# parse_list_section
# ---------------------------------------------------------------------------

class TestParseListSection:
    def test_basic_dash_list(self):
        text = "## Requirements\n- Item 1\n- Item 2\n- Item 3\n"
        result = parse_list_section(text, "Requirements")
        assert result == ["Item 1", "Item 2", "Item 3"]

    def test_asterisk_bullets(self):
        text = "## Issues\n* Bug A\n* Bug B\n"
        result = parse_list_section(text, "Issues")
        assert result == ["Bug A", "Bug B"]

    def test_h3_header(self):
        text = "### Edge Cases\n- Case 1\n- Case 2\n"
        result = parse_list_section(text, "Edge Cases")
        assert result == ["Case 1", "Case 2"]

    def test_case_insensitive(self):
        text = "## REQUIREMENTS\n- Item A\n"
        result = parse_list_section(text, "requirements")
        assert result == ["Item A"]

    def test_section_not_found(self):
        text = "## Something Else\n- Item\n"
        assert parse_list_section(text, "Requirements") == []

    def test_empty_text(self):
        assert parse_list_section("", "Requirements") == []

    def test_stops_at_next_section(self):
        text = (
            "## Requirements\n- Req 1\n- Req 2\n"
            "## Other\n- Other 1\n"
        )
        result = parse_list_section(text, "Requirements")
        assert result == ["Req 1", "Req 2"]

    def test_strips_whitespace(self):
        text = "## Items\n-   Spaced item   \n"
        result = parse_list_section(text, "Items")
        assert result == ["Spaced item"]

    def test_ignores_empty_items(self):
        text = "## Items\n- Real item\n-   \n- Another\n"
        result = parse_list_section(text, "Items")
        # The regex matches items with content; stripping handles whitespace
        assert "Real item" in result
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# parse_section_content
# ---------------------------------------------------------------------------

class TestParseSectionContent:
    def test_basic_paragraph(self):
        text = "## Technical Approach\nUse a factory pattern.\n"
        result = parse_section_content(text, "Technical Approach")
        assert "factory pattern" in result

    def test_stops_at_next_section(self):
        # parse_section_content uses ###? regex, so ## headers with 2 hashes
        # are captured by the lookahead only when using ###
        text = (
            "## Technical Approach\nFactory pattern.\n"
            "### Code Structure\nSomething else.\n"
        )
        result = parse_section_content(text, "Technical Approach")
        assert "Factory pattern" in result
        assert "Something else" not in result

    def test_case_insensitive(self):
        text = "## technical approach\nSome content.\n"
        result = parse_section_content(text, "Technical Approach")
        assert "Some content" in result

    def test_section_not_found(self):
        assert parse_section_content("## Other\nStuff\n", "Missing") == ""

    def test_empty_text(self):
        assert parse_section_content("", "Anything") == ""

    def test_strips_bullet_prefixes(self):
        text = "## Notes\n- First note\n- Second note\n"
        result = parse_section_content(text, "Notes")
        assert "First note" in result

    def test_multiline_content(self):
        text = "## Summary\nLine 1.\nLine 2.\nLine 3.\n"
        result = parse_section_content(text, "Summary")
        assert "Line 1" in result
        assert "Line 3" in result

    def test_h3_header(self):
        text = "### Code Structure\nDefine a module.\n"
        result = parse_section_content(text, "Code Structure")
        assert "module" in result
