"""Cost-tracking precision tests (REQ-CT-1..6).

Covers cache-aware pricing, family-safe model resolution, default-model coverage,
the estimated-vs-measured signal, end-to-end cache-token flow, and precision reconcile.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from startd8.costs.pricing import PricingService
from startd8.costs.store import CostStore
from startd8.costs.tracker import CostTracker


@pytest.fixture
def pricing():
    return PricingService()


@pytest.fixture
def tracker():
    with tempfile.TemporaryDirectory() as tmp:
        store = CostStore(Path(tmp) / "costs.db")
        yield CostTracker(store, PricingService(), enabled=True)


# -- REQ-CT-1: cache-aware pricing -----------------------------------------


def test_no_cache_result_unchanged(pricing):
    # Regression: default (no cache) breakdown equals the plain input/output math.
    in_cost, out_cost = pricing.calculate_cost_breakdown("claude-opus-4-6", 1000, 500)
    assert in_cost == pytest.approx(1000 / 1_000_000 * 5.0)
    assert out_cost == pytest.approx(500 / 1_000_000 * 25.0)


def test_cache_read_priced_at_read_multiplier(pricing):
    # opus-4-6: input $5/M, read multiplier 0.1
    in_cost, out_cost = pricing.calculate_cost_breakdown(
        "claude-opus-4-6", input_tokens=1000, output_tokens=500,
        cache_read_input_tokens=50_000,
    )
    expected_in = (1000 * 5.0 + 50_000 * 5.0 * 0.1) / 1_000_000
    assert in_cost == pytest.approx(expected_in)
    assert out_cost == pytest.approx(500 / 1_000_000 * 25.0)


def test_cache_write_priced_at_write_multiplier(pricing):
    in_cost, _ = pricing.calculate_cost_breakdown(
        "claude-opus-4-6", input_tokens=1000, output_tokens=0,
        cache_creation_input_tokens=50_000,
    )
    expected_in = (1000 * 5.0 + 50_000 * 5.0 * 1.25) / 1_000_000
    assert in_cost == pytest.approx(expected_in)


# -- REQ-CT-3: family-safe model resolution --------------------------------


def test_gpt5_does_not_resolve_to_gpt4_1(pricing):
    # The old loose prefix match would have priced gpt-5.5-pro as gpt-4.1.
    p = pricing.get_pricing("gpt-5.5-pro")
    assert p is not None
    assert p.model == "gpt-5.5-pro"
    assert p.input_cost_per_million != pricing.get_pricing("gpt-4.1").input_cost_per_million


def test_unknown_model_falls_back_estimated_not_wrong_family(pricing):
    p, estimated = pricing.resolve_pricing("gpt-9.9-imaginary")
    assert estimated is True
    # fallback rate, NOT any real openai entry's rate
    assert p.input_cost_per_million == pytest.approx(3.0)
    assert p.output_cost_per_million == pytest.approx(15.0)
    # get_pricing (exact-only) returns None for a truly unknown model
    assert pricing.get_pricing("gpt-9.9-imaginary") is None


def test_dated_variant_normalizes_to_family(pricing):
    # Anthropic -YYYYMMDD and OpenAI -YYYY-MM-DD date suffixes resolve to the family entry.
    assert pricing.get_pricing("claude-opus-4-6-20260101").model == "claude-opus-4-6"
    assert pricing.get_pricing("gpt-5.5-2026-04-23").model == "gpt-5.5"


def test_existing_exact_dated_model_still_resolves(pricing):
    # A model that previously relied on loose matching but IS an exact key stays correct.
    p = pricing.get_pricing("claude-3-5-sonnet-20241022")
    assert p is not None and p.input_cost_per_million == pytest.approx(3.0)


# -- REQ-CT-4: pricing for current shipped defaults ------------------------


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-4-8", "claude-opus-4-7",
        "gpt-5.5-pro", "gpt-5.5", "gpt-5.4-mini", "gpt-5.4-nano",
        "gemini-3.1-pro-preview",
    ],
)
def test_shipped_defaults_have_entries(pricing, model):
    p = pricing.get_pricing(model)  # exact-only; must not be None (no fallback)
    assert p is not None and p.model == model


# -- REQ-CT-5: estimated-vs-measured signal --------------------------------


def test_estimated_flag_set_for_estimated_entry(pricing):
    _p, est = pricing.resolve_pricing("claude-opus-4-8")  # flagged estimated
    assert est is True


def test_estimated_flag_false_for_confirmed_entry(pricing):
    _p, est = pricing.resolve_pricing("claude-opus-4-6")
    assert est is False


def test_record_carries_estimated_marker(tracker):
    est_rec = tracker.record_cost("a", "claude-opus-4-8", 100, 50)
    measured_rec = tracker.record_cost("a", "claude-opus-4-6", 100, 50)
    assert est_rec.pricing_estimated is True
    assert measured_rec.pricing_estimated is False


def test_unknown_model_logs_warning(pricing, caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        pricing.resolve_pricing("totally-unknown-model-xyz")
    assert any("totally-unknown-model-xyz" in r.message for r in caplog.records)


# -- REQ-CT-2: end-to-end cache-token flow ---------------------------------


def test_record_cost_threads_cache_tokens(tracker):
    rec = tracker.record_cost(
        "claude", "claude-opus-4-6", input_tokens=1000, output_tokens=500,
        cache_read_input_tokens=50_000,
    )
    assert rec.cache_read_input_tokens == 50_000
    # cost includes the cache-read cost, so it exceeds the input-only cost
    input_only = tracker.record_cost("claude", "claude-opus-4-6", 1000, 500)
    assert rec.total_cost > input_only.total_cost


# -- REQ-CT-6: precision reconcile -----------------------------------------


def test_summary_reconciles_to_sum_of_records(tracker):
    from datetime import datetime, timezone, timedelta
    start = datetime.now(timezone.utc) - timedelta(hours=1)
    recs = [
        tracker.record_cost("a", "claude-opus-4-6", 333, 111),
        tracker.record_cost("a", "gpt-4o", 777, 222),
        tracker.record_cost("a", "claude-opus-4-6", 1, 1, cache_read_input_tokens=12_345),
    ]
    summary = tracker.get_summary(start, datetime.now(timezone.utc) + timedelta(hours=1))
    assert summary.total_cost == pytest.approx(sum(r.total_cost for r in recs), abs=1e-6)
