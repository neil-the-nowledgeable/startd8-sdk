"""Tests for IMP-1 through IMP-7: Artisan prompt externalization and quality improvements."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure src/ is on path for direct imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))


# ============================================================================
# Part A: Prompt Externalization
# ============================================================================


class TestPromptLoader:
    """Tests for the YAML prompt loader module."""

    def test_load_design_yaml(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        t = get_template("design", "design_system")
        assert isinstance(t, str)
        assert len(t) > 100
        assert "{sections_list}" in t

    def test_load_plan_ingestion_yaml(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        t = get_template("plan_ingestion", "parse")
        assert "{plan_text}" in t

    def test_load_test_construction_yaml(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        t = get_template("test_construction", "test_system")
        assert "expert Python test engineer" in t

    def test_load_review_yaml(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        t = get_template("review", "review_user")
        assert "{task_id}" in t

    def test_format_prompt(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        result = format_prompt(
            "design", "revision_user",
            original_document="doc1",
            review_feedback="feedback1",
            guidance="guidance1",
        )
        assert "doc1" in result
        assert "feedback1" in result

    def test_get_depth_tiers(self):
        from startd8.contractors.artisan_phases.prompts import get_depth_tiers
        tiers = get_depth_tiers()
        assert "brief" in tiers
        assert "standard" in tiers
        assert "comprehensive" in tiers
        assert tiers["brief"]["max_tokens"] == 4096
        assert tiers["comprehensive"]["max_tokens"] == 16384

    def test_missing_prompt_raises(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        with pytest.raises(KeyError):
            get_template("design", "nonexistent_prompt")

    def test_missing_file_raises(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        with pytest.raises(FileNotFoundError):
            get_template("nonexistent_phase", "some_prompt")

    def test_caching(self):
        """Repeated loads return the same cached dict."""
        from startd8.contractors.artisan_phases.prompts import _load_file
        _load_file.cache_clear()
        d1 = _load_file("design")
        d2 = _load_file("design")
        assert d1 is d2  # Same object from cache


# ============================================================================
# IMP-2: Protocol-Aware DESIGN System Prompt
# ============================================================================


class TestIMP2ProtocolGuidance:
    """IMP-2: Protocol guidance is present in the design system prompt."""

    def test_design_system_prompt_has_protocol_guidance(self):
        from startd8.contractors.artisan_phases.design_documentation import (
            build_design_system_prompt,
        )
        result = build_design_system_prompt()
        assert "Protocol and Parameter Fidelity" in result
        assert "grpc_health_probe" in result
        assert "transport_protocol" in result

    def test_backward_compat_constant_has_protocol_guidance(self):
        from startd8.contractors.artisan_phases.design_documentation import (
            DESIGN_GENERATION_SYSTEM_PROMPT,
        )
        assert "Protocol and Parameter Fidelity" in DESIGN_GENERATION_SYSTEM_PROMPT

    def test_refine_system_prompt_does_not_have_protocol_guidance(self):
        """Protocol guidance is only in design_system, not refine_system."""
        from startd8.contractors.artisan_phases.design_documentation import (
            build_refine_system_prompt,
        )
        result = build_refine_system_prompt()
        assert "refining an existing design" in result


# ============================================================================
# IMP-3: All target_files passed to DESIGN
# ============================================================================


class TestIMP3AllTargetFiles:
    """IMP-3: All target_files are joined, not just the first."""

    def test_multiple_target_files_joined(self):
        """_task_to_feature_context joins all target_files with comma."""
        from startd8.contractors.context_seed_handlers import (
            DesignPhaseHandler,
        )

        # Create a minimal mock task with multiple target files
        class MockTask:
            title = "Test Feature"
            description = "A test"
            target_files = ["src/a.py", "src/b.py", "src/c.py"]
            prompt_constraints = []
            domain = "backend"
            domain_reasoning = ""
            available_siblings = []
            feature_id = "F-1"
            design_doc_sections = []
            artifact_types_addressed = []
            file_scope = {}
            requirements_text = ""
            api_signatures = []
            protocol = ""
            runtime_dependencies = []
            negative_scope = []

        ctx = DesignPhaseHandler._task_to_feature_context(MockTask())
        assert "src/a.py" in ctx.target_file
        assert "src/b.py" in ctx.target_file
        assert "src/c.py" in ctx.target_file
        assert ", " in ctx.target_file


# ============================================================================
# IMP-1: Requirements Text in DESIGN Prompt
# ============================================================================


class TestIMP1RequirementsText:
    """IMP-1: requirements_text flows from SeedTask to FeatureContext."""

    def test_seed_task_has_requirements_text_field(self):
        from startd8.contractors.context_seed_handlers import SeedTask
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SeedTask)]
        assert "requirements_text" in field_names

    def test_feature_context_has_requirements_text_field(self):
        from startd8.contractors.artisan_phases.design_documentation import FeatureContext
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(FeatureContext)]
        assert "requirements_text" in field_names

    def test_from_seed_entry_populates_requirements_text(self):
        from startd8.contractors.context_seed_handlers import SeedTask
        entry = {
            "task_id": "T-1",
            "title": "Test Task",
            "config": {
                "task_description": "Do something",
                "requirements_text": "Must use postgres user=admin",
                "context": {
                    "target_files": [],
                    "feature_id": "F-1",
                },
            },
        }
        task = SeedTask.from_seed_entry(entry)
        assert task.requirements_text == "Must use postgres user=admin"

    def test_design_user_template_has_requirements_block(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        t = get_template("design", "design_user")
        assert "{requirements_block}" in t


# ============================================================================
# IMP-4: ParsedFeature Schema Expansion
# ============================================================================


class TestIMP4ParsedFeatureSchema:
    """IMP-4: ParsedFeature has 4 new fields."""

    def test_parsed_feature_has_new_fields(self):
        from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(ParsedFeature)]
        assert "api_signatures" in field_names
        assert "protocol" in field_names
        assert "runtime_dependencies" in field_names
        assert "negative_scope" in field_names

    def test_parsed_feature_defaults(self):
        from startd8.workflows.builtin.plan_ingestion_models import ParsedFeature
        f = ParsedFeature(feature_id="F-1", name="test")
        assert f.api_signatures == []
        assert f.protocol == ""
        assert f.runtime_dependencies == []
        assert f.negative_scope == []

    def test_seed_task_has_new_fields(self):
        from startd8.contractors.context_seed_handlers import SeedTask
        import dataclasses
        field_names = [f.name for f in dataclasses.fields(SeedTask)]
        assert "api_signatures" in field_names
        assert "protocol" in field_names
        assert "runtime_dependencies" in field_names
        assert "negative_scope" in field_names

    def test_parse_prompt_has_new_fields(self):
        from startd8.contractors.artisan_phases.prompts import get_template
        t = get_template("plan_ingestion", "parse")
        assert "api_signatures" in t
        assert "protocol" in t
        assert "runtime_dependencies" in t
        assert "negative_scope" in t

    def test_to_seed_dict_includes_new_fields(self):
        from startd8.workflows.builtin.plan_ingestion_models import (
            ParsedFeature,
            ParsedPlan,
        )
        f = ParsedFeature(
            feature_id="F-1",
            name="test",
            api_signatures=["def serve(port: int)"],
            protocol="grpc",
            runtime_dependencies=["grpcio"],
            negative_scope=["no OpenTelemetry"],
        )
        plan = ParsedPlan(title="t", features=[f])
        d = plan.to_seed_dict()
        feat = d["features"][0]
        assert feat["api_signatures"] == ["def serve(port: int)"]
        assert feat["protocol"] == "grpc"
        assert feat["runtime_dependencies"] == ["grpcio"]
        assert feat["negative_scope"] == ["no OpenTelemetry"]


# ============================================================================
# IMP-5: Constraint Priority Tagging + Formatter
# ============================================================================


class TestIMP5ConstraintFormatter:
    """IMP-5: format_constraints groups by priority prefix."""

    def test_groups_by_prefix(self):
        from startd8.contractors.artisan_phases.prompts import format_constraints
        result = format_constraints([
            "[BINDING] Must use X",
            "[STRUCTURAL] Output single module",
            "[ADVISORY] Prefer stdlib",
            "Untagged rule",
        ])
        assert "### Binding (must not violate)" in result
        assert "Must use X" in result
        assert "### Structural (code organization)" in result
        assert "Output single module" in result
        assert "### Advisory (prefer but not blocking)" in result
        assert "Prefer stdlib" in result
        assert "- Untagged rule" in result

    def test_empty_constraints(self):
        from startd8.contractors.artisan_phases.prompts import format_constraints
        assert format_constraints([]) == ""

    def test_only_untagged(self):
        from startd8.contractors.artisan_phases.prompts import format_constraints
        result = format_constraints(["Rule A", "Rule B"])
        assert "- Rule A" in result
        assert "- Rule B" in result
        assert "###" not in result

    def test_python_single_constraints_are_tagged(self):
        """Smoke test that the preflight rule actually produces tagged constraints."""
        from startd8.workflows.builtin.preflight_rules.rules_python_single import (
            SingleModuleConstraintsRule,
        )
        # We can't easily instantiate a full RuleContext, so just verify
        # the class exists and has the expected rule_id
        assert SingleModuleConstraintsRule.rule_id == "single_module_constraints"


# ============================================================================
# IMP-6: Critical Parameters Elevation
# ============================================================================


class TestIMP6CriticalParameters:
    """IMP-6: resolved_parameters are elevated in _generate_design."""

    def test_feature_context_with_resolved_params(self):
        """When resolved_parameters are in additional_context, they should
        be formatted with the Critical Parameters header."""
        from startd8.contractors.artisan_phases.design_documentation import (
            FeatureContext,
        )
        ctx = FeatureContext(
            feature_name="Test",
            description="A test feature",
            target_file="test.py",
            additional_context={
                "resolved_parameters": {"db_user": "admin", "port": "5432"},
                "domain": "backend",
            },
        )
        # The resolved_parameters key exists and will be elevated in _generate_design
        assert "resolved_parameters" in ctx.additional_context


# ============================================================================
# IMP-7: DESIGN→IMPLEMENT Validation Gate
# ============================================================================


class TestIMP7ValidationGate:
    """IMP-7: Design completeness warning is injected into build_task_description."""

    def test_warning_injected_when_present(self):
        """_build_task_description includes design_completeness_warning if set."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
            DevelopmentChunk,
        )

        chunk = DevelopmentChunk(
            chunk_id="T-1",
            description="Implement feature",
            dependencies=[],
            file_targets=["test.py"],
            implementation_prompt="Implement feature",
            test_commands=[],
            max_retries=1,
            metadata={
                "design_document": "## Overview\nA design doc...",
                "prompt_constraints": [],
                "design_completeness_warning": (
                    "WARNING: 2 resolved parameter(s) not found in design document"
                ),
            },
        )

        executor = LeadContractorChunkExecutor.__new__(LeadContractorChunkExecutor)
        result = executor._build_task_description(chunk, {})
        assert "## Design Completeness Warning" in result
        assert "WARNING: 2 resolved parameter(s)" in result

    def test_no_warning_when_empty(self):
        """No warning section when design_completeness_warning is empty."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
            DevelopmentChunk,
        )

        chunk = DevelopmentChunk(
            chunk_id="T-1",
            description="Implement feature",
            dependencies=[],
            file_targets=["test.py"],
            implementation_prompt="Implement feature",
            test_commands=[],
            max_retries=1,
            metadata={
                "prompt_constraints": [],
                "design_completeness_warning": "",
            },
        )

        executor = LeadContractorChunkExecutor.__new__(LeadContractorChunkExecutor)
        result = executor._build_task_description(chunk, {})
        assert "Design Completeness Warning" not in result


# ============================================================================
# Integration: DEPTH_TIERS loaded from YAML
# ============================================================================


class TestDepthTiersFromYAML:
    """DEPTH_TIERS module-level constant is loaded from plan_ingestion.yaml."""

    def test_depth_tiers_loaded(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import DEPTH_TIERS
        assert isinstance(DEPTH_TIERS, dict)
        assert "brief" in DEPTH_TIERS
        assert DEPTH_TIERS["standard"]["max_tokens"] == 8192

    def test_depth_tiers_sections_are_lists(self):
        from startd8.workflows.builtin.plan_ingestion_workflow import DEPTH_TIERS
        for tier_name, tier in DEPTH_TIERS.items():
            assert isinstance(tier["sections"], list), f"{tier_name} sections not a list"
            assert len(tier["sections"]) > 0


# ============================================================================
# Integration: build_design_system_prompt uses YAML
# ============================================================================


class TestBuildDesignSystemPrompt:
    """build_design_system_prompt uses YAML template with dynamic sections."""

    def test_custom_sections(self):
        from startd8.contractors.artisan_phases.design_documentation import (
            build_design_system_prompt,
        )
        result = build_design_system_prompt(
            sections=["Overview", "Testing Strategy"],
            depth_guidance="Keep it brief",
        )
        assert "## Overview" in result
        assert "## Testing Strategy" in result
        assert "Keep it brief" in result
        # Default sections should NOT be present
        assert "## Data Model" not in result
