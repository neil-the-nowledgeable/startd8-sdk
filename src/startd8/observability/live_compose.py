# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Stand up a **multi-container** subject + a Prometheus scraping one of them.

Inc-1 of the expanded-subject-coverage effort (see
``docs/design/observability-compare/SUBJECT_COVERAGE_REQUIREMENTS.md``). Where
``live_standup.py`` boots a single subject image on a plain bridge, this boots an
N-container subject *topology* on a two-network compose and fronts it with the
same Prometheus warm-up gate the single-image path already trusts.

Design (OQ-B — resolved by CRP R1):
- **A new, leaner compose builder — NOT an import of ``benchmark_matrix``.**
  ``benchmark_matrix.fleet.compose`` couples to the global OB ``_SERVICES``
  registry at three sites (ingress validation, the dep-edge fan-out
  ``get_service(dep_name)``, and topo-order), so it cannot stand up an arbitrary
  subject. We reuse its *patterns* — an ``internal: true`` ``fleet`` network
  (service-DNS + network-layer egress-deny), an ``edge`` bridge carrying only the
  host↔Prometheus ingress, dependency-ordered bring-up — over our own lean
  topology model.
- **Single scrape target (FR-1 v1 boundary).** Exactly one ``metrics_service`` is
  scraped; ``render_prometheus_yml`` emits a single job. A topology may *contain*
  N containers but only one exposes the metrics compare-live replays.
- **The Tier-B replay + warm-up gate are reused unchanged (FR-3/FR-6).** We
  delegate the readiness poll to ``live_standup._await_scrape`` against the
  stood-up Prometheus; a timeout maps to ``unknown``, never ``fail``.
- **Fail-loud on a malformed topology (FR-5).** A missing/duplicate/unresolvable
  field raises :class:`TopologyError` and the caller reports ``unknown`` — never a
  partial standup.
- **N-container best-effort teardown (FR-7).** ``startd8-cmp-<hex>`` (the compose
  *project name*) is the sole ownership key; teardown removes the whole project
  best-effort, sweeps any survivor by that prefix, drops the temp dir, and reports
  a leaked-resource count rather than raising.
- **Every effect is injectable** (``runner`` / ``scrape_ready_check``) so the
  compose argv and the readiness path are unit-tested with zero docker.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from . import prometheus_query
from .live_standup import (
    PROMETHEUS_IMAGE,
    Runner,
    ScrapeReadyCheck,
    SeriesCountCheck,
    _await_scrape,
    _parse_duration_seconds,
    _parse_published_port,
    _swallow,
    render_prometheus_yml,
)
from .prometheus_query import Auth

FLEET_NETWORK = "fleet"
EDGE_NETWORK = "edge"

#: The compose service name Prometheus is emitted under. Reserved: a subject
#: container may not take it (validated on parse) so ``compose port`` is unambiguous.
PROMETHEUS_SERVICE = "prometheus"


class TopologyError(ValueError):
    """A malformed / incomplete subject topology (FR-1 schema violation).

    Raised by :func:`parse_subject_topology`; the caller maps it to an ``unknown``
    verdict (fail-loud per FR-5), never a partial standup.
    """


@dataclass(frozen=True)
class Container:
    """One subject container in the topology (FR-1)."""

    name: str
    image: str
    port: int
    deps: tuple[str, ...] = ()


@dataclass(frozen=True)
class SubjectTopology:
    """A validated multi-container subject topology (FR-1).

    Exactly one ``metrics_service`` (which must be one of ``containers``) exposes
    the ``metrics_port``/``metrics_path`` Prometheus scrapes.
    """

    containers: tuple[Container, ...]
    metrics_service: str
    metrics_port: int
    metrics_path: str = "/metrics"


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise TopologyError(msg)


def _as_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise TopologyError(f"{field_name} must be an integer, got {value!r}")


def parse_subject_topology(data: Any) -> SubjectTopology:
    """Parse + validate a lean subject-topology (FR-1). Raises :class:`TopologyError`.

    Accepts either a YAML string / bytes or an already-loaded mapping. Schema::

        containers:
          - {name: web, image: myapp:latest, port: 3000, deps: [db]}
          - {name: db,  image: postgres:16,  port: 5432}
        metrics_service: web
        metrics_port: 3000
        metrics_path: /metrics   # optional, defaults to /metrics

    Every failure is fail-loud (never a partial standup): a non-mapping document,
    an empty/absent ``containers`` list, a container missing ``name``/``image``/
    ``port``, a duplicate or reserved container name, a ``metrics_service`` /
    ``deps`` entry that names no container, or a dependency cycle.
    """
    if isinstance(data, (str, bytes)):
        try:
            data = yaml.safe_load(data)
        except yaml.YAMLError as e:  # noqa: BLE001 — surface as a topology error
            raise TopologyError(f"topology is not valid YAML: {e}")
    _require(isinstance(data, dict), "topology must be a mapping")

    raw_containers = data.get("containers")
    _require(
        isinstance(raw_containers, list) and len(raw_containers) > 0,
        "topology.containers must be a non-empty list",
    )

    containers: List[Container] = []
    seen: set[str] = set()
    for i, rc in enumerate(raw_containers):
        _require(isinstance(rc, dict), f"containers[{i}] must be a mapping")
        name = rc.get("name")
        image = rc.get("image")
        _require(isinstance(name, str) and name.strip() != "", f"containers[{i}].name is required")
        _require(isinstance(image, str) and image.strip() != "", f"container {name!r}: image is required")
        _require(name != PROMETHEUS_SERVICE, f"container name {name!r} is reserved (Prometheus service)")
        _require(name not in seen, f"duplicate container name {name!r}")
        seen.add(name)
        port = _as_int(rc.get("port"), f"container {name!r}: port")
        deps_raw = rc.get("deps", []) or []
        _require(isinstance(deps_raw, list), f"container {name!r}: deps must be a list")
        deps = tuple(str(d) for d in deps_raw)
        containers.append(Container(name=name, image=image, port=port, deps=deps))

    # deps must resolve to declared containers (before the cycle check reads them).
    for c in containers:
        for dep in c.deps:
            _require(dep in seen, f"container {c.name!r} dials unknown service {dep!r}")

    metrics_service = data.get("metrics_service")
    _require(
        isinstance(metrics_service, str) and metrics_service in seen,
        f"metrics_service must name one of {sorted(seen)}, got {metrics_service!r}",
    )
    metrics_port = _as_int(data.get("metrics_port"), "metrics_port")
    metrics_path = data.get("metrics_path", "/metrics") or "/metrics"
    _require(isinstance(metrics_path, str), "metrics_path must be a string")

    topology = SubjectTopology(
        containers=tuple(containers),
        metrics_service=metrics_service,
        metrics_port=metrics_port,
        metrics_path=metrics_path,
    )
    _topo_order(topology.containers)  # raises TopologyError on a dependency cycle
    return topology


def _topo_order(containers: tuple[Container, ...]) -> tuple[Container, ...]:
    """Dependency-ordered containers (a depended-on service precedes its dependents).

    Our own topo-sort (NOT ``benchmark_matrix.fleet.services.topo_order``, which is
    bound to the OB registry). Raises :class:`TopologyError` on a dependency cycle;
    unknown deps are already rejected by :func:`parse_subject_topology`.
    """
    by_name = {c.name: c for c in containers}
    ordered: List[Container] = []
    placed: set[str] = set()
    visiting: set[str] = set()

    def visit(c: Container) -> None:
        if c.name in placed:
            return
        if c.name in visiting:
            raise TopologyError(f"dependency cycle through {c.name!r}")
        visiting.add(c.name)
        for dep in c.deps:
            if dep in by_name:  # unknown deps already rejected; guard defensively
                visit(by_name[dep])
        visiting.discard(c.name)
        placed.add(c.name)
        ordered.append(c)

    for c in containers:
        visit(c)
    return tuple(ordered)


def generate_live_compose_dict(
    topology: SubjectTopology,
    *,
    host_port: int = 0,
    prometheus_image: str = PROMETHEUS_IMAGE,
    prometheus_yml_name: str = "prometheus.yml",
) -> Dict[str, Any]:
    """Build the docker-compose mapping for ``topology`` + a Prometheus ingress.

    Networking mirrors ``benchmark_matrix.fleet.compose``'s proven pattern:
    every subject container sits on the ``internal: true`` ``fleet`` network
    (service-DNS + egress-deny); Prometheus joins **both** ``fleet`` (to scrape the
    subject by DNS) and ``edge`` (to publish on a loopback host port). ``host_port``
    ``0`` publishes on an ephemeral loopback port resolved after boot.
    """
    services: Dict[str, Any] = {}
    for c in _topo_order(topology.containers):
        block: Dict[str, Any] = {"image": c.image, "networks": [FLEET_NETWORK]}
        if c.deps:
            block["depends_on"] = list(c.deps)
        services[c.name] = block

    services[PROMETHEUS_SERVICE] = {
        "image": prometheus_image,
        "networks": [FLEET_NETWORK, EDGE_NETWORK],
        "depends_on": [topology.metrics_service],
        "ports": [f"127.0.0.1:{host_port}:9090"],
        "volumes": [f"./{prometheus_yml_name}:/etc/prometheus/prometheus.yml:ro"],
    }

    return {
        "services": services,
        "networks": {
            # internal: true => no route out; peers reach each other by service-DNS
            # but cannot reach any external host (network-layer egress-deny).
            FLEET_NETWORK: {"internal": True},
            EDGE_NETWORK: {"driver": "bridge"},
        },
    }


@dataclass
class ComposeStandupHandle:
    """Everything the caller needs to replay against, and to tear down.

    Returned **even on partial failure** so the caller's ``finally`` always has the
    project name to sweep — never a leak. ``reason`` is empty on success.
    """

    prometheus_url: str
    job_name: str
    project_name: str
    metrics_service: str
    container_names: List[str] = field(default_factory=list)
    workdir: Optional[Path] = None
    compose_path: Optional[Path] = None
    subject_ready: bool = False
    scrape_ready: bool = False
    reason: str = ""
    leaked: int = 0
    run_cmds: List[List[str]] = field(default_factory=list)

    def teardown_hint(self) -> str:
        """The exact command a ``--keep-up`` run must issue to clean up (FR-7)."""
        cwd = f" (in {self.workdir})" if self.workdir else ""
        return f"docker compose -p {self.project_name} down -v --remove-orphans{cwd}"

    def to_dict(self) -> dict:
        return {
            "mode": "compose",
            "prometheus_url": self.prometheus_url,
            "job_name": self.job_name,
            "project_name": self.project_name,
            "metrics_service": self.metrics_service,
            "containers": list(self.container_names),
            "subject_ready": self.subject_ready,
            "scrape_ready": self.scrape_ready,
            "reason": self.reason,
            "leaked": self.leaked,
            "teardown_hint": self.teardown_hint(),
        }


def _compose(
    runner: Runner,
    workdir: Path,
    project: str,
    *args: str,
    timeout: float = 120.0,
) -> "subprocess.CompletedProcess[str]":
    """Run ``docker compose -p <project> <args>`` in ``workdir`` (never raises here)."""
    return runner(
        ["docker", "compose", "-p", project, *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
        cwd=str(workdir),
    )


def stand_up_compose_subject(
    *,
    topology: SubjectTopology,
    job_name: str = "subject",
    scrape_interval: str = "5s",
    scrape_timeout: float = 90.0,
    up_timeout: float = 300.0,
    run_id: Optional[str] = None,
    auth: Optional[Auth] = None,
    runner: Runner = subprocess.run,
    scrape_ready_check: ScrapeReadyCheck = prometheus_query.scrape_ready,
    series_count_check: Optional[SeriesCountCheck] = None,
    poll_interval: Optional[float] = None,
    docker_available_fn: Callable[[], bool] = None,  # type: ignore[assignment]
) -> ComposeStandupHandle:
    """Bring up ``topology`` + Prometheus via compose; return a handle once a scrape lands.

    The caller is responsible for :func:`tear_down_compose` in a ``finally`` block.
    """
    rid = run_id or uuid.uuid4().hex[:8]
    project = f"startd8-cmp-{rid}"  # the sole ownership key for teardown (FR-7)
    handle = ComposeStandupHandle(
        prometheus_url="",
        job_name=job_name,
        project_name=project,
        metrics_service=topology.metrics_service,
        container_names=[c.name for c in topology.containers] + [PROMETHEUS_SERVICE],
    )

    # Degrade-honest: no docker CLI → fail-loud handle, never a false green.
    _docker_available = docker_available_fn
    if _docker_available is None:
        from ..benchmark_matrix.fleet.containerize import docker_available as _docker_available  # noqa: E501
    if not _docker_available():
        handle.reason = "docker CLI not available on PATH"
        return handle

    # 1) render the compose + a single-job prometheus.yml into a temp project dir.
    workdir = Path(tempfile.mkdtemp(prefix="startd8-cmp-"))
    handle.workdir = workdir
    yml = render_prometheus_yml(
        job_name=job_name,
        target_host=topology.metrics_service,  # compose service-DNS name
        target_port=topology.metrics_port,
        metrics_path=topology.metrics_path,
        scrape_interval=scrape_interval,
    )
    (workdir / "prometheus.yml").write_text(yml, encoding="utf-8")
    compose = generate_live_compose_dict(topology, host_port=0)
    compose_path = workdir / "docker-compose.yml"
    compose_path.write_text(yaml.safe_dump(compose, sort_keys=False), encoding="utf-8")
    handle.compose_path = compose_path

    # 2) compose up -d (compose resolves depends_on ordering itself).
    up_cmd = ["docker", "compose", "-p", project, "up", "-d"]
    handle.run_cmds.append(up_cmd)
    r = _compose(runner, workdir, project, "up", "-d", timeout=up_timeout)
    if r.returncode != 0:
        handle.reason = f"compose up failed: {(r.stderr or r.stdout or '').strip()[:200]}"
        return handle
    handle.subject_ready = True  # containers started; the scrape gate is the real readiness

    # 3) resolve the published loopback Prometheus port.
    r = _compose(runner, workdir, project, "port", PROMETHEUS_SERVICE, "9090", timeout=30.0)
    port = _parse_published_port(r.stdout) if r.returncode == 0 else None
    if not port:
        handle.reason = "could not resolve the published Prometheus port"
        return handle
    handle.prometheus_url = f"http://127.0.0.1:{port}"

    # 4) the reused load-bearing warm-up gate (FR-3/FR-6): samples landed AND the
    #    series set settled across two consecutive scrapes.
    handle.scrape_ready = _await_scrape(
        handle.prometheus_url,
        job_name,
        scrape_timeout,
        auth=auth,
        ready_fn=scrape_ready_check,
        count_fn=series_count_check,
        scrape_interval_s=_parse_duration_seconds(scrape_interval),
        poll_interval=poll_interval,
    )
    if not handle.scrape_ready:
        handle.reason = (
            f"subject did not warm up within {scrape_timeout:.0f}s "
            f"(no sustained scrape of {topology.metrics_path} on "
            f"{topology.metrics_service}:{topology.metrics_port})"
        )
    return handle


def _count_leaked(runner: Runner, project: str) -> int:
    """Best-effort count of containers still owned by ``project`` (never raises)."""
    try:
        r = runner(
            ["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30.0,
        )
        if r.returncode == 0:
            return len([ln for ln in (r.stdout or "").splitlines() if ln.strip()])
    except Exception:  # noqa: BLE001 — the count is advisory
        pass
    return 0


def tear_down_compose(handle: ComposeStandupHandle, *, runner: Runner = subprocess.run) -> None:
    """Best-effort removal of the whole compose project, its network, and temp files.

    N-container contract (FR-7): teardown never raises, one failure does not abort
    the rest, the ``startd8-cmp-<hex>`` project is the sole ownership key, and any
    surviving container is recorded in ``handle.leaked`` rather than raising.
    """
    if handle.project_name and handle.workdir:
        _swallow(
            lambda: _compose(
                runner, handle.workdir, handle.project_name, "down", "-v", "--remove-orphans", timeout=120.0
            )
        )
    if handle.project_name:
        handle.leaked = _count_leaked(runner, handle.project_name)
    if handle.workdir:
        _swallow(lambda: shutil.rmtree(handle.workdir, ignore_errors=True))


__all__ = [
    "FLEET_NETWORK",
    "EDGE_NETWORK",
    "PROMETHEUS_SERVICE",
    "TopologyError",
    "Container",
    "SubjectTopology",
    "ComposeStandupHandle",
    "parse_subject_topology",
    "generate_live_compose_dict",
    "stand_up_compose_subject",
    "tear_down_compose",
]
