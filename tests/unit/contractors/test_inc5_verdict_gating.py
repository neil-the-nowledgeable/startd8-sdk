"""Inc-5: aggregate any-error rule (REQ-CKG-245).

A cross-file contract error is build-breaking and must cap the batch verdict at FAIL
independent of the mean disk score — which otherwise dilutes a single failing feature
away (the score-vs-reality inversion the CRP found: 1 zeroed feature in ~13 -> ~0.92 -> PASS).

(REQ-CKG-240 synchronous verdict *consumption* into the run result / exit code is a
separate, larger change in the prime_contractor run path — tracked, not in this test.)
"""

from __future__ import annotations

from startd8.contractors.prime_postmortem import FeaturePostMortem, PrimePostMortemEvaluator

_cap = PrimePostMortemEvaluator._cap_verdict_on_cross_file_errors


def _feat(fid, verdict, success=True):
    return FeaturePostMortem(
        feature_id=fid, name=fid, status="completed", success=success,
        generated_files=[], verdict=verdict,
    )


def test_single_cross_file_fail_in_large_batch_forces_fail():
    # 12 clean features + 1 cross-file FAIL: mean disk score ≈ 0.92 -> would be PASS.
    feats = [_feat(f"F{i}", "PASS") for i in range(12)]
    feats.append(_feat("BAD", "FAIL:cross_file", success=False))
    assert _cap(feats, "PASS") == "FAIL"          # the dilution must NOT win
    assert _cap(feats, "PARTIAL") == "FAIL"


def test_no_cross_file_error_preserves_verdict():
    feats = [_feat("F0", "PASS"), _feat("F1", "PASS")]
    assert _cap(feats, "PASS") == "PASS"
    assert _cap(feats, "PARTIAL") == "PARTIAL"
    assert _cap(feats, "FAIL") == "FAIL"


def test_other_failure_kinds_do_not_trigger_the_cross_file_cap():
    # A non-cross-file failure verdict is governed by the normal mean/threshold logic,
    # not this rule (this rule only reacts to FAIL:cross_file).
    feats = [_feat("F0", "PASS"), _feat("F1", "FAIL:semantic", success=False)]
    assert _cap(feats, "PASS") == "PASS"


def test_empty_features_returns_input_verdict():
    assert _cap([], "PASS") == "PASS"
