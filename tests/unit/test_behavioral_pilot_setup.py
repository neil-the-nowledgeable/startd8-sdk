"""M-T2.4 setup — pilot spec shape + Node-runtime workdir prep (no LLM, no pilot run)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("grpc")

from startd8.benchmark_matrix.behavioral.execute import prepare_node_workdir  # noqa: E402

_REPO = Path(__file__).resolve().parents[2]
_NODE_RUNTIME = _REPO / "src" / "startd8" / "benchmark_matrix" / "behavioral" / "node_runtime"


def _load_pilot():
    spec = importlib.util.spec_from_file_location("_pilot", _REPO / "scripts" / "run_behavioral_pilot.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_pilot"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_pilot_spec_is_one_service_times_roster_times_reps():
    pilot = _load_pilot()
    spec = pilot.build_spec(["paymentservice"],
                            ["anthropic:claude-opus-4-8", "openai:gpt-5.5", "gemini:gemini-2.5-pro"],
                            repetitions=3, budget=10.0, per_cell_cap=None)
    assert spec.services == ("paymentservice",)
    assert spec.total_cells == 1 * 3 * 3
    assert spec.budget_ceiling_usd == 10.0


def test_node_runtime_closure_declares_pino_and_uuid():
    # FR-T2-DEPS: the vendored closure must include the real paymentservice deps the models require
    # without declaring (pino, uuid) — not just gRPC. Asserted on package.json (no install needed).
    import json
    deps = json.loads((_NODE_RUNTIME / "package.json").read_text())["dependencies"]
    assert {"@grpc/grpc-js", "@grpc/proto-loader", "pino", "uuid"} <= set(deps)


@pytest.mark.skipif(not (_NODE_RUNTIME / "node_modules").is_dir(),
                    reason="node runtime not vendored (run node_runtime/vendor.sh)")
def test_prepare_node_workdir_materializes_closure_and_proto_at_all_paths(tmp_path):
    assert prepare_node_workdir(tmp_path) is True
    # FR-T2-DEPS: full closure present.
    for pkg in ("@grpc/grpc-js", "@grpc/proto-loader", "pino", "uuid"):
        assert (tmp_path / "node_modules" / pkg).exists(), pkg
    # FR-T2-PROTO: proto provisioned at every conventional location a server might load it from.
    for sub in ("", "protos", "proto", "pb", "lib/proto"):
        loc = (tmp_path / sub / "demo.proto") if sub else (tmp_path / "demo.proto")
        assert loc.is_file(), sub


@pytest.mark.skipif(not (_NODE_RUNTIME / "node_modules").is_dir(),
                    reason="node runtime not vendored (run node_runtime/vendor.sh)")
def test_prepare_node_workdir_drops_proto_service_relative(tmp_path):
    # FR-T2-PROTO: service-relative paths (next to the server + its proto/ subdir). The pilot saw
    # Opus load from src/<service>/demo.proto, which the fixed-list multiplex alone misses.
    assert prepare_node_workdir(tmp_path, ["src/paymentservice/server.js"]) is True
    assert (tmp_path / "src" / "paymentservice" / "demo.proto").is_file()
    assert (tmp_path / "src" / "paymentservice" / "proto" / "demo.proto").is_file()
