"""Detection + idempotency cursor tests (FR-1,2,3,4,13)."""

import json
import os

from startd8.service_assistant import detector


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_completed_run_detected(tmp_path):
    run_dir = tmp_path / "run-001" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    _write(run_dir / "prime-result.json", {"success": True, "succeeded": 3, "failed": 0})
    _write(run_dir / "prime-postmortem-report.json", {"aggregate_verdict": "PASS"})

    det = detector.detect_run(run_dir)
    assert det.run_sentinel_present
    assert det.postmortem_present
    assert det.status == "completed"
    assert det.actionable


def test_result_without_postmortem_is_partial(tmp_path):
    run_dir = tmp_path / "run-002" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    _write(run_dir / "prime-result.json", {"success": False})

    det = detector.detect_run(run_dir)
    assert det.status == "partial"  # FR-4 ordering tolerance


def test_hard_abort_detected(tmp_path):
    run_dir = tmp_path / "run-003" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    state = run_dir / ".prime_contractor_state.json"
    _write(state, {"order": ["a", "b", "c"], "features": {}})
    # Age the state file past the staleness threshold (FR-13).
    old = os.stat(state).st_mtime - (detector.HARD_ABORT_STALENESS_SECONDS + 5)
    os.utime(state, (old, old))

    det = detector.detect_run(run_dir)
    assert det.hard_abort
    assert det.status == "aborted"
    assert det.features_attempted == 3


def test_no_run_is_not_actionable(tmp_path):
    run_dir = tmp_path / "run-004" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    det = detector.detect_run(run_dir)
    assert not det.actionable


def test_run_id_resolution_from_dir_name(tmp_path):
    run_dir = tmp_path / "run-042" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    _write(run_dir / "prime-result.json", {"success": True})
    det = detector.detect_run(run_dir)
    assert det.run_id == "run-042"


def test_cursor_idempotency(tmp_path):
    run_dir = tmp_path / "run-005" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    _write(run_dir / "prime-result.json", {"success": True})
    _write(run_dir / "prime-postmortem-report.json", {"aggregate_verdict": "PASS"})

    det = detector.detect_run(run_dir)
    seen, cursor_path = detector.already_processed(det)
    assert not seen
    detector.record_processed(det, cursor_path)

    det2 = detector.detect_run(run_dir)
    seen2, _ = detector.already_processed(det2)
    assert seen2  # FR-3: same run+checksum is a no-op
    # Cursor lives at the pipeline-output base, not inside the run dir (OQ-8).
    assert cursor_path == tmp_path / "service-assistant-cursor.json"
