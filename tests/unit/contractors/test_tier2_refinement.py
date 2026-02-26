"""Tests for T2 refinement in ArtisanChunkExecutor and tier alias constants."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Tier alias identity checks
# ---------------------------------------------------------------------------


class TestTierAliases:
    """Verify T1/T2/T3 aliases point to the correct catalog entries."""

    def test_t1_economy_is_haiku(self):
        from startd8.contractors.protocols import (
            DRAFT_MODEL_CLAUDE_HAIKU,
            T1_ECONOMY,
        )
        assert T1_ECONOMY is DRAFT_MODEL_CLAUDE_HAIKU

    def test_t2_standard_is_sonnet(self):
        from startd8.contractors.protocols import (
            T2_STANDARD,
            VALIDATE_MODEL_CLAUDE_SONNET,
        )
        assert T2_STANDARD is VALIDATE_MODEL_CLAUDE_SONNET

    def test_t3_premium_is_opus(self):
        from startd8.contractors.protocols import (
            REVIEW_MODEL_CLAUDE_OPUS,
            T3_PREMIUM,
        )
        assert T3_PREMIUM is REVIEW_MODEL_CLAUDE_OPUS

    def test_tier_aliases_in_all(self):
        from startd8.contractors import protocols
        for name in ("T1_ECONOMY", "T2_STANDARD", "T3_PREMIUM"):
            assert name in protocols.__all__, f"{name} missing from __all__"


# ---------------------------------------------------------------------------
# HandlerConfig tier2 defaults
# ---------------------------------------------------------------------------


class TestHandlerConfigTier2:
    """Verify HandlerConfig resolves tier2_agent correctly."""

    def test_default_tier2_is_sonnet(self):
        from startd8.contractors.context_seed_handlers import HandlerConfig
        from startd8.contractors.protocols import VALIDATE_MODEL_CLAUDE_SONNET

        config = HandlerConfig()
        assert config.tier2_agent == VALIDATE_MODEL_CLAUDE_SONNET.agent_spec

    def test_skip_refinement_leaves_tier2_none(self):
        from startd8.contractors.context_seed_handlers import HandlerConfig

        config = HandlerConfig(skip_refinement=True)
        assert config.tier2_agent is None

    def test_explicit_tier2_overrides_default(self):
        from startd8.contractors.context_seed_handlers import HandlerConfig

        config = HandlerConfig(tier2_agent="openai:gpt-4-turbo")
        assert config.tier2_agent == "openai:gpt-4-turbo"

    def test_walkthrough_default_false(self):
        from startd8.contractors.context_seed_handlers import HandlerConfig

        config = HandlerConfig()
        assert config.walkthrough is False


# ---------------------------------------------------------------------------
# ArtisanChunkExecutor with/without refiner
# ---------------------------------------------------------------------------


@dataclass
class FakeTokenUsage:
    input: int = 100
    output: int = 200
    cost_estimate: float = 0.001


@dataclass
class FakeDevelopmentChunk:
    chunk_id: str = "test-chunk"
    description: str = "Test task"
    dependencies: list = field(default_factory=list)
    file_targets: list = field(default_factory=lambda: ["src/test.py"])
    implementation_prompt: str = "Implement test"
    test_commands: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    priority: int = 0


class TestArtisanChunkExecutorRefiner:
    """Test ArtisanChunkExecutor T2 refinement integration."""

    def test_init_without_refiner(self):
        """Default constructor has no refiner."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=Path("/tmp/test-staging"),
        )
        assert executor._refiner_spec is None
        assert executor._artisan_refiner is None

    def test_init_with_refiner(self):
        """Constructor stores refiner spec."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="anthropic:claude-sonnet-4-5-20250929",
            output_dir=Path("/tmp/test-staging"),
        )
        assert executor._refiner_spec == "anthropic:claude-sonnet-4-5-20250929"

    def test_resolve_refiner_returns_none_when_no_spec(self):
        """_resolve_artisan_refiner returns None when refiner_spec is None."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=Path("/tmp/test-staging"),
        )
        assert executor._resolve_artisan_refiner() is None

    @pytest.mark.asyncio
    @patch("startd8.contractors.artisan_phases.development.ArtisanChunkExecutor._resolve_artisan_refiner")
    @patch("startd8.contractors.artisan_phases.development.ArtisanChunkExecutor._resolve_artisan_drafter")
    async def test_execute_without_refiner_has_iterations_1(self, mock_drafter, mock_refiner, tmp_path):
        """When refiner_spec is None, iterations=1 in metadata."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        # Mock drafter
        fake_agent = AsyncMock()
        fake_agent.agenerate.return_value = (
            "```python\n# src/test.py\ndef hello(): pass\n```",
            100,
            FakeTokenUsage(),
        )
        fake_agent.model = "mock:mock-model"
        mock_drafter.return_value = fake_agent
        mock_refiner.return_value = None

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        chunk = FakeDevelopmentChunk()
        context: Dict[str, Any] = {}

        success, msg = await executor.execute(chunk, context)

        assert success
        assert chunk.metadata.get("iterations") == 1
        assert "refine_cost_usd" not in chunk.metadata

    @pytest.mark.asyncio
    async def test_refine_written_files_returns_none_on_empty_extraction(self, tmp_path):
        """_refine_written_files returns None when T2 produces empty code."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        # Write a draft file
        draft_file = staging / "src" / "test.py"
        draft_file.parent.mkdir(parents=True)
        draft_file.write_text("def hello(): pass\n")

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="mock:refiner-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        # Mock refiner to return truly empty response
        fake_refiner = AsyncMock()
        fake_refiner.agenerate.return_value = (
            "",  # Empty string — no code at all
            50,
            FakeTokenUsage(),
        )
        executor._artisan_refiner = fake_refiner

        chunk = FakeDevelopmentChunk()
        result = await executor._refine_written_files(
            [draft_file], "Test task", chunk, {},
        )
        assert result is None  # Falls back to T1

    @pytest.mark.asyncio
    async def test_refine_written_files_returns_none_on_exception(self, tmp_path):
        """_refine_written_files returns None when T2 throws an exception."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        draft_file = staging / "src" / "test.py"
        draft_file.parent.mkdir(parents=True)
        draft_file.write_text("def hello(): pass\n")

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="mock:refiner-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        # Mock refiner to raise
        fake_refiner = AsyncMock()
        fake_refiner.agenerate.side_effect = RuntimeError("API error")
        executor._artisan_refiner = fake_refiner

        chunk = FakeDevelopmentChunk()
        result = await executor._refine_written_files(
            [draft_file], "Test task", chunk, {},
        )
        assert result is None  # Non-fatal, keeps T1

    @pytest.mark.asyncio
    async def test_refine_written_files_success(self, tmp_path):
        """Successful T2 refinement overwrites staging files."""
        from startd8.contractors.artisan_phases.development import (
            ArtisanChunkExecutor,
        )

        staging = tmp_path / "staging"
        staging.mkdir()

        draft_file = staging / "src" / "test.py"
        draft_file.parent.mkdir(parents=True)
        draft_file.write_text("def hello(): pass  # T1 draft\n")

        executor = ArtisanChunkExecutor(
            drafter_spec="mock:mock-model",
            refiner_spec="mock:refiner-model",
            output_dir=staging,
            project_root=tmp_path,
        )

        refined_code = "def hello() -> None:\n    \"\"\"Say hello.\"\"\"\n    pass\n"
        fake_refiner = AsyncMock()
        fake_refiner.agenerate.return_value = (
            f"```python\n{refined_code}```",
            80,
            FakeTokenUsage(input=300, output=400, cost_estimate=0.005),
        )
        fake_refiner.model = "mock:refiner-model"
        executor._artisan_refiner = fake_refiner

        chunk = FakeDevelopmentChunk(file_targets=["src/test.py"])
        result = await executor._refine_written_files(
            [draft_file], "Test task", chunk, {},
        )

        assert result is not None
        updated_files, refine_info = result
        assert len(updated_files) > 0
        assert refine_info["refine_cost_usd"] == 0.005
        assert refine_info["refine_input_tokens"] == 300
        assert refine_info["refine_output_tokens"] == 400
