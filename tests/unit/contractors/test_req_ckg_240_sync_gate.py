"""REQ-CKG-240 — synchronous verdict consumption (cross-file gate).

The cross-file verifier verdict must GATE the run: folded into ``result_dict``
(and the CLI exit code) before ``PrimeContractor.run()`` returns, not computed in
a detached ``daemon=False`` thread that runs after the result is already out.

Covers:
- :func:`apply_cross_file_gate` folding the verdict into ``result_dict``;
- the real #4/#11 path: ``_evaluate_cross_file_integrity`` flips the Zod feature
  to ``FAIL:cross_file`` → the gate reports a non-PASS, build-breaking failure;
- NFR-5 determinism: repeated evaluation yields an identical verdict;
- :func:`evaluate_prime_postmortem_sync` runs inline (returns a report, not a
  Thread).
"""

from __future__ import annotations

import threading
from pathlib import Path
from types import SimpleNamespace

from startd8.contractors.prime_postmortem import (
    FeaturePostMortem,
    PrimePostMortemEvaluator,
    PrimePostMortemReport,
    apply_cross_file_gate,
    evaluate_prime_postmortem_sync,
)

FIX = Path(__file__).parents[1] / "validators" / "fixtures"
PRISMA = FIX / "run008_schema.prisma"
ZOD = FIX / "run008_value_model.ts"


def _run008_features():
    """Fresh feature objects mirroring the run-008 cross-file failure class."""
    prisma_feat = FeaturePostMortem(
        feature_id="PI-010", name="prisma schema", status="completed", success=True,
        generated_files=[str(PRISMA)], verdict="PASS", requirement_score=1.0,
    )
    zod_feat = FeaturePostMortem(
        feature_id="PI-011", name="zod value-model", status="completed", success=True,
        generated_files=[str(ZOD)], verdict="PASS", requirement_score=1.0,
    )
    return [prisma_feat, zod_feat]


def _report(features, verdict, score=0.0):
    # apply_cross_file_gate only reads features / aggregate_verdict /
    # aggregate_score — a duck-typed stand-in keeps the test focused on the seam.
    return SimpleNamespace(
        features=features, aggregate_verdict=verdict, aggregate_score=score
    )


class TestApplyCrossFileGate:
    def test_gate_fails_on_cross_file_error(self):
        feats = _run008_features()
        feats[1].verdict = "FAIL:cross_file"
        feats[1].success = False
        feats[1].error_message = "Zod field 'value' diverges from Prisma model"
        result_dict = {"processed": 2, "succeeded": 2, "failed": 0}

        gate = apply_cross_file_gate(result_dict, _report(feats, "FAIL"))

        assert gate["passed"] is False
        assert result_dict["cross_file_gate"]["passed"] is False
        assert result_dict["postmortem_verdict"] == "FAIL"
        ids = [f["feature_id"] for f in gate["cross_file_failures"]]
        assert ids == ["PI-011"]
        assert gate["cross_file_failures"][0]["error_message"]

    def test_gate_passes_clean_batch(self):
        feats = _run008_features()  # both PASS
        result_dict = {"processed": 2, "succeeded": 2, "failed": 0}

        gate = apply_cross_file_gate(result_dict, _report(feats, "PASS", 1.0))

        assert gate["passed"] is True
        assert gate["available"] is True  # explicit availability (vs a skipped gate)
        assert gate["cross_file_failures"] == []
        assert result_dict["cross_file_gate"]["passed"] is True
        assert result_dict["postmortem_verdict"] == "PASS"


class TestRealEvaluationGates:
    """The #4/#11 acceptance: a real cross-file divergence yields a non-PASS gate."""

    def test_run008_divergence_fails_the_gate(self):
        feats = _run008_features()
        ev = PrimePostMortemEvaluator()
        ev._evaluate_cross_file_integrity(feats, project_root=str(FIX))

        # the evaluator flipped the Zod consumer to a cross-file failure
        assert any(f.verdict == "FAIL:cross_file" for f in feats)

        result_dict = {"processed": 2, "succeeded": 2, "failed": 0}
        gate = apply_cross_file_gate(result_dict, _report(feats, "FAIL"))

        # consumable, non-PASS result — not just a log line in a detached thread
        assert gate["passed"] is False
        assert result_dict["cross_file_gate"]["passed"] is False

    def test_nfr5_determinism_repeated_evaluation(self):
        verdicts = set()
        for _ in range(20):
            feats = _run008_features()
            PrimePostMortemEvaluator()._evaluate_cross_file_integrity(
                feats, project_root=str(FIX)
            )
            result_dict: dict = {}
            gate = apply_cross_file_gate(result_dict, _report(feats, "FAIL"))
            verdicts.add((gate["passed"], tuple(
                f["feature_id"] for f in gate["cross_file_failures"]
            )))
        # identical verdict every time — no race, no flake
        assert verdicts == {(False, ("PI-011",))}


class TestSyncEntryRunsInline:
    def test_returns_report_not_thread(self, tmp_path):
        queue = SimpleNamespace(features={})
        result_dict = {
            "processed": 0, "succeeded": 0, "failed": 0,
            "history": [], "progress": {},
        }
        report = evaluate_prime_postmortem_sync(
            result_dict=result_dict,
            queue=queue,
            seed_path=None,
            output_dir=str(tmp_path),
            project_root=str(tmp_path),
        )
        assert not isinstance(report, threading.Thread)
        assert isinstance(report, PrimePostMortemReport)
        assert hasattr(report, "aggregate_verdict")
