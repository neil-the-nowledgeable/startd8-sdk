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
        ]
        result = translate_to_diagnostics(issues, "test.py")
        assert len(result) == 4
        categories = {d.semantic_category for d in result}
        assert categories == _REPAIRABLE_CATEGORIES

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
