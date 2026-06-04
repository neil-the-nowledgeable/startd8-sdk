"""Tests for cross-language element pattern surface (Layer 5).

The former engine-side cache/query API (``MicroPrimeEngine.get_cross_language_elements`` +
``_cross_language_cache`` with archetype keying and ``exclude_language`` filtering) was removed; the
cross-language reference is now built in the drafter from a pre-assembled ``context['cross_language_elements']``
list. Coverage lives in ``TestDrafterCrossLanguageSection`` below. (The obsolete ``TestCrossLanguageElements``
class was deleted with that API — it tested a method that no longer exists anywhere in ``src/``.)
"""

from startd8.implementation_engine.drafter import _build_cross_language_element_context


class TestDrafterCrossLanguageSection:
    """Tests for _build_cross_language_element_context in drafter."""

    def test_section_with_elements(self):
        """Cross-language context appears in drafter output."""
        ctx = {
            "cross_language_elements": [
                {
                    "name": "main",
                    "language": "go",
                    "code_excerpt": "grpc.NewServer()",
                },
            ]
        }
        section = _build_cross_language_element_context(ctx)
        assert "Cross-Language Element Reference" in section
        assert "grpc.NewServer()" in section
        assert "main (go)" in section

    def test_empty_context(self):
        """Empty context returns empty string."""
        assert _build_cross_language_element_context({}) == ""

    def test_none_elements(self):
        """None elements returns empty string."""
        assert _build_cross_language_element_context(
            {"cross_language_elements": None}
        ) == ""

    def test_non_list_elements(self):
        """Non-list elements returns empty string."""
        assert _build_cross_language_element_context(
            {"cross_language_elements": "not a list"}
        ) == ""

    def test_limit_to_three(self):
        """Only first 3 elements are shown."""
        elements = [
            {"name": f"elem_{i}", "language": "go", "code_excerpt": f"code_{i}"}
            for i in range(10)
        ]
        ctx = {"cross_language_elements": elements}
        section = _build_cross_language_element_context(ctx)
        assert "elem_0" in section
        assert "elem_2" in section
        assert "elem_3" not in section

    def test_code_excerpt_truncated(self):
        """Code excerpts longer than 500 chars are truncated."""
        long_code = "x" * 1000
        ctx = {
            "cross_language_elements": [
                {"name": "big_func", "language": "go", "code_excerpt": long_code},
            ]
        }
        section = _build_cross_language_element_context(ctx)
        # The code block should contain at most 500 chars of the excerpt
        assert len(long_code[:500]) == 500
        assert "x" * 501 not in section

    def test_element_without_code_skipped(self):
        """Elements without code_excerpt are skipped."""
        ctx = {
            "cross_language_elements": [
                {"name": "no_code", "language": "go", "code_excerpt": ""},
                {"name": "has_code", "language": "java", "code_excerpt": "int x = 1;"},
            ]
        }
        section = _build_cross_language_element_context(ctx)
        assert "no_code" not in section
        assert "has_code" in section
