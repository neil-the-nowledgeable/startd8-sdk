# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Persona-format adapter registry (FR-4) — mirrors ``providers/registry.py``'s entry-point idiom.

A downstream project registers its own adapter under the entry-point group
``startd8.stakeholder_panel.roster_adapters`` (``name = "pkg.module:AdapterClass"``); ``discover()``
loads them. Trust posture (R1-S2):

* **Failure isolation** — a broken/raising entry point is skipped-and-warned, never aborting
  discovery of the others.
* **Built-in wins** a name collision (an entry point named like a built-in is ignored).
* An entry-point adapter **runs arbitrary third-party code** at load/adapt time — the caller naming
  the ``--format`` (NR-4) is the only trust gate.

The built-in ``role-rubric`` is a **lazy** built-in (imported only on ``get_adapter("role-rubric")``,
R2-F4) and is registered here rather than solely via entry point so it resolves in an editable /
multi-worktree checkout without a reinstall.
"""

from __future__ import annotations

import importlib
import sys
import threading
from typing import Dict, List

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.adapters.base import Adapter, AdapterError, AdaptResult

__all__ = [
    "Adapter",
    "AdapterError",
    "AdaptResult",
    "ENTRY_POINT_GROUP",
    "discover",
    "get_adapter",
    "available",
    "register",
]

logger = get_logger(__name__)

ENTRY_POINT_GROUP = "startd8.stakeholder_panel.roster_adapters"

# Built-in adapters: name -> "module:Class" dotted path, imported lazily on first use (R2-F4).
_BUILTINS: Dict[str, str] = {
    "role-rubric": "startd8.stakeholder_panel.adapters.role_rubric:RoleRubricAdapter",
}

_registered: Dict[str, Adapter] = (
    {}
)  # explicitly registered + entry-point-discovered instances
_discovered = False
_lock = threading.Lock()


def _entry_points():
    """Return the group's entry points across importlib.metadata interface versions (providers parity)."""
    try:
        if sys.version_info >= (3, 10):
            from importlib.metadata import entry_points

            try:
                return list(entry_points(group=ENTRY_POINT_GROUP))
            except TypeError:  # pragma: no cover - very old 3.9 backport interface
                return list(entry_points().get(ENTRY_POINT_GROUP, []))
        from importlib.metadata import entry_points

        return list(entry_points().get(ENTRY_POINT_GROUP, []))
    except (
        Exception
    ) as exc:  # pragma: no cover - metadata access should not break the SDK
        logger.debug("roster-adapter entry-point discovery failed: %s", exc)
        return []


def _instantiate(loaded) -> Adapter:
    """An entry point may resolve to a class or an instance; normalize to an instance."""
    return loaded() if isinstance(loaded, type) else loaded


def register(adapter: Adapter) -> None:
    """Register an adapter instance (used by third parties in code and by tests).

    Note: an explicit ``register()`` is an intentional override and *does* shadow a same-named
    built-in — the built-in-wins rule (R1-S2) governs *entry-point* discovery, not deliberate
    in-code registration.
    """
    with _lock:
        _registered[adapter.name] = adapter


def discover(force: bool = False) -> None:
    """Load entry-point adapters (idempotent, failure-isolated). Built-ins load lazily on demand."""
    global _discovered
    with _lock:
        if _discovered and not force:
            return
    for ep in _entry_points():
        if ep.name in _BUILTINS:
            # Built-in wins a name collision (R1-S2) — the SDK's own EP and any third-party shadow.
            logger.debug(
                "entry-point adapter %r shadows a built-in; built-in wins", ep.name
            )
            continue
        try:
            register(_instantiate(ep.load()))
        except (
            Exception
        ) as exc:  # failure isolation — one bad adapter must not break the rest
            logger.warning(
                "skipping broken roster adapter entry point %r: %s", ep.name, exc
            )
    with _lock:
        _discovered = True


def available() -> List[str]:
    """The names of all resolvable adapters (built-ins + discovered), sorted."""
    discover()
    with _lock:  # snapshot under the lock — the loop may be registering concurrently
        registered = set(_registered)
    return sorted(set(_BUILTINS) | registered)


def get_adapter(name: str) -> Adapter:
    """Resolve an adapter by name. Raises :class:`AdapterError` (listing ``available()``) on miss."""
    discover()
    with _lock:
        adapter = _registered.get(
            name
        )  # explicit registration / third-party entry point
    if adapter is not None:
        return adapter
    dotted = _BUILTINS.get(name)
    if dotted is not None:  # lazy import of the built-in (R2-F4), off the lock
        module_name, _, class_name = dotted.partition(":")
        try:
            adapter = getattr(importlib.import_module(module_name), class_name)()
        except (
            Exception
        ) as exc:  # a listed-but-unimportable built-in → clean AdapterError
            raise AdapterError(
                f"built-in adapter {name!r} failed to load: {exc}"
            ) from exc
        register(adapter)
        return adapter
    raise AdapterError(
        f"unknown persona format {name!r}; available: {', '.join(available()) or 'none'}"
    )
