# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""
Doppler secrets backend — reads a config's secrets via the Doppler v3 REST API.

Direct REST (no Doppler SDK dependency — OQ-1): one ``secrets/download`` call returns
the whole config as a JSON map, which the SecretsManager then hydrates into the
environment. Auth is a read-only service token scoped to one project+config (FR-8a /
NR-8 — single-token/single-config in v1).

Security/ops invariants enforced here:
- The bearer ``DOPPLER_TOKEN`` is read for the request and is **never** returned in the
  secret map, so hydration can never re-export it to child processes (R1-S2 / FR-15a).
- Doppler metadata keys (``DOPPLER_PROJECT``/``DOPPLER_CONFIG``/``DOPPLER_ENVIRONMENT``)
  are stripped.
- The fetch is wrapped in an OTel span whose attributes carry only non-secret metadata;
  no secret/token value is ever set as an attribute (R1-S5 / FR-16).
- In-memory cache only, fetch-once-per-process; no TTL / no force-refresh in v1
  (NR-7 — rotation requires a process restart).
"""

import os
import time
from typing import Dict, List, Optional

from ..exceptions import ConfigurationError
from ..logging_config import get_logger
from ..security import mask_api_key
from .protocol import SecretsBackendError

logger = get_logger("startd8.secrets.doppler")

# Graceful OTel import — no-op span when not installed (matches orchestration.py).
try:  # pragma: no cover - import guard
    from opentelemetry import trace as _otel_trace
    _tracer = _otel_trace.get_tracer("startd8.secrets")
except ImportError:  # pragma: no cover
    _otel_trace = None
    _tracer = None

DOPPLER_DOWNLOAD_URL = "https://api.doppler.com/v3/configs/config/secrets/download"

# Doppler injects these book-keeping keys into every config; they are not app secrets.
_DOPPLER_METADATA_KEYS = frozenset({
    "DOPPLER_PROJECT",
    "DOPPLER_CONFIG",
    "DOPPLER_ENVIRONMENT",
    "DOPPLER_TOKEN",  # never surface the bearer token as a hydratable secret
})

_DEFAULT_TIMEOUT_S = 10.0
_MAX_ATTEMPTS = 3


class DopplerSecretsProvider:
    """Read-only Doppler backend over the v3 download endpoint."""

    def __init__(self, token: Optional[str] = None, *, timeout: float = _DEFAULT_TIMEOUT_S):
        # Token precedence: explicit arg > DOPPLER_TOKEN env (Doppler's own convention).
        # SDK-config sourcing is layered in by the manager when it constructs us.
        self._token = token or os.environ.get("DOPPLER_TOKEN")
        self._timeout = timeout
        self._cache: Optional[Dict[str, str]] = None  # v1: no runtime invalidation (NR-7)

    @property
    def name(self) -> str:
        return "doppler"

    def get_required_env_vars(self) -> List[str]:
        return ["DOPPLER_TOKEN"]

    def validate_config(self) -> bool:
        if not self._token:
            raise ConfigurationError(
                "Doppler secrets backend requires a service token. "
                "Set DOPPLER_TOKEN, or configure secrets_backend.doppler_token."
            )
        return True

    def get_secret(self, key: str) -> Optional[str]:
        return self.get_all_secrets().get(key)

    def get_all_secrets(self) -> Dict[str, str]:
        """Fetch + cache the config's secret map (FR-3, FR-6, FR-16).

        Raises:
            SecretsBackendError: on network/auth/parse failure — the manager decides
                fail-open vs fail-closed (FR-13).
        """
        if self._cache is not None:
            return self._cache
        self.validate_config()

        span_cm = (
            _tracer.start_as_current_span("secrets.fetch")
            if _tracer is not None else _NullSpan()
        )
        with span_cm as span:
            _set_attr(span, "secrets.backend", "doppler")
            cache_hit = False  # this method only runs on a cache miss
            _set_attr(span, "secrets.cache_hit", cache_hit)
            try:
                raw = self._download()
                secrets = {
                    k: v for k, v in raw.items() if k not in _DOPPLER_METADATA_KEYS
                }
                self._cache = secrets
                _set_attr(span, "secrets.key_count", len(secrets))  # count only, never values
                _set_attr(span, "secrets.outcome", "ok")
                logger.info("Doppler fetch ok: %d secret(s) available", len(secrets))
                return secrets
            except SecretsBackendError as e:
                _set_attr(span, "secrets.outcome", "fetch_error")
                if _otel_trace is not None and span is not None:
                    try:
                        span.record_exception(e)
                    except Exception:  # pragma: no cover - telemetry best-effort
                        pass
                raise

    # ------------------------------------------------------------------ #
    def _download(self) -> Dict[str, str]:
        """One GET to the v3 download endpoint, with bounded retries."""
        import httpx  # local import: keeps httpx out of the hot import path

        headers = {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
        params = {"format": "json"}
        last_error: Optional[Exception] = None

        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                with httpx.Client(timeout=self._timeout) as client:
                    resp = client.get(DOPPLER_DOWNLOAD_URL, headers=headers, params=params)
                if resp.status_code in (401, 403):
                    # Auth failures are not retryable — fail fast with a masked hint.
                    raise SecretsBackendError(
                        f"Doppler auth failed (HTTP {resp.status_code}) for token "
                        f"{mask_api_key(self._token or '')}",
                        backend="doppler",
                    )
                if 400 <= resp.status_code < 500:
                    # Other client errors (404 project/config not found, 422, …) are not
                    # transient — surface the real cause instead of retrying 3× (FR-13).
                    raise SecretsBackendError(
                        f"Doppler request rejected (HTTP {resp.status_code}) — check the "
                        f"project/config the token is scoped to.",
                        backend="doppler",
                    )
                resp.raise_for_status()  # 5xx → retryable below
                data = resp.json()
                if not isinstance(data, dict):
                    raise SecretsBackendError(
                        "Doppler download returned a non-object payload", backend="doppler"
                    )
                # All values are strings in Doppler's format=json response.
                return {str(k): "" if v is None else str(v) for k, v in data.items()}
            except SecretsBackendError:
                raise  # already classified (auth) — do not retry
            except Exception as e:  # network/timeout/HTTP-5xx/json — retryable
                last_error = e
                if attempt < _MAX_ATTEMPTS:
                    backoff = 0.25 * (2 ** (attempt - 1))  # 0.25, 0.5
                    logger.debug("Doppler fetch attempt %d failed (%s); retrying in %.2fs",
                                 attempt, type(e).__name__, backoff)
                    time.sleep(backoff)

        raise SecretsBackendError(
            f"Doppler fetch failed after {_MAX_ATTEMPTS} attempts: "
            f"{type(last_error).__name__}: {last_error}",
            backend="doppler",
            original_error=last_error,
        )


def _set_attr(span, key: str, value) -> None:
    """Best-effort span attribute set (no-op when telemetry is off)."""
    if span is None:
        return
    try:
        span.set_attribute(key, value)
    except Exception:  # pragma: no cover - telemetry best-effort
        pass


class _NullSpan:
    """Context manager yielding ``None`` when OTel is unavailable."""

    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False
