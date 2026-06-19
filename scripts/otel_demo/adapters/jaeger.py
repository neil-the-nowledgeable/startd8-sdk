"""Jaeger query-API adapter for §4 trace coverage checks."""
from __future__ import annotations

import urllib.parse
from typing import Any, Iterable, Optional

from .http_json import get_json

# Services that usually carry cross-cutting span patterns in the OTel Demo.
_PROBE_SERVICES = (
    "checkout",
    "frontend",
    "cart",
    "product-catalog",
    "recommendation",
    "payment",
    "ad",
    "product-reviews",
    "kafka",
    "accounting",
    "flagd",
)


def list_services(base: str) -> list[str]:
    data = get_json(f"{base.rstrip('/')}/api/services")
    return list(data.get("data") or [])


def fetch_traces(
    base: str,
    service: str,
    *,
    lookback: str = "15m",
    limit: int = 20,
) -> list[dict[str, Any]]:
    svc = urllib.parse.quote(service, safe="")
    url = (
        f"{base.rstrip('/')}/api/traces"
        f"?service={svc}&limit={limit}&lookback={lookback}"
    )
    data = get_json(url)
    return list(data.get("data") or [])


def _iter_process_tags(trace: dict[str, Any]) -> Iterable[tuple[str, str]]:
    for proc in (trace.get("processes") or {}).values():
        for tag in proc.get("tags") or []:
            yield tag.get("key", ""), str(tag.get("value", ""))


def _iter_span_tags(trace: dict[str, Any]) -> Iterable[tuple[str, str, str]]:
    """Yield (operation, key, value) for each span tag."""
    for span in trace.get("spans") or []:
        op = span.get("operationName", "")
        for tag in span.get("tags") or []:
            yield op, tag.get("key", ""), str(tag.get("value", ""))


def _span_kind(span: dict[str, Any]) -> Optional[str]:
    for tag in span.get("tags") or []:
        if tag.get("key") == "span.kind":
            return str(tag.get("value", "")).upper()
    return None


def services_with_traces(base: str, *, lookback: str, min_count: int) -> dict[str, Any]:
    try:
        services = list_services(base)
    except Exception as exc:
        return {
            "observed": 0,
            "passed": False,
            "detail": f"jaeger services API error: {exc}",
            "observed_names": [],
            "error": str(exc),
        }
    with_traces = 0
    for svc in services[:30]:
        traces = fetch_traces(base, svc, lookback=lookback, limit=1)
        if traces:
            with_traces += 1
    return {
        "observed": with_traces,
        "passed": with_traces >= min_count,
        "detail": f"{with_traces} services returned traces (lookback={lookback})",
        "observed_names": services[:50],
    }


def distinct_process_tag(
    base: str,
    *,
    tag_key: str,
    lookback: str,
    min_count: int,
) -> dict[str, Any]:
    services = list_services(base)
    probe = [s for s in _PROBE_SERVICES if s in services]
    if not probe:
        probe = services[:10]
    values: set[str] = set()
    for svc in probe:
        for trace in fetch_traces(base, svc, lookback=lookback, limit=10):
            for k, v in _iter_process_tags(trace):
                if k == tag_key and v:
                    values.add(v)
    return {
        "observed": len(values),
        "passed": len(values) >= min_count,
        "detail": f"distinct {tag_key}={sorted(values)}",
        "observed_names": sorted(values),
    }


def span_tag_count(
    base: str,
    *,
    tag_key: str,
    lookback: str,
    min_count: int,
    tag_value: Optional[str] = None,
    tag_values: Optional[list[str]] = None,
) -> dict[str, Any]:
    services = list_services(base)
    probe = [s for s in _PROBE_SERVICES if s in services] or services[:10]
    matches = 0
    seen_values: set[str] = set()
    for svc in probe:
        for trace in fetch_traces(base, svc, lookback=lookback, limit=20):
            for _op, k, v in _iter_span_tags(trace):
                if k != tag_key:
                    continue
                if tag_value is not None and v != tag_value:
                    continue
                if tag_values is not None and v not in tag_values:
                    continue
                matches += 1
                seen_values.add(v)
                if matches >= min_count:
                    break
            if matches >= min_count:
                break
        if matches >= min_count:
            break
    return {
        "observed": matches,
        "passed": matches >= min_count,
        "detail": f"{matches} spans with {tag_key}"
        + (f"={tag_value}" if tag_value else "")
        + (f" in {tag_values}" if tag_values else ""),
        "observed_names": sorted(seen_values) if seen_values else [tag_key],
    }


def messaging_kafka_count(
    base: str,
    *,
    lookback: str,
    min_count: int,
    messaging_key: str = "messaging.system",
    messaging_value: str = "kafka",
) -> dict[str, Any]:
    services = list_services(base)
    probe = [s for s in _PROBE_SERVICES if s in services] or services[:10]
    matches = 0
    kinds_seen: set[str] = set()
    for svc in probe:
        for trace in fetch_traces(base, svc, lookback=lookback, limit=30):
            for span in trace.get("spans") or []:
                tags = {t.get("key"): str(t.get("value", "")) for t in span.get("tags") or []}
                if tags.get(messaging_key) != messaging_value:
                    continue
                kind = _span_kind(span) or tags.get("span.kind", "").upper()
                if kind in ("PRODUCER", "CONSUMER", "SPAN_KIND_PRODUCER", "SPAN_KIND_CONSUMER"):
                    matches += 1
                    kinds_seen.add(kind)
                elif tags.get(messaging_key) == messaging_value:
                    # Some SDKs omit span.kind but still stamp messaging.system.
                    matches += 1
                    kinds_seen.add("messaging.system")
                if matches >= min_count:
                    break
            if matches >= min_count:
                break
        if matches >= min_count:
            break
    return {
        "observed": matches,
        "passed": matches >= min_count,
        "detail": f"{matches} kafka messaging spans (kinds={sorted(kinds_seen)})",
        "observed_names": sorted({messaging_key, "messaging.destination.name"}),
    }
