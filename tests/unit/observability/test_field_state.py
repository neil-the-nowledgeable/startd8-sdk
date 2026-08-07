# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""FieldState explicit-state emission — CCbC Tier B, Phase 1.

REQ: docs/design/FIELDSTATE_EXPLICIT_STATE_REQUIREMENTS.md (§8 test list).

The seven tests below lock the Phase-1 contract:
- FR-19 serializer refusals (×4)
- FR-11/FR-18 byte-identical when the flag is OFF (both producers)
- FR-20 export-durable merge path → null+reason, NOT 0/absent
- the core discrimination: computed-0.0 ≠ not_computed-null
- FR-9 plain value DERIVED from FieldState.value (single source)
- FR-21 both producers share the serializer (drift mirror)
- FR-17 consumer parity fixture (a null-flattening reader fails it)
"""

import json
from pathlib import Path

import pytest

from startd8.observability.affordance_map_consume import merge_quality_services
from startd8.observability.artifact_generator import (
    ArtifactResult,
    _write_quality_report,
)
from startd8.observability.artifact_generator_models import (
    FIELD_STATE_NAMES,
    FieldState,
    render_field_state,
)


# ---------------------------------------------------------------------------
# Shared builders — a service whose expected metrics are NOT referenced by any
# artifact content, so `compute_metric_coverage` returns a genuine 0.0 (the
# `export-verify` computed-zero surface). The bridge/system/human orientations
# all resolve 0.0 because no content references the expected metric.
# ---------------------------------------------------------------------------

_EXPECTED = {"svc": {"app_requests_total", "app_errors_total"}}


def _artifacts():
    # A generated, scored dashboard_spec whose content references NONE of the
    # expected metrics → coverage computes to a real 0.0 (computed, not absent).
    return [
        ArtifactResult(
            artifact_type="dashboard_spec",
            service_id="svc",
            output_path="dashboards/svc-dashboard-spec.yaml",
            status="generated",
            content="title: unrelated\npanels: []\n",
            quality={"score": 0.9, "checks_passed": 9, "checks_total": 10},
        )
    ]


def _write_and_load(tmp_path: Path, *, emit_field_states: bool, service_metrics):
    out = tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    _write_quality_report(
        _artifacts(),
        out,
        service_metrics=service_metrics,
        emit_field_states=emit_field_states,
    )
    return json.loads((out / "observability-quality.json").read_text())


def _strip_volatile(report: dict) -> dict:
    """Drop the non-deterministic fields (timestamp + git sha) so byte-identity
    is asserted over the SHAPE the flag controls, not the clock or the checkout."""
    r = json.loads(json.dumps(report))  # deep copy
    r.pop("generated_at", None)
    r.pop("provenance", None)
    agg = r.get("aggregate", {})
    for k in ("sdk_sha", "sdk_sha_source"):
        agg.pop(k, None)
    return r


# ---------------------------------------------------------------------------
# 1. FR-19 — serializer refusals (×4)
# ---------------------------------------------------------------------------


class TestFieldStateSerializerRefusals:
    def test_unknown_state_refused(self):
        with pytest.raises(ValueError):
            FieldState(value=None, state="bogus", reason="x")

    def test_computed_with_none_value_refused(self):
        with pytest.raises(ValueError):
            FieldState(value=None, state="computed")

    def test_non_computed_with_value_refused(self):
        with pytest.raises(ValueError):
            FieldState(value=0.0, state="not_computed", reason="x")

    def test_non_computed_without_reason_refused(self):
        with pytest.raises(ValueError):
            FieldState(value=None, state="not_computed")
        with pytest.raises(ValueError):
            FieldState(value=None, state="not_computed", reason="")

    def test_valid_states_construct(self):
        # computed with a float + no reason; not_computed/excluded/unbound with reason.
        assert render_field_state(FieldState(0.0, "computed"))[0] == 0.0
        for st in ("not_computed", "excluded", "unbound"):
            plain, side = render_field_state(FieldState(None, st, reason="r"))
            assert plain is None
            assert side["state"] == st
        assert set(FIELD_STATE_NAMES) == {
            "computed",
            "not_computed",
            "excluded",
            "unbound",
        }


# ---------------------------------------------------------------------------
# 2. FR-18 / FR-11 — byte-identical when the flag is OFF (both producers)
# ---------------------------------------------------------------------------


class TestFlagOffByteIdentical:
    def test_producer_a_flag_off_byte_identical(self, tmp_path):
        """Producer A: flag-OFF output equals a from-scratch run with NO flag param
        (the pre-feature default). Computed keys keep their float; no field_states."""
        off = _write_and_load(
            tmp_path / "a", emit_field_states=False, service_metrics=_EXPECTED
        )
        assert "field_states" not in off
        svc = off["services"]["svc"]
        # computed-0.0 stays a plain float, present (byte-identical behaviour).
        assert svc["metric_coverage_bridge"] == 0.0
        # schema_version does NOT bump when off (FR-22).
        assert off["schema_version"] == "1.0"

    def test_producer_a_off_matches_no_flag_call(self, tmp_path):
        out1 = tmp_path / "o1"
        out2 = tmp_path / "o2"
        out1.mkdir()
        out2.mkdir()
        # Explicit flag=False vs the pre-feature call path (default False).
        _write_quality_report(
            _artifacts(), out1, service_metrics=_EXPECTED, emit_field_states=False
        )
        _write_quality_report(_artifacts(), out2, service_metrics=_EXPECTED)
        r1 = _strip_volatile(json.loads((out1 / "observability-quality.json").read_text()))
        r2 = _strip_volatile(json.loads((out2 / "observability-quality.json").read_text()))
        assert r1 == r2

    def test_producer_b_flag_off_byte_identical(self):
        """Producer B: merge with flag-OFF equals the prior merge output —
        export-durable stays ABSENT (the flag does not add the key when off)."""
        prior = {
            "services": {"svc": {"dashboard_spec": {"score": 0.9}}},
            "aggregate": {"avg_composite_score": 0.9},
        }
        merged_off = merge_quality_services(prior, {}, emit_field_states=False)
        merged_default = merge_quality_services(prior, {})
        assert merged_off == merged_default
        assert "field_states" not in merged_off
        # metric_coverage_* stays ABSENT (FR-11 absence-preserved).
        assert "metric_coverage_bridge" not in merged_off["services"]["svc"]


# ---------------------------------------------------------------------------
# 3. FR-20 — export-durable merge path → null+reason, NOT 0/absent
# ---------------------------------------------------------------------------


class TestMergePathNotComputed:
    def _prior(self):
        return {
            "services": {"svc": {"dashboard_spec": {"score": 0.9}}},
            "aggregate": {"avg_composite_score": 0.9},
        }

    def test_flag_on_renders_null_plus_reason_not_zero_not_absent(self):
        merged = merge_quality_services(self._prior(), {}, emit_field_states=True)
        svc = merged["services"]["svc"]
        # NOT absent (the original export-durable bug was absence).
        assert "metric_coverage_bridge" in svc
        # NOT 0 — explicitly null.
        assert svc["metric_coverage_bridge"] is None
        # Sidecar carries the explicit state + the contracted reason.
        fs = merged["field_states"]["svc.metric_coverage_bridge"]
        assert fs["value"] is None
        assert fs["state"] == "not_computed"
        assert fs["reason"] == "affordance-apply path; coverage not recomputed"
        assert fs["reason"]  # non-empty (FR-3)


# ---------------------------------------------------------------------------
# 4. computed-0.0 (export-verify) DISTINCT from not_computed-null (durable)
# ---------------------------------------------------------------------------


class TestComputedZeroDistinctFromNotComputed:
    def test_computed_zero_vs_not_computed_null(self, tmp_path):
        # Producer A, flag-on: expected metrics present, none referenced → real 0.0.
        on = _write_and_load(
            tmp_path / "verify", emit_field_states=True, service_metrics=_EXPECTED
        )
        verify_fs = on["field_states"]["svc.metric_coverage_bridge"]
        assert verify_fs["value"] == 0.0
        assert verify_fs["state"] == "computed"
        assert verify_fs["reason"] is None

        # Producer B, flag-on: merge path → null + not_computed.
        durable = merge_quality_services(
            {"services": {"svc": {"dashboard_spec": {"score": 0.9}}}, "aggregate": {}},
            {},
            emit_field_states=True,
        )
        durable_fs = durable["field_states"]["svc.metric_coverage_bridge"]
        assert durable_fs["value"] is None
        assert durable_fs["state"] == "not_computed"

        # The core discrimination: a computed real-zero is NOT the same disk shape
        # as a not-computed absence — the exact misread this REQ kills.
        assert verify_fs["value"] == 0.0 and durable_fs["value"] is None
        assert verify_fs["state"] != durable_fs["state"]


# ---------------------------------------------------------------------------
# 5. FR-9 — plain value DERIVED from FieldState.value (single source)
# ---------------------------------------------------------------------------


class TestPlainValueDerivedFromFieldState:
    def test_plain_key_reproducible_from_sidecar(self, tmp_path):
        on = _write_and_load(
            tmp_path / "d", emit_field_states=True, service_metrics=_EXPECTED
        )
        svc = on["services"]["svc"]
        for key, fs in on["field_states"].items():
            if not key.startswith("svc."):
                continue
            field = key.split(".", 1)[1]
            # Every migrated plain key equals its sidecar FieldState.value (FR-17 parity).
            assert svc[field] == fs["value"], key

    def test_single_serializer_derives_both_channels(self):
        # render_field_state is the ONE function producing BOTH channels; the plain
        # value it returns is fs.value verbatim (never an independent computation).
        fs = FieldState(0.42, "computed")
        plain, sidecar = render_field_state(fs)
        assert plain == fs.value == sidecar["value"] == 0.42


# ---------------------------------------------------------------------------
# 6. FR-21 — both producers share the serializer (drift mirror)
# ---------------------------------------------------------------------------


class TestBothProducersShareSerializer:
    def test_identical_field_state_for_identical_input(self):
        # Same input (a not_computed coverage field) → identical sidecar shape from
        # a direct serializer render as from the merge producer. If the producers
        # diverged (hand-rolled a dict), this drifts.
        _, direct = render_field_state(
            FieldState(
                None,
                "not_computed",
                reason="affordance-apply path; coverage not recomputed",
            )
        )
        merged = merge_quality_services(
            {"services": {"svc": {"dashboard_spec": {"score": 0.9}}}, "aggregate": {}},
            {},
            emit_field_states=True,
        )
        from_producer = merged["field_states"]["svc.metric_coverage_bridge"]
        assert from_producer == direct

    def test_both_producers_import_the_same_serializer(self):
        import startd8.observability.affordance_map_consume as amc
        import startd8.observability.artifact_generator as ag

        assert ag.render_field_state is amc.render_field_state
        assert ag.FieldState is amc.FieldState


# ---------------------------------------------------------------------------
# 7. FR-17 — consumer parity fixture (a null-flattening reader fails it)
# ---------------------------------------------------------------------------


def _grade_null_respecting(quality: dict) -> dict:
    """A reference consumer that OBEYS the null-rule (FR-14/FR-16): it averages
    only the MEASURED (computed) coverage values and counts not_computed
    separately — it NEVER flattens null → 0."""
    measured = []
    not_measured = 0
    for key, fs in quality.get("field_states", {}).items():
        if not key.startswith("svc.") or not key.endswith("metric_coverage_bridge"):
            continue
        if fs["state"] == "computed":
            measured.append(fs["value"])
        else:
            not_measured += 1
    avg = round(sum(measured) / len(measured), 4) if measured else None
    return {"avg_measured": avg, "not_measured": not_measured}


def _grade_null_flattening(quality: dict) -> dict:
    """A BROKEN consumer that flattens null → 0 (the gen-report-card.py:299
    `... or 0` anti-pattern). It must produce a DIFFERENT grade — that difference
    is what makes the fixture the safe-to-flip signal (FR-12/FR-17)."""
    vals = []
    for key, fs in quality.get("field_states", {}).items():
        if not key.startswith("svc.") or not key.endswith("metric_coverage_bridge"):
            continue
        vals.append(fs["value"] or 0)  # the bug: null → 0
    avg = round(sum(vals) / len(vals), 4) if vals else None
    return {"avg": avg}


class TestConsumerParityFixture:
    def test_null_respecting_reader_matches_expected_tristate(self, tmp_path):
        # Build a real two-surface fixture: one computed-0.0 service (Producer A)
        # and one not_computed service (Producer B merge), both flag-on.
        verify = _write_and_load(
            tmp_path / "v", emit_field_states=True, service_metrics=_EXPECTED
        )
        durable = merge_quality_services(
            {"services": {"svc": {"dashboard_spec": {"score": 0.9}}}, "aggregate": {}},
            {},
            emit_field_states=True,
        )

        # The null-rule reader: computed-0.0 is a measured 0; not_computed is tallied.
        g_verify = _grade_null_respecting(verify)
        assert g_verify == {"avg_measured": 0.0, "not_measured": 0}
        g_durable = _grade_null_respecting(durable)
        assert g_durable == {"avg_measured": None, "not_measured": 1}

    def test_flattening_reader_produces_wrong_grade(self, tmp_path):
        # On the durable (not_computed) surface, a null-flattening reader scores 0.0
        # (treating "not measured" as "measured zero") while the null-respecting
        # reader scores None — the fixture DISCRIMINATES them (FR-17).
        durable = merge_quality_services(
            {"services": {"svc": {"dashboard_spec": {"score": 0.9}}}, "aggregate": {}},
            {},
            emit_field_states=True,
        )
        correct = _grade_null_respecting(durable)  # {"avg_measured": None, ...}
        flattened = _grade_null_flattening(durable)  # {"avg": 0}
        assert correct["avg_measured"] is None
        assert flattened["avg"] == 0
        assert correct["avg_measured"] != flattened["avg"]
