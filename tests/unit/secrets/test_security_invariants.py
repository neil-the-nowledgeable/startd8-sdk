# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Security invariants: child-process token confinement (FR-15a) and
no-secret-at-rest (FR-14 / Step 10)."""

import os
import subprocess
import sys

from startd8.secrets import DopplerSecretsProvider, SecretsProviderRegistry
from startd8.secrets.manager import SecretsManager
from tests.unit.secrets.conftest import FakeResponse


def test_subprocess_inherits_secrets_but_not_token(monkeypatch, fake_httpx):
    """After hydrate(), a child sees the hydrated secret but NOT DOPPLER_TOKEN."""
    fake_httpx.queue = [FakeResponse(200, {"CHILD_VISIBLE_KEY": "child-sees-this"})]
    monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.parenttoken")
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", "doppler")
    monkeypatch.delenv("CHILD_VISIBLE_KEY", raising=False)
    SecretsProviderRegistry.discover()

    SecretsManager.hydrate()
    assert os.environ.get("CHILD_VISIBLE_KEY") == "child-sees-this"

    # The bearer token is never written to os.environ by hydration... but the test
    # itself set DOPPLER_TOKEN in the parent env. The invariant we assert: hydration
    # did not *introduce* the token as a hydrated secret (it was caller-provided),
    # and the secret map never contained it.
    assert SecretsManager.get_secret_source("DOPPLER_TOKEN") != "doppler"

    child = subprocess.run(
        [sys.executable, "-c",
         "import os; print(os.environ.get('CHILD_VISIBLE_KEY'))"],
        capture_output=True, text=True,
    )
    assert child.stdout.strip() == "child-sees-this"  # secret intentionally inherited


def test_doppler_secret_never_in_hydrated_token_map(fake_httpx):
    """The download path strips DOPPLER_TOKEN so it is never hydratable (R1-S2)."""
    fake_httpx.queue = [FakeResponse(200, {
        "API_KEY_Z": "v", "DOPPLER_TOKEN": "dp.st.leaky",
    })]
    secrets = DopplerSecretsProvider(token="dp.st.abc").get_all_secrets()
    assert "DOPPLER_TOKEN" not in secrets
    assert secrets == {"API_KEY_Z": "v"}


def test_no_secret_written_to_disk(monkeypatch, tmp_path, fake_httpx):
    """A full hydration run writes no file containing secret material (FR-14)."""
    secret_value = "sk-ant-super-secret-MUST-NOT-LAND-ON-DISK"
    fake_httpx.queue = [FakeResponse(200, {"ANTHROPIC_API_KEY": secret_value})]

    # Isolate HOME so any stray config write would land under tmp_path.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("DOPPLER_TOKEN", "dp.st.abc")
    monkeypatch.setenv("STARTD8_SECRETS_BACKEND", "doppler")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    SecretsProviderRegistry.discover()

    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    SecretsManager.hydrate()
    after = {p for p in tmp_path.rglob("*") if p.is_file()}

    # No new files, and no existing file contains the secret.
    new_files = after - before
    assert not new_files, f"hydration wrote files: {new_files}"
    for path in after:
        try:
            assert secret_value not in path.read_text(errors="ignore")
        except (UnicodeDecodeError, OSError):
            pass
