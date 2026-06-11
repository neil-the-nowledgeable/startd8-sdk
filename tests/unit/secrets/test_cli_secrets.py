# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""CLI: `startd8 secrets status|test|list` (FR-10, FR-11, R1-S8)."""

from typer.testing import CliRunner

from startd8.cli_secrets import secrets_app
from startd8.secrets import SecretsProviderRegistry
from tests.unit.secrets.conftest import FakeResponse

runner = CliRunner()


def test_status_local_backend():
    result = runner.invoke(secrets_app, ["status"])
    assert result.exit_code == 0
    assert "local" in result.stdout


def test_test_local_is_noop_success():
    result = runner.invoke(secrets_app, ["test"])
    assert result.exit_code == 0
    assert "local" in result.stdout


def test_list_local_explains_no_remote():
    result = runner.invoke(secrets_app, ["list"])
    assert result.exit_code == 0
    assert "no remote" in result.stdout.lower() or "directly" in result.stdout.lower()


def test_test_doppler_success(monkeypatch, fake_httpx):
    fake_httpx.queue = [FakeResponse(200, {"ANTHROPIC_API_KEY": "sk-ant-xyz"})]
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", "doppler")
    monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.abc123")
    SecretsProviderRegistry.discover()
    result = runner.invoke(secrets_app, ["test"])
    assert result.exit_code == 0
    assert "reachable" in result.stdout


def test_test_doppler_auth_failure_nonzero(monkeypatch, fake_httpx):
    fake_httpx.queue = [FakeResponse(401, {})]
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", "doppler")
    monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.bad")
    SecretsProviderRegistry.discover()
    result = runner.invoke(secrets_app, ["test"])
    assert result.exit_code == 1


def test_refresh_local_is_noop():
    result = runner.invoke(secrets_app, ["refresh"])
    assert result.exit_code == 0
    assert "nothing to refresh" in result.stdout.lower()


def test_refresh_doppler_rotates_key(monkeypatch, fake_httpx):
    fake_httpx.queue = [
        FakeResponse(200, {"ANTHROPIC_API_KEY": "v1"}),
        FakeResponse(200, {"ANTHROPIC_API_KEY": "v2"}),
    ]
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", "doppler")
    monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.abc123")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    SecretsProviderRegistry.discover()

    runner.invoke(secrets_app, ["status"])          # hydrate v1
    result = runner.invoke(secrets_app, ["refresh"])  # force re-fetch -> v2
    assert result.exit_code == 0
    assert "rotated" in result.stdout.lower()
    assert "ANTHROPIC_API_KEY" in result.stdout


def test_list_doppler_masks_values(monkeypatch, fake_httpx):
    fake_httpx.queue = [FakeResponse(200, {"ANTHROPIC_API_KEY": "sk-ant-abcdef123456"})]
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", "doppler")
    monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.abc123")
    SecretsProviderRegistry.discover()
    result = runner.invoke(secrets_app, ["list"])
    assert result.exit_code == 0
    assert "ANTHROPIC_API_KEY" in result.stdout
    assert "sk-ant-abcdef123456" not in result.stdout  # masked
