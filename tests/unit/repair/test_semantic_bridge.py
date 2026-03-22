"""Tests for startd8.repair.semantic_bridge — diagnostic translation."""

from startd8.repair.semantic_bridge import (
    _REPAIRABLE_CATEGORIES,
    translate_to_diagnostics,
)


class TestTranslateToDiagnostics:
    def test_repairable_category_translated(self):
        issues = [
            {"category": "method_resolution", "severity": "warning",
             "message": "self.index() is module-level", "line": 46, "symbol": "index"},
        ]
        result = translate_to_diagnostics(issues, "locustfile.py")
        assert len(result) == 1
        d = result[0]
        assert d.category == "semantic"
        assert d.semantic_category == "method_resolution"
        assert d.severity == "warning"
        assert d.symbol == "index"
        assert d.line == 46
        assert d.file == "locustfile.py"

    def test_all_repairable_categories(self):
        issues = [
            {"category": "method_resolution", "severity": "warning", "message": "m", "line": 1, "symbol": "x"},
            {"category": "import_resolution", "severity": "error", "message": "m", "line": 2, "symbol": "y"},
            {"category": "discarded_return", "severity": "warning", "message": "m", "line": 3, "symbol": "z"},
            {"category": "duplicate_main_guard", "severity": "warning", "message": "m", "line": 4, "symbol": "w"},
            {"category": "sql_injection_risk", "severity": "error", "message": "m", "line": 5},
        ]
        result = translate_to_diagnostics(issues, "test.py")
        assert len(result) == 5
        # sql_injection_risk produces a plain Diagnostic (category="security"),
        # not a SemanticDiagnostic, so collect categories from both types.
        from startd8.repair.models import SemanticDiagnostic
        semantic_cats = {d.semantic_category for d in result if isinstance(d, SemanticDiagnostic)}
        route_cats = {d.category for d in result if not isinstance(d, SemanticDiagnostic)}
        assert semantic_cats == {"method_resolution", "import_resolution", "discarded_return", "duplicate_main_guard"}
        assert route_cats == {"security"}

    def test_sql_injection_risk_routes_as_security(self):
        """REQ-KZ-CS-402b: sql_injection_risk maps to category='security'."""
        issues = [
            {"category": "sql_injection_risk", "severity": "error",
             "message": "SQL injection risk", "line": 65},
        ]
        result = translate_to_diagnostics(issues, "AlloyDBCartStore.cs")
        assert len(result) == 1
        d = result[0]
        assert d.category == "security"
        assert d.file == "AlloyDBCartStore.cs"
        assert d.message == "SQL injection risk"

    def test_unreachable_function_not_translated(self):
        issues = [
            {"category": "unreachable_function", "severity": "warning",
             "message": "never called", "line": 61, "symbol": "empty_cart"},
        ]
        result = translate_to_diagnostics(issues, "test.py")
        assert len(result) == 0

    def test_unknown_category_skipped(self):
        issues = [
            {"category": "some_future_check", "severity": "info", "message": "m"},
        ]
        result = translate_to_diagnostics(issues, "test.py")
        assert len(result) == 0

    def test_non_dict_skipped(self):
        issues = ["not a dict", 42, None]  # type: ignore[list-item]
        result = translate_to_diagnostics(issues, "test.py")
        assert len(result) == 0

    def test_mixed_repairable_and_not(self):
        issues = [
            {"category": "import_resolution", "severity": "error", "message": "bad import", "line": 4, "symbol": "pkg.mod"},
            {"category": "unreachable_function", "severity": "warning", "message": "dead code", "line": 61, "symbol": "logout"},
            {"category": "method_resolution", "severity": "warning", "message": "self.x()", "line": 46, "symbol": "x"},
        ]
        result = translate_to_diagnostics(issues, "test.py")
        assert len(result) == 2
        assert {d.semantic_category for d in result} == {"import_resolution", "method_resolution"}

    def test_missing_fields_use_defaults(self):
        issues = [{"category": "discarded_return"}]
        result = translate_to_diagnostics(issues, "test.py")
        assert len(result) == 1
        d = result[0]
        assert d.severity == "warning"
        assert d.symbol == ""
        assert d.line == 0
        assert d.message == ""

    def test_empty_list(self):
        result = translate_to_diagnostics([], "test.py")
        assert result == []

    # --- Java-specific cases (REQ-KZ-JV-402e) ---

    def test_sql_injection_risk_java_routes_as_security(self):
        """REQ-KZ-JV-402e: Java sql_injection_risk also maps to category='security'."""
        issues = [
            {"category": "sql_injection_risk", "severity": "error",
             "message": "SQL injection risk", "line": 42},
        ]
        result = translate_to_diagnostics(issues, "UserDao.java")
        assert len(result) == 1
        d = result[0]
        assert d.category == "security"
        assert d.file == "UserDao.java"

    def test_wildcard_import_routes_as_semantic(self):
        """REQ-KZ-JV-402e Phase 2: wildcard_import is repairable and routes as semantic."""
        issues = [
            {"category": "wildcard_import", "severity": "warning",
             "message": "Wildcard import", "line": 3},
        ]
        result = translate_to_diagnostics(issues, "Foo.java")
        assert len(result) == 1
        d = result[0]
        assert d.category == "semantic"
        assert d.semantic_category == "wildcard_import"

    def test_wildcard_import_in_repairable_categories(self):
        """wildcard_import must be in _REPAIRABLE_CATEGORIES."""
        assert "wildcard_import" in _REPAIRABLE_CATEGORIES

    def test_java_advisory_categories_not_translated(self):
        """Advisory-only Java categories should not produce diagnostics."""
        advisory_cats = [
            "system_out_in_service", "interface_file_contains_class",
            "empty_catch_block", "raw_type_usage", "missing_override",
            "missing_access_modifier", "package_filepath_mismatch",
            "package_case_mismatch",
        ]
        issues = [
            {"category": cat, "severity": "warning", "message": "m", "line": 1}
            for cat in advisory_cats
        ]
        result = translate_to_diagnostics(issues, "Foo.java")
        assert len(result) == 0
