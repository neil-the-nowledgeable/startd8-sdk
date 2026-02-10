"""
Unit tests for LeadContractorChunkExecutor.

Tests cover:
- Async wrapping of synchronous generator.generate()
- Cost/token metric accumulation in context
- GenerationResult storage in chunk.metadata["_generation_result"]
- Dry-run short-circuit
- Retry feedback injection into generation context
- Task description enrichment with prompt constraints
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.artisan_phases.development import (
    DevelopmentChunk,
    LeadContractorChunkExecutor,
)
from startd8.contractors.protocols import GenerationResult


# ============================================================================
# Fixtures
# ============================================================================


def _make_chunk(
    chunk_id: str = "task-1",
    description: str = "Implement feature X",
    file_targets: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> DevelopmentChunk:
    """Create a DevelopmentChunk for testing."""
    return DevelopmentChunk(
        chunk_id=chunk_id,
        description=description,
        dependencies=[],
        file_targets=file_targets or ["src/feature_x.py"],
        implementation_prompt=description,
        test_commands=[],
        max_retries=2,
        metadata=metadata or {
            "feature_id": "F1",
            "domain": "backend",
            "estimated_loc": 100,
            "prompt_constraints": ["Use type hints", "Follow PEP 8"],
            "environment_checks": [],
            "post_generation_validators": ["ruff", "mypy"],
            "title": "Feature X",
        },
    )


def _make_generation_result(
    success: bool = True,
    cost: float = 0.05,
    input_tokens: int = 1000,
    output_tokens: int = 500,
    iterations: int = 2,
    error: str | None = None,
) -> GenerationResult:
    """Create a GenerationResult for testing."""
    return GenerationResult(
        success=success,
        generated_files=[Path("generated/feature_x.py")] if success else [],
        error=error,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost,
        iterations=iterations,
        model="anthropic:claude-sonnet-4-5-20250927",
    )


def _make_mock_generator(result: GenerationResult | None = None) -> MagicMock:
    """Create a mock CodeGenerator."""
    mock = MagicMock()
    mock.generate.return_value = result or _make_generation_result()
    return mock


# ============================================================================
# Tests: execute() basics
# ============================================================================


class TestLeadContractorChunkExecutorExecute:
    """Tests for the core execute() method."""

    @pytest.mark.asyncio
    async def test_successful_execution(self):
        """Successful generation returns (True, output_summary)."""
        gen_result = _make_generation_result(success=True)
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        success, output = await executor.execute(chunk, context)

        assert success is True
        assert "Generated files:" in output
        mock_gen.generate.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_execution(self):
        """Failed generation returns (False, error_message)."""
        gen_result = _make_generation_result(
            success=False, error="LLM returned empty code"
        )
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        success, output = await executor.execute(chunk, context)

        assert success is False
        assert "LLM returned empty code" in output

    @pytest.mark.asyncio
    async def test_dry_run_skips_generation(self):
        """Dry-run mode skips generation entirely."""
        mock_gen = _make_mock_generator()

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": True}

        success, output = await executor.execute(chunk, context)

        assert success is True
        assert "Dry-run" in output
        mock_gen.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_returns_false(self):
        """Unexpected exceptions are caught and returned as failure."""
        mock_gen = MagicMock()
        mock_gen.generate.side_effect = RuntimeError("Unexpected!")

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        success, output = await executor.execute(chunk, context)

        assert success is False
        assert "Unexpected!" in output


# ============================================================================
# Tests: GenerationResult storage in metadata
# ============================================================================


class TestGenerationResultStorage:
    """Tests for storing GenerationResult in chunk metadata."""

    @pytest.mark.asyncio
    async def test_generation_result_stored_in_metadata(self):
        """GenerationResult is stored under _generation_result key."""
        gen_result = _make_generation_result(success=True)
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        await executor.execute(chunk, context)

        assert "_generation_result" in chunk.metadata
        stored = chunk.metadata["_generation_result"]
        assert stored is gen_result
        assert stored.success is True
        assert stored.cost_usd == 0.05

    @pytest.mark.asyncio
    async def test_failed_result_also_stored(self):
        """Even failed results are stored for cost tracking."""
        gen_result = _make_generation_result(success=False, error="fail")
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        await executor.execute(chunk, context)

        assert chunk.metadata["_generation_result"].success is False

    @pytest.mark.asyncio
    async def test_per_chunk_cost_in_metadata(self):
        """Per-chunk cost metrics are stored in metadata."""
        gen_result = _make_generation_result(
            success=True, cost=0.12, input_tokens=2000, output_tokens=800
        )
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        await executor.execute(chunk, context)

        assert chunk.metadata["llm_cost_usd"] == 0.12
        assert chunk.metadata["llm_input_tokens"] == 2000
        assert chunk.metadata["llm_output_tokens"] == 800
        assert chunk.metadata["iterations"] == 2


# ============================================================================
# Tests: Cost accumulation in context
# ============================================================================


class TestCostAccumulation:
    """Tests for cost/token metric accumulation in context."""

    @pytest.mark.asyncio
    async def test_cost_accumulated_in_context(self):
        """Cost and tokens are accumulated across executions."""
        gen_result = _make_generation_result(
            success=True, cost=0.05, input_tokens=1000, output_tokens=500
        )
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        await executor.execute(chunk, context)

        assert context["_llm_cost_usd"] == pytest.approx(0.05)
        assert context["_llm_input_tokens"] == 1000
        assert context["_llm_output_tokens"] == 500

    @pytest.mark.asyncio
    async def test_cost_accumulates_across_chunks(self):
        """Costs add up across multiple chunk executions."""
        gen_result = _make_generation_result(
            success=True, cost=0.03, input_tokens=500, output_tokens=200
        )
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        # Execute two chunks
        chunk1 = _make_chunk(chunk_id="task-1")
        chunk2 = _make_chunk(chunk_id="task-2")

        await executor.execute(chunk1, context)
        await executor.execute(chunk2, context)

        assert context["_llm_cost_usd"] == pytest.approx(0.06)
        assert context["_llm_input_tokens"] == 1000
        assert context["_llm_output_tokens"] == 400


# ============================================================================
# Tests: Retry feedback injection
# ============================================================================


class TestRetryFeedback:
    """Tests for retry feedback injection into generation context."""

    @pytest.mark.asyncio
    async def test_retry_feedback_injected_into_task_desc(self):
        """When context has last_error, it's injected into task description."""
        gen_result = _make_generation_result(success=True)
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {
            "plan_id": "test",
            "dry_run": False,
            "last_error": "TypeError: missing arg",
            "test_output": "FAILED test_feature_x",
        }

        await executor.execute(chunk, context)

        # Check the task description passed to generate()
        call_args = mock_gen.generate.call_args
        task_desc = call_args[0][0]  # First positional arg
        assert "Retry Feedback" in task_desc
        assert "TypeError: missing arg" in task_desc
        assert "FAILED test_feature_x" in task_desc

    @pytest.mark.asyncio
    async def test_no_retry_feedback_on_first_attempt(self):
        """First attempt (no last_error) doesn't include retry section."""
        gen_result = _make_generation_result(success=True)
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        await executor.execute(chunk, context)

        call_args = mock_gen.generate.call_args
        task_desc = call_args[0][0]
        assert "Retry Feedback" not in task_desc

    @pytest.mark.asyncio
    async def test_prompt_constraints_in_task_desc(self):
        """Prompt constraints from metadata are included in task description."""
        gen_result = _make_generation_result(success=True)
        mock_gen = _make_mock_generator(gen_result)

        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        await executor.execute(chunk, context)

        call_args = mock_gen.generate.call_args
        task_desc = call_args[0][0]
        assert "Use type hints" in task_desc
        assert "Follow PEP 8" in task_desc


# ============================================================================
# Tests: Context building
# ============================================================================


class TestContextBuilding:
    """Tests for _build_generation_context()."""

    def test_basic_context_fields(self):
        """Basic metadata fields are included in generation context."""
        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        chunk = _make_chunk()
        context: Dict[str, Any] = {"plan_id": "test", "dry_run": False}

        gen_ctx = executor._build_generation_context(chunk, context)

        assert gen_ctx["task_id"] == "task-1"
        assert gen_ctx["feature_id"] == "F1"
        assert gen_ctx["domain"] == "backend"
        assert gen_ctx["target_files"] == ["src/feature_x.py"]
        assert gen_ctx["estimated_loc"] == 100
        assert gen_ctx["prompt_constraints"] == ["Use type hints", "Follow PEP 8"]

    def test_domain_constraints_injected(self):
        """Domain constraints from DomainChecklist are forwarded."""
        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        chunk = _make_chunk()
        context: Dict[str, Any] = {
            "plan_id": "test",
            "dry_run": False,
            "domain_constraints": ["Must use SQLAlchemy", "No raw SQL"],
        }

        gen_ctx = executor._build_generation_context(chunk, context)

        assert gen_ctx["domain_constraints"] == ["Must use SQLAlchemy", "No raw SQL"]

    def test_retry_feedback_in_context(self):
        """Retry feedback is included in generation context."""
        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        chunk = _make_chunk()
        context: Dict[str, Any] = {
            "plan_id": "test",
            "dry_run": False,
            "last_error": "ImportError: no module named foo",
            "test_output": "test_foo FAILED",
        }

        gen_ctx = executor._build_generation_context(chunk, context)

        assert "retry_feedback" in gen_ctx
        assert gen_ctx["retry_feedback"]["last_error"] == "ImportError: no module named foo"


# ============================================================================
# Tests: Generator resolution
# ============================================================================


class TestGeneratorResolution:
    """Tests for lazy generator resolution."""

    def test_generator_cached_after_first_resolve(self):
        """Generator is created once and cached."""
        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))

        # Inject a mock to avoid real import
        mock_gen = _make_mock_generator()
        executor._generator = mock_gen

        result = executor._resolve_generator()
        assert result is mock_gen

    def test_injected_generator_used(self):
        """Pre-injected generator is used without re-creation."""
        mock_gen = _make_mock_generator()
        executor = LeadContractorChunkExecutor(output_dir=Path("/tmp/test"))
        executor._generator = mock_gen

        assert executor._resolve_generator() is mock_gen
