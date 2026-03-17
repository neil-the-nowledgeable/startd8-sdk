"""Tests for startd8.repair.models — REQ-RPL-004 and REQ-RPL-403 field enrichment."""

from pathlib import Path

from startd8.repair.models import (
    FeatureRepairAttribution,
    RepairContext,
    SemanticDiagnostic,
)


class TestRepairContextFields:
    """REQ-RPL-004: RepairContext enrichment."""

    def test_defaults(self):
        ctx = RepairContext()
        assert ctx.feature_name == ""
        assert ctx.attempt_number == 0
        assert ctx.skeleton_content is None
        assert ctx.project_root is None

    def test_feature_name(self):
        ctx = RepairContext(feature_name="auth-login")
        assert ctx.feature_name == "auth-login"

    def test_attempt_number(self):
        ctx = RepairContext(attempt_number=2)
        assert ctx.attempt_number == 2

    def test_all_fields_together(self):
        ctx = RepairContext(
            feature_name="payment",
            attempt_number=3,
            project_root=Path("/tmp"),
        )
        assert ctx.feature_name == "payment"
        assert ctx.attempt_number == 3
        assert ctx.project_root == Path("/tmp")

    def test_removed_fields_absent(self):
        """Verify dead fields (forward_manifest, service_metadata, test_regressions) were removed."""
        ctx = RepairContext()
        assert not hasattr(ctx, "forward_manifest")
        assert not hasattr(ctx, "service_metadata")
        assert not hasattr(ctx, "test_regressions")


class TestSemanticDiagnostic:
    """Semantic repair diagnostic fields (REQ-SR-100–400)."""

    def test_defaults(self):
        d = SemanticDiagnostic(category="semantic", file="x.py", message="test")
        assert d.category == "semantic"
        assert d.semantic_category == ""
        assert d.severity == "warning"
        assert d.symbol == ""
        assert d.line == 0

    def test_category_auto_set(self):
        d = SemanticDiagnostic(category="wrong", file="x.py", message="test")
        assert d.category == "semantic"  # __post_init__ forces "semantic"

    def test_populated(self):
        d = SemanticDiagnostic(
            category="semantic",
            file="locustfile.py",
            message="'self.index()' is module-level",
            semantic_category="method_resolution",
            severity="warning",
            symbol="index",
            line=46,
        )
        assert d.semantic_category == "method_resolution"
        assert d.severity == "warning"
        assert d.symbol == "index"
        assert d.line == 46


class TestFeatureRepairAttributionNewFields:
    """REQ-RPL-403: FeatureRepairAttribution enrichment."""

    def test_defaults(self):
        attr = FeatureRepairAttribution()
        assert attr.feature_name == ""
        assert attr.files_repaired == 0
        assert attr.total_steps_applied == 0
        assert attr.total_steps_reverted == 0
        assert attr.lines_added == 0
        assert attr.lines_removed == 0
        assert attr.imports_added == []
        assert attr.fences_stripped == 0
        assert attr.indent_fixes == 0
        assert attr.brackets_balanced == 0
        assert attr.duplicates_removed == 0
        assert attr.lint_fixes == 0
        assert attr.wall_clock_ms == 0.0
        assert attr.per_file == {}
        assert attr.steps_applied == []
        assert attr.repair_success is False

    def test_populated(self):
        attr = FeatureRepairAttribution(
            feature_name="auth",
            files_repaired=3,
            total_steps_applied=5,
            total_steps_reverted=1,
            lines_added=42,
            lines_removed=10,
            imports_added=["os", "sys"],
            fences_stripped=2,
            indent_fixes=1,
            brackets_balanced=0,
            duplicates_removed=3,
            lint_fixes=2,
            wall_clock_ms=150.5,
            per_file={"foo.py": {"steps": 2}},
            steps_applied=["fence_strip", "import_completion"],
            repair_success=True,
        )
        assert attr.feature_name == "auth"
        assert attr.files_repaired == 3
        assert attr.total_steps_applied == 5
        assert attr.total_steps_reverted == 1
        assert attr.lines_added == 42
        assert attr.lines_removed == 10
        assert attr.imports_added == ["os", "sys"]
        assert attr.fences_stripped == 2
        assert attr.wall_clock_ms == 150.5
        assert attr.per_file == {"foo.py": {"steps": 2}}
        assert attr.repair_success is True

    def test_list_defaults_not_shared(self):
        a = FeatureRepairAttribution()
        b = FeatureRepairAttribution()
        a.imports_added.append("os")
        a.steps_applied.append("fence_strip")
        assert b.imports_added == []
        assert b.steps_applied == []
