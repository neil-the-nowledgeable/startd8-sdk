"""Tests for missing file target detection (Fix 3).

Validates that LLMChunkExecutor and ArtisanChunkExecutor flag
_missing_targets in chunk metadata when generated files don't cover
all expected file_targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from startd8.contractors.artisan_phases.development import (
    DevelopmentChunk,
    LLMChunkExecutor,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_chunk(
    chunk_id: str = "T-1",
    file_targets: Optional[List[str]] = None,
) -> DevelopmentChunk:
    """Build a minimal DevelopmentChunk for testing."""
    return DevelopmentChunk(
        chunk_id=chunk_id,
        description="Test chunk",
        dependencies=[],
        file_targets=file_targets or ["src/foo.py"],
        implementation_prompt="Implement foo",
        test_commands=[],
    )


class _FakeTokenUsage:
    """Minimal token usage stub."""

    def __init__(self):
        self.input = 100
        self.output = 200
        self.cost_estimate = 0.01


# ============================================================================
# LLMChunkExecutor: missing target detection
# ============================================================================


class TestLLMChunkExecutorMissingTargets:
    """LLMChunkExecutor._write_generated_files + missing target check."""

    @pytest.mark.asyncio
    async def test_missing_target_flagged(self, tmp_path):
        """When LLM produces only 1 of 2 expected files, flag the missing one."""
        chunk = _make_chunk(
            file_targets=["src/foo.py", "src/bar.py"],
        )
        executor = LLMChunkExecutor(
            drafter_agent="mock:mock-model",
            output_dir=tmp_path,
        )

        # Mock the drafter agent and code extraction
        fake_usage = _FakeTokenUsage()
        mock_agent = AsyncMock()
        mock_agent.agenerate = AsyncMock(
            return_value=("```python\nprint('hello')\n```", 100, fake_usage),
        )
        mock_agent.model = "mock:mock-model"

        # Patch to return only one file (foo.py) from write
        written_file = tmp_path / "src" / "foo.py"
        written_file.parent.mkdir(parents=True, exist_ok=True)
        written_file.write_text("print('hello')", encoding="utf-8")

        with (
            patch.object(executor, "_resolve_drafter", return_value=mock_agent),
            patch(
                "startd8.utils.code_extraction.extract_code_from_response",
                return_value="print('hello')",
            ),
            patch.object(
                executor,
                "_write_generated_files",
                return_value=[written_file],
            ),
            patch(
                "startd8.contractors.forensic_log.emit_forensic_log",
            ),
        ):
            success, output = await executor.execute(chunk, {})

        assert success is True
        assert "_missing_targets" in chunk.metadata
        assert chunk.metadata["_missing_targets"] == ["src/bar.py"]

    @pytest.mark.asyncio
    async def test_all_targets_produced_no_flag(self, tmp_path):
        """When LLM produces all expected files, no _missing_targets."""
        chunk = _make_chunk(
            file_targets=["src/foo.py", "src/bar.py"],
        )
        executor = LLMChunkExecutor(
            drafter_agent="mock:mock-model",
            output_dir=tmp_path,
        )

        fake_usage = _FakeTokenUsage()
        mock_agent = AsyncMock()
        mock_agent.agenerate = AsyncMock(
            return_value=("```python\nprint('hello')\n```", 100, fake_usage),
        )
        mock_agent.model = "mock:mock-model"

        foo_file = tmp_path / "src" / "foo.py"
        bar_file = tmp_path / "src" / "bar.py"
        foo_file.parent.mkdir(parents=True, exist_ok=True)
        foo_file.write_text("print('foo')", encoding="utf-8")
        bar_file.write_text("print('bar')", encoding="utf-8")

        with (
            patch.object(executor, "_resolve_drafter", return_value=mock_agent),
            patch(
                "startd8.utils.code_extraction.extract_code_from_response",
                return_value="print('hello')",
            ),
            patch.object(
                executor,
                "_write_generated_files",
                return_value=[foo_file, bar_file],
            ),
            patch(
                "startd8.contractors.forensic_log.emit_forensic_log",
            ),
        ):
            success, output = await executor.execute(chunk, {})

        assert success is True
        assert "_missing_targets" not in chunk.metadata

    @pytest.mark.asyncio
    async def test_single_target_no_false_positive(self, tmp_path):
        """Single target file that is produced should not flag."""
        chunk = _make_chunk(file_targets=["src/foo.py"])
        executor = LLMChunkExecutor(
            drafter_agent="mock:mock-model",
            output_dir=tmp_path,
        )

        fake_usage = _FakeTokenUsage()
        mock_agent = AsyncMock()
        mock_agent.agenerate = AsyncMock(
            return_value=("```python\nprint('hello')\n```", 100, fake_usage),
        )
        mock_agent.model = "mock:mock-model"

        written_file = tmp_path / "src" / "foo.py"
        written_file.parent.mkdir(parents=True, exist_ok=True)
        written_file.write_text("print('hello')", encoding="utf-8")

        with (
            patch.object(executor, "_resolve_drafter", return_value=mock_agent),
            patch(
                "startd8.utils.code_extraction.extract_code_from_response",
                return_value="print('hello')",
            ),
            patch.object(
                executor,
                "_write_generated_files",
                return_value=[written_file],
            ),
            patch(
                "startd8.contractors.forensic_log.emit_forensic_log",
            ),
        ):
            success, output = await executor.execute(chunk, {})

        assert success is True
        assert "_missing_targets" not in chunk.metadata

    @pytest.mark.asyncio
    async def test_same_basename_in_different_dirs_detects_missing(self, tmp_path):
        """Path-aware detection should not collapse by basename."""
        chunk = _make_chunk(file_targets=["a/config.py", "b/config.py"])
        executor = LLMChunkExecutor(
            drafter_agent="mock:mock-model",
            output_dir=tmp_path,
        )

        fake_usage = _FakeTokenUsage()
        mock_agent = AsyncMock()
        mock_agent.agenerate = AsyncMock(
            return_value=("```python\nprint('hello')\n```", 100, fake_usage),
        )
        mock_agent.model = "mock:mock-model"

        only_one = tmp_path / "a" / "config.py"
        only_one.parent.mkdir(parents=True, exist_ok=True)
        only_one.write_text("print('hello')", encoding="utf-8")

        with (
            patch.object(executor, "_resolve_drafter", return_value=mock_agent),
            patch(
                "startd8.utils.code_extraction.extract_code_from_response",
                return_value="print('hello')",
            ),
            patch.object(executor, "_write_generated_files", return_value=[only_one]),
            patch("startd8.contractors.forensic_log.emit_forensic_log"),
        ):
            success, output = await executor.execute(chunk, {})

        assert success is True
        assert chunk.metadata["_missing_targets"] == ["b/config.py"]
