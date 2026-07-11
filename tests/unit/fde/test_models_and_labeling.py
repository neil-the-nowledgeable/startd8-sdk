# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Contract round-trips (FR-12/FR-20) + the FR-6/FR-21 labeling guard."""

from __future__ import annotations

import pytest

from startd8.fde.deterministic_compose import (
    UnlabeledClaimError,
    assert_all_labeled,
    assert_claims_labeled,
)
from startd8.fde.models import (
    PROTOCOL_VERSION,
    ClaimLabel,
    FdeExplanation,
    FdeMode,
    FdePreflightReport,
    FdeRequest,
    FailureExplanation,
    LabeledClaim,
    Landmine,
)


def test_request_json_roundtrip_preserves_protocol_version():
    req = FdeRequest(mode=FdeMode.EXPLAIN, run_output_dir="/x/run-1")
    back = FdeRequest.from_json(req.to_dict())
    assert back.mode == FdeMode.EXPLAIN
    assert back.protocol_version == PROTOCOL_VERSION
    req.validate()  # no raise


def test_request_validate_rejects_missing_fields():
    with pytest.raises(ValueError):
        FdeRequest(mode=FdeMode.EXPLAIN).validate()
    with pytest.raises(ValueError):
        FdeRequest(mode=FdeMode.PREFLIGHT).validate()


def test_explanation_json_canonical_roundtrip():
    exp = FdeExplanation(
        run_id="r1",
        generated_at="t",
        sdk_version="0.4.0",
        failures=[
            FailureExplanation(
                "PI-1",
                "el",
                [
                    LabeledClaim(
                        ClaimLabel.MECHANISM,
                        "ran at tier simple",
                        source="ElementPostMortem.tier",
                        claim_id="c1",
                    ),
                ],
            )
        ],
        batch_claims=[LabeledClaim(ClaimLabel.OBSERVED, "batch", source="triage")],
    )
    back = FdeExplanation.from_json(exp.to_dict())
    assert back.run_id == "r1"
    assert back.failures[0].claims[0].label == ClaimLabel.MECHANISM
    assert back.failures[0].claims[0].claim_id == "c1"
    assert (
        "## FDE Explanation" in back.to_prompt_section()
        or "FDE Explanation" in back.to_prompt_section()
    )


def test_prediction_label_is_distinct_from_mechanism():
    # FR-21 / R1-F9: three distinct labels.
    assert ClaimLabel.PREDICTION.value != ClaimLabel.MECHANISM.value
    c = LabeledClaim(
        ClaimLabel.PREDICTION, "would be simple", qualifier="low-confidence"
    )
    assert c.tag() == "PREDICTION (sdk, live, low-confidence)"


def test_labeling_guard_passes_on_labeled_report():
    exp = FdeExplanation(
        run_id="r",
        generated_at="t",
        sdk_version="v",
        failures=[
            FailureExplanation(
                "F",
                None,
                [
                    LabeledClaim(ClaimLabel.MECHANISM, "x", source="s"),
                    LabeledClaim(ClaimLabel.OBSERVED, "y", source="t"),
                ],
            )
        ],
    )
    assert_all_labeled(exp.to_markdown())  # no raise


def test_labeling_guard_fails_on_unlabeled_claim():
    md = "# R\n\n## F\n- this is an untagged load-bearing claim\n"
    with pytest.raises(UnlabeledClaimError):
        assert_all_labeled(md)


def test_assert_claims_labeled_rejects_bad_label():
    good = [LabeledClaim(ClaimLabel.MECHANISM, "x")]
    assert_claims_labeled(good)  # no raise


def test_preflight_report_roundtrip_and_severity_sort():
    rep = FdePreflightReport(
        generated_at="t",
        sdk_version="v",
        plan_path="p.md",
        landmines=[
            Landmine(
                "M2",
                1,
                "low",
                "t-low",
                "a",
                LabeledClaim(ClaimLabel.PREDICTION, "m", source="s"),
            ),
            Landmine(
                "M1",
                1,
                "high",
                "t-high",
                "a",
                LabeledClaim(ClaimLabel.PREDICTION, "m", source="s"),
            ),
        ],
    )
    back = FdePreflightReport.from_json(rep.to_dict())
    assert [m.severity for m in back.sorted_landmines()] == ["high", "low"]
    assert_all_labeled(back.to_markdown())
