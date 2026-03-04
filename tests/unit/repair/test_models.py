"""Tests for startd8.repair.models."""

from pathlib import Path

import pytest

from startd8.repair.models import (
    Diagnostic,
    ElementContext,
    FeatureRepairAttribution,
    FileRepairResult,
    ImportDiagnostic,
    LintDiagnostic,
    RepairAttribution,
    RepairContext,
    RepairError,
    RepairOutcome,
    RepairPipelineResult,
    RepairRoute,
    RepairStepResult,
    StagingError,
    SyntaxDiagnostic,
)
from startd8.exceptions import FileOperationError, Startd8Error


class TestDiagnostics:
    def test_syntax_diagnostic(self):
        d = SyntaxDiagnostic(category="syntax", file="foo.py", message="unexpected indent", line=10, col=4)
        assert d.category == "syntax"
        assert d.file == "foo.py"
        assert d.line == 10
        assert d.col == 4

    def test_import_diagnostic(self):
        d = ImportDiagnostic(category="import", file="bar.py", message="No module named 'grpc'", module="grpc", name="")
        assert d.category == "import"
        assert d.module == "grpc"

    def test_lint_diagnostic(self):
        d = LintDiagnostic(category="lint", file="baz.py", message="unused import", rule="F401", line=1, fixable=True)
        assert d.category == "lint"
        assert d.rule == "F401"
        assert d.fixable is True

    def test_diagnostic_base(self):
        d = Diagnostic(category="test", file="x.py", message="test failed")
        assert d.category == "test"


class TestRepairStepResult:
    def test_construction(self):
        r = RepairStepResult(step_name="fence_strip", modified=True, code="x=1")
        assert r.step_name == "fence_strip"
        assert r.modified is True
        assert r.code == "x=1"
        assert r.metrics == {}

    def test_with_metrics(self):
        r = RepairStepResult(step_name="test", modified=False, code="", metrics={"had_fences": True})
        assert r.metrics["had_fences"] is True


class TestRepairAttribution:
    def test_defaults(self):
        a = RepairAttribution()
        assert a.fence_stripped is False
        assert a.nodes_removed == 0

    def test_is_pydantic_model(self):
        a = RepairAttribution(fence_stripped=True)
        d = a.model_dump()
        assert d["fence_stripped"] is True


class TestElementContext:
    def test_default(self):
        ec = ElementContext()
        assert ec.parent_class is None
        assert ec.element_kind is None
        assert ec.imports is None

    def test_with_parent_class(self):
        ec = ElementContext(parent_class="MyClass", element_name="my_method")
        assert ec.parent_class == "MyClass"


class TestRepairContext:
    def test_defaults(self):
        ctx = RepairContext()
        assert ctx.diagnostics == []
        assert ctx.config is None
        assert ctx.element_context is None
        assert ctx.project_root is None

    def test_existing_imports_field(self):
        """R1-S3: existing_imports prevents duplicate imports."""
        ctx = RepairContext(
            existing_imports={Path("foo.py"): {"os", "sys"}},
        )
        assert "os" in ctx.existing_imports[Path("foo.py")]

    def test_manifest_registry_field(self):
        """R3-S8: optional ManifestRegistry."""
        ctx = RepairContext(manifest_registry="mock_registry")
        assert ctx.manifest_registry == "mock_registry"

    def test_forward_manifest_field(self):
        """R7-S1: Phase 2 FLCM awareness."""
        ctx = RepairContext(forward_manifest={"manifest": True})
        assert ctx.forward_manifest is not None


class TestRepairRoute:
    def test_construction(self):
        r = RepairRoute(
            matched_patterns=["syntax_error", "missing_import"],
            steps=["fence_strip", "indent_normalize", "import_completion"],
            confidence="HIGH",
        )
        assert len(r.matched_patterns) == 2
        assert len(r.steps) == 3
        assert r.confidence == "HIGH"

    def test_empty_route(self):
        r = RepairRoute()
        assert r.steps == []
        assert r.matched_patterns == []


class TestFileRepairResult:
    def test_construction(self):
        r = FileRepairResult(
            file_path=Path("foo.py"),
            before_valid=False,
            after_valid=True,
            steps_applied=["fence_strip"],
        )
        assert r.file_path == Path("foo.py")
        assert r.after_valid is True


class TestRepairOutcome:
    def test_empty(self):
        o = RepairOutcome()
        assert o.repaired_files == {}
        assert o.any_modified is False

    def test_with_files(self):
        o = RepairOutcome(
            repaired_files={Path("a.py"): "fixed"},
            any_modified=True,
            steps_applied=["fence_strip"],
        )
        assert o.any_modified is True


class TestRepairPipelineResult:
    def test_construction(self):
        outcome = RepairOutcome(any_modified=True)
        r = RepairPipelineResult(
            outcome=outcome,
            recheckpoint_passed=True,
            metadata={"repair_duration_ms": 42.0},
        )
        assert r.recheckpoint_passed is True
        assert r.metadata["repair_duration_ms"] == 42.0


class TestFeatureRepairAttribution:
    def test_construction(self):
        a = FeatureRepairAttribution(
            feature_name="auth",
            files_repaired=2,
            steps_applied=["fence_strip", "indent_normalize"],
            repair_success=True,
        )
        assert a.feature_name == "auth"
        assert a.files_repaired == 2


class TestExceptionHierarchy:
    def test_repair_error_is_startd8_error(self):
        assert issubclass(RepairError, Startd8Error)
        e = RepairError("test", step_name="fence_strip")
        assert e.step_name == "fence_strip"

    def test_staging_error_is_file_operation_error(self):
        assert issubclass(StagingError, FileOperationError)

    def test_repair_error_propagates(self):
        with pytest.raises(Startd8Error):
            raise RepairError("broken step")

    def test_staging_error_propagates(self):
        with pytest.raises(FileOperationError):
            raise StagingError("staging I/O failed")
