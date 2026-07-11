# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""
Secrets-provider protocol — the interface a managed secrets backend implements.

Mirrors the ``AgentProvider`` protocol (``providers/protocol.py``): a backend is a
named, discoverable plugin that knows how to surface secrets. Backends are read-only
consumers (NR-1) — they fetch, they never write to the managed store.

See ``docs/design/doppler-secrets/`` for the requirements/plan this implements.
"""

from typing import Protocol, runtime_checkable, Dict, List, Optional

from ..exceptions import Startd8Error


class SecretsBackendError(Startd8Error):
    """A secrets backend could not fetch its secrets (network/auth/parse).

    Raised by ``get_all_secrets()`` implementations. The ``SecretsManager`` decides
    whether this is fail-open (log masked warning, continue) or fail-closed
    (re-raise as ``ConfigurationError``) per FR-13.
    """

    def __init__(self, message: str, *, backend: Optional[str] = None,
                 original_error: Optional[Exception] = None):
        super().__init__(message)
        self.backend = backend
        self.original_error = original_error


@runtime_checkable
class SecretsProvider(Protocol):
    """Interface for a secrets backend (e.g. ``local``, ``doppler``).

    Example implementation::

        class MyBackend:
            @property
            def name(self) -> str:
                return "my-backend"

            def get_all_secrets(self) -> Dict[str, str]:
                return {"ANTHROPIC_API_KEY": "sk-ant-..."}

            def get_secret(self, key: str) -> Optional[str]:
                return self.get_all_secrets().get(key)

            def validate_config(self) -> bool:
                return True

            def get_required_env_vars(self) -> List[str]:
                return ["MY_BACKEND_TOKEN"]
    """

    @property
    def name(self) -> str:
        """Unique, lowercase backend identifier (e.g. ``'doppler'``)."""
        ...

    def get_all_secrets(self, force: bool = False) -> Dict[str, str]:
        """Return the full secret map this backend exposes.

        Args:
            force: bypass any in-process cache and re-fetch (rotation — FR-ROT-3).
                Backends without a cache may ignore it.

        Returns:
            Mapping of secret name -> value. May be empty (the ``local`` backend
            returns ``{}`` because env/config already cover it — FR-5a).

        Raises:
            SecretsBackendError: on fetch/auth/parse failure (FR-13).
        """
        ...

    def get_secret(self, key: str) -> Optional[str]:
        """Return a single secret value, or ``None`` if absent."""
        ...

    def validate_config(self) -> bool:
        """Validate the backend is configured well enough to fetch.

        Returns:
            True if valid.

        Raises:
            ConfigurationError: if misconfigured (with an actionable message).
        """
        ...

    def get_required_env_vars(self) -> List[str]:
        """Environment variables this backend needs (for docs/diagnostics)."""
        ...
