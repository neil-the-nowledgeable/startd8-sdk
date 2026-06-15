"""P2 invariant suites (currency / shipping / ad) — discrimination proof.

Hosts a good and a broken reference server (each serving all three stateless services) and runs the
three suites against them. Proves the invariant suites separate a correct impl (1.0) from a careless
one (<1.0) WITHOUT pinned ground-truth data. Hermetic: grpcio + Python only, no LLM, no external net.
"""
from __future__ import annotations

import shutil
import socket
import sys
from pathlib import Path

import pytest

pytest.importorskip("grpc")

import startd8.benchmark_matrix.behavioral as beh  # noqa: E402
from startd8.benchmark_matrix.behavioral import (  # noqa: E402
    run_ad_suite,
    run_currency_suite,
    run_shipping_suite,
)
from startd8.benchmark_matrix.sandbox import SandboxConfig, run_service_sandboxed  # noqa: E402

_BEH_DIR = Path(beh.__file__).parent
_FIXTURES = Path(__file__).parent / "fixtures" / "behavioral"
_NO_NET = SandboxConfig(no_network=False)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _all_suites(port: int) -> dict:
    return {
        "currency": run_currency_suite(port),
        "shipping": run_shipping_suite(port),
        "ad": run_ad_suite(port),
    }


def _host(tmp_path: Path, server_fixture: str):
    ws = tmp_path / "svc"
    ws.mkdir(parents=True)
    for f in ("demo_pb2.py", "demo_pb2_grpc.py"):
        shutil.copy(_BEH_DIR / f, ws / f)
    shutil.copy(_FIXTURES / server_fixture, ws / server_fixture)
    port = _free_port()
    return run_service_sandboxed(
        [sys.executable, server_fixture], ws, port, _all_suites,
        cfg=_NO_NET, readiness_timeout_s=15.0, extra_env={"PORT": str(port)},
    )


def test_suites_pass_known_good_server(tmp_path):
    res = _host(tmp_path, "good_stateless_server.py")
    assert res.ready and res.violation is None
    out = res.client_outcome
    assert out["currency"].coverage == 1.0, [r.__dict__ for r in out["currency"].results]
    assert out["shipping"].coverage == 1.0, [r.__dict__ for r in out["shipping"].results]
    assert out["ad"].coverage == 1.0, [r.__dict__ for r in out["ad"].results]


def test_suites_discriminate_known_broken_server(tmp_path):
    res = _host(tmp_path, "broken_stateless_server.py")
    assert res.ready
    out = res.client_outcome
    # currency: identity broken + accepts unknown + empty supported → only determinism passes (1/4)
    assert out["currency"].coverage < 1.0
    c = {r.name: r.passed for r in out["currency"].results}
    assert c["convert_identity"] is False and c["convert_rejects_unknown_code"] is False
    assert c["supported_currencies_nonempty"] is False and c["convert_deterministic"] is True
    # shipping: negative cost + invalid code → 1/3 (determinism still holds)
    assert out["shipping"].coverage < 1.0
    s = {r.name: r.passed for r in out["shipping"].results}
    assert s["quote_non_negative"] is False and s["quote_valid_currency_code"] is False
    # ad: no ads → 0/2
    assert out["ad"].coverage == 0.0
