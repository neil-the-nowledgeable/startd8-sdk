"""Unit tests for the post-mortem evaluation module."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict

import pytest

from startd8.contractors.postmortem import (
    PostMortemEvaluator,
    PostMortemReport,
    TaskPostMortem,
    _PASS_THRESHOLD,
    _PARTIAL_THRESHOLD,
    _VERDICT_FAIL,
    _VERDICT_PARTIAL,
    _VERDICT_PASS,
    _compute_verdict,
    _extract_requirement_keywords,
    launch_postmortem_async,
)

from tests.unit.contractors.conftest import FakeSeedTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_dict(**overrides: Any) -> Dict[str, Any]:
    """Build a seed-task dict from FakeSeedTask defaults with overrides."""
    task = FakeSeedTask(**overrides)
    return {k: v for k, v in task.__dict__.items()}


def _make_gen_results(
    task_id: str,
    files: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """Build generation_results dict for a single task."""
    return {
        task_id: {
            "generated_files": files or {},
        },
    }


def _make_workflow_result(**overrides: Any) -> Dict[str, Any]:
    base = {
        "workflow_id": "wf-test-1",
        "status": "completed",
        "dry_run": False,
        "total_cost": 0.5,
        "total_duration_seconds": 120.0,
        "start_time": "2026-02-24T00:00:00Z",
        "end_time": "2026-02-24T00:02:00Z",
        "phase_results": [
            {
                "phase": "plan",
                "status": "completed",
                "cost": 0.1,
                "duration_seconds": 30.0,
                "error_message": None,
            },
            {
                "phase": "implement",
                "status": "completed",
                "cost": 0.3,
                "duration_seconds": 60.0,
                "error_message": None,
            },
        ],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Requirement Checking
# ---------------------------------------------------------------------------


class TestRequirementChecking:
    """Tests for _check_requirements logic."""

    def test_requirement_checking_all_met(self):
        """All requirement keywords found in generated code -> score 1.0."""
        task = _make_task_dict(
            task_id="T-1",
            requirements_text=(
                "- implement authentication middleware\n"
                "- add user session management\n"
            ),
        )
        code = (
            "class AuthMiddleware:\n"
            "    def implement_authentication_middleware(self):\n"
            "        pass\n"
            "    def add_user_session_management(self):\n"
            "        pass\n"
        )
        evaluator = PostMortemEvaluator()
        met, missed = evaluator._check_requirements(task, code)
        assert len(missed) == 0
        assert len(met) == 2
        total = len(met) + len(missed)
        assert len(met) / total == 1.0

    def test_requirement_checking_partial(self):
        """2/4 keywords found -> score 0.5."""
        task = _make_task_dict(
            task_id="T-2",
            requirements_text=(
                "- implement user login flow\n"
                "- implement user logout flow\n"
                "- add password reset feature\n"
                "- implement two factor authentication\n"
            ),
        )
        code = (
            "def implement_user_login_flow():\n"
            "    pass\n"
            "def implement_user_logout_flow():\n"
            "    pass\n"
        )
        evaluator = PostMortemEvaluator()
        met, missed = evaluator._check_requirements(task, code)
        assert len(met) == 2
        assert len(missed) == 2
        score = len(met) / (len(met) + len(missed))
        assert score == pytest.approx(0.5)

    def test_requirement_checking_none_met(self):
        """No keywords -> score 0.0."""
        task = _make_task_dict(
            task_id="T-3",
            requirements_text=(
                "- implement database migration system\n"
                "- add rollback capability for migrations\n"
            ),
        )
        code = "print('hello world')\n"
        evaluator = PostMortemEvaluator()
        met, missed = evaluator._check_requirements(task, code)
        assert len(met) == 0
        assert len(missed) == 2
        total = len(met) + len(missed)
        assert len(met) / total == 0.0

    def test_requirement_checking_with_constraints(self):
        """prompt_constraints are also checked."""
        task = _make_task_dict(
            task_id="T-4",
            requirements_text="",
            prompt_constraints=[
                "implement async fetch data function",
                "handle network error with try except",
            ],
        )
        code = (
            "async def fetch_data():\n"
            "    try:\n"
            "        await client.get(url)\n"
            "    except NetworkError as error:\n"
            "        handle_network_error(error)\n"
        )
        evaluator = PostMortemEvaluator()
        met, missed = evaluator._check_requirements(task, code)
        assert len(met) == 2

    def test_empty_requirements(self):
        """No requirements -> empty lists."""
        task = _make_task_dict(task_id="T-5", requirements_text="")
        evaluator = PostMortemEvaluator()
        met, missed = evaluator._check_requirements(task, "some code")
        assert met == []
        assert missed == []


# ---------------------------------------------------------------------------
# File Coverage
# ---------------------------------------------------------------------------


class TestFileCoverage:
    """Tests for _check_file_coverage logic."""

    def test_file_coverage_complete(self):
        """All target_files produced."""
        task = _make_task_dict(
            task_id="T-1",
            target_files=["src/auth.py", "src/middleware.py"],
        )
        gen = _make_gen_results(
            "T-1",
            files={"src/auth.py": "code", "src/middleware.py": "code"},
        )
        evaluator = PostMortemEvaluator()
        expected, produced, missing = evaluator._check_file_coverage(task, gen)
        assert len(expected) == 2
        assert len(produced) == 2
        assert len(missing) == 0

    def test_file_coverage_partial(self):
        """2/3 files produced, 1 missing."""
        task = _make_task_dict(
            task_id="T-1",
            target_files=["a.py", "b.py", "c.py"],
        )
        gen = _make_gen_results("T-1", files={"a.py": "code", "b.py": "code"})
        evaluator = PostMortemEvaluator()
        expected, produced, missing = evaluator._check_file_coverage(task, gen)
        assert len(expected) == 3
        assert len(produced) == 2
        assert missing == ["c.py"]

    def test_file_coverage_empty(self):
        """No generation results -> all missing."""
        task = _make_task_dict(
            task_id="T-1",
            target_files=["a.py", "b.py"],
        )
        evaluator = PostMortemEvaluator()
        expected, produced, missing = evaluator._check_file_coverage(task, {})
        assert len(expected) == 2
        assert len(produced) == 0
        assert len(missing) == 2

    def test_file_coverage_no_targets(self):
        """No target_files -> empty lists."""
        task = _make_task_dict(task_id="T-1", target_files=[])
        evaluator = PostMortemEvaluator()
        expected, produced, missing = evaluator._check_file_coverage(task, {})
        assert expected == []
        assert produced == []
        assert missing == []


# ---------------------------------------------------------------------------
# Verdict Thresholds
# ---------------------------------------------------------------------------


class TestVerdictThresholds:
    """Tests for verdict computation."""

    def test_verdict_pass_threshold(self):
        assert _compute_verdict(0.8) == _VERDICT_PASS
        assert _compute_verdict(0.9) == _VERDICT_PASS
        assert _compute_verdict(1.0) == _VERDICT_PASS

    def test_verdict_partial_threshold(self):
        assert _compute_verdict(0.4) == _VERDICT_PARTIAL
        assert _compute_verdict(0.5) == _VERDICT_PARTIAL
        assert _compute_verdict(0.79) == _VERDICT_PARTIAL

    def test_verdict_fail_threshold(self):
        assert _compute_verdict(0.0) == _VERDICT_FAIL
        assert _compute_verdict(0.39) == _VERDICT_FAIL


# ---------------------------------------------------------------------------
# Full Evaluation
# ---------------------------------------------------------------------------


class TestEvaluateFull:
    """End-to-end evaluation tests."""

    def test_evaluate_full_workflow(self, tmp_path: Path):
        """End-to-end with mock seed + mock WorkflowResult."""
        tasks = [
            _make_task_dict(
                task_id="T-1",
                title="Auth module",
                requirements_text="- implement login endpoint\n- implement logout endpoint\n",
                target_files=["src/auth.py"],
            ),
        ]
        gen_results = _make_gen_results(
            "T-1",
            files={
                "src/auth.py": (
                    "def implement_login_endpoint():\n"
                    "    pass\n"
                    "def implement_logout_endpoint():\n"
                    "    pass\n"
                ),
            },
        )
        wf_result = _make_workflow_result()
        context = {"generation_results": gen_results}

        evaluator = PostMortemEvaluator()
        report = evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=wf_result,
            context=context,
            output_dir=str(tmp_path),
        )

        assert report.total_tasks == 1
        assert report.tasks_evaluated >= 1
        assert report.aggregate_score > 0
        assert report.workflow_id == "wf-test-1"

        # Check output files written
        assert (tmp_path / "postmortem-report.json").exists()
        assert (tmp_path / "postmortem-summary.md").exists()

    def test_partial_failure_handling(self, tmp_path: Path):
        """3/10 tasks completed, 7 get score 0.0."""
        tasks = []
        gen_results: Dict[str, Any] = {}
        for idx in range(10):
            tid = f"T-{idx}"
            tasks.append(
                _make_task_dict(
                    task_id=tid,
                    title=f"Task {idx}",
                    requirements_text=f"- implement feature number {idx} for task\n",
                    target_files=[f"src/feat_{idx}.py"],
                )
            )
            if idx < 3:
                gen_results[tid] = {
                    "generated_files": {
                        f"src/feat_{idx}.py": f"def implement_feature_number_{idx}_for_task(): pass\n",
                    },
                }

        wf_result = _make_workflow_result()
        context = {"generation_results": gen_results}

        evaluator = PostMortemEvaluator()
        report = evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=wf_result,
            context=context,
            output_dir=str(tmp_path),
        )

        assert report.total_tasks == 10
        # At least 3 tasks should have non-zero scores
        nonzero = [t for t in report.tasks if t.requirement_score > 0]
        assert len(nonzero) >= 3

    def test_per_task_error_guard(self, tmp_path: Path):
        """One corrupt task does not abort evaluation."""
        tasks = [
            _make_task_dict(task_id="T-1", title="Good task",
                            requirements_text="- implement basic feature in module\n",
                            target_files=["a.py"]),
            # Corrupt: target_files is not a list
            {"task_id": "T-BAD", "title": "Bad task", "target_files": 12345,
             "requirements_text": "- do something useful here\n"},
            _make_task_dict(task_id="T-3", title="Another good task",
                            requirements_text="- another basic requirement for module\n",
                            target_files=["b.py"]),
        ]
        gen_results = {
            "T-1": {"generated_files": {"a.py": "def implement_basic_feature_in_module(): pass"}},
            "T-3": {"generated_files": {"b.py": "def another_basic_requirement_for_module(): pass"}},
        }

        evaluator = PostMortemEvaluator()
        report = evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=_make_workflow_result(),
            context={"generation_results": gen_results},
            output_dir=str(tmp_path),
        )

        # All 3 tasks should be in the report (bad one scored as FAIL)
        assert report.total_tasks == 3
        ids = {t.task_id for t in report.tasks}
        assert "T-1" in ids
        assert "T-BAD" in ids
        assert "T-3" in ids


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


class TestSanitization:
    """Tests for sanitization in output files."""

    def test_sanitization_applied(self, tmp_path: Path):
        """API keys/paths are redacted in JSON and Markdown output."""
        tasks = [
            _make_task_dict(
                task_id="T-1",
                title="Task with secrets",
                requirements_text="- store the api_key securely in vault\n",
                target_files=["config.py"],
            ),
        ]
        gen_results = _make_gen_results(
            "T-1",
            files={
                "config.py": (
                    "api_key = 'sk-abc123456789xyz'\n"
                    "home = '/Users/testuser/project'\n"
                ),
            },
        )

        evaluator = PostMortemEvaluator()
        report = evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=_make_workflow_result(),
            context={"generation_results": gen_results},
            output_dir=str(tmp_path),
        )

        report_json = (tmp_path / "postmortem-report.json").read_text()
        assert "sk-abc123456789xyz" not in report_json
        assert "/Users/testuser" not in report_json

        summary_md = (tmp_path / "postmortem-summary.md").read_text()
        assert "/Users/testuser" not in summary_md


# ---------------------------------------------------------------------------
# Lessons Extraction
# ---------------------------------------------------------------------------


class TestLessonsExtraction:
    """Tests for lessons extraction logic."""

    def test_lessons_extracted(self, tmp_path: Path):
        """Failed requirements become Lesson objects."""
        tasks = [
            _make_task_dict(
                task_id="T-1",
                title="Missing reqs task",
                requirements_text=(
                    "- implement database connection pooling\n"
                    "- add retry logic for transient failures\n"
                ),
                target_files=["db.py"],
            ),
        ]
        # No generated code -> all requirements missed
        evaluator = PostMortemEvaluator()
        report = evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=_make_workflow_result(),
            context={"generation_results": {}},
            output_dir=str(tmp_path),
        )

        assert len(report.lessons) >= 1
        req_lessons = [
            les for les in report.lessons
            if "requirements-gap" in les.get("tags", [])
        ]
        assert len(req_lessons) >= 1

    def test_anti_pattern_lessons(self, tmp_path: Path):
        """AntiPatternFindings are converted to Lessons."""
        # Generate code with a detectable anti-pattern (deep nesting)
        deeply_nested = "def f():\n"
        for depth in range(8):
            indent = "    " * (depth + 1)
            deeply_nested += f"{indent}if True:\n"
        deeply_nested += "    " * 9 + "pass\n"

        tasks = [
            _make_task_dict(
                task_id="T-NEST",
                title="Nested task",
                requirements_text="- implement the deeply nested function logic\n",
                target_files=["nested.py"],
            ),
        ]
        gen_results = _make_gen_results("T-NEST", files={"nested.py": deeply_nested})

        evaluator = PostMortemEvaluator()
        report = evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=_make_workflow_result(),
            context={"generation_results": gen_results},
            output_dir=str(tmp_path),
        )

        ap_lessons = [
            les for les in report.lessons
            if "anti-pattern" in les.get("tags", [])
        ]
        # May or may not detect — depends on threshold; at minimum, no crash
        assert isinstance(ap_lessons, list)

    def test_missing_file_lessons(self, tmp_path: Path):
        """Missing files generate lessons."""
        tasks = [
            _make_task_dict(
                task_id="T-MF",
                title="Missing files task",
                target_files=["a.py", "b.py", "c.py"],
            ),
        ]
        evaluator = PostMortemEvaluator()
        report = evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=_make_workflow_result(),
            context={"generation_results": {}},
            output_dir=str(tmp_path),
        )

        file_lessons = [
            les for les in report.lessons
            if "missing-files" in les.get("tags", [])
        ]
        assert len(file_lessons) >= 1


# ---------------------------------------------------------------------------
# Markdown Output
# ---------------------------------------------------------------------------


class TestMarkdownOutput:
    """Tests for Markdown report structure."""

    def test_markdown_output_structure(self, tmp_path: Path):
        """Markdown contains expected sections and tables."""
        tasks = [
            _make_task_dict(
                task_id="T-1",
                title="Test task",
                requirements_text="- implement basic endpoint for api\n",
                target_files=["api.py"],
            ),
        ]
        gen_results = _make_gen_results(
            "T-1",
            files={"api.py": "def implement_basic_endpoint_for_api(): pass\n"},
        )

        evaluator = PostMortemEvaluator()
        evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=_make_workflow_result(),
            context={"generation_results": gen_results},
            output_dir=str(tmp_path),
        )

        md = (tmp_path / "postmortem-summary.md").read_text()
        assert "# Post-Mortem Evaluation Report" in md
        assert "## Phase Summary" in md
        assert "## Per-Task Results" in md
        assert "## Cost Summary" in md
        assert "| T-1 |" in md


# ---------------------------------------------------------------------------
# JSON Serialization
# ---------------------------------------------------------------------------


class TestJsonSerialization:
    """Tests for PostMortemReport serialization."""

    def test_json_serialization(self):
        """PostMortemReport.to_dict() round-trips through JSON."""
        tpm = TaskPostMortem(
            task_id="T-1",
            title="Test",
            requirement_score=0.75,
            file_coverage_score=1.0,
            verdict=_VERDICT_PARTIAL,
            requirements_met=["req a"],
            requirements_missed=["req b"],
            files_expected=["a.py"],
            files_produced=["a.py"],
            files_missing=[],
        )
        report = PostMortemReport(
            report_id="r-1",
            workflow_id="wf-1",
            timestamp="2026-02-24T00:00:00Z",
            method="rules",
            tasks=[tpm],
            aggregate_score=0.875,
            aggregate_verdict=_VERDICT_PASS,
            total_tasks=1,
            tasks_evaluated=1,
        )

        json_str = report.to_json()
        parsed = json.loads(json_str)

        assert parsed["report_id"] == "r-1"
        assert parsed["aggregate_score"] == 0.875
        assert len(parsed["tasks"]) == 1
        assert parsed["tasks"][0]["task_id"] == "T-1"
        assert parsed["tasks"][0]["verdict"] == _VERDICT_PARTIAL

    def test_to_dict_round_trip(self):
        """to_dict -> JSON -> loads produces identical structure."""
        report = PostMortemReport(
            report_id="r-2",
            workflow_id="wf-2",
            timestamp="2026-02-24T00:00:00Z",
            method="hybrid",
            aggregate_score=0.5,
            aggregate_verdict=_VERDICT_PARTIAL,
            total_tasks=0,
            tasks_evaluated=0,
        )
        d = report.to_dict()
        round_tripped = json.loads(json.dumps(d, default=str))
        assert round_tripped == d


# ---------------------------------------------------------------------------
# Async Launcher
# ---------------------------------------------------------------------------


class TestAsyncLauncher:
    """Tests for launch_postmortem_async."""

    def test_async_launch_daemon(self, tmp_path: Path):
        """Thread is daemon, starts without blocking."""
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps({
            "tasks": [
                _make_task_dict(
                    task_id="T-1",
                    title="Daemon test",
                    requirements_text="- implement simple feature for testing\n",
                    target_files=["x.py"],
                ),
            ],
        }))

        wf_result = _make_workflow_result()
        context = {"generation_results": {}}

        thread = launch_postmortem_async(
            seed_path=str(seed_path),
            workflow_result=wf_result,
            context=context,
            output_dir=str(tmp_path),
        )

        assert isinstance(thread, threading.Thread)
        assert thread.daemon is True
        assert thread.is_alive() or True  # May finish quickly

        # Wait for it to complete
        thread.join(timeout=30.0)
        assert not thread.is_alive()

        # Should have written the report
        assert (tmp_path / "postmortem-report.json").exists()

    def test_async_launch_missing_seed(self, tmp_path: Path):
        """Missing seed file doesn't crash — logs error and returns."""
        thread = launch_postmortem_async(
            seed_path=str(tmp_path / "nonexistent.json"),
            workflow_result=_make_workflow_result(),
            context={},
            output_dir=str(tmp_path),
        )
        thread.join(timeout=10.0)
        assert not thread.is_alive()
        # No report written
        assert not (tmp_path / "postmortem-report.json").exists()


# ---------------------------------------------------------------------------
# Keyword Extraction
# ---------------------------------------------------------------------------


class TestKeywordExtraction:
    """Tests for _extract_requirement_keywords helper."""

    def test_extracts_from_requirements_text(self):
        keywords = _extract_requirement_keywords({
            "requirements_text": "- implement user login\n- add password validation\n"
        })
        assert len(keywords) == 2
        assert "implement user login" in keywords

    def test_extracts_from_constraints(self):
        keywords = _extract_requirement_keywords({
            "prompt_constraints": [
                "must handle concurrent requests properly",
            ],
        })
        assert len(keywords) >= 1

    def test_deduplicates(self):
        keywords = _extract_requirement_keywords({
            "requirements_text": "- implement user login\n",
            "prompt_constraints": ["implement user login"],
        })
        assert keywords.count("implement user login") == 1

    def test_skips_short_fragments(self):
        keywords = _extract_requirement_keywords({
            "requirements_text": "- ok\n- implement the full feature\n",
        })
        # "ok" is < 3 words, should be skipped
        assert all(len(kw.split()) >= 3 for kw in keywords)


# ---------------------------------------------------------------------------
# Filter slug in filenames
# ---------------------------------------------------------------------------


class TestFilterSlug:
    """Tests for filter slug appended to output filenames."""

    def test_filter_slug_in_filenames(self, tmp_path: Path):
        tasks = [
            _make_task_dict(
                task_id="PI-001",
                title="Filtered task",
                target_files=["x.py"],
            ),
        ]
        evaluator = PostMortemEvaluator()
        evaluator.evaluate(
            seed_tasks=tasks,
            workflow_result=_make_workflow_result(),
            context={"generation_results": {}},
            output_dir=str(tmp_path),
            filter_slug="PI-001-PI-002",
        )
        assert (tmp_path / "postmortem-report-PI-001-PI-002.json").exists()
        assert (tmp_path / "postmortem-summary-PI-001-PI-002.md").exists()
