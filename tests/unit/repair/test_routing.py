"""Tests for startd8.repair.routing."""

from startd8.repair.config import RepairConfig
from startd8.repair.models import (
    Diagnostic,
    ImportDiagnostic,
    LintDiagnostic,
    SyntaxDiagnostic,
)
from startd8.repair.routing import create_steps_from_route, route_failures


class TestRouteFailures:
    def test_syntax_error_routes_correctly(self):
        diags = [SyntaxDiagnostic(category="syntax", file="x.py", message="unexpected indent", line=5)]
        config = RepairConfig()
        route = route_failures(diags, config)
        assert "syntax_error" in route.matched_patterns
        assert "fence_strip" in route.steps
        assert "future_import_reorder" in route.steps
        assert "indent_normalize" in route.steps
        assert "ast_validate" in route.steps
        assert route.confidence == "HIGH"

    def test_import_error_routes_correctly(self):
        diags = [ImportDiagnostic(category="import", file="x.py", message="No module named 'foo'", module="foo")]
        config = RepairConfig()
        route = route_failures(diags, config)
        assert "missing_import" in route.matched_patterns
        assert "import_completion" in route.steps
        assert "duplicate_removal" in route.steps
        assert "ast_validate" in route.steps

    def test_lint_error_routes_correctly(self):
        diags = [LintDiagnostic(category="lint", file="x.py", message="F401 unused", rule="F401", line=1)]
        config = RepairConfig()
        route = route_failures(diags, config)
        assert "lint_violation" in route.matched_patterns
        assert "import_completion" in route.steps
        assert route.confidence == "MEDIUM"

    def test_f821_dual_diagnostic_routes_import_completion(self):
        """F821 emits both lint and import diagnostics; import_completion step is routed."""
        diags = [
            LintDiagnostic(category="lint", file="app.py", message="Undefined name `Flask`", rule="F821", line=7),
            ImportDiagnostic(category="import", file="app.py", message="Undefined name `Flask`", module="flask", name="Flask"),
        ]
        config = RepairConfig()
        route = route_failures(diags, config)
        assert "lint_violation" in route.matched_patterns
        assert "missing_import" in route.matched_patterns
        assert "import_completion" in route.steps
        assert "fence_strip" in route.steps
        assert "ast_validate" in route.steps

    def test_non_repairable_category_empty(self):
        """Test, size categories are not repairable."""
        diags = [Diagnostic(category="test", file="x.py", message="test failed")]
        config = RepairConfig()
        route = route_failures(diags, config)
        assert route.steps == []
        assert route.matched_patterns == []

    def test_multiple_diagnostics_merge_and_dedup(self):
        diags = [
            SyntaxDiagnostic(category="syntax", file="a.py", message="err", line=1),
            ImportDiagnostic(category="import", file="b.py", message="missing", module="os"),
        ]
        config = RepairConfig()
        route = route_failures(diags, config)
        # Both patterns matched
        assert "syntax_error" in route.matched_patterns
        assert "missing_import" in route.matched_patterns
        # Steps deduplicated and in canonical order
        assert route.steps == ["fence_strip", "future_import_reorder", "indent_normalize", "import_completion", "duplicate_removal", "ast_validate"]

    def test_canonical_step_order(self):
        """Steps always appear in canonical order regardless of input order."""
        diags = [
            ImportDiagnostic(category="import", file="a.py", message="m", module="x"),
            SyntaxDiagnostic(category="syntax", file="a.py", message="e", line=1),
        ]
        config = RepairConfig()
        route = route_failures(diags, config)
        expected_order = ["fence_strip", "future_import_reorder", "indent_normalize", "import_completion", "duplicate_removal", "ast_validate"]
        assert route.steps == expected_order

    def test_disabled_category_not_routed(self):
        diags = [SyntaxDiagnostic(category="syntax", file="x.py", message="err", line=1)]
        config = RepairConfig(repairable_categories=frozenset({"import"}))
        route = route_failures(diags, config)
        assert route.steps == []

    def test_route_has_deterministic_ordering(self):
        """R1-S1: RepairRoute has deterministic ordering and matched_patterns."""
        diags = [SyntaxDiagnostic(category="syntax", file="x.py", message="e", line=1)]
        config = RepairConfig()
        route1 = route_failures(diags, config)
        route2 = route_failures(diags, config)
        assert route1.steps == route2.steps
        assert route1.matched_patterns == route2.matched_patterns


class TestCreateStepsFromRoute:
    def test_creates_step_objects(self):
        from startd8.repair.models import RepairRoute
        route = RepairRoute(steps=["fence_strip", "ast_validate"])
        steps = create_steps_from_route(route)
        assert len(steps) == 2
        assert steps[0].name == "fence_strip"
        assert steps[1].name == "ast_validate"

    def test_unknown_step_skipped(self):
        from startd8.repair.models import RepairRoute
        route = RepairRoute(steps=["nonexistent_step"])
        steps = create_steps_from_route(route)
        assert len(steps) == 0
