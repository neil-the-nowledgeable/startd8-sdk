"""Tests for fingerprint pattern consolidation (REQ-KZ-GO-402a).

Verifies that Go contamination patterns come from a single canonical
source and that all locations reference it instead of maintaining
independent copies.
"""

from startd8.languages._validation_utils import (
    GO_CONTAMINATION_FINGERPRINTS,
    PYTHON_FINGERPRINTS,
)


class TestFingerprintConsolidation:

    def test_go_superset_of_python_minus_exclusions(self):
        """GO_CONTAMINATION_FINGERPRINTS covers PYTHON_FINGERPRINTS minus
        intentional exclusions.

        ``print(`` is excluded from Go because it false-positives on Go's
        builtin ``print()``/``println()`` and on ``fmt.Fprint(``.  Python
        ``print()`` contamination always co-occurs with stronger signals.
        """
        # Patterns intentionally excluded from Go fingerprints
        go_exclusions = {"print("}
        go_set = set(GO_CONTAMINATION_FINGERPRINTS)
        py_set = set(PYTHON_FINGERPRINTS) - go_exclusions
        missing = py_set - go_set
        assert not missing, (
            f"GO_CONTAMINATION_FINGERPRINTS missing patterns from "
            f"PYTHON_FINGERPRINTS: {missing}"
        )

    def test_go_has_extended_patterns(self):
        """Go patterns include class/raise/main-guard beyond base Python set."""
        go_set = set(GO_CONTAMINATION_FINGERPRINTS)
        assert "class " in go_set
        assert "raise " in go_set
        assert "if __name__" in go_set

    def test_go_semantic_checks_uses_canonical(self):
        """go_semantic_checks imports from _validation_utils, not inline."""
        import startd8.validators.go_semantic_checks as mod
        # The module should import GO_CONTAMINATION_FINGERPRINTS
        assert hasattr(mod, "GO_CONTAMINATION_FINGERPRINTS"), (
            "go_semantic_checks should import GO_CONTAMINATION_FINGERPRINTS"
        )

    def test_no_duplicate_patterns(self):
        """No duplicate entries in either fingerprint tuple."""
        assert len(GO_CONTAMINATION_FINGERPRINTS) == len(set(GO_CONTAMINATION_FINGERPRINTS))
        assert len(PYTHON_FINGERPRINTS) == len(set(PYTHON_FINGERPRINTS))
