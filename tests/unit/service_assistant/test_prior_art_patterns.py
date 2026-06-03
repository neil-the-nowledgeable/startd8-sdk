"""Tests for patterns adopted from the rabbit/squirrel/coyote prior art.

- Skip-filter verdict (Coyote): environmental/transient causes are non-actionable.
- Broadened detection (HOWL): aux error stores beyond run/post-mortem sentinels.
"""

import json
import os

from startd8.contractors.prime_postmortem import RootCause
from startd8.service_assistant import detector, run_service_assistant
from startd8.service_assistant.operational_actions import resolve_operational_action


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


# --- Skip-filter (Coyote) ---------------------------------------------------

def test_environmental_causes_are_not_actionable():
    for cause in (
        RootCause.OLLAMA_CIRCUIT_BREAKER,
        RootCause.OLLAMA_EMPTY_RESPONSE,
        RootCause.GENERATION_ERROR,
    ):
        assert resolve_operational_action(cause).actionable is False


def test_code_causes_are_actionable():
    for cause in (
        RootCause.CROSS_FILE_CONTRACT,
        RootCause.TIER_ESCALATION,
        RootCause.UNFILLED_STUB,
    ):
        assert resolve_operational_action(cause).actionable is True


def test_actionable_failure_outranks_environmental_in_summary(tmp_path):
    run_dir = tmp_path / "run-020" / "plan-ingestion"
    run_dir.mkdir(parents=True)
    _write(run_dir / "prime-result.json", {"success": False, "succeeded": 0, "failed": 2})
    _write(
        run_dir / "prime-postmortem-report.json",
        {
            "aggregate_verdict": "FAIL",
            "total_features": 2,
            "successful_features": 0,
            "failed_features": 2,
            "features": [
                # Environmental, higher raw severity (high) but NOT actionable.
                {"feature_id": "infra", "success": False,
                 "root_cause": "ollama_circuit_breaker", "pipeline_stage": "ollama_generation"},
                # Actionable code fix, medium severity.
                {"feature_id": "code", "success": False,
                 "root_cause": "tier_escalation", "pipeline_stage": "ollama_generation"},
            ],
        },
    )
    report = run_service_assistant(run_dir, emit=False)
    # The actionable 'code' failure must be the headline despite lower severity.
    assert report.summary.top_recommendation.startswith("code ")


# --- Broadened detection (HOWL) ---------------------------------------------

def test_aux_error_sources_detected(tmp_path):
    run_dir = tmp_path / "run-021" / "plan-ingestion"
    (run_dir / "checkpoints").mkdir(parents=True)
    _write(run_dir / "checkpoints" / "phase1.checkpoint.json", {"status": "failed"})
    _write(run_dir / "checkpoints" / "phase2.checkpoint.json", {"status": "ok"})
    _write(run_dir / "PI-007-error.json", {"error": "boom"})
    errors_dir = run_dir / ".startd8" / "task_errors"
    errors_dir.mkdir(parents=True)
    (errors_dir / "errors.jsonl").write_text('{"e":1}\n{"e":2}\n', encoding="utf-8")

    aux = detector.scan_aux_error_sources(run_dir)
    assert aux.failed_checkpoints == 1  # only the failed one
    assert aux.pi_errors == 1
    assert aux.task_errors == 2
    assert aux.total == 4


def test_aux_signals_make_run_actionable_without_result(tmp_path):
    run_dir = tmp_path / "run-022" / "plan-ingestion"
    (run_dir / "checkpoints").mkdir(parents=True)
    _write(run_dir / "checkpoints" / "p.checkpoint.json", {"status": "failed"})

    det = detector.detect_run(run_dir)
    assert not det.run_sentinel_present
    assert det.actionable  # aux signals alone make it worth triaging
