"""M1 specimen tests (FR-2, FR-9).

Covers: raw record-per-series flattening + the raw invariant (R1-F9), grain honesty with the
least-trusted default (FR-9 §0.1 fail-safe), the FR-4 raw-input guard (assert_raw), reserved
record-key collision refusal, JSON round-trip, and the dry-run summary.
"""

from __future__ import annotations

import json

import pytest

from startd8.tsdb_maturation.reader import ReadResult, Series
from startd8.tsdb_maturation.specimen import (
    Grain,
    Specimen,
    SpecimenError,
    flatten_series,
    load_specimen,
    summarize,
    write_specimen,
)


def _series(labels, value, ts=1_700_000_000.0):
    return Series(labels=labels, value=value, timestamp=ts)


def _read_result(series, metric="gov_expenditure_amount", lookback="3000d"):
    return ReadResult(metric=metric, lookback=lookback, series=tuple(series))


# --------------------------------------------------------------------------- #
# Flattening — one record per series, correct shape (FR-2).                      #
# --------------------------------------------------------------------------- #
def test_flatten_series_shape():
    records = flatten_series([_series({"department": "corrections", "fiscal_year": "2025"}, 1000000.5)])
    assert len(records) == 1
    rec = records[0]
    assert rec["department"] == "corrections"
    assert rec["fiscal_year"] == "2025"
    assert rec["value"] == pytest.approx(1000000.5)
    assert rec["observed_at"] == "2023-11-14T22:13:20Z"  # deterministic ISO-8601 UTC


def test_flatten_refuses_reserved_key_collision():
    # A label literally named "value" would shadow the measure → refuse loudly.
    with pytest.raises(SpecimenError):
        flatten_series([_series({"value": "oops", "department": "x"}, 1.0)])


# --------------------------------------------------------------------------- #
# Raw invariant (R1-F9) — record count == series count, aggregated=False.        #
# --------------------------------------------------------------------------- #
def test_from_read_result_is_raw_and_one_per_series():
    series = [
        _series({"department": "corrections"}, 1.0),
        _series({"department": "health"}, 2.0),
        _series({"department": "education"}, 3.0),
    ]
    spec = Specimen.from_read_result(_read_result(series))
    assert spec.n_records == len(series) == 3
    assert spec.aggregated is False
    assert spec.metric == "gov_expenditure_amount"
    assert spec.lookback == "3000d"


# --------------------------------------------------------------------------- #
# Grain honesty (FR-9) — least-trusted default on unknown/missing.              #
# --------------------------------------------------------------------------- #
def test_tsdb_read_defaults_to_least_trusted_grain():
    spec = Specimen.from_read_result(_read_result([_series({"a": "b"}, 1.0)]))
    assert spec.grain is Grain.TSDB_AGGREGATE


def test_grain_coerce_unknown_defaults_to_tsdb_aggregate():
    assert Grain.coerce("bananas") is Grain.TSDB_AGGREGATE
    assert Grain.coerce(None) is Grain.TSDB_AGGREGATE
    assert Grain.coerce("") is Grain.TSDB_AGGREGATE


def test_grain_coerce_preserves_known_values():
    assert Grain.coerce("import_source") is Grain.IMPORT_SOURCE
    assert Grain.coerce("tsdb_aggregate") is Grain.TSDB_AGGREGATE
    assert Grain.coerce(Grain.IMPORT_SOURCE) is Grain.IMPORT_SOURCE


def test_from_records_lossless_source_grain():
    spec = Specimen.from_records(
        "m", [{"a": "x", "value": 1.0, "observed_at": "2025-01-01T00:00:00Z"}]
    )
    assert spec.grain is Grain.IMPORT_SOURCE  # lossless source default


# --------------------------------------------------------------------------- #
# FR-4 raw-input guard (R1-F9) — aggregated specimen must not reach identity.    #
# --------------------------------------------------------------------------- #
def test_assert_raw_passes_for_raw_specimen():
    spec = Specimen.from_read_result(_read_result([_series({"a": "b"}, 1.0)]))
    assert spec.assert_raw() is spec  # chainable, no raise


def test_assert_raw_raises_for_aggregated_specimen():
    spec = Specimen.from_records("m", [{"a": "x", "value": 3.0}], aggregated=True)
    with pytest.raises(SpecimenError, match="RAW specimen"):
        spec.assert_raw()


# --------------------------------------------------------------------------- #
# Label helpers.                                                                #
# --------------------------------------------------------------------------- #
def test_label_keys_excludes_reserved():
    spec = Specimen.from_read_result(_read_result([_series({"dept": "c", "fy": "2025"}, 1.0)]))
    assert spec.label_keys() == ["dept", "fy"]  # no "value"/"observed_at"


def test_cardinality_counts_distinct_values():
    series = [
        _series({"dept": "corrections", "fy": "2025"}, 1.0),
        _series({"dept": "corrections", "fy": "2026"}, 2.0),
        _series({"dept": "health", "fy": "2025"}, 3.0),
    ]
    spec = Specimen.from_read_result(_read_result(series))
    assert spec.cardinality() == {"dept": 2, "fy": 2}


# --------------------------------------------------------------------------- #
# Persistence round-trip.                                                        #
# --------------------------------------------------------------------------- #
def test_write_load_round_trip(tmp_path):
    series = [_series({"dept": "corrections"}, 1.5), _series({"dept": "health"}, 2.5)]
    spec = Specimen.from_read_result(_read_result(series))
    path = write_specimen(spec, tmp_path / "specimen.json")
    assert path.exists()

    loaded = load_specimen(path)
    assert loaded.metric == spec.metric
    assert loaded.grain is spec.grain
    assert loaded.lookback == spec.lookback
    assert loaded.aggregated is spec.aggregated
    assert loaded.n_records == spec.n_records
    assert [dict(r) for r in loaded.records] == [dict(r) for r in spec.records]


def test_persisted_json_has_grain_and_count(tmp_path):
    spec = Specimen.from_read_result(_read_result([_series({"a": "b"}, 1.0)]))
    path = write_specimen(spec, tmp_path / "s.json")
    data = json.loads(path.read_text())
    assert data["grain"] == "tsdb_aggregate"
    assert data["n_records"] == 1
    assert data["aggregated"] is False
    assert data["records"][0]["value"] == pytest.approx(1.0)


def test_write_is_atomic_no_tmp_left(tmp_path):
    spec = Specimen.from_read_result(_read_result([_series({"a": "b"}, 1.0)]))
    write_specimen(spec, tmp_path / "s.json")
    assert list(tmp_path.glob("*.tmp")) == []


def test_loaded_aggregated_specimen_still_blocks_identity(tmp_path):
    # An aggregated specimen persisted then reloaded must STILL fail the FR-4 guard.
    spec = Specimen.from_records("m", [{"a": "x", "value": 3.0}], aggregated=True)
    path = write_specimen(spec, tmp_path / "agg.json")
    reloaded = load_specimen(path)
    assert reloaded.aggregated is True
    with pytest.raises(SpecimenError):
        reloaded.assert_raw()


# --------------------------------------------------------------------------- #
# Dry-run summary (FR-2 "reports counts + a sample").                            #
# --------------------------------------------------------------------------- #
def test_summary_reports_counts_and_sample():
    series = [
        _series({"dept": "corrections", "fy": "2025"}, 1.0),
        _series({"dept": "health", "fy": "2025"}, 2.0),
    ]
    spec = Specimen.from_read_result(_read_result(series))
    summary = summarize(spec)
    assert summary.n_records == 2
    assert summary.label_keys == ("dept", "fy")
    assert summary.cardinality == {"dept": 2, "fy": 1}
    assert summary.sample is not None
    text = summary.render()
    assert "records:   2" in text
    assert "least-trusted" in text  # grain honesty surfaced for a TSDB specimen


def test_summary_of_empty_specimen_has_no_sample():
    spec = Specimen.from_records("m", [], grain=Grain.IMPORT_SOURCE)
    summary = summarize(spec)
    assert summary.n_records == 0
    assert summary.sample is None
