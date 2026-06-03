"""End-to-end triage synthesis + notification tests (FR-6,7,8,9)."""

import json

from startd8.events import EventBus, EventType
from startd8.service_assistant import run_service_assistant


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def _failed_run(tmp_path):
    run_dir = tmp_path / "run-010" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    _write(run_dir / "prime-result.json", {"success": False, "succeeded": 1, "failed": 1})
    _write(
        run_dir / "prime-postmortem-report.json",
        {
            "aggregate_verdict": "PARTIAL",
            "total_features": 2,
            "successful_features": 1,
            "failed_features": 1,
            "cost_summary": {"total_usd": 1.25},
            "features": [
                {"feature_id": "ok", "success": True, "root_cause": "unknown"},
                {
                    "feature_id": "broken",
                    "success": False,
                    "root_cause": "cross_file_contract",
                    "pipeline_stage": "cross_feature_contract",
                    "error_message": "DTO field renamed",
                    "target_files": ["src/app/web/export_router.py"],
                },
            ],
            "cross_feature_patterns": [
                {
                    "pattern_type": "schema_divergence",
                    "description": "DTO mismatch",
                    "affected_features": ["broken", "report"],
                    "severity": "high",
                }
            ],
        },
    )
    return run_dir


def test_triage_synthesizes_failure_with_recommendation(tmp_path):
    run_dir = _failed_run(tmp_path)
    report = run_service_assistant(run_dir, emit=False)

    assert report is not None
    assert report.verdict.aggregate_verdict == "PARTIAL"
    assert report.verdict.total_cost_usd == 1.25
    assert len(report.failures) == 1  # only the failed feature (FR-8 consume)

    failure = report.failures[0]
    assert failure.feature_id == "broken"
    assert failure.root_cause == "cross_file_contract"
    assert failure.severity == "critical"
    assert failure.recommended_action.re_run_strategy == "from_latest_producer"
    assert failure.recommended_action.source_classification == "postmortem_report"
    assert failure.file == "src/app/web/export_router.py"

    # Artifact written (FR-7) and is the authoritative bridge.
    triage_json = run_dir / "service-assistant-triage.json"
    triage_md = run_dir / "service-assistant-triage.md"
    assert triage_json.is_file() and triage_md.is_file()
    data = json.loads(triage_json.read_text())
    assert data["schema_version"] == "1.0"
    assert data["summary"]["top_recommendation"]


def test_events_emitted_on_failure(tmp_path):
    run_dir = _failed_run(tmp_path)
    EventBus.clear_history()
    run_service_assistant(run_dir, emit=True)

    types = {e.type for e in EventBus.get_history()}
    assert EventType.POSTMORTEM_AVAILABLE in types
    assert EventType.RUN_DETECTED in types
    # PARTIAL is not FAIL/ABORTED, so RUN_FAILED should NOT fire.
    assert EventType.RUN_FAILED not in types


def test_idempotent_second_run_is_noop(tmp_path):
    run_dir = _failed_run(tmp_path)
    first = run_service_assistant(run_dir, emit=False)
    second = run_service_assistant(run_dir, emit=False)
    assert first is not None
    assert second is None  # FR-3


def test_hard_abort_emits_run_failed(tmp_path):
    import os
    from startd8.service_assistant import detector

    run_dir = tmp_path / "run-011" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    state = run_dir / ".prime_contractor_state.json"
    state.write_text(json.dumps({"order": ["x", "y"]}), encoding="utf-8")
    old = os.stat(state).st_mtime - (detector.HARD_ABORT_STALENESS_SECONDS + 5)
    os.utime(state, (old, old))

    EventBus.clear_history()
    report = run_service_assistant(run_dir, emit=True)
    assert report is not None
    assert report.verdict.aggregate_verdict == "ABORTED"
    types = {e.type for e in EventBus.get_history()}
    assert EventType.RUN_FAILED in types
