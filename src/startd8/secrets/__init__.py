# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Pluggable secrets-management backends for the startd8 SDK.

The default ``local`` backend preserves today's behavior exactly (env var →
``~/.startd8/config.json``). An optional ``doppler`` backend sources secrets from
Doppler (https://www.doppler.com/) and **hydrates** them into ``os.environ`` at
startup, so every provider's existing ``os.getenv(...)`` call sees them with zero
provider changes.

Public API::

    from startd8.secrets import hydrate, get_secret, get_secret_source

    hydrate()                       # idempotent; safe to call from anywhere at startup
    key = get_secret("ANTHROPIC_API_KEY")
    src = get_secret_source("ANTHROPIC_API_KEY")   # 'doppler' | 'env' | None

Precedence is preserved end-to-end: explicit ``config['api_key']`` > env var (possibly
Doppler-populated) > local config file. Doppler is **off by default** — no network call
happens unless ``STARTD8_SECRETS_BACKEND=doppler`` (or the equivalent SDK config) is set.

Design docs: ``docs/design/doppler-secrets/``.
"""

from typing import Optional

from .protocol import SecretsProvider, SecretsBackendError
from .registry import SecretsProviderRegistry
from .manager import (
    SecretsManager,
    HydrationResult,
    is_dangerous_key,
)
from .local import LocalSecretsProvider
from .doppler import DopplerSecretsProvider

__all__ = [
    "SecretsProvider",
    "SecretsBackendError",
    "SecretsProviderRegistry",
    "SecretsManager",
    "HydrationResult",
    "is_dangerous_key",
    "LocalSecretsProvider",
    "DopplerSecretsProvider",
    "hydrate",
    "get_secret",
    "get_secret_source",
]


def hydrate(force: bool = False) -> HydrationResult:
    """Hydrate the environment from the active secrets backend (idempotent).

    Library users who construct providers directly should call this once at startup
    (the CLI and ``AgentFramework`` already do — FR-17).
    """
    return SecretsManager.hydrate(force=force)


def get_secret(name: str) -> Optional[str]:
    """Resolve a secret from the (possibly hydrated) environment."""
    return SecretsManager.get_secret(name)


def get_secret_source(name: str) -> Optional[str]:
    """Report where ``name`` resolves from: ``'doppler'`` | ``'env'`` | ``None``."""
    return SecretsManager.get_secret_source(name)
