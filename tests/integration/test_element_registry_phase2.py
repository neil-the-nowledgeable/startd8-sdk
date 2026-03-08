"""Phase 2 integration tests for Element Registry artisan phase wiring.

Tests Steps 2.1-2.9: plan_deconstruction metadata, SCAFFOLD pre-fill,
DESIGN element contracts, INTEGRATE provenance, TEST coverage tracking,
FINALIZE manifest, handoff serialization, gate emission, contract propagation.
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest import mock

import pytest

from startd8.element_registry import ElementEntry, ElementRegistry, PhaseRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_state(tmp_path: Path) -> Path:
    """Create a temp state dir for the element registry."""
    state = tmp_path / "state"
    state.mkdir()
    return state


@pytest.fixture()
def registry(tmp_state: Path) -> ElementRegistry:
    """Create a pre-populated element registry."""
    reg = ElementRegistry(state_dir=tmp_state)
    reg.put(ElementEntry(
        element_id="function/mymod-abc123",
        kind="function",
        name="my_func",
        file_path="src/pkg/mymod.py",
        phases={},
        extra={"code": "return 42"},
    ))
    reg.put(ElementEntry(
        element_id="class/mymod-def456",
        kind="class",
        name="MyClass",
        file_path="src/pkg/mymod.py",
        phases={},
        extra={},
    ))
    reg.put(ElementEntry(
        element_id="function/other-ghi789",
        kind="function",
        name="helper",
        file_path="src/pkg/other.py",
        phases={},
        extra={"code": "pass"},
    ))
    return reg


# ---------------------------------------------------------------------------
# Step 2.1: PLAN phase — element inventory in task metadata
# ---------------------------------------------------------------------------


class TestPlanElementInventory:
    """Step 2.1: plan_deconstruction adds element metadata to tasks."""

    def test_elements_available_count(self, registry: ElementRegistry) -> None:
        """Registry reports correct element counts per file."""
        entries = registry.elements_for_file("src/pkg/mymod.py")
        assert len(entries) == 2
        with_code = [e for e in entries if e.extra.get("code")]
        assert len(with_code) == 1  # only my_func has code


# ---------------------------------------------------------------------------
# Step 2.2: SCAFFOLD phase — registry pre-fill in file_assembler
# ---------------------------------------------------------------------------


class TestScaffoldRegistryPreFill:
    """Step 2.2: DeterministicFileAssembler uses registry code."""

    def _make_func_elem(self, name: str, source_contract_id: str = "") -> Any:
        """Create a ForwardElementSpec for a function with a minimal signature."""
        from startd8.forward_manifest import ForwardElementSpec
        from startd8.utils.code_manifest import Signature

        kwargs: dict[str, Any] = {
            "kind": "function",
            "name": name,
            "signature": Signature(params=[]),
        }
        if source_contract_id:
            kwargs["source_contract_id"] = source_contract_id
        return ForwardElementSpec(**kwargs)

    def test_render_element_with_registry_code(self, registry: ElementRegistry) -> None:
        """When registry has code, stub should contain it instead of NotImplementedError."""
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler(element_registry=registry)
        elem = self._make_func_elem("my_func", "function/mymod-abc123")
        rendered = assembler._render_element(elem, indent="")
        assert "return 42" in rendered
        assert "NotImplementedError" not in rendered

    def test_render_element_without_registry_falls_back(self) -> None:
        """Without registry, render still produces NotImplementedError stubs."""
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler()
        elem = self._make_func_elem("no_code_func")
        rendered = assembler._render_element(elem, indent="")
        assert "NotImplementedError" in rendered

    def test_render_element_registry_miss_falls_back(self, registry: ElementRegistry) -> None:
        """When element_id not in registry, fall back to stub."""
        from startd8.utils.file_assembler import DeterministicFileAssembler

        assembler = DeterministicFileAssembler(element_registry=registry)
        elem = self._make_func_elem("unknown_func", "function/unknown-zzz000")
        rendered = assembler._render_element(elem, indent="")
        assert "NotImplementedError" in rendered


# ---------------------------------------------------------------------------
# Step 2.3: DESIGN phase — element contracts
# ---------------------------------------------------------------------------


class TestDesignElementContracts:
    """Step 2.3: design_support records element contracts."""

    def test_record_design_element_contracts(self, registry: ElementRegistry) -> None:
        from startd8.contractors.context_seed.design_support import (
            _record_design_element_contracts,
        )

        task = mock.MagicMock()
        task.task_id = "T-001"
        task.target_files = ["src/pkg/mymod.py"]
        design_doc = """
### Files Touched
- `src/pkg/mymod.py` (modify)
  - Add `my_func` with new logic
"""
        count = _record_design_element_contracts(task, design_doc, registry)
        assert count >= 1

        entry = registry.get("function/mymod-abc123")
        assert "design" in entry.phases
        records = entry.phases["design"]
        assert any("contracted" in r.status for r in records)


# ---------------------------------------------------------------------------
# Step 2.4: INTEGRATE phase — element provenance
# ---------------------------------------------------------------------------


class TestIntegrateElementProvenance:
    """Step 2.4: IntegrationEngine records merge outcomes."""

    def test_element_registry_parameter_accepted(self, registry: ElementRegistry) -> None:
        """IntegrationEngine accepts element_registry kwarg."""
        from startd8.contractors.integration_engine import IntegrationEngine

        engine = IntegrationEngine(
            project_root=Path("/tmp/fake"),
            merge_strategy=mock.MagicMock(),
            element_registry=registry,
        )
        assert engine._element_registry is registry

    def test_record_element_merge_outcomes(self, registry: ElementRegistry) -> None:
        """_record_element_merge_outcomes marks elements as merged."""
        from startd8.contractors.integration_engine import IntegrationEngine

        engine = IntegrationEngine(
            project_root=Path("/tmp/fake"),
            merge_strategy=mock.MagicMock(),
            element_registry=registry,
        )

        unit = mock.MagicMock()
        unit.id = "unit-001"
        unit.target_files = ["src/pkg/mymod.py"]

        engine._record_element_merge_outcomes(
            unit,
            integrated_files=[Path("src/pkg/mymod.py")],
            skipped_files=[],
        )

        entry = registry.get("function/mymod-abc123")
        assert "integrate" in entry.phases
        records = entry.phases["integrate"]
        assert any(r.status == "merged" for r in records)


# ---------------------------------------------------------------------------
# Step 2.5: TEST phase — element test coverage
# ---------------------------------------------------------------------------


class TestTestElementCoverage:
    """Step 2.5: TestConstructionPhase records test coverage."""

    def test_element_registry_parameter_accepted(self, registry: ElementRegistry) -> None:
        """TestConstructionPhase accepts element_registry kwarg."""
        from startd8.contractors.artisan_phases.test_construction import (
            TestConstructionPhase,
        )

        phase = TestConstructionPhase(
            design_doc={"feature_name": "test"},
            element_registry=registry,
        )
        assert phase._element_registry is registry


# ---------------------------------------------------------------------------
# Step 2.6: FINALIZE phase — element manifest
# ---------------------------------------------------------------------------


class TestFinalizeElementManifest:
    """Step 2.6: FinalAssemblyPhase generates element manifest."""

    def test_element_registry_parameter_accepted(self, registry: ElementRegistry) -> None:
        from startd8.contractors.artisan_phases.final_assembly import (
            FinalAssemblyPhase,
        )

        phase = FinalAssemblyPhase(element_registry=registry)
        assert phase._element_registry is registry

    def test_element_manifest_in_report(self, registry: ElementRegistry) -> None:
        """Run with registry produces element_manifest in report."""
        from startd8.contractors.artisan_phases.final_assembly import (
            FinalAssemblyPhase,
        )

        phase = FinalAssemblyPhase(element_registry=registry)
        report = phase.run({
            "design_specs": [],
            "work_items": [],
        })
        manifest = report.element_manifest
        assert manifest["total_elements"] == 3
        assert manifest["elements_with_code"] == 2  # my_func + helper

    def test_report_without_registry(self) -> None:
        """Run without registry produces empty element_manifest."""
        from startd8.contractors.artisan_phases.final_assembly import (
            FinalAssemblyPhase,
        )

        phase = FinalAssemblyPhase()
        report = phase.run({
            "design_specs": [],
            "work_items": [],
        })
        assert report.element_manifest == {}


# ---------------------------------------------------------------------------
# Step 2.7: Handoff — element_state serialization
# ---------------------------------------------------------------------------


class TestHandoffElementState:
    """Step 2.7: HandoffData includes element_state."""

    def test_handoff_data_has_element_state(self) -> None:
        from startd8.contractors.handoff import HandoffData

        hd = HandoffData(
            enriched_seed_path="/tmp/seed.json",
            project_root="/tmp/project",
            output_dir="/tmp/output",
            workflow_id="wf-001",
            element_state={"test": "value"},
        )
        assert hd.element_state == {"test": "value"}


# ---------------------------------------------------------------------------
# Step 2.8: Gate emission
# ---------------------------------------------------------------------------


class TestGateEmission:
    """Step 2.8: GateEmitter.emit_element_gate works."""

    def test_emit_element_gate(self) -> None:
        from startd8.contractors.gate_contracts import GateEmitter

        with mock.patch.object(GateEmitter, "emit") as mock_emit:
            GateEmitter.emit_element_gate(
                gate_id="test_gate",
                element_id="function/mymod-abc123",
                phase="design",
                outcome="PASS",
            )
            assert mock_emit.called
            result = mock_emit.call_args[0][0]
            assert result["gate_id"] == "artisan.element.test_gate"
            assert result["element_id"] == "function/mymod-abc123"
            assert result["result"] == "pass"


# ---------------------------------------------------------------------------
# Step 2.9: Context schema fields
# ---------------------------------------------------------------------------


class TestContextSchemaFields:
    """Step 2.9: Pydantic output models have element registry fields."""

    def test_design_phase_output_element_state(self) -> None:
        from startd8.contractors.context_schema import DesignPhaseOutput

        out = DesignPhaseOutput(
            design_results={"task1": {"status": "success"}},
            element_state={"foo": "bar"},
        )
        assert out.element_state == {"foo": "bar"}

    def test_integrate_phase_output_element_merge_outcomes(self) -> None:
        from startd8.contractors.context_schema import IntegratePhaseOutput

        out = IntegratePhaseOutput(
            integration_results={"task1": {
                "success": True,
                "integrated_files": [],
                "errors": [],
            }},
            element_merge_outcomes={"merged": 3},
        )
        assert out.element_merge_outcomes == {"merged": 3}

    def test_finalize_phase_output_element_manifest(self) -> None:
        from startd8.contractors.context_schema import FinalizePhaseOutput

        out = FinalizePhaseOutput(
            workflow_summary={
                "plan_title": "test",
                "task_count": 1,
                "status": "done",
                "cost_summary": {},
            },
            element_manifest={"total": 5},
        )
        assert out.element_manifest == {"total": 5}


# ---------------------------------------------------------------------------
# Step 2.10: all_entries method
# ---------------------------------------------------------------------------


class TestAllEntries:
    """ElementRegistry.all_entries() returns all entries."""

    def test_all_entries_returns_all(self, registry: ElementRegistry) -> None:
        entries = registry.all_entries()
        assert len(entries) == 3
        ids = {e.element_id for e in entries}
        assert "function/mymod-abc123" in ids
        assert "class/mymod-def456" in ids
        assert "function/other-ghi789" in ids
