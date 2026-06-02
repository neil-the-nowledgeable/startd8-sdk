"""Deterministic file providers — the language-agnostic seam for the prime-contractor's
owned-file skip-hook.

The prime contractor can skip the LLM (mark a feature ``GENERATED`` at $0.00) when every
target file is *deterministically provided* and currently in-sync with its source. **What
counts as "deterministically provided" must not be hard-coded to any one stack** — the core
orchestrator stays polyglot. This module is that decoupling: a small protocol + registry that
``prime_contractor`` consults without importing any language/framework-specific code.

- The TS **Prisma→Zod** logic lives in a provider in ``frontend_codegen`` (registered via the
  ``startd8.contractors.deterministic_providers`` entry-point group), not in the core.
- A future **proto/gRPC stub** provider (for the online-boutique microservices target) registers
  the same way. The core never changes.

Mirrors the SDK's ``ProviderRegistry``/``LanguageRegistry`` discovery idiom (entry points +
explicit registration for tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Protocol, Tuple, runtime_checkable

from ..logging_config import get_logger

logger = get_logger(__name__)

_ENTRY_POINT_GROUP = "startd8.contractors.deterministic_providers"


@dataclass(frozen=True)
class ProviderContext:
    """What a provider may need to judge in-sync-ness, supplied by the orchestrator.

    Intentionally generic (no Prisma/TS specifics): the project root and the feature/seed
    upstream anchors (e.g. a ``.prisma`` schema, a ``.proto`` file). A provider finds and reads
    whatever source it needs from these — the core does not read schemas.
    """

    project_root: Path
    source_anchors: Tuple[str, ...] = ()


@runtime_checkable
class DeterministicFileProvider(Protocol):
    """A pluggable judge of "is this on-disk file a deterministically-generated, in-sync file?".

    Implementations are stack-specific (Prisma→Zod, proto stubs, …) and register themselves;
    the prime contractor only ever sees this protocol.
    """

    name: str

    def owns(self, path: Path, content: str) -> bool:
        """True if this provider recognizes *path*/*content* as one of its generated artifacts
        (e.g. by a generated-file header or path/extension). Cheap; no source read."""
        ...

    def is_in_sync(self, path: Path, content: str, context: ProviderContext) -> bool:
        """True iff the file is currently in-sync with its source (safe to skip the LLM).
        Header/marker presence alone must NOT return True — verify against the source.
        """
        ...


_PROVIDERS: List[DeterministicFileProvider] = []
_DISCOVERED = False


def register_provider(provider: DeterministicFileProvider) -> None:
    """Register a provider explicitly (used by tests and as a programmatic fallback)."""
    if provider not in _PROVIDERS:
        _PROVIDERS.append(provider)


def clear_providers() -> None:
    """Reset the registry (test hygiene)."""
    global _DISCOVERED
    _PROVIDERS.clear()
    _DISCOVERED = False


def discover(force: bool = False) -> None:
    """Load providers from the ``startd8.contractors.deterministic_providers`` entry points.

    Idempotent; failures are logged and non-fatal (a missing/old entry point simply means the
    skip-hook won't fire for that stack — safe degradation, never a crash).
    """
    global _DISCOVERED
    if _DISCOVERED and not force:
        return
    _DISCOVERED = True
    try:
        try:
            from importlib.metadata import entry_points

            try:
                eps = entry_points(group=_ENTRY_POINT_GROUP)  # py3.10+
            except TypeError:  # pragma: no cover - older selection API
                eps = entry_points().get(_ENTRY_POINT_GROUP, [])
        except ImportError:  # pragma: no cover
            from importlib_metadata import entry_points  # type: ignore

            eps = entry_points().get(_ENTRY_POINT_GROUP, [])
    except Exception as exc:  # pragma: no cover - discovery is best-effort
        logger.debug("deterministic-provider discovery unavailable: %s", exc)
        return

    for ep in eps:
        try:
            cls = ep.load()
            register_provider(cls() if isinstance(cls, type) else cls)
        except (
            Exception
        ) as exc:  # pragma: no cover - one bad provider must not break the rest
            logger.debug("failed to load deterministic provider %r: %s", ep, exc)


def is_deterministically_provided(
    path: Path, content: str, context: ProviderContext
) -> bool:
    """True iff some registered provider owns *path* and reports it in-sync with its source.

    This is the single question the prime-contractor skip-hook asks — with no knowledge of
    Prisma, TypeScript, protobuf, or any specific stack.
    """
    discover()
    for provider in _PROVIDERS:
        try:
            if provider.owns(path, content) and provider.is_in_sync(
                path, content, context
            ):
                return True
        except (
            Exception
        ) as exc:  # pragma: no cover - a provider error is never a false skip
            logger.debug(
                "provider %s errored on %s: %s",
                getattr(provider, "name", provider),
                path,
                exc,
            )
    return False
