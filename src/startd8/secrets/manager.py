# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
SecretsManager — selects a backend and hydrates ``os.environ`` once at startup.

This is the chokepoint the v0.1 design wrongly placed in ``ConfigManager.get_api_key()``:
providers each call ``os.getenv(...)`` directly, so the only way to reach all of them
with zero provider edits is to populate the environment before they look (FR-4).

Hydration is **thread-safe** (a module lock guards the guard-flag + env writes — FR-6a),
**fail-safe** (a process-control deny-list is never injected — FR-4a; an empty allowlist
injects nothing — FR-4b), and **fail-open by default** (a Doppler outage logs one masked
warning and continues — FR-13). The bearer token is never hydrated (the backend strips it),
so it cannot leak to child processes (FR-15a).
"""

import os
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from ..exceptions import ConfigurationError
from ..logging_config import get_logger
from ..security import mask_api_key
from .protocol import SecretsBackendError, SecretsProvider
from .registry import SecretsProviderRegistry

logger = get_logger("startd8.secrets.manager")

# Process-control env vars that must NEVER be introduced/overwritten by hydration —
# injecting any of these is a host-process code-execution / hijack surface (FR-4a).
# Matched exactly, plus the LD_*/DYLD_* dynamic-linker families by prefix.
_DANGEROUS_KEYS: Set[str] = {
    "PATH", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME", "PYTHONEXECUTABLE",
    "IFS", "BASH_ENV", "ENV", "SHELL", "SHELLOPTS", "GLOBIGNORE",
    "NODE_OPTIONS", "PERL5LIB", "PERL5OPT", "RUBYOPT", "RUBYLIB",
    "GIT_SSH", "GIT_SSH_COMMAND", "GIT_EXTERNAL_DIFF",
    "PROMPT_COMMAND", "PS1", "HOME",
}
_DANGEROUS_PREFIXES = ("LD_", "DYLD_")


def is_dangerous_key(key: str) -> bool:
    """True if ``key`` is a process-control variable hydration must refuse (FR-4a)."""
    return key in _DANGEROUS_KEYS or key.startswith(_DANGEROUS_PREFIXES)


@dataclass
class HydrationResult:
    """Outcome of a ``hydrate()`` call (for diagnostics / CLI ``secrets status``)."""

    backend: str = "local"
    outcome: str = "noop"  # noop | ok | fail_open
    hydrated_keys: List[str] = field(default_factory=list)
    skipped_dangerous: List[str] = field(default_factory=list)
    skipped_present: List[str] = field(default_factory=list)
    fetch_failure: Optional[str] = None  # masked


class SecretsManager:
    """Process-wide secrets hydration coordinator (class-level singleton state)."""

    _lock: threading.Lock = threading.Lock()
    _hydrated: bool = False
    _source_map: Dict[str, str] = {}      # key -> backend name (e.g. 'doppler')
    _fetch_failure: Optional[str] = None  # masked failure string (fail-open)
    _backend_name: str = "local"
    _last_result: Optional[HydrationResult] = None

    # ------------------------------------------------------------------ #
    @classmethod
    def hydrate(cls, force: bool = False) -> HydrationResult:
        """Select the active backend and populate ``os.environ`` once (FR-4, FR-17).

        Idempotent and thread-safe: concurrent callers (e.g. ``AgentFramework`` built
        on multiple threads) trigger exactly one fetch (FR-6a).
        """
        with cls._lock:
            if cls._hydrated and not force:
                return cls._last_result or HydrationResult(backend=cls._backend_name)

            if force:
                # Drop prior-run attribution so a re-hydrate can't report stale sources
                # or a stale fail-open note. (Already-injected os.environ keys are left
                # in place — "existing env wins" still holds on the re-run.)
                cls._source_map = {}
                cls._fetch_failure = None

            cfg = _load_settings()
            backend_name = cfg["backend"]
            cls._backend_name = backend_name
            result = HydrationResult(backend=backend_name)

            if backend_name == "local":
                # Default: nothing to hydrate; env/config already apply (FR-9).
                cls._hydrated = True
                cls._last_result = result
                return result

            backend = _resolve_backend(backend_name, cfg)
            secrets: Dict[str, str] = {}
            try:
                backend.validate_config()
                secrets = backend.get_all_secrets()
                result.outcome = "ok"
            except (SecretsBackendError, ConfigurationError) as e:
                masked = _mask_error(str(e))
                if cfg["fail_closed"]:
                    # Surface misconfiguration at the exact source (FR-13).
                    raise ConfigurationError(
                        f"Secrets backend '{backend_name}' failed (fail_closed): {masked}. "
                        f"Check credentials/network, or set secrets_backend.fail_closed=false "
                        f"to continue with env/config."
                    )
                # Fail-open: one loud masked warning, continue un-hydrated (FR-13a).
                cls._fetch_failure = masked
                result.outcome = "fail_open"
                result.fetch_failure = masked
                logger.warning(
                    "Secrets backend '%s' fetch failed; continuing with env/config "
                    "(fail-open). Cause: %s", backend_name, masked
                )

            allowlist = cfg["allowlist"]  # None=all, set()=none, {..}=those
            for key, value in secrets.items():
                if is_dangerous_key(key):
                    result.skipped_dangerous.append(key)
                    logger.warning(
                        "Refusing to hydrate process-control key '%s' from secrets "
                        "backend '%s' (deny-list)", key, backend_name
                    )
                    continue
                if allowlist is not None and key not in allowlist:
                    continue
                if key in os.environ:  # existing env ALWAYS wins
                    result.skipped_present.append(key)
                    continue
                os.environ[key] = value
                cls._source_map[key] = backend_name
                result.hydrated_keys.append(key)

            if result.outcome != "fail_open":
                logger.info(
                    "Secrets hydration via '%s': %d injected, %d skipped (present), "
                    "%d denied", backend_name, len(result.hydrated_keys),
                    len(result.skipped_present), len(result.skipped_dangerous)
                )
            cls._hydrated = True
            cls._last_result = result
            return result

    # ------------------------------------------------------------------ #
    @classmethod
    def get_secret(cls, name: str) -> Optional[str]:
        """Resolve a secret from the (possibly hydrated) environment."""
        if not cls._hydrated:
            cls.hydrate()
        return os.environ.get(name)

    @classmethod
    def get_secret_source(cls, name: str) -> Optional[str]:
        """Report where ``name`` resolves from: ``doppler`` | ``env`` | ``None``.

        ``local`` is a backend, not a provenance — a value the local backend "provides"
        is really an ``env`` value, so it is reported as ``env`` (FR-5a). Config-file
        attribution for provider keys stays with ``ConfigManager.get_api_key_source``.
        """
        if name in cls._source_map:
            return cls._source_map[name]
        if os.environ.get(name):
            return "env"
        return None

    @classmethod
    def get_fetch_failure(cls) -> Optional[str]:
        """The masked fail-open failure string, if the last fetch failed."""
        return cls._fetch_failure

    @classmethod
    def annotate_missing_key(cls, name: str) -> str:
        """A bounded missing-key message that cites an earlier fail-open (FR-13a).

        The masked failure is referenced once; raw/full token material is never
        included (the stash is already masked).
        """
        base = f"{name} not set"
        if cls._fetch_failure:
            return f"{base} — note: secrets backend fetch failed earlier: {cls._fetch_failure}"
        return base

    @classmethod
    def active_backend(cls) -> str:
        return cls._backend_name

    @classmethod
    def last_result(cls) -> Optional[HydrationResult]:
        return cls._last_result

    @classmethod
    def _reset_for_tests(cls) -> None:
        with cls._lock:
            cls._hydrated = False
            cls._source_map = {}
            cls._fetch_failure = None
            cls._backend_name = "local"
            cls._last_result = None


# ---------------------------------------------------------------------- #
def _load_settings() -> Dict[str, object]:
    """Resolve backend selection + options from env (highest) then SDK config."""
    cfg: Dict[str, object] = {}
    try:
        from ..config import get_config_manager
        cfg = get_config_manager().get_secrets_backend_config() or {}
    except Exception as e:  # pragma: no cover - config best-effort
        logger.debug("Could not read secrets_backend config: %s", e)
        cfg = {}

    backend = (os.environ.get("STARTD8_SECRETS_BACKEND")
               or cfg.get("backend") or "local")
    backend = str(backend).lower()

    # fail_closed: env wins, else config, else False (fail-open default — FR-13).
    if "STARTD8_SECRETS_FAIL_CLOSED" in os.environ:
        fail_closed = _truthy(os.environ["STARTD8_SECRETS_FAIL_CLOSED"])
    else:
        fail_closed = bool(cfg.get("fail_closed", False))

    # allowlist: env wins (present => parse; "" => inject-none), else config, else None.
    if "STARTD8_SECRETS_ALLOWLIST" in os.environ:
        raw = os.environ["STARTD8_SECRETS_ALLOWLIST"].strip()
        allowlist: Optional[Set[str]] = (
            set() if raw == "" else {p.strip() for p in raw.split(",") if p.strip()}
        )
    elif "allowlist" in cfg and cfg["allowlist"] is not None:
        allowlist = set(cfg["allowlist"])  # [] => inject-none (FR-4b)
    else:
        allowlist = None  # absent => inject-all-if-absent (FR-4b)

    token = os.environ.get("DOPPLER_TOKEN") or cfg.get("doppler_token")

    return {
        "backend": backend,
        "fail_closed": fail_closed,
        "allowlist": allowlist,
        "doppler_token": token,
    }


def _resolve_backend(name: str, cfg: Dict[str, object]) -> SecretsProvider:
    backend = SecretsProviderRegistry.get_backend(name)
    if backend is None:
        raise ConfigurationError(
            f"Unknown secrets backend '{name}'. "
            f"Available: {', '.join(SecretsProviderRegistry.list_backends())}"
        )
    # Layer SDK-config token into the doppler backend if env didn't supply one.
    if name == "doppler" and cfg.get("doppler_token") and not getattr(backend, "_token", None):
        try:
            backend._token = cfg["doppler_token"]  # type: ignore[attr-defined]
        except Exception:  # pragma: no cover
            pass
    return backend


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _mask_error(message: str) -> str:
    """Redact anything that looks like a Doppler token (``dp.*``) from an error string."""
    import re
    return re.sub(r"dp\.[A-Za-z0-9._-]{6,}",
                  lambda m: mask_api_key(m.group(0)), message)
