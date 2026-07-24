# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Warm-up traffic for compare-live standup (FR-8) — reuse a driver, add no engine.

Span-metrics (and lazily-registered RED series) emit **no series until the subject
handles a request**, so a standup that only boots + scrapes greens at a
*registered-but-empty* state — the exact false-ready path Tier B exists to kill
(see ``SUBJECT_COVERAGE_REQUIREMENTS.md`` FR-8). This module drives **bounded**
traffic at the subject's ingress before the readiness gate, then supplies the
FR-8 convergence signal.

**No new load engine (FR-8/FR-6).** It *selects and loops* one of the three
request drivers the SDK already ships, by subject shape:

* ``smoke``   → ``deploy_harness.smoke.run_smoke(base_url)`` — schema-driven CRUD
  round-trip against an **arbitrary** OpenAPI subject (the common compare-live case);
* ``ob-http`` → ``benchmark_matrix.fleet.frontend_gate.run_journey_http(client)`` —
  the 5-step Online-Boutique journey over HTTP;
* ``ob-grpc`` → ``benchmark_matrix.fleet.adapter_b.run_journey(addr_map)`` — the
  same journey over direct gRPC.

**Two-part convergence (FR-8/R1-F3/F8), never series-count alone.** The gate
releases only when **both** hold: (a) the driver reached a **terminal success**
(``run_smoke`` ``pass`` / ``JourneyOutcome.completed`` / no ``failed_steps``), and
(b) the subject's histogram ``_count`` shows **non-zero samples**
(``sum(increase(<metric>[<window>])) > 0``). A driver that produces **no
successful request** — ``run_smoke`` ``skipped`` (no ``/openapi.json`` / no CRUD),
or the OB journey scoring all-fail on a non-OB subject — resolves the run to
**``unknown`` naming the driver** (fail-loud, R1-F5), never a silent proceed.

Every effect is injectable (driver fns / ``query_fn`` / ``sleep_fn``) so the
selection, the bounded loop, and the convergence math are unit-tested with zero
network and zero docker.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from . import prometheus_query
from .prometheus_query import Auth

SHAPE_SMOKE = "smoke"
SHAPE_OB_HTTP = "ob-http"
SHAPE_OB_GRPC = "ob-grpc"
VALID_SHAPES = (SHAPE_SMOKE, SHAPE_OB_HTTP, SHAPE_OB_GRPC)

#: The HTTP shapes a host-side driver loop can exercise (v1). ``ob-grpc`` needs an
#: in-fleet driver (the subject's gRPC ports stay on the internal, host-unreachable
#: fleet net), so the standup wiring defers it; the driver itself is still selectable
#: here for the future in-compose sidecar.
HOST_DRIVABLE_SHAPES = (SHAPE_SMOKE, SHAPE_OB_HTTP)


@dataclass
class WarmupSpec:
    """How much bounded traffic to drive, and how (FR-8)."""

    shape: str
    max_iterations: int = 10
    request_interval: float = 0.5  # seconds between iterations (bounded, polite)
    timeout: float = 10.0  # per-request driver timeout (smoke)


@dataclass
class WarmupOutcome:
    """The result of the bounded warm-up loop.

    ``exercised`` — at least one iteration produced a *successful request* against
    the subject (spans fired). ``terminal_success`` — the driver reached its
    terminal success at least once. ``exercised=False`` is the driver-can't-exercise
    fail-loud branch (R1-F5): map to ``unknown`` naming ``driver``.
    """

    driver: str
    exercised: bool = False
    terminal_success: bool = False
    iterations: int = 0
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "driver": self.driver,
            "exercised": self.exercised,
            "terminal_success": self.terminal_success,
            "iterations": self.iterations,
            "reason": self.reason,
        }


@dataclass
class DriverFns:
    """Injectable driver seams (default to the real SDK drivers, imported lazily)."""

    smoke: Optional[Callable[..., Any]] = None
    ob_http: Optional[Callable[..., Any]] = None
    ob_grpc: Optional[Callable[..., Any]] = None
    client_factory: Optional[Callable[[str], Any]] = None


def _resolve_fns(fns: Optional[DriverFns], shape: str) -> DriverFns:
    fns = fns or DriverFns()
    if shape == SHAPE_SMOKE and fns.smoke is None:
        from ..deploy_harness.smoke import run_smoke

        fns.smoke = run_smoke
    if shape == SHAPE_OB_HTTP:
        if fns.ob_http is None:
            from ..benchmark_matrix.fleet.frontend_gate import run_journey_http

            fns.ob_http = run_journey_http
        if fns.client_factory is None:
            import httpx

            fns.client_factory = lambda url: httpx.Client(base_url=url, timeout=10.0)
    if shape == SHAPE_OB_GRPC and fns.ob_grpc is None:
        from ..benchmark_matrix.fleet.adapter_b import run_journey

        fns.ob_grpc = run_journey
    return fns


def _run_once(
    shape: str,
    fns: DriverFns,
    *,
    ingress_url: Optional[str],
    addr_map: Optional[Dict[str, str]],
    client: Any,
    timeout: float,
) -> tuple[bool, bool, str]:
    """One driver invocation → ``(exercised, terminal_success, detail)`` (never raises)."""
    try:
        if shape == SHAPE_SMOKE:
            out = fns.smoke(ingress_url, timeout=timeout)  # SmokeOutcome, never raises
            # "skipped" == could not exercise (no openapi / no CRUD); "fail" still hit the app.
            return (out.status != "skipped", out.status == "pass", out.reason or out.status)
        if shape == SHAPE_OB_HTTP:
            out = fns.ob_http(client)  # JourneyOutcome
            exercised = any(out.signals.values())
            return (exercised, bool(out.completed), "" if out.completed else "journey incomplete")
        if shape == SHAPE_OB_GRPC:
            out = fns.ob_grpc(addr_map)  # JourneyResult
            exercised = bool(out.steps) and out.unweighted_coverage > 0
            terminal = bool(out.steps) and not out.failed_steps
            return (exercised, terminal, "" if terminal else f"failed={out.failed_steps}")
    except Exception as e:  # noqa: BLE001 — a driver hiccup is a non-exercise, not a crash
        return (False, False, f"{type(e).__name__}: {e}")
    return (False, False, f"unknown shape {shape!r}")


def drive_warmup(
    spec: WarmupSpec,
    *,
    ingress_url: Optional[str] = None,
    addr_map: Optional[Dict[str, str]] = None,
    driver_fns: Optional[DriverFns] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> WarmupOutcome:
    """Drive bounded traffic via the shape's driver until terminal success or the cap.

    Loops up to ``spec.max_iterations`` (stopping early on the first terminal
    success — bounded is the point). Accumulates ``exercised`` / ``terminal_success``
    across iterations so a subject that needs a few requests to warm up still
    converges. Never raises.
    """
    if spec.shape not in VALID_SHAPES:
        return WarmupOutcome(driver=spec.shape, reason=f"unknown warm-up shape {spec.shape!r}")
    fns = _resolve_fns(driver_fns, spec.shape)
    outcome = WarmupOutcome(driver=spec.shape)

    client = None
    if spec.shape == SHAPE_OB_HTTP and fns.client_factory is not None:
        client = fns.client_factory(ingress_url)
    last_detail = ""
    try:
        for i in range(max(1, spec.max_iterations)):
            outcome.iterations = i + 1
            exercised, terminal, detail = _run_once(
                spec.shape, fns, ingress_url=ingress_url, addr_map=addr_map,
                client=client, timeout=spec.timeout,
            )
            outcome.exercised = outcome.exercised or exercised
            outcome.terminal_success = outcome.terminal_success or terminal
            last_detail = detail
            if terminal:
                break
            if i + 1 < spec.max_iterations:
                sleep_fn(spec.request_interval)
    finally:
        if client is not None:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001 — client teardown is best-effort
                    pass

    if not outcome.exercised:
        outcome.reason = (
            f"driver '{spec.shape}' could not exercise the subject "
            f"after {outcome.iterations} attempt(s): {last_detail}"
        )
    elif not outcome.terminal_success:
        outcome.reason = (
            f"driver '{spec.shape}' exercised the subject but never reached terminal "
            f"success after {outcome.iterations} attempt(s): {last_detail}"
        )
    return outcome


def samples_landed(
    prometheus_url: str,
    count_metric: str,
    *,
    window: str = "1m",
    auth: Optional[Auth] = None,
    query_fn: Callable[..., Optional[float]] = prometheus_query.instant_query_value,
) -> bool:
    """True when ``sum(increase(<count_metric>[<window>])) > 0`` — non-zero samples.

    The FR-8/R1-F3 convergence signal that series-count settling cannot give: a
    histogram registers ``_bucket``/``_count``/``_sum`` on the first scrape with
    **zero** observations, so a series count can "settle" while every sample is 0.
    """
    q = f"sum(increase({count_metric}[{window}]))"
    val = query_fn(prometheus_url, q, auth=auth)
    return val is not None and val > 0


def evaluate_warmup(
    outcome: WarmupOutcome,
    *,
    prometheus_url: Optional[str] = None,
    count_metric: Optional[str] = None,
    window: str = "1m",
    auth: Optional[Auth] = None,
    query_fn: Callable[..., Optional[float]] = prometheus_query.instant_query_value,
) -> tuple[bool, str]:
    """The combined FR-8 gate → ``(ready, reason)``. Fail-loud on every non-ready path.

    Ready iff: the driver exercised the subject **and** reached terminal success
    **and** (when a ``count_metric`` is given) that metric shows non-zero samples.
    Otherwise ``ready=False`` with a reason naming the driver / the empty metric —
    the caller maps a non-ready warm-up to ``unknown`` (never ``fail``).
    """
    if not outcome.exercised:
        return False, outcome.reason or f"warm-up driver '{outcome.driver}' could not exercise the subject"
    if not outcome.terminal_success:
        return False, outcome.reason or f"warm-up driver '{outcome.driver}' never reached terminal success"
    if count_metric:
        if not prometheus_url:
            return False, "warm-up convergence needs a prometheus_url to check non-zero samples"
        if not samples_landed(prometheus_url, count_metric, window=window, auth=auth, query_fn=query_fn):
            return False, (
                f"no non-zero samples for {count_metric} after warm-up "
                f"(driver '{outcome.driver}' succeeded, but the subject emits no such series)"
            )
    return True, ""


__all__ = [
    "SHAPE_SMOKE",
    "SHAPE_OB_HTTP",
    "SHAPE_OB_GRPC",
    "VALID_SHAPES",
    "HOST_DRIVABLE_SHAPES",
    "WarmupSpec",
    "WarmupOutcome",
    "DriverFns",
    "drive_warmup",
    "samples_landed",
    "evaluate_warmup",
]
