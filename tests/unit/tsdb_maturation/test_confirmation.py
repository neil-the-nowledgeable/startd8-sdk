"""M2.5 confirmation-gate tests (FR-4 / R1-F7 / R1-S6).

The load-bearing acceptance is the three-case gate (R1-S6):
  1. promote without a recorded confirmation → refused;
  2. with a confirmation for the current key → allowed;
  3. re-promote after the inferred key CHANGED → re-confirmation required (STALE).
"""

from __future__ import annotations

import pytest
import yaml

from startd8.tsdb_maturation import ReadResult, Series, Specimen, infer_schema
from startd8.tsdb_maturation.confirmation import (
    LEDGER_REL,
    ConfirmationError,
    ConfirmationRequired,
    ConfirmationStatus,
    confirm_inference,
    confirmation_status,
    is_confirmed,
    load_ledger,
    record_confirmation,
    render_confirmation_surface,
    require_confirmation,
)

METRIC = "gov_expenditure_amount"
KEY = ["department", "fiscal_year"]


def _spec(records):
    series = [Series(labels=dict(r), value=float(i), timestamp=0.0) for i, r in enumerate(records)]
    return Specimen.from_read_result(ReadResult(metric=METRIC, lookback="3000d", series=tuple(series)))


def _inference(records, entity="DepartmentBudget"):
    return infer_schema(_spec(records), entity_name=entity)


# --------------------------------------------------------------------------- #
# R1-S6 case 1 — unconfirmed → refused.                                        #
# --------------------------------------------------------------------------- #
def test_unconfirmed_is_refused(tmp_path):
    assert confirmation_status(tmp_path, METRIC, KEY) is ConfirmationStatus.UNCONFIRMED
    assert not is_confirmed(tmp_path, METRIC, KEY)
    with pytest.raises(ConfirmationRequired, match="not confirmed"):
        require_confirmation(tmp_path, METRIC, KEY)


def test_absent_ledger_loads_empty(tmp_path):
    assert load_ledger(tmp_path) == {}


# --------------------------------------------------------------------------- #
# R1-S6 case 2 — confirmed key → allowed.                                      #
# --------------------------------------------------------------------------- #
def test_recorded_confirmation_allows_promotion(tmp_path):
    record_confirmation(tmp_path, METRIC, "DepartmentBudget", KEY, today="2026-07-08")
    assert confirmation_status(tmp_path, METRIC, KEY) is ConfirmationStatus.CONFIRMED
    assert is_confirmed(tmp_path, METRIC, KEY)
    require_confirmation(tmp_path, METRIC, KEY)  # does not raise


def test_confirmation_is_order_insensitive(tmp_path):
    # A composite key is a SET of columns — confirming [a,b] confirms [b,a].
    record_confirmation(tmp_path, METRIC, "T", ["department", "fiscal_year"], today="2026-07-08")
    assert is_confirmed(tmp_path, METRIC, ["fiscal_year", "department"])


def test_ledger_is_committed_yaml_at_expected_path(tmp_path):
    record_confirmation(tmp_path, METRIC, "DepartmentBudget", KEY, today="2026-07-08")
    ledger_file = tmp_path / LEDGER_REL
    assert ledger_file.is_file()
    data = yaml.safe_load(ledger_file.read_text())
    assert data["schema"] == "tsdb.confirmed.v1"
    assert data["confirmed"][METRIC]["identity"] == sorted(KEY)
    assert data["confirmed"][METRIC]["entity"] == "DepartmentBudget"
    assert data["confirmed"][METRIC]["confirmed_at"] == "2026-07-08"


def test_no_tmp_file_left(tmp_path):
    record_confirmation(tmp_path, METRIC, "T", KEY, today="2026-07-08")
    assert list((tmp_path / "docs/tsdb-maturation").glob("*.tmp")) == []


# --------------------------------------------------------------------------- #
# R1-S6 case 3 — key changed on re-promote → re-confirmation required (STALE).  #
# --------------------------------------------------------------------------- #
def test_changed_key_is_stale_and_refused(tmp_path):
    record_confirmation(tmp_path, METRIC, "DepartmentBudget", KEY, today="2026-07-08")
    changed = ["department", "fiscal_year", "fund_source"]  # key grew → different identity
    assert confirmation_status(tmp_path, METRIC, changed) is ConfirmationStatus.STALE
    with pytest.raises(ConfirmationRequired, match="changed since it was confirmed"):
        require_confirmation(tmp_path, METRIC, changed)


def test_reconfirmation_updates_the_record(tmp_path):
    record_confirmation(tmp_path, METRIC, "DepartmentBudget", KEY, today="2026-07-08")
    changed = ["department", "fiscal_year", "fund_source"]
    record_confirmation(tmp_path, METRIC, "DepartmentBudget", changed, today="2026-07-09")
    assert is_confirmed(tmp_path, METRIC, changed)
    assert not is_confirmed(tmp_path, METRIC, KEY)  # old key no longer valid
    assert load_ledger(tmp_path)[METRIC].confirmed_at == "2026-07-09"


# --------------------------------------------------------------------------- #
# End-to-end via an InferenceResult.                                           #
# --------------------------------------------------------------------------- #
def test_confirm_inference_round_trip(tmp_path):
    res = _inference([{"department": "a", "fiscal_year": "2025"},
                      {"department": "b", "fiscal_year": "2025"}])
    # department is a single-column unique key here.
    confirm_inference(tmp_path, res, METRIC, today="2026-07-08")
    require_confirmation(tmp_path, METRIC, res.identity_fields)  # promotable
    rec = load_ledger(tmp_path)[METRIC]
    assert rec.schema_sha256 == res.schema.schema_sha256


def test_empty_identity_cannot_be_confirmed(tmp_path):
    with pytest.raises(ConfirmationError):
        record_confirmation(tmp_path, METRIC, "T", [], today="2026-07-08")


def test_malformed_ledger_degrades_to_empty(tmp_path):
    path = tmp_path / LEDGER_REL
    path.parent.mkdir(parents=True)
    path.write_text("{{ not valid yaml", encoding="utf-8")
    assert load_ledger(tmp_path) == {}
    assert confirmation_status(tmp_path, METRIC, KEY) is ConfirmationStatus.UNCONFIRMED


# --------------------------------------------------------------------------- #
# Confirmation surface (R1-F7 — inferred key next to the golden diff).          #
# --------------------------------------------------------------------------- #
def test_surface_shows_key_and_matches_golden():
    res = _inference([{"department": "a", "fiscal_year": "2025"},
                      {"department": "b", "fiscal_year": "2025"}])
    text = render_confirmation_surface(res, golden_key=["department"])
    assert "inferred key" in text
    assert "MATCHES golden" in text


def test_surface_flags_divergence_from_golden():
    res = _inference([{"department": "a", "fiscal_year": "2025"},
                      {"department": "b", "fiscal_year": "2025"}])
    # Pretend the golden key is fund_source (not what was inferred) → surface must flag DIVERGES.
    text = render_confirmation_surface(res, golden_key=["fund_source"])
    assert "DIVERGES" in text
    assert "missing" in text or "extra" in text


def test_surface_echoes_status_when_supplied():
    res = _inference([{"department": "a", "fiscal_year": "2025"},
                      {"department": "b", "fiscal_year": "2025"}])
    text = render_confirmation_surface(res, status=ConfirmationStatus.STALE)
    assert "stale" in text
