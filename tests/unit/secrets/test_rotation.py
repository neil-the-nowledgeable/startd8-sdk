# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Runtime rotation (FR-ROT-1..6): refresh overwrites SDK-owned keys only,
preserves user env, lazy TTL, and fail-open-preserving refresh."""

import os
import time

from startd8.secrets import SecretsProviderRegistry
from startd8.secrets.manager import SecretsManager
from startd8.secrets.protocol import SecretsBackendError


class RotatingBackend:
    """Fake backend whose values can change between fetches."""

    def __init__(self, name, secrets):
        self._name = name
        self._secrets = dict(secrets)
        self.fetch_count = 0
        self.raises = False

    @property
    def name(self):
        return self._name

    def get_all_secrets(self, force=False):
        self.fetch_count += 1
        if self.raises:
            raise SecretsBackendError("rotation fetch failed for dp.st.sometoken")
        return dict(self._secrets)

    def get_secret(self, key):
        return self._secrets.get(key)

    def validate_config(self):
        return True

    def get_required_env_vars(self):
        return []

    def rotate(self, key, value):
        self._secrets[key] = value


def _use(monkeypatch, backend):
    SecretsProviderRegistry.register(backend)
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", backend.name)
    return backend


def test_refresh_overwrites_sdk_owned_key(monkeypatch):
    b = _use(monkeypatch, RotatingBackend("rot1", {"ROT_KEY": "v1"}))
    monkeypatch.delenv("ROT_KEY", raising=False)
    SecretsManager.hydrate()
    assert os.environ["ROT_KEY"] == "v1"

    b.rotate("ROT_KEY", "v2")
    r = SecretsManager.refresh()
    assert os.environ["ROT_KEY"] == "v2"           # rotated in place (FR-ROT-2)
    assert "ROT_KEY" in r.hydrated_keys             # reported as changed
    assert SecretsManager.get_secret_source("ROT_KEY") == "rot1"


def test_refresh_never_overwrites_user_env(monkeypatch):
    b = _use(monkeypatch, RotatingBackend("rot2", {"USER_KEY": "doppler-v1"}))
    monkeypatch.setenv("USER_KEY", "user-set-value")  # user owns it
    SecretsManager.hydrate()
    assert os.environ["USER_KEY"] == "user-set-value"

    b.rotate("USER_KEY", "doppler-v2")
    r = SecretsManager.refresh()
    assert os.environ["USER_KEY"] == "user-set-value"  # untouched (FR-ROT-2)
    assert "USER_KEY" not in r.hydrated_keys


def test_refresh_local_is_noop(monkeypatch):
    r = SecretsManager.refresh()
    assert r.backend == "local"
    assert r.hydrated_keys == []


def test_refresh_unchanged_key_reports_no_change(monkeypatch):
    _use(monkeypatch, RotatingBackend("rot3", {"STABLE": "same"}))
    monkeypatch.delenv("STABLE", raising=False)
    SecretsManager.hydrate()
    r = SecretsManager.refresh()  # value unchanged
    assert os.environ["STABLE"] == "same"
    assert r.hydrated_keys == []  # nothing rotated


def test_lazy_ttl_refresh_on_access(monkeypatch):
    b = _use(monkeypatch, RotatingBackend("rot4", {"TTL_KEY": "v1"}))
    monkeypatch.setenv("STARTD8_SECRETS_TTL", "100")
    monkeypatch.delenv("TTL_KEY", raising=False)
    SecretsManager.hydrate()
    assert b.fetch_count == 1

    b.rotate("TTL_KEY", "v2")
    # Not expired yet → no refetch, still v1.
    assert SecretsManager.get_secret("TTL_KEY") == "v1"
    assert b.fetch_count == 1

    # Force expiry by backdating the hydration time, then access → lazy refresh.
    SecretsManager._hydrated_at = time.monotonic() - 200
    assert SecretsManager.get_secret("TTL_KEY") == "v2"
    assert b.fetch_count == 2


def test_no_ttl_means_fetch_once(monkeypatch):
    b = _use(monkeypatch, RotatingBackend("rot5", {"K": "v1"}))
    monkeypatch.delenv("K", raising=False)
    SecretsManager.hydrate()
    # No TTL configured → repeated get_secret never refetches.
    for _ in range(3):
        SecretsManager.get_secret("K")
    assert b.fetch_count == 1


def test_refresh_failure_preserves_env(monkeypatch):
    b = _use(monkeypatch, RotatingBackend("rot6", {"PK": "v1"}))
    monkeypatch.delenv("PK", raising=False)
    SecretsManager.hydrate()
    assert os.environ["PK"] == "v1"

    b.raises = True  # next fetch fails
    r = SecretsManager.refresh()
    assert r.outcome == "fail_open"
    assert os.environ["PK"] == "v1"          # preserved — never left worse off (FR-ROT-5)
    assert r.fetch_failure is not None
    assert "dp.st.sometoken" not in r.fetch_failure  # masked


def test_refresh_failure_fail_closed_raises(monkeypatch):
    from startd8.exceptions import ConfigurationError
    import pytest

    b = _use(monkeypatch, RotatingBackend("rot7", {"PK": "v1"}))
    monkeypatch.delenv("PK", raising=False)
    SecretsManager.hydrate()
    b.raises = True
    monkeypatch.setenv("STARTD8_SECRETS_FAIL_CLOSED", "true")
    with pytest.raises(ConfigurationError):
        SecretsManager.refresh()
