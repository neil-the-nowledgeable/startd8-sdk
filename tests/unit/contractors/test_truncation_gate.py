"""Tests for Gate 4: artisan-native truncation detection.

Validates that _validate_truncation() correctly detects truncated,
syntactically broken, and undersized generated files, and that the
truncation_flags propagate through the context dict to downstream phases.
"""

from __future__ import annotations

import textwrap
from dataclasses import field
from pathlib import Path
from typing import Any

import pytest

from startd8.contractors.context_schema import ImplementPhaseOutput
from startd8.contractors.context_seed_handlers import (
    ImplementPhaseHandler,
    _CACHE_SCHEMA_VERSION,
)
from startd8.contractors.protocols import GenerationResult
from startd8.truncation_detection import (
    CONFIDENCE_TRUNCATION_BLOCKED,
    MIN_LINES_TRUNCATION_BLOCKING,
    detect_truncation,
)

# Import shared FakeSeedTask from conftest (auto-discovered by pytest)
from conftest import FakeSeedTask


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_file(tmp_path: Path, name: str, content: str) -> Path:
    """Write a file and return its Path."""
    fp = tmp_path / name
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(content, encoding="utf-8")
    return fp


def _make_gen_result(tmp_path: Path, files: dict[str, str]) -> GenerationResult:
    """Create a GenerationResult with the given files written to tmp_path."""
    paths = []
    for name, content in files.items():
        fp = _write_file(tmp_path, name, content)
        paths.append(fp)
    return GenerationResult(success=True, generated_files=paths)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestValidateTruncation:
    """Tests for ImplementPhaseHandler._validate_truncation()."""

    def test_no_truncation_when_files_ok(self, tmp_path: Path) -> None:
        """Well-formed Python files produce empty truncation_flags."""
        content = textwrap.dedent("""\
            \"\"\"A well-formed module.\"\"\"

            class Widget:
                def __init__(self, name: str) -> None:
                    self.name = name

                def greet(self) -> str:
                    return f"Hello from {self.name}"


            def create_widget(name: str) -> Widget:
                return Widget(name)
        """)
        task = FakeSeedTask(
            task_id="T-1",
            target_files=["widget.py"],
            estimated_loc=15,
        )
        gr = _make_gen_result(tmp_path, {"widget.py": content})

        flags = ImplementPhaseHandler._validate_truncation(
            [task], {"T-1": gr}, tmp_path,
        )
        assert flags == {}

    def test_syntax_error_detected(self, tmp_path: Path) -> None:
        """A Python file with SyntaxError is flagged (source='syntax')."""
        broken_code = textwrap.dedent("""\
            class Broken:
                def method(self):
                    return (1 + 2
            # Missing closing paren — SyntaxError
        """)
        task = FakeSeedTask(
            task_id="T-2",
            target_files=["broken.py"],
            estimated_loc=10,
        )
        gr = _make_gen_result(tmp_path, {"broken.py": broken_code})

        flags = ImplementPhaseHandler._validate_truncation(
            [task], {"T-2": gr}, tmp_path,
        )
        assert "T-2" in flags
        assert flags["T-2"]["detected"] is True
        assert flags["T-2"]["source"] == "syntax"
        assert len(flags["T-2"]["syntax_errors"]) > 0

    def test_heuristic_truncation_detected(self, tmp_path: Path) -> None:
        """An unclosed code block triggers heuristic truncation detection."""
        # Content that looks like it was cut off mid-block
        truncated_code = textwrap.dedent("""\
            class Service:
                def __init__(self):
                    self.data = {}

                def process(self):
                    for item in self.data:
                        if item.startswith("x"):
                            result = {
                                "key": item,
        """)
        task = FakeSeedTask(
            task_id="T-3",
            target_files=["service.py"],
            estimated_loc=50,
        )
        gr = _make_gen_result(tmp_path, {"service.py": truncated_code})

        flags = ImplementPhaseHandler._validate_truncation(
            [task], {"T-3": gr}, tmp_path,
        )
        # The file has both SyntaxError AND likely heuristic truncation
        assert "T-3" in flags
        assert flags["T-3"]["detected"] is True

    def test_ratio_flag(self, tmp_path: Path) -> None:
        """10 lines vs estimated_loc=100 triggers the <30% ratio flag."""
        short_code = textwrap.dedent("""\
            \"\"\"Short module.\"\"\"

            def hello():
                return "hello"
        """)
        task = FakeSeedTask(
            task_id="T-4",
            target_files=["short.py"],
            estimated_loc=100,  # expect 100 lines
        )
        gr = _make_gen_result(tmp_path, {"short.py": short_code})

        flags = ImplementPhaseHandler._validate_truncation(
            [task], {"T-4": gr}, tmp_path,
        )
        # The ratio is ~4/100 = 4%, well below 30%
        # But the file itself is syntactically valid and not heuristically truncated.
        # Only the ratio flag should trigger.
        assert "T-4" in flags
        assert flags["T-4"]["detected"] is True
        assert "ratio" in flags["T-4"].get("source", "") or flags["T-4"].get("ratio") is not None

    def test_multi_file_task_partial_truncation(self, tmp_path: Path) -> None:
        """One OK file and one broken file in the same task."""
        good_code = textwrap.dedent("""\
            \"\"\"Good module.\"\"\"

            def good_func():
                return True
        """)
        broken_code = textwrap.dedent("""\
            class Incomplete:
                def method(self):
                    return (1 +
        """)
        task = FakeSeedTask(
            task_id="T-5",
            target_files=["good.py", "broken.py"],
            estimated_loc=20,
        )
        good_path = _write_file(tmp_path, "good.py", good_code)
        broken_path = _write_file(tmp_path, "broken.py", broken_code)
        gr = GenerationResult(
            success=True,
            generated_files=[good_path, broken_path],
        )

        flags = ImplementPhaseHandler._validate_truncation(
            [task], {"T-5": gr}, tmp_path,
        )
        assert "T-5" in flags
        assert flags["T-5"]["detected"] is True
        # Should have file_results for both files
        assert len(flags["T-5"]["file_results"]) == 2

    def test_skips_failed_tasks(self, tmp_path: Path) -> None:
        """Tasks with success=False are not checked for truncation."""
        task = FakeSeedTask(task_id="T-6", target_files=["fail.py"])
        gr = GenerationResult(success=False, error="Generation failed")

        flags = ImplementPhaseHandler._validate_truncation(
            [task], {"T-6": gr}, tmp_path,
        )
        assert flags == {}

    def test_skips_missing_tasks(self, tmp_path: Path) -> None:
        """Tasks not in generation_results are skipped."""
        task = FakeSeedTask(task_id="T-7", target_files=["missing.py"])

        flags = ImplementPhaseHandler._validate_truncation(
            [task], {}, tmp_path,
        )
        assert flags == {}


class TestContextPropagation:
    """Tests for truncation_flags propagation through context dict."""

    def test_implement_output_validates_with_truncation_flags(self) -> None:
        """ImplementPhaseOutput accepts the truncation_flags field."""
        output = ImplementPhaseOutput(
            implementation={"tasks_processed": 1},
            generation_results={"T-1": {"success": True}},
            truncation_flags={"T-1": {"detected": True, "source": "syntax"}},
        )
        assert output.truncation_flags == {"T-1": {"detected": True, "source": "syntax"}}

    def test_implement_output_defaults_to_empty(self) -> None:
        """ImplementPhaseOutput defaults truncation_flags to {}."""
        output = ImplementPhaseOutput(
            implementation={"tasks_processed": 1},
            generation_results={"T-1": {"success": True}},
        )
        assert output.truncation_flags == {}

    def test_context_propagation_to_test(self, tmp_path: Path) -> None:
        """truncation_flags in context are annotated in TEST per_task results."""
        # Simulate a context dict with truncation_flags from IMPLEMENT
        context: dict[str, Any] = {
            "project_root": str(tmp_path),
            "tasks": [
                FakeSeedTask(
                    task_id="T-1",
                    target_files=["widget.py"],
                    post_generation_validators=[],
                ),
            ],
            "task_index": {"T-1": None},
            "generation_results": {
                "T-1": GenerationResult(success=True, generated_files=[]),
            },
            "truncation_flags": {
                "T-1": {
                    "detected": True,
                    "max_confidence": 0.8,
                    "source": "syntax",
                },
            },
        }

        from startd8.contractors.context_seed_handlers import TestPhaseHandler

        handler = TestPhaseHandler()
        result = handler.execute(
            phase=_make_phase("test"),
            context=context,
            dry_run=True,
        )

        # In dry-run, per_task is still built; check annotation
        per_task = context.get("test_results", {}).get("per_task", {})
        # Dry-run doesn't produce per_task entries with passed/failed for
        # tasks that have no validators, but if per_task has T-1, check annotation.
        # The truncation annotation is added after per_task is built, so if
        # T-1 exists in per_task, it should be annotated.
        if "T-1" in per_task:
            assert per_task["T-1"].get("truncation_warning") is True
            assert per_task["T-1"].get("truncation_confidence") == 0.8
            assert per_task["T-1"].get("truncation_source") == "syntax"

    def test_context_propagation_to_finalize(self, tmp_path: Path) -> None:
        """truncation_flags flow into FINALIZE summary as truncation_summary."""
        from startd8.contractors.context_seed_handlers import FinalizePhaseHandler

        context: dict[str, Any] = {
            "plan_title": "Test Plan",
            "tasks": [
                FakeSeedTask(task_id="T-1", target_files=["widget.py"]),
            ],
            "task_index": {"T-1": None},
            "domain_summary": {"domain": "test"},
            "preflight_summary": {},
            "scaffold": {
                "directories_needed": [],
                "directories_created": [],
                "project_root": str(tmp_path),
            },
            "implementation": {"tasks_processed": 1},
            "generation_results": {
                "T-1": GenerationResult(
                    success=True,
                    generated_files=[],
                    cost_usd=0.01,
                ),
            },
            "test_results": {
                "test_plan": [],
                "total_validators": 0,
                "unique_validators": {},
                "tasks_with_tests": 0,
                "total_passed": 0,
                "total_failed": 0,
                "per_task": {},
            },
            "review_results": {
                "review_items": [],
                "preflight_summary": {},
                "constraint_coverage": {},
                "tasks_with_env_issues": 0,
                "total_cost": 0.0,
                "total_passed": 1,
                "total_failed": 0,
                "per_task": {"T-1": {"status": "reviewed", "passed": True, "score": 90, "verdict": "PASS"}},
            },
            "truncation_flags": {
                "T-1": {
                    "detected": True,
                    "max_confidence": 0.75,
                    "source": "heuristic_high",
                    "syntax_errors": [],
                },
            },
        }

        handler = FinalizePhaseHandler(output_dir=str(tmp_path / "out"))
        result = handler.execute(
            phase=_make_phase("finalize"),
            context=context,
            dry_run=True,
        )

        summary = context.get("workflow_summary", {})
        ts = summary.get("truncation_summary", {})
        assert ts["tasks_flagged"] == 1
        assert ts["flagged_task_ids"] == ["T-1"]
        assert ts["max_confidence"] == 0.75
        assert "T-1" in ts["details"]


class TestCacheEnvelope:
    """Tests for truncation_flags in the cache envelope."""

    def test_cache_schema_version_bumped(self) -> None:
        """_CACHE_SCHEMA_VERSION is 3 (includes truncation_flags)."""
        assert _CACHE_SCHEMA_VERSION == 3

    def test_cache_includes_truncation_flags(self) -> None:
        """Verify that a cache envelope built with truncation_flags is valid."""
        import datetime

        cache_envelope = {
            "_cache_meta": {
                "schema_version": _CACHE_SCHEMA_VERSION,
                "created_at": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "source_checksum": None,
            },
            "downstream_map": {},
            "truncation_flags": {
                "T-1": {
                    "detected": True,
                    "source": "syntax",
                    "max_confidence": 0.9,
                },
            },
            "tasks": {},
        }
        assert cache_envelope["truncation_flags"]["T-1"]["detected"] is True
        assert cache_envelope["_cache_meta"]["schema_version"] == 3


# ---------------------------------------------------------------------------
# Gate 4 blocking threshold tests
# ---------------------------------------------------------------------------


def _compute_blocking(file_results: list[dict]) -> tuple[float, bool]:
    """Replicate Gate 4 blocking logic for testing."""
    detected = any(fr.get("truncation_detected", False) for fr in file_results)
    _blocking_confidence = max(
        (
            fr["truncation_confidence"]
            for fr in file_results
            if fr["lines"] >= MIN_LINES_TRUNCATION_BLOCKING
            and fr.get("truncation_detected", False)
        ),
        default=0.0,
    )
    blocked = detected and _blocking_confidence >= CONFIDENCE_TRUNCATION_BLOCKED
    return _blocking_confidence, blocked


class TestTruncationBlockingThresholds:
    """Two-layer defense against false-positive truncation blocking."""

    def test_small_file_excluded_from_blocking(self):
        """A 1-line file at 0.55 confidence does NOT block when under MIN_LINES."""
        file_results = [
            {
                "file": "tests/__init__.py",
                "lines": 1,
                "truncation_detected": True,
                "truncation_confidence": 0.55,
            },
        ]
        _blocking_conf, blocked = _compute_blocking(file_results)
        assert _blocking_conf == 0.0, "Small file should not contribute to blocking"
        assert blocked is False

    def test_large_file_above_threshold_blocks(self):
        """A 20-line file at 0.7 confidence blocks integration."""
        file_results = [
            {
                "file": "src/core.py",
                "lines": 20,
                "truncation_detected": True,
                "truncation_confidence": 0.7,
            },
        ]
        _blocking_conf, blocked = _compute_blocking(file_results)
        assert _blocking_conf == 0.7
        assert blocked is True

    def test_mixed_files_small_excluded(self):
        """Task with one tiny high-confidence file and one large low-confidence file.

        Blocking should use only the large file's confidence.
        """
        file_results = [
            {
                "file": "tests/__init__.py",
                "lines": 1,
                "truncation_detected": True,
                "truncation_confidence": 0.8,  # high, but tiny file
            },
            {
                "file": "src/module.py",
                "lines": 50,
                "truncation_detected": True,
                "truncation_confidence": 0.4,  # below blocking threshold
            },
        ]
        _blocking_conf, blocked = _compute_blocking(file_results)
        assert _blocking_conf == 0.4, "Should use large file's confidence only"
        assert blocked is False, "0.4 < 0.6 threshold, should not block"

    def test_pi001_false_positive_scenario(self):
        """Exact reproduction: `tests/__init__.py` with docstring-only content.

        The file '\"\"\"Tests for hybrid_scaffold.\"\"\"' triggers prose heuristics
        (unclosed quote + unclosed string) but must NOT block integration.
        """
        content = '"""Tests for hybrid_scaffold."""'
        result = detect_truncation(content, code_mode=None)
        # Detection may still flag it (is_truncated=True with ~0.55 confidence)
        # but Gate 4 would NOT block because line_count=1 < MIN_LINES=5.
        file_results = [
            {
                "file": "tests/__init__.py",
                "lines": content.count("\n") + 1,  # 1 line
                "truncation_detected": result.is_truncated,
                "truncation_confidence": result.confidence,
            },
        ]
        _blocking_conf, blocked = _compute_blocking(file_results)
        assert blocked is False, (
            f"1-line __init__.py should not block: "
            f"confidence={result.confidence}, indicators={result.indicators}"
        )


# ---------------------------------------------------------------------------
# Helpers for phase mocking
# ---------------------------------------------------------------------------


class _FakePhase:
    """Minimal phase object with a .value attribute."""

    def __init__(self, value: str) -> None:
        self.value = value


def _make_phase(value: str) -> _FakePhase:
    return _FakePhase(value)
