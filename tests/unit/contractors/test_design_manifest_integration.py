"""Tests for Phase 5: Code Manifest DESIGN Phase Integration.

Covers:
- FeatureContext.manifest_summary field
- YAML placeholder rendering with manifest blocks
- V1 path manifest injection via _task_to_feature_context()
- V2 ManifestModule rendering
- Edit-mode block enhancement with manifest summaries
- Graceful degradation when manifest_registry=None
- Budget compliance for manifest context
- Kill switch (manifest_consumption_enabled=False)
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

# Ensure the conftest FakeSeedTask is importable
sys.path.insert(0, str(Path(__file__).parent))
from conftest import FakeSeedTask  # noqa: E402

from startd8.contractors.artisan_phases.design_documentation import (
    FeatureContext,
    _build_edit_mode_block,
    _build_structural_awareness_block,
    _build_structural_validation_block,
    _build_structural_ground_truth_block,
    build_design_system_prompt,
    build_refine_system_prompt,
)
from startd8.contractors.artisan_phases.design_prompts.modules import (
    ManifestModule,
    PromptFragment,
)
from startd8.contractors.artisan_phases.design_prompts.seed_mapping import (
    extract_manifest_context,
)
from startd8.contractors.prompt_utils import CONTEXT_FIELD_TIERS


# ============================================================================
# Helpers
# ============================================================================


def _make_mock_registry(
    summaries: dict[str, str] | None = None,
    dep_graph: dict[str, list[str]] | None = None,
) -> MagicMock:
    """Create a mock ManifestRegistry with configurable responses."""
    registry = MagicMock()
    _summaries = summaries or {}

    def _file_element_summary(
        filepath: str, budget: int = 4000, *, include_resolved_types: bool = False
    ) -> str:
        summary = _summaries.get(filepath, "")
        if summary and len(summary) > budget:
            return summary[:budget]
        return summary

    registry.file_element_summary = MagicMock(side_effect=_file_element_summary)
    registry.dependency_graph = MagicMock(return_value=dep_graph or {})
    return registry


@pytest.fixture
def basic_task():
    """A minimal SeedTask for testing manifest integration."""
    return FakeSeedTask(
        task_id="DM-001",
        title="Add manifest module",
        description="Integrate code manifest into DESIGN phase.",
        target_files=["src/manifest.py", "src/config.py"],
        estimated_loc=120,
        feature_id="F-DM",
        domain="backend",
        prompt_constraints=["[BINDING] Use existing ManifestRegistry API"],
    )


@pytest.fixture
def mock_registry():
    """Registry with sample file summaries."""
    return _make_mock_registry(
        summaries={
            "src/manifest.py": (
                "Classes: ManifestRegistry(BaseRegistry)\n"
                "Functions: parse_ast(source) -> AST, resolve_imports()\n"
                "Imports: ast, pathlib"
            ),
            "src/config.py": (
                "Classes: Config(BaseModel)\n"
                "Functions: load_config(path) -> Config\n"
                "Imports: pydantic, pathlib"
            ),
        },
        dep_graph={
            "src/manifest.py": ["src/config.py", "src/utils.py"],
            "src/config.py": ["pydantic"],
        },
    )


# ============================================================================
# 7a: FeatureContext manifest_summary field
# ============================================================================


class TestFeatureContextManifestField:
    """Verify the manifest_summary field exists and defaults correctly."""

    def test_default_empty_string(self):
        ctx = FeatureContext(
            feature_name="test",
            description="desc",
            target_file="src/test.py",
        )
        assert ctx.manifest_summary == ""

    def test_explicit_value(self):
        ctx = FeatureContext(
            feature_name="test",
            description="desc",
            target_file="src/test.py",
            manifest_summary="Classes: Foo\nFunctions: bar()",
        )
        assert "Classes: Foo" in ctx.manifest_summary


# ============================================================================
# 7b: YAML placeholder rendering (no KeyError)
# ============================================================================


class TestYAMLPlaceholderRendering:
    """Verify all 8 templates render cleanly with empty defaults."""

    def test_design_system_renders(self):
        result = build_design_system_prompt()
        assert "software architect" in result

    def test_design_system_with_manifest(self):
        result = build_design_system_prompt(has_manifest_context=True)
        assert "Structural Awareness" in result

    def test_refine_system_renders(self):
        result = build_refine_system_prompt()
        assert "refining" in result

    def test_refine_system_with_manifest(self):
        result = build_refine_system_prompt(has_manifest_context=True)
        assert "Structural Awareness" in result

    def test_reviewer_system_renders(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        result = format_prompt(
            "design", "reviewer_system",
            structural_validation_block="",
        )
        assert "code reviewer" in result

    def test_reviewer_system_with_block(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        block = _build_structural_validation_block(True)
        result = format_prompt(
            "design", "reviewer_system",
            structural_validation_block=block,
        )
        assert "Structural Validation" in result

    def test_arbiter_system_renders(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        result = format_prompt(
            "design", "arbiter_system",
            structural_ground_truth_block="",
        )
        assert "pragmatic arbiter" in result

    def test_arbiter_system_with_block(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        block = _build_structural_ground_truth_block(True)
        result = format_prompt(
            "design", "arbiter_system",
            structural_ground_truth_block=block,
        )
        assert "Ground Truth" in result

    def test_reviewer_user_renders(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        result = format_prompt(
            "design", "reviewer_user",
            project_context="",
            manifest_context="",
            design_document="test doc",
        )
        assert "test doc" in result

    def test_arbiter_user_renders(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        result = format_prompt(
            "design", "arbiter_user",
            project_context="",
            manifest_context="",
            design_document="test doc",
        )
        assert "test doc" in result

    def test_design_user_renders(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        result = format_prompt(
            "design", "design_user",
            feature_name="Test",
            requirements_block="",
            description="desc",
            target_file="test.py",
            constraints="None",
            additional_context="None",
            manifest_context="",
            revision_guidance="",
        )
        assert "Test" in result

    def test_refine_user_renders(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        result = format_prompt(
            "design", "refine_user",
            feature_name="Test",
            requirements_block="",
            description="desc",
            target_file="test.py",
            constraints="None",
            additional_context="None",
            manifest_context="",
            prior_design="prior doc",
            revision_guidance="",
        )
        assert "prior doc" in result


# ============================================================================
# 7c: V1 path manifest injection
# ============================================================================


class TestV1ManifestInjection:
    """Test _task_to_feature_context with manifest registry."""

    def test_manifest_summary_populated(self, basic_task, mock_registry):
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            basic_task,
            manifest_registry=mock_registry,
            manifest_context_budget=2000,
        )
        assert ctx.manifest_summary != ""
        assert "ManifestRegistry" in ctx.manifest_summary
        assert "manifest_context" in ctx.additional_context

    def test_no_registry_returns_empty(self, basic_task):
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            basic_task,
            manifest_registry=None,
        )
        assert ctx.manifest_summary == ""
        assert "manifest_context" not in ctx.additional_context

    def test_registry_called_per_target_file(self, basic_task, mock_registry):
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        DesignPhaseHandler._task_to_feature_context(
            basic_task,
            manifest_registry=mock_registry,
            manifest_context_budget=1500,
        )
        assert mock_registry.file_element_summary.call_count == len(
            basic_task.target_files
        )

    def test_empty_target_files_skips(self, mock_registry):
        task = FakeSeedTask(task_id="DM-002", target_files=[])
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            task,
            manifest_registry=mock_registry,
        )
        assert ctx.manifest_summary == ""

    def test_registry_exception_handled(self, basic_task):
        """Registry exceptions per file should not crash the handler."""
        registry = MagicMock()
        registry.file_element_summary = MagicMock(
            side_effect=RuntimeError("symtable error"),
        )
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            basic_task,
            manifest_registry=registry,
        )
        assert ctx.manifest_summary == ""


# ============================================================================
# 7d: V2 ManifestModule
# ============================================================================


class TestManifestModule:
    """Test ManifestModule.render() with sample data."""

    def test_render_with_summaries(self):
        mod = ManifestModule()
        data = {
            "file_summaries": {
                "src/a.py": "Classes: A\nFunctions: foo()",
                "src/b.py": "Classes: B\nFunctions: bar()",
            },
        }
        frag = mod.render(data)
        assert isinstance(frag, PromptFragment)
        assert frag.category == "manifest"
        assert frag.droppable is False
        assert "src/a.py" in frag.text
        assert "Classes: A" in frag.text
        assert "src/b.py" in frag.text

    def test_render_with_dependency_context(self):
        mod = ManifestModule()
        data = {
            "file_summaries": {"src/a.py": "Classes: A"},
            "dependency_context": {
                "src/a.py": ["src/b.py", "src/c.py"],
            },
        }
        frag = mod.render(data)
        assert "File Dependencies" in frag.text
        assert "src/b.py" in frag.text

    def test_render_empty_summaries(self):
        mod = ManifestModule()
        frag = mod.render({"file_summaries": {}})
        assert frag.text == ""
        assert frag.token_estimate == 0

    def test_render_no_summaries_key(self):
        mod = ManifestModule()
        frag = mod.render({})
        assert frag.text == ""


# ============================================================================
# 7e: Edit-mode block with manifest summaries
# ============================================================================


class TestEditModeBlockManifest:
    """Test _build_edit_mode_block with and without manifest_summaries."""

    def test_without_manifest(self):
        result = _build_edit_mode_block(
            edit_mode_hint="edit",
            existing_target_files=["src/a.py", "src/b.py"],
        )
        assert "src/a.py" in result
        assert "ALREADY EXIST" in result
        # No structural detail
        assert "Classes:" not in result

    def test_with_manifest(self):
        summaries = {
            "src/a.py": "Classes: Foo\nFunctions: bar()",
        }
        result = _build_edit_mode_block(
            edit_mode_hint="edit",
            existing_target_files=["src/a.py", "src/b.py"],
            manifest_summaries=summaries,
        )
        assert "Classes: Foo" in result
        assert "src/a.py" in result
        # src/b.py has no summary, still listed
        assert "src/b.py" in result

    def test_create_mode_returns_empty(self):
        result = _build_edit_mode_block(
            edit_mode_hint="create",
            existing_target_files=["src/a.py"],
            manifest_summaries={"src/a.py": "Classes: X"},
        )
        assert result == ""

    def test_none_hint_returns_empty(self):
        result = _build_edit_mode_block(
            edit_mode_hint=None,
            existing_target_files=["src/a.py"],
            manifest_summaries={"src/a.py": "Classes: X"},
        )
        assert result == ""


# ============================================================================
# 7f: Graceful degradation
# ============================================================================


class TestGracefulDegradation:
    """All paths work when manifest_registry=None."""

    def test_structural_blocks_empty_without_manifest(self):
        assert _build_structural_awareness_block(False) == ""
        assert _build_structural_validation_block(False) == ""
        assert _build_structural_ground_truth_block(False) == ""

    def test_extract_manifest_context_returns_none(self, basic_task):
        result = extract_manifest_context(basic_task, manifest_registry=None)
        assert result is None

    def test_manifest_module_in_modules_list(self):
        """ManifestModule is registered in the _MODULES list."""
        from startd8.contractors.artisan_phases.design_prompts import _MODULES
        categories = [m.category for m in _MODULES]
        assert "manifest" in categories

    def test_tier_registration(self):
        """manifest_context is registered as Tier 1 (High)."""
        assert CONTEXT_FIELD_TIERS.get("manifest_context") == 1


# ============================================================================
# 7g: Budget compliance
# ============================================================================


class TestBudgetCompliance:
    """Verify manifest context respects manifest_context_budget."""

    def test_budget_truncation(self, basic_task):
        large_summary = "X" * 5000
        registry = _make_mock_registry(
            summaries={"src/manifest.py": large_summary},
        )
        result = extract_manifest_context(
            basic_task,
            manifest_registry=registry,
            manifest_context_budget=100,
        )
        assert result is not None
        for filepath, summary in result["file_summaries"].items():
            assert len(summary) <= 100

    def test_budget_passed_to_registry(self, basic_task, mock_registry):
        extract_manifest_context(
            basic_task,
            manifest_registry=mock_registry,
            manifest_context_budget=1234,
        )
        for call_args in mock_registry.file_element_summary.call_args_list:
            assert call_args[0][1] == 1234  # second positional arg is budget


# ============================================================================
# 7g2: Phase 5 Plan Ingestion — PI-1, PI-2, PI-3
# ============================================================================


class TestPhase5PlanIngestion:
    """PI-1: module_version in context. PI-2: resolved signatures. PI-3: graceful degradation."""

    def test_pi1_module_versions_included_when_enable_introspect(self, basic_task):
        """PI-1: When enable_introspect=True, module_versions dict is populated."""
        registry = _make_mock_registry(
            summaries={
                "src/manifest.py": "Classes: Foo",
                "src/config.py": "Functions: load",
            },
        )
        registry.module_version_for = MagicMock(side_effect=lambda p: {
            "src/manifest.py": "0.4.0",
            "src/config.py": "0.4.0",
        }.get(p))
        result = extract_manifest_context(
            basic_task,
            manifest_registry=registry,
            enable_introspect=True,
        )
        assert result is not None
        assert "module_versions" in result
        assert result["module_versions"]["src/manifest.py"] == "0.4.0"
        assert result["module_versions"]["src/config.py"] == "0.4.0"

    def test_pi1_module_versions_absent_when_no_versions(self, basic_task):
        """PI-1: When no files have module_version, key is absent."""
        registry = _make_mock_registry(
            summaries={"src/manifest.py": "Classes: Foo"},
        )
        registry.module_version_for = MagicMock(return_value=None)
        result = extract_manifest_context(
            basic_task,
            manifest_registry=registry,
            enable_introspect=True,
        )
        assert result is not None
        assert "module_versions" not in result

    def test_pi2_include_resolved_types_passed_to_registry(self, basic_task, mock_registry):
        """PI-2: When enable_introspect=True, file_element_summary gets include_resolved_types=True."""
        mock_registry.module_version_for = MagicMock(return_value=None)
        extract_manifest_context(
            basic_task,
            manifest_registry=mock_registry,
            enable_introspect=True,
        )
        for call in mock_registry.file_element_summary.call_args_list:
            assert call[1].get("include_resolved_types") is True

    def test_pi3_graceful_degradation_without_introspect(self, basic_task, mock_registry):
        """PI-3: When enable_introspect=False, no module_versions, include_resolved_types not passed."""
        result = extract_manifest_context(
            basic_task,
            manifest_registry=mock_registry,
            enable_introspect=False,
        )
        assert result is not None
        assert "module_versions" not in result
        # file_element_summary called without include_resolved_types (default False)
        for call in mock_registry.file_element_summary.call_args_list:
            assert call[1].get("include_resolved_types", False) is False

    def test_pi3_default_enable_introspect_false(self, basic_task, mock_registry):
        """PI-3: Default enable_introspect=False preserves pre-Phase-5 behavior."""
        result = extract_manifest_context(
            basic_task,
            manifest_registry=mock_registry,
        )
        assert result is not None
        assert "module_versions" not in result


# ============================================================================
# 7h: Kill switch
# ============================================================================


class TestKillSwitch:
    """manifest_consumption_enabled=False skips all manifest processing."""

    def test_kill_switch_in_handler_config(self):
        from startd8.contractors.context_seed_handlers import HandlerConfig
        config = HandlerConfig(manifest_consumption_enabled=False)
        assert config.manifest_consumption_enabled is False

    def test_kill_switch_default_enabled(self):
        from startd8.contractors.context_seed_handlers import HandlerConfig
        config = HandlerConfig()
        assert config.manifest_consumption_enabled is True


# ============================================================================
# 7i: CS-4 — Dependency graph injection in V1 path
# ============================================================================


class TestV1DependencyGraphInjection:
    """Test CS-4: dependency_graph() data injected into additional_context."""

    def test_dependency_graph_injected(self, basic_task, mock_registry):
        """Registry with dep_graph → manifest_dependencies populated."""
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            basic_task,
            manifest_registry=mock_registry,
            manifest_context_budget=2000,
        )
        assert "manifest_dependencies" in ctx.additional_context
        deps = ctx.additional_context["manifest_dependencies"]
        assert "src/manifest.py imports from:" in deps
        assert "src/config.py" in deps
        assert "src/utils.py" in deps

    def test_dependency_graph_absent(self, basic_task):
        """Registry without dep_graph → key absent."""
        registry = _make_mock_registry(
            summaries={"src/manifest.py": "Classes: Foo"},
            dep_graph={},
        )
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            basic_task,
            manifest_registry=registry,
            manifest_context_budget=2000,
        )
        assert "manifest_dependencies" not in ctx.additional_context

    def test_dependency_graph_exception_handled(self, basic_task):
        """dependency_graph() exception should not crash the handler."""
        registry = _make_mock_registry(
            summaries={"src/manifest.py": "Classes: Foo"},
        )
        registry.dependency_graph = MagicMock(
            side_effect=RuntimeError("graph error"),
        )
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            basic_task,
            manifest_registry=registry,
            manifest_context_budget=2000,
        )
        # Should degrade gracefully — no crash, key absent
        assert "manifest_dependencies" not in ctx.additional_context

    def test_dependency_tier_registration(self):
        """manifest_dependencies is registered as Tier 2 (Medium)."""
        assert CONTEXT_FIELD_TIERS.get("manifest_dependencies") == 2


# ============================================================================
# 7j: CS-3 — Edit-mode manifest context key
# ============================================================================


class TestEditModeManifestContextKey:
    """Test CS-3: manifest_edit_context key in additional_context."""

    def test_edit_mode_adds_manifest_edit_context(self, mock_registry):
        """edit_mode_hint='edit' → manifest_edit_context populated."""
        task = FakeSeedTask(
            task_id="DM-010",
            target_files=["src/manifest.py"],
        )
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            task,
            manifest_registry=mock_registry,
            manifest_context_budget=2000,
            scaffold_existing_files=["src/manifest.py"],
        )
        assert ctx.edit_mode_hint == "edit"
        assert "manifest_edit_context" in ctx.additional_context
        assert "ManifestRegistry" in ctx.additional_context["manifest_edit_context"]

    def test_create_mode_no_manifest_edit_context(self, mock_registry):
        """edit_mode_hint='create' → no manifest_edit_context key."""
        task = FakeSeedTask(
            task_id="DM-011",
            target_files=["src/new_file.py"],
        )
        from startd8.contractors.context_seed_handlers import DesignPhaseHandler
        ctx = DesignPhaseHandler._task_to_feature_context(
            task,
            manifest_registry=mock_registry,
            manifest_context_budget=2000,
            scaffold_existing_files=[],
        )
        assert ctx.edit_mode_hint == "create"
        assert "manifest_edit_context" not in ctx.additional_context

    def test_edit_context_tier_registration(self):
        """manifest_edit_context is registered as Tier 1 (High)."""
        assert CONTEXT_FIELD_TIERS.get("manifest_edit_context") == 1


# ============================================================================
# 7k: EM-3 — Dependency consumers in edit-mode block
# ============================================================================


class TestEditModeBlockDependencyConsumers:
    """Test EM-3: dependency_consumers rendered in edit-mode block."""

    def test_dependency_consumers_rendered(self):
        """File with consumers → 'Imported by' line appears."""
        result = _build_edit_mode_block(
            edit_mode_hint="edit",
            existing_target_files=["src/a.py", "src/b.py"],
            manifest_summaries={"src/a.py": "Classes: Foo"},
            dependency_consumers={
                "src/a.py": ["src/main.py", "src/cli.py"],
            },
        )
        assert "Imported by: src/main.py, src/cli.py" in result

    def test_no_consumers_omits_line(self):
        """File with no consumers → no 'Imported by' line."""
        result = _build_edit_mode_block(
            edit_mode_hint="edit",
            existing_target_files=["src/a.py"],
            manifest_summaries={"src/a.py": "Classes: Foo"},
            dependency_consumers={},
        )
        assert "Imported by" not in result

    def test_consumers_without_summaries(self):
        """dependency_consumers works even without manifest_summaries."""
        result = _build_edit_mode_block(
            edit_mode_hint="edit",
            existing_target_files=["src/a.py"],
            dependency_consumers={"src/a.py": ["src/consumer.py"]},
        )
        assert "Imported by: src/consumer.py" in result


# ============================================================================
# 7l: EM-5 — Budget enforcement in edit-mode block
# ============================================================================


class TestEditModeBlockBudget:
    """Test EM-5: manifest_budget parameter enforces per-file truncation."""

    def test_budget_enforcement(self):
        """Summaries exceeding budget → truncated per-file."""
        large_summary = "Z" * 3000
        result = _build_edit_mode_block(
            edit_mode_hint="edit",
            existing_target_files=["src/a.py", "src/b.py"],
            manifest_summaries={
                "src/a.py": large_summary,
                "src/b.py": large_summary,
            },
            manifest_budget=200,
        )
        # Per-file budget = 200 // 2 = 100 chars
        # Each file's summary should be truncated to 100 chars
        # Count total Z chars in result — should be <= 200 (budget)
        z_count = result.count("Z")
        assert z_count <= 200

    def test_small_budget_still_renders(self):
        """Even a tiny budget produces valid output."""
        result = _build_edit_mode_block(
            edit_mode_hint="edit",
            existing_target_files=["src/a.py"],
            manifest_summaries={"src/a.py": "Classes: BigClass\nFunctions: foo()"},
            manifest_budget=10,
        )
        assert "ALREADY EXIST" in result
        assert "src/a.py" in result


# ============================================================================
# 7m: DR-2 — Breaking change detection in reviewer block
# ============================================================================


class TestBreakingChangeDetection:
    """Test DR-2: reviewer validation block references breaking changes."""

    def test_reviewer_block_mentions_breaking_changes(self):
        block = _build_structural_validation_block(True)
        assert "breaking change" in block
        assert "Dependencies" in block

    def test_reviewer_system_with_block_has_breaking_change(self):
        from startd8.contractors.artisan_phases.prompts import format_prompt
        block = _build_structural_validation_block(True)
        result = format_prompt(
            "design", "reviewer_system",
            structural_validation_block=block,
        )
        assert "breaking change" in result
