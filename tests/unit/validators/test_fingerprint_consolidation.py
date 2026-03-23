"""Tests for fingerprint pattern consolidation (REQ-KZ-GO-402a).

Verifies that contamination patterns come from a single canonical
source and that all languages reference centralized fingerprints
instead of maintaining independent copies.
"""

from startd8.languages._validation_utils import (
    CONTAMINATION_FINGERPRINTS,
    GO_CONTAMINATION_FINGERPRINTS,
    JAVA_CONTAMINATION_FINGERPRINTS,
    NODEJS_CONTAMINATION_FINGERPRINTS,
    PYTHON_FINGERPRINTS,
    get_contamination_fingerprints,
)


class TestFingerprintConsolidation:

    def test_go_superset_of_python_minus_exclusions(self):
        """GO_CONTAMINATION_FINGERPRINTS covers PYTHON_FINGERPRINTS minus
        intentional exclusions.

        ``print(`` is excluded from Go because it false-positives on Go's
        builtin ``print()``/``println()`` and on ``fmt.Fprint(``.
        """
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

    def test_java_excludes_class(self):
        """Java fingerprints exclude 'class ' (Java has classes)."""
        assert "class " not in JAVA_CONTAMINATION_FINGERPRINTS

    def test_nodejs_excludes_class(self):
        """Node.js fingerprints exclude 'class ' (JS has classes)."""
        assert "class " not in NODEJS_CONTAMINATION_FINGERPRINTS

    def test_all_languages_have_core_fingerprints(self):
        """Every language's fingerprints include the core Python signals."""
        core = {"def ", "from __future__", "#!/usr/bin/env python"}
        for lang_id, fps in CONTAMINATION_FINGERPRINTS.items():
            fp_set = set(fps)
            missing = core - fp_set
            assert not missing, (
                f"{lang_id} missing core fingerprints: {missing}"
            )

    def test_go_semantic_checks_uses_canonical(self):
        """go_semantic_checks imports from _validation_utils, not inline."""
        import startd8.validators.go_semantic_checks as mod
        assert hasattr(mod, "GO_CONTAMINATION_FINGERPRINTS")

    def test_nodejs_uses_centralized(self):
        """nodejs_semantic_checks uses get_contamination_fingerprints, not local copy."""
        import startd8.validators.nodejs_semantic_checks as mod
        # The module's _PY_FINGERPRINTS should be the centralized tuple
        assert mod._PY_FINGERPRINTS == get_contamination_fingerprints("nodejs")

    def test_java_uses_centralized(self):
        """java_semantic_checks imports from _validation_utils."""
        import startd8.validators.java_semantic_checks as mod
        assert hasattr(mod, "get_contamination_fingerprints")

    def test_no_duplicate_patterns(self):
        """No duplicate entries in any fingerprint tuple."""
        for name, fps in [
            ("PYTHON", PYTHON_FINGERPRINTS),
            ("GO", GO_CONTAMINATION_FINGERPRINTS),
            ("JAVA", JAVA_CONTAMINATION_FINGERPRINTS),
            ("NODEJS", NODEJS_CONTAMINATION_FINGERPRINTS),
        ]:
            assert len(fps) == len(set(fps)), f"Duplicates in {name}_FINGERPRINTS"

    def test_registry_covers_all_languages(self):
        """Every non-Python language has an entry in CONTAMINATION_FINGERPRINTS."""
        for lang_id in ("go", "java", "csharp", "nodejs"):
            assert lang_id in CONTAMINATION_FINGERPRINTS, (
                f"Missing CONTAMINATION_FINGERPRINTS entry for {lang_id}"
            )

    def test_get_contamination_fingerprints_fallback(self):
        """Unknown language falls back to base PYTHON_FINGERPRINTS."""
        result = get_contamination_fingerprints("cobol")
        assert result == PYTHON_FINGERPRINTS
