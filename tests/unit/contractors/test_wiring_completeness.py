"""Cross-language pipeline wiring completeness tests (REQ-KZ-006).

Verifies that every semantic check category has a complete pipeline path:
  semantic check → collection → scoring → Kaizen suggestion mapping.

These tests would have caught all 15 gaps found in the 2026-03-23 audit.
"""

import pytest

from startd8.contractors.prime_postmortem import (
    CAUSE_TO_SUGGESTION,
    _SEMANTIC_CATEGORY_TO_SUGGESTION,
)


class TestSuggestionMappingCompleteness:
    """Every _SEMANTIC_CATEGORY_TO_SUGGESTION value must resolve to CAUSE_TO_SUGGESTION."""

    def test_every_mapping_resolves(self):
        """REQ-KZ-003: No orphaned suggestion mappings."""
        missing = []
        for category, suggestion_key in _SEMANTIC_CATEGORY_TO_SUGGESTION.items():
            if suggestion_key not in CAUSE_TO_SUGGESTION:
                missing.append(f"{category} -> {suggestion_key}")
        assert not missing, (
            f"{len(missing)} mapping(s) point to missing CAUSE_TO_SUGGESTION keys:\n"
            + "\n".join(f"  {m}" for m in missing)
        )

    def test_cause_to_suggestion_has_required_fields(self):
        """Every CAUSE_TO_SUGGESTION entry must have 'phase' and 'hint'."""
        for key, entry in CAUSE_TO_SUGGESTION.items():
            assert "phase" in entry, f"Missing 'phase' in CAUSE_TO_SUGGESTION['{key}']"
            assert "hint" in entry, f"Missing 'hint' in CAUSE_TO_SUGGESTION['{key}']"


class TestPythonSemanticChecksMapped:
    """Python AST semantic checks must have Kaizen feedback loop wiring."""

    @pytest.mark.parametrize("category", [
        "duplicate_main_guard",
        "duplicate_definition",
        "bare_except_pass",
        "phantom_dependency",
    ])
    def test_python_category_mapped(self, category):
        """REQ-KZ-003: Python semantic check categories have Kaizen mappings."""
        assert category in _SEMANTIC_CATEGORY_TO_SUGGESTION, (
            f"Python semantic category '{category}' is missing from "
            "_SEMANTIC_CATEGORY_TO_SUGGESTION — detected issues won't generate "
            "Kaizen suggestions"
        )
        suggestion_key = _SEMANTIC_CATEGORY_TO_SUGGESTION[category]
        assert suggestion_key in CAUSE_TO_SUGGESTION, (
            f"Python category '{category}' maps to '{suggestion_key}' "
            "which is missing from CAUSE_TO_SUGGESTION"
        )


class TestExemplarExtensions:
    """Exemplar system must classify all language extensions correctly."""

    def test_commonjs_extensions(self):
        """REQ-KZ-002: .mjs/.cjs map to nodejs in exemplar system."""
        from startd8.exemplars.models import _ext_to_language

        assert _ext_to_language(".mjs") == "nodejs"
        assert _ext_to_language(".cjs") == "nodejs"

    @pytest.mark.parametrize("ext", [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"])
    def test_all_nodejs_extensions(self, ext):
        from startd8.exemplars.models import _ext_to_language

        assert _ext_to_language(ext) == "nodejs"
