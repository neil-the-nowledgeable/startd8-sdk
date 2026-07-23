# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Stand up a single subject image + a Prometheus scraping its ``/metrics``.

The Tier-B substrate for ``compare_live`` (see
``docs/design/observability-compare/REQUIREMENTS.md``). It owns **only** the
container lifecycle: create a per-run bridge network, render a ``prometheus.yml``
scrape config, ``docker run`` the subject and a ``prom/prometheus`` sibling on
that network (Prometheus reaches the subject by Docker service-DNS), publish
Prometheus on loopback, and **wait for the first scrape to land** before the
caller replays any PromQL.

Design notes:
- **Single-image v1 (FR-1 / NR-1).** One ``subject_image``. Multi-container
  subjects (Mastodon = Postgres+Redis+Sidekiq) are reached via
  ``compare-live --prometheus <existing-backend>``, not stood up here.
- **We own the subject ``docker run`` argv** (rather than call
  ``fleet.containerize.boot_and_probe``) so we can join the subject to the shared
  ``--network`` — a capability ``boot_and_probe`` does not expose (OQ-1). We reuse
  its *semantics* (``docker_available`` gate, port-accept readiness) without
  editing the tracked ``benchmark_matrix`` module.
- **Scrape-ready gate is load-bearing (FR-3).** Replaying before the first scrape
  lands reads empty for every query — a false all-``fail`` report. The gate polls
  ``prometheus_query.scrape_ready`` (``scrape_samples_scraped>0``); a timeout is
  reported as ``scrape_ready=False`` and mapped by the caller to ``unknown``,
  never ``fail``.
- **Loopback only.** Prometheus is published on ``127.0.0.1`` so the
  ``validate_promql`` prod-replay guardrail (``_is_local_backend``) passes
  naturally without ``--allow-prod``.
- **Every effect is injectable** (``runner`` / ``scrape_ready_check``) so argv
  construction and the readiness path are unit-tested with zero docker (FR-10).
"""

from __future__ import annotations

import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, List, Optional

from . import prometheus_query
from .prometheus_query import Auth

#: The Prometheus image. Pinning to a digest (``prom/prometheus@sha256:…``) and a
#: documented pre-pull is the airgapped-CI hardening step (R3) — a tag keeps the
#: default path working without asserting a digest we cannot verify here.
PROMETHEUS_IMAGE = "prom/prometheus:v2.53.0"

Runner = Callable[..., "subprocess.CompletedProcess[str]"]
ScrapeReadyCheck = Callable[..., bool]
SeriesCountCheck = Callable[..., Optional[float]]


def render_prometheus_yml(
    *,
    job_name: str,
    target_host: str,
    target_port: int,
    metrics_path: str = "/metrics",
    scrape_interval: str = "5s",
) -> str:
    """A minimal single-job ``prometheus.yml`` scraping ``target_host:target_port``.

    Pure string render (no I/O) so it is unit-testable. A short ``scrape_interval``
    (5s, not the 15s default) lets the readiness gate resolve quickly. ``target_host``
    MUST be the exact ``--name`` of the subject container so Docker service-DNS
    resolves it (R4: one ``run_id`` is the single source of truth for both).
    """
    return (
        "global:\n"
        f"  scrape_interval: {scrape_interval}\n"
        "scrape_configs:\n"
        f"  - job_name: {job_name}\n"
        f"    metrics_path: {metrics_path}\n"
        "    static_configs:\n"
        f"      - targets: ['{target_host}:{target_port}']\n"
    )


@dataclass
class StandupHandle:
    """Everything the caller needs to replay against, and to tear down.

    Returned **even on partial failure** (network created but Prometheus crashed)
    so the caller's ``finally`` always has the names to remove — never a leak.
    ``reason`` is empty on success and explains the first failure otherwise.
    """

    prometheus_url: str
    job_name: str
    network: str
    subject_container: str
    prometheus_container: str
    prometheus_yml_path: Optional[Path] = None
    subject_ready: bool = False
    scrape_ready: bool = False
    reason: str = ""
    run_cmds: List[List[str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "prometheus_url": self.prometheus_url,
            "job_name": self.job_name,
            "network": self.network,
            "subject_container": self.subject_container,
            "prometheus_container": self.prometheus_container,
            "subject_ready": self.subject_ready,
            "scrape_ready": self.scrape_ready,
            "reason": self.reason,
        }

    def teardown_hint(self) -> str:
        """The exact commands a ``--keep-up`` run must issue to clean up (FR-9)."""
        return (
            f"docker rm -f {self.subject_container} {self.prometheus_container}; "
            f"docker network rm {self.network}"
        )


def _run(runner: Runner, argv: List[str], *, timeout: float = 60.0) -> "subprocess.CompletedProcess[str]":
    return runner(argv, capture_output=True, text=True, check=False, timeout=timeout)


def _parse_duration_seconds(value: str, *, default: float = 5.0) -> float:
    """Parse a Prometheus-style duration (``5s`` / ``500ms`` / ``2m``) to seconds."""
    s = str(value).strip()
    try:
        if s.endswith("ms"):
            return float(s[:-2]) / 1000.0
        if s.endswith("s"):
            return float(s[:-1])
        if s.endswith("m"):
            return float(s[:-1]) * 60.0
        return float(s)
    except (TypeError, ValueError):
        return default


def job_series_count(
    prometheus_url: str, job: str, *, auth: Optional[Auth] = None
) -> Optional[float]:
    """Number of distinct series Prometheus currently holds for ``job`` (``count({job=…})``).

    Watching this settle is how the warm-up gate distinguishes "the metric surface has
    finished registering" from "one scrape landed but lazy SLI series are still appearing."
    """
    return prometheus_query.instant_query_value(
        prometheus_url, f'count({{job="{job}"}})', auth=auth
    )


def _await_scrape(
    prometheus_url: str,
    job: str,
    timeout: float,
    *,
    auth: Optional[Auth] = None,
    scrape_interval_s: float = 5.0,
    poll_interval: Optional[float] = None,
    ready_fn: ScrapeReadyCheck = prometheus_query.scrape_ready,
    count_fn: Optional[SeriesCountCheck] = None,
    require_stable: bool = True,
) -> bool:
    """Poll until the subject is **warm**, or ``timeout`` elapses.

    Warm = samples have landed (``ready_fn``) **and** the job's series-set size is
    ``>0`` and **unchanged across two consecutive scrapes** (``count_fn``). Gating on
    the first landed sample alone releases before lazily-registered SLI series appear
    (lazy histograms, first-request counters), so replay reads those series as absent
    and the derived SLI surfaces a false ``fail`` — the exact false-negative Tier B
    exists to prevent (R1-F1/F2).

    The poll cadence is ``>=`` the scrape interval so each stability comparison spans a
    *fresh* scrape: an unchanged count read twice within a single scrape interval would
    be a false "settled" (nothing re-scraped). Errors (backend not up yet) are swallowed
    so the poll keeps trying.
    """
    count_fn = count_fn or job_series_count
    interval = poll_interval if poll_interval is not None else max(1.0, scrape_interval_s)
    deadline = time.monotonic() + timeout
    prev: Optional[float] = None
    while time.monotonic() < deadline:
        try:
            if ready_fn(prometheus_url, job, auth=auth):
                if not require_stable:
                    return True
                count = count_fn(prometheus_url, job, auth=auth)
                if count is not None and count > 0 and prev is not None and count == prev:
                    return True  # two consecutive scrapes agree on the series set → warm
                prev = count
        except Exception:  # noqa: BLE001 — backend not ready yet; keep polling
            pass
        time.sleep(interval)
    return False


def _parse_published_port(docker_port_stdout: str) -> Optional[int]:
    """Parse ``docker port <name> 9090`` output (``127.0.0.1:49153``) → 49153."""
    for line in (docker_port_stdout or "").splitlines():
        line = line.strip()
        if ":" in line:
            try:
                return int(line.rsplit(":", 1)[1])
            except (ValueError, IndexError):
                continue
    return None


def stand_up_subject_and_prometheus(
    *,
    subject_image: str,
    subject_port: int = 8080,
    job_name: str = "subject",
    metrics_path: str = "/metrics",
    scrape_interval: str = "5s",
    scrape_timeout: float = 60.0,
    run_id: Optional[str] = None,
    auth: Optional[Auth] = None,
    runner: Runner = subprocess.run,
    scrape_ready_check: ScrapeReadyCheck = prometheus_query.scrape_ready,
    series_count_check: Optional[SeriesCountCheck] = None,
    poll_interval: Optional[float] = None,
    docker_available_fn: Callable[[], bool] = None,  # type: ignore[assignment]
) -> StandupHandle:
    """Bring up ``subject_image`` + Prometheus; return a handle once a scrape lands.

    The caller is responsible for :func:`tear_down` in a ``finally`` block — the
    subject/Prometheus runs deliberately drop ``--rm`` so a crashed container's
    logs survive for the failure ``reason``.
    """
    rid = run_id or uuid.uuid4().hex[:8]
    network = f"startd8-cmp-{rid}"
    subject_container = f"cmp-subject-{rid}"
    prometheus_container = f"cmp-prom-{rid}"
    handle = StandupHandle(
        prometheus_url="",
        job_name=job_name,
        network=network,
        subject_container=subject_container,
        prometheus_container=prometheus_container,
    )

    # Degrade-honest: no docker CLI → return a fail-loud handle, never a false green.
    _docker_available = docker_available_fn
    if _docker_available is None:
        from ..benchmark_matrix.fleet.containerize import docker_available as _docker_available  # noqa: E501
    if not _docker_available():
        handle.reason = "docker CLI not available on PATH"
        return handle

    # 1) per-run bridge network (service-DNS reachable, no egress-deny needed).
    r = _run(runner, ["docker", "network", "create", network])
    if r.returncode != 0:
        handle.reason = f"docker network create failed: {(r.stderr or r.stdout or '').strip()[:200]}"
        return handle

    # 2) scrape config → temp file bind-mounted into Prometheus.
    yml = render_prometheus_yml(
        job_name=job_name,
        target_host=subject_container,  # R4: DNS name == subject --name
        target_port=subject_port,
        metrics_path=metrics_path,
        scrape_interval=scrape_interval,
    )
    tmp = tempfile.NamedTemporaryFile("w", suffix="-prometheus.yml", delete=False, encoding="utf-8")
    tmp.write(yml)
    tmp.close()
    handle.prometheus_yml_path = Path(tmp.name)

    # 3) subject — we own the argv so it joins the shared network (OQ-1).
    subject_cmd = [
        "docker", "run", "-d", "--network", network,
        "--name", subject_container, subject_image,
    ]
    handle.run_cmds.append(subject_cmd)
    r = _run(runner, subject_cmd)
    if r.returncode != 0:
        handle.reason = f"subject boot failed: {(r.stderr or r.stdout or '').strip()[:200]}"
        return handle
    handle.subject_ready = True  # container started; the scrape gate is the real readiness

    # 4) Prometheus, publishing 9090 on loopback (keeps the prod-replay guardrail happy).
    prom_cmd = [
        "docker", "run", "-d", "--network", network,
        "--name", prometheus_container,
        "-p", "127.0.0.1:0:9090",
        "-v", f"{handle.prometheus_yml_path}:/etc/prometheus/prometheus.yml:ro",
        PROMETHEUS_IMAGE,
    ]
    handle.run_cmds.append(prom_cmd)
    r = _run(runner, prom_cmd)
    if r.returncode != 0:
        handle.reason = f"prometheus boot failed: {(r.stderr or r.stdout or '').strip()[:200]}"
        return handle

    # 5) read back the published loopback port.
    r = _run(runner, ["docker", "port", prometheus_container, "9090"])
    port = _parse_published_port(r.stdout) if r.returncode == 0 else None
    if not port:
        handle.reason = "could not resolve the published Prometheus port"
        return handle
    handle.prometheus_url = f"http://127.0.0.1:{port}"

    # 6) the load-bearing warm-up gate: samples landed AND the series set has settled
    #    across two consecutive scrapes (R1-F1/F2 — avoids releasing before lazy SLI
    #    series register, which would surface a false `fail`).
    handle.scrape_ready = _await_scrape(
        handle.prometheus_url, job_name, scrape_timeout,
        auth=auth, ready_fn=scrape_ready_check, count_fn=series_count_check,
        scrape_interval_s=_parse_duration_seconds(scrape_interval),
        poll_interval=poll_interval,
    )
    if not handle.scrape_ready:
        handle.reason = (
            f"subject did not warm up within {scrape_timeout:.0f}s "
            f"(no sustained scrape of {metrics_path} on :{subject_port})"
        )
    return handle


def tear_down(handle: StandupHandle, *, runner: Runner = subprocess.run) -> None:
    """Best-effort removal of both containers, the network, and the temp config.

    Never raises: each step is independent so one failure does not leak the rest.
    Runs on every path (pass/fail/scrape-timeout/exception) via the caller's
    ``finally`` (FR-9).
    """
    for name in (handle.subject_container, handle.prometheus_container):
        if name:
            _swallow(lambda: _run(runner, ["docker", "rm", "-f", name], timeout=30.0))
    if handle.network:
        _swallow(lambda: _run(runner, ["docker", "network", "rm", handle.network], timeout=30.0))
    if handle.prometheus_yml_path:
        _swallow(lambda: handle.prometheus_yml_path.unlink(missing_ok=True))  # type: ignore[union-attr]


def _swallow(fn: Callable[[], Any]) -> None:
    try:
        fn()
    except Exception:  # noqa: BLE001 — teardown is best-effort, never masks the real outcome
        pass


__all__ = [
    "PROMETHEUS_IMAGE",
    "StandupHandle",
    "render_prometheus_yml",
    "job_series_count",
    "stand_up_subject_and_prometheus",
    "tear_down",
]
