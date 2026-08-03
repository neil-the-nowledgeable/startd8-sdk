# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2
"""FR-9 — declarative workload-journey shape (AC-1..AC-5). Zero network, zero docker."""
from __future__ import annotations

from startd8.observability import warmup_traffic as wt
from startd8.observability.warmup_traffic import (
    SHAPE_WORKLOAD,
    WarmupSpec,
    WorkloadSpec,
    WorkloadStep,
    drive_warmup,
    evaluate_warmup,
    run_workload_journey,
)


def _spec():
    return WorkloadSpec(
        name="demo",
        auth={"kind": "basic", "user": "admin", "password_env": "X"},
        steps=[
            WorkloadStep(name="create", kind="http", method="POST", path="/p", expect_status="2xx",
                         registers_metric="core_http_total"),
            WorkloadStep(name="push", kind="command", argv=["docker", "push", "x"],
                         registers_metric="registry_total"),
            WorkloadStep(name="gc", kind="http", method="POST", path="/gc", expect_status="2xx",
                         registers_metric="job_task_total"),
        ],
    )


def test_ac1_all_pass_ready():
    """AC-1: injected all-pass runners + query_fn>0 → exercised, terminal_success, ready."""
    out = run_workload_journey(
        _spec(), base_url="http://x", allow_commands=True,
        http_runner=lambda s, **k: (200, ""),
        command_runner=lambda s: (0, ""),
    )
    assert out.exercised and out.terminal_success
    assert set(out.registers_metrics) == {"core_http_total", "registry_total", "job_task_total"}
    ready, reason = evaluate_warmup(
        out, prometheus_url="http://prom", count_metric=list(out.registers_metrics),
        query_fn=lambda url, q, auth=None: 5.0,
    )
    assert ready, reason


def test_ac2_required_step_fail_loud():
    """AC-2: a required http step returns non-2xx → terminal_success False, reason names it; not ready."""
    def http(s, **k):
        return (500 if s.name == "gc" else 200), ""
    out = run_workload_journey(_spec(), base_url="http://x", allow_commands=True,
                               http_runner=http, command_runner=lambda s: (0, ""))
    assert out.exercised and not out.terminal_success
    assert "gc" in out.reason
    ready, _ = evaluate_warmup(out, prometheus_url="http://prom",
                               count_metric=list(out.registers_metrics), query_fn=lambda *a, **k: 5.0)
    assert not ready


def test_ac3_union_metric_zero_fails_loud():
    """AC-3: terminal success but a metric stays zero → not ready, names the empty metric."""
    out = run_workload_journey(_spec(), base_url="http://x", allow_commands=True,
                               http_runner=lambda s, **k: (200, ""), command_runner=lambda s: (0, ""))
    assert out.terminal_success
    # registry_total never lands (job silently didn't emit) → fail-loud
    def q(url, query, auth=None):
        return 0.0 if "registry_total" in query else 3.0
    ready, reason = evaluate_warmup(out, prometheus_url="http://prom",
                                    count_metric=list(out.registers_metrics), query_fn=q)
    assert not ready and "registry_total" in reason


def test_ac4_existing_shapes_untouched():
    """AC-4: workload is additive; drive_warmup rejects it with a clear pointer; smoke still loops."""
    o = drive_warmup(WarmupSpec(shape=SHAPE_WORKLOAD))
    assert not o.exercised and "run_workload_journey" in o.reason
    # a smoke drive still works via an injected driver (unchanged behavior)
    from startd8.observability.warmup_traffic import DriverFns

    class _Smoke:
        status = "pass"; reason = ""
    o2 = drive_warmup(WarmupSpec(shape="smoke", max_iterations=1),
                      ingress_url="http://x", driver_fns=DriverFns(smoke=lambda u, timeout=0: _Smoke()))
    assert o2.exercised and o2.terminal_success


def test_ac5_commands_gated_and_redacted():
    """AC-5: command steps are no-ops unless allow_commands; auth password is env-only (not inline)."""
    # commands disallowed → the command step is skipped → required-step fail (not exercised as ok)
    out = run_workload_journey(_spec(), base_url="http://x", allow_commands=False,
                               http_runner=lambda s, **k: (200, ""))
    names = dict(out.step_results)
    assert "skipped" in names["push"]
    # allow → the command_runner is invoked
    called = {}
    def cmd(s):
        called["argv"] = s.argv
        return (0, "")
    run_workload_journey(_spec(), base_url="http://x", allow_commands=True,
                         http_runner=lambda s, **k: (200, ""), command_runner=cmd)
    assert called["argv"] == ["docker", "push", "x"]
    # auth block never carries a literal password (password_env names the var)
    assert _spec().auth.get("password") is None and _spec().auth["password_env"] == "X"
