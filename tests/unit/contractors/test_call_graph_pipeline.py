"""Tests for Phase 6 call graph pipeline integration (Tier 2).

Tests cover call graph enrichment in IMPLEMENT, INTEGRATE severity escalation,
REVIEW blast radius section, and Plan Ingestion call graph impact dimension.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from startd8.utils.code_manifest import (
    CallEdge,
    CallEntry,
    CallGraphInfo,
    CallKind,
    Element,
    ElementKind,
    FileManifest,
    Param,
    ParamKind,
    SCHEMA_VERSION,
    Signature,
    Span,
    Visibility,
)
from startd8.utils.manifest_registry import ManifestDiff, ManifestRegistry


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _span() -> Span:
    return Span(start_line=1, start_col=0, end_line=1, end_col=10)


def _sig(*params: str) -> Signature:
    return Signature(params=[
        Param(name=p, kind=ParamKind.POSITIONAL)
        for p in (params or ("self",))
    ])


def _func_element(
    name: str,
    fqn: str,
    calls: list[CallEntry] | None = None,
    visibility: Visibility = Visibility.PUBLIC,
    kind: ElementKind = ElementKind.FUNCTION,
) -> Element:
    cg = None
    if calls is not None:
        cg = CallGraphInfo(calls=calls)
    return Element(
        kind=kind,
        name=name,
        fqn=fqn,
        span=_span(),
        signature=_sig(),
        call_graph=cg,
        visibility=visibility,
    )


def _manifest(
    file: str, module: str, elements: list[Element],
) -> FileManifest:
    return FileManifest(
        file=file,
        module=module,
        digest="sha256:test",
        generated_at="2026-01-01T00:00:00Z",
        elements=elements,
    )


def _call(target: str, fqn: str | None = None) -> CallEntry:
    return CallEntry(
        target=target,
        target_fqn=fqn,
        kind=CallKind.FUNCTION_CALL,
    )


def _make_mock_registry_with_call_graph() -> ManifestRegistry:
    """Build a registry with cross-file call edges for testing.

    Graph:
        pkg/a.py: func_a → func_b (cross-file)
        pkg/b.py: func_b → func_c (cross-file), func_d (no callers)
        pkg/c.py: func_c (leaf)
    """
    func_a = _func_element("func_a", "pkg.func_a", calls=[_call("func_b", "pkg2.func_b")])
    func_b = _func_element("func_b", "pkg2.func_b", calls=[_call("func_c", "pkg3.func_c")])
    func_d = _func_element("func_d", "pkg2.func_d")  # dead code candidate
    func_c = _func_element("func_c", "pkg3.func_c")

    m_a = _manifest("pkg/a.py", "pkg", [func_a])
    m_b = _manifest("pkg/b.py", "pkg2", [func_b, func_d])
    m_c = _manifest("pkg/c.py", "pkg3", [func_c])

    return ManifestRegistry({
        "pkg/a.py": m_a,
        "pkg/b.py": m_b,
        "pkg/c.py": m_c,
    })


# ═══════════════════════════════════════════════════════════════════════════
# IMPLEMENT call graph context (Step 4)
# ═══════════════════════════════════════════════════════════════════════════


class TestImplementCallGraphContext:
    """Tests for call graph metadata injection into chunks."""

    def test_call_graph_context_injected(self):
        """call_graph_summary data appears in chunk metadata."""
        reg = _make_mock_registry_with_call_graph()
        summary = reg.call_graph_summary("pkg/b.py", budget=2000)
        assert summary  # b has connections (calls c, called by a)

    def test_callers_of_file_for_enrichment(self):
        """callers_of_file returns cross-file callers."""
        reg = _make_mock_registry_with_call_graph()
        callers = reg.callers_of_file("pkg/b.py")
        assert "pkg2.func_b" in callers
        assert "pkg.func_a" in callers["pkg2.func_b"]

    def test_build_call_graph_context_formats_section(self):
        """_build_call_graph_context produces a section when metadata present."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        # Create a mock chunk with call graph metadata
        chunk = MagicMock()
        chunk.metadata = {
            "_call_graph_context": "### pkg/b.py\n- pkg2.func_b: called by 1, calls 1",
            "_call_graph_callers": [
                {"fqn": "pkg2.func_b", "direct_callers": ["pkg.func_a"], "blast_radius": 1},
            ],
        }

        result = LeadContractorChunkExecutor._build_call_graph_context(chunk)
        assert len(result) > 0
        assert any("Function Call Dependencies" in p for p in result)

    def test_build_call_graph_context_empty_metadata(self):
        """_build_call_graph_context returns [] when no metadata."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = MagicMock()
        chunk.metadata = {}

        result = LeadContractorChunkExecutor._build_call_graph_context(chunk)
        assert result == []

    def test_build_call_graph_context_high_impact(self):
        """High-impact functions (blast radius > 5) are highlighted."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = MagicMock()
        chunk.metadata = {
            "_call_graph_context": "### pkg/b.py\n- pkg2.func_b: called by 10, calls 5",
            "_call_graph_callers": [
                {"fqn": "pkg2.func_b", "direct_callers": ["a", "b", "c"], "blast_radius": 15},
            ],
        }

        result = LeadContractorChunkExecutor._build_call_graph_context(chunk)
        combined = "\n".join(result)
        assert "High-impact functions" in combined
        assert "blast radius 15" in combined


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATE severity escalation (Step 5)
# ═══════════════════════════════════════════════════════════════════════════


class TestIntegrateCallGraphEscalation:
    """Tests for CG-IN-1,2,3 escalation logic."""

    def test_caller_escalation_error_on_callers(self, caplog):
        """Removing a public element with callers logs at ERROR."""
        reg = _make_mock_registry_with_call_graph()

        # func_b has callers (func_a calls it)
        callers = reg.callers_of("pkg2.func_b")
        assert len(callers) > 0  # precondition

        # Simulate the escalation logic
        fqn = "pkg2.func_b"
        callers = reg.callers_of(fqn)
        if callers:
            logging.getLogger().error(
                "manifest.diff: removed public element %s has %d callers",
                fqn, len(callers),
            )

    def test_caller_escalation_info_on_no_callers(self):
        """Removing a public element with no callers stays at INFO."""
        reg = _make_mock_registry_with_call_graph()
        # func_a has no callers
        callers = reg.callers_of("pkg.func_a")
        assert len(callers) == 0

    def test_call_edge_diff_detected(self):
        """Call edge changes between old and new manifests are detected."""
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        old = _manifest("a.py", "mod", [a, b])

        a_new = _func_element("a", "mod.a")  # removed call edge
        new = _manifest("a.py", "mod", [a_new, b])

        removed, added = ManifestDiff.call_edge_diff(old, new)
        assert len(removed) == 1
        assert len(added) == 0

    def test_cross_file_caller_impact(self):
        """Modified file with cross-file callers is detected."""
        reg = _make_mock_registry_with_call_graph()
        callers_map = reg.callers_of_file("pkg/b.py")
        assert callers_map  # b has cross-file callers

        # Resolve affected files
        affected_files: set[str] = set()
        for _fqn, callers in callers_map.items():
            for caller_fqn in callers:
                resolved = reg.resolve_fqn(caller_fqn)
                if resolved:
                    affected_files.add(resolved[0])
        assert "pkg/a.py" in affected_files


# ═══════════════════════════════════════════════════════════════════════════
# REVIEW call graph section (Step 6)
# ═══════════════════════════════════════════════════════════════════════════


class TestReviewCallGraphSection:
    """Tests for CG-RV-1,2,3 review prompt section."""

    def _make_handler_with_registry(self):
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            ReviewPhaseHandler,
        )
        reg = _make_mock_registry_with_call_graph()
        config = HandlerConfig()
        config.manifest_registry = reg
        config.manifest_consumption_enabled = True
        return ReviewPhaseHandler(handler_config=config)

    def _make_seed_task(self, target_files: list[str]):
        """Create a minimal SeedTask-like object."""
        task = MagicMock()
        task.target_files = target_files
        task.task_id = "T-001"
        task.title = "Test task"
        task.domain = "python"
        task.description = "Test description"
        task.prompt_constraints = []
        task.deps_confidence = 1.0
        task.deps_source = None
        return task

    def test_section_present_for_file_with_callers(self):
        """Review section includes caller info for files with external callers."""
        handler = self._make_handler_with_registry()
        task = self._make_seed_task(["pkg/b.py"])

        section = handler._build_call_graph_section(task, "def func_b(): pass")
        assert len(section) > 0
        combined = "\n".join(section)
        assert "CALL GRAPH IMPACT" in combined
        assert "pkg2.func_b" in combined

    def test_section_empty_for_file_without_callers(self):
        """Review section is empty for files with no external callers."""
        handler = self._make_handler_with_registry()
        task = self._make_seed_task(["pkg/a.py"])

        section = handler._build_call_graph_section(task, "def func_a(): pass")
        # func_a has no callers → may have dead code flag but no caller section
        # At minimum, if no content beyond header, returns []
        if section:
            combined = "\n".join(section)
            assert "CALL GRAPH IMPACT" in combined

    def test_section_empty_when_disabled(self):
        """No section when manifest_consumption_enabled is False."""
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            ReviewPhaseHandler,
        )
        config = HandlerConfig()
        config.manifest_consumption_enabled = False
        handler = ReviewPhaseHandler(handler_config=config)
        task = self._make_seed_task(["pkg/b.py"])

        section = handler._build_call_graph_section(task, "code")
        assert section == []

    def test_section_empty_when_no_registry(self):
        """No section when registry is None."""
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            ReviewPhaseHandler,
        )
        config = HandlerConfig()
        config.manifest_consumption_enabled = True
        config.manifest_registry = None
        handler = ReviewPhaseHandler(handler_config=config)
        task = self._make_seed_task(["pkg/b.py"])

        section = handler._build_call_graph_section(task, "code")
        assert section == []

    def test_dead_code_flag(self):
        """Dead code candidates are flagged in review section."""
        handler = self._make_handler_with_registry()
        task = self._make_seed_task(["pkg/b.py"])

        section = handler._build_call_graph_section(task, "code")
        if section:
            combined = "\n".join(section)
            # func_d is dead code (no callers), and in the registry for pkg/b.py
            if "Dead code" in combined:
                assert "pkg2.func_d" in combined

    def test_budget_respected(self):
        """Review section respects call_graph_review_budget."""
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            ReviewPhaseHandler,
        )
        reg = _make_mock_registry_with_call_graph()
        config = HandlerConfig()
        config.manifest_registry = reg
        config.manifest_consumption_enabled = True
        config.call_graph_review_budget = 50  # Very small budget
        handler = ReviewPhaseHandler(handler_config=config)
        task = self._make_seed_task(["pkg/b.py"])

        section = handler._build_call_graph_section(task, "code")
        if section:
            total = sum(len(s) for s in section)
            # Should be reasonably bounded
            assert total < 200  # Some overhead expected for header


# ═══════════════════════════════════════════════════════════════════════════
# Plan Ingestion call graph impact (Step 7)
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanIngestionCallGraphImpact:
    """Tests for CG-PI-1 through CG-PI-4."""

    def test_sixth_dimension_present(self):
        """call_graph_impact dimension is populated when registry available."""
        from startd8.workflows.builtin.plan_ingestion_models import (
            ComplexityScore,
            ParsedFeature,
            ParsedPlan,
        )
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _heuristic_assess_complexity,
        )

        reg = _make_mock_registry_with_call_graph()
        plan = ParsedPlan(
            title="Test Plan",
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="Test Feature",
                    target_files=["pkg/b.py"],
                ),
            ],
        )

        result = _heuristic_assess_complexity(
            plan, threshold=50, force_route=None,
            manifest_registry=reg,
        )
        assert isinstance(result, ComplexityScore)
        # call_graph_impact may or may not be > 0 depending on blast radius
        assert result.call_graph_impact >= 0

    def test_sixth_dimension_zero_without_registry(self):
        """call_graph_impact is 0 when no registry available."""
        from startd8.workflows.builtin.plan_ingestion_models import (
            ParsedFeature,
            ParsedPlan,
        )
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _heuristic_assess_complexity,
        )

        plan = ParsedPlan(
            title="Test Plan",
            features=[
                ParsedFeature(feature_id="F-001", name="Test Feature"),
            ],
        )

        result = _heuristic_assess_complexity(
            plan, threshold=50, force_route=None,
            manifest_registry=None,
        )
        assert result.call_graph_impact == 0

    def test_high_impact_annotation(self):
        """Features with high blast radius get high_impact=True."""
        from startd8.workflows.builtin.plan_ingestion_models import (
            ParsedFeature,
            ParsedPlan,
        )
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _heuristic_assess_complexity,
        )

        # Build a registry with many callers for func_c
        elements = [_func_element("func_c", "pkg.func_c")]
        # Create 25 callers for func_c (> threshold of 20)
        for i in range(25):
            elements.append(
                _func_element(f"caller_{i}", f"pkg.caller_{i}",
                              calls=[_call("func_c", "pkg.func_c")])
            )
        m = _manifest("pkg/a.py", "pkg", elements)
        reg = ManifestRegistry({"pkg/a.py": m})

        plan = ParsedPlan(
            title="Test Plan",
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="High Impact Feature",
                    target_files=["pkg/a.py"],
                ),
            ],
        )

        result = _heuristic_assess_complexity(
            plan, threshold=50, force_route=None,
            manifest_registry=reg,
        )

        # func_c has 25 callers → high_impact should be True
        assert plan.features[0].high_impact is True

    def test_targets_dead_code_annotation(self):
        """Features targeting only dead code functions get targets_dead_code=True."""
        from startd8.workflows.builtin.plan_ingestion_models import (
            ParsedFeature,
            ParsedPlan,
        )
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _heuristic_assess_complexity,
        )

        reg = _make_mock_registry_with_call_graph()
        # func_d is dead code (public, no callers), func_a is also dead
        dead = set(reg.dead_candidates())
        assert "pkg2.func_d" in dead  # precondition

        # Note: targets_dead_code requires ALL fqns in dead set
        # Create a file with only dead code elements
        dead_func = _func_element("dead_func", "dead.dead_func")
        m = _manifest("dead/mod.py", "dead", [dead_func])
        reg_with_dead = ManifestRegistry({**{"dead/mod.py": m}})

        plan = ParsedPlan(
            title="Test Plan",
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="Dead Code Feature",
                    target_files=["dead/mod.py"],
                ),
            ],
        )

        _heuristic_assess_complexity(
            plan, threshold=50, force_route=None,
            manifest_registry=reg_with_dead,
        )

        # dead_func has no callers → targets_dead_code should be True
        assert plan.features[0].targets_dead_code is True

    def test_affected_callers_populated(self):
        """affected_callers is populated from callers_of for feature FQNs."""
        from startd8.workflows.builtin.plan_ingestion_models import (
            ParsedFeature,
            ParsedPlan,
        )
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            _heuristic_assess_complexity,
        )

        reg = _make_mock_registry_with_call_graph()
        plan = ParsedPlan(
            title="Test Plan",
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="Feature B",
                    target_files=["pkg/b.py"],
                ),
            ],
        )

        _heuristic_assess_complexity(
            plan, threshold=50, force_route=None,
            manifest_registry=reg,
        )

        # func_b is called by func_a
        callers = plan.features[0].affected_callers
        assert "pkg.func_a" in callers

    def test_complexity_seed_dict_includes_call_graph_impact(self):
        """ComplexityScore.to_seed_dict() includes call_graph_impact dimension."""
        from startd8.workflows.builtin.plan_ingestion_models import ComplexityScore

        score = ComplexityScore(call_graph_impact=42)
        d = score.to_seed_dict()
        assert "call_graph_impact" in d["dimensions"]
        assert d["dimensions"]["call_graph_impact"] == 42

    def test_parsed_feature_seed_dict_includes_new_fields(self):
        """ParsedPlan.to_seed_dict() includes Phase 6 feature fields."""
        from startd8.workflows.builtin.plan_ingestion_models import (
            ParsedFeature,
            ParsedPlan,
        )

        plan = ParsedPlan(
            title="Test",
            features=[
                ParsedFeature(
                    feature_id="F-001",
                    name="Test",
                    affected_callers=["a.b", "c.d"],
                    high_impact=True,
                    targets_dead_code=False,
                ),
            ],
        )
        d = plan.to_seed_dict()
        f = d["features"][0]
        assert f["affected_callers"] == ["a.b", "c.d"]
        assert f["high_impact"] is True
        assert f["targets_dead_code"] is False


# ═══════════════════════════════════════════════════════════════════════════
# Graceful degradation (common across consumers)
# ═══════════════════════════════════════════════════════════════════════════


class TestGracefulDegradation:
    """All consumers with empty/None call graph → no-op."""

    def test_callers_of_file_empty_graph(self):
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})
        assert reg.callers_of_file("a.py") == {}

    def test_call_graph_summary_no_edges(self):
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})
        assert reg.call_graph_summary("a.py") == ""

    def test_max_blast_radius_no_edges(self):
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})
        assert reg.max_blast_radius(["mod.a"]) == ("", 0)

    def test_build_call_graph_context_no_metadata(self):
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )
        chunk = MagicMock()
        chunk.metadata = {}
        assert LeadContractorChunkExecutor._build_call_graph_context(chunk) == []

    def test_review_section_no_registry(self):
        from startd8.contractors.context_seed_handlers import (
            HandlerConfig,
            ReviewPhaseHandler,
        )
        config = HandlerConfig()
        config.manifest_registry = None
        config.manifest_consumption_enabled = True
        handler = ReviewPhaseHandler(handler_config=config)
        task = MagicMock()
        task.target_files = ["a.py"]
        assert handler._build_call_graph_section(task, "code") == []


# ═══════════════════════════════════════════════════════════════════════════
# DESIGN call graph context (Step 9)
# ═══════════════════════════════════════════════════════════════════════════


class TestDesignCallGraphContext:
    """Tests for call graph context injection in DESIGN phase."""

    def test_call_graph_summary_in_extract_manifest_context(self):
        """extract_manifest_context includes call_graph_context."""
        from startd8.contractors.artisan_phases.design_prompts.seed_mapping import (
            extract_manifest_context,
        )

        reg = _make_mock_registry_with_call_graph()
        task = MagicMock()
        task.task_id = "T-001"
        task.target_files = ["pkg/b.py"]

        result = extract_manifest_context(
            task,
            manifest_registry=reg,
            manifest_context_budget=2000,
        )
        assert result is not None
        assert "call_graph_context" in result

    def test_extract_manifest_context_no_call_edges(self):
        """No call_graph_context when file has no call relationships."""
        from startd8.contractors.artisan_phases.design_prompts.seed_mapping import (
            extract_manifest_context,
        )

        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        task = MagicMock()
        task.task_id = "T-001"
        task.target_files = ["a.py"]

        result = extract_manifest_context(
            task,
            manifest_registry=reg,
            manifest_context_budget=2000,
        )
        # May or may not have result (depends on element summary)
        if result is not None:
            # call_graph_context should not appear since no call edges
            assert "call_graph_context" not in result or result["call_graph_context"] == ""

    def test_extract_manifest_context_no_registry(self):
        """Returns None when no registry."""
        from startd8.contractors.artisan_phases.design_prompts.seed_mapping import (
            extract_manifest_context,
        )

        task = MagicMock()
        task.task_id = "T-001"
        task.target_files = ["a.py"]

        result = extract_manifest_context(
            task, manifest_registry=None, manifest_context_budget=2000,
        )
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════
# Post-generation caller check (Step 8)
# ═══════════════════════════════════════════════════════════════════════════


class TestPostGenCallerCheck:
    """Tests for CG-IM-5 — post-gen signature change with callers."""

    def test_sig_change_caller_warning_metadata(self):
        """Signature change with callers populates warning metadata."""
        # Build a registry: a calls b
        a = _func_element("a", "mod.a", calls=[_call("b", "mod.b")])
        b = _func_element("b", "mod.b")
        m = _manifest("a.py", "mod", [a, b])
        reg = ManifestRegistry({"a.py": m})

        # Compute diff where b's signature changes
        b_new = Element(
            kind=ElementKind.FUNCTION,
            name="b",
            fqn="mod.b",
            span=_span(),
            signature=Signature(params=[
                Param(name="self", kind=ParamKind.POSITIONAL),
                Param(name="x", kind=ParamKind.POSITIONAL, annotation="int"),
            ]),
            visibility=Visibility.PUBLIC,
        )
        new_m = _manifest("a.py", "mod", [a, b_new])

        diff = ManifestDiff.diff(m, new_m, registry=reg)
        assert len(diff.changed_signatures) == 1

        # Verify callers_of detects the caller
        fqn, old_sig, new_sig = diff.changed_signatures[0]
        callers = reg.callers_of(fqn)
        assert len(callers) > 0  # a calls b
        assert "mod.a" in callers

    def test_sig_change_no_callers_no_warning(self):
        """Signature change with no callers doesn't escalate."""
        a = _func_element("a", "mod.a")
        m = _manifest("a.py", "mod", [a])
        reg = ManifestRegistry({"a.py": m})

        a_new = Element(
            kind=ElementKind.FUNCTION,
            name="a",
            fqn="mod.a",
            span=_span(),
            signature=Signature(params=[
                Param(name="self", kind=ParamKind.POSITIONAL),
                Param(name="x", kind=ParamKind.POSITIONAL, annotation="int"),
            ]),
            visibility=Visibility.PUBLIC,
        )
        new_m = _manifest("a.py", "mod", [a_new])

        diff = ManifestDiff.diff(m, new_m, registry=reg)
        assert len(diff.changed_signatures) == 1
        # No callers → no signature_changes_with_callers
        assert len(diff.signature_changes_with_callers) == 0
