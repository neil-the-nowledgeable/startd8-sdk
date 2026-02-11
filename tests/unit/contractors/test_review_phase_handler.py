"""Tests for ReviewPhaseHandler wiring.

Covers:
- Agent resolution and caching
- LLM review call (success / error)
- Pass / fail verdict logic
- Dry-run mode
- Skip when no generation result
- Reading generated files
- Cost aggregation
- _parse_review_response edge cases
- File I/O error handling (missing, unreadable, binary)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from startd8.contractors.context_seed_handlers import (
    HandlerConfig,
    ReviewPhaseHandler,
    SeedTask,
    WorkflowPhase,
)
from startd8.contractors.protocols import GenerationResult


# ============================================================================
# Helpers
# ============================================================================


def _make_seed_task(
    task_id: str = "T1",
    title: str = "Implement feature",
    description: str = "Build the feature module",
    target_files: list[str] | None = None,
    depends_on: list[str] | None = None,
    env_checks: list[dict[str, Any]] | None = None,
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
        environment_checks=env_checks or [],
        prompt_constraints=prompt_constraints or ["Use type hints"],
        post_generation_validators=["ruff", "mypy"],
        available_siblings=[],
        existing_content_hash=None,
    )


def _make_token_usage(input_tokens: int = 500, output_tokens: int = 200, cost: float = 0.005):
    """Create a lightweight TokenUsage stand-in.

    Uses SimpleNamespace so hasattr checks work correctly with
    token_usage_cost/input/output utilities — attributes exist only
    if explicitly set, matching real TokenUsage behaviour.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        input=input_tokens,
        output=output_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        cost_estimate=cost,
    )


def _make_review_response(score: int = 85, verdict: str = "PASS") -> str:
    return (
        f"### Score: {score}\n\n"
        f"### Verdict: {verdict}\n\n"
        "### Strengths\n- Good structure\n\n"
        "### Issues\n- [severity: MINOR] Needs docstring\n\n"
        "### Suggestions\n- Add logging\n"
    )


def _make_mock_agent(response_text: str = "", time_ms: int = 1200, token_usage=None):
    """Create a mock agent with .generate()."""
    agent = MagicMock()
    if token_usage is None:
        token_usage = _make_token_usage()
    agent.generate.return_value = (response_text, time_ms, token_usage)
    return agent


def _build_context(tasks: list[SeedTask], generation_results=None, test_results=None):
    """Build execute() context dict from tasks."""
    ctx: dict[str, Any] = {"enriched_seed": {"tasks": []}}
    ctx["tasks"] = tasks
    if generation_results is not None:
        ctx["generation_results"] = generation_results
    if test_results is not None:
        ctx["test_results"] = test_results
    return ctx


def _write_gen_file(tmp_path: Path, name: str, content: str) -> Path:
    """Write a temp file and return its Path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ============================================================================
# Tests
# ============================================================================


class TestResolveReviewAgent:
    """_resolve_review_agent caching."""

    @patch("startd8.utils.agent_resolution.resolve_agent_spec")
    def test_resolve_review_agent_cached(self, mock_resolve):
        mock_agent = MagicMock()
        mock_resolve.return_value = mock_agent

        handler = ReviewPhaseHandler(HandlerConfig(review_temperature=0.1))
        a1 = handler._resolve_review_agent()
        a2 = handler._resolve_review_agent()

        assert a1 is a2
        assert a1 is mock_agent
        mock_resolve.assert_called_once_with(
            handler.config.lead_agent,
            name="context-seed-reviewer",
            temperature=0.1,
        )


class TestReviewTask:
    """_review_task success and error paths."""

    def test_review_task_success(self):
        response = _make_review_response(score=90, verdict="PASS")
        token_usage = _make_token_usage(input_tokens=600, output_tokens=300, cost=0.008)
        mock_agent = _make_mock_agent(response, time_ms=1500, token_usage=token_usage)

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = mock_agent

        task = _make_seed_task()
        result = handler._review_task(task, "def foo(): pass", {})

        assert result["task_id"] == "T1"
        assert result["score"] == 90
        assert result["verdict"] == "PASS"
        assert result["passed"] is True
        assert result["cost"] == pytest.approx(0.008)
        assert result["tokens"]["input"] == 600
        assert result["tokens"]["output"] == 300
        mock_agent.generate.assert_called_once()

    def test_review_task_agent_error(self):
        mock_agent = MagicMock()
        mock_agent.generate.side_effect = RuntimeError("API timeout")

        handler = ReviewPhaseHandler()
        handler._review_agent = mock_agent

        task = _make_seed_task(task_id="T-ERR")
        result = handler._review_task(task, "code", {})

        assert result["task_id"] == "T-ERR"
        assert result["score"] == 0
        assert result["verdict"] == "ERROR"
        assert result["passed"] is False
        assert result["cost"] == 0.0
        assert "API timeout" in result["error"]

    def test_review_task_pass_verdict(self):
        response = _make_review_response(score=85, verdict="PASS")
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(response)

        result = handler._review_task(_make_seed_task(), "code", {})
        assert result["passed"] is True
        assert result["verdict"] == "PASS"

    def test_review_task_fail_verdict(self):
        response = _make_review_response(score=60, verdict="FAIL")
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(response)

        result = handler._review_task(_make_seed_task(), "code", {})
        assert result["passed"] is False
        assert result["verdict"] == "FAIL"
        assert result["score"] == 60


class TestExecute:
    """execute() integration paths."""

    def test_execute_dry_run(self):
        handler = ReviewPhaseHandler()
        tasks = [_make_seed_task(task_id="T1"), _make_seed_task(task_id="T2")]
        ctx = _build_context(tasks)

        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=True)

        items = result["output"]["review_items"]
        assert len(items) == 2
        assert all(r["review_status"] == "dry_run_pending" for r in items)
        assert result["cost"] == 0.0

    def test_execute_skip_no_generation(self):
        handler = ReviewPhaseHandler()
        tasks = [_make_seed_task(task_id="T1")]
        ctx = _build_context(tasks, generation_results={})

        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        items = result["output"]["review_items"]
        assert len(items) == 1
        assert items[0]["review_status"] == "skipped_no_generation"

    def test_execute_reads_generated_files(self, tmp_path):
        f1 = _write_gen_file(tmp_path, "module.py", "def hello(): return 'hi'")
        f2 = _write_gen_file(tmp_path, "utils.py", "import os")

        gen_result = GenerationResult(
            success=True,
            generated_files=[f1, f2],
        )

        response = _make_review_response(score=92, verdict="PASS")
        mock_agent = _make_mock_agent(response)

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = mock_agent

        tasks = [_make_seed_task(task_id="T1")]
        ctx = _build_context(tasks, generation_results={"T1": gen_result})

        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        # Verify the prompt sent to the agent contains file contents
        call_args = mock_agent.generate.call_args[0][0]
        assert "def hello()" in call_args
        assert "import os" in call_args
        assert "# File: module.py" in call_args

        items = result["output"]["review_items"]
        assert len(items) == 1
        assert items[0]["review_status"] == "reviewed"
        assert items[0]["passed"] is True

    def test_execute_cost_aggregation(self, tmp_path):
        # Each task needs a real generated file so the review path runs
        f1 = _write_gen_file(tmp_path, "a.py", "# task 1 code")
        f2 = _write_gen_file(tmp_path, "b.py", "# task 2 code")

        tu1 = _make_token_usage(cost=0.01)
        tu2 = _make_token_usage(cost=0.02)
        responses = [
            (_make_review_response(90, "PASS"), 100, tu1),
            (_make_review_response(70, "FAIL"), 100, tu2),
        ]

        mock_agent = MagicMock()
        mock_agent.generate.side_effect = responses

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = mock_agent

        tasks = [_make_seed_task(task_id="T1"), _make_seed_task(task_id="T2")]
        gen_results = {
            "T1": GenerationResult(success=True, generated_files=[f1]),
            "T2": GenerationResult(success=True, generated_files=[f2]),
        }
        ctx = _build_context(tasks, generation_results=gen_results)

        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        assert result["output"]["total_cost"] == pytest.approx(0.03)
        assert result["output"]["total_passed"] == 1
        assert result["output"]["total_failed"] == 1

    def test_execute_handles_missing_generated_file(self, tmp_path):
        """generated_files contains a Path that doesn't exist on disk.

        The handler should skip the missing file silently.  If ALL files
        are missing, the task is marked ``skipped_no_code``.
        """
        nonexistent = tmp_path / "does_not_exist.py"
        assert not nonexistent.exists()

        gen_result = GenerationResult(
            success=True,
            generated_files=[nonexistent],
        )

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(
            _make_review_response(score=90, verdict="PASS"),
        )

        tasks = [_make_seed_task(task_id="T-MISS")]
        ctx = _build_context(tasks, generation_results={"T-MISS": gen_result})

        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        items = result["output"]["review_items"]
        assert len(items) == 1
        # No readable code => skipped_no_code
        assert items[0]["review_status"] == "skipped_no_code"
        # Agent should NOT have been called
        handler._review_agent.generate.assert_not_called()

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod not reliable on Windows")
    def test_execute_handles_unreadable_file(self, tmp_path):
        """File exists but is not readable (permission denied).

        The handler should log a warning and continue.  If this is the
        only generated file the task is marked ``skipped_no_code``.
        """
        unreadable = _write_gen_file(tmp_path, "secret.py", "x = 42")
        os.chmod(unreadable, 0o000)

        gen_result = GenerationResult(
            success=True,
            generated_files=[unreadable],
        )

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(
            _make_review_response(score=90, verdict="PASS"),
        )

        tasks = [_make_seed_task(task_id="T-PERM")]
        ctx = _build_context(tasks, generation_results={"T-PERM": gen_result})

        try:
            result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

            items = result["output"]["review_items"]
            assert len(items) == 1
            # File unreadable => no code => skipped
            assert items[0]["review_status"] == "skipped_no_code"
            handler._review_agent.generate.assert_not_called()
        finally:
            # Restore permissions so pytest can clean up tmp_path
            os.chmod(unreadable, 0o644)

    def test_execute_handles_binary_file_encoding_error(self, tmp_path):
        """File contains invalid UTF-8 bytes.

        The handler catches ``UnicodeDecodeError`` and skips the file
        gracefully.  If this is the only generated file the task is
        marked ``skipped_no_code``.
        """
        binary_file = tmp_path / "binary.py"
        # Write bytes that are not valid UTF-8
        binary_file.write_bytes(b"\x80\x81\x82\xff\xfe\xfd")

        gen_result = GenerationResult(
            success=True,
            generated_files=[binary_file],
        )

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(
            _make_review_response(score=90, verdict="PASS"),
        )

        tasks = [_make_seed_task(task_id="T-BIN")]
        ctx = _build_context(tasks, generation_results={"T-BIN": gen_result})

        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        items = result["output"]["review_items"]
        assert len(items) == 1
        # Decode error => no code => skipped
        assert items[0]["review_status"] == "skipped_no_code"
        handler._review_agent.generate.assert_not_called()


class TestParseReviewResponse:
    """_parse_review_response edge cases."""

    def test_full_response(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        response = _make_review_response(score=85, verdict="PASS")
        parsed = handler._parse_review_response(response)

        assert parsed["score"] == 85
        assert parsed["verdict"] == "PASS"
        assert parsed["passed"] is True
        assert "Good structure" in parsed["strengths"]
        assert any("Needs docstring" in i for i in parsed["issues"])

    def test_missing_score_defaults_zero(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("### Verdict: PASS\nSome text")

        assert parsed["score"] == 0
        assert parsed["verdict"] == "PASS"
        assert parsed["passed"] is False  # score 0 < threshold 80

    def test_missing_verdict_defaults_fail(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("### Score: 95\nSome text")

        assert parsed["score"] == 95
        assert parsed["verdict"] == "FAIL"
        assert parsed["passed"] is False  # verdict is FAIL

    def test_empty_response(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("")

        assert parsed["score"] == 0
        assert parsed["verdict"] == "FAIL"
        assert parsed["passed"] is False

    def test_score_clamped_to_100(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("### Score: 150\n### Verdict: PASS")

        assert parsed["score"] == 100
        assert parsed["passed"] is True
