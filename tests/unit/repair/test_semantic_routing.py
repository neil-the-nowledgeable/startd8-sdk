"""Tests for semantic repair routing extensions (REQ-SR-100–400)."""

from startd8.repair.config import RepairConfig
from startd8.repair.models import SemanticDiagnostic, SyntaxDiagnostic
from startd8.repair.routing import infer_language_from_diagnostics, route_failures


def _make_config(**overrides):
    """Build RepairConfig with semantic categories enabled."""
    defaults = dict(
        semantic_repair_categories=frozenset({
            "method_resolution", "import_resolution",
            "discarded_return", "duplicate_main_guard",
        }),
    )
    defaults.update(overrides)
    return RepairConfig(**defaults)


class TestSemanticRouting:
    def test_method_resolution_routes(self):
        diags = [SemanticDiagnostic(
            category="semantic", file="locustfile.py", message="self.index()",
            semantic_category="method_resolution", symbol="index", line=46,
        )]
        route = route_failures(diags, _make_config())
        assert "method_resolution" in route.matched_patterns
        assert "semantic_method_resolution_fix" in route.steps
        assert "ast_validate" in route.steps

    def test_import_resolution_routes(self):
        diags = [SemanticDiagnostic(
            category="semantic", file="email_client.py", message="unresolvable",
            semantic_category="import_resolution", symbol="emailservice.email_server", line=4,
        )]
        route = route_failures(diags, _make_config())
        assert "import_resolution" in route.matched_patterns
        assert "semantic_import_fix" in route.steps

    def test_discarded_return_routes(self):
        diags = [SemanticDiagnostic(
            category="semantic", file="server.py", message="discarded",
            semantic_category="discarded_return", symbol="os.environ.get", line=33,
        )]
        route = route_failures(diags, _make_config())
        assert "discarded_return" in route.matched_patterns
        assert "semantic_discarded_return_fix" in route.steps
        assert route.confidence == "MEDIUM"

    def test_duplicate_main_guard_routes(self):
        diags = [SemanticDiagnostic(
            category="semantic", file="main.py", message="duplicate",
            semantic_category="duplicate_main_guard", symbol="__main__", line=85,
        )]
        route = route_failures(diags, _make_config())
        assert "duplicate_main_guard" in route.matched_patterns
        assert "semantic_duplicate_main_fix" in route.steps

    def test_multiple_categories_produce_union(self):
        diags = [
            SemanticDiagnostic(
                category="semantic", file="f.py", message="m1",
                semantic_category="method_resolution", symbol="x", line=1,
            ),
            SemanticDiagnostic(
                category="semantic", file="f.py", message="m2",
                semantic_category="import_resolution", symbol="y", line=2,
            ),
        ]
        route = route_failures(diags, _make_config())
        assert "method_resolution" in route.matched_patterns
        assert "import_resolution" in route.matched_patterns
        assert "semantic_method_resolution_fix" in route.steps
        assert "semantic_import_fix" in route.steps
        # Both have ast_validate — should appear only once
        assert route.steps.count("ast_validate") == 1

    def test_semantic_excluded_from_repairable_categories(self):
        """When 'semantic' is removed from repairable_categories, no semantic route."""
        diags = [SemanticDiagnostic(
            category="semantic", file="f.py", message="m",
            semantic_category="method_resolution", symbol="x", line=1,
        )]
        config = RepairConfig(repairable_categories=frozenset({"syntax", "import", "lint"}))
        route = route_failures(diags, config)
        assert "semantic_method_resolution_fix" not in route.steps
        assert "method_resolution" not in route.matched_patterns

    def test_routing_matches_with_default_config(self):
        """Default config includes 'semantic' in repairable_categories — routing matches.

        The actual per-category gating (semantic_repair_categories) is enforced
        upstream in run_semantic_repair(), not in route_failures().
        """
        diags = [SemanticDiagnostic(
            category="semantic", file="f.py", message="m",
            semantic_category="method_resolution", symbol="x", line=1,
        )]
        config = RepairConfig()  # "semantic" in repairable_categories by default
        route = route_failures(diags, config)
        assert "method_resolution" in route.matched_patterns

    def test_semantic_does_not_interfere_with_syntax(self):
        """Semantic diagnostics don't affect syntax routing and vice versa."""
        diags = [
            SyntaxDiagnostic(category="syntax", file="a.py", message="err", line=1),
            SemanticDiagnostic(
                category="semantic", file="b.py", message="m",
                semantic_category="import_resolution", symbol="x", line=5,
            ),
        ]
        route = route_failures(diags, _make_config())
        assert "syntax_error" in route.matched_patterns
        assert "import_resolution" in route.matched_patterns
        assert "fence_strip" in route.steps  # from syntax
        assert "semantic_import_fix" in route.steps  # from semantic

    def test_unregistered_semantic_category_skipped(self):
        """A SemanticDiagnostic with unknown sub-category doesn't match anything."""
        diags = [SemanticDiagnostic(
            category="semantic", file="f.py", message="m",
            semantic_category="unknown_check", symbol="x", line=1,
        )]
        route = route_failures(diags, _make_config())
        assert route.steps == [] or all("semantic" not in s for s in route.steps if s != "ast_validate")

    def test_canonical_order_preserved(self):
        """Semantic steps appear in canonical order relative to other steps."""
        diags = [
            SemanticDiagnostic(
                category="semantic", file="f.py", message="m",
                semantic_category="import_resolution", symbol="x", line=1,
            ),
            SemanticDiagnostic(
                category="semantic", file="f.py", message="m",
                semantic_category="method_resolution", symbol="y", line=2,
            ),
        ]
        route = route_failures(diags, _make_config())
        # import_fix comes before method_resolution_fix in canonical order
        if "semantic_import_fix" in route.steps and "semantic_method_resolution_fix" in route.steps:
            idx_import = route.steps.index("semantic_import_fix")
            idx_method = route.steps.index("semantic_method_resolution_fix")
            assert idx_import < idx_method


def test_infer_language_from_diagnostics_vue() -> None:
    """REQ-VUE-B-006: ``.vue`` diagnostics map to ``vue`` for routing."""
    diags = [
        SyntaxDiagnostic(category="syntax", file="src/App.vue", message="x", line=1),
    ]
    assert infer_language_from_diagnostics(diags) == "vue"
