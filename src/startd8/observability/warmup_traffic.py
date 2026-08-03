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
#: FR-9 — a subject-supplied declarative domain-workload journey (http + opt-in command
#: steps). Generalizes ``smoke`` (auto-discovered CRUD) to an authored workflow so
#: per-component, domain-gated metrics register. Driven by ``run_workload_journey`` (a
#: single pass through the steps), NOT the ``drive_warmup`` iteration loop — most domain
#: ops (create-project, push-image) are not idempotent.
SHAPE_WORKLOAD = "workload"
VALID_SHAPES = (SHAPE_SMOKE, SHAPE_OB_HTTP, SHAPE_OB_GRPC, SHAPE_WORKLOAD)

#: The shapes a host-side driver loop can exercise (v1). ``ob-grpc`` needs an in-fleet
#: driver (the subject's gRPC ports stay on the internal, host-unreachable fleet net), so
#: the standup wiring defers it; the driver itself is still selectable here for the future
#: in-compose sidecar. ``workload`` is host-drivable (http + host commands).
HOST_DRIVABLE_SHAPES = (SHAPE_SMOKE, SHAPE_OB_HTTP, SHAPE_WORKLOAD)


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
    #: FR-9 — the union of the workload steps' ``registers_metric`` (the count metrics the
    #: caller feeds to :func:`evaluate_warmup` for the non-zero-samples gate). Empty for the
    #: non-workload shapes (they take a single ``--warm-up-metric``). Additive/back-compat.
    registers_metrics: tuple = ()
    #: FR-9 — per-step results, for a fail-loud report (name → detail). Empty for other shapes.
    step_results: tuple = ()

    def to_dict(self) -> dict:
        return {
            "driver": self.driver,
            "exercised": self.exercised,
            "terminal_success": self.terminal_success,
            "iterations": self.iterations,
            "reason": self.reason,
            "registers_metrics": list(self.registers_metrics),
            "step_results": list(self.step_results),
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
    if spec.shape == SHAPE_WORKLOAD:
        # FR-9: the workload shape drives a single pass through a subject-supplied WorkloadSpec
        # (non-idempotent domain ops), not this iteration loop. The caller must use
        # run_workload_journey(workload_spec, base_url=..., ...) directly.
        return WarmupOutcome(
            driver=SHAPE_WORKLOAD,
            reason="workload shape uses run_workload_journey(spec, base_url=...), not drive_warmup",
        )
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


# ---------------------------------------------------------------------------
# FR-9 — declarative domain-workload journey (SHAPE_WORKLOAD)
# ---------------------------------------------------------------------------

@dataclass
class WorkloadStep:
    """One authored domain operation in a WorkloadSpec (FR-9.1)."""

    name: str
    kind: str = "http"                       # "http" | "command"
    # http
    method: str = "GET"
    path: str = ""
    body: Optional[Any] = None
    auth_ref: Optional[str] = None           # references the spec-level auth block
    expect_status: str = "2xx"               # "2xx" | "any" | explicit like "200,201,409"
    # command (opt-in; non-HTTP effects, e.g. `docker push`)
    argv: Optional[list] = None
    env: Optional[Dict[str, str]] = None
    # convergence
    registers_metric: str = ""               # count/total metric this step should make non-zero
    optional: bool = False                   # a failing optional step does not sink terminal_success


@dataclass
class WorkloadSpec:
    """A subject-supplied, subject-agnostic domain-workload journey (FR-9.1/9.4/9.6)."""

    name: str
    steps: list
    #: {"kind": "basic"|"bearer"|"none", "user"?, "password_env"?, "token_env"?} — creds come
    #: from the ENV only (password_env / token_env name the var), and are redacted in logs.
    auth: Optional[Dict[str, str]] = None


def load_workload_spec(path: str) -> WorkloadSpec:
    """Load a WorkloadSpec from a JSON (or YAML if pyyaml is present) file. Fail-loud on shape."""
    import json
    from pathlib import Path as _P

    text = _P(path).read_text()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        import yaml  # optional; only needed for .yaml specs

        raw = yaml.safe_load(text)
    if not isinstance(raw, dict) or not isinstance(raw.get("steps"), list):
        raise ValueError(f"{path}: WorkloadSpec must be an object with a 'steps' list")
    steps = [WorkloadStep(**s) for s in raw["steps"]]
    return WorkloadSpec(name=str(raw.get("name") or _P(path).stem), steps=steps, auth=raw.get("auth"))


def _status_ok(code: int, expect: str) -> bool:
    expect = (expect or "2xx").strip().lower()
    if expect == "any":
        return True
    if expect == "2xx":
        return 200 <= code < 300
    return str(code) in {c.strip() for c in expect.split(",")}


def _resolve_app_auth(spec: WorkloadSpec) -> tuple:
    """App-level auth for the workload's HTTP steps → (basic_tuple|None, headers|None).

    Distinct from the Prometheus :class:`Auth` (bearer for the metrics backend). Credentials
    come from the ENV only (FR-9.4): ``password_env`` / ``token_env`` name the var, never a
    literal in the spec.
    """
    import os

    a = spec.auth or {}
    kind = str(a.get("kind") or "none").lower()
    if kind == "basic":
        return (str(a.get("user") or ""), os.environ.get(str(a.get("password_env") or ""), "")), None
    if kind == "bearer":
        tok = os.environ.get(str(a.get("token_env") or ""), "")
        return None, ({"Authorization": f"Bearer {tok}"} if tok else None)
    return None, None


def _default_http_runner(step: WorkloadStep, *, base_url: str, basic=None, headers=None) -> tuple[int, str]:
    """Real HTTP step → (status_code, detail). Never raises (a hiccup is a non-success)."""
    import httpx

    kwargs: Dict[str, Any] = {"timeout": 15.0}
    if basic:
        kwargs["auth"] = basic
    if headers:
        kwargs["headers"] = headers
    try:
        r = httpx.request(step.method.upper(), base_url.rstrip("/") + step.path,
                          json=step.body if step.body is not None else None, **kwargs)
        return r.status_code, ""
    except Exception as e:  # noqa: BLE001 — a transport hiccup is a non-success, not a crash
        return 0, f"{type(e).__name__}: {e}"


def _default_command_runner(step: WorkloadStep) -> tuple[int, str]:
    import os
    import subprocess

    env = {**os.environ, **(step.env or {})}
    try:
        p = subprocess.run(step.argv or [], env=env, capture_output=True, text=True, timeout=120)
        return p.returncode, (p.stderr or "")[:200]
    except Exception as e:  # noqa: BLE001
        return 1, f"{type(e).__name__}: {e}"


def run_workload_journey(
    spec: WorkloadSpec,
    *,
    base_url: str,
    allow_commands: bool = False,
    http_runner: Optional[Callable[..., tuple]] = None,
    command_runner: Optional[Callable[..., tuple]] = None,
) -> WarmupOutcome:
    """FR-9.2 — one pass through the spec's steps → a WarmupOutcome (reuses the dataclass +
    :func:`evaluate_warmup`). ``exercised`` = ≥1 step succeeded; ``terminal_success`` = every
    non-``optional`` step reached its ``expect_status``. Command steps are no-ops unless
    ``allow_commands`` (FR-9.1). Fully injectable (``http_runner``/``command_runner``) → tested
    with zero network / zero docker. Never raises."""
    http_runner = http_runner or _default_http_runner
    command_runner = command_runner or _default_command_runner
    basic, headers = _resolve_app_auth(spec)
    out = WarmupOutcome(driver=SHAPE_WORKLOAD, iterations=1)
    metrics: list = []
    results: list = []
    all_required_ok = True
    for step in spec.steps:
        if step.kind == "command":
            if not allow_commands:
                results.append((step.name, "skipped (commands not allowed)"))
                if not step.optional:
                    all_required_ok = False
                continue  # a skipped optional step does NOT contribute its metric to the required union
            rc, detail = command_runner(step)
            ok = rc == 0
        else:
            code, detail = http_runner(step, base_url=base_url, basic=basic, headers=headers)
            ok = code != 0 and _status_ok(code, step.expect_status)
            detail = detail or f"status={code}"
        results.append((step.name, "ok" if ok else f"FAIL: {detail}"))
        if ok:
            out.exercised = True
            # Only a step that actually ran should require its metric to land — a
            # skipped/failed step must not force its registers_metric into the gate.
            if step.registers_metric:
                metrics.append(step.registers_metric)
        elif not step.optional:
            all_required_ok = False
    out.terminal_success = out.exercised and all_required_ok
    out.registers_metrics = tuple(dict.fromkeys(metrics))  # dedup, preserve order
    out.step_results = tuple(results)
    if not out.exercised:
        out.reason = f"workload '{spec.name}' exercised nothing: {results}"
    elif not out.terminal_success:
        out.reason = f"workload '{spec.name}' had a required step fail: {[r for r in results if 'FAIL' in r[1] or 'skipped' in r[1]]}"
    return out


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
    # count_metric may be a single name (smoke/ob shapes) or a list (FR-9 workload: the union of the
    # steps' registers_metric). A list requires EVERY metric to land — a job that silently never ran
    # leaves its metric at zero and must fail-loud, not green.
    metrics = [count_metric] if isinstance(count_metric, str) else list(count_metric or [])
    if metrics:
        if not prometheus_url:
            return False, "warm-up convergence needs a prometheus_url to check non-zero samples"
        empty = [m for m in metrics
                 if not samples_landed(prometheus_url, m, window=window, auth=auth, query_fn=query_fn)]
        if empty:
            return False, (
                f"no non-zero samples for {empty} after warm-up "
                f"(driver '{outcome.driver}' succeeded, but the subject emits no such series)"
            )
    return True, ""


__all__ = [
    "SHAPE_SMOKE",
    "SHAPE_OB_HTTP",
    "SHAPE_OB_GRPC",
    "SHAPE_WORKLOAD",
    "VALID_SHAPES",
    "HOST_DRIVABLE_SHAPES",
    "WarmupSpec",
    "WarmupOutcome",
    "DriverFns",
    "drive_warmup",
    "WorkloadStep",
    "WorkloadSpec",
    "load_workload_spec",
    "run_workload_journey",
    "samples_landed",
    "evaluate_warmup",
]
