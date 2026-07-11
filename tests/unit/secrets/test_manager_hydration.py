# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""SecretsManager hydration matrix: precedence, deny-list, allowlist, fail modes,
source attribution, and thread-safety (FR-4, FR-4a, FR-4b, FR-5a, FR-6a, FR-13)."""

import threading

import pytest

from startd8.exceptions import ConfigurationError
from startd8.secrets import SecretsProviderRegistry, is_dangerous_key
from startd8.secrets.manager import SecretsManager
from startd8.secrets.protocol import SecretsBackendError


class FakeBackend:
    """Configurable backend registered under an arbitrary name."""

    def __init__(self, name, secrets=None, raises=None):
        self._name = name
        self._secrets = secrets or {}
        self._raises = raises
        self.fetch_count = 0

    @property
    def name(self):
        return self._name

    def get_all_secrets(self):
        self.fetch_count += 1
        if self._raises:
            raise self._raises
        return dict(self._secrets)

    def get_secret(self, key):
        return self._secrets.get(key)

    def validate_config(self):
        return True

    def get_required_env_vars(self):
        return []


def _use_backend(monkeypatch, backend):
    SecretsProviderRegistry.register(backend)
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", backend.name)
    return backend


# --------------------------------------------------------------------------- #
def test_local_backend_is_noop(monkeypatch):
    result = SecretsManager.hydrate()
    assert result.backend == "local"
    assert result.outcome == "noop"
    assert result.hydrated_keys == []


def test_hydrates_absent_keys(monkeypatch):
    _use_backend(monkeypatch, FakeBackend("be1", {"NEW_KEY_X": "v1"}))
    monkeypatch.delenv("NEW_KEY_X", raising=False)
    result = SecretsManager.hydrate()
    import os
    assert os.environ.get("NEW_KEY_X") == "v1"
    assert "NEW_KEY_X" in result.hydrated_keys
    assert SecretsManager.get_secret_source("NEW_KEY_X") == "be1"


def test_existing_env_always_wins(monkeypatch):
    monkeypatch.setenv("PINNED_KEY", "from-env")
    _use_backend(monkeypatch, FakeBackend("be2", {"PINNED_KEY": "from-doppler"}))
    SecretsManager.hydrate()
    import os
    assert os.environ["PINNED_KEY"] == "from-env"  # not overwritten
    assert SecretsManager.get_secret_source("PINNED_KEY") == "env"


def test_dangerous_keys_are_denied(monkeypatch):
    _use_backend(monkeypatch, FakeBackend("be3", {
        "LD_PRELOAD": "/tmp/evil.so",
        "PATH": "/evil/bin",
        "PYTHONPATH": "/evil",
        "SAFE_KEY_Y": "ok",
    }))
    for k in ("LD_PRELOAD", "PATH", "PYTHONPATH", "SAFE_KEY_Y"):
        monkeypatch.delenv(k, raising=False)
    result = SecretsManager.hydrate()
    import os
    assert "LD_PRELOAD" not in result.hydrated_keys
    assert os.environ.get("LD_PRELOAD") is None  # never injected
    assert set(result.skipped_dangerous) >= {"LD_PRELOAD", "PATH", "PYTHONPATH"}
    assert os.environ.get("SAFE_KEY_Y") == "ok"


def test_is_dangerous_key_helper():
    assert is_dangerous_key("PATH")
    assert is_dangerous_key("LD_LIBRARY_PATH")
    assert is_dangerous_key("DYLD_INSERT_LIBRARIES")
    assert not is_dangerous_key("ANTHROPIC_API_KEY")


def test_allowlist_absent_injects_all(monkeypatch):
    _use_backend(monkeypatch, FakeBackend("be4", {"AAA": "1", "BBB": "2"}))
    for k in ("AAA", "BBB"):
        monkeypatch.delenv(k, raising=False)
    SecretsManager.hydrate()
    import os
    assert os.environ.get("AAA") == "1"
    assert os.environ.get("BBB") == "2"


def test_allowlist_empty_injects_none(monkeypatch):
    _use_backend(monkeypatch, FakeBackend("be5", {"AAA": "1", "BBB": "2"}))
    monkeypatch.setenv("STARTD8_SECRETS_ALLOWLIST", "")  # empty => inject none
    for k in ("AAA", "BBB"):
        monkeypatch.delenv(k, raising=False)
    result = SecretsManager.hydrate()
    import os
    assert os.environ.get("AAA") is None
    assert os.environ.get("BBB") is None
    assert result.hydrated_keys == []


def test_allowlist_named_injects_subset(monkeypatch):
    _use_backend(monkeypatch, FakeBackend("be6", {"AAA": "1", "BBB": "2", "CCC": "3"}))
    monkeypatch.setenv("STARTD8_SECRETS_ALLOWLIST", "AAA,CCC")
    for k in ("AAA", "BBB", "CCC"):
        monkeypatch.delenv(k, raising=False)
    SecretsManager.hydrate()
    import os
    assert os.environ.get("AAA") == "1"
    assert os.environ.get("BBB") is None  # excluded
    assert os.environ.get("CCC") == "3"


def test_fail_open_continues_with_masked_failure(monkeypatch):
    _use_backend(monkeypatch, FakeBackend(
        "be7", raises=SecretsBackendError("Doppler auth failed for dp.st.secrettoken123")))
    result = SecretsManager.hydrate()
    assert result.outcome == "fail_open"
    assert result.fetch_failure is not None
    assert "dp.st.secrettoken123" not in result.fetch_failure  # masked
    # downstream missing-key error references the earlier failure (bounded)
    note = SecretsManager.annotate_missing_key("ANTHROPIC_API_KEY")
    assert "ANTHROPIC_API_KEY not set" in note
    assert "failed earlier" in note


def test_fail_closed_raises(monkeypatch):
    _use_backend(monkeypatch, FakeBackend("be8", raises=SecretsBackendError("boom")))
    monkeypatch.setenv("STARTD8_SECRETS_FAIL_CLOSED", "true")
    with pytest.raises(ConfigurationError):
        SecretsManager.hydrate()


def test_hydration_is_idempotent(monkeypatch):
    backend = _use_backend(monkeypatch, FakeBackend("be9", {"ZZZ": "1"}))
    monkeypatch.delenv("ZZZ", raising=False)
    SecretsManager.hydrate()
    SecretsManager.hydrate()
    SecretsManager.hydrate()
    assert backend.fetch_count == 1  # exactly one fetch despite 3 calls


def test_hydration_thread_safe_single_fetch(monkeypatch):
    backend = _use_backend(monkeypatch, FakeBackend("be10", {"TKEY": "1"}))
    monkeypatch.delenv("TKEY", raising=False)
    barrier = threading.Barrier(8)

    def worker():
        barrier.wait()
        SecretsManager.hydrate()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert backend.fetch_count == 1  # exactly one fetch under concurrency (FR-6a)


def test_get_secret_source_none_for_unknown(monkeypatch):
    SecretsManager.hydrate()
    assert SecretsManager.get_secret_source("DEFINITELY_NOT_SET_KEY") is None
