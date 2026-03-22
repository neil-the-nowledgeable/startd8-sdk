"""Tests for Go Kaizen suggestion mappings (REQ-KZ-GO-501).

Validates that all 6 Go semantic check categories have entries in
both ``_SEMANTIC_CATEGORY_TO_SUGGESTION`` and ``CAUSE_TO_SUGGESTION``.
"""

import pytest


def _load_postmortem_dicts():
    """Import the two mapping dicts from prime_postmortem."""
    from startd8.contractors.prime_postmortem import (
        CAUSE_TO_SUGGESTION,
        _SEMANTIC_CATEGORY_TO_SUGGESTION,
    )
    return CAUSE_TO_SUGGESTION, _SEMANTIC_CATEGORY_TO_SUGGESTION


# All 6 Go semantic check categories from go_semantic_checks.py
GO_SEMANTIC_CATEGORIES = [
    "unchecked_error",
    "duplicate_function",
    "fmt_println_in_service",
    "dot_import",
    "python_contamination",
    "package_dir_mismatch",
]


class TestGoKaizenMappings:
    """All Go semantic categories must be mapped to Kaizen suggestions."""

    def test_all_categories_in_semantic_map(self):
        """Every Go category has a _SEMANTIC_CATEGORY_TO_SUGGESTION entry."""
        _, sem_map = _load_postmortem_dicts()
        for cat in GO_SEMANTIC_CATEGORIES:
            assert cat in sem_map, (
                f"Go semantic category '{cat}' missing from "
                f"_SEMANTIC_CATEGORY_TO_SUGGESTION"
            )

    def test_all_suggestion_keys_in_cause_map(self):
        """Every mapped suggestion key exists in CAUSE_TO_SUGGESTION."""
        cause_map, sem_map = _load_postmortem_dicts()
        for cat in GO_SEMANTIC_CATEGORIES:
            suggestion_key = sem_map.get(cat)
            if suggestion_key is None:
                pytest.skip(f"No mapping for {cat}")
            assert suggestion_key in cause_map, (
                f"Suggestion key '{suggestion_key}' (from Go category '{cat}') "
                f"missing from CAUSE_TO_SUGGESTION"
            )

    def test_cause_entries_have_required_fields(self):
        """Each CAUSE_TO_SUGGESTION entry has 'phase' and 'hint'."""
        cause_map, sem_map = _load_postmortem_dicts()
        for cat in GO_SEMANTIC_CATEGORIES:
            key = sem_map.get(cat)
            if key is None:
                continue
            entry = cause_map.get(key)
            if entry is None:
                continue
            assert "phase" in entry, f"Missing 'phase' in CAUSE_TO_SUGGESTION['{key}']"
            assert "hint" in entry, f"Missing 'hint' in CAUSE_TO_SUGGESTION['{key}']"

    @pytest.mark.parametrize("category", ["duplicate_function", "dot_import"])
    def test_newly_added_go_categories(self, category):
        """Categories added in REQ-KZ-GO-501 gap fix are wired end-to-end."""
        cause_map, sem_map = _load_postmortem_dicts()
        assert category in sem_map
        key = sem_map[category]
        assert key in cause_map
        assert "hint" in cause_map[key]
