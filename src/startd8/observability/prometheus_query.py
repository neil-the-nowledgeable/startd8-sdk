# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Canonical Prometheus query-API client (single, discoverable home).

This is the **one** Prometheus HTTP client in ``src/`` (Genchi Genbutsu R4 /
Mottainai — one canonical, discoverable implementation). It hosts the vetted
``instant_query_count`` / ``list_metric_names`` primitives that previously lived
only in ``scripts/otel_demo/adapters/prometheus.py`` (not on the package path),
plus a new ``label_values`` primitive the FR-9 diagnosis needs.

The live-validation harness (``validate_promql.py``, ContextCore
``REQ_TARGET_METRIC_BINDING.md`` FR-8..10) replays generated PromQL through
these functions. The scripts adapter now re-exports from here so there is a
single implementation, not two.

Auth (FR-8b): bearer-token and the Mimir ``X-Scope-OrgID`` multi-tenant header
are read from an :class:`Auth` value built from the environment (never from a
CLI flag or manifest). All requests are read-only ``GET`` against the Prometheus
query API.

Environment variables (FR-8b — credentials from env/secret only):

* ``PROMETHEUS_BEARER_TOKEN`` — bearer token for ``Authorization: Bearer …``.
* ``PROMETHEUS_ORG_ID`` (or ``X_SCOPE_ORGID``) — Mimir/Cortex tenant id.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

REQUEST_TIMEOUT = 15

#: Environment variable names carrying credentials (FR-8b). Kept here so the
#: harness can enumerate them for redaction without hardcoding the list twice.
BEARER_TOKEN_ENV = "PROMETHEUS_BEARER_TOKEN"
ORG_ID_ENVS = ("PROMETHEUS_ORG_ID", "X_SCOPE_ORGID")


@dataclass(frozen=True)
class Auth:
    """Prometheus auth material — bearer token + multi-tenant org id (FR-8b).

    Built via :meth:`from_env` so credentials come **only** from the
    environment/secret store, never a CLI flag or manifest. ``redactions``
    exposes the raw secret strings so callers can scrub them from any output.
    """

    bearer_token: Optional[str] = None
    org_id: Optional[str] = None

    @classmethod
    def from_env(cls, env: Optional[Dict[str, str]] = None) -> "Auth":
        """Read bearer token + ``X-Scope-OrgID`` from the environment (FR-8b)."""
        e = env if env is not None else os.environ
        token = e.get(BEARER_TOKEN_ENV) or None
        org_id = None
        for name in ORG_ID_ENVS:
            if e.get(name):
                org_id = e[name]
                break
        return cls(bearer_token=token, org_id=org_id)

    def headers(self) -> Dict[str, str]:
        """HTTP headers implied by this auth (empty when unauthenticated)."""
        h: Dict[str, str] = {"Accept": "application/json"}
        if self.bearer_token:
            h["Authorization"] = f"Bearer {self.bearer_token}"
        if self.org_id:
            h["X-Scope-OrgID"] = self.org_id
        return h

    def redactions(self) -> List[str]:
        """Raw secret strings to scrub from output (FR-8b redaction)."""
        secrets: List[str] = []
        if self.bearer_token:
            secrets.append(self.bearer_token)
        if self.org_id:
            secrets.append(self.org_id)
        return secrets


def _get_json(
    url: str,
    *,
    auth: Optional[Auth] = None,
    timeout: int = REQUEST_TIMEOUT,
) -> Any:
    """Read-only ``GET`` returning parsed JSON, with optional auth headers.

    Mirrors ``scripts/otel_demo/adapters/http_json.get_json`` but threads the
    FR-8b auth headers. Network/parse errors propagate to the caller so the
    harness can classify an unreachable backend as a distinct non-pass (FR-10).
    """
    headers = auth.headers() if auth else {"Accept": "application/json"}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def instant_query_count(
    base: str,
    promql: str,
    *,
    auth: Optional[Auth] = None,
    timeout: int = REQUEST_TIMEOUT,
) -> int:
    """Number of series returned by an instant ``/api/v1/query`` (0 ⇒ empty).

    The load-bearing primitive the FR-8 harness replays every generated PromQL
    through. A non-zero return means the query matched live series (PASS).
    """
    q = urllib.parse.quote(promql, safe="")
    data = _get_json(
        f"{base.rstrip('/')}/api/v1/query?query={q}", auth=auth, timeout=timeout
    )
    result = data.get("data", {}).get("result") or []
    return len(result)


def scrape_ready(
    base: str,
    job: str,
    *,
    auth: Optional[Auth] = None,
    timeout: int = REQUEST_TIMEOUT,
) -> bool:
    """True once Prometheus has landed ≥1 sample for ``job`` in its TSDB.

    The load-bearing readiness signal for the Tier-B live comparison
    (``compare_live``): replaying generated PromQL *before* the first scrape
    completes would return empty for every query — a false all-``fail`` report
    indistinguishable from a genuinely dead SLI. We gate on
    ``sum(scrape_samples_scraped{job="<job>"})`` rather than ``up`` because
    ``up==1`` only means the target *responded*; a positive sample count
    guarantees series actually exist and are queryable. Any backend/parse error
    propagates so the poller keeps waiting rather than treating a transient as
    ready.
    """
    promql = f'sum(scrape_samples_scraped{{job="{job}"}})'
    q = urllib.parse.quote(promql, safe="")
    data = _get_json(
        f"{base.rstrip('/')}/api/v1/query?query={q}", auth=auth, timeout=timeout
    )
    result = data.get("data", {}).get("result") or []
    for series in result:
        value = series.get("value") or []
        # instant-vector value is ``[<ts>, "<number>"]``; ready iff strictly > 0.
        if len(value) == 2:
            try:
                if float(value[1]) > 0:
                    return True
            except (TypeError, ValueError):
                continue
    return False


def list_metric_names(
    base: str,
    *,
    auth: Optional[Auth] = None,
    timeout: int = REQUEST_TIMEOUT,
) -> List[str]:
    """All metric ``__name__`` values the backend actually exposes (FR-9).

    One half of FR-9's two-sided ground truth: the live system's real series,
    used to decide whether an emitted metric name is simply absent.
    """
    data = _get_json(
        f"{base.rstrip('/')}/api/v1/label/__name__/values", auth=auth, timeout=timeout
    )
    return list(data.get("data") or [])


def label_values(
    base: str,
    label: str,
    *,
    auth: Optional[Auth] = None,
    timeout: int = REQUEST_TIMEOUT,
) -> List[str]:
    """All values the backend has for a given ``label`` (FR-9).

    Used to check whether a descriptor's service-identity label **key** exists
    at all (empty ⇒ the key is absent from the backend's label set).
    """
    safe_label = urllib.parse.quote(label, safe="")
    data = _get_json(
        f"{base.rstrip('/')}/api/v1/label/{safe_label}/values",
        auth=auth,
        timeout=timeout,
    )
    return list(data.get("data") or [])


__all__ = [
    "Auth",
    "instant_query_count",
    "scrape_ready",
    "list_metric_names",
    "label_values",
    "REQUEST_TIMEOUT",
    "BEARER_TOKEN_ENV",
    "ORG_ID_ENVS",
]
