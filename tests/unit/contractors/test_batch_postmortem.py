"""Tests for batch-aware cross-run post-mortem analysis."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from startd8.contractors.batch_postmortem import (
    BatchLedger,
    BatchPostMortemEvaluator,
    BatchPostMortemReport,
    CumulativeCostSummary,
    PersistentFailure,
    RunSnapshot,
    TaskLedgerRecord,
    TaskRunEntry,
    VelocityEstimate,
    append_run_to_ledger,
    compute_seed_checksum,
    derive_batch_id,
    detect_force_regenerated,
    load_or_create_ledger,
    save_ledger,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def seed_file(tmp_dir):
    """Create a minimal seed file."""
    seed = {
        "tasks": [
            {"task_id": "T-001", "title": "Feature Alpha"},
            {"task_id": "T-002", "title": "Feature Beta"},
            {"task_id": "T-003", "title": "Feature Gamma"},
        ]
    }
    path = tmp_dir / "seed.json"
    path.write_text(json.dumps(seed), encoding="utf-8")
    return path


@pytest.fixture
def ledger_path(tmp_dir):
    return str(tmp_dir / "batch-ledger.json")


def _make_ledger(seed_path, checksum="abc123", total_tasks=3):
    return BatchLedger(
        batch_id=derive_batch_id(checksum),
        seed_path=str(seed_path),
        seed_checksum=checksum,
        total_tasks=total_tasks,
        created_at="2026-03-01T00:00:00",
        updated_at="2026-03-01T00:00:00",
    )


# ---------------------------------------------------------------------------
# Seed checksum and batch ID
# ---------------------------------------------------------------------------


class TestSeedChecksum:
    def test_deterministic(self, seed_file):
        c1 = compute_seed_checksum(str(seed_file))
        c2 = compute_seed_checksum(str(seed_file))
        assert c1 == c2
        assert len(c1) == 64  # SHA256 hex

    def test_different_content(self, tmp_dir):
        f1 = tmp_dir / "a.json"
        f2 = tmp_dir / "b.json"
        f1.write_text('{"x": 1}')
        f2.write_text('{"x": 2}')
        assert compute_seed_checksum(str(f1)) != compute_seed_checksum(str(f2))


class TestBatchId:
    def test_format(self):
        bid = derive_batch_id("abcdef1234567890")
        assert bid == "batch-abcdef123456"
        assert bid.startswith("batch-")
        assert len(bid) == len("batch-") + 12


# ---------------------------------------------------------------------------
# Ledger CRUD
# ---------------------------------------------------------------------------


class TestLoadOrCreateLedger:
    def test_create_new(self, seed_file, ledger_path):
        ledger = load_or_create_ledger(
            ledger_path, str(seed_file), "abc123", total_tasks=3
        )
        assert ledger.batch_id == derive_batch_id("abc123")
        assert ledger.total_tasks == 3
        assert ledger.tasks == {}
        assert ledger.runs == []

    def test_load_existing(self, seed_file, ledger_path):
        # Create and save
        ledger = _make_ledger(seed_file)
        save_ledger(ledger, ledger_path)

        # Load
        loaded = load_or_create_ledger(
            ledger_path, str(seed_file), "abc123", total_tasks=3
        )
        assert loaded.batch_id == ledger.batch_id
        assert loaded.seed_checksum == "abc123"

    def test_checksum_mismatch_creates_new(self, seed_file, ledger_path):
        ledger = _make_ledger(seed_file, checksum="old_checksum")
        save_ledger(ledger, ledger_path)

        loaded = load_or_create_ledger(
            ledger_path, str(seed_file), "new_checksum", total_tasks=5
        )
        assert loaded.seed_checksum == "new_checksum"
        assert loaded.total_tasks == 5
        assert loaded.tasks == {}


# ---------------------------------------------------------------------------
# Append run
# ---------------------------------------------------------------------------


class TestAppendRun:
    def test_first_run(self, seed_file):
        ledger = _make_ledger(seed_file)
        results = {
            "T-001": {"success": True, "cost_usd": 0.01},
            "T-002": {"success": False, "cost_usd": 0.02, "error": "ast failure"},
        }
        queue = {
            "T-001": {"name": "Feature Alpha"},
            "T-002": {"name": "Feature Beta"},
        }

        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results, queue
        )

        assert len(ledger.runs) == 1
        assert ledger.runs[0].tasks_attempted == 2
        assert ledger.runs[0].tasks_passed == 1
        assert ledger.runs[0].tasks_failed == 1
        assert ledger.runs[0].cumulative_passed == 1
        assert ledger.runs[0].remaining == 2  # 3 total - 1 passed
        assert ledger.tasks["T-001"].current_status == "passed"
        assert ledger.tasks["T-002"].current_status == "failed"

    def test_second_run_preserves_first(self, seed_file):
        ledger = _make_ledger(seed_file)

        # Run 1: T-001 passes, T-002 fails
        results1 = {
            "T-001": {"success": True, "cost_usd": 0.01},
            "T-002": {"success": False, "cost_usd": 0.02},
        }
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results1, {}
        )

        # Run 2: T-002 passes, T-003 passes
        results2 = {
            "T-002": {"success": True, "cost_usd": 0.03},
            "T-003": {"success": True, "cost_usd": 0.01},
        }
        ledger = append_run_to_ledger(
            ledger, "run-002", "2026-03-01T11:00:00", results2, {}
        )

        assert len(ledger.runs) == 2
        assert ledger.runs[1].cumulative_passed == 3
        assert ledger.runs[1].remaining == 0
        # T-001 still has its run-001 history
        assert len(ledger.tasks["T-001"].history) == 1
        # T-002 has entries from both runs
        assert len(ledger.tasks["T-002"].history) == 2

    def test_idempotent_append(self, seed_file):
        ledger = _make_ledger(seed_file)
        results = {"T-001": {"success": True, "cost_usd": 0.01}}

        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results, {}
        )
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results, {}
        )

        # Should have exactly 1 run and 1 history entry
        assert len(ledger.runs) == 1
        assert len(ledger.tasks["T-001"].history) == 1


# ---------------------------------------------------------------------------
# Force-regeneration detection
# ---------------------------------------------------------------------------


class TestForceRegeneration:
    def test_detect_pass_then_rerun(self, seed_file):
        ledger = _make_ledger(seed_file)

        # Run 1: T-001 passes
        results1 = {"T-001": {"success": True, "cost_usd": 0.01}}
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results1, {}
        )

        # Detect: T-001 reappearing in run 2
        force_regen = detect_force_regenerated(ledger, {"T-001", "T-002"})
        assert "T-001" in force_regen
        assert "T-002" not in force_regen

    def test_no_false_positives_on_failures(self, seed_file):
        ledger = _make_ledger(seed_file)

        # Run 1: T-001 fails
        results1 = {"T-001": {"success": False}}
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results1, {}
        )

        # T-001 reappearing is a retry, not force-regen
        force_regen = detect_force_regenerated(ledger, {"T-001"})
        assert len(force_regen) == 0

    def test_force_regen_marked_in_ledger(self, seed_file):
        ledger = _make_ledger(seed_file)

        # Run 1: T-001 passes
        results1 = {"T-001": {"success": True, "cost_usd": 0.01}}
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results1, {}
        )

        # Run 2: T-001 force-regenerated
        results2 = {"T-001": {"success": True, "cost_usd": 0.02}}
        ledger = append_run_to_ledger(
            ledger, "run-002", "2026-03-01T11:00:00", results2, {}
        )

        run2_entry = ledger.tasks["T-001"].history[-1]
        assert run2_entry.force_regenerated is True
        assert ledger.runs[-1].force_regenerated_count == 1


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------


class TestBatchPostMortemEvaluator:
    def _build_3run_ledger(self, seed_file):
        """Build a ledger simulating 3 runs: 1/3 -> 2/3 -> 3/3."""
        ledger = _make_ledger(seed_file)

        # Run 1: T-001 passes, T-002 + T-003 fail
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00",
            {
                "T-001": {"success": True, "cost_usd": 0.01},
                "T-002": {"success": False, "cost_usd": 0.02, "root_cause": "ast_failure"},
                "T-003": {"success": False, "cost_usd": 0.01, "root_cause": "timeout"},
            },
            {},
        )

        # Run 2: T-002 passes, T-003 fails again
        ledger = append_run_to_ledger(
            ledger, "run-002", "2026-03-01T11:00:00",
            {
                "T-002": {"success": True, "cost_usd": 0.03},
                "T-003": {"success": False, "cost_usd": 0.02, "root_cause": "timeout"},
            },
            {},
        )

        # Run 3: T-003 passes
        ledger = append_run_to_ledger(
            ledger, "run-003", "2026-03-01T12:00:00",
            {
                "T-003": {"success": True, "cost_usd": 0.01},
            },
            {},
        )

        return ledger

    def test_complete_verdict(self, seed_file):
        ledger = self._build_3run_ledger(seed_file)
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        assert report.batch_verdict == "COMPLETE"
        assert report.cumulative_passed == 3
        assert report.remaining == 0
        assert report.runs_completed == 3

    def test_in_progress_verdict(self, seed_file):
        ledger = _make_ledger(seed_file)
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00",
            {"T-001": {"success": True, "cost_usd": 0.01}},
            {},
        )
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        assert report.batch_verdict == "IN_PROGRESS"
        assert report.remaining == 2

    def test_stalled_verdict(self, seed_file):
        ledger = _make_ledger(seed_file)
        # Run 1: 1 pass
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00",
            {"T-001": {"success": True}},
            {},
        )
        # Run 2: 0 passes
        ledger = append_run_to_ledger(
            ledger, "run-002", "2026-03-01T11:00:00",
            {"T-002": {"success": False}, "T-003": {"success": False}},
            {},
        )
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        assert report.batch_verdict == "STALLED"

    def test_persistent_failures(self, seed_file):
        ledger = self._build_3run_ledger(seed_file)
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        # T-003 failed in runs 1 and 2 (persistent), then resolved in run 3
        pf_ids = {pf.task_id for pf in report.persistent_failures}
        assert "T-003" in pf_ids

        t003_pf = next(pf for pf in report.persistent_failures if pf.task_id == "T-003")
        assert t003_pf.failure_count == 2
        assert "timeout" in t003_pf.root_causes
        assert t003_pf.resolved_in_run == "run-003"

    def test_newly_resolved(self, seed_file):
        ledger = self._build_3run_ledger(seed_file)
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        assert "T-003" in report.newly_resolved

    def test_velocity_calculation(self, seed_file):
        ledger = self._build_3run_ledger(seed_file)
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        assert report.velocity is not None
        assert report.velocity.tasks_per_run_avg == 1.0  # 1, 1, 1 new passes per run
        assert report.velocity.estimated_runs_remaining == 0  # batch complete
        assert report.velocity.trend == "stable"

    def test_velocity_trend_decelerating(self, seed_file):
        ledger = _make_ledger(seed_file, total_tasks=10)

        # Run 1: 5 pass (high velocity)
        results1 = {f"T-{i:03d}": {"success": True} for i in range(1, 6)}
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results1, {}
        )

        # Run 2: 1 pass (low velocity)
        results2 = {"T-006": {"success": True}}
        ledger = append_run_to_ledger(
            ledger, "run-002", "2026-03-01T11:00:00", results2, {}
        )

        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)
        assert report.velocity is not None
        assert report.velocity.trend == "decelerating"

    def test_cumulative_cost(self, seed_file):
        ledger = self._build_3run_ledger(seed_file)
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        assert report.cumulative_cost is not None
        expected_total = 0.01 + 0.02 + 0.01 + 0.03 + 0.02 + 0.01
        assert abs(report.cumulative_cost.total_usd - expected_total) < 1e-6
        assert report.cumulative_cost.retry_cost_usd > 0
        assert 0 < report.cumulative_cost.retry_cost_fraction < 1

    def test_progression_table(self, seed_file):
        ledger = self._build_3run_ledger(seed_file)
        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)

        assert len(report.progression) == 3
        assert report.progression[0].cumulative_passed == 1
        assert report.progression[1].cumulative_passed == 2
        assert report.progression[2].cumulative_passed == 3


# ---------------------------------------------------------------------------
# JSON roundtrip
# ---------------------------------------------------------------------------


class TestJsonRoundtrip:
    def test_save_and_load_preserves_data(self, seed_file, ledger_path):
        ledger = _make_ledger(seed_file)
        results = {
            "T-001": {"success": True, "cost_usd": 0.01},
            "T-002": {"success": False, "cost_usd": 0.02, "error": "boom"},
        }
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00", results,
            {"T-001": {"name": "Alpha"}, "T-002": {"name": "Beta"}},
        )

        save_ledger(ledger, ledger_path)
        loaded = load_or_create_ledger(
            ledger_path, str(seed_file), "abc123", total_tasks=3
        )

        assert loaded.batch_id == ledger.batch_id
        assert len(loaded.runs) == 1
        assert len(loaded.tasks) == 2
        assert loaded.tasks["T-001"].current_status == "passed"
        assert loaded.tasks["T-002"].history[0].verdict == "FAIL"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


class TestMarkdownRendering:
    def test_contains_key_sections(self, seed_file):
        ledger = _make_ledger(seed_file)
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00",
            {
                "T-001": {"success": True, "cost_usd": 0.01},
                "T-002": {"success": False, "cost_usd": 0.02, "root_cause": "ast_failure"},
            },
            {},
        )
        ledger = append_run_to_ledger(
            ledger, "run-002", "2026-03-01T11:00:00",
            {
                "T-002": {"success": False, "cost_usd": 0.02, "root_cause": "ast_failure"},
            },
            {},
        )

        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)
        md = evaluator.render_markdown(report)

        assert "# Batch Post-Mortem Report" in md
        assert "## Progression" in md
        assert "## Persistent Failures" in md
        assert "## Velocity" in md
        assert "## Cumulative Cost" in md
        assert "run-001" in md
        assert "run-002" in md

    def test_write_outputs(self, seed_file, tmp_dir):
        ledger = _make_ledger(seed_file)
        ledger = append_run_to_ledger(
            ledger, "run-001", "2026-03-01T10:00:00",
            {"T-001": {"success": True, "cost_usd": 0.01}},
            {},
        )

        evaluator = BatchPostMortemEvaluator()
        report = evaluator.evaluate(ledger)
        evaluator.write_outputs(report, str(tmp_dir))

        assert (tmp_dir / "batch-postmortem-report.json").is_file()
        assert (tmp_dir / "batch-postmortem-summary.md").is_file()

        # Verify JSON is valid
        data = json.loads(
            (tmp_dir / "batch-postmortem-report.json").read_text(encoding="utf-8")
        )
        assert data["batch_id"] == report.batch_id
