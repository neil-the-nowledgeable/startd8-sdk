# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Secrets-backend registry — entry-point discovery mirroring ``ProviderRegistry``.

Backends register under the ``startd8.secrets`` entry-point group. Discovery falls
back to the built-in ``local`` + ``doppler`` backends if entry points are unavailable,
so the SDK works from a source checkout (FR-2).
"""

import sys
import threading
from typing import Dict, List, Optional

from ..logging_config import get_logger
from .protocol import SecretsProvider

logger = get_logger("startd8.secrets.registry")


class SecretsProviderRegistry:
    """Thread-safe registry of secrets backends (singleton-style class state)."""

    _lock: threading.Lock = threading.Lock()
    _backends: Dict[str, SecretsProvider] = {}
    _discovered: bool = False

    @classmethod
    def register(cls, backend: SecretsProvider) -> None:
        required = ("name", "get_all_secrets", "get_secret", "validate_config",
                    "get_required_env_vars")
        if not all(hasattr(backend, attr) for attr in required):
            raise TypeError(
                f"{backend} does not implement SecretsProvider protocol. "
                f"Required: {', '.join(required)}"
            )
        name = backend.name.lower()
        with cls._lock:
            if name in cls._backends:
                logger.warning("Overwriting existing secrets backend: %s", name)
            cls._backends[name] = backend
            logger.debug("Registered secrets backend: %s", name)

    @classmethod
    def discover(cls, force: bool = False) -> None:
        """Auto-discover backends via the ``startd8.secrets`` entry-point group."""
        with cls._lock:
            if cls._discovered and not force:
                return

        discovered = 0
        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                try:
                    eps = entry_points(group="startd8.secrets")
                except TypeError:  # pragma: no cover - older interface
                    eps = entry_points().get("startd8.secrets", [])
            else:  # pragma: no cover - 3.9 fallback
                try:
                    from importlib_metadata import entry_points
                    eps = entry_points().get("startd8.secrets", [])
                except ImportError:
                    eps = []

            for ep in eps:
                try:
                    backend_class = ep.load()
                    cls.register(backend_class())
                    discovered += 1
                except Exception as e:
                    logger.warning("Failed to load secrets backend %s: %s", ep.name, e)
        except Exception as e:  # pragma: no cover - discovery best-effort
            logger.debug("Secrets entry-point discovery failed: %s", e)

        cls._register_builtin()

        with cls._lock:
            cls._discovered = True
        logger.debug("Secrets discovery complete (%d external, %d total)",
                     discovered, len(cls._backends))

    @classmethod
    def _register_builtin(cls) -> None:
        """Register built-in backends, never overwriting entry-point ones."""
        from .local import LocalSecretsProvider
        from .doppler import DopplerSecretsProvider
        for backend_cls in (LocalSecretsProvider, DopplerSecretsProvider):
            try:
                inst = backend_cls()
                if inst.name.lower() not in cls._backends:
                    cls.register(inst)
            except Exception as e:  # pragma: no cover
                logger.debug("Built-in secrets backend %s skipped: %s", backend_cls, e)

    @classmethod
    def get_backend(cls, name: str) -> Optional[SecretsProvider]:
        cls.discover()
        return cls._backends.get(name.lower())

    @classmethod
    def list_backends(cls) -> List[str]:
        cls.discover()
        return sorted(cls._backends.keys())

    @classmethod
    def _reset_for_tests(cls) -> None:
        """Test helper — clear discovery state."""
        with cls._lock:
            cls._backends = {}
            cls._discovered = False
