"""K2 leverage delta — S2 (paired coordinate), S3 (integrity-exempt ON), S4 (delta report).

Unit-level, no LLM / no subprocess (S3 mocks the model_comparison boundary).
"""
from __future__ import annotations

from unittest import mock

import pytest

from startd8.benchmark_matrix import (
    BenchmarkRunSpec,
    CellResult,
    MatrixCell,
    aggregate_cells,  # noqa: F401  (kept for parity / future use)
    build_leverage_delta_markdown,
    cell_id,
    leverage_delta,
    sandbox_dir_name,
)
from startd8.benchmark_matrix.runner import (
    STATUS_INFRA_FAIL,
    STATUS_INTEGRITY_FAIL,
    STATUS_OK,
    SubprocessCellExecutor,
)


def _spec(**kw) -> BenchmarkRunSpec:
    base = dict(name="t", models=("anthropic:opus",), services=("cartservice",), repetitions=2)
    base.update(kw)
    return BenchmarkRunSpec(**base)


# ============================ S2 — paired coordinate =========================

def test_default_offonly_is_backward_compatible():
    """Default leverage_states=("off",): total_cells, cells, spec_hash all match a no-K2 spec."""
    s_default = _spec()
    s_explicit_off = _spec(leverage_states=("off",))
    assert s_default.total_cells == 2  # 1 svc × 1 model × 2 reps × 1 state
    assert s_default.spec_hash() == s_explicit_off.spec_hash()
    cells = list(s_default.cells())
    assert all(c.leverage == "off" for c in cells) and len(cells) == 2


def test_leverage_states_change_hash_and_double_cells():
    s_off = _spec()
    s_onoff = _spec(leverage_states=("off", "on"))
    assert s_onoff.total_cells == 4                       # doubled
    assert s_onoff.spec_hash() != s_off.spec_hash()       # identity changed (R1-F5)


def test_cells_iterate_leverage_innermost_adjacent():
    """R5-S1: off and on of the SAME coordinate are adjacent (innermost loop)."""
    cells = list(_spec(repetitions=1, leverage_states=("off", "on")).cells())
    assert [c.leverage for c in cells] == ["off", "on"]   # back-to-back per coordinate
    assert cells[0][:3] == cells[1][:3]                   # same (service, model, rep)


def test_cell_id_appends_leverage_only_for_on_and_keeps_spec_hash_recoverable():
    h = "abcdef012345xyz"
    off = MatrixCell("cartservice", "anthropic:opus", 0, "off")
    on = MatrixCell("cartservice", "anthropic:opus", 0, "on")
    assert cell_id(h, off) == f"{h[:12]}:cartservice:anthropic:opus:r0"   # unsuffixed (FR-1)
    assert cell_id(h, on).endswith(":lev-on")                            # appended (R5-S2)
    # R5-S3: spec_hash still recoverable as the first ':'-delimited segment for both
    assert cell_id(h, on).split(":", 1)[0] == h[:12]


def test_sandbox_dir_name_distinct_per_leverage_off_unsuffixed():
    """R5-S2/S6: off/on resolve DISTINCT workdirs; off stays byte-identical to pre-K2."""
    off = sandbox_dir_name("cartservice", "anthropic:opus", 0, "off")
    on = sandbox_dir_name("cartservice", "anthropic:opus", 0, "on")
    assert off == "cartservice-anthropic_opus-r0"   # unchanged
    assert on == "cartservice-anthropic_opus-r0-lev-on"
    assert off != on


def test_leverage_state_validation():
    with pytest.raises(Exception):
        _spec(leverage_states=("off", "sideways"))
    with pytest.raises(Exception):
        _spec(leverage_states=())
    with pytest.raises(Exception):
        _spec(leverage_on_config={"bogus": True})


def test_cellresult_roundtrip_preserves_leverage_fields():
    c = CellResult(cell_id="x", service="s", model="m", language="go", repetition=0,
                   status=STATUS_OK, leverage="on", leverage_source="routing")
    again = CellResult.from_dict(c.to_dict())   # R3-S4: rescore round-trip keeps K2 fields
    assert again.leverage == "on" and again.leverage_source == "routing"


# ============================ S3 — integrity-exempt ON =======================

def _run_cell(tmp_path, leverage, *, det_skips=0, integrity_ok=True, status="success",
              on_config=None):
    """Drive SubprocessCellExecutor.__call__ with the model_comparison boundary mocked."""
    seeds = tmp_path / "seeds"
    seeds.mkdir()
    (seeds / "seed-cartservice.json").write_text('{"tasks": [{"config": {"context": {}}}]}')
    spec = _spec(leverage_states=("off", "on"),
                 leverage_on_config=on_config or {"routing": True, "micro_prime": False})
    cell = MatrixCell("cartservice", "anthropic:opus", 0, leverage)
    ex = SubprocessCellExecutor(seeds, workdir_root=tmp_path / "wd")
    captured = {}

    def fake_run_command(cmd, root, timeout=None):
        captured["cmd"] = list(cmd)
        return {"timed_out": False, "stderr_tail": "", "duration_seconds": 1.0}

    prime_result = {"benchmark_provenance": {"deterministic_skip_count": det_skips,
                                             "integrity_ok": integrity_ok},
                    "leverage_provenance": {"deterministic_skip_count": det_skips,
                                            "integrity_ok": integrity_ok}}
    with mock.patch("startd8.model_comparison.build_command",
                    return_value=["python3", "rpw.py", "--lead-agent", "anthropic:opus"]), \
         mock.patch("startd8.model_comparison.run_command", side_effect=fake_run_command), \
         mock.patch("startd8.model_comparison.extract_metrics",
                    return_value={"status": status, "mean_disk_quality_score": 0.8,
                                  "total_cost": 0.1, "input_tokens": 10, "output_tokens": 20}), \
         mock.patch("startd8.model_comparison._latest_match", return_value=tmp_path / "pr.json"), \
         mock.patch("startd8.model_comparison._load_json", return_value=prime_result):
        res = ex(cell, spec, "csharp")
    return res, captured["cmd"]


def test_off_cell_uses_benchmark_mode(tmp_path):
    res, cmd = _run_cell(tmp_path, "off")
    assert "--benchmark-mode" in cmd
    assert "--complexity-routing" not in cmd
    assert res.leverage == "off"


def test_on_cell_drops_benchmark_mode_adds_routing(tmp_path):
    """R2-S1: on-cells must NOT carry --benchmark-mode; they carry the on-path flags."""
    res, cmd = _run_cell(tmp_path, "on")
    assert "--benchmark-mode" not in cmd
    assert "--complexity-routing" in cmd
    assert res.leverage == "on" and res.leverage_source == "routing"


def test_off_cell_with_skips_is_integrity_fail(tmp_path):
    res, _ = _run_cell(tmp_path, "off", det_skips=3)
    assert res.status == STATUS_INTEGRITY_FAIL          # R1-S1 fail-closed


def test_on_cell_with_skips_is_ok(tmp_path):
    """R5-S5: skip-heavy on-cell with a valid artifact resolves OK, not FAILED."""
    res, _ = _run_cell(tmp_path, "on", det_skips=3)
    assert res.status == STATUS_OK
    assert res.deterministic_skips == 3                  # recorded as data


def test_on_cell_with_integrity_false_still_fails(tmp_path):
    """R2-S2: integrity_ok=false ⇒ INTEGRITY_FAIL even for on-cells (run corrupt ≠ shortcuts used)."""
    res, _ = _run_cell(tmp_path, "on", det_skips=3, integrity_ok=False)
    assert res.status == STATUS_INTEGRITY_FAIL


def test_on_cell_both_mechanisms_source(tmp_path):
    res, cmd = _run_cell(tmp_path, "on", on_config={"routing": True, "micro_prime": True})
    assert "--complexity-routing" in cmd and "--micro-prime" in cmd
    assert res.leverage_source == "both"


# ============================ S4 — leverage delta ============================

def _cell(service, model, rep, leverage, q, cost, *, status=STATUS_OK, compile_ok=True,
          degraded=False, skips=0):
    return CellResult(cell_id=f"{service}:{model}:r{rep}:{leverage}", service=service, model=model,
                      language="csharp", repetition=rep, status=status, quality=q,
                      compile_ok=compile_ok, degraded=degraded, cost_usd=cost,
                      deterministic_skips=skips, leverage=leverage)


def test_leverage_delta_paired_per_coordinate():
    cells = [
        _cell("cart", "m", 0, "off", 0.6, 1.0), _cell("cart", "m", 0, "on", 1.0, 0.3),
        _cell("cart", "m", 1, "off", 0.8, 1.0), _cell("cart", "m", 1, "on", 0.9, 0.3),
    ]
    d = leverage_delta(cells)
    s = d["by_model"]["m"]
    assert s["n_pairs"] == 2
    assert s["delta_quality_median"] == pytest.approx(0.25)   # median(0.4, 0.1)
    assert s["delta_cost_total"] == pytest.approx(-1.4)       # 2×(0.3-1.0)
    assert s["leverage_regressed"] is False


def test_paired_estimator_differs_from_unpaired():
    """R3-S2: median-of-per-coordinate-deltas must NOT equal median(on)−median(off) here."""
    cells = [
        _cell("a", "m", 0, "off", 0.0, 1.0), _cell("a", "m", 0, "on", 0.1, 1.0),  # Δ +0.1
        _cell("b", "m", 0, "off", 0.9, 1.0), _cell("b", "m", 0, "on", 1.0, 1.0),  # Δ +0.1
        _cell("c", "m", 0, "off", 0.5, 1.0), _cell("c", "m", 0, "on", 0.0, 1.0),  # Δ −0.5
    ]
    d = leverage_delta(cells)["by_model"]["m"]
    # paired: median(+0.1, +0.1, −0.5) = +0.1
    assert d["delta_quality_median"] == pytest.approx(0.1)
    # unpaired median(on)=0.1, median(off)=0.5 ⇒ −0.4 — would be wrong; confirm we don't report it
    assert d["delta_quality_median"] != pytest.approx(-0.4)


def test_unpaired_coordinate_excluded_with_reason():
    cells = [
        _cell("a", "m", 0, "off", 0.6, 1.0), _cell("a", "m", 0, "on", 0.9, 0.3),     # paired
        _cell("b", "m", 0, "off", 0.6, 1.0),                                          # on missing
        _cell("c", "m", 0, "off", 0.6, 1.0), _cell("c", "m", 0, "on", None, 0.0, status=STATUS_INFRA_FAIL),
    ]
    d = leverage_delta(cells)
    assert d["by_model"]["m"]["n_pairs"] == 1
    assert d["unpaired_count"] == 2
    reasons = {u["reason"] for u in d["unpaired"]}
    assert "missing" in reasons and "infra_fail" in reasons


def test_regressed_flag_and_branch_divergence():
    cells = [
        _cell("a", "m", 0, "off", 0.9, 1.0, compile_ok=True, degraded=False),
        _cell("a", "m", 0, "on", 0.4, 1.2, compile_ok=None, degraded=True),   # worse + cost up + branch diff
    ]
    s = leverage_delta(cells)["by_model"]["m"]
    assert s["leverage_regressed"] is True
    assert s["branch_divergent_pairs"] == 1            # R5-S4: scorer-confounded pair flagged
    assert "Leverage delta" in build_leverage_delta_markdown(leverage_delta(cells))
