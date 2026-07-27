# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Unit tests for the Inc-1 multi-container standup — no docker, all seams injected.

Covers the FR-1 topology schema (fail-loud), the FR-2 two-network compose shape,
the FR-3 reused warm-up gate, and the FR-7 N-container best-effort teardown.
"""

from __future__ import annotations

import subprocess

import pytest
import yaml

from startd8.observability import live_compose

_MINIMAL = """
containers:
  - {name: web, image: myapp:latest, port: 3000, deps: [db]}
  - {name: db,  image: postgres:16,  port: 5432}
metrics_service: web
metrics_port: 3000
metrics_path: /metrics
"""


# ── FR-1: topology parsing / schema (fail-loud) ─────────────────────────────

def test_parse_minimal_topology():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    assert [c.name for c in topo.containers] == ["web", "db"]
    assert topo.metrics_service == "web"
    assert topo.metrics_port == 3000
    assert topo.metrics_path == "/metrics"
    web = next(c for c in topo.containers if c.name == "web")
    assert web.deps == ("db",)


def test_parse_accepts_a_preloaded_mapping():
    topo = live_compose.parse_subject_topology(yaml.safe_load(_MINIMAL))
    assert topo.metrics_service == "web"


def test_parse_defaults_metrics_path():
    topo = live_compose.parse_subject_topology(
        {"containers": [{"name": "a", "image": "i", "port": 1}], "metrics_service": "a", "metrics_port": 1}
    )
    assert topo.metrics_path == "/metrics"


@pytest.mark.parametrize(
    "doc, needle",
    [
        ("[]", "must be a mapping"),
        ("containers: []\nmetrics_service: a\nmetrics_port: 1", "non-empty list"),
        ("containers:\n  - {image: i, port: 1}\nmetrics_service: a\nmetrics_port: 1", "name is required"),
        ("containers:\n  - {name: a, port: 1}\nmetrics_service: a\nmetrics_port: 1", "image is required"),
        ("containers:\n  - {name: a, image: i, port: x}\nmetrics_service: a\nmetrics_port: 1", "port must be an integer"),
        (
            "containers:\n  - {name: a, image: i, port: 1}\n  - {name: a, image: j, port: 2}\nmetrics_service: a\nmetrics_port: 1",
            "duplicate container name",
        ),
        (
            "containers:\n  - {name: prometheus, image: i, port: 1}\nmetrics_service: prometheus\nmetrics_port: 1",
            "reserved",
        ),
        (
            "containers:\n  - {name: a, image: i, port: 1}\nmetrics_service: nope\nmetrics_port: 1",
            "metrics_service must name one of",
        ),
        (
            "containers:\n  - {name: a, image: i, port: 1, deps: [ghost]}\nmetrics_service: a\nmetrics_port: 1",
            "unknown service 'ghost'",
        ),
    ],
)
def test_parse_rejects_malformed_topology(doc, needle):
    with pytest.raises(live_compose.TopologyError) as e:
        live_compose.parse_subject_topology(doc)
    assert needle in str(e.value)


def test_parse_rejects_dependency_cycle():
    doc = {
        "containers": [
            {"name": "a", "image": "i", "port": 1, "deps": ["b"]},
            {"name": "b", "image": "j", "port": 2, "deps": ["a"]},
        ],
        "metrics_service": "a",
        "metrics_port": 1,
    }
    with pytest.raises(live_compose.TopologyError) as e:
        live_compose.parse_subject_topology(doc)
    assert "cycle" in str(e.value)


# ── FR-2: two-network compose shape ─────────────────────────────────────────

def test_compose_dict_two_networks_and_prometheus_ingress():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    compose = live_compose.generate_live_compose_dict(topo, host_port=0)

    # fleet is internal (egress-deny + service-DNS); edge is a plain bridge.
    assert compose["networks"][live_compose.FLEET_NETWORK] == {"internal": True}
    assert compose["networks"][live_compose.EDGE_NETWORK] == {"driver": "bridge"}

    # subject containers sit on the internal fleet net only.
    for name in ("web", "db"):
        assert compose["services"][name]["networks"] == [live_compose.FLEET_NETWORK]
    # depends_on preserved for dependency-ordered bring-up.
    assert compose["services"]["web"]["depends_on"] == ["db"]

    # Prometheus joins BOTH nets, publishes on loopback, mounts the scrape config.
    prom = compose["services"][live_compose.PROMETHEUS_SERVICE]
    assert prom["networks"] == [live_compose.FLEET_NETWORK, live_compose.EDGE_NETWORK]
    assert prom["ports"] == ["127.0.0.1:0:9090"]
    assert prom["depends_on"] == ["web"]  # the metrics_service
    assert any(":/etc/prometheus/prometheus.yml:ro" in v for v in prom["volumes"])


def test_compose_services_emitted_in_dependency_order():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    compose = live_compose.generate_live_compose_dict(topo)
    names = [n for n in compose["services"] if n != live_compose.PROMETHEUS_SERVICE]
    # db is depended-on by web → db precedes web.
    assert names.index("db") < names.index("web")


# ── a fake docker-compose runner ────────────────────────────────────────────

class FakeRunner:
    """Records argv; returns canned results keyed by the compose subcommand."""

    def __init__(self, *, port_stdout="127.0.0.1:49153", fail_on=None, leaked_ids=""):
        self.calls = []
        self.port_stdout = port_stdout
        self.fail_on = fail_on or ()  # e.g. ("up",) to fail `docker compose up`
        self.leaked_ids = leaked_ids

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        # docker compose -p <proj> <sub> ...  → sub at index 4; plain `docker ps ...` → index 1
        if argv[:2] == ["docker", "compose"]:
            sub = argv[4] if len(argv) > 4 else ""
        else:
            sub = argv[1] if len(argv) > 1 else ""
        if sub in self.fail_on:
            return subprocess.CompletedProcess(argv, 1, "", "boom")
        if sub == "port":
            return subprocess.CompletedProcess(argv, 0, self.port_stdout, "")
        if sub == "ps":
            return subprocess.CompletedProcess(argv, 0, self.leaked_ids, "")
        return subprocess.CompletedProcess(argv, 0, "ok\n", "")


def _flat(calls):
    return [" ".join(c) for c in calls]


# ── FR-3 / FR-6: standup boots compose and gates on the reused warm-up ───────

def test_standup_boots_compose_and_gates_on_scrape(tmp_path):
    topo = live_compose.parse_subject_topology(_MINIMAL)
    runner = FakeRunner()
    handle = live_compose.stand_up_compose_subject(
        topology=topo,
        run_id="abc123",
        runner=runner,
        scrape_ready_check=lambda url, job, auth=None: True,
        series_count_check=lambda url, job, auth=None: 9.0,  # stable → warm
        poll_interval=0.0,
        docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is True
    assert handle.reason == ""
    assert handle.prometheus_url == "http://127.0.0.1:49153"
    assert handle.project_name == "startd8-cmp-abc123"

    flat = _flat(runner.calls)
    assert any("docker compose -p startd8-cmp-abc123 up -d" in c for c in flat)
    assert any("docker compose -p startd8-cmp-abc123 port prometheus 9090" in c for c in flat)

    # the compose + prometheus.yml were rendered into the project workdir.
    assert (handle.workdir / "docker-compose.yml").exists()
    assert (handle.workdir / "prometheus.yml").exists()
    prom_yml = (handle.workdir / "prometheus.yml").read_text()
    assert "targets: ['web:3000']" in prom_yml  # scrapes the metrics_service by DNS


def test_standup_scrape_timeout_is_unknown_not_fail():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    handle = live_compose.stand_up_compose_subject(
        topology=topo,
        run_id="t1",
        scrape_timeout=0.05,
        runner=FakeRunner(),
        scrape_ready_check=lambda url, job, auth=None: False,  # never ready
        poll_interval=0.0,
        docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is False
    assert "did not warm up" in handle.reason
    assert handle.project_name  # teardown still has the ownership key


def test_standup_no_docker_is_fail_loud():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="nd", runner=FakeRunner(), docker_available_fn=lambda: False
    )
    assert handle.scrape_ready is False
    assert "docker" in handle.reason.lower()


def test_standup_compose_up_failure_returns_handle_with_reason():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="nf", runner=FakeRunner(fail_on=("up",)),
        docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is False
    assert "compose up failed" in handle.reason


def test_standup_unresolved_port_is_fail_loud():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="np", runner=FakeRunner(port_stdout="garbage-no-port"),
        docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is False
    assert "published Prometheus port" in handle.reason


# ── FR-7: N-container best-effort teardown ──────────────────────────────────

def test_teardown_removes_project_and_workdir(tmp_path):
    workdir = tmp_path / "proj"
    workdir.mkdir()
    (workdir / "docker-compose.yml").write_text("x")
    handle = live_compose.ComposeStandupHandle(
        prometheus_url="", job_name="subject", project_name="startd8-cmp-z9",
        metrics_service="web", workdir=workdir,
    )
    runner = FakeRunner()  # ps returns no leaked ids
    live_compose.tear_down_compose(handle, runner=runner)

    flat = _flat(runner.calls)
    assert any("docker compose -p startd8-cmp-z9 down -v --remove-orphans" in c for c in flat)
    assert handle.leaked == 0
    assert not workdir.exists()  # temp dir swept


def test_standup_never_raises_after_up_so_caller_can_tear_down():
    # FR-7 safety: a subprocess TIMEOUT (or any raise) AFTER `compose up` must not
    # propagate — else the caller's `finally: if handle is not None` never runs and the
    # whole fleet leaks. The standup must catch it and return the handle (with workdir +
    # project set) so teardown owns cleanup.
    class RaisingAfterUp:
        def __init__(self):
            self.calls = []

        def __call__(self, argv, **kwargs):
            self.calls.append(argv)
            sub = argv[4] if argv[:2] == ["docker", "compose"] and len(argv) > 4 else ""
            if sub == "up":
                return subprocess.CompletedProcess(argv, 0, "ok\n", "")
            if sub == "port":  # times out AFTER containers are up
                raise subprocess.TimeoutExpired(cmd=argv, timeout=30.0)
            return subprocess.CompletedProcess(argv, 0, "ok\n", "")

    topo = live_compose.parse_subject_topology(_MINIMAL)
    runner = RaisingAfterUp()
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="raise1", runner=runner, docker_available_fn=lambda: True,
    )
    # did NOT propagate; returned a fail-loud handle the caller's finally can tear down.
    assert handle.scrape_ready is False
    assert "standup error" in handle.reason
    assert handle.project_name == "startd8-cmp-raise1"
    assert handle.workdir is not None  # teardown has the project dir to sweep
    # clean up the temp dir the test created.
    live_compose.tear_down_compose(handle, runner=lambda *a, **k: subprocess.CompletedProcess(a, 0, "", ""))


def test_teardown_reports_leaked_count_without_raising():
    handle = live_compose.ComposeStandupHandle(
        prometheus_url="", job_name="subject", project_name="startd8-cmp-lk",
        metrics_service="web", workdir=None,
    )
    # down fails AND ps reports two survivors → leaked=2, never raises.
    runner = FakeRunner(fail_on=("down",), leaked_ids="cid1\ncid2\n")
    live_compose.tear_down_compose(handle, runner=runner)
    assert handle.leaked == 2


def test_teardown_hint_is_a_compose_down():
    handle = live_compose.ComposeStandupHandle(
        prometheus_url="", job_name="subject", project_name="startd8-cmp-h1",
        metrics_service="web",
    )
    hint = handle.teardown_hint()
    assert "docker compose -p startd8-cmp-h1 down -v --remove-orphans" in hint
    assert handle.to_dict()["teardown_hint"] == hint
    assert handle.to_dict()["mode"] == "compose"


# ── FR-8: warm-up traffic wired into the compose standup ────────────────────

def test_compose_dict_publishes_ingress_when_requested():
    topo = live_compose.parse_subject_topology(_MINIMAL)
    compose = live_compose.generate_live_compose_dict(topo, publish_ingress=("web", 3000))
    web = compose["services"]["web"]
    assert web["networks"] == [live_compose.FLEET_NETWORK, live_compose.EDGE_NETWORK]
    assert web["ports"] == ["127.0.0.1:0:3000"]
    # non-ingress subject containers stay internal-only.
    assert compose["services"]["db"]["networks"] == [live_compose.FLEET_NETWORK]


def test_standup_warmup_drives_ingress_and_gates_on_terminal_success():
    from startd8.observability import warmup_traffic

    topo = live_compose.parse_subject_topology(_MINIMAL)
    runner = FakeRunner()  # port subcommand returns 127.0.0.1:49153 for both prom + ingress
    seen = {}

    def fake_warmup(spec, *, ingress_url=None, addr_map=None):
        seen["ingress_url"] = ingress_url
        seen["shape"] = spec.shape
        return warmup_traffic.WarmupOutcome(
            driver=spec.shape, exercised=True, terminal_success=True, iterations=1
        )

    handle = live_compose.stand_up_compose_subject(
        topology=topo,
        run_id="w1",
        warmup=warmup_traffic.WarmupSpec(shape="smoke"),
        warmup_count_metric=None,  # driver-only gate (sample check unit-tested separately)
        runner=runner,
        scrape_ready_check=lambda url, job, auth=None: True,
        series_count_check=lambda url, job, auth=None: 5.0,
        poll_interval=0.0,
        docker_available_fn=lambda: True,
        warmup_fn=fake_warmup,
    )
    assert handle.scrape_ready is True
    assert seen["ingress_url"] == "http://127.0.0.1:49153"
    assert handle.warmup["terminal_success"] is True
    # the compose published the metrics_service as an ingress.
    compose_yaml = (handle.workdir / "docker-compose.yml").read_text()
    assert "127.0.0.1:0:3000" in compose_yaml


def test_standup_warmup_driver_cannot_exercise_is_unknown():
    from startd8.observability import warmup_traffic

    topo = live_compose.parse_subject_topology(_MINIMAL)
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="w2",
        warmup=warmup_traffic.WarmupSpec(shape="smoke"),
        runner=FakeRunner(),
        scrape_ready_check=lambda url, job, auth=None: True,
        series_count_check=lambda url, job, auth=None: 5.0,
        poll_interval=0.0,
        docker_available_fn=lambda: True,
        warmup_fn=lambda spec, **kw: warmup_traffic.WarmupOutcome(
            driver="smoke", exercised=False, reason="driver 'smoke' could not exercise the subject"
        ),
    )
    assert handle.scrape_ready is False
    assert "could not exercise" in handle.reason


def test_standup_ob_grpc_warmup_is_deferred_unknown():
    from startd8.observability import warmup_traffic

    topo = live_compose.parse_subject_topology(_MINIMAL)
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="w3",
        warmup=warmup_traffic.WarmupSpec(shape="ob-grpc"),
        runner=FakeRunner(),
        docker_available_fn=lambda: True,
        warmup_fn=lambda spec, **kw: (_ for _ in ()).throw(AssertionError("grpc must not drive host-side")),
    )
    assert handle.scrape_ready is False
    assert "not host-drivable" in handle.reason


# ── Inc-2: span-metrics preset (collector-fronted) ──────────────────────────

_APP_TOPO = (
    "containers:\n"
    "  - {name: app, image: myapp:latest, port: 8080}\n"
    "metrics_service: app\n"
    "metrics_port: 8080\n"
)


def test_parse_rejects_collector_reserved_name():
    with pytest.raises(live_compose.TopologyError) as e:
        live_compose.parse_subject_topology(
            "containers:\n  - {name: collector, image: i, port: 1}\n"
            "metrics_service: collector\nmetrics_port: 1"
        )
    assert "reserved" in str(e.value)


def test_span_metrics_compose_adds_collector_and_repoints_prometheus():
    topo = live_compose.parse_subject_topology(_APP_TOPO)
    wiring = live_compose.SpanMetricsWiring(otlp_app="app")
    compose = live_compose.generate_live_compose_dict(topo, span_metrics=wiring)

    # collector container present, mounts the config at the contrib default path.
    coll = compose["services"][live_compose.COLLECTOR_SERVICE]
    assert coll["image"] == live_compose.COLLECTOR_IMAGE
    assert any(live_compose.COLLECTOR_CONFIG_MOUNT in v for v in coll["volumes"])

    # the app emits OTLP to the collector and starts after it.
    app = compose["services"]["app"]
    assert app["environment"]["OTEL_EXPORTER_OTLP_ENDPOINT"] == "http://collector:4317"
    assert app["environment"]["OTEL_TRACES_EXPORTER"] == "otlp"
    assert "collector" in app["depends_on"]

    # Prometheus scrapes the COLLECTOR, not the subject.
    assert compose["services"][live_compose.PROMETHEUS_SERVICE]["depends_on"] == [
        live_compose.COLLECTOR_SERVICE
    ]


def test_standup_span_metrics_scrapes_collector_and_writes_config():
    topo = live_compose.parse_subject_topology(_APP_TOPO)
    runner = FakeRunner()
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="sm1", span_metrics=True,
        runner=runner,
        scrape_ready_check=lambda url, job, auth=None: True,
        series_count_check=lambda url, job, auth=None: 3.0,
        poll_interval=0.0,
        docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is True
    assert handle.metrics_service == live_compose.COLLECTOR_SERVICE
    assert live_compose.COLLECTOR_SERVICE in handle.container_names

    # prometheus.yml targets the collector:8889, and the collector config was written.
    prom_yml = (handle.workdir / "prometheus.yml").read_text()
    assert "targets: ['collector:8889']" in prom_yml
    otelcol = (handle.workdir / "otelcol.yaml").read_text()
    assert "spanmetrics" in otelcol
    assert "0.0.0.0:4317" in otelcol and "0.0.0.0:8889" in otelcol


def test_standup_span_metrics_with_warmup_drives_app_serving_port():
    from startd8.observability import warmup_traffic

    topo = live_compose.parse_subject_topology(_APP_TOPO)
    seen = {}

    def fake_warmup(spec, *, ingress_url=None, addr_map=None):
        seen["ingress_url"] = ingress_url
        return warmup_traffic.WarmupOutcome(
            driver=spec.shape, exercised=True, terminal_success=True, iterations=1
        )

    # count_metric=None → driver-only gate (the non-zero-sample metric gate is unit-tested
    # directly in test_warmup_traffic against an injected query_fn).
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="sm2", span_metrics=True,
        warmup=warmup_traffic.WarmupSpec(shape="ob-http"),
        warmup_count_metric=None,
        runner=FakeRunner(),
        scrape_ready_check=lambda url, job, auth=None: True,
        series_count_check=lambda url, job, auth=None: 4.0,
        poll_interval=0.0,
        docker_available_fn=lambda: True,
        warmup_fn=fake_warmup,
    )
    # ob-http drove the app's own serving port (published as ingress), not /metrics.
    assert seen["ingress_url"] == "http://127.0.0.1:49153"
    assert handle.warmup["terminal_success"] is True
    assert handle.scrape_ready is True


def test_standup_span_metrics_unknown_otlp_app_is_fail_loud():
    topo = live_compose.parse_subject_topology(_APP_TOPO)
    handle = live_compose.stand_up_compose_subject(
        topology=topo, run_id="sm3", span_metrics=True, otlp_app="ghost",
        runner=FakeRunner(), docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is False
    assert "not a container" in handle.reason
