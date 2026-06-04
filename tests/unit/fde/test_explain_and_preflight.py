# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Explain composition (FR-4/6/7/25), idempotency (FR-19), preflight (FR-8/23), bridge (FR-24)."""

from __future__ import annotations

import json

from startd8.fde import run_fde_explain, run_fde_preflight
from startd8.fde.models import ClaimLabel


def test_explain_composes_observed_and_mechanism(run_dir, project_root):
    out = run_fde_explain(run_dir, project_root=project_root, emit=False)
    exp = out.explanation
    assert exp.evidence_available is True
    labels = {c.label for c in exp.all_claims()}
    assert ClaimLabel.OBSERVED in labels  # SA evidence half
    assert ClaimLabel.MECHANISM in labels  # SDK mechanism half
    assert out.report_path.exists()


def test_explain_flags_deterministic_correction(run_dir, project_root):
    # FR-7: SA said regenerate_clean but failure is deterministic → futile; FDE corrects.
    out = run_fde_explain(run_dir, project_root=project_root, emit=False)
    assert out.explanation.failures[0].correction is not None
    assert "idempotent" in out.explanation.failures[0].correction


def test_explain_includes_batch_pattern(run_dir, project_root):
    out = run_fde_explain(run_dir, project_root=project_root, emit=False)
    assert any("batch pattern" in c.text for c in out.explanation.batch_claims)


def test_explain_writes_back_ref_to_triage(run_dir, project_root):
    # FR-24: explain atomically patches service-assistant-triage.json with fde_explanation.
    out = run_fde_explain(run_dir, project_root=project_root, emit=False)
    assert out.ref_attached is True
    triage = json.loads((run_dir / "service-assistant-triage.json").read_text())
    assert triage["fde_explanation"]["report_path"].endswith("fde-explanation.md")
    assert triage["fde_explanation"]["checksum"].startswith("sha256:")


def test_explain_idempotent_no_op_on_second_call(run_dir, project_root):
    # FR-19: re-invocation on unchanged inputs is a no-op (write-back must not invalidate key).
    assert (
        run_fde_explain(run_dir, project_root=project_root, emit=False).skipped is False
    )
    assert (
        run_fde_explain(run_dir, project_root=project_root, emit=False).skipped is True
    )


def test_explain_recomputes_when_mechanism_artifact_changes(run_dir, project_root):
    # FR-19 / R1-F12: a regenerated prime-result must re-explain, not serve stale.
    run_fde_explain(run_dir, project_root=project_root, emit=False)
    (run_dir / "prime-result.json").write_text(
        json.dumps(
            {
                "history": [
                    {
                        "generation_metadata": {
                            "micro_prime_file_results": [
                                {
                                    "element_results": [
                                        {
                                            "element_name": "resolve_matches",
                                            "generation_strategy": "llm_simple",
                                        }
                                    ]
                                }
                            ]
                        }
                    }
                ]
            }
        )
    )
    assert (
        run_fde_explain(run_dir, project_root=project_root, emit=False).skipped is False
    )


def test_explain_degrades_without_triage(tmp_path):
    run = tmp_path / "run-x"
    run.mkdir()
    out = run_fde_explain(run, project_root=tmp_path, emit=False)
    assert out.explanation.evidence_available is False
    assert out.ref_attached is False


def test_preflight_flags_unsupported_language_and_redacts(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan\nBuild it in Rust.\nAPI_KEY=sk-ant-AAAAAAAAAAAAAAAA\n")
    out = run_fde_preflight(plan_path=plan, project_root=tmp_path, emit=False)
    assert any("rust" in m.title for m in out.report.landmines)
    assert out.report.redaction_manifest  # FR-23: secret was stripped
    assert out.report_path.exists()


def test_preflight_track2_disabled_records_skip(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text("# Plan\nA Python service.\n")
    out = run_fde_preflight(plan_path=plan, project_root=tmp_path, emit=False)
    assert out.report.track2_ran is False
    assert any("track2 disabled" in s for s in out.report.skipped_track2)
