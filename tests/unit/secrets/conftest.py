# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Shared fixtures for secrets-backend tests."""

import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_secrets_state():
    """Reset manager/registry singletons and restore os.environ around each test."""
    from startd8.secrets.manager import SecretsManager
    from startd8.secrets.registry import SecretsProviderRegistry

    saved_env = dict(os.environ)
    SecretsManager._reset_for_tests()
    SecretsProviderRegistry._reset_for_tests()

    # Drop any secrets-related env that could leak in from the host shell.
    for var in ("STARTD8_SECRETS_BACKEND", "STARTD8_SECRETS_FAIL_CLOSED",
                "STARTD8_SECRETS_ALLOWLIST", "DOPPLER_TOKEN"):
        os.environ.pop(var, None)

    yield

    SecretsManager._reset_for_tests()
    SecretsProviderRegistry._reset_for_tests()
    os.environ.clear()
    os.environ.update(saved_env)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data if json_data is not None else {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    """Drop-in for httpx.Client driven by a queue of responses/exceptions."""

    queue = []  # class-level: list of FakeResponse or Exception

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get(self, *a, **k):
        item = FakeClient.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake_httpx(monkeypatch):
    """Patch httpx.Client and reset the response queue."""
    import httpx
    FakeClient.queue = []
    monkeypatch.setattr(httpx, "Client", FakeClient)
    return FakeClient
