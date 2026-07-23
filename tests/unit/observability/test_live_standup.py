# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Unit tests for the Tier-B standup substrate — no docker, all seams injected."""

from __future__ import annotations

import subprocess

import pytest

from startd8.observability import live_standup


# ── render_prometheus_yml (pure) ────────────────────────────────────────────

def test_render_prometheus_yml_targets_subject_by_dns():
    yml = live_standup.render_prometheus_yml(
        job_name="subject", target_host="cmp-subject-abc123", target_port=9464,
    )
    assert "job_name: subject" in yml
    assert "targets: ['cmp-subject-abc123:9464']" in yml
    assert "metrics_path: /metrics" in yml
    assert "scrape_interval: 5s" in yml


def test_render_prometheus_yml_custom_path_and_interval():
    yml = live_standup.render_prometheus_yml(
        job_name="j", target_host="h", target_port=1, metrics_path="/actuator/prometheus",
        scrape_interval="2s",
    )
    assert "metrics_path: /actuator/prometheus" in yml
    assert "scrape_interval: 2s" in yml


# ── a fake docker runner ────────────────────────────────────────────────────

class FakeRunner:
    """Records argv and returns canned results keyed by the docker subcommand."""

    def __init__(self, *, port_stdout="127.0.0.1:49153", fail_on=None):
        self.calls = []
        self.port_stdout = port_stdout
        self.fail_on = fail_on or ()  # e.g. ("network",) to fail `docker network create`

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        sub = argv[1] if len(argv) > 1 else ""
        if sub in self.fail_on:
            return subprocess.CompletedProcess(argv, 1, "", "boom")
        stdout = self.port_stdout if sub == "port" else "deadbeef\n"
        return subprocess.CompletedProcess(argv, 0, stdout, "")


def _flat(calls):
    return [" ".join(c) for c in calls]


def test_standup_builds_networked_argv_and_gates_on_scrape():
    runner = FakeRunner()
    handle = live_standup.stand_up_subject_and_prometheus(
        subject_image="mysubject:latest",
        subject_port=9464,
        run_id="abc123",
        runner=runner,
        scrape_ready_check=lambda url, job, auth=None: True,
        docker_available_fn=lambda: True,
    )

    assert handle.scrape_ready is True
    assert handle.reason == ""
    assert handle.prometheus_url == "http://127.0.0.1:49153"

    flat = _flat(runner.calls)
    # network created with the per-run id
    assert any("network create startd8-cmp-abc123" in c for c in flat)
    # subject joins the shared network by name
    assert any(
        "run -d --network startd8-cmp-abc123 --name cmp-subject-abc123 mysubject:latest" in c
        for c in flat
    )
    # prometheus mounts the generated config and publishes 9090 on loopback
    prom = next(c for c in flat if live_standup.PROMETHEUS_IMAGE in c)
    assert "--network startd8-cmp-abc123" in prom
    assert "-p 127.0.0.1:0:9090" in prom
    assert ":/etc/prometheus/prometheus.yml:ro" in prom


def test_standup_scrape_timeout_is_not_a_fail():
    runner = FakeRunner()
    handle = live_standup.stand_up_subject_and_prometheus(
        subject_image="s:1", run_id="t1", runner=runner,
        scrape_ready_check=lambda url, job, auth=None: False,  # never ready
        docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is False
    assert "no scrape landed" in handle.reason
    # still resolved a URL and both containers exist → teardown has names
    assert handle.subject_container and handle.prometheus_container


def test_standup_no_docker_is_fail_loud():
    handle = live_standup.stand_up_subject_and_prometheus(
        subject_image="s:1", run_id="nd", runner=FakeRunner(),
        docker_available_fn=lambda: False,
    )
    assert handle.scrape_ready is False
    assert "docker" in handle.reason.lower()


def test_standup_network_create_failure_returns_handle_with_reason():
    runner = FakeRunner(fail_on=("network",))
    handle = live_standup.stand_up_subject_and_prometheus(
        subject_image="s:1", run_id="nf", runner=runner,
        docker_available_fn=lambda: True,
    )
    assert handle.scrape_ready is False
    assert "network create failed" in handle.reason


def test_await_scrape_returns_true_once_ready():
    calls = {"n": 0}

    def ready(url, job, auth=None):
        calls["n"] += 1
        return calls["n"] >= 2

    assert live_standup._await_scrape("http://x", "j", timeout=5.0, interval=0.0, ready_fn=ready)


def test_await_scrape_times_out_when_never_ready():
    assert not live_standup._await_scrape(
        "http://x", "j", timeout=0.05, interval=0.01, ready_fn=lambda u, j, auth=None: False,
    )


def test_await_scrape_swallows_backend_errors_and_keeps_polling():
    def raising(url, job, auth=None):
        raise ConnectionError("prom not up")

    # must not propagate — returns False on timeout
    assert not live_standup._await_scrape(
        "http://x", "j", timeout=0.05, interval=0.01, ready_fn=raising)


def test_parse_published_port():
    assert live_standup._parse_published_port("127.0.0.1:49153") == 49153
    assert live_standup._parse_published_port("0.0.0.0:8080\n[::]:8080") == 8080
    assert live_standup._parse_published_port("") is None


def test_teardown_removes_both_containers_and_network_best_effort():
    runner = FakeRunner()
    handle = live_standup.StandupHandle(
        prometheus_url="http://127.0.0.1:1", job_name="subject",
        network="startd8-cmp-x", subject_container="cmp-subject-x",
        prometheus_container="cmp-prom-x",
    )
    live_standup.tear_down(handle, runner=runner)
    flat = _flat(runner.calls)
    assert any("rm -f cmp-subject-x" in c for c in flat)
    assert any("rm -f cmp-prom-x" in c for c in flat)
    assert any("network rm startd8-cmp-x" in c for c in flat)


def test_teardown_never_raises_on_runner_error():
    def boom(*a, **k):
        raise RuntimeError("docker gone")

    handle = live_standup.StandupHandle(
        prometheus_url="", job_name="s", network="n",
        subject_container="c1", prometheus_container="c2",
    )
    live_standup.tear_down(handle, runner=boom)  # must not raise
