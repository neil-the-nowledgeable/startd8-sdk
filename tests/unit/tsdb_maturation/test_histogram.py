"""M7 histogram → stats table tests (FR-13)."""

from __future__ import annotations

import math

import pytest

from startd8.languages.prisma_parser import parse_prisma_schema
from startd8.tsdb_maturation import (
    HistogramFamily,
    Series,
    compute_histogram_stats,
    detect_histogram_family,
    histogram_payload,
    histogram_quantile,
    infer_histogram_schema,
)


# --------------------------------------------------------------------------- #
# Family detection.                                                            #
# --------------------------------------------------------------------------- #
def test_detect_histogram_family():
    names = ["http_request_duration_seconds_bucket", "http_request_duration_seconds_sum",
             "http_request_duration_seconds_count", "other_metric"]
    fam = detect_histogram_family(names)
    assert fam is not None
    assert fam.base == "http_request_duration_seconds"
    assert fam.bucket_metric.endswith("_bucket")
    assert fam.sum_metric.endswith("_sum")
    assert fam.count_metric.endswith("_count")


def test_detect_requires_all_three_members():
    assert detect_histogram_family(["x_bucket", "x_sum"]) is None       # no _count
    assert detect_histogram_family(["x_sum", "x_count"]) is None        # no _bucket
    assert detect_histogram_family(["gauge_metric"]) is None


# --------------------------------------------------------------------------- #
# histogram_quantile — the core algorithm, validated against known values.     #
# --------------------------------------------------------------------------- #
def test_quantile_linear_interpolation():
    # 10 obs: 5 in (0,1], 3 in (1,2], 2 in (2,+Inf]. Cumulative: le1=5, le2=8, Inf=10.
    buckets = [(1.0, 5.0), (2.0, 8.0), (math.inf, 10.0)]
    # p50 → rank 5.0 → at the boundary of the first bucket → 1.0
    assert histogram_quantile(0.5, buckets) == pytest.approx(1.0)
    # p90 → rank 9.0 → in the +Inf bucket → largest finite bound (2.0)
    assert histogram_quantile(0.9, buckets) == pytest.approx(2.0)
    # p70 → rank 7.0 → within (1,2]: 1 + (2-1)*((7-5)/(8-5)) = 1.6667
    assert histogram_quantile(0.7, buckets) == pytest.approx(1.0 + (2.0 / 3.0))


def test_quantile_first_bucket_interpolates_from_zero():
    buckets = [(10.0, 4.0), (20.0, 4.0), (math.inf, 4.0)]
    # p50 → rank 2.0, within (0,10]: 0 + 10*(2/4) = 5.0
    assert histogram_quantile(0.5, buckets) == pytest.approx(5.0)


def test_quantile_empty_or_zero_is_nan():
    assert math.isnan(histogram_quantile(0.5, []))
    assert math.isnan(histogram_quantile(0.5, [(1.0, 0.0), (math.inf, 0.0)]))


def test_quantile_unsorted_buckets_are_sorted():
    buckets = [(math.inf, 10.0), (2.0, 8.0), (1.0, 5.0)]
    assert histogram_quantile(0.5, buckets) == pytest.approx(1.0)


def test_quantile_clamps_out_of_range():
    buckets = [(1.0, 5.0), (math.inf, 10.0)]
    assert histogram_quantile(-0.1, buckets) == pytest.approx(1.0)  # q<=0 → first bound
    assert histogram_quantile(1.5, buckets) == pytest.approx(1.0)   # q>=1 → largest finite


# --------------------------------------------------------------------------- #
# Stats computation from the three families.                                   #
# --------------------------------------------------------------------------- #
def _bucket(le, val, **labels):
    return Series(labels={"le": le, **labels}, value=val, timestamp=0.0)


def test_compute_stats_single_identity():
    buckets = [
        _bucket("1", 5.0, route="/a"), _bucket("2", 8.0, route="/a"), _bucket("+Inf", 10.0, route="/a"),
    ]
    sums = [Series(labels={"route": "/a"}, value=14.0, timestamp=0.0)]
    counts = [Series(labels={"route": "/a"}, value=10.0, timestamp=0.0)]
    rows = compute_histogram_stats(buckets, sums, counts, percentiles=(0.5, 0.9))
    assert len(rows) == 1
    row = rows[0]
    assert row.labels == {"route": "/a"}
    assert row.count == 10
    assert float(row.sum) == pytest.approx(14.0)
    assert float(row.mean) == pytest.approx(1.4)
    assert row.quantiles[0.5] == pytest.approx(1.0)
    assert row.quantiles[0.9] == pytest.approx(2.0)


def test_compute_stats_groups_by_non_le_labels():
    buckets = [
        _bucket("1", 3.0, route="/a"), _bucket("+Inf", 6.0, route="/a"),
        _bucket("1", 1.0, route="/b"), _bucket("+Inf", 4.0, route="/b"),
    ]
    sums = [Series(labels={"route": "/a"}, value=6.0, timestamp=0.0),
            Series(labels={"route": "/b"}, value=8.0, timestamp=0.0)]
    counts = [Series(labels={"route": "/a"}, value=6.0, timestamp=0.0),
              Series(labels={"route": "/b"}, value=4.0, timestamp=0.0)]
    rows = compute_histogram_stats(buckets, sums, counts)
    by_route = {tuple(r.labels.items()): r for r in rows}
    assert len(rows) == 2
    assert by_route[(("route", "/a"),)].count == 6
    assert by_route[(("route", "/b"),)].count == 4


# --------------------------------------------------------------------------- #
# Stats-table schema (the distinct inference path).                            #
# --------------------------------------------------------------------------- #
def test_infer_histogram_schema_columns():
    buckets = [_bucket("1", 5.0, route="/a"), _bucket("+Inf", 10.0, route="/a")]
    sums = [Series(labels={"route": "/a"}, value=14.0, timestamp=0.0)]
    counts = [Series(labels={"route": "/a"}, value=10.0, timestamp=0.0)]
    rows = compute_histogram_stats(buckets, sums, counts)
    family = HistogramFamily(base="http_request_duration_seconds")
    result = infer_histogram_schema(family, rows, entity_name="RequestLatency")

    assert result.schema.errors == ()
    assert result.schema.unrenderable == ()
    m = parse_prisma_schema(result.schema_text).model("RequestLatency")
    assert m is not None
    # stat columns present with the right types
    assert m.field("count").type == "Int"
    assert m.field("sum").type == "Decimal"
    assert m.field("mean").type == "Decimal"
    assert m.field("p50").type == "Decimal"
    assert m.field("p99").type == "Decimal"
    assert m.field("route").type == "String"      # the non-le label
    assert m.field("observedAt").type == "DateTime"
    # identity is the non-le label
    assert set(result.identity_fields) == {"route"}
    # `le` is consumed, NOT a column
    assert m.field("le") is None


def test_histogram_payload_round_trips_stats():
    buckets = [_bucket("1", 5.0, route="/a"), _bucket("+Inf", 10.0, route="/a")]
    sums = [Series(labels={"route": "/a"}, value=14.0, timestamp=0.0)]
    counts = [Series(labels={"route": "/a"}, value=10.0, timestamp=0.0)]
    rows = compute_histogram_stats(buckets, sums, counts, percentiles=(0.5, 0.9))
    family = HistogramFamily(base="hist")
    result = infer_histogram_schema(family, rows, entity_name="RequestLatency", percentiles=(0.5, 0.9))
    payload = histogram_payload(family, rows, result, percentiles=(0.5, 0.9))
    row = payload["RequestLatency"][0]
    assert row["route"] == "/a"
    assert row["count"] == 10
    assert row["mean"] == "1.4"
    assert row["p50"] == "1.0"
    assert "observedAt" in row
