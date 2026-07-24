# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Unit tests for FR-8 warm-up traffic — no network, all drivers/queries injected.

Covers driver selection + the bounded loop, per-shape terminal-success and
driver-can't-exercise semantics (R1-F5), and the two-part convergence gate
(terminal success AND non-zero samples, never series-count alone — R1-F3/F8).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from startd8.observability import warmup_traffic as wt


# ── driver stand-ins (mirror the real SDK driver return shapes) ─────────────

@dataclass
class FakeSmoke:  # mirrors deploy_harness.smoke.SmokeOutcome
    status: str
    reason: str = ""


@dataclass
class FakeJourneyOutcome:  # mirrors fleet.frontend_gate.JourneyOutcome
    completed: bool
    signals: Dict[str, bool] = field(default_factory=dict)


@dataclass
class FakeStep:
    name: str
    passed: bool
    weight: float = 1.0


@dataclass
class FakeJourneyResult:  # mirrors fleet.adapter_b.JourneyResult
    steps: List[FakeStep] = field(default_factory=list)

    @property
    def unweighted_coverage(self) -> float:
        return sum(s.passed for s in self.steps) / len(self.steps) if self.steps else 0.0

    @property
    def failed_steps(self) -> List[str]:
        return [s.name for s in self.steps if not s.passed]


def _fns(**kw) -> wt.DriverFns:
    return wt.DriverFns(**kw)


# ── smoke shape ──────────────────────────────────────────────────────────────

def test_smoke_pass_is_terminal_success_on_first_iteration():
    calls = {"n": 0}

    def smoke(url, timeout=10.0):
        calls["n"] += 1
        return FakeSmoke(status="pass")

    out = wt.drive_warmup(
        wt.WarmupSpec(shape="smoke", max_iterations=5), ingress_url="http://x",
        driver_fns=_fns(smoke=smoke), sleep_fn=lambda s: None,
    )
    assert out.exercised and out.terminal_success
    assert out.iterations == 1  # stops early on terminal success
    assert calls["n"] == 1


def test_smoke_skipped_is_driver_cannot_exercise():
    out = wt.drive_warmup(
        wt.WarmupSpec(shape="smoke", max_iterations=3), ingress_url="http://x",
        driver_fns=_fns(smoke=lambda url, timeout=10.0: FakeSmoke(status="skipped", reason="skipped:no-openapi")),
        sleep_fn=lambda s: None,
    )
    assert out.exercised is False
    assert out.terminal_success is False
    assert "could not exercise" in out.reason
    assert out.iterations == 3  # exhausts the budget looking for a successful request


def test_smoke_fail_exercised_but_not_terminal():
    # a 500 still hit the app (spans fire) → exercised, but never terminal.
    out = wt.drive_warmup(
        wt.WarmupSpec(shape="smoke", max_iterations=2), ingress_url="http://x",
        driver_fns=_fns(smoke=lambda url, timeout=10.0: FakeSmoke(status="fail", reason="post-500")),
        sleep_fn=lambda s: None,
    )
    assert out.exercised is True
    assert out.terminal_success is False
    assert "never reached terminal success" in out.reason


def test_smoke_warms_up_after_a_few_attempts():
    seq = iter([FakeSmoke("fail"), FakeSmoke("fail"), FakeSmoke("pass")])
    out = wt.drive_warmup(
        wt.WarmupSpec(shape="smoke", max_iterations=5), ingress_url="http://x",
        driver_fns=_fns(smoke=lambda url, timeout=10.0: next(seq)), sleep_fn=lambda s: None,
    )
    assert out.terminal_success is True
    assert out.iterations == 3


# ── ob-http shape ────────────────────────────────────────────────────────────

class _DummyClient:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def test_ob_http_completed_is_terminal_and_closes_client():
    client = _DummyClient()

    def journey(c):
        assert c is client
        return FakeJourneyOutcome(completed=True, signals={"browse": True, "checkout": True})

    out = wt.drive_warmup(
        wt.WarmupSpec(shape="ob-http", max_iterations=3), ingress_url="http://ingress",
        driver_fns=_fns(ob_http=journey, client_factory=lambda url: client),
        sleep_fn=lambda s: None,
    )
    assert out.exercised and out.terminal_success
    assert client.closed is True  # client torn down


def test_ob_http_all_fail_is_not_exercised():
    out = wt.drive_warmup(
        wt.WarmupSpec(shape="ob-http", max_iterations=2), ingress_url="http://ingress",
        driver_fns=_fns(
            ob_http=lambda c: FakeJourneyOutcome(completed=False, signals={"browse": False, "checkout": False}),
            client_factory=lambda url: _DummyClient(),
        ),
        sleep_fn=lambda s: None,
    )
    assert out.exercised is False
    assert "could not exercise" in out.reason


def test_ob_http_partial_signals_is_exercised_not_terminal():
    out = wt.drive_warmup(
        wt.WarmupSpec(shape="ob-http", max_iterations=1), ingress_url="http://ingress",
        driver_fns=_fns(
            ob_http=lambda c: FakeJourneyOutcome(completed=False, signals={"browse": True, "checkout": False}),
            client_factory=lambda url: _DummyClient(),
        ),
        sleep_fn=lambda s: None,
    )
    assert out.exercised is True and out.terminal_success is False


# ── ob-grpc shape ────────────────────────────────────────────────────────────

def test_ob_grpc_no_failed_steps_is_terminal():
    steps = [FakeStep("browse", True), FakeStep("checkout", True)]
    out = wt.drive_warmup(
        wt.WarmupSpec(shape="ob-grpc", max_iterations=2),
        addr_map={"frontend": "frontend:8080"},
        driver_fns=_fns(ob_grpc=lambda addr: FakeJourneyResult(steps=steps)),
        sleep_fn=lambda s: None,
    )
    assert out.exercised and out.terminal_success


def test_ob_grpc_all_failed_is_not_exercised():
    steps = [FakeStep("browse", False), FakeStep("checkout", False)]
    out = wt.drive_warmup(
        wt.WarmupSpec(shape="ob-grpc", max_iterations=1),
        addr_map={"frontend": "frontend:8080"},
        driver_fns=_fns(ob_grpc=lambda addr: FakeJourneyResult(steps=steps)),
        sleep_fn=lambda s: None,
    )
    assert out.exercised is False


# ── robustness ───────────────────────────────────────────────────────────────

def test_unknown_shape_is_fail_loud():
    out = wt.drive_warmup(wt.WarmupSpec(shape="bogus"), sleep_fn=lambda s: None)
    assert out.exercised is False and "unknown warm-up shape" in out.reason


def test_driver_exception_is_a_non_exercise_not_a_crash():
    def boom(url, timeout=10.0):
        raise RuntimeError("connection refused")

    out = wt.drive_warmup(
        wt.WarmupSpec(shape="smoke", max_iterations=2), ingress_url="http://x",
        driver_fns=_fns(smoke=boom), sleep_fn=lambda s: None,
    )
    assert out.exercised is False
    assert "RuntimeError" in out.reason


# ── convergence: samples_landed + evaluate_warmup ───────────────────────────

def test_samples_landed_true_on_nonzero():
    seen = {}

    def q(url, promql, auth=None):
        seen["promql"] = promql
        return 4.0

    assert wt.samples_landed("http://p", "hist_count", window="2m", query_fn=q) is True
    assert seen["promql"] == "sum(increase(hist_count[2m]))"


def test_samples_landed_false_on_zero_or_absent():
    assert wt.samples_landed("http://p", "hist_count", query_fn=lambda u, q, auth=None: 0.0) is False
    assert wt.samples_landed("http://p", "hist_count", query_fn=lambda u, q, auth=None: None) is False


def test_evaluate_warmup_ready_when_terminal_and_samples_land():
    out = wt.WarmupOutcome(driver="smoke", exercised=True, terminal_success=True)
    ready, why = wt.evaluate_warmup(
        out, prometheus_url="http://p", count_metric="hist_count",
        query_fn=lambda u, q, auth=None: 3.0,
    )
    assert ready is True and why == ""


def test_evaluate_warmup_unknown_when_driver_cannot_exercise():
    # the outcome's own reason (which drive_warmup names the driver in) is surfaced verbatim.
    out = wt.WarmupOutcome(driver="smoke", exercised=False, reason="driver 'smoke' could not exercise")
    ready, why = wt.evaluate_warmup(out, prometheus_url="http://p", count_metric="hist_count")
    assert ready is False and why == "driver 'smoke' could not exercise"


def test_evaluate_warmup_names_driver_when_outcome_reason_empty():
    out = wt.WarmupOutcome(driver="smoke", exercised=False, reason="")
    ready, why = wt.evaluate_warmup(out, count_metric=None)
    assert ready is False and "smoke" in why


def test_evaluate_warmup_unknown_when_no_samples_despite_terminal_success():
    # R1-F3/F8: terminal success but the histogram never got non-zero samples.
    out = wt.WarmupOutcome(driver="ob-http", exercised=True, terminal_success=True)
    ready, why = wt.evaluate_warmup(
        out, prometheus_url="http://p", count_metric="traces_spanmetrics_calls_total",
        query_fn=lambda u, q, auth=None: 0.0,
    )
    assert ready is False
    assert "no non-zero samples" in why


def test_evaluate_warmup_skips_sample_check_when_no_metric():
    out = wt.WarmupOutcome(driver="smoke", exercised=True, terminal_success=True)
    ready, why = wt.evaluate_warmup(out, count_metric=None)
    assert ready is True and why == ""
