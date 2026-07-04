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

import hashlib
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
    _CACHE_SCHEMA_VERSION,
)
from startd8.contractors.protocols import GenerationResult
from startd8.forward_manifest import (
    ContractCategory,
    ContractConfidence,
    ForwardManifest,
    InterfaceContract,
)
from startd8.forward_manifest_validator import ContractViolation

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
        design_doc_sections=[],
        artifact_types_addressed=[],
        file_scope={},
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
            enable_prompt_caching=False,
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
        assert result["prompt_telemetry"]["prompt_chars"] > 0
        mock_agent.generate.assert_called_once()

    def test_review_task_agent_error(self):
        mock_agent = MagicMock()
        mock_agent.generate.side_effect = RuntimeError("API timeout")

        handler = ReviewPhaseHandler()
        handler._review_agent = mock_agent

        task = _make_seed_task(task_id="T-ERR")
        result = handler._review_task(task, "code", {})

        assert result["task_id"] == "T-ERR"
        assert result["score"] is None
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
        assert result["output"]["prompt_telemetry"]["tasks_with_telemetry"] == 2

    def test_review_section_budget_helper_deduplicates(self):
        sections = [
            ("project_context", "## Project Context\nA"),
            ("project_context", "## Project Context\nA"),
            ("design_compliance", "X" * 10000),
        ]
        rendered, diagnostics = ReviewPhaseHandler._apply_review_section_budgets(sections)
        assert diagnostics["dropped_section_count"] >= 1
        assert diagnostics["truncation_count"] >= 1
        assert any("Overflow Summary" in s for s in rendered)

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

    def test_missing_score_defaults_none(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("### Verdict: PASS\nSome text")

        assert parsed["score"] is None
        assert parsed["verdict"] == "PASS"
        assert parsed["passed"] is False  # None score → not passed

    def test_missing_verdict_defaults_fail(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("### Score: 95\nSome text")

        assert parsed["score"] == 95
        assert parsed["verdict"] == "FAIL"
        assert parsed["passed"] is False  # verdict is FAIL

    def test_empty_response(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("")

        assert parsed["score"] is None
        assert parsed["verdict"] == "FAIL"
        assert parsed["passed"] is False

    def test_score_clamped_to_100(self):
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        parsed = handler._parse_review_response("### Score: 150\n### Verdict: PASS")

        assert parsed["score"] == 100
        assert parsed["passed"] is True


# ============================================================================
# Review cache v2 defense-in-depth
# ============================================================================


def _make_v2_review_cache(task_data, source_checksum=None):
    """Build a v2 review cache envelope for testing."""
    return {
        "_cache_meta": {
            "schema_version": _CACHE_SCHEMA_VERSION,
            "created_at": "2026-02-16T00:00:00+00:00",
            "source_checksum": source_checksum,
        },
        "tasks": task_data,
    }


def _make_reviewed_entry(
    task_id="T1",
    score=90,
    verdict="PASS",
    passed=True,
    code_hash=None,
):
    """Build a single cached review entry."""
    entry = {
        "task_id": task_id,
        "score": score,
        "verdict": verdict,
        "passed": passed,
        "cost": 0.005,
        "tokens": {"input": 500, "output": 200},
        "status": "reviewed",
        "strengths": ["Good"],
        "issues": [],
        "suggestions": [],
    }
    if code_hash is not None:
        entry["reviewed_code_hash"] = code_hash
    return entry


class TestReviewCacheDefenseInDepth:
    """Tests for _validate_review_cache() — 4-layer defense-in-depth."""

    def test_v1_cache_rejected(self):
        """Layer 0: flat dict without _cache_meta → rejected."""
        handler = ReviewPhaseHandler()
        saved = {"T1": {"status": "reviewed", "score": 90}}
        result = handler._validate_review_cache(saved, {}, None)
        assert result == {}

    def test_wrong_schema_version_rejected(self):
        """Layer 0: wrong schema_version → rejected."""
        handler = ReviewPhaseHandler()
        saved = {
            "_cache_meta": {
                "schema_version": 99,
                "created_at": "2026-01-01T00:00:00+00:00",
                "source_checksum": None,
            },
            "tasks": {"T1": _make_reviewed_entry()},
        }
        result = handler._validate_review_cache(saved, {}, None)
        assert result == {}

    def test_source_checksum_mismatch_rejects_all(self):
        """Layer 1: source checksum mismatch → reject entire cache."""
        handler = ReviewPhaseHandler()
        saved = _make_v2_review_cache(
            {"T1": _make_reviewed_entry()},
            source_checksum="old_checksum",
        )
        result = handler._validate_review_cache(saved, {}, "new_checksum")
        assert result == {}

    def test_source_checksum_absent_accepted(self):
        """Layer 1: if either checksum is None, skip the check."""
        handler = ReviewPhaseHandler()
        # Cached checksum is None
        saved = _make_v2_review_cache(
            {"T1": _make_reviewed_entry()},
            source_checksum=None,
        )
        result = handler._validate_review_cache(saved, {}, "any_checksum")
        assert "T1" in result

        # Current checksum is None
        saved2 = _make_v2_review_cache(
            {"T1": _make_reviewed_entry()},
            source_checksum="some_checksum",
        )
        result2 = handler._validate_review_cache(saved2, {}, None)
        assert "T1" in result2

    def test_reviewed_entry_accepted(self):
        """Layer 2: entry with status=reviewed passes."""
        handler = ReviewPhaseHandler()
        saved = _make_v2_review_cache({"T1": _make_reviewed_entry()})
        result = handler._validate_review_cache(saved, {}, None)
        assert "T1" in result
        assert result["T1"]["score"] == 90

    def test_non_reviewed_entry_filtered(self):
        """Layer 2: entry with status != reviewed is filtered out."""
        handler = ReviewPhaseHandler()
        entry = _make_reviewed_entry()
        entry["status"] = "review_error"
        saved = _make_v2_review_cache({"T1": entry})
        result = handler._validate_review_cache(saved, {}, None)
        assert "T1" not in result

    def test_code_hash_match_accepted(self, tmp_path):
        """Layer 3: matching code hash → entry accepted."""
        handler = ReviewPhaseHandler()
        f1 = tmp_path / "module.py"
        f1.write_text("def foo(): pass", encoding="utf-8")

        gen_result = GenerationResult(success=True, generated_files=[f1])
        code_hash = ReviewPhaseHandler._hash_generated_code(gen_result)

        entry = _make_reviewed_entry(code_hash=code_hash)
        saved = _make_v2_review_cache({"T1": entry})
        result = handler._validate_review_cache(saved, {"T1": gen_result}, None)
        assert "T1" in result

    def test_code_hash_mismatch_rejected(self, tmp_path):
        """Layer 3: code changed since review → entry rejected."""
        handler = ReviewPhaseHandler()
        f1 = tmp_path / "module.py"
        f1.write_text("def foo(): pass", encoding="utf-8")

        gen_result = GenerationResult(success=True, generated_files=[f1])

        # Cached with a different hash (old code)
        entry = _make_reviewed_entry(code_hash="deadbeef" * 8)
        saved = _make_v2_review_cache({"T1": entry})
        result = handler._validate_review_cache(saved, {"T1": gen_result}, None)
        assert "T1" not in result

    def test_code_hash_absent_accepted(self):
        """Layer 3: no reviewed_code_hash in entry → accepted (additive field)."""
        handler = ReviewPhaseHandler()
        entry = _make_reviewed_entry()  # no code_hash kwarg → field absent
        assert "reviewed_code_hash" not in entry
        saved = _make_v2_review_cache({"T1": entry})
        result = handler._validate_review_cache(saved, {}, None)
        assert "T1" in result

    def test_valid_v2_cache_roundtrip(self, tmp_path):
        """Layers 0-3: fully valid cache returns all entries."""
        handler = ReviewPhaseHandler()
        f1 = tmp_path / "a.py"
        f1.write_text("# task 1", encoding="utf-8")
        f2 = tmp_path / "b.py"
        f2.write_text("# task 2", encoding="utf-8")

        gr1 = GenerationResult(success=True, generated_files=[f1])
        gr2 = GenerationResult(success=True, generated_files=[f2])

        h1 = ReviewPhaseHandler._hash_generated_code(gr1)
        h2 = ReviewPhaseHandler._hash_generated_code(gr2)

        saved = _make_v2_review_cache(
            {
                "T1": _make_reviewed_entry(task_id="T1", code_hash=h1),
                "T2": _make_reviewed_entry(task_id="T2", code_hash=h2),
            },
            source_checksum="abc123",
        )
        result = handler._validate_review_cache(
            saved, {"T1": gr1, "T2": gr2}, "abc123",
        )
        assert set(result.keys()) == {"T1", "T2"}


class TestReviewCacheWriteV2:
    """Tests for v2 envelope written by execute()."""

    def test_write_produces_v2_envelope(self, tmp_path):
        """Written cache has _cache_meta.schema_version and tasks key."""
        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])

        response = _make_review_response(score=90, verdict="PASS")
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(response)

        project_root = tmp_path / "project"
        project_root.mkdir()

        tasks = [_make_seed_task(task_id="T1")]
        ctx = _build_context(tasks, generation_results={"T1": gen_result})
        ctx["project_root"] = str(project_root)

        handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        import json
        cache_path = project_root / ".startd8" / "state" / "review_results.json"
        assert cache_path.exists()
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert "_cache_meta" in data
        assert data["_cache_meta"]["schema_version"] == _CACHE_SCHEMA_VERSION
        assert "created_at" in data["_cache_meta"]
        assert "tasks" in data
        assert "T1" in data["tasks"]

    def test_write_includes_code_hash(self, tmp_path):
        """Per-task reviewed_code_hash matches SHA-256 of generated files."""
        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])
        expected_hash = hashlib.sha256(f1.read_bytes()).hexdigest()

        response = _make_review_response(score=90, verdict="PASS")
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(response)

        project_root = tmp_path / "project"
        project_root.mkdir()

        tasks = [_make_seed_task(task_id="T1")]
        ctx = _build_context(tasks, generation_results={"T1": gen_result})
        ctx["project_root"] = str(project_root)

        handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        import json
        cache_path = project_root / ".startd8" / "state" / "review_results.json"
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["tasks"]["T1"]["reviewed_code_hash"] == expected_hash

    def test_write_includes_source_checksum(self, tmp_path):
        """_cache_meta.source_checksum is taken from context."""
        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])

        response = _make_review_response(score=90, verdict="PASS")
        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80))
        handler._review_agent = _make_mock_agent(response)

        project_root = tmp_path / "project"
        project_root.mkdir()

        tasks = [_make_seed_task(task_id="T1")]
        ctx = _build_context(tasks, generation_results={"T1": gen_result})
        ctx["project_root"] = str(project_root)
        ctx["source_checksum"] = "my_plan_checksum"

        handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        import json
        cache_path = project_root / ".startd8" / "state" / "review_results.json"
        data = json.loads(cache_path.read_text(encoding="utf-8"))
        assert data["_cache_meta"]["source_checksum"] == "my_plan_checksum"


# ============================================================================
# Integration helper: execute() with pre-populated cache
# ============================================================================


def _run_review_execute_with_cache(
    tmp_path: Path,
    tasks: list[SeedTask],
    gen_results: dict[str, GenerationResult],
    cache_data: dict[str, Any] | None = None,
    force_review: bool = False,
    dry_run: bool = False,
    source_checksum: str | None = None,
    review_side_effect=None,
) -> tuple[dict[str, Any], ReviewPhaseHandler]:
    """Set up cache file, mock agent, call execute(), return (result, handler).

    Args:
        tmp_path: pytest tmp_path for project_root.
        tasks: SeedTask list to review.
        gen_results: task_id → GenerationResult mapping.
        cache_data: If provided, written to .startd8/state/review_results.json.
        force_review: Passed through to HandlerConfig.
        dry_run: Passed through to execute().
        source_checksum: Added to context for cache validation.
        review_side_effect: If provided, used as _review_task side_effect.
            Defaults to a lambda returning score=85, PASS for each task.

    Returns:
        (execute_result, handler) tuple.
    """
    import json as _json

    project_root = tmp_path / "project"
    project_root.mkdir(exist_ok=True)

    # Write cache file if provided
    if cache_data is not None:
        state_dir = project_root / ".startd8" / "state"
        state_dir.mkdir(parents=True, exist_ok=True)
        (state_dir / "review_results.json").write_text(
            _json.dumps(cache_data), encoding="utf-8",
        )

    handler = ReviewPhaseHandler(HandlerConfig(
        pass_threshold=80,
        force_review=force_review,
    ))

    # Default review side effect: return PASS with score=85
    if review_side_effect is None:
        def _default_review(task, code, test_results, **kwargs):
            return {
                "task_id": task.task_id,
                "score": 85,
                "verdict": "PASS",
                "passed": True,
                "cost": 0.005,
                "tokens": {"input": 500, "output": 200},
                "status": "reviewed",
                "strengths": ["Good"],
                "issues": [],
                "suggestions": [],
            }
        review_side_effect = _default_review

    ctx = _build_context(tasks, generation_results=gen_results)
    ctx["project_root"] = str(project_root)
    if source_checksum is not None:
        ctx["source_checksum"] = source_checksum

    with patch.object(
        ReviewPhaseHandler, "_review_task", side_effect=review_side_effect,
    ) as mock_review:
        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=dry_run)

    # Attach mock for caller assertions
    handler._mock_review_task = mock_review  # type: ignore[attr-defined]

    return result, handler


# ============================================================================
# Tests: execute()-level integration (cache roundtrip)
# ============================================================================


class TestReviewCacheExecuteIntegration:
    """Full execute() cycle tests verifying cache write → reload behavior.

    Unlike the unit-level TestReviewCacheDefenseInDepth which tests
    _validate_review_cache() in isolation, these tests exercise the
    complete execute() path with _review_task mocked.
    """

    def test_roundtrip_write_then_reload_accepts(self, tmp_path):
        """Execute writes v2 cache → second execute() loads it → cached tasks skip LLM."""
        import json as _json

        f1 = _write_gen_file(tmp_path, "module.py", "def hello(): return 'hi'")
        gen_result = GenerationResult(success=True, generated_files=[f1])
        tasks = [_make_seed_task(task_id="T1")]

        # --- First execute: writes cache ---
        result1, handler1 = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gen_result},
        )
        assert result1["output"]["total_passed"] == 1
        handler1._mock_review_task.assert_called_once()

        # Verify cache was written
        project_root = tmp_path / "project"
        cache_path = project_root / ".startd8" / "state" / "review_results.json"
        assert cache_path.exists()
        cache_data = _json.loads(cache_path.read_text(encoding="utf-8"))
        assert "T1" in cache_data["tasks"]

        # --- Second execute: should use cache, no LLM call ---
        result2, handler2 = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gen_result},
            cache_data=cache_data,
        )
        handler2._mock_review_task.assert_not_called()
        items = result2["output"]["review_items"]
        assert len(items) == 1
        assert items[0]["review_status"] == "cached"
        assert items[0]["passed"] is True

    def test_modified_code_invalidates_cached_entry(self, tmp_path):
        """Execute writes cache → modify file → second execute detects hash mismatch."""
        import json as _json

        f1 = _write_gen_file(tmp_path, "module.py", "def hello(): return 'hi'")
        gen_result = GenerationResult(success=True, generated_files=[f1])
        tasks = [_make_seed_task(task_id="T1")]

        # First execute writes cache
        result1, _ = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gen_result},
        )
        project_root = tmp_path / "project"
        cache_path = project_root / ".startd8" / "state" / "review_results.json"
        cache_data = _json.loads(cache_path.read_text(encoding="utf-8"))

        # Modify the generated file on disk (hash will change)
        f1.write_text("def hello(): return 'MODIFIED'", encoding="utf-8")

        # Second execute: cache hash mismatch → re-reviews
        result2, handler2 = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gen_result},
            cache_data=cache_data,
        )
        handler2._mock_review_task.assert_called_once()
        items = result2["output"]["review_items"]
        assert items[0]["review_status"] == "reviewed"

    def test_partial_cache_hit_mixed_with_fresh(self, tmp_path):
        """Cache has T1 but not T2 → T1 uses cache, T2 gets fresh review."""
        f1 = _write_gen_file(tmp_path, "a.py", "# task 1 code")
        f2 = _write_gen_file(tmp_path, "b.py", "# task 2 code")
        gr1 = GenerationResult(success=True, generated_files=[f1])
        gr2 = GenerationResult(success=True, generated_files=[f2])

        code_hash_t1 = ReviewPhaseHandler._hash_generated_code(gr1)

        cache_data = _make_v2_review_cache(
            {"T1": _make_reviewed_entry(task_id="T1", code_hash=code_hash_t1)},
        )

        tasks = [_make_seed_task(task_id="T1"), _make_seed_task(task_id="T2")]
        result, handler = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gr1, "T2": gr2},
            cache_data=cache_data,
        )

        # T1 should be cached, T2 should be fresh-reviewed
        items = result["output"]["review_items"]
        item_by_id = {it["task_id"]: it for it in items}
        assert item_by_id["T1"]["review_status"] == "cached"
        assert item_by_id["T2"]["review_status"] == "reviewed"

        # _review_task called only for T2
        handler._mock_review_task.assert_called_once()
        call_task = handler._mock_review_task.call_args[0][0]
        assert call_task.task_id == "T2"

        # Cost: only T2's fresh review contributes
        assert result["output"]["total_cost"] == pytest.approx(0.005)
        assert result["cost"] == pytest.approx(0.005)

    def test_force_review_bypasses_cache(self, tmp_path):
        """force_review=True → valid cache on disk is ignored → all tasks fresh."""
        f1 = _write_gen_file(tmp_path, "module.py", "def foo(): pass")
        gr = GenerationResult(success=True, generated_files=[f1])
        code_hash = ReviewPhaseHandler._hash_generated_code(gr)

        cache_data = _make_v2_review_cache(
            {"T1": _make_reviewed_entry(task_id="T1", code_hash=code_hash)},
        )

        tasks = [_make_seed_task(task_id="T1")]
        result, handler = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gr},
            cache_data=cache_data,
            force_review=True,
        )

        # Cache bypassed — _review_task must be called
        handler._mock_review_task.assert_called_once()
        items = result["output"]["review_items"]
        assert items[0]["review_status"] == "reviewed"

    def test_dry_run_does_not_load_or_write_cache(self, tmp_path):
        """dry_run=True → cache file on disk untouched, not loaded."""
        import json as _json

        f1 = _write_gen_file(tmp_path, "module.py", "x = 1")
        gr = GenerationResult(success=True, generated_files=[f1])
        code_hash = ReviewPhaseHandler._hash_generated_code(gr)

        cache_data = _make_v2_review_cache(
            {"T1": _make_reviewed_entry(task_id="T1", code_hash=code_hash)},
        )

        tasks = [_make_seed_task(task_id="T1")]
        result, handler = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gr},
            cache_data=cache_data,
            dry_run=True,
        )

        # Dry run: _review_task not called (dry_run skips review entirely)
        handler._mock_review_task.assert_not_called()
        items = result["output"]["review_items"]
        assert items[0]["review_status"] == "dry_run_pending"

        # Cache file should be unchanged (dry_run doesn't write)
        project_root = tmp_path / "project"
        cache_path = project_root / ".startd8" / "state" / "review_results.json"
        # File should still contain only T1 from the original cache
        current = _json.loads(cache_path.read_text(encoding="utf-8"))
        assert current == cache_data


# ============================================================================
# Tests: _hash_generated_code edge cases
# ============================================================================


class TestReviewCacheHashEdgeCases:
    """Boundary conditions for _hash_generated_code()."""

    def test_hash_with_no_readable_files_returns_none(self, tmp_path):
        """All files missing/unreadable → returns None."""
        nonexistent = tmp_path / "ghost.py"
        gr = GenerationResult(success=True, generated_files=[nonexistent])
        result = ReviewPhaseHandler._hash_generated_code(gr)
        assert result is None

    def test_hash_with_multiple_files_is_order_independent(self, tmp_path):
        """Hash(a, b) == Hash(b, a) — file order does not affect hash."""
        fa = _write_gen_file(tmp_path, "a.py", "aaa")
        fb = _write_gen_file(tmp_path, "b.py", "bbb")

        gr_ab = GenerationResult(success=True, generated_files=[fa, fb])
        gr_ba = GenerationResult(success=True, generated_files=[fb, fa])

        hash_ab = ReviewPhaseHandler._hash_generated_code(gr_ab)
        hash_ba = ReviewPhaseHandler._hash_generated_code(gr_ba)

        assert hash_ab is not None
        assert hash_ba is not None
        assert hash_ab == hash_ba

    def test_hash_with_deleted_file_skips_missing(self, tmp_path):
        """One file exists, one deleted → hash computed from existing only."""
        fa = _write_gen_file(tmp_path, "exists.py", "content")
        fb = _write_gen_file(tmp_path, "will_delete.py", "gone")
        fb.unlink()  # delete it

        gr = GenerationResult(success=True, generated_files=[fa, fb])
        result = ReviewPhaseHandler._hash_generated_code(gr)

        # Should still return a hash (from fa only)
        assert result is not None

        # It should match the hash of just fa
        gr_single = GenerationResult(success=True, generated_files=[fa])
        assert result == ReviewPhaseHandler._hash_generated_code(gr_single)


# ============================================================================
# Tests: GateEmitter interaction with cached reviews
# ============================================================================


class TestReviewCacheGateEmitterInteraction:
    """Verify GateEmitter is only fired for fresh reviews, not cached ones."""

    def test_gate_emitter_not_fired_for_cached_reviews(self, tmp_path):
        """Cached reviews skip GateEmitter; only fresh reviews emit gates."""
        f1 = _write_gen_file(tmp_path, "a.py", "# task 1")
        f2 = _write_gen_file(tmp_path, "b.py", "# task 2")
        gr1 = GenerationResult(success=True, generated_files=[f1])
        gr2 = GenerationResult(success=True, generated_files=[f2])

        code_hash_t1 = ReviewPhaseHandler._hash_generated_code(gr1)
        cache_data = _make_v2_review_cache(
            {"T1": _make_reviewed_entry(task_id="T1", code_hash=code_hash_t1)},
        )

        tasks = [_make_seed_task(task_id="T1"), _make_seed_task(task_id="T2")]

        with patch(
            "startd8.contractors.context_seed.phases.review.GateEmitter"
        ) as mock_gate_cls:
            result, handler = _run_review_execute_with_cache(
                tmp_path, tasks, {"T1": gr1, "T2": gr2},
                cache_data=cache_data,
            )

        # GateEmitter.from_review_result should be called only for T2 (fresh)
        calls = mock_gate_cls.from_review_result.call_args_list
        assert len(calls) == 1
        assert calls[0][1]["task_id"] == "T2"


# ============================================================================
# Tests: Fix 5 — resumed flag and task counts in REVIEW metadata
# ============================================================================


class TestReviewResumeMetadata:
    """Verify REVIEW returns resumed flag and cached/fresh task counts."""

    def test_all_cached_sets_resumed_true(self, tmp_path):
        """When all tasks use cache, metadata.resumed=True."""
        f1 = _write_gen_file(tmp_path, "a.py", "# task 1")
        gr1 = GenerationResult(success=True, generated_files=[f1])
        code_hash = ReviewPhaseHandler._hash_generated_code(gr1)

        cache_data = _make_v2_review_cache(
            {"T1": _make_reviewed_entry(task_id="T1", code_hash=code_hash)},
        )

        tasks = [_make_seed_task(task_id="T1")]
        result, _ = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gr1},
            cache_data=cache_data,
        )

        assert result["metadata"]["resumed"] is True
        assert result["metadata"]["cached_task_count"] == 1
        assert result["metadata"]["fresh_task_count"] == 0

    def test_all_fresh_sets_resumed_false(self, tmp_path):
        """When no tasks use cache, metadata.resumed=False."""
        f1 = _write_gen_file(tmp_path, "a.py", "# task 1")
        gr1 = GenerationResult(success=True, generated_files=[f1])

        tasks = [_make_seed_task(task_id="T1")]
        result, _ = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gr1},
        )

        assert result["metadata"]["resumed"] is False
        assert result["metadata"]["cached_task_count"] == 0
        assert result["metadata"]["fresh_task_count"] == 1

    def test_mixed_cached_and_fresh(self, tmp_path):
        """Mix of cached and fresh tasks reports correct counts."""
        f1 = _write_gen_file(tmp_path, "a.py", "# task 1")
        f2 = _write_gen_file(tmp_path, "b.py", "# task 2")
        gr1 = GenerationResult(success=True, generated_files=[f1])
        gr2 = GenerationResult(success=True, generated_files=[f2])

        code_hash_t1 = ReviewPhaseHandler._hash_generated_code(gr1)
        cache_data = _make_v2_review_cache(
            {"T1": _make_reviewed_entry(task_id="T1", code_hash=code_hash_t1)},
        )

        tasks = [_make_seed_task(task_id="T1"), _make_seed_task(task_id="T2")]
        result, _ = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gr1, "T2": gr2},
            cache_data=cache_data,
        )

        assert result["metadata"]["resumed"] is True
        assert result["metadata"]["cached_task_count"] == 1
        assert result["metadata"]["fresh_task_count"] == 1

    def test_dry_run_resumed_false(self):
        """Dry-run always reports resumed=False."""
        tasks = [_make_seed_task(task_id="T1")]
        handler = ReviewPhaseHandler()
        ctx = _build_context(tasks)
        result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=True)

        assert result["metadata"]["resumed"] is False
        assert result["metadata"]["cached_task_count"] == 0
        assert result["metadata"]["fresh_task_count"] == 0


# ============================================================================
# Tests: Fix 3 — broadened exception handling in REVIEW cache loading
# ============================================================================


class TestReviewCacheExceptionHandling:
    """Verify corrupt/inaccessible REVIEW cache files gracefully fall through."""

    def test_corrupt_binary_cache_falls_through(self, tmp_path):
        """Binary garbage in review cache file doesn't crash."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        state_dir = project_root / ".startd8" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "review_results.json").write_bytes(b"\x80\x81\xff\xfe")

        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])

        tasks = [_make_seed_task(task_id="T1")]
        result, handler = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gen_result},
            # Don't pass cache_data — file already written manually
        )

        # Should have fallen through to fresh review (not crashed)
        handler._mock_review_task.assert_called_once()
        assert result["metadata"]["resumed"] is False

    def test_malformed_json_cache_falls_through(self, tmp_path):
        """Invalid JSON in review cache file falls through to fresh review."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        state_dir = project_root / ".startd8" / "state"
        state_dir.mkdir(parents=True)
        (state_dir / "review_results.json").write_text("{not valid json!")

        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])

        tasks = [_make_seed_task(task_id="T1")]
        result, handler = _run_review_execute_with_cache(
            tmp_path, tasks, {"T1": gen_result},
        )

        handler._mock_review_task.assert_called_once()
        assert result["metadata"]["resumed"] is False


# ============================================================================
# Tests: REVIEW cache write failure is non-fatal
# ============================================================================


class TestReviewCacheWriteFailureNonFatal:
    """Verify REVIEW cache write failures don't crash the phase."""

    def test_write_failure_is_non_fatal(self, tmp_path):
        """When atomic_write_json raises, REVIEW completes successfully."""
        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])

        tasks = [_make_seed_task(task_id="T1")]

        with patch(
            "startd8.contractors.context_seed.phases.review.atomic_write_json",
            side_effect=OSError("disk full"),
        ):
            result, handler = _run_review_execute_with_cache(
                tmp_path, tasks, {"T1": gen_result},
            )

        # Phase should complete despite write failure
        handler._mock_review_task.assert_called_once()
        assert result["output"]["total_passed"] == 1


# ============================================================================
# Tests: Phase 5 - ForwardManifest Validator Integration
# ============================================================================


class TestReviewForwardManifestIntegration:
    """Verify validate_forward_manifest integration into execute() stringently fails reviews."""

    def test_forward_manifest_error_yields_fail_verdict_and_blocks(self, tmp_path):
        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])

        tasks = [_make_seed_task(task_id="T1")]

        # Mock a successful default review response
        response = _make_review_response(score=90, verdict="PASS")

        # Create a mock manifest and registry
        manifest = ForwardManifest(
            contracts=[
                InterfaceContract(
                    contract_id="C1",
                    category=ContractCategory.FUNCTION_NAME,
                    confidence=ContractConfidence.EXPLICIT,
                    description="Requires init",
                    binding_text="def __init__(self)",
                )
            ]
        )
        registry = MagicMock()

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80, manifest_consumption_enabled=True))
        handler._review_agent = _make_mock_agent(response)
        handler.config.manifest_registry = registry

        ctx = _build_context(tasks, {"T1": gen_result})
        ctx["forward_manifest"] = manifest

        # Force the validator to return an error violation
        violation = ContractViolation(
            contract_id="C1",
            violation_type="Missing Element",
            expected="def __init__(self)",
            actual=None,
            severity="error"
        )

        with patch(
            "startd8.forward_manifest_validator.validate_forward_manifest",
            return_value=[violation],
        ) as mock_validator:
            result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        assert mock_validator.call_count >= 1
        assert all(call.args == (manifest, registry) for call in mock_validator.call_args_list)

        items = result["output"]["review_items"]
        assert len(items) == 1
        review = items[0]

        # The LLM verdict was PASS, but the forward manifest explicitly failed it
        assert review["passed"] is False
        assert review["verdict"] == "FAIL"

        # Check if the issue was injected properly
        issues = review.get("issues", [])
        assert any("[BLOCKING] Contract Violation" in issue and "C1" in issue for issue in issues)

    def test_forward_manifest_warning_advises_does_not_fail(self, tmp_path):
        f1 = _write_gen_file(tmp_path, "code.py", "x = 1")
        gen_result = GenerationResult(success=True, generated_files=[f1])

        tasks = [_make_seed_task(task_id="T1")]

        response = _make_review_response(score=90, verdict="PASS")
        manifest = ForwardManifest(contracts=[])
        registry = MagicMock()

        handler = ReviewPhaseHandler(HandlerConfig(pass_threshold=80, manifest_consumption_enabled=True))
        handler._review_agent = _make_mock_agent(response)
        handler.config.manifest_registry = registry

        ctx = _build_context(tasks, {"T1": gen_result})
        ctx["forward_manifest"] = manifest

        violation = ContractViolation(
            contract_id="W1",
            violation_type="Advisory Mismatch",
            expected="Should use factory",
            actual=None,
            severity="warning",
        )

        with patch(
            "startd8.forward_manifest_validator.validate_forward_manifest",
            return_value=[violation],
        ) as mock_validator:
            result = handler.execute(WorkflowPhase.REVIEW, ctx, dry_run=False)

        assert mock_validator.call_count >= 1
        assert all(call.args == (manifest, registry) for call in mock_validator.call_args_list)

        items = result["output"]["review_items"]
        assert len(items) == 1
        review = items[0]

        # Must not have mutated PASS/FAIL state
        assert review["passed"] is True
        assert review["verdict"] == "PASS"

        issues = review.get("issues", [])
        assert any("[MINOR] Contract Advisory" in issue and "W1" in issue for issue in issues)
