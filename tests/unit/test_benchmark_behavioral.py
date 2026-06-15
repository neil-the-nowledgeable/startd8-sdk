"""M-T2.2 (startup contract + serve resolution) + M-T2.3 (Charge behavioral suite).

The end-to-end tests host a Python reference PaymentService (good / broken) inside the M-T2.1
sandbox primitive and run the SDK-authored Charge suite against it over the loopback gRPC wire —
proving the suite DISCRIMINATES (passes correct behavior, fails plausible-but-wrong behavior)
before any model output is involved. Hermetic: no LLM, no external network, no Node (the real
Node pilot server runs at M-T2.4); grpcio is required.
"""
from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

import pytest

pytest.importorskip("grpc")

from startd8.benchmark_matrix.behavioral import (  # noqa: E402
    StartupContract,
    resolve_serve_command,
    run_behavioral_cell,
    run_charge_suite,
)
import startd8.benchmark_matrix.behavioral as beh  # noqa: E402
from startd8.benchmark_matrix.sandbox import SandboxConfig, run_service_sandboxed  # noqa: E402

_BEH_DIR = Path(beh.__file__).parent
_FIXTURES = Path(__file__).parent / "fixtures" / "behavioral"
_NO_NET = SandboxConfig(no_network=False)  # skip seatbelt wrap → hermetic lifecycle test


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --- M-T2.2 startup contract + serve resolution ------------------------------

def test_startup_contract_parses_and_resolves_port():
    seed = {"startup": {"cmd": ["node", "server.js", "$PORT"], "port_env": "PORT"}}
    contract = StartupContract.from_seed(seed)
    assert contract is not None
    argv, env = contract.resolve(54321)
    assert argv == ["node", "server.js", "54321"]   # $PORT substituted in argv
    assert env == {"PORT": "54321"}                 # and injected as env


def test_resolve_serve_command_prefers_contract_then_node_default_then_none():
    # Explicit contract wins.
    seed = {"startup": {"cmd": ["node", "src/paymentservice/server.js"]}, "language": "nodejs"}
    argv, env = resolve_serve_command(seed, ["src/paymentservice/server.js"], 7000)
    assert argv == ["node", "src/paymentservice/server.js"] and env == {"PORT": "7000"}
    # No contract → Node default builder.
    argv2, env2 = resolve_serve_command({"language": "nodejs"}, ["src/paymentservice/server.js"], 7001)
    assert argv2 == ["node", "src/paymentservice/server.js"] and env2 == {"PORT": "7001"}
    # Unknown language, no contract → None (caller degrades, FR-32).
    assert resolve_serve_command({"language": "rust"}, ["main.rs"], 7002) is None


def test_real_paymentservice_seed_has_startup_contract():
    import json
    seed = json.loads((
        Path(__file__).parents[2] / "docs/design/model-benchmark/seeds/seed-paymentservice.json"
    ).read_text())
    contract = StartupContract.from_seed(seed)
    assert contract is not None and contract.cmd[0] == "node"


# --- M-T2.3 behavioral suite vs reference servers ----------------------------

def _host_reference_server(tmp_path: Path, server_fixture: str):
    """Copy the stubs + a reference server into a workspace and run the Charge suite against it."""
    ws = tmp_path / "svc"
    ws.mkdir()
    for f in ("demo_pb2.py", "demo_pb2_grpc.py"):
        shutil.copy(_BEH_DIR / f, ws / f)
    shutil.copy(_FIXTURES / server_fixture, ws / server_fixture)
    port = _free_port()
    return run_service_sandboxed(
        [sys.executable, server_fixture], ws, port, run_charge_suite,
        cfg=_NO_NET, readiness_timeout_s=15.0, extra_env={"PORT": str(port)},
    )


def test_suite_passes_known_good_server(tmp_path):
    res = _host_reference_server(tmp_path, "good_payment_server.py")
    assert res.ready is True and res.violation is None
    suite = res.client_outcome
    assert suite is not None and not suite.connect_error
    assert suite.coverage == 1.0                     # all 3 RPCs pass on a correct impl
    assert all(r.passed for r in suite.results)


def test_suite_fails_known_broken_server(tmp_path):
    # Broken server accepts ANY card (no Luhn/expiry) — static analysis can't see this; behavior can.
    res = _host_reference_server(tmp_path, "broken_payment_server.py")
    assert res.ready is True
    suite = res.client_outcome
    assert suite is not None and not suite.connect_error
    by_name = {r.name: r.passed for r in suite.results}
    assert by_name["charge_valid_card"] is True              # happy path still works...
    assert by_name["charge_invalid_card_rejected"] is False  # ...but it accepts invalid cards
    assert by_name["charge_expired_card_rejected"] is False  # ...and expired cards
    assert suite.coverage == pytest.approx(1 / 3)            # the suite discriminates


# --- M-T2.4 ($0 wiring) — run_behavioral_cell orchestration ------------------

def _workspace_with(tmp_path: Path, server_fixture: str) -> Path:
    ws = tmp_path / "cell"
    ws.mkdir(parents=True)
    for f in ("demo_pb2.py", "demo_pb2_grpc.py"):
        shutil.copy(_BEH_DIR / f, ws / f)
    shutil.copy(_FIXTURES / server_fixture, ws / server_fixture)
    return ws


def test_run_behavioral_cell_scores_good_and_broken(tmp_path):
    # Launch the reference server via a startup contract (Python here; Node at the real pilot).
    good = _workspace_with(tmp_path / "g", "good_payment_server.py")
    seed_g = {"startup": {"cmd": [sys.executable, "good_payment_server.py"], "port_env": "PORT"}}
    rg = run_behavioral_cell(seed_g, good, "paymentservice", ["good_payment_server.py"], cfg=_NO_NET)
    assert rg.has_suite and not rg.degraded and rg.functional == 1.0
    assert rg.provenance["suite"]["coverage"] == 1.0

    broken = _workspace_with(tmp_path / "b", "broken_payment_server.py")
    seed_b = {"startup": {"cmd": [sys.executable, "broken_payment_server.py"], "port_env": "PORT"}}
    rb = run_behavioral_cell(seed_b, broken, "paymentservice", ["broken_payment_server.py"], cfg=_NO_NET)
    assert rb.functional == pytest.approx(1 / 3)


def test_run_behavioral_cell_no_suite_for_service(tmp_path):
    # cartservice is still out of scope (stateful) — no suite registered → leave composite unchanged.
    res = run_behavioral_cell({}, tmp_path, "cartservice", ["Cart.cs"], cfg=_NO_NET)
    assert res.has_suite is False and res.functional is None and not res.degraded


def test_run_behavioral_cell_no_launcher_degrades(tmp_path):
    # paymentservice HAS a suite, but no startup contract + unknown language → degrade, don't 0.
    res = run_behavioral_cell({"service_metadata": {"language": "rust"}}, tmp_path,
                              "paymentservice", ["main.rs"], cfg=_NO_NET)
    assert res.has_suite and res.degraded and res.functional is None


@pytest.mark.skipif(not (_BEH_DIR / "node_runtime" / "node_modules").is_dir()
                    or shutil.which("node") is None,
                    reason="node + vendored runtime required")
def test_run_behavioral_cell_names_missing_module_on_degrade(tmp_path):
    # FR-T2-DEPS2: a server that dies on an unprovisioned module degrades with the module NAMED in
    # provenance (diagnosable harness gap), never scored 0.
    seed = {"startup": {"cmd": ["node", "-e", "require('totally-not-installed-zzz')"], "port_env": "PORT"}}
    res = run_behavioral_cell(seed, tmp_path, "paymentservice", ["server.js"], cfg=_NO_NET)
    assert res.degraded and res.functional is None
    assert res.provenance.get("missing_module") == "totally-not-installed-zzz"

