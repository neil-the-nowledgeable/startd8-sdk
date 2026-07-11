# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Backend protocol conformance + registry discovery (FR-1, FR-2, FR-3)."""

import pytest

from startd8.secrets import (
    DopplerSecretsProvider,
    LocalSecretsProvider,
    SecretsProvider,
    SecretsProviderRegistry,
)
from startd8.secrets.protocol import SecretsBackendError


def test_builtin_backends_discovered():
    names = SecretsProviderRegistry.list_backends()
    assert "local" in names
    assert "doppler" in names


def test_local_and_doppler_satisfy_protocol():
    assert isinstance(LocalSecretsProvider(), SecretsProvider)
    assert isinstance(DopplerSecretsProvider(token="dp.st.xxx"), SecretsProvider)


def test_local_backend_hydrates_nothing():
    backend = LocalSecretsProvider()
    assert backend.name == "local"
    assert backend.get_all_secrets() == {}
    assert backend.validate_config() is True
    assert backend.get_required_env_vars() == []


def test_local_get_secret_reads_environment(monkeypatch):
    monkeypatch.setenv("SOME_KEY", "v1")
    assert LocalSecretsProvider().get_secret("SOME_KEY") == "v1"
    assert LocalSecretsProvider().get_secret("MISSING_KEY") is None


def test_doppler_requires_token():
    backend = DopplerSecretsProvider(token=None)
    with pytest.raises(Exception):  # ConfigurationError
        backend.validate_config()


def test_registry_rejects_non_conforming_backend():
    class Bad:
        name = "bad"

    with pytest.raises(TypeError):
        SecretsProviderRegistry.register(Bad())


def test_registry_get_unknown_backend_returns_none():
    assert SecretsProviderRegistry.get_backend("nope") is None


def test_backend_error_carries_backend_name():
    err = SecretsBackendError("boom", backend="doppler")
    assert err.backend == "doppler"
