"""M0 — TSDB read-back seam (FR-1).

A bounded reader that queries a Prometheus/Mimir-compatible endpoint for a metric (or
family) via ``last_over_time(<metric>[<lookback>])`` and returns label-sets + latest value.
This generalizes the *shape* of the michigan reference's ``query_mimir``
(``export_to_supabase.py``) onto ``httpx`` — it does **not** port the urllib specifics, and
it is **not** a general PromQL builder (NR-6): one bounded ``last_over_time`` read.

Load-bearing FR-1 behaviors (all CRP-hardened):

* **Endpoint config** — Grafana datasource proxy (auth) *or* direct Mimir/Prometheus.
* **Auth (R1-F11)** — a Grafana-proxy token comes from **env / secrets, never a CLI flag**;
  a ``401``/``403`` is a **distinct** :class:`AuthError` exit, never the empty-result path,
  so an auth failure can never masquerade as an honest empty refuse.
* **Empty-result classification (OQ-6, R1-F6)** — an empty vector is never silently yielded
  as an empty specimen. It is classified into two distinct causes:
    - *names-in-index but samples-pruned* → :class:`EmptyMaterialization` (the honest
      empty-materialization refuse, OQ-6);
    - *metric genuinely absent from the index* → :class:`MetricNotFound` (a config/typo
      error worth a distinct message).
* **Family fan-out (FR-12 coupling, R1-S5)** — :meth:`TsdbReader.read_family` issues **one
  query per member**; the index-join by identity happens in M2 (which owns the identity),
  so M0 provides the per-member read *capability* the family grouper depends on.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional, Protocol, Sequence, runtime_checkable

import httpx

from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Default lookback mirrors the michigan reference's intent (`last_over_time(gov_*[3000d])`):
# reach back far enough to catch pruned/old snapshots. Configurable per read.
DEFAULT_LOOKBACK = "3000d"

# Env vars consulted (in order) for a Grafana-proxy bearer token. Never a CLI flag (R1-F11).
DEFAULT_TOKEN_ENV = ("GRAFANA_API_TOKEN", "GRAFANA_SA_TOKEN")


# --------------------------------------------------------------------------- #
# Errors — each maps to a distinct CLI exit (M6). None of the "empty" causes    #
# share an exception, so a config typo, an auth failure, and honest pruning are #
# never conflated.                                                              #
# --------------------------------------------------------------------------- #
class TsdbReaderError(RuntimeError):
    """Base class for all reader failures."""


class AuthError(TsdbReaderError):
    """A ``401``/``403`` from the endpoint (R1-F11). Distinct from every empty path."""


class MetricNotFound(TsdbReaderError):
    """The metric is genuinely absent from the index — a config/typo error (R1-F6)."""


class EmptyMaterialization(TsdbReaderError):
    """The metric exists in the index but the query yielded no samples — pruned/retention.

    This is the honest empty-materialization *refuse* (OQ-6): promotion must not proceed on
    an empty specimen. It is deliberately a hard error rather than an empty result so the
    reader can never silently yield an empty specimen (FR-1).
    """


class TsdbQueryError(TsdbReaderError):
    """The endpoint returned a non-success PromQL status (e.g. a bad query/range)."""


# --------------------------------------------------------------------------- #
# Result models                                                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Series:
    """One time-series: its label-set plus the latest observed sample.

    ``labels`` excludes ``__name__``. ``value`` is the ``last_over_time`` scalar; ``timestamp``
    is the Unix-seconds evaluation time of the instant query (the sample's effective time).
    """

    labels: Mapping[str, str]
    value: float
    timestamp: float


@dataclass(frozen=True)
class ReadResult:
    """The materialized read of one metric — the raw input to M1's specimen (FR-2)."""

    metric: str
    lookback: str
    series: tuple[Series, ...]

    @property
    def is_empty(self) -> bool:
        return not self.series

    def __len__(self) -> int:
        return len(self.series)


# --------------------------------------------------------------------------- #
# Endpoints — Grafana datasource proxy (auth) or direct Mimir/Prometheus.        #
# Both resolve to a Prometheus HTTP API v1 base + request headers.              #
# --------------------------------------------------------------------------- #
@runtime_checkable
class Endpoint(Protocol):
    """A resolvable Prometheus HTTP API v1 endpoint."""

    def api_url(self, api: str) -> str:
        """Absolute URL for a v1 API path, e.g. ``api("query")`` / ``api("label/__name__/values")``."""

    def headers(self) -> dict[str, str]:
        """Request headers (auth, tenant). May be empty."""


def _resolve_token(env_names: Sequence[str]) -> Optional[str]:
    """Resolve a bearer token from the environment, then the secrets manager (R1-F11).

    Never reads a CLI flag. The secrets lookup is best-effort: if the secrets subsystem is
    unavailable it degrades to env-only rather than raising.
    """
    for name in env_names:
        val = os.getenv(name)
        if val:
            return val
    try:  # best-effort: hydrated secrets (Doppler/local) without a hard import dependency
        from startd8 import secrets as _secrets

        for name in env_names:
            val = _secrets.get_secret(name)
            if val:
                return val
    except Exception:  # noqa: BLE001 — secrets are optional; env-only is a valid config
        logger.debug("secrets subsystem unavailable; token resolved from env only")
    return None


@dataclass(frozen=True)
class GrafanaProxyEndpoint:
    """Query a Prometheus-API datasource **through the Grafana proxy** by datasource uid.

    Mirrors the recon scripts' ``/api/datasources/proxy/uid/<uid>/api/v1/...`` shape. The
    bearer token is resolved from ``token_env`` (env → secrets), never a flag.
    """

    base_url: str  # e.g. "http://localhost:3000"
    datasource_uid: str  # e.g. "mimir"
    token_env: tuple[str, ...] = DEFAULT_TOKEN_ENV

    def api_url(self, api: str) -> str:
        base = self.base_url.rstrip("/")
        return f"{base}/api/datasources/proxy/uid/{self.datasource_uid}/api/v1/{api.lstrip('/')}"

    def headers(self) -> dict[str, str]:
        token = _resolve_token(self.token_env)
        return {"Authorization": f"Bearer {token}"} if token else {}


@dataclass(frozen=True)
class DirectMimirEndpoint:
    """Query a Mimir/Prometheus HTTP API directly.

    ``prometheus_prefix`` defaults to Mimir's ``/prometheus`` query-frontend prefix; set it to
    ``""`` for a vanilla Prometheus. ``tenant`` sets the ``X-Scope-OrgID`` multi-tenant header.
    """

    base_url: str  # e.g. "http://localhost:9009"
    prometheus_prefix: str = "/prometheus"
    tenant: Optional[str] = None
    token_env: tuple[str, ...] = DEFAULT_TOKEN_ENV

    def api_url(self, api: str) -> str:
        base = self.base_url.rstrip("/")
        prefix = self.prometheus_prefix.rstrip("/")
        return f"{base}{prefix}/api/v1/{api.lstrip('/')}"

    def headers(self) -> dict[str, str]:
        hdrs: dict[str, str] = {}
        if self.tenant:
            hdrs["X-Scope-OrgID"] = self.tenant
        token = _resolve_token(self.token_env)
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        return hdrs


# --------------------------------------------------------------------------- #
# The reader                                                                    #
# --------------------------------------------------------------------------- #
def _build_promql(metric: str, lookback: str, matchers: Optional[Mapping[str, str]]) -> str:
    """``last_over_time(<metric>{<matchers>}[<lookback>])`` — a bounded read (NR-6)."""
    selector = metric
    if matchers:
        parts = ",".join(f'{k}="{v}"' for k, v in sorted(matchers.items()))
        selector = f"{metric}{{{parts}}}"
    return f"last_over_time({selector}[{lookback}])"


@dataclass
class TsdbReader:
    """Bounded reader for a Prometheus/Mimir-compatible endpoint (FR-1).

    Inject ``client`` (an :class:`httpx.Client`) in tests — e.g. one backed by
    :class:`httpx.MockTransport` — so the reader is exercisable without a live TSDB
    (the gov series are retention-pruned; recorded fixtures are the validation path).
    """

    endpoint: Endpoint
    timeout: float = 30.0
    client: Optional[httpx.Client] = None
    _owns_client: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.client is None:
            self.client = httpx.Client(timeout=self.timeout)
            self._owns_client = True

    # -- lifecycle --------------------------------------------------------- #
    def close(self) -> None:
        if self._owns_client and self.client is not None:
            self.client.close()

    def __enter__(self) -> "TsdbReader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- low-level HTTP ---------------------------------------------------- #
    def _get(self, api: str, params: Optional[dict] = None) -> dict:
        assert self.client is not None
        url = self.endpoint.api_url(api)
        # A connection/timeout failure is a reader error, not a raw httpx traceback — callers
        # (the CLI) catch TsdbReaderError, so every failure mode surfaces through that contract.
        try:
            resp = self.client.get(url, params=params, headers=self.endpoint.headers())
        except httpx.RequestError as exc:
            raise TsdbReaderError(f"cannot reach {url!r}: {exc}") from exc
        # Auth is classified BEFORE any body parsing so a 401 can never fall through to the
        # empty-result path (R1-F11).
        if resp.status_code in (401, 403):
            raise AuthError(
                f"endpoint returned {resp.status_code} for {api!r} — check the token "
                f"({'/'.join(_token_env_of(self.endpoint))}); tokens come from env/secrets, "
                "never a flag"
            )
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise TsdbReaderError(
                f"endpoint returned HTTP {resp.status_code} for {api!r}: {exc}"
            ) from exc
        try:
            payload = resp.json()
        except ValueError as exc:  # non-JSON body (e.g. an HTML error page from a proxy)
            raise TsdbReaderError(f"non-JSON response from {url!r}: {exc}") from exc
        if payload.get("status") != "success":
            raise TsdbQueryError(
                f"PromQL {api!r} returned status={payload.get('status')!r}: "
                f"{payload.get('error') or payload.get('errorType') or 'unknown error'}"
            )
        return payload.get("data", {}) or {}

    # -- public API -------------------------------------------------------- #
    def read(
        self,
        metric: str,
        lookback: str = DEFAULT_LOOKBACK,
        matchers: Optional[Mapping[str, str]] = None,
    ) -> ReadResult:
        """Read one metric's latest value per series via ``last_over_time``.

        Raises :class:`AuthError` on 401/403, :class:`EmptyMaterialization` when the metric is
        in the index but yielded no samples (OQ-6 refuse), and :class:`MetricNotFound` when the
        metric is absent from the index (config/typo). Never returns an empty :class:`ReadResult`.
        """
        promql = _build_promql(metric, lookback, matchers)
        logger.debug("tsdb read: %s", promql)
        data = self._get("query", {"query": promql})
        series = _parse_vector(data)
        if series:
            return ReadResult(metric=metric, lookback=lookback, series=tuple(series))

        # Empty vector → classify the cause (R1-F6). This second call only happens on the
        # empty path, so the common (non-empty) read is a single request.
        if self._metric_in_index(metric):
            raise EmptyMaterialization(
                f"metric {metric!r} exists in the index but returned no samples over "
                f"[{lookback}] — retention-pruned. Refusing empty materialization (OQ-6); "
                "widen --lookback or re-push the source data."
            )
        raise MetricNotFound(
            f"metric {metric!r} is absent from the index — check for a typo or wrong "
            "endpoint/datasource (this is not an empty-data refuse)."
        )

    def read_family(
        self,
        metrics: Sequence[str],
        lookback: str = DEFAULT_LOOKBACK,
        matchers: Optional[Mapping[str, str]] = None,
    ) -> dict[str, ReadResult]:
        """Issue **one query per member** of a metric family (FR-12 coupling, R1-S5).

        Returns a per-member ``{metric: ReadResult}`` map — the read *capability* the M2 family
        grouper consumes to index-join members by their (M2-inferred) identity. Member-level
        empties/typos surface as their own exceptions (fail-loud), since the join semantics for
        partial-overlap member sets are owned by M2 (R1-F4), not smoothed over here.
        """
        if not metrics:
            raise ValueError("read_family requires at least one metric")
        results: dict[str, ReadResult] = {}
        for metric in metrics:
            results[metric] = self.read(metric, lookback=lookback, matchers=matchers)
        return results

    # -- index classification --------------------------------------------- #
    def _metric_in_index(self, metric: str) -> bool:
        """Is ``metric`` a known name in the series index? (drives the R1-F6 split.)"""
        data = self._get("label/__name__/values")
        names = data if isinstance(data, list) else data.get("data", data)
        # `/label/<name>/values` returns data == list[str]; _get already unwrapped "data".
        return metric in set(names or ())


# --------------------------------------------------------------------------- #
# Parsing helpers                                                               #
# --------------------------------------------------------------------------- #
def _parse_vector(data: dict) -> list[Series]:
    """Parse an instant-query vector result into :class:`Series`.

    Tolerates a scalar/absent value; skips result entries without a usable ``value`` pair.
    """
    result = data.get("result", []) if isinstance(data, dict) else []
    out: list[Series] = []
    for entry in result:
        metric = {k: v for k, v in entry.get("metric", {}).items() if k != "__name__"}
        pair = entry.get("value")
        if not pair or len(pair) != 2:
            continue
        ts, raw = pair
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        try:
            timestamp = float(ts)
        except (TypeError, ValueError):
            timestamp = 0.0
        out.append(Series(labels=metric, value=value, timestamp=timestamp))
    return out


def _token_env_of(endpoint: Endpoint) -> tuple[str, ...]:
    return tuple(getattr(endpoint, "token_env", DEFAULT_TOKEN_ENV))
