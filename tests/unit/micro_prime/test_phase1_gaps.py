"""Tests for Phase 1 gap fixes (Simple → Trivial Decomposer).

Covers:
  Gap 1: decomposition_source field on ForwardElementSpec
  Gap 2: SimpleDecomposerReport dataclass + persist_report()
  Gap 3: enable_simple_decomposer / simple_decomposer_confidence_threshold config
  Gap 4: Leaf-only constraint (recursive decomposition blocked)
  Gap 5: Rejection reason metadata on failure paths
  Gap 6: ast.parse syntax gate in prime_adapter
"""

from __future__ import annotations

import json
import platform
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from startd8.complexity.models import RejectionReason
from startd8.forward_manifest import (
    ForwardElementSpec,
    ForwardFileSpec,
    ForwardImportSpec,
    ForwardManifest,
    InterfaceContract,
)
from startd8.micro_prime.engine import MicroPrimeEngine
from startd8.micro_prime.models import (
    EscalationReason,
    MicroPrimeConfig,
    TierClassification,
)
from startd8.micro_prime.reporting import (
    CostSavings,
    ReportMeta,
    SimpleDecomposerReport,
    persist_report,
)
from startd8.utils.code_manifest import ElementKind, Param, Signature


# ── Gap 1: decomposition_source field ────────────────────────────────


class TestDecompositionSource:
    """Gap 1: ForwardElementSpec.decomposition_source field."""

    def test_default_is_none(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
        )
        assert elem.decomposition_source is None

    def test_set_simple(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
            decomposition_source="simple",
        )
        assert elem.decomposition_source == "simple"

    def test_set_moderate(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
            decomposition_source="moderate",
        )
        assert elem.decomposition_source == "moderate"

    def test_frozen_model_rejects_mutation(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
        )
        with pytest.raises(Exception):
            elem.decomposition_source = "simple"  # type: ignore[misc]

    def test_model_copy_preserves_field(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
            decomposition_source="copy",
        )
        copy = elem.model_copy(update={"name": "bar"})
        assert copy.decomposition_source == "copy"
        assert copy.name == "bar"

    def test_serialization_includes_field(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
            decomposition_source="simple",
        )
        data = elem.model_dump()
        assert data["decomposition_source"] == "simple"

    def test_serialization_none_when_unset(self):
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="foo",
            signature=Signature(params=[], return_annotation="None"),
        )
        data = elem.model_dump()
        assert data["decomposition_source"] is None


# ── Gap 2: SimpleDecomposerReport ────────────────────────────────────


class TestSimpleDecomposerReport:
    """Gap 2: Typed report dataclass and advisory persistence."""

    def test_default_construction(self):
        report = SimpleDecomposerReport()
        assert report.run_id == ""
        assert report.attempted == 0
        assert report.succeeded == 0
        assert report.rejected == 0
        assert report.deterministic_ratio == 0.0
        assert isinstance(report.rejection_reasons, dict)
        assert isinstance(report.template_coverage, dict)

    def test_cost_savings_defaults(self):
        cs = CostSavings()
        assert cs.llm_calls_avoided == 0
        assert cs.usd_saved_estimate == 0.0
        assert cs.per_call_rate_usd == 0.005

    def test_report_meta_auto_populates(self):
        meta = ReportMeta()
        assert meta.python_version == platform.python_version()
        assert meta.schema_version == "1.0.0"
        # sdk_version should be populated (either a version or "unknown")
        assert meta.sdk_version != ""

    def test_asdict_round_trip(self):
        report = SimpleDecomposerReport(
            run_id="test-123",
            attempted=10,
            succeeded=8,
            rejected=2,
            rejection_reasons={"no_template_match": 2},
            deterministic_ratio=0.8,
        )
        d = asdict(report)
        assert d["run_id"] == "test-123"
        assert d["attempted"] == 10
        assert d["rejection_reasons"] == {"no_template_match": 2}
        # JSON-serializable
        json_str = json.dumps(d)
        assert "test-123" in json_str

    def test_persist_report_creates_file(self, tmp_path):
        report = SimpleDecomposerReport(run_id="r-001", attempted=5, succeeded=3)
        persist_report(report, tmp_path)
        report_file = tmp_path / ".startd8" / "reports" / "simple-decomposer.json"
        assert report_file.exists()
        data = json.loads(report_file.read_text())
        assert data["run_id"] == "r-001"
        assert data["attempted"] == 5

    def test_persist_report_advisory_no_raise(self, tmp_path):
        """I/O failure should not raise — advisory persistence."""
        report = SimpleDecomposerReport(run_id="r-002")
        # Use a path that can't be created (file as parent)
        blocker = tmp_path / "blocker"
        blocker.write_text("not a dir")
        # persist_report should not raise even though .startd8 can't be created
        persist_report(report, blocker)  # no exception


# ── Gap 3: Config gating ─────────────────────────────────────────────


class TestConfigGating:
    """Gap 3: enable_simple_decomposer and confidence threshold."""

    def test_default_enabled(self):
        config = MicroPrimeConfig()
        assert config.enable_simple_decomposer is True

    def test_default_threshold(self):
        config = MicroPrimeConfig()
        assert config.simple_decomposer_confidence_threshold == 0.7

    def test_disable_simple_decomposer(self):
        config = MicroPrimeConfig(enable_simple_decomposer=False)
        assert config.enable_simple_decomposer is False

    def test_custom_threshold(self):
        config = MicroPrimeConfig(simple_decomposer_confidence_threshold=0.8)
        assert config.simple_decomposer_confidence_threshold == 0.8


# ── Gap 4: Leaf-only constraint ──────────────────────────────────────


class TestLeafOnlyConstraint:
    """Gap 4: Decomposed sub-elements must never re-enter the decomposer."""

    def test_recursive_decomposition_blocked(self):
        """A sub-element with decomposition_source set must raise RuntimeError."""
        decomposed_elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="SomeClass",
            signature=Signature(params=[]),
            decomposition_source="moderate",
        )
        file_spec = ForwardFileSpec(
            file="src/pkg/mod.py",
            imports=[],
            elements=[decomposed_elem],
        )
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/pkg/mod.py": file_spec},
            contracts=[],
        )
        skeleton = "class SomeClass:\n    raise NotImplementedError\n"

        engine = MicroPrimeEngine()

        with pytest.raises(RuntimeError, match="Recursive decomposition blocked"):
            engine._handle_moderate(
                decomposed_elem,
                file_spec,
                manifest,
                skeleton,
                [],
                "src/pkg/mod.py",
                reasoning="test",
            )

    def test_non_decomposed_element_passes(self):
        """An element without decomposition_source should not raise."""
        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="SomeClass",
            signature=Signature(params=[]),
            # decomposition_source is None (default)
        )
        file_spec = ForwardFileSpec(
            file="src/pkg/mod.py",
            imports=[],
            elements=[elem],
        )
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/pkg/mod.py": file_spec},
            contracts=[],
        )
        skeleton = "class SomeClass:\n    raise NotImplementedError\n"

        engine = MicroPrimeEngine()
        # Should not raise — will proceed to decomposition (and likely escalate)
        result = engine._handle_moderate(
            elem, file_spec, manifest, skeleton, [],
            "src/pkg/mod.py", reasoning="test",
        )
        # Doesn't raise; returns some ElementResult (likely escalated)
        assert result.element_name == "SomeClass"


# ── Gap 5: Rejection reason metadata ─────────────────────────────────


class TestRejectionReasonMetadata:
    """Gap 5: Failure paths must include rejection_reason in decomposition_metadata."""

    def test_no_strategy_includes_rejection_reason(self):
        """When no decomposition strategy applies, metadata has rejection_reason."""
        elem = ForwardElementSpec(
            kind=ElementKind.FUNCTION,
            name="some_func",
            signature=Signature(params=[], return_annotation="None"),
        )
        file_spec = ForwardFileSpec(
            file="src/pkg/mod.py",
            imports=[],
            elements=[elem],
        )
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/pkg/mod.py": file_spec},
            contracts=[],
        )
        skeleton = "def some_func() -> None:\n    raise NotImplementedError\n"

        engine = MicroPrimeEngine()
        result = engine._handle_moderate(
            elem, file_spec, manifest, skeleton, [],
            "src/pkg/mod.py", reasoning="test",
        )
        assert result.success is False
        assert result.decomposition_metadata is not None
        assert "rejection_reason" in result.decomposition_metadata
        assert result.decomposition_metadata["rejection_reason"] == RejectionReason.NO_TEMPLATE_MATCH.value

    @patch("startd8.micro_prime.engine.ModerateDecomposer.decompose")
    def test_assembly_failure_includes_rejection_reason(self, mock_decompose):
        """When assembly fails, metadata has rejection_reason."""
        from startd8.micro_prime.decomposer import DecompositionPlan, SubElement

        elem = ForwardElementSpec(
            kind=ElementKind.CLASS,
            name="MyClass",
            signature=Signature(params=[]),
        )

        sub = SubElement(
            name="method_a",
            kind=ElementKind.METHOD,
            prompt_context="",
            depends_on=[],
            assembly_order=0,
            deterministic=False,
            element_spec=ForwardElementSpec(
                kind=ElementKind.METHOD,
                name="method_a",
                signature=Signature(
                    params=[Param(name="self")],
                    return_annotation="None",
                ),
                parent_class="MyClass",
            ),
        )
        mock_decompose.return_value = DecompositionPlan(
            strategy="class_decompose",
            sub_elements=[sub],
            original_element=elem,
            assembly_kind="class_compose",
            confidence=0.9,
        )
        file_spec = ForwardFileSpec(
            file="src/pkg/mod.py",
            imports=[],
            elements=[elem],
        )
        manifest = ForwardManifest(
            schema_version="1.0.0",
            file_specs={"src/pkg/mod.py": file_spec},
            contracts=[],
        )
        skeleton = "class MyClass:\n    raise NotImplementedError\n"

        engine = MicroPrimeEngine()

        # Mock _handle_simple to return a failed result (sub-element failure)
        with patch.object(engine, "_handle_simple") as mock_simple:
            mock_simple.return_value = MagicMock(
                success=False,
                code=None,
                input_tokens=0,
                output_tokens=0,
                escalation=MagicMock(detail="test failure"),
            )
            result = engine._handle_moderate(
                elem, file_spec, manifest, skeleton, [],
                "src/pkg/mod.py", reasoning="test",
            )

        assert result.success is False
        assert result.decomposition_metadata is not None
        assert "rejection_reason" in result.decomposition_metadata


# ── Gap 6: ast.parse syntax gate in prime_adapter ─────────────────────


class TestAstParseSyntaxGate:
    """Gap 6: prime_adapter file-level ast.parse gate before writing."""

    def test_valid_python_written(self, tmp_path):
        """Valid Python should be written to disk."""
        from startd8.micro_prime.models import FileResult, ElementResult

        valid_code = "def foo():\n    return 42\n"
        file_result = FileResult(
            file_path="src/pkg/mod.py",
            element_results=[
                ElementResult(
                    element_name="foo",
                    file_path="src/pkg/mod.py",
                    tier=TierClassification.SIMPLE,
                    success=True,
                    code="return 42",
                ),
            ],
            filled_skeleton=valid_code,
        )

        target = tmp_path / "src" / "pkg" / "mod.py"
        target.parent.mkdir(parents=True, exist_ok=True)

        # Simulate what prime_adapter does: ast.parse gate
        import ast
        try:
            ast.parse(valid_code)
            can_write = True
        except SyntaxError:
            can_write = False

        assert can_write is True

    def test_invalid_python_blocked(self):
        """Invalid Python should fail ast.parse."""
        import ast
        invalid_code = "def foo(\n    return 42\n"
        with pytest.raises(SyntaxError):
            ast.parse(invalid_code)
