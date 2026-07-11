# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Doppler backend: download, metadata strip, token confinement, auth, retry (FR-3)."""

import pytest

from startd8.secrets import DopplerSecretsProvider
from startd8.secrets.protocol import SecretsBackendError
from tests.unit.secrets.conftest import FakeResponse


def test_download_strips_doppler_metadata_and_token(fake_httpx):
    fake_httpx.queue = [FakeResponse(200, {
        "ANTHROPIC_API_KEY": "sk-ant-xyz",
        "OPENAI_API_KEY": "sk-oai-xyz",
        "DOPPLER_PROJECT": "strtd8",
        "DOPPLER_CONFIG": "dev",
        "DOPPLER_ENVIRONMENT": "dev",
        "DOPPLER_TOKEN": "dp.st.should-not-surface",
    })]
    backend = DopplerSecretsProvider(token="dp.st.abc123def")
    secrets = backend.get_all_secrets()

    assert secrets == {"ANTHROPIC_API_KEY": "sk-ant-xyz", "OPENAI_API_KEY": "sk-oai-xyz"}
    # The bearer token must never appear in the hydratable map (R1-S2 / FR-15a).
    assert "DOPPLER_TOKEN" not in secrets
    assert "DOPPLER_PROJECT" not in secrets


def test_download_is_cached_single_fetch(fake_httpx):
    fake_httpx.queue = [FakeResponse(200, {"A": "1"})]  # only one response queued
    backend = DopplerSecretsProvider(token="dp.st.abc123def")
    first = backend.get_all_secrets()
    second = backend.get_all_secrets()  # must not pop a second response
    assert first == second == {"A": "1"}


def test_force_invalidates_cache_and_refetches(fake_httpx):
    # Rotation: force=True must bypass the cache and pull the new value (FR-ROT-3).
    fake_httpx.queue = [FakeResponse(200, {"A": "1"}), FakeResponse(200, {"A": "2"})]
    backend = DopplerSecretsProvider(token="dp.st.abc123def")
    assert backend.get_all_secrets() == {"A": "1"}
    assert backend.get_all_secrets() == {"A": "1"}          # cached
    assert backend.get_all_secrets(force=True) == {"A": "2"}  # refetched
    backend.invalidate()  # also exposed directly
    fake_httpx.queue = [FakeResponse(200, {"A": "3"})]
    assert backend.get_all_secrets() == {"A": "3"}


def test_auth_failure_is_not_retried(fake_httpx):
    fake_httpx.queue = [FakeResponse(401, {})]  # single 401, no retries consumed
    backend = DopplerSecretsProvider(token="dp.st.badtoken")
    with pytest.raises(SecretsBackendError) as ei:
        backend.get_all_secrets()
    assert "auth failed" in str(ei.value).lower()
    # token must be masked in the error, never full
    assert "dp.st.badtoken" not in str(ei.value)


def test_client_error_404_is_not_retried(fake_httpx):
    # A single 404 queued; if it retried it would IndexError popping an empty queue.
    fake_httpx.queue = [FakeResponse(404, {})]
    backend = DopplerSecretsProvider(token="dp.st.abc123def")
    with pytest.raises(SecretsBackendError) as ei:
        backend.get_all_secrets()
    assert "404" in str(ei.value)
    assert "project/config" in str(ei.value)


def test_network_error_retries_then_succeeds(fake_httpx):
    fake_httpx.queue = [RuntimeError("conn reset"), FakeResponse(200, {"A": "1"})]
    backend = DopplerSecretsProvider(token="dp.st.abc123def", timeout=0.01)
    # monkeypatch sleep to keep the test fast
    import startd8.secrets.doppler as dmod
    dmod.time.sleep = lambda *_: None
    assert backend.get_all_secrets() == {"A": "1"}


def test_network_error_exhausts_attempts(fake_httpx):
    fake_httpx.queue = [RuntimeError("x"), RuntimeError("y"), RuntimeError("z")]
    backend = DopplerSecretsProvider(token="dp.st.abc123def")
    import startd8.secrets.doppler as dmod
    dmod.time.sleep = lambda *_: None
    with pytest.raises(SecretsBackendError) as ei:
        backend.get_all_secrets()
    assert "after 3 attempts" in str(ei.value)


def test_otel_span_carries_no_secret_values(fake_httpx):
    """If OTel is installed, assert no attribute value equals a secret (FR-16)."""
    pytest.importorskip("opentelemetry")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    import startd8.secrets.doppler as dmod
    dmod._tracer = provider.get_tracer("test")

    fake_httpx.queue = [FakeResponse(200, {"ANTHROPIC_API_KEY": "sk-ant-secret-value"})]
    DopplerSecretsProvider(token="dp.st.abc123def").get_all_secrets()

    spans = exporter.get_finished_spans()
    assert spans, "expected a secrets.fetch span"
    for span in spans:
        for value in (span.attributes or {}).values():
            assert "sk-ant-secret-value" not in str(value)
            assert "dp.st.abc123def" not in str(value)
        # required keys present
        assert "secrets.backend" in (span.attributes or {})
        assert "secrets.key_count" in (span.attributes or {})
