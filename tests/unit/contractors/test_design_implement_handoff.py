"""Tests for Defense-in-Depth DESIGN → IMPLEMENT handoff.

Covers five layers:
- Layer 1: Structural validation (DP-2 empty design normalization, scope logging)
- Layer 2: Prompt authority reframing (AUTHORITATIVE framing, scope metrics, demotion)
- Layer 3: Post-generation scope validation (mismatch detection)
- Layer 4: Design-aware REVIEW (design compliance injection, truncation)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.context_seed_handlers import (
    HandlerConfig,
    ImplementPhaseHandler,
    ReviewPhaseHandler,
    SeedTask,
)
from startd8.contractors.artisan_phases.development import (
    DevelopmentChunk,
    LeadContractorChunkExecutor,
)


# ============================================================================
# Helpers
# ============================================================================


def _make_seed_task(
    task_id: str = "T1",
    title: str = "Implement feature",
    description: str = "Build the feature module",
    target_files: list[str] | None = None,
    depends_on: list[str] | None = None,
    prompt_constraints: list[str] | None = None,
    domain: str = "backend",
) -> SeedTask:
    return SeedTask(
        task_id=task_id,
        title=title,
        task_type="task",
        story_points=3,
        priority="high",
        labels=["feature"],
        depends_on=depends_on or [],
        description=description,
        target_files=target_files or ["src/feature.py"],
        estimated_loc=100,
        feature_id="F1",
        domain=domain,
        domain_reasoning="Backend logic",
        environment_checks=[],
        prompt_constraints=prompt_constraints or [],
        post_generation_validators=[],
        available_siblings=[],
        existing_content_hash=None,
        design_doc_sections=[],
        artifact_types_addressed=[],
        file_scope={},
    )


def _make_chunk(
    chunk_id: str = "task-1",
    description: str = "Implement feature X",
    file_targets: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> DevelopmentChunk:
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
            "prompt_constraints": [],
            "environment_checks": [],
            "post_generation_validators": [],
            "title": "Feature X",
        },
    )


SUBSTANTIAL_DESIGN_DOC = """## Overview
This module implements the Prometheus alerting rules for the observability stack.

## Rule Group 1: Availability Alerts
- Service down alert (5m threshold)
- Error rate > 5% alert (10m window)
- Latency P99 > 500ms

## Rule Group 2: Capacity Alerts
- Disk usage > 80%
- Memory pressure > 90%
- CPU saturation > 75%

## Rule Group 3: Recording Rules
- record: namespace:http_requests_total:rate5m
- record: namespace:http_errors_total:rate5m
- record: namespace:http_duration_seconds:p99

## Rule Group 4: SLO Burn Rate
- 1h burn rate > 14.4x budget
- 6h burn rate > 6x budget
- 3d burn rate > 1x budget

## Rule Group 5: Dependency Health
- Upstream timeout rate
- Circuit breaker open count
- Database connection pool exhaustion

## Rule Group 6: Metric Guards
- Stale metric detection (no data for 15m)
- Cardinality explosion guard
- Label consistency checks
""".strip()


# ============================================================================
# Layer 1: Structural Validation
# ============================================================================


class TestLayer1StructuralValidation:
    """DP-2: no silent defaults at DESIGN→IMPLEMENT boundary."""

    def test_empty_design_doc_normalized_to_none(self, caplog):
        """Status 'designed' + empty doc → None + WARNING log."""
        task = _make_seed_task(task_id="PI-001e")
        design_results = {
            "PI-001e": {
                "status": "designed",
                "design_document": "   ",  # trivial whitespace
            },
        }

        with caplog.at_level(logging.WARNING):
            chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
                [task],
                design_results=design_results,
            )

        assert len(chunks) == 1
        assert chunks[0].metadata.get("design_document") is None
        assert any(
            "DESIGN→IMPLEMENT boundary" in r.message
            and "empty/trivial" in r.message
            and "DP-2" in r.message
            for r in caplog.records
        )

    def test_substantial_design_doc_passes_through(self, caplog):
        """Valid design doc preserved unchanged with INFO log."""
        task = _make_seed_task(task_id="PI-001e")
        design_results = {
            "PI-001e": {
                "status": "designed",
                "design_document": SUBSTANTIAL_DESIGN_DOC,
            },
        }

        with caplog.at_level(logging.INFO):
            chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
                [task],
                design_results=design_results,
            )

        assert len(chunks) == 1
        assert chunks[0].metadata["design_document"] == SUBSTANTIAL_DESIGN_DOC
        assert any(
            "DESIGN→IMPLEMENT boundary" in r.message
            and "propagated" in r.message
            for r in caplog.records
        )
        # Aggregate log
        assert any(
            "DESIGN→IMPLEMENT handoff" in r.message
            and "1/1 tasks have design documents" in r.message
            for r in caplog.records
        )

    def test_no_design_status_skips_validation(self, caplog):
        """Tasks without design status are unaffected."""
        task = _make_seed_task(task_id="PI-001e")
        design_results = {}

        with caplog.at_level(logging.WARNING):
            chunks, skipped = ImplementPhaseHandler._tasks_to_chunks(
                [task],
                design_results=design_results,
            )

        assert len(chunks) == 1
        assert chunks[0].metadata.get("design_document") is None
        # No boundary warning for tasks without design status
        assert not any(
            "DESIGN→IMPLEMENT boundary" in r.message
            and "empty/trivial" in r.message
            for r in caplog.records
        )


# ============================================================================
# Layer 2: Prompt Authority Reframing
# ============================================================================


class TestLayer2PromptAuthority:
    """Design doc framed as AUTHORITATIVE; task summary demoted to label."""

    def _make_executor(self):
        config = MagicMock()
        config.lead_agent = "anthropic:test"
        config.max_tokens = None
        config.enable_prompt_caching = False
        executor = LeadContractorChunkExecutor.__new__(LeadContractorChunkExecutor)
        executor.config = config
        executor.logger = logging.getLogger("test")
        executor._generator = None
        return executor

    def test_authoritative_framing_with_design(self):
        """'AUTHORITATIVE' and 'OVERRIDES' appear in task description."""
        executor = self._make_executor()
        chunk = _make_chunk(metadata={
            "feature_id": "F1",
            "domain": "backend",
            "estimated_loc": 100,
            "prompt_constraints": [],
            "environment_checks": [],
            "post_generation_validators": [],
            "title": "Feature X",
            "design_document": SUBSTANTIAL_DESIGN_DOC,
        })
        desc = executor._build_task_description(chunk, {})
        assert "AUTHORITATIVE" in desc
        assert "OVERRIDES" in desc

    def test_design_scope_metrics_in_prompt(self):
        """Line/section counts appear in prompt."""
        executor = self._make_executor()
        chunk = _make_chunk(metadata={
            "feature_id": "F1",
            "domain": "backend",
            "estimated_loc": 100,
            "prompt_constraints": [],
            "environment_checks": [],
            "post_generation_validators": [],
            "title": "Feature X",
            "design_document": SUBSTANTIAL_DESIGN_DOC,
        })
        desc = executor._build_task_description(chunk, {})

        design_lines = len(SUBSTANTIAL_DESIGN_DOC.strip().splitlines())
        design_sections = sum(
            1 for line in SUBSTANTIAL_DESIGN_DOC.splitlines()
            if line.strip().startswith("##")
        )
        assert f"{design_lines} lines" in desc
        assert f"{design_sections} sections" in desc

    def test_task_summary_demoted_with_design(self):
        """'label only' appears when design is present."""
        executor = self._make_executor()
        chunk = _make_chunk(metadata={
            "feature_id": "F1",
            "domain": "backend",
            "estimated_loc": 100,
            "prompt_constraints": [],
            "environment_checks": [],
            "post_generation_validators": [],
            "title": "Feature X",
            "design_document": SUBSTANTIAL_DESIGN_DOC,
        })
        desc = executor._build_task_description(chunk, {})
        assert "label only" in desc

    def test_no_design_preserves_original_format(self):
        """No design = original format (no AUTHORITATIVE framing)."""
        executor = self._make_executor()
        chunk = _make_chunk(metadata={
            "feature_id": "F1",
            "domain": "backend",
            "estimated_loc": 100,
            "prompt_constraints": [],
            "environment_checks": [],
            "post_generation_validators": [],
            "title": "Feature X",
        })
        desc = executor._build_task_description(chunk, {})
        assert "AUTHORITATIVE" not in desc
        assert "OVERRIDES" not in desc
        assert "label only" not in desc
        assert chunk.description in desc


# ============================================================================
# Layer 3: Post-generation Scope Validation
# ============================================================================


class TestLayer3ScopeValidation:
    """Detect scope mismatch between design and output."""

    @pytest.mark.asyncio
    async def test_scope_mismatch_detection(self, tmp_path, caplog):
        """27 output lines vs 327 design lines → WARNING + metadata tag."""
        # Create a small output file (simulating 27-line boilerplate)
        output_file = tmp_path / "rules.yaml"
        output_file.write_text("\n".join(f"line {i}" for i in range(27)))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.generated_files = [output_file]
        mock_result.cost_usd = 0.05
        mock_result.input_tokens = 1000
        mock_result.output_tokens = 500
        mock_result.model = "anthropic:test"
        mock_result.iterations = 1
        mock_result.error = None

        # Design doc with ~100 lines — 27/100 = 0.27 which is > 0.25
        # so use 200 lines to ensure ratio < 0.25
        big_design = "\n".join(f"## Section {i}\nRule definition {i}" for i in range(100))

        chunk = _make_chunk(
            file_targets=[str(output_file)],
            metadata={
                "feature_id": "F1",
                "domain": "backend",
                "estimated_loc": 100,
                "prompt_constraints": [],
                "environment_checks": [],
                "post_generation_validators": [],
                "title": "Feature X",
                "design_document": big_design,
            },
        )

        mock_gen = MagicMock()
        mock_gen.generate.return_value = mock_result
        executor = LeadContractorChunkExecutor(output_dir=tmp_path)
        executor._generator = mock_gen

        with caplog.at_level(logging.WARNING):
            success, output = await executor.execute(chunk, {})

        assert success
        assert "_scope_mismatch" in chunk.metadata
        mismatch = chunk.metadata["_scope_mismatch"]
        assert mismatch["output_lines"] == 27
        assert mismatch["ratio"] < 0.25
        assert any("SCOPE MISMATCH" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_no_scope_mismatch_when_adequate(self, tmp_path):
        """150 output lines vs 100 design lines → no warning."""
        output_file = tmp_path / "rules.yaml"
        output_file.write_text("\n".join(f"line {i}" for i in range(150)))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.generated_files = [output_file]
        mock_result.cost_usd = 0.05
        mock_result.input_tokens = 1000
        mock_result.output_tokens = 500
        mock_result.model = "anthropic:test"
        mock_result.iterations = 1
        mock_result.error = None

        design = "\n".join(f"## Section {i}\nContent" for i in range(50))

        chunk = _make_chunk(
            file_targets=[str(output_file)],
            metadata={
                "feature_id": "F1",
                "domain": "backend",
                "estimated_loc": 100,
                "prompt_constraints": [],
                "environment_checks": [],
                "post_generation_validators": [],
                "title": "Feature X",
                "design_document": design,
            },
        )

        mock_gen = MagicMock()
        mock_gen.generate.return_value = mock_result
        executor = LeadContractorChunkExecutor(output_dir=tmp_path)
        executor._generator = mock_gen

        success, _ = await executor.execute(chunk, {})

        assert success
        assert "_scope_mismatch" not in chunk.metadata


# ============================================================================
# Layer 4: Design-Aware REVIEW
# ============================================================================


class TestLayer4DesignAwareReview:
    """Design document injected into review prompt for compliance."""

    def _make_handler(self):
        config = HandlerConfig(lead_agent="anthropic:test")
        handler = ReviewPhaseHandler.__new__(ReviewPhaseHandler)
        handler.config = config
        handler._review_agent = None
        return handler

    def test_review_prompt_includes_design_compliance(self):
        """Design doc injected into review prompt."""
        handler = self._make_handler()
        task = _make_seed_task()

        prompt = handler._build_review_prompt(
            task,
            generated_code="def hello(): pass",
            test_results={},
            design_document=SUBSTANTIAL_DESIGN_DOC,
        )

        assert "## Design Document (from DESIGN phase" in prompt
        assert "You MUST check that the implementation covers ALL sections" in prompt
        # Ensure it appears BEFORE Review Instructions
        design_idx = prompt.index("## Design Document")
        review_idx = prompt.index("## Review Instructions")
        assert design_idx < review_idx

    def test_review_prompt_without_design_unchanged(self):
        """No design = original prompt format."""
        handler = self._make_handler()
        task = _make_seed_task()

        prompt = handler._build_review_prompt(
            task,
            generated_code="def hello(): pass",
            test_results={},
        )

        assert "## Design Document" not in prompt
        assert "## Review Instructions" in prompt

    def test_review_design_truncated_at_8000(self):
        """Large design doc capped at 8000 chars."""
        handler = self._make_handler()
        task = _make_seed_task()

        huge_design = "x" * 12000

        prompt = handler._build_review_prompt(
            task,
            generated_code="def hello(): pass",
            test_results={},
            design_document=huge_design,
        )

        assert "chars truncated" in prompt
        # The full 12000-char design should NOT appear
        assert "x" * 12000 not in prompt
        # But the first 8000 should
        assert "x" * 8000 in prompt
