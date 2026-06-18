"""Pure-model speed dimension (FR-SPEED-1..4): accumulation → emit → extract → aggregate → render."""
from __future__ import annotations

import json

from startd8.agents.model_timing import (
    get_model_call_count,
    get_model_time_ms_total,
    record_model_time_ms,
    reset_model_time_ms,
)
from startd8.benchmark_matrix.aggregate import build_matrix_markdown, aggregate_cells, summarize_group
from startd8.benchmark_matrix.runner import CellResult, STATUS_OK
from startd8.model_comparison import extract_metrics


def test_accumulator_records_sums_and_resets():
    reset_model_time_ms()
    assert get_model_time_ms_total() == 0.0 and get_model_call_count() == 0
    record_model_time_ms(120)
    record_model_time_ms(80.5)
    record_model_time_ms(None)        # ignored
    record_model_time_ms("oops")      # ignored
    record_model_time_ms(-5)          # ignored (negative)
    assert get_model_time_ms_total() == 200.5
    assert get_model_call_count() == 2
    reset_model_time_ms()
    assert get_model_time_ms_total() == 0.0


def test_cellresult_model_tokens_per_sec():
    c = CellResult(cell_id="x", service="s", model="m", language="nodejs", repetition=0,
                   status=STATUS_OK, output_tokens=900, model_time_s=10.0, latency_s=100.0)
    assert c.model_tokens_per_sec == 90.0          # pure model: 900/10
    assert c.tokens_per_sec == 9.0                  # pipeline wall: 900/100
    # absent model time → None (degrade, FR-SPEED-4)
    assert CellResult(cell_id="x", service="s", model="m", language="nodejs", repetition=0,
                      status=STATUS_OK, output_tokens=900, latency_s=100.0).model_tokens_per_sec is None


def test_extract_metrics_reads_total_model_time_ms(tmp_path):
    (tmp_path / "prime-result.json").write_text(json.dumps({
        "success": True, "total_output_tokens": 1000, "total_model_time_ms": 25000,
    }))
    m = extract_metrics(tmp_path)
    assert m["model_time_s"] == 25.0
    # absent → None (degrade-honest)
    (tmp_path / "prime-result.json").write_text(json.dumps({"success": True}))
    assert extract_metrics(tmp_path)["model_time_s"] is None


def _cell(model, model_time_s, out=1000, q=1.0):
    return CellResult(cell_id=f"h:{model}", service="paymentservice", model=model, language="nodejs",
                      repetition=0, status=STATUS_OK, quality=q, output_tokens=out,
                      model_time_s=model_time_s, latency_s=(model_time_s or 0) + 50)


def test_aggregate_exposes_model_time_medians():
    s = summarize_group([_cell("m", 20.0), _cell("m", 40.0)])
    assert s["model_time_median_s"] == 30.0
    # model tok/s per cell = 1000/20=50 and 1000/40=25 → median 37.5
    assert s["model_tokens_per_sec_median"] == 37.5


def test_report_surfaces_speed_dimension():
    agg = aggregate_cells([_cell("anthropic:opus", 50.0), _cell("anthropic:haiku", 20.0)])
    md = build_matrix_markdown("t", "spec", agg)
    assert "model tok/s med" in md            # scoreboard headline column
    assert "## Speed (generation time" in md   # dedicated Speed section
    assert "harness overhead" in md
