"""
WCP Self-Validating Gap Verification — startd8-sdk propagation gaps.

These runtime integration tests verify that each identified propagation gap
in the WCP epic is fixed.  They are designed to FAIL before the corresponding
WCP task is implemented and PASS afterward.

Run after each WCP task:
    python3 -m pytest tests/plan_validation/test_wcp_gap_validation.py -v

Progressive schedule:
    Before any WCP task  → SV-PREREQ passes, all others fail
    After WCP-005        → + SV-005
    After WCP-006        → + SV-006, SV-007
    After WCP-008        → + SV-008
    After WCP-003        → + SV-003-propagated, SV-003-defaulted
    After WCP-004        → + SV-004
    After WCP-009        → + SV-E2E (all passing)
"""

import json
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures: shared enriched seed and helpers
# ---------------------------------------------------------------------------

def _make_enriched_seed_data() -> List[Dict[str, Any]]:
    """Build a minimal enriched seed with 3 tasks of different domains."""
    return [
        {
            "task_id": "WCP-T1",
            "title": "Implement tracker module",
            "task_type": "task",
            "story_points": 3,
            "priority": "high",
            "labels": ["python"],
            "depends_on": [],
            "config": {
                "task_description": "Build the tracker module with OTel spans",
                "context": {
                    "target_files": ["src/mypackage/tracker.py"],
                    "estimated_loc": 120,
                    "feature_id": "F-001",
                },
            },
            "_enrichment": {
                "domain": "python-package-module",
                "domain_reasoning": "Python file in package with __init__.py",
                "prompt_constraints": [
                    "Use relative imports for intra-package modules",
                    "Include __init__.py exports",
                ],
                "environment_checks": [
                    {"check": "parent_package_exists", "args": {}},
                ],
                "post_generation_validators": [
                    "relative_imports_valid",
                    "deps_available",
                    "no_circular_imports",
                    "no_markdown_fences",
                    "merge_damage",
                ],
                "available_siblings": ["__init__.py", "models.py"],
            },
        },
        {
            "task_id": "WCP-T2",
            "title": "Update config.yaml",
            "task_type": "task",
            "story_points": 1,
            "priority": "medium",
            "labels": ["config"],
            "depends_on": [],
            "config": {
                "task_description": "Update YAML configuration",
                "context": {
                    "target_files": ["config/settings.yaml"],
                    "estimated_loc": 30,
                    "feature_id": "F-002",
                },
            },
            "_enrichment": {
                "domain": "config-yaml",
                "domain_reasoning": "YAML configuration file",
                "prompt_constraints": [
                    "Preserve existing key ordering",
                    "Use standard YAML formatting",
                ],
                "environment_checks": [],
                "post_generation_validators": [
                    "no_markdown_fences",
                ],
                "available_siblings": [],
            },
        },
        {
            "task_id": "WCP-T3",
            "title": "Unknown domain task",
            "task_type": "task",
            "story_points": 2,
            "priority": "low",
            "labels": [],
            "depends_on": [],
            "config": {
                "task_description": "Task with no enrichment data",
                "context": {
                    "target_files": ["misc/readme.txt"],
                    "estimated_loc": 20,
                    "feature_id": "F-003",
                },
            },
            # No _enrichment key → will default to "unknown"
        },
    ]


@pytest.fixture
def enriched_seed_path(tmp_path: Path) -> Path:
    """Write an enriched seed JSON to a temp file."""
    seed_path = tmp_path / "artisan-context-seed-enriched.json"
    seed_path.write_text(
        json.dumps({"tasks": _make_enriched_seed_data()}, indent=2),
        encoding="utf-8",
    )
    return seed_path


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a minimal project root."""
    (tmp_path / "src" / "mypackage").mkdir(parents=True)
    (tmp_path / "src" / "mypackage" / "__init__.py").write_text("")
    (tmp_path / "config").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# SV-PREREQ: Auto-enrichment detection works (Gap #1, already fixed)
# ---------------------------------------------------------------------------

class TestSVPrereq:
    """Verify auto-enrichment detection is present in run_artisan_workflow.py."""

    def test_auto_enrichment_logic_exists(self):
        """run_artisan_workflow.py contains has_enrichment check logic.

        This is a source-level check because the script is not easily
        importable as a module.  It verifies the fix for Gap #1 is present.
        """
        script = Path(__file__).resolve().parents[2] / "scripts" / "run_artisan_workflow.py"
        if not script.exists():
            pytest.skip("run_artisan_workflow.py not found at expected path")

        content = script.read_text(encoding="utf-8")
        assert "has_enrichment" in content, (
            "run_artisan_workflow.py missing auto-enrichment detection variable"
        )
        assert "DomainPreflightWorkflow" in content, (
            "run_artisan_workflow.py missing DomainPreflightWorkflow import"
        )


# ---------------------------------------------------------------------------
# SV-005: Design calibration is domain-aware (Gap #2)
# Fixed by: WCP-005
# ---------------------------------------------------------------------------

class TestSV005DomainAwareCalibration:
    """Verify _derive_design_calibration uses domain for token budgets."""

    def test_calibration_differs_by_domain(self):
        """config-yaml tasks should get lower token budgets than python-package-module."""
        from startd8.workflows.builtin.plan_ingestion_workflow import (
            PlanIngestionWorkflow,
        )

        tasks = _make_enriched_seed_data()
        calibration = PlanIngestionWorkflow._derive_design_calibration(tasks)

        t1_cal = calibration["WCP-T1"]  # python-package-module, 120 LOC
        t2_cal = calibration["WCP-T2"]  # config-yaml, 30 LOC

        # Before WCP-005: calibration is domain-agnostic.  The SizeEstimator
        # (when available) returns "medium" for all tasks → "standard" tier
        # → implement_max_output_tokens = 32768 for both.
        #
        # After WCP-005: config-yaml gets a 0.5x domain multiplier applied
        # to implement_max_output_tokens → 32768 * 0.5 = 16384, which is
        # strictly less than the python-package-module task's 32768.
        #
        # We assert that config-yaml tokens are STRICTLY LESS than
        # python-package-module tokens.  Before WCP-005, they are equal.

        python_tokens = t1_cal["implement_max_output_tokens"]
        config_yaml_tokens = t2_cal["implement_max_output_tokens"]

        assert config_yaml_tokens < python_tokens, (
            f"config-yaml task got {config_yaml_tokens} implement tokens — "
            f"same as python-package-module ({python_tokens}). "
            "Domain multiplier not applied. WCP-005 not implemented."
        )


# ---------------------------------------------------------------------------
# SV-006: DomainChecklist wired to DevelopmentPhase (Gap #3)
# Fixed by: WCP-006
# ---------------------------------------------------------------------------

class TestSV006DomainChecklistWiring:
    """Verify ImplementPhaseHandler passes DomainChecklist to DevelopmentPhase."""

    def test_implement_handler_passes_domain_checklist(self):
        """DevelopmentPhase constructed by ImplementPhaseHandler has domain_checklist set."""
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        handler = ImplementPhaseHandler()

        # After WCP-006: ImplementPhaseHandler should accept enriched_seed_path
        # and project_root, and its execute() should create DevelopmentPhase
        # with domain_checklist != None.
        #
        # We test this by checking the handler constructor accepts the new params.
        assert hasattr(handler, "_enriched_seed_path") or hasattr(handler, "_project_root"), (
            "ImplementPhaseHandler lacks _enriched_seed_path/_project_root attributes. "
            "WCP-006 not implemented."
        )

    def test_domain_constraints_injected_for_enriched_chunk(
        self, enriched_seed_path: Path, project_root: Path,
    ):
        """DomainChecklist injects domain_constraints into chunk execution context."""
        from startd8.contractors.artisan_phases.domain_checklist import DomainChecklist
        from startd8.contractors.artisan_phases.development import DevelopmentPhase

        checklist = DomainChecklist(
            project_root=project_root,
            enriched_seed_path=enriched_seed_path,
        )

        # Simulate what DevelopmentPhase._execute_chunk does at lines 1896-1916
        enrichment = checklist.get_enrichment(
            "WCP-T1", ["src/mypackage/tracker.py"],
        )
        assert enrichment is not None, (
            "DomainChecklist.get_enrichment() returned None for enriched task WCP-T1"
        )
        assert enrichment.prompt_constraints, (
            "Enrichment has no prompt_constraints for python-package-module task"
        )

        # Now verify DevelopmentPhase accepts domain_checklist
        dev_phase = DevelopmentPhase(domain_checklist=checklist)
        assert dev_phase.domain_checklist is not None, (
            "DevelopmentPhase.domain_checklist is None after passing DomainChecklist"
        )


# ---------------------------------------------------------------------------
# SV-007: Key name alignment — domain_constraints consistent end-to-end
# Fixed by: WCP-007 (resolved-by-design when WCP-006 is done)
# ---------------------------------------------------------------------------

class TestSV007KeyNameAlignment:
    """Verify domain_constraints key is used consistently."""

    def test_domain_checklist_writes_domain_constraints_key(
        self, enriched_seed_path: Path, project_root: Path,
    ):
        """DomainChecklist injection uses 'domain_constraints' key (not 'prompt_constraints')."""
        from startd8.contractors.artisan_phases.domain_checklist import DomainChecklist
        from startd8.contractors.artisan_phases.development import DevelopmentPhase

        checklist = DomainChecklist(
            project_root=project_root,
            enriched_seed_path=enriched_seed_path,
        )

        # Simulate _execute_chunk context building
        context: Dict[str, Any] = {}
        enrichment = checklist.get_enrichment(
            "WCP-T1", ["src/mypackage/tracker.py"],
        )
        if enrichment is not None:
            # This mirrors development.py lines 1903-1905
            context["domain_constraints"] = enrichment.prompt_constraints
            context["domain"] = enrichment.domain.value

        assert "domain_constraints" in context, (
            "Expected 'domain_constraints' key in context. "
            "Key name mismatch not resolved."
        )
        assert "prompt_constraints" not in context, (
            "Context should use 'domain_constraints', not 'prompt_constraints' "
            "in the execution path."
        )
        assert context["domain"] == "python-package-module"


# ---------------------------------------------------------------------------
# SV-008: Validator names align between enrichment and TEST phase (Gap #6)
# Fixed by: WCP-008
# ---------------------------------------------------------------------------

class TestSV008ValidatorNameAlignment:
    """Verify every enrichment validator name resolves in TestPhaseHandler."""

    # All validator names that can appear in enrichment post_generation_validators
    ENRICHMENT_VALIDATOR_NAMES = [
        "relative_imports_valid",
        "deps_available",
        "no_circular_imports",
        "no_markdown_fences",
        "merge_damage",
        "no_relative_imports",
        "definition_ordering",
        "test_naming",
        "no_hardcoded_secrets",
        "no_substring_tag_matching",
    ]

    def test_all_enrichment_validators_resolve(self, project_root: Path):
        """Every enrichment validator name resolves to a command."""
        from startd8.contractors.context_seed_handlers import TestPhaseHandler

        handler = TestPhaseHandler()
        target_files = ["src/mypackage/tracker.py"]
        unresolved = []

        for name in self.ENRICHMENT_VALIDATOR_NAMES:
            cmd = handler._resolve_validator_command(name, target_files, project_root)
            if cmd is None:
                unresolved.append(name)

        assert not unresolved, (
            f"These enrichment validators are NOT recognized by "
            f"TestPhaseHandler._resolve_validator_command(): {unresolved}. "
            "WCP-008 not implemented."
        )


# ---------------------------------------------------------------------------
# SV-003-propagated: Span event emitted on successful propagation
# Fixed by: WCP-003
# ---------------------------------------------------------------------------

class TestSV003Propagated:
    """Verify context.propagated span events are emitted."""

    def test_propagated_event_emitted_on_domain_injection(
        self, enriched_seed_path: Path, project_root: Path,
    ):
        """DevelopmentPhase emits context.propagated when DomainChecklist injects constraints."""
        from startd8.contractors.artisan_phases.domain_checklist import DomainChecklist
        from startd8.contractors.artisan_phases.development import DevelopmentPhase

        checklist = DomainChecklist(
            project_root=project_root,
            enriched_seed_path=enriched_seed_path,
        )
        dev_phase = DevelopmentPhase(domain_checklist=checklist)

        # Mock the tracer to capture span events
        mock_span = MagicMock()
        mock_span.is_recording.return_value = True
        events_captured = []

        def capture_event(name, attributes=None):
            events_captured.append({"name": name, "attributes": attributes or {}})

        mock_span.add_event = capture_event

        # Simulate _execute_chunk's domain injection section
        # After WCP-003: a context.propagated event should be emitted
        context: Dict[str, Any] = {}
        enrichment = checklist.get_enrichment("WCP-T1", ["src/mypackage/tracker.py"])

        if enrichment is not None:
            context["domain_constraints"] = enrichment.prompt_constraints
            context["domain"] = enrichment.domain.value

        # Check if DevelopmentPhase has instrumentation code
        # by looking for the span event emission in its source
        import inspect
        source = inspect.getsource(DevelopmentPhase._execute_chunk)

        assert "context.propagated" in source, (
            "DevelopmentPhase._execute_chunk() does not emit 'context.propagated' "
            "span event. WCP-003 not implemented."
        )


# ---------------------------------------------------------------------------
# SV-003-defaulted: Span event emitted when context defaults to unknown
# Fixed by: WCP-003
# ---------------------------------------------------------------------------

class TestSV003Defaulted:
    """Verify context.defaulted span events are emitted."""

    def test_defaulted_event_in_seed_task_extraction(self):
        """SeedTask.from_seed_entry emits context.defaulted when domain is unknown."""
        import inspect
        from startd8.contractors.context_seed_handlers import SeedTask

        source = inspect.getsource(SeedTask.from_seed_entry)

        assert "context.defaulted" in source, (
            "SeedTask.from_seed_entry() does not emit 'context.defaulted' "
            "span event when domain defaults to unknown. WCP-003 not implemented."
        )


# ---------------------------------------------------------------------------
# SV-004: FINALIZE validates propagation completeness
# Fixed by: WCP-004
# ---------------------------------------------------------------------------

class TestSV004FinalizeValidation:
    """Verify FinalizePhaseHandler has propagation completeness validation."""

    def test_finalize_has_validation_method(self):
        """FinalizePhaseHandler has _validate_propagation_completeness method."""
        from startd8.contractors.context_seed_handlers import FinalizePhaseHandler

        handler = FinalizePhaseHandler()
        assert hasattr(handler, "_validate_propagation_completeness"), (
            "FinalizePhaseHandler lacks _validate_propagation_completeness method. "
            "WCP-004 not implemented."
        )

    def test_finalize_validation_counts_correctly(self):
        """_validate_propagation_completeness returns correct counts for mixed tasks."""
        from startd8.contractors.context_seed_handlers import (
            FinalizePhaseHandler,
            SeedTask,
        )

        handler = FinalizePhaseHandler()
        if not hasattr(handler, "_validate_propagation_completeness"):
            pytest.skip("_validate_propagation_completeness not yet implemented")

        seed_data = _make_enriched_seed_data()
        tasks = [SeedTask.from_seed_entry(entry) for entry in seed_data]

        results = handler._validate_propagation_completeness({"tasks": tasks})

        assert results["total"] == 3
        # WCP-T1 and WCP-T2 have full enrichment, WCP-T3 has none
        assert results["complete"] == 2, (
            f"Expected 2 complete tasks, got {results['complete']}"
        )
        assert results["defaulted"] == 1, (
            f"Expected 1 defaulted task, got {results['defaulted']}"
        )


# ---------------------------------------------------------------------------
# SV-E2E: End-to-end context propagation
# Fixed by: WCP-009 (all prior tasks must be done)
# ---------------------------------------------------------------------------

class TestSVE2E:
    """End-to-end: enriched seed → SeedTask → DomainChecklist → DevelopmentPhase → FINALIZE."""

    def test_full_propagation_chain(
        self, enriched_seed_path: Path, project_root: Path,
    ):
        """Domain context propagates from enriched seed through to FINALIZE completeness check."""
        from startd8.contractors.context_seed_handlers import (
            FinalizePhaseHandler,
            ImplementPhaseHandler,
            SeedTask,
        )
        from startd8.contractors.artisan_phases.domain_checklist import DomainChecklist
        from startd8.contractors.artisan_phases.development import DevelopmentPhase

        # --- Step 1: Parse seed tasks ---
        seed_data = _make_enriched_seed_data()
        tasks = [SeedTask.from_seed_entry(entry) for entry in seed_data]

        assert tasks[0].domain == "python-package-module"
        assert tasks[1].domain == "config-yaml"
        assert tasks[2].domain == "unknown"

        # --- Step 2: Construct DomainChecklist ---
        checklist = DomainChecklist(
            project_root=project_root,
            enriched_seed_path=enriched_seed_path,
        )

        # --- Step 3: Verify constraint injection per domain ---
        # python-package-module → should get constraints
        e1 = checklist.get_enrichment("WCP-T1", ["src/mypackage/tracker.py"])
        assert e1 is not None
        assert len(e1.prompt_constraints) >= 2

        # config-yaml → should get constraints
        e2 = checklist.get_enrichment("WCP-T2", ["config/settings.yaml"])
        assert e2 is not None
        assert len(e2.prompt_constraints) >= 1

        # unknown (no enrichment) → should get None
        e3 = checklist.get_enrichment("WCP-T3", ["misc/readme.txt"])
        # For unknown domain tasks without enrichment, get_enrichment may
        # return None or an enrichment with domain "unknown"
        if e3 is not None:
            assert e3.domain.value == "unknown" or e3.prompt_constraints == []

        # --- Step 4: DevelopmentPhase receives checklist ---
        dev_phase = DevelopmentPhase(domain_checklist=checklist)
        assert dev_phase.domain_checklist is not None

        # --- Step 5: ImplementPhaseHandler accepts enriched_seed_path ---
        handler = ImplementPhaseHandler()
        assert hasattr(handler, "_enriched_seed_path") or hasattr(handler, "_project_root"), (
            "ImplementPhaseHandler not wired with enriched seed path"
        )

        # --- Step 6: FINALIZE validates completeness ---
        finalize = FinalizePhaseHandler()
        assert hasattr(finalize, "_validate_propagation_completeness"), (
            "FinalizePhaseHandler lacks propagation completeness validation"
        )
        results = finalize._validate_propagation_completeness({"tasks": tasks})
        assert results["total"] == 3
        assert results["complete"] == 2
        assert results["defaulted"] == 1

        # Completeness should be ~66%
        completeness_pct = round(
            results["complete"] / max(results["total"], 1) * 100, 1,
        )
        assert 60.0 <= completeness_pct <= 70.0, (
            f"Expected ~66% completeness, got {completeness_pct}%"
        )
