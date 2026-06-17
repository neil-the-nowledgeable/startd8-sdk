"""Hardened difficulty tier — the smallest slice that produces a real discrimination signal.

Two halves:
  1. Tier matrix-dimension plumbing (pure): the `tier` axis is byte-identical to pre-tier when
     defaulted (the critical FR-2 backward-compat guarantee), and adds a distinct hash/cell_id/
     sandbox segment only when non-baseline — mirroring the K2/K3 precedent.
  2. Discrimination proof ($0, hermetic gRPC): the hardened currency suite separates a correct impl
     (1.0) from a careless-but-happy-path impl (<1.0) where the BASELINE suite gives both 1.0. This is
     the evidence the difficulty dial works, without any LLM/pilot spend (FR-30).
"""
from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

import pytest

from startd8.benchmark_matrix.run_spec import BenchmarkRunSpec, MatrixCell
from startd8.benchmark_matrix.runner import cell_id, sandbox_dir_name, seed_filename

_SEEDS_DIR = Path(__file__).resolve().parents[2] / "docs" / "design" / "model-benchmark" / "seeds"


def _spec(**kw):
    base = dict(name="t", models=("anthropic:claude-fable-5",),
                services=("currencyservice",), repetitions=2)
    base.update(kw)
    return BenchmarkRunSpec(**base)


# ----------------------------- tier plumbing (pure) -----------------------------

def test_baseline_tier_is_byte_identical_default():
    s = _spec()
    assert s.tier_states == ("baseline",)
    # explicit baseline-only hashes identically to the default (conditional-inclusion, FR-2)
    assert _spec(tier_states=("baseline",)).spec_hash() == s.spec_hash()
    cells = list(s.cells())
    assert len(cells) == s.total_cells == 2
    assert all(c.tier == "baseline" for c in cells)


def test_hardened_tier_changes_hash_and_doubles_cells():
    s, h = _spec(), _spec(tier_states=("baseline", "hardened"))
    assert h.total_cells == s.total_cells * 2
    assert h.spec_hash() != s.spec_hash()
    assert sorted({c.tier for c in h.cells()}) == ["baseline", "hardened"]


def test_cell_id_and_sandbox_segments_omitted_for_baseline():
    sh = _spec().spec_hash()
    cb = MatrixCell("currencyservice", "m", 0)
    ch = MatrixCell("currencyservice", "m", 0, tier="hardened")
    # baseline byte-identical to pre-tier; hardened appends a segment AFTER any leverage segment
    assert cell_id(sh, cb) == f"{sh[:12]}:currencyservice:m:r0"
    assert cell_id(sh, ch) == f"{sh[:12]}:currencyservice:m:r0:tier-hardened"
    assert sandbox_dir_name("currencyservice", "m", 0) == "currencyservice-m-r0"
    assert sandbox_dir_name("currencyservice", "m", 0, tier="hardened") == \
        "currencyservice-m-r0-tier-hardened"


def test_tier_validator_rejects_empty_and_duplicates():
    with pytest.raises(Exception):
        _spec(tier_states=())
    with pytest.raises(Exception):
        _spec(tier_states=("baseline", "baseline"))


def test_seed_filename_matches_generated_files_on_disk():
    """Regression guard (pilot run-20260617T140903): the runner looked for seed-<svc>-hardened.json
    while the generator wrote seed-<svc>.hardened.json → every hardened cell fail-closed. Lock the
    runner's seed_filename to the actual on-disk generator output so they can't drift again."""
    assert seed_filename("currencyservice", "baseline") == "seed-currencyservice.json"
    assert seed_filename("currencyservice", "hardened") == "seed-currencyservice.hardened.json"
    # the file the runner will select for a hardened cell must actually exist (generator wrote it)
    assert (_SEEDS_DIR / seed_filename("currencyservice", "hardened")).exists()


# --------------------- discrimination proof (hermetic gRPC, $0) ---------------------

# The generated demo_pb2_grpc stubs pin grpcio>=1.81; an older runtime raises at import. Treat that
# (and a missing grpc) as an environment limitation and skip the live half — the pure tier-plumbing
# tests above still run. The discrimination tests run wherever the behavioral runtime is satisfied
# (same dependency as test_benchmark_stateless_suites.py).
try:
    import grpc  # noqa: F401
    import startd8.benchmark_matrix.behavioral as beh
    from startd8.benchmark_matrix.behavioral.currency_suite import run_currency_suite
    from startd8.benchmark_matrix.behavioral.charge_suite import run_charge_suite
    from startd8.benchmark_matrix.sandbox import SandboxConfig, run_service_sandboxed
    _BEH_DIR = Path(beh.__file__).parent
    _NO_NET = SandboxConfig(no_network=False)  # in-process loopback; matches the stateless-suite tests
    _GRPC_SKIP = ""
except Exception as _e:  # noqa: BLE001 — grpc missing OR generated-stub/runtime version mismatch
    _GRPC_SKIP = f"behavioral gRPC runtime unavailable: {_e}"

grpc_required = pytest.mark.skipif(bool(_GRPC_SKIP), reason=_GRPC_SKIP or "grpc")
_FIXTURES = Path(__file__).parent / "fixtures" / "behavioral"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _run(tmp_path: Path, fixture: str, *, tier: str, suite=None):
    suite = suite or run_currency_suite
    ws = tmp_path / "svc"
    ws.mkdir(parents=True)
    for f in ("demo_pb2.py", "demo_pb2_grpc.py"):
        shutil.copy(_BEH_DIR / f, ws / f)
    shutil.copy(_FIXTURES / fixture, ws / fixture)
    port = _free_port()
    res = run_service_sandboxed(
        [sys.executable, fixture], ws, port,
        lambda p: suite(p, tier=tier),
        cfg=_NO_NET, readiness_timeout_s=15.0, extra_env={"PORT": str(port)},
    )
    assert res.ready and res.violation is None, res.server_stderr
    return res.client_outcome


@grpc_required
def test_baseline_suite_does_not_discriminate(tmp_path):
    """The point of the hardened tier: BOTH a correct and a careless impl pass the baseline suite."""
    good = _run(tmp_path / "g", "good_stateless_server.py", tier="baseline")
    careless = _run(tmp_path / "c", "careless_currency_server.py", tier="baseline")
    assert good.coverage == 1.0, [r.__dict__ for r in good.results]
    assert careless.coverage == 1.0, [r.__dict__ for r in careless.results]


@grpc_required
def test_hardened_suite_discriminates(tmp_path):
    """The hardened superset separates the correct impl (1.0) from the careless one (<1.0)."""
    good = _run(tmp_path / "g", "good_stateless_server.py", tier="hardened")
    careless = _run(tmp_path / "c", "careless_currency_server.py", tier="hardened")
    assert good.coverage == 1.0, [r.__dict__ for r in good.results]
    assert careless.coverage < 1.0, [r.__dict__ for r in careless.results]
    # the discriminating invariant is the lossy round-trip
    failed = {r.name for r in careless.results if not r.passed}
    assert "h_round_trip_identity" in failed
    # and it is a strict superset — the careless impl still passes every baseline invariant
    assert careless.coverage > 0.5


@grpc_required
def test_charge_baseline_does_not_discriminate(tmp_path):
    """Both the hardened-correct and the constant-id/no-validation impl pass the baseline charge suite."""
    good = _run(tmp_path / "g", "hardened_good_payment_server.py", tier="baseline", suite=run_charge_suite)
    careless = _run(tmp_path / "c", "good_payment_server.py", tier="baseline", suite=run_charge_suite)
    assert good.coverage == 1.0, [r.__dict__ for r in good.results]
    assert careless.coverage == 1.0, [r.__dict__ for r in careless.results]


@grpc_required
def test_charge_hardened_discriminates(tmp_path):
    """Hardened charge separates a validating/unique-id impl (1.0) from the constant-id, no-amount-
    validation impl (<1.0) — which the baseline suite scores identically."""
    good = _run(tmp_path / "g", "hardened_good_payment_server.py", tier="hardened", suite=run_charge_suite)
    careless = _run(tmp_path / "c", "good_payment_server.py", tier="hardened", suite=run_charge_suite)
    assert good.coverage == 1.0, [r.__dict__ for r in good.results]
    assert careless.coverage < 1.0, [r.__dict__ for r in careless.results]
    failed = {r.name for r in careless.results if not r.passed}
    # constant transaction_id and missing amount validation are the discriminators
    assert {"h_unique_transaction_ids", "h_negative_amount_rejected"} & failed
