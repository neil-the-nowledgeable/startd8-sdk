"""M5 backfill tests (FR-6/FR-8) — payload mapping + key-collapse aggregation (R1-S4)."""

from __future__ import annotations


import pytest

from startd8.tsdb_maturation import (
    Additivity,
    AggFunc,
    ReadResult,
    Series,
    Specimen,
    build_payload,
    classify_additivity,
    infer_schema,
    records_to_json,
)

ENTITY = "DepartmentBudget"


def _specimen(records, metric="gov_expenditure_amount"):
    series = [Series(labels={k: v for k, v in r.items() if k != "value"},
                     value=float(r["value"]), timestamp=1_700_000_000.0)
              for r in records]
    return Specimen.from_read_result(ReadResult(metric=metric, lookback="3000d", series=tuple(series)))


def _infer(spec):
    return infer_schema(spec, entity_name=ENTITY)


# --------------------------------------------------------------------------- #
# Additivity classification (R1-F5).                                          #
# --------------------------------------------------------------------------- #
def test_additive_metrics():
    assert classify_additivity("gov_expenditure_amount") is Additivity.ADDITIVE
    assert classify_additivity("http_requests_total") is Additivity.ADDITIVE
    assert classify_additivity("otel_histogram_sum") is Additivity.ADDITIVE
    assert classify_additivity("gov_payment_count") is Additivity.ADDITIVE


def test_non_additive_default_is_fail_safe():
    # Unknown / gauge-shaped → NEVER silently summed.
    assert classify_additivity("cpu_usage_ratio") is Additivity.NON_ADDITIVE
    assert classify_additivity("temperature_celsius") is Additivity.NON_ADDITIVE
    assert classify_additivity("some_gauge") is Additivity.NON_ADDITIVE


# --------------------------------------------------------------------------- #
# Payload mapping — raw labels → emitted field names.                          #
# --------------------------------------------------------------------------- #
def test_payload_maps_emitted_names_and_measure():
    recs = [{"department": "corrections", "fiscal_year": "2025", "source": "hfa_mi", "value": 1000000.5}]
    spec = _specimen(recs)
    res = _infer(spec)
    built = build_payload(spec, res, metric="gov_expenditure_amount")
    rows = built.payload[ENTITY]
    assert len(rows) == 1
    row = rows[0]
    assert row["department"] == "corrections"
    assert row["fiscalYear"] == "2025"
    assert row["dataSource"] == "hfa_mi"     # source → dataSource (FR-11 rename)
    assert row["amount"] == "1000000.5"      # measure as canonical Decimal string
    assert row["observedAt"] == "2023-11-14T22:13:20Z"
    assert not built.collapsed


# --------------------------------------------------------------------------- #
# R1-S4 — key-collapse guard: additive metric → SUMMED, no last-writer-wins.    #
# --------------------------------------------------------------------------- #
def test_additive_collision_sums_the_measure():
    # Two DISTINCT series that collapse onto one identity when the declared key is coarser.
    recs = [
        {"department": "corrections", "fiscal_year": "2025", "fund_source": "general", "value": 100.0},
        {"department": "corrections", "fiscal_year": "2025", "fund_source": "federal", "value": 25.5},
    ]
    spec = _specimen(recs)
    # Declare a COARSE identity (department, fiscal_year) that collapses the two fund_source series.
    res = infer_schema(spec, entity_name=ENTITY, identity=["department", "fiscal_year"])
    built = build_payload(spec, res, metric="gov_expenditure_amount")
    assert built.collapsed
    assert built.collapsed_groups == 1
    assert built.agg_func is AggFunc.SUM
    rows = built.payload[ENTITY]
    assert len(rows) == 1                       # 2 → 1, no last-writer-wins loss
    assert rows[0]["amount"] == "125.5"         # 100.0 + 25.5, exact (Decimal)
    assert built.warnings == ()                 # additive sum is not a warning


def test_additive_sum_is_decimal_exact():
    # Financial fidelity: 0.1 + 0.2 must be 0.3 (Decimal), not 0.30000000000000004 (float).
    recs = [
        {"department": "d", "fiscal_year": "2025", "fund_source": "a", "value": 0.1},
        {"department": "d", "fiscal_year": "2025", "fund_source": "b", "value": 0.2},
    ]
    spec = _specimen(recs)
    res = infer_schema(spec, entity_name=ENTITY, identity=["department", "fiscal_year"])
    built = build_payload(spec, res, metric="gov_expenditure_amount")
    assert built.payload[ENTITY][0]["amount"] == "0.3"


# --------------------------------------------------------------------------- #
# R1-S4 — non-additive negative: gauge → NOT blindly summed (last + warning).   #
# --------------------------------------------------------------------------- #
def test_non_additive_collision_is_not_summed():
    recs = [
        {"host": "a", "region": "us", "value": 40.0},
        {"host": "b", "region": "us", "value": 90.0},
    ]
    spec = _specimen(recs, metric="cpu_usage_ratio")
    res = infer_schema(spec, entity_name="CpuUsage", identity=["region"])  # collapse both hosts
    built = build_payload(spec, res, metric="cpu_usage_ratio")
    assert built.collapsed
    assert built.agg_func is AggFunc.LAST
    rows = built.payload["CpuUsage"]
    assert len(rows) == 1
    # measure kept `last` (90.0), NOT summed to 130.0
    assert rows[0][res.measure_field] == "90.0"
    assert any("non-additive" in w for w in built.warnings)  # loud warning


def test_explicit_aggregate_override_wins():
    recs = [
        {"host": "a", "region": "us", "value": 40.0},
        {"host": "b", "region": "us", "value": 90.0},
    ]
    spec = _specimen(recs, metric="cpu_usage_ratio")
    res = infer_schema(spec, entity_name="CpuUsage", identity=["region"])
    # Force sum despite non-additive classification.
    built = build_payload(spec, res, metric="cpu_usage_ratio", aggregate="sum")
    assert built.agg_func is AggFunc.SUM
    assert built.payload["CpuUsage"][0][res.measure_field] == "130.0"


def test_avg_aggregate():
    recs = [
        {"region": "us", "shard": "a", "value": 10.0},
        {"region": "us", "shard": "b", "value": 20.0},
    ]
    spec = _specimen(recs, metric="queue_depth")
    res = infer_schema(spec, entity_name="QueueDepth", identity=["region"])
    built = build_payload(spec, res, metric="queue_depth", aggregate="avg")
    assert built.payload["QueueDepth"][0][res.measure_field] == "15.0"


# --------------------------------------------------------------------------- #
# records_to_json convenience + raw-input guard.                               #
# --------------------------------------------------------------------------- #
def test_records_to_json_serializes():
    import json

    recs = [{"department": "corrections", "fiscal_year": "2025", "value": 100.0}]
    spec = _specimen(recs)
    res = _infer(spec)
    text, built = records_to_json(spec, res, metric="gov_expenditure_amount")
    parsed = json.loads(text)
    assert parsed[ENTITY][0]["amount"] == "100.0"
    assert built.rows_out == 1


def test_aggregated_specimen_rejected():
    spec = Specimen.from_records("m", [{"a": "1", "value": 3.0}], aggregated=True)
    res = infer_schema(Specimen.from_records("m", [{"a": "1", "value": 3.0}, {"a": "2", "value": 4.0}]),
                       entity_name="T")
    with pytest.raises(Exception):  # assert_raw
        build_payload(spec, res, metric="m")
