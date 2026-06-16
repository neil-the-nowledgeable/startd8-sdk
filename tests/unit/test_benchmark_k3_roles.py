"""K3 lead/drafter role matrix — S5 (generalized role coordinate: identity + command).

Unit-level, no LLM. Covers MatrixCell role fields, cell_id/sandbox_dir_name composition with the
shipped K2 leverage segment, diagonal byte-identity (R6-S1/S2/S7/S8/S9), build_command argv equality,
and CellResult role round-trip (R6-S4).
"""
from __future__ import annotations

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
