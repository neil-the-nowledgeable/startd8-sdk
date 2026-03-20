"""Tests for startd8.repair.routing."""

from startd8.repair.config import RepairConfig
from startd8.repair.models import (
    Diagnostic,
    ImportDiagnostic,
    LintDiagnostic,
    SyntaxDiagnostic,
)
from startd8.repair.routing import (
    create_steps_from_route,
    infer_language_from_diagnostics,
    route_failures,
)


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

    def test_python_diagnostics_get_python_only_steps(self):
        """Python files should only get Python routes, not Java/Go/C#/JS steps."""
        diags = [
            SyntaxDiagnostic(category="syntax", file="a.py", message="err", line=1),
            ImportDiagnostic(category="import", file="b.py", message="missing", module="os"),
        ]
        config = RepairConfig()
        route = route_failures(diags, config)
        # Both Python patterns matched
        assert "syntax_error" in route.matched_patterns
        assert "missing_import" in route.matched_patterns
        # Python steps only — no language-specific validate steps
        assert route.steps == [
            "fence_strip", "future_import_reorder", "indent_normalize",
            "bracket_balance", "class_body_dedup", "definition_order_fix",
            "import_completion", "variable_initialization", "duplicate_removal",
            "ast_validate",
        ]
        # Verify no non-Python steps leaked through
        assert "java_syntax_validate" not in route.steps
        assert "go_syntax_validate" not in route.steps
        assert "csharp_syntax_validate" not in route.steps
        assert "js_syntax_validate" not in route.steps

    def test_canonical_step_order(self):
        """Steps always appear in canonical order regardless of input order."""
        diags = [
            ImportDiagnostic(category="import", file="a.py", message="m", module="x"),
            SyntaxDiagnostic(category="syntax", file="a.py", message="e", line=1),
        ]
        config = RepairConfig()
        route = route_failures(diags, config)
        expected_order = [
            "fence_strip", "future_import_reorder", "indent_normalize",
            "bracket_balance", "class_body_dedup", "definition_order_fix",
            "import_completion", "variable_initialization", "duplicate_removal",
            "ast_validate",
        ]
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


class TestLanguageAwareRouting:
    """Language-aware routing selects only matching language routes."""

    def test_java_syntax_route_only_java_steps(self):
        diags = [Diagnostic(category="syntax", file="Test.java", message="error")]
        config = RepairConfig(repairable_categories={"syntax"})
        route = route_failures(diags, config)
        assert "java_syntax_validate" in route.steps
        assert "ast_validate" not in route.steps
        assert "go_syntax_validate" not in route.steps

    def test_go_syntax_route_only_go_steps(self):
        diags = [Diagnostic(category="syntax", file="main.go", message="error")]
        config = RepairConfig(repairable_categories={"syntax"})
        route = route_failures(diags, config)
        assert "go_syntax_validate" in route.steps
        assert "ast_validate" not in route.steps
        assert "java_syntax_validate" not in route.steps

    def test_csharp_syntax_route_only_csharp_steps(self):
        diags = [Diagnostic(category="syntax", file="Test.cs", message="error")]
        config = RepairConfig(repairable_categories={"syntax"})
        route = route_failures(diags, config)
        assert "csharp_syntax_validate" in route.steps
        assert "ast_validate" not in route.steps

    def test_js_syntax_route_only_js_steps(self):
        diags = [Diagnostic(category="syntax", file="app.js", message="error")]
        config = RepairConfig(repairable_categories={"syntax"})
        route = route_failures(diags, config)
        assert "js_syntax_validate" in route.steps
        assert "ast_validate" not in route.steps

    def test_explicit_language_id_overrides_inference(self):
        diags = [Diagnostic(category="syntax", file="unknown.txt", message="error")]
        config = RepairConfig(repairable_categories={"syntax"})
        route = route_failures(diags, config, language_id="java")
        assert "java_syntax_validate" in route.steps
        assert "ast_validate" not in route.steps

    def test_no_language_no_file_ext_matches_all(self):
        """When language cannot be inferred, all routes match (backward compat)."""
        diags = [Diagnostic(category="syntax", file="unknown", message="error")]
        config = RepairConfig(repairable_categories={"syntax"})
        route = route_failures(diags, config)
        # All syntax routes match when language is unknown
        assert "ast_validate" in route.steps
        assert "java_syntax_validate" in route.steps
        assert "go_syntax_validate" in route.steps


class TestInferLanguageFromDiagnostics:
    def test_python_files(self):
        diags = [Diagnostic(category="syntax", file="app.py", message="err")]
        assert infer_language_from_diagnostics(diags) == "python"

    def test_java_files(self):
        diags = [Diagnostic(category="syntax", file="Test.java", message="err")]
        assert infer_language_from_diagnostics(diags) == "java"

    def test_go_files(self):
        diags = [Diagnostic(category="syntax", file="main.go", message="err")]
        assert infer_language_from_diagnostics(diags) == "go"

    def test_csharp_files(self):
        diags = [Diagnostic(category="syntax", file="Service.cs", message="err")]
        assert infer_language_from_diagnostics(diags) == "csharp"

    def test_js_files(self):
        diags = [Diagnostic(category="syntax", file="app.js", message="err")]
        assert infer_language_from_diagnostics(diags) == "nodejs"

    def test_mixed_languages_returns_none(self):
        diags = [
            Diagnostic(category="syntax", file="app.py", message="err"),
            Diagnostic(category="syntax", file="Test.java", message="err"),
        ]
        assert infer_language_from_diagnostics(diags) is None

    def test_unknown_extension_returns_none(self):
        diags = [Diagnostic(category="syntax", file="data.xyz", message="err")]
        assert infer_language_from_diagnostics(diags) is None


class TestStepFactoryCompleteness:
    """Verify all routed steps have factory entries and vice versa."""

    _PENDING_STEPS: set[str] = set()

    def test_all_routed_steps_have_factories_or_pending(self):
        """Every step in _ROUTING_TABLE has a factory or is in the pending set."""
        from startd8.repair.routing import _ROUTING_TABLE, _STEP_FACTORIES

        for _cat, _pattern, steps, _confidence, _lang in _ROUTING_TABLE:
            for step_name in steps:
                assert step_name in _STEP_FACTORIES or step_name in self._PENDING_STEPS, (
                    f"Routing references step '{step_name}' but no factory registered and not pending"
                )

    def test_all_canonical_steps_have_factories_or_pending(self):
        """Every step in _CANONICAL_ORDER has a factory or is pending."""
        from startd8.repair.routing import _CANONICAL_ORDER, _STEP_FACTORIES

        for step_name in _CANONICAL_ORDER:
            assert step_name in _STEP_FACTORIES or step_name in self._PENDING_STEPS, (
                f"Canonical order references step '{step_name}' but no factory and not pending"
            )

    def test_all_factories_in_canonical_order(self):
        """Every factory entry must appear in _CANONICAL_ORDER."""
        from startd8.repair.routing import _CANONICAL_ORDER, _STEP_FACTORIES

        for step_name in _STEP_FACTORIES:
            assert step_name in _CANONICAL_ORDER, (
                f"Factory '{step_name}' registered but missing from _CANONICAL_ORDER"
            )


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
