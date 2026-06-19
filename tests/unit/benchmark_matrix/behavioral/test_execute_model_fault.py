"""R3-F3 — end-to-end behavioral wiring: an off-contract dep floors via ``run_behavioral_cell``.

No node runtime / no network: stubs Node provisioning + the sandbox to simulate a generated server
that fails to launch because it ``require()``s a framework off-contract for its wire protocol, and
asserts the cell is marked ``model_fault`` (→ floored by scoring), NOT degraded. A control case
proves a missing PROTOCOL dep (a real harness vendoring gap) still degrades. Complements the pure
classifier (`test_execute_dep_classification`) and composite-flooring (`test_benchmark_functional_composite`) tests.
"""
from __future__ import annotations

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.sandbox import ServiceResult


def _stub_launch(monkeypatch, stderr: str):
    # Node deps are offline-vendored; stub provisioning so the test needs no node_modules, and stub
    # the sandbox to return a server that never became ready with the given launch error on stderr.
    monkeypatch.setattr(execute, "prepare_node_workdir", lambda *a, **k: True)
    fake = ServiceResult(ready=False, server_stderr=stderr,
                         isolation_level="seatbelt-loopback", network_isolated=True)
    monkeypatch.setattr(execute, "run_service_sandboxed", lambda *a, **k: fake)


def test_off_contract_dep_floors_via_run_behavioral_cell(tmp_path, monkeypatch):
    # A gRPC paymentservice that hallucinated `express` → launch fails on the missing module.
    _stub_launch(monkeypatch, "Error: Cannot find module 'express'\n    at Module._resolveFilename")
    seed = {"service_metadata": {"language": "nodejs"}}  # default tcp (gRPC) contract
    res = execute.run_behavioral_cell(seed, tmp_path, "paymentservice", ["server.js"])

    assert res.has_suite is True
    assert res.model_fault is True        # off-contract framework → model fault (R3-F3)
    assert res.functional == 0.0          # real zero coverage; runner floors it to COMPILE_FLOOR
    assert res.degraded is False          # NOT a harness degrade
    assert "express" in res.provenance.get("model_fault", "")


def test_missing_protocol_dep_still_degrades(tmp_path, monkeypatch):
    # Control: a missing PROTOCOL dep (@grpc/grpc-js — a harness vendoring gap) must still DEGRADE.
    _stub_launch(monkeypatch, "Error: Cannot find module '@grpc/grpc-js'")
    seed = {"service_metadata": {"language": "nodejs"}}
    res = execute.run_behavioral_cell(seed, tmp_path, "paymentservice", ["server.js"])

    assert res.degraded is True and res.model_fault is False
    assert res.functional is None
    assert res.provenance.get("missing_module") == "@grpc/grpc-js"
