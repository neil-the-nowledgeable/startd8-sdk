# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Docker-gated end-to-end proof of the Tier-B standup + scrape gate + teardown.

Self-contained: the subject IS ``prom/prometheus`` (it exposes ``/metrics`` on
9090), so a second Prometheus scrapes it and the scrape-ready gate resolves with
no bespoke image. Skipped unless ``STARTD8_RUN_INTEGRATION=1`` AND docker is on
PATH — the same gate the fleet-compose integration test uses.

    STARTD8_RUN_INTEGRATION=1 pytest -m integration tests/integration/test_compare_live_standup.py
"""

from __future__ import annotations

import os
import subprocess

import pytest

from startd8.benchmark_matrix.fleet.containerize import docker_available
from startd8.observability import live_standup

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("STARTD8_RUN_INTEGRATION") != "1",
        reason="set STARTD8_RUN_INTEGRATION=1 to run docker integration tests",
    ),
    pytest.mark.skipif(not docker_available(), reason="docker CLI not on PATH"),
]


def _container_gone(name: str) -> bool:
    r = subprocess.run(["docker", "ps", "-a", "-q", "-f", f"name={name}"],
                       capture_output=True, text=True, check=False)
    return not (r.stdout or "").strip()


def test_real_standup_scrape_lands_and_teardown_is_clean():
    handle = None
    try:
        handle = live_standup.stand_up_subject_and_prometheus(
            subject_image=live_standup.PROMETHEUS_IMAGE,  # prometheus scrapes ITSELF as subject
            subject_port=9090,
            job_name="subject",
            scrape_timeout=90.0,
        )
        assert handle.scrape_ready, handle.reason
        assert handle.prometheus_url.startswith("http://127.0.0.1:")
    finally:
        if handle is not None:
            live_standup.tear_down(handle)

    # both containers and the network are gone
    assert _container_gone(handle.subject_container)
    assert _container_gone(handle.prometheus_container)
