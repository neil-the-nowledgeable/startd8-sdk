"""Tests for PCA P0 Critical Path Requirements.

PCA-100: project_root in initial_context
PCA-200: checkpoint context keys for onboarding fields
PCA-201: _ensure_context_loaded re-extracts onboarding from seed
PCA-203: backward compat — v4 checkpoint without new keys loads OK
PCA-300: architectural_context + plan_goals + plan_context in chunk metadata
PCA-301/400: service_metadata in chunk metadata + generation context
PCA-302: project context section in review prompt
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.contractors.conftest import FakeSeedTask


# ============================================================================
# PCA-200: _CHECKPOINT_CONTEXT_KEYS includes onboarding + service fields
# ============================================================================

class TestPCA200CheckpointKeys:
    """PCA-200: 8 new keys must survive checkpoint round-trip."""

    def test_checkpoint_keys_contain_onboarding_fields(self):
        from startd8.contractors.artisan_contractor import _CHECKPOINT_CONTEXT_KEYS

        expected_new = {
            "onboarding_derivation_rules",
            "onboarding_resolved_parameters",
            "onboarding_output_contracts",
            "onboarding_calibration_hints",
            "onboarding_open_questions",
            "onboarding_dependency_graph",
            "service_metadata",
            "plan_document_text",
        }
        missing = expected_new - _CHECKPOINT_CONTEXT_KEYS
        assert not missing, f"Missing checkpoint keys: {missing}"

    def test_checkpoint_keys_total_count(self):
        """Guard against accidental removal of existing keys."""
        from startd8.contractors.artisan_contractor import _CHECKPOINT_CONTEXT_KEYS

        # 22 existing + 8 new = 30
        assert len(_CHECKPOINT_CONTEXT_KEYS) >= 30, (
            f"Expected >= 30 checkpoint keys, got {len(_CHECKPOINT_CONTEXT_KEYS)}"
        )


# ============================================================================
# PCA-203: Backward compat — old checkpoints without new keys still load
# ============================================================================

class TestPCA203BackwardCompat:
    """A v4 checkpoint (pre-PCA) that lacks the 8 new keys must not crash."""

    def test_old_checkpoint_loads_without_new_keys(self):
        from startd8.contractors.artisan_contractor import _CHECKPOINT_CONTEXT_KEYS

        # Simulate a v4 checkpoint that has only the original keys
        original_keys = {
            "enriched_seed_path", "plan_title", "plan_goals", "domain_summary",
            "preflight_summary", "total_estimated_loc", "architectural_context",
            "design_calibration", "task_filter", "project_root",
            "design_results", "test_results", "review_results",
            "integration_results", "abort_on_preflight_fail",
            "source_checksum", "parameter_sources", "semantic_conventions",
            "output_conventions", "scaffold", "example_artifacts",
            "workflow_id", "truncation_flags", "_staging_dir",
        }
        old_context = {k: "dummy" for k in original_keys}

        # Checkpoint filtering: only persist keys in the frozenset
        filtered = {k: v for k, v in old_context.items() if k in _CHECKPOINT_CONTEXT_KEYS}

        # All original keys survive
        assert set(filtered.keys()) == original_keys

        # New keys are simply absent — no error
        new_keys = {"service_metadata", "plan_document_text", "onboarding_derivation_rules"}
        for key in new_keys:
            assert key not in filtered


# ============================================================================
# PCA-201: _ensure_context_loaded re-extracts onboarding from seed
# ============================================================================

class TestPCA201ContextReload:
    """_ensure_context_loaded restores onboarding fields from seed data."""

    def _make_seed_data(self) -> dict[str, Any]:
        return {
            "plan": {
                "title": "Test Plan",
                "goals": ["goal-1", "goal-2"],
            },
            "tasks": [
                {
                    "task_id": "T-1",
                    "title": "Test task",
                    "description": "A test task",
                    "target_files": ["src/foo.py"],
                    "estimated_loc": 50,
                    "feature_id": "F-1",
                    "domain": "backend",
                },
            ],
            "onboarding": {
                "derivation_rules": {"rule1": "value1"},
                "resolved_artifact_parameters": {"param1": "v1"},
                "expected_output_contracts": [{"name": "contract1"}],
                "design_calibration_hints": {"hint1": "h1"},
                "open_questions": ["q1"],
                "artifact_dependency_graph": {"dep": "graph"},
                "service_metadata": {"transport_protocol": "gRPC"},
            },
            "artifacts": {
                "source_checksum": "abc123",
                "parameter_sources": {},
                "semantic_conventions": {},
                "output_conventions": {},
            },
        }

    def _write_seed_json(self, seed_data: dict, path: Path) -> None:
        """Write seed data as JSON (the format _load_enriched_seed expects)."""
        path.write_text(json.dumps(seed_data), encoding="utf-8")

    def test_onboarding_fields_restored_on_empty_context(self, tmp_path):
        """When context has no onboarding keys, they are re-extracted from seed."""
        from startd8.contractors.context_seed_handlers import _ensure_context_loaded

        seed_data = self._make_seed_data()
        seed_file = tmp_path / "seed.json"
        self._write_seed_json(seed_data, seed_file)

        context: dict[str, Any] = {
            "enriched_seed_path": str(seed_file),
        }

        _ensure_context_loaded(context)

        assert context["onboarding_derivation_rules"] == {"rule1": "value1"}
        assert context["onboarding_resolved_parameters"] == {"param1": "v1"}
        assert context["onboarding_output_contracts"] == [{"name": "contract1"}]
        assert context["onboarding_calibration_hints"] == {"hint1": "h1"}
        assert context["onboarding_open_questions"] == ["q1"]
        assert context["onboarding_dependency_graph"] == {"dep": "graph"}
        assert context["service_metadata"] == {"transport_protocol": "gRPC"}

    def test_onboarding_fields_not_overwritten_if_present(self, tmp_path):
        """Pre-existing context keys are NOT overwritten by seed data."""
        from startd8.contractors.context_seed_handlers import _ensure_context_loaded

        seed_data = self._make_seed_data()
        seed_file = tmp_path / "seed.json"
        self._write_seed_json(seed_data, seed_file)

        context: dict[str, Any] = {
            "enriched_seed_path": str(seed_file),
            "service_metadata": {"transport_protocol": "HTTP"},  # pre-existing
        }

        _ensure_context_loaded(context)

        # Pre-existing value preserved
        assert context["service_metadata"] == {"transport_protocol": "HTTP"}
        # Others restored from seed
        assert context["onboarding_derivation_rules"] == {"rule1": "value1"}

    def test_plan_document_text_restored_from_file(self, tmp_path):
        """plan_document_text is re-loaded from plan_document_path in artifacts."""
        from startd8.contractors.context_seed_handlers import _ensure_context_loaded

        plan_text = "# My Plan\n\nThis is the plan content."
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan_text, encoding="utf-8")

        seed_data = self._make_seed_data()
        seed_data["artifacts"]["plan_document_path"] = str(plan_file)
        seed_file = tmp_path / "seed.json"
        self._write_seed_json(seed_data, seed_file)

        context: dict[str, Any] = {
            "enriched_seed_path": str(seed_file),
        }

        _ensure_context_loaded(context)

        assert context["plan_document_text"] == plan_text


# ============================================================================
# PCA-300/301/400: _tasks_to_chunks includes project context in metadata
# ============================================================================

class TestPCA300ChunkMetadata:
    """architectural_context, plan_goals, plan_context, service_metadata
    are injected into DevelopmentChunk.metadata by _tasks_to_chunks."""

    def _make_task(self) -> FakeSeedTask:
        return FakeSeedTask(
            task_id="T-1",
            title="Build API",
            target_files=["src/api.py"],
        )

    def test_architectural_context_in_chunk(self):
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        arch = {"objectives": ["scalability"], "constraints": ["no ORM"]}
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [self._make_task()],
            architectural_context=arch,
        )
        assert len(chunks) == 1
        assert chunks[0].metadata["architectural_context"] == arch

    def test_plan_goals_in_chunk_capped_at_5(self):
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        goals = [f"goal-{i}" for i in range(10)]
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [self._make_task()],
            plan_goals=goals,
        )
        assert len(chunks[0].metadata["plan_goals"]) == 5

    def test_plan_context_in_chunk_truncated(self):
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        long_text = "x" * 5000
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [self._make_task()],
            plan_context=long_text,
        )
        assert len(chunks[0].metadata["plan_context"]) <= 4000

    def test_service_metadata_in_chunk(self):
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        svc = {"transport_protocol": "gRPC", "runtime_dependencies": ["protobuf"]}
        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [self._make_task()],
            service_metadata=svc,
        )
        assert chunks[0].metadata["service_metadata"] == svc

    def test_none_service_metadata_is_none_in_chunk(self):
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [self._make_task()],
            service_metadata=None,
        )
        assert chunks[0].metadata["service_metadata"] is None

    def test_empty_architectural_context_defaults_to_empty_dict(self):
        from startd8.contractors.context_seed_handlers import ImplementPhaseHandler

        chunks, _ = ImplementPhaseHandler._tasks_to_chunks(
            [self._make_task()],
        )
        assert chunks[0].metadata["architectural_context"] == {}
        assert chunks[0].metadata["plan_goals"] == []
        assert chunks[0].metadata["plan_context"] is None
        assert chunks[0].metadata["service_metadata"] is None


# ============================================================================
# PCA-300/301: _build_generation_context extracts PCA fields from metadata
# ============================================================================

class TestPCA300GenerationContext:
    """_build_generation_context propagates PCA metadata into gen_ctx."""

    def _make_executor(self, tmp_path):
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        executor = LeadContractorChunkExecutor.__new__(LeadContractorChunkExecutor)
        executor._output_dir = tmp_path
        executor._MAX_EXISTING_FILE_BYTES = 50_000
        executor.logger = MagicMock()
        return executor

    def _make_chunk(self, metadata: dict[str, Any]):
        from startd8.contractors.artisan_phases.development import DevelopmentChunk

        return DevelopmentChunk(
            chunk_id="T-1",
            description="Build API",
            dependencies=[],
            file_targets=["src/api.py"],
            implementation_prompt="build it",
            test_commands=[],
            max_retries=1,
            metadata=metadata,
        )

    def test_architectural_context_propagated(self, tmp_path):
        executor = self._make_executor(tmp_path)
        arch = {"objectives": ["perf"], "constraints": ["no ORM"]}
        chunk = self._make_chunk({"architectural_context": arch})

        gen_ctx = executor._build_generation_context(chunk, {})

        assert gen_ctx["architectural_context"] == arch

    def test_service_metadata_propagated(self, tmp_path):
        executor = self._make_executor(tmp_path)
        svc = {"transport_protocol": "HTTP", "runtime_dependencies": ["flask"]}
        chunk = self._make_chunk({"service_metadata": svc})

        gen_ctx = executor._build_generation_context(chunk, {})

        assert gen_ctx["service_metadata"] == svc

    def test_plan_goals_propagated(self, tmp_path):
        executor = self._make_executor(tmp_path)
        chunk = self._make_chunk({"plan_goals": ["g1", "g2"]})

        gen_ctx = executor._build_generation_context(chunk, {})

        assert gen_ctx["plan_goals"] == ["g1", "g2"]

    def test_empty_metadata_excluded(self, tmp_path):
        executor = self._make_executor(tmp_path)
        chunk = self._make_chunk({})

        gen_ctx = executor._build_generation_context(chunk, {})

        assert "architectural_context" not in gen_ctx
        assert "service_metadata" not in gen_ctx
        assert "plan_goals" not in gen_ctx


# ============================================================================
# PCA-300/301: _build_task_description includes project architecture section
# ============================================================================

class TestPCA300TaskDescription:
    """_build_task_description injects ## Project Architecture and ## Service Metadata."""

    def _make_executor(self, tmp_path):
        from startd8.contractors.artisan_phases.development import (
            LeadContractorChunkExecutor,
        )

        executor = LeadContractorChunkExecutor.__new__(LeadContractorChunkExecutor)
        executor._output_dir = tmp_path
        executor._MAX_EXISTING_FILE_BYTES = 50_000
        executor.logger = MagicMock()
        return executor

    def _make_chunk(self, metadata: dict[str, Any]):
        from startd8.contractors.artisan_phases.development import DevelopmentChunk

        return DevelopmentChunk(
            chunk_id="T-1",
            description="Build API",
            dependencies=[],
            file_targets=["src/api.py"],
            implementation_prompt="build it",
            test_commands=[],
            max_retries=1,
            metadata=metadata,
        )

    def test_project_architecture_section(self, tmp_path):
        executor = self._make_executor(tmp_path)
        chunk = self._make_chunk({
            "architectural_context": {
                "objectives": ["high availability"],
                "constraints": ["no ORM", "Python 3.9+"],
            },
        })

        desc = executor._build_task_description(chunk, {})

        assert "## Project Architecture" in desc
        assert "high availability" in desc
        assert "no ORM" in desc

    def test_project_goals_section(self, tmp_path):
        executor = self._make_executor(tmp_path)
        chunk = self._make_chunk({
            "plan_goals": ["deliver MVP", "ensure test coverage"],
        })

        desc = executor._build_task_description(chunk, {})

        assert "## Project Goals" in desc
        assert "deliver MVP" in desc

    def test_service_metadata_section(self, tmp_path):
        executor = self._make_executor(tmp_path)
        chunk = self._make_chunk({
            "service_metadata": {
                "transport_protocol": "gRPC",
                "runtime_dependencies": ["protobuf", "grpcio"],
            },
        })

        desc = executor._build_task_description(chunk, {})

        assert "## Service Metadata" in desc
        assert "gRPC" in desc
        assert "protobuf, grpcio" in desc
        assert "HEALTHCHECK type MUST match transport_protocol" in desc

    def test_no_sections_when_metadata_absent(self, tmp_path):
        executor = self._make_executor(tmp_path)
        chunk = self._make_chunk({})

        desc = executor._build_task_description(chunk, {})

        assert "## Project Architecture" not in desc
        assert "## Project Goals" not in desc
        assert "## Service Metadata" not in desc


# ============================================================================
# PCA-302: _build_review_prompt includes ## Project Context
# ============================================================================

class TestPCA302ReviewPrompt:
    """_build_review_prompt injects project context section."""

    def _make_handler(self):
        from startd8.contractors.context_seed_handlers import ReviewPhaseHandler

        handler = ReviewPhaseHandler.__new__(ReviewPhaseHandler)
        # Set minimal config
        config = MagicMock()
        config.review_max_code_chars = 50_000
        config.pass_threshold = 70
        config.review_task_retries = 0
        handler.config = config
        return handler

    def _make_task(self) -> FakeSeedTask:
        return FakeSeedTask(
            task_id="T-1",
            title="Build API",
            domain="backend",
            description="A task",
            prompt_constraints=["constraint1"],
        )

    def test_project_context_section_present(self):
        handler = self._make_handler()
        task = self._make_task()

        project_context = {
            "plan_title": "My Great Plan",
            "plan_goals": ["goal-1", "goal-2"],
            "architectural_context": {
                "objectives": ["scalability"],
                "constraints": ["Python 3.9+"],
            },
        }

        prompt = handler._build_review_prompt(
            task,
            generated_code="def foo(): pass",
            test_results={"passed": True},
            project_context=project_context,
        )

        assert "## Project Context" in prompt
        assert "My Great Plan" in prompt
        assert "goal-1" in prompt
        assert "scalability" in prompt
        assert "Python 3.9+" in prompt

    def test_no_project_context_when_none(self):
        handler = self._make_handler()
        task = self._make_task()

        prompt = handler._build_review_prompt(
            task,
            generated_code="def foo(): pass",
            test_results={"passed": True},
            project_context=None,
        )

        assert "## Project Context" not in prompt

    def test_project_context_truncated_at_2000_chars(self):
        handler = self._make_handler()
        task = self._make_task()

        # Create a project_context that would produce > 2000 chars
        project_context = {
            "plan_goals": [f"very long goal description number {i} " * 20 for i in range(20)],
        }

        prompt = handler._build_review_prompt(
            task,
            generated_code="def foo(): pass",
            test_results={"passed": True},
            project_context=project_context,
        )

        assert "## Project Context" in prompt
        assert "truncated for prompt budget" in prompt

    def test_project_context_injected_before_review_instructions(self):
        handler = self._make_handler()
        task = self._make_task()

        project_context = {
            "plan_title": "Test Plan",
        }

        prompt = handler._build_review_prompt(
            task,
            generated_code="def foo(): pass",
            test_results={"passed": True},
            project_context=project_context,
        )

        ctx_pos = prompt.find("## Project Context")
        review_pos = prompt.find("## Review Instructions")
        if review_pos >= 0:
            assert ctx_pos < review_pos, (
                "Project Context must appear before Review Instructions"
            )
