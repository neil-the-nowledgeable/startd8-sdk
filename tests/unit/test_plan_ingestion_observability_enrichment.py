"""Issue #268 R1 — regression coverage for the OPI-150/200/600 observability enrichment.

The enrichment (`plan_ingestion_emitter.py`) was shipped untested: a regression could
silently null `service_name` / `convention_metrics` / `observability_contract` and CI would
stay green. These assert the enrichment actually populates, matches by service dir, leaves
unmatched tasks alone (OPI-201), and that the contract is absent without hints (OPI-602).
"""

from __future__ import annotations

from startd8.workflows.builtin.plan_ingestion_emitter import (
    _build_observability_contract,
    _enrich_tasks_with_observability,
)


_HINTS = {
    "checkout-service": {  # hyphen in the id — must normalize to "checkoutservice"
        "transport": "grpc",
        "language": "Go",
        "sdk": ["opentelemetry-instrumentation-grpc"],
        "alert_thresholds": {"latency_p99": "500ms"},
        "slo_targets": {"availability": "99.9", "window": "30d"},
        "metrics": {"convention_based": [
            {"name": "rpc.server.duration", "type": "histogram", "source": "otel_semconv:grpc"},
        ]},
    },
}


# --- OPI-600 / OPI-602: the seed-level observability_contract ---

class TestObservabilityContract:
    def test_contract_shape_from_hints(self):
        c = _build_observability_contract(_HINTS)
        assert c is not None
        svc = c["services"]["checkout-service"]   # contract keys keep the original id
        assert svc["transport"] == "grpc"
        assert svc["language"] == "Go"
        assert svc["convention_metrics"][0]["name"] == "rpc.server.duration"
        assert svc["sdk_packages"] == ["opentelemetry-instrumentation-grpc"]
        assert svc["slo_window"] == "30d"
        assert "source" in c

    def test_contract_absent_without_hints(self):
        # OPI-602: absence = "no guidance", graceful — None so the caller omits the key.
        assert _build_observability_contract(None) is None
        assert _build_observability_contract({}) is None
        assert _build_observability_contract({"svc": "not-a-dict"}) is None


# --- OPI-150 / OPI-200 / OPI-201: per-task enrichment ---

class TestTaskEnrichment:
    def _task(self, target_files, ctx=None):
        cfg = {"context": dict(ctx)} if ctx is not None else {}
        cfg.setdefault("context", {})["target_files"] = target_files
        return {"config": cfg}

    def test_task_matched_by_service_dir_is_enriched(self):
        # OPI-151: a target file under src/checkout-service/ matches the (hyphen-normalized) hint.
        task = self._task(["src/checkout-service/main.go"])
        n = _enrich_tasks_with_observability([task], _HINTS)
        assert n == 1
        ctx = task["config"]["context"]
        assert ctx["service_name"] == "checkoutservice"
        assert ctx["convention_metrics"][0]["name"] == "rpc.server.duration"
        assert ctx["transport"] == "grpc"
        assert ctx["sdk_packages"] == ["opentelemetry-instrumentation-grpc"]
        assert ctx["alert_thresholds"] == {"latency_p99": "500ms"}

    def test_preset_service_name_is_honored(self):
        # OPI-150: an already-set service_name wins over path inference.
        task = self._task(["src/unrelated/x.go"], ctx={"service_name": "checkout-service"})
        assert _enrich_tasks_with_observability([task], _HINTS) == 1
        assert task["config"]["context"]["service_name"] == "checkoutservice"

    def test_unmatched_task_left_untouched(self):
        # OPI-201: no service match ⇒ config.context unchanged (no phantom enrichment).
        task = self._task(["src/paymentservice/pay.go"])
        assert _enrich_tasks_with_observability([task], _HINTS) == 0
        assert "convention_metrics" not in task["config"]["context"]
        assert "service_name" not in task["config"]["context"]

    def test_no_hints_is_a_noop(self):
        task = self._task(["src/checkout-service/main.go"])
        assert _enrich_tasks_with_observability([task], None) == 0
        assert "convention_metrics" not in task["config"]["context"]

    def test_task_without_a_config_context_gets_one_on_match(self):
        # write-back: a task that arrives with no config still persists enrichment.
        task = {"target_files": ["src/checkout-service/main.go"]}
        assert _enrich_tasks_with_observability([task], _HINTS) == 1
        assert task["config"]["context"]["service_name"] == "checkoutservice"
