"""FR-14 — cost-aware remediation: $0 deterministic failures must not be told to regenerate."""

from startd8.contractors.prime_postmortem import RootCause
from startd8.service_assistant.operational_actions import (
    DETERMINISTIC_STRATEGY,
    apply_cost_overlay,
    resolve_operational_action,
)
from startd8.service_assistant.triage import synthesize_triage


def test_zero_cost_overrides_to_fix_generator():
    op = resolve_operational_action(RootCause.DUPLICATE_IMPORT)
    assert op.re_run_strategy == "regenerate_clean"  # default (LLM-path) advice
    overlaid, deterministic = apply_cost_overlay(op, RootCause.DUPLICATE_IMPORT, cost_usd=0.0)
    assert deterministic is True
    assert overlaid.re_run_strategy == DETERMINISTIC_STRATEGY
    assert "re-run reproduces" in overlaid.action  # names the idempotency, not "regenerate"
    assert "import" in overlaid.action and "redefinition" in overlaid.action  # the real F811 fix


def test_nonzero_cost_keeps_default():
    op = resolve_operational_action(RootCause.DUPLICATE_IMPORT)
    overlaid, deterministic = apply_cost_overlay(op, RootCause.DUPLICATE_IMPORT, cost_usd=0.0031)
    assert deterministic is False
    assert overlaid is op  # unchanged for an LLM-path failure


def test_unknown_cost_keeps_default():
    op = resolve_operational_action(RootCause.TIER_ESCALATION)
    overlaid, deterministic = apply_cost_overlay(op, RootCause.TIER_ESCALATION, cost_usd=None)
    assert deterministic is False
    assert overlaid is op


def test_generic_zero_cost_cause():
    op = resolve_operational_action(RootCause.AST_FAILURE)
    overlaid, deterministic = apply_cost_overlay(op, RootCause.AST_FAILURE, cost_usd=0.0)
    assert deterministic is True
    assert overlaid.re_run_strategy == DETERMINISTIC_STRATEGY
    assert "ast_failure" in overlaid.action


def test_run028_shape_end_to_end():
    """The exact run-028 shape: $0 deterministic duplicate_import → fix_deterministic_generator."""
    class _Det:
        run_sentinel_present = True
        postmortem_present = True
        run_sentinel = None
        postmortem_sentinel = "x"
        output_dir = __import__("pathlib").Path(".")

    # Drive synthesize_triage via its readers by monkeypatching the JSON loads.
    import startd8.service_assistant.triage as T

    report = {
        "aggregate_verdict": "FAIL", "total_features": 1, "successful_features": 0,
        "failed_features": 1, "cost_summary": {"total_usd": 0.0},
        "features": [{
            "feature_id": "PI-001", "success": False, "cost_usd": 0.0,
            "root_cause": "duplicate_import", "pipeline_stage": "repair",
            "error_message": "F811 Redefinition of unused `resolve_matches`",
            "target_files": ["app/jobs.py"],
        }],
    }
    failures = T._failures_from_report(report, occurrences={})
    assert len(failures) == 1
    f = failures[0]
    assert f.deterministic is True
    assert f.recommended_action.re_run_strategy == DETERMINISTIC_STRATEGY
    assert "regenerate" not in f.recommended_action.action.lower()
