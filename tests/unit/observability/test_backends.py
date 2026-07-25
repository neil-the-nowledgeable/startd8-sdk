# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Tests for the backend-pluggable render seam (container-o11y FR-13 / ADR-008)."""

import yaml

from startd8.observability.artifact_generator_generators import generate_service_monitor
from startd8.observability.artifact_generator_models import BusinessContext, ServiceHints
from startd8.observability.backends import (
    AgentAdapter,
    OperatorAdapter,
    RenderBackend,
    ScrapeIntent,
    get_adapter,
)


def _intent():
    return ScrapeIntent(name="cart", transport="grpc", namespace="shop", scrape_interval="15s")


def test_operator_adapter_emits_servicemonitor_crd_byte_shape():
    r = OperatorAdapter().render_scrape(_intent(), "# derivations: app=cart")
    assert r.output_path == "service-monitors/cart-servicemonitor.yaml"
    # header comment preserved, then a parseable ServiceMonitor CRD
    body = r.content.split("\n\n", 1)[1]
    doc = yaml.safe_load(body)
    assert doc["apiVersion"] == "monitoring.coreos.com/v1"
    assert doc["kind"] == "ServiceMonitor"
    assert doc["metadata"]["namespace"] == "shop"
    assert doc["spec"]["endpoints"][0] == {"port": "metrics", "path": "/metrics", "interval": "15s"}


def test_agent_adapter_emits_alloy_prometheus_scrape():
    r = AgentAdapter().render_scrape(_intent(), "# derivations: app=cart")
    assert r.output_path == "alloy/cart-scrape.alloy"
    assert 'prometheus.scrape "cart"' in r.content
    assert 'metrics_path    = "/metrics"' in r.content
    assert 'scrape_interval = "15s"' in r.content
    assert "forward_to" in r.content
    # Alloy uses // comments, never # (would be a syntax error)
    assert "\n#" not in r.content and not r.content.startswith("#")


def test_get_adapter_dispatch_defaults_to_operator():
    assert isinstance(get_adapter(), OperatorAdapter)
    assert isinstance(get_adapter(RenderBackend.OPERATOR), OperatorAdapter)
    assert isinstance(get_adapter(RenderBackend.AGENT), AgentAdapter)


def test_generate_service_monitor_operator_is_the_default_and_unchanged():
    svc = ServiceHints(service_id="cart", transport="grpc")
    biz = BusinessContext(project_id="shop")
    default = generate_service_monitor(svc, biz)
    explicit = generate_service_monitor(svc, biz, backend=RenderBackend.OPERATOR)
    # default == operator, and it's a ServiceMonitor
    assert default.content == explicit.content
    assert default.output_path.endswith("-servicemonitor.yaml")
    assert "kind: ServiceMonitor" in default.content


def test_generate_service_monitor_agent_backend_switches_to_alloy():
    svc = ServiceHints(service_id="cart", transport="grpc")
    biz = BusinessContext(project_id="shop")
    result = generate_service_monitor(svc, biz, backend=RenderBackend.AGENT)
    assert result.artifact_type == "service_monitor"       # same logical type
    assert result.output_path == "alloy/cart-scrape.alloy"  # different mechanism
    assert 'prometheus.scrape "cart"' in result.content
    assert "ServiceMonitor" not in result.content
    # provenance/derivations preserved across backends
    assert result.derivations == generate_service_monitor(svc, biz).derivations
