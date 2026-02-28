"""Tests for IMPLEMENT walk-through mode prompt persistence."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class FakeTokenUsage:
    input: int = 100
    output: int = 200
    cost_estimate: float = 0.001


@dataclass
class FakeDevelopmentChunk:
    chunk_id: str = "WT-001"
    description: str = "Walkthrough test task"
    dependencies: list = field(default_factory=list)
    file_targets: list = field(default_factory=lambda: ["src/widget.py"])
    implementation_prompt: str = "Implement widget"
    test_commands: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    priority: int = 0


# ---------------------------------------------------------------------------
# IMPLEMENT walkthrough
# ---------------------------------------------------------------------------


class TestImplementWalkthrough:
    """Test ArtisanChunkExecutor walkthrough prompt persistence."""

    def test_walkthrough_persists_t1_prompts(self, tmp_path):
        """Walkthrough writes t1_system_prompt.md and t1_user_prompt.md."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk()
        executor._persist_walkthrough_prompts(
            chunk,
            task_desc="## Task\nImplement widget module",
            sys_prompt="You are an expert Python engineer.",
            context={},
            complexity_tier="tier_2",
            effective_drafter_spec="mock:mock-model",
        )

        wt_dir = tmp_path / ".startd8" / "walkthrough" / "implement" / "WT-001"
        assert wt_dir.exists()
        assert (wt_dir / "t1_system_prompt.md").exists()
        assert (wt_dir / "t1_user_prompt.md").exists()
        assert (wt_dir / "metadata.json").exists()

        sys_content = (wt_dir / "t1_system_prompt.md").read_text()
        assert "Python engineer" in sys_content

        user_content = (wt_dir / "t1_user_prompt.md").read_text()
        assert "Implement widget" in user_content

        meta = json.loads((wt_dir / "metadata.json").read_text())
        assert meta["chunk_id"] == "WT-001"
        assert meta["drafter_spec"] == "mock:mock-model"
        assert meta["refiner_spec"] is None

    def test_walkthrough_persists_t2_prompts_when_refiner_set(self, tmp_path):
        """When refiner_spec is set, walkthrough writes T2 prompt templates."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="mock:refiner-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk()
        executor._persist_walkthrough_prompts(
            chunk,
            task_desc="## Task\nImplement widget",
            sys_prompt="You are an expert.",
            context={},
            complexity_tier="tier_2",
            effective_drafter_spec="mock:mock-model",
        )

        wt_dir = tmp_path / ".startd8" / "walkthrough" / "implement" / "WT-001"
        assert (wt_dir / "t2_refine_system_prompt.md").exists()
        assert (wt_dir / "t2_refine_user_prompt.md").exists()

        t2_user = (wt_dir / "t2_refine_user_prompt.md").read_text()
        assert "{draft_code}" in t2_user

        meta = json.loads((wt_dir / "metadata.json").read_text())
        assert meta["refiner_spec"] == "mock:refiner-model"

    def test_walkthrough_no_t2_prompts_without_refiner(self, tmp_path):
        """When refiner_spec is None, no T2 prompt files are written."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk()
        executor._persist_walkthrough_prompts(
            chunk,
            task_desc="## Task",
            sys_prompt="System prompt.",
            context={},
            complexity_tier="tier_2",
            effective_drafter_spec="mock:mock-model",
        )

        wt_dir = tmp_path / ".startd8" / "walkthrough" / "implement" / "WT-001"
        assert not (wt_dir / "t2_refine_system_prompt.md").exists()
        assert not (wt_dir / "t2_refine_user_prompt.md").exists()

    @pytest.mark.asyncio
    @patch("startd8.contractors.artisan_phases.development.ArtisanChunkExecutor._resolve_artisan_drafter")
    async def test_execute_walkthrough_skips_llm(self, mock_drafter, tmp_path):
        """In walkthrough mode, execute() persists prompts and skips LLM call."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        # The drafter should NOT be called
        fake_agent = AsyncMock()
        mock_drafter.return_value = fake_agent

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk()
        context: Dict[str, Any] = {"walkthrough": True}

        success, msg = await executor.execute(chunk, context)

        assert success
        assert "Walkthrough" in msg
        assert "prompts persisted" in msg
        # LLM should NOT have been called
        fake_agent.agenerate.assert_not_called()

        # Verify prompt files exist
        wt_dir = tmp_path / ".startd8" / "walkthrough" / "implement" / "WT-001"
        assert wt_dir.exists()


# ---------------------------------------------------------------------------
# DESIGN walkthrough
# NOTE: DesignDocumentationPhase walkthrough tests removed (REQ-DSR-001).
# ---------------------------------------------------------------------------


class TestDevelopmentWalkthrough:
    """Test walkthrough prompt persistence for development/implement phase."""

    def test_walkthrough_output_directory_structure(self, tmp_path):
        """Verify the expected directory structure for walkthrough output."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="mock:refiner-model",
            output_dir=tmp_path / "staging",
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk(chunk_id="PI-001")
        executor._persist_walkthrough_prompts(
            chunk,
            "task desc",
            "sys prompt",
            {},
            complexity_tier="tier_2",
            effective_drafter_spec="mock:mock-model",
        )

        # Check structure
        base = tmp_path / ".startd8" / "walkthrough" / "implement" / "PI-001"
        expected_files = [
            "t1_system_prompt.md",
            "t1_user_prompt.md",
            "t2_refine_system_prompt.md",
            "t2_refine_user_prompt.md",
            "metadata.json",
        ]
        for fname in expected_files:
            assert (base / fname).exists(), f"Missing: {fname}"

    @pytest.mark.asyncio
    async def test_walkthrough_propagates_through_development_phase(self, tmp_path):
        """DevelopmentPhase.run() propagates walkthrough flag to executor context."""
        from startd8.contractors.artisan_phases.development import (
            DevelopmentPhase,
            DevelopmentPlan,
            DevelopmentChunk,
            DefaultTestRunner,
            JsonFileStateStore,
        )

        staging = tmp_path / "staging"
        staging.mkdir()
        state_dir = tmp_path / "state"
        state_dir.mkdir()

        # Track what context the executor receives
        captured_contexts: list = []

        class CapturingExecutor:
            async def execute(self, chunk, context):
                captured_contexts.append(dict(context))
                return True, "captured"

        plan = DevelopmentPlan(
            plan_id="test-wt-propagation",
            chunks=[
                DevelopmentChunk(
                    chunk_id="WTP-001",
                    description="Test walkthrough propagation",
                    dependencies=[],
                    file_targets=["src/test.py"],
                    implementation_prompt="Test",
                    test_commands=[],
                ),
            ],
            config={
                "dry_run": False,
                "walkthrough": True,
                "state_dir": str(state_dir),
            },
        )

        dev_phase = DevelopmentPhase(
            executor=CapturingExecutor(),
            test_runner=DefaultTestRunner(),
            state_store=JsonFileStateStore(directory=str(state_dir)),
            max_parallel=1,
        )

        result = await dev_phase.run(plan)

        assert len(captured_contexts) == 1
        assert captured_contexts[0].get("walkthrough") is True


# ---------------------------------------------------------------------------
# AR-410: Design doc S/R disambiguation
# ---------------------------------------------------------------------------


class TestAR410DesignDocSRDisambiguation:
    """AR-410: When design doc contains S/R spec blocks, inject disambiguation."""

    def test_design_doc_with_sr_blocks_gets_disambiguation(self):
        """Design framing includes disambiguation note when S/R markers present."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        design_doc = (
            "# Changes\n"
            "<<<<<<< SEARCH\n"
            "old_function()\n"
            "=======\n"
            "new_function()\n"
            ">>>>>>> REPLACE\n"
        )
        chunk = FakeDevelopmentChunk(
            metadata={"design_document": design_doc},
        )
        existing = {"src/widget.py": "def old_function(): pass\n"}

        parts = LeadContractorChunkExecutor._build_design_framing(chunk, existing)

        joined = "\n".join(parts)
        assert "SEARCH/REPLACE notation" in joined
        assert "NOT your output format" in joined

    def test_design_doc_without_sr_blocks_no_disambiguation(self):
        """Design framing omits disambiguation note when no S/R markers."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = FakeDevelopmentChunk(
            metadata={"design_document": "# Pure prose design\nAdd a widget class."},
        )
        existing = {"src/widget.py": "# existing\n"}

        parts = LeadContractorChunkExecutor._build_design_framing(chunk, existing)

        joined = "\n".join(parts)
        assert "SEARCH/REPLACE notation" not in joined

    def test_sr_disambiguation_only_for_edit_mode(self):
        """Disambiguation is only injected in edit mode (existing files present)."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        design_doc = "<<<<<<< SEARCH\nold\n=======\nnew\n>>>>>>> REPLACE\n"
        chunk = FakeDevelopmentChunk(
            metadata={"design_document": design_doc},
        )
        # No existing files → CREATE mode
        parts = LeadContractorChunkExecutor._build_design_framing(chunk, {})

        joined = "\n".join(parts)
        assert "SEARCH/REPLACE notation" not in joined


# ---------------------------------------------------------------------------
# AR-411: Stale context suppression
# ---------------------------------------------------------------------------


class TestAR411StaleContextSuppressed:
    """AR-411: Template-default placeholders are suppressed from prompts."""

    def test_stale_architectural_context_suppressed(self):
        """Stale arch_ctx with template-default objectives/constraints is omitted."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = FakeDevelopmentChunk(
            metadata={
                "architectural_context": {
                    "objectives": ["Example objective for the project"],
                    "constraints": ["Do NOT proceed to Phase 1 until reviewed"],
                },
            },
        )

        parts = LeadContractorChunkExecutor._build_supplementary_context(chunk)
        joined = "\n".join(parts)
        assert "Project Architecture" not in joined
        assert "Example objective" not in joined
        assert "Do NOT proceed to Phase 1" not in joined

    def test_stale_service_metadata_suppressed(self):
        """Stale svc_meta with no transport_protocol + boilerplate is omitted."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = FakeDevelopmentChunk(
            metadata={
                "service_metadata": {
                    "transport_protocol": None,
                    "healthcheck_note": "HEALTHCHECK type MUST match transport_protocol",
                },
            },
        )

        parts = LeadContractorChunkExecutor._build_supplementary_context(chunk)
        joined = "\n".join(parts)
        assert "Service Metadata" not in joined

    def test_legitimate_context_preserved(self):
        """Real arch_ctx with non-template objectives is preserved."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = FakeDevelopmentChunk(
            metadata={
                "architectural_context": {
                    "objectives": ["Implement OTel cost tracking for all providers"],
                    "constraints": ["Must use existing CostTracker interface"],
                },
            },
        )

        parts = LeadContractorChunkExecutor._build_supplementary_context(chunk)
        joined = "\n".join(parts)
        assert "Project Architecture" in joined
        assert "OTel cost tracking" in joined
        assert "CostTracker interface" in joined

    def test_legitimate_service_metadata_preserved(self):
        """Real svc_meta with transport_protocol is preserved."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = FakeDevelopmentChunk(
            metadata={
                "service_metadata": {
                    "transport_protocol": "grpc",
                    "runtime_dependencies": ["grpcio"],
                },
            },
        )

        parts = LeadContractorChunkExecutor._build_supplementary_context(chunk)
        joined = "\n".join(parts)
        assert "Service Metadata" in joined
        assert "grpc" in joined

    def test_mixed_stale_and_real_fields(self):
        """When objectives are stale but constraints are real, only constraints shown."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        chunk = FakeDevelopmentChunk(
            metadata={
                "architectural_context": {
                    "objectives": ["Example objective — update with real business goal"],
                    "constraints": ["All handlers must implement the Protocol interface"],
                },
            },
        )

        parts = LeadContractorChunkExecutor._build_supplementary_context(chunk)
        joined = "\n".join(parts)
        assert "Project Architecture" in joined
        assert "Example objective" not in joined
        assert "Protocol interface" in joined

    def test_svc_meta_no_useful_fields_suppressed(self):
        """Dict with keys but no transport_protocol or runtime_dependencies is suppressed."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        # Simulates real seed data: dict has keys but no useful content
        chunk = FakeDevelopmentChunk(
            metadata={
                "service_metadata": {
                    "transport_protocol": None,
                    "some_other_key": "irrelevant value",
                },
            },
        )

        parts = LeadContractorChunkExecutor._build_supplementary_context(chunk)
        joined = "\n".join(parts)
        assert "Service Metadata" not in joined
        assert "HEALTHCHECK" not in joined

    def test_is_stale_context_unknown_field(self):
        """Unknown field names return False (no markers configured)."""
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        assert LeadContractorChunkExecutor._is_stale_context("unknown_field", "anything") is False


# ---------------------------------------------------------------------------
# AR-412: T2 context condensation
# ---------------------------------------------------------------------------


class TestAR412T2ContextCondensed:
    """AR-412: T2 refinement uses condensed context instead of full T1 prompt."""

    def test_t2_context_includes_essential_fields(self):
        """_build_t2_context includes design doc, constraints, target files."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        chunk = FakeDevelopmentChunk(
            description="Implement cost tracking module",
            file_targets=["src/costs/tracker.py", "src/costs/analytics.py"],
            metadata={
                "project_name": "startd8",
                "design_document": "# Cost Tracker Design\n## API\ndef track_cost()...",
                "prompt_constraints": ["Must use Pydantic v2 models"],
                "parameter_sources": {
                    "cost_usd": {"origin": "CostTracker.total_cost"},
                    "provider": {"origin": "agent.provider_name"},
                },
                "semantic_conventions": {
                    "cost.total": {"rule": "Sum of all provider costs"},
                },
            },
        )

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="mock:refiner-model",
            output_dir=Path("/tmp/staging"),
        )

        t2 = executor._build_t2_context(chunk, {})

        assert "startd8" in t2
        assert "`src/costs/tracker.py`" in t2
        assert "Cost Tracker Design" in t2
        assert "Implement cost tracking module" in t2
        assert "Pydantic v2" in t2
        assert "`cost_usd`" in t2
        assert "cost.total" in t2

    def test_t2_context_excludes_heavy_fields(self):
        """_build_t2_context excludes existing file content and plan context."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        existing_content = "x" * 50000  # Large existing file content
        chunk = FakeDevelopmentChunk(
            description="Small edit",
            metadata={
                "design_document": "# Small change",
                "plan_context": "Long plan context " * 1000,
                "architectural_context": {"objectives": ["Real obj"]},
                "existing_files": {"src/big.py": existing_content},
            },
        )

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=Path("/tmp/staging"),
        )

        t2 = executor._build_t2_context(chunk, {})

        # Should NOT contain plan context or existing file content
        assert "Long plan context" not in t2
        assert existing_content not in t2
        # Should contain design doc and description
        assert "Small change" in t2
        assert "Small edit" in t2

    def test_t2_context_smaller_than_t1(self):
        """T2 context should be significantly smaller than a full T1 prompt."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        # Build a chunk with lots of metadata
        chunk = FakeDevelopmentChunk(
            description="Implement feature X",
            file_targets=["src/feature.py"],
            metadata={
                "project_name": "myproject",
                "design_document": "# Design\n" + "Design line\n" * 50,
                "plan_context": "Plan context " * 500,
                "requirements_text": "Requirements " * 200,
                "architectural_context": {
                    "objectives": ["Build scalable system"],
                    "constraints": ["Use async patterns"],
                },
                "prompt_constraints": ["Follow PEP 8"],
                "parameter_sources": {"param1": "source1"},
            },
        )

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=Path("/tmp/staging"),
        )

        t2 = executor._build_t2_context(chunk, {})

        # T2 context should be much smaller than all metadata combined
        all_meta_size = sum(
            len(str(v)) for v in chunk.metadata.values()
        )
        assert len(t2) < all_meta_size

    def test_walkthrough_metadata_has_t2_chars(self, tmp_path):
        """Walkthrough metadata.json includes estimated_t2_context_chars."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="mock:refiner-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk(
            metadata={
                "design_document": "# Design\nImplement widget",
            },
        )
        executor._persist_walkthrough_prompts(
            chunk,
            task_desc="## Full T1 prompt with lots of context",
            sys_prompt="System prompt.",
            context={},
            complexity_tier="tier_2",
            effective_drafter_spec="mock:mock-model",
        )

        wt_dir = tmp_path / ".startd8" / "walkthrough" / "implement" / "WT-001"
        meta = json.loads((wt_dir / "metadata.json").read_text())
        assert "estimated_t2_context_chars" in meta
        assert meta["estimated_t2_context_chars"] > 0

    def test_walkthrough_metadata_t2_chars_zero_without_refiner(self, tmp_path):
        """Without refiner, estimated_t2_context_chars is 0."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk()
        executor._persist_walkthrough_prompts(
            chunk,
            task_desc="## Task",
            sys_prompt="System prompt.",
            context={},
            complexity_tier="tier_2",
            effective_drafter_spec="mock:mock-model",
        )

        wt_dir = tmp_path / ".startd8" / "walkthrough" / "implement" / "WT-001"
        meta = json.loads((wt_dir / "metadata.json").read_text())
        assert meta["estimated_t2_context_chars"] == 0
