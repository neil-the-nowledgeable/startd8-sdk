"""K3 lead/drafter role matrix — S5 (generalized role coordinate: identity + command).

Unit-level, no LLM. Covers MatrixCell role fields, cell_id/sandbox_dir_name composition with the
shipped K2 leverage segment, diagonal byte-identity (R6-S1/S2/S7/S8/S9), build_command argv equality,
and CellResult role round-trip (R6-S4).
"""
from __future__ import annotations

import pytest

from startd8.benchmark_matrix import CellResult, MatrixCell, cell_id, sandbox_dir_name
from startd8.benchmark_matrix.runner import STATUS_OK
from startd8.model_comparison import build_command

H = "abcdef012345deadbeef"   # dummy spec_hash (cell_id uses [:12])
A, B = "anthropic:claude-opus-4-8", "openai:gpt-5.5"


def _diag(model="anthropic:opus", lev="off"):
    return MatrixCell("cart", model, 0, lev)               # lead/drafter default None ⇒ diagonal


def _role(lead, drafter, model=None, lev="off"):
    return MatrixCell("cart", model or lead, 0, lev, lead=lead, drafter=drafter)


# --- MatrixCell resolution ---------------------------------------------------

def test_matrixcell_role_resolution():
    d = _diag("m")
    assert d.resolved_lead == "m" and d.resolved_drafter == "m" and d.is_diagonal
    r = _role(A, B)
    assert r.resolved_lead == A and r.resolved_drafter == B and not r.is_diagonal
    # explicit lead==drafter==model is still diagonal (byte-identity must hold either form)
    assert MatrixCell("cart", "m", 0, lead="m", drafter="m").is_diagonal


# --- cell_id: diagonal byte-identity + off-diagonal composition --------------

def test_cell_id_diagonal_is_byte_identical():
    # diagonal + off-leverage ⇒ no role/lev segment (pre-K3/pre-K2 format, FR-1)
    assert cell_id(H, _diag("m")) == f"{H[:12]}:cart:m:r0"


def test_cell_id_offdiagonal_appends_role_then_leverage():
    # role segment first, then lev (R6-S1); agents slugged so no stray top-level ':' (R6-S9)
    cid = cell_id(H, _role(A, B, lev="on"))
    assert ":lead-anthropic_claude-opus-4-8_drafter-openai_gpt-5.5" in cid
    assert cid.endswith(":lev-on")
    assert cid.index("lead-") < cid.index("lev-on")            # role BEFORE lev
    assert cid.split(":", 1)[0] == H[:12]                       # spec_hash still recoverable (R6-S9)


def test_cell_id_offdiagonal_no_leverage():
    cid = cell_id(H, _role(A, B))
    assert "lead-" in cid and ":lev-" not in cid


# --- sandbox_dir_name: distinct workdirs + diagonal unchanged ----------------

def test_sandbox_dir_diagonal_unchanged():
    assert sandbox_dir_name("cart", "m", 0) == "cart-m-r0"      # backward-compat (FR-1)


def test_sandbox_isolation_five_distinct_workdirs():
    """R6-S8: A→B, B→A, A→A, B→B, A→A+lev-on all resolve to DISTINCT workdirs."""
    dirs = {
        sandbox_dir_name("cart", A, 0, lead=A, drafter=B),     # A→B
        sandbox_dir_name("cart", B, 0, lead=B, drafter=A),     # B→A (symmetric-distinct)
        sandbox_dir_name("cart", A, 0, lead=A, drafter=A),     # A→A diagonal
        sandbox_dir_name("cart", B, 0, lead=B, drafter=B),     # B→B diagonal
        sandbox_dir_name("cart", A, 0, "on", lead=A, drafter=A),  # A→A + lev-on
    }
    assert len(dirs) == 5


def test_sandbox_role_before_leverage_segment():
    name = sandbox_dir_name("cart", A, 0, "on", lead=A, drafter=B)
    assert name.index("lead-") < name.index("lev-on")


# --- build_command: diagonal argv byte-equality (R6-S2) ----------------------

def test_build_command_diagonal_byte_identical(tmp_path):
    seed, wd, out = tmp_path / "s.json", tmp_path / "wd", tmp_path / "o"
    today = build_command(seed, wd, out, A, 1.0)               # no lead/drafter (today's call)
    explicit = build_command(seed, wd, out, A, 1.0, lead_agent=A, drafter_agent=A)
    assert explicit == today                                   # diagonal == today, byte-for-byte
    # repair/expose combos too
    assert (build_command(seed, wd, out, A, 1.0, repair_mode="shadow", lead_agent=A, drafter_agent=A)
            == build_command(seed, wd, out, A, 1.0, repair_mode="shadow"))


def test_build_command_offdiagonal_differs(tmp_path):
    seed, wd, out = tmp_path / "s.json", tmp_path / "wd", tmp_path / "o"
    today = build_command(seed, wd, out, A, 1.0)
    off = build_command(seed, wd, out, A, 1.0, lead_agent=A, drafter_agent=B)
    assert off != today
    i = off.index("--lead-agent")
    assert off[i + 1] == A and off[off.index("--drafter-agent") + 1] == B


# --- CellResult role round-trip (R6-S4) --------------------------------------

def test_cellresult_role_roundtrip():
    c = CellResult(cell_id="x", service="cart", model=A, language="csharp", repetition=0,
                   status=STATUS_OK, lead=A, drafter=B)
    again = CellResult.from_dict(c.to_dict())
    assert again.lead == A and again.drafter == B


def test_cellresult_diagonal_defaults_none():
    c = CellResult(cell_id="x", service="cart", model="m", language="go", repetition=0, status=STATUS_OK)
    assert c.lead is None and c.drafter is None               # diagonal default


# ============================ S6 — selection + grouping ======================

from startd8.benchmark_matrix import (  # noqa: E402
    BenchmarkRunSpec, aggregate_cells, build_role_grid_markdown, leverage_delta,
)


def _spec(**kw):
    base = dict(name="t", models=("anthropic:opus", "gemini:flash"), services=("cart",), repetitions=2)
    base.update(kw)
    return BenchmarkRunSpec(**base)


def test_diagonal_default_is_backward_compatible():
    """role_pairs=None ⇒ diagonal (#models, 1:1 NOT N²); total_cells/cells/spec_hash unchanged."""
    s = _spec()
    assert s.effective_role_pairs == (("anthropic:opus", "anthropic:opus"),
                                      ("gemini:flash", "gemini:flash"))
    assert s.total_cells == 2 * 2 * 1  # 1 svc × 2 models × 2 reps × 1 lev (NOT 2²)
    cells = list(s.cells())
    assert len(cells) == 4 and all(c.is_diagonal and c.lead is None for c in cells)


def test_grid_pairs_and_total_cells():
    g = BenchmarkRunSpec.grid_pairs(("a", "b"))
    assert g == (("a", "a"), ("a", "b"), ("b", "a"), ("b", "b"))
    s = _spec(role_pairs=BenchmarkRunSpec.grid_pairs(("anthropic:opus", "gemini:flash")))
    assert s.total_cells == 1 * 4 * 2 * 1   # grid = #models² = 4 role pairs


def test_grid_cost_estimate_scales_with_role_factor():
    """Review fix: estimate_run_cost must price every role pair — a grid was undercounted as
    diagonal (~#models× too low), risking a too-small ceiling passing preflight then aborting."""
    from startd8.benchmark_matrix import estimate_run_cost
    m = ("anthropic:claude-opus-4-8", "gemini:gemini-2.5-pro")
    diag = estimate_run_cost(_spec(models=m, repetitions=1))
    grid = estimate_run_cost(_spec(models=m, repetitions=1, role_pairs=BenchmarkRunSpec.grid_pairs(m)))
    assert diag.total_cells == 2 and grid.total_cells == 4   # 2 diagonal vs 4 grid pairs (1 svc, 1 rep)
    assert grid.total_usd > diag.total_usd                   # scales (was equal → undercount bug)


def test_spec_hash_role_conditional():
    """R6-S7: diagonal-only (None) hashes byte-identically to pre-K3; an off-diagonal pair changes it."""
    diag = _spec()
    off = _spec(role_pairs=(("anthropic:opus", "gemini:flash"),))
    assert off.spec_hash() != diag.spec_hash()
    # a None role_pairs adds nothing to identity (diagonal hash stable across constructions)
    assert _spec().spec_hash() == diag.spec_hash()


def test_cells_offdiagonal_carry_roles():
    s = _spec(models=("a", "b"), role_pairs=(("a", "b"), ("a", "a")))
    cells = list(s.cells())
    offdiag = [c for c in cells if not c.is_diagonal]
    assert all(c.lead == "a" and c.drafter == "b" and c.model == "a" for c in offdiag)
    assert any(c.is_diagonal for c in cells)   # (a,a) diagonal present


def test_role_pairs_validation():
    with pytest.raises(Exception):
        _spec(role_pairs=(("a",),))            # not a 2-tuple
    with pytest.raises(Exception):
        _spec(role_pairs=())                   # empty (use None for diagonal)


# --- aggregation: off-diagonal → by_pair only; by_model diagonal-only (R6-S5) ---

def _rc(model, lead=None, drafter=None, q=1.0):
    return CellResult(cell_id="x", service="cart", model=model, language="csharp", repetition=0,
                      status=STATUS_OK, quality=q, cost_usd=0.1, lead=lead, drafter=drafter)


def test_aggregate_offdiagonal_only_in_by_pair():
    cells = [
        _rc("a", q=0.9),                       # a→a diagonal
        _rc("b", q=0.8),                       # b→b diagonal
        _rc("a", lead="a", drafter="b", q=0.3),  # a→b off-diagonal (poison if it leaked into by_model)
    ]
    agg = aggregate_cells(cells)
    # by_model has ONLY diagonal cells (a@0.9, b@0.8) — the a→b 0.3 must not drag model 'a'
    assert agg["by_model"]["a"]["quality_median"] == 0.9
    assert set(agg["by_model"]) == {"a", "b"}
    # by_pair carries all three, including the off-diagonal
    assert "a|b" in agg["by_pair"] and agg["by_pair"]["a|b"]["quality_median"] == 0.3
    assert "a|a" in agg["by_pair"] and "b|b" in agg["by_pair"]
    # by_lead/by_drafter exist
    assert "a" in agg["by_lead"] and "b" in agg["by_drafter"]


def test_leverage_delta_ignores_offdiagonal():
    """R6-S5: an off-diagonal cell must not enter the K2 per-model delta."""
    cells = [
        _rc("a", q=0.6), _rc("a", lead="a", drafter="b", q=0.1),  # diagonal off + off-diagonal
    ]
    for c in cells:
        c.leverage = "off"
    cells.append(CellResult(cell_id="y", service="cart", model="a", language="csharp", repetition=0,
                            status=STATUS_OK, quality=0.9, cost_usd=0.1, leverage="on"))
    d = leverage_delta(cells)
    # only the diagonal a-off↔a-on pair counts (Δ 0.3); the a→b off-diagonal is excluded
    assert d["n_pairs"] == 1 and d["by_model"]["a"]["delta_quality_median"] == pytest.approx(0.3)


def test_role_grid_renders_when_offdiagonal():
    cells = [_rc("a", q=0.9), _rc("b", q=0.8),
             _rc("a", lead="a", drafter="b", q=0.3), _rc("b", lead="b", drafter="a", q=0.5)]
    md = build_role_grid_markdown(aggregate_cells(cells))
    assert "Lead × Drafter role grid" in md and "drafter" in md
    # diagonal-only run → empty grid
    assert build_role_grid_markdown(aggregate_cells([_rc("a"), _rc("b")])) == ""
