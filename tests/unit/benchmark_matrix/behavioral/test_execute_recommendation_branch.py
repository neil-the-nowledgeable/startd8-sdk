"""Unit tests for the execute.py recommendationservice dispatch (no live launch).

Proves run_behavioral_cell guard-dispatches recommendationservice to _run_recommendation_cell (NOT
through _SUITES), binds the productcatalog stub, injects PRODUCT_CATALOG_SERVICE_ADDR, and tears the
stub down on every path — by stubbing out the launch/score core so no server is started.
"""
from __future__ import annotations

from pathlib import Path

from startd8.benchmark_matrix.behavioral import execute
from startd8.benchmark_matrix.behavioral.execute import BehavioralResult
from startd8.benchmark_matrix.behavioral.recommendation_stubs import ENV_PRODUCT_CATALOG

_SEED = {
    "service_metadata": {"language": "python"},
    "startup": {
        "cmd": ["sh", "-c", "cd src/recommendationservice && exec python3 server.py"],
        "port_env": "PORT",
        "readiness": "tcp",
        "dependency_addr_env": [ENV_PRODUCT_CATALOG],
    },
}
_TARGETS = ["src/recommendationservice/server.py"]


def test_dispatch_routes_recommendation_to_dedicated_branch(monkeypatch, tmp_path):
    captured = {}

    def _fake_core(seed, workdir, service, target_files, argv, extra_env, port, client,
                   *, port_source="injected", cfg=None, extra_provenance=None):
        # Capture what the branch resolved + injected BEFORE any real launch.
        captured["service"] = service
        captured["extra_env"] = dict(extra_env or {})
        captured["extra_provenance"] = dict(extra_provenance or {})
        return BehavioralResult(has_suite=True, functional=1.0, provenance={})

    monkeypatch.setattr(execute, "_provision_launch_and_score", _fake_core)
    res = execute.run_behavioral_cell(_SEED, tmp_path, "recommendationservice", _TARGETS)

    assert res.has_suite and res.functional == 1.0
    assert captured["service"] == "recommendationservice"
    # PRODUCT_CATALOG_SERVICE_ADDR was injected into the SUT env, bound to a loopback addr.
    addr = captured["extra_env"].get(ENV_PRODUCT_CATALOG, "")
    assert addr.startswith("127.0.0.1:"), captured["extra_env"]
    # PORT is also present (from the startup contract).
    assert "PORT" in captured["extra_env"]
    # Provenance records the orchestrator kind + declared dep env.
    prov = captured["extra_provenance"]
    assert prov["suite_kind"] == "recommendation-orchestrator"
    assert prov["recommendation_declared_dep_env"] == [ENV_PRODUCT_CATALOG]
    assert prov["recommendation_unbound_declared_env"] == []
    # The branch records final call-counts in provenance.
    assert ENV_PRODUCT_CATALOG in res.provenance["recommendation_call_counts"]


def test_recommendation_not_in_leaf_suites_table():
    # Guard-dispatched like checkout — NOT a plain client(port) leaf.
    assert "recommendationservice" not in execute._SUITES


def test_no_startup_block_degrades_not_crash(tmp_path):
    seed = {"service_metadata": {"language": "python"}}  # no startup block
    res = execute.run_behavioral_cell(seed, tmp_path, "recommendationservice", _TARGETS)
    assert res.has_suite and res.degraded
    assert "startup block" in res.provenance.get("reason", "")


def test_stub_torn_down_even_if_core_raises(monkeypatch, tmp_path):
    started = {}

    real_harness_cls = execute.RecommendationDepHarness

    class _TrackingHarness(real_harness_cls):  # type: ignore[misc, valid-type]
        def start(self):
            started["addr"] = super().start()
            return started["addr"]

        def stop(self):
            started["stopped"] = True
            super().stop()

    monkeypatch.setattr(execute, "RecommendationDepHarness", _TrackingHarness)

    def _boom(*a, **k):
        raise RuntimeError("core blew up")

    monkeypatch.setattr(execute, "_provision_launch_and_score", _boom)
    try:
        execute.run_behavioral_cell(_SEED, tmp_path, "recommendationservice", _TARGETS)
    except RuntimeError:
        pass
    # finally: teardown ran despite the exception (no leaked loopback listener).
    assert started.get("stopped") is True
    assert Path  # touch import
