"""Prometheus query-API adapter for §4 metrics coverage checks."""
from __future__ import annotations

import urllib.parse
from typing import Any

from .http_json import get_json


def list_metric_names(base: str) -> list[str]:
    data = get_json(f"{base.rstrip('/')}/api/v1/label/__name__/values")
    return list(data.get("data") or [])


def count_matching_patterns(
    base: str,
    patterns: list[str],
    *,
    min_count: int,
) -> dict[str, Any]:
    names = list_metric_names(base)
    matched: list[str] = []
    for pat in patterns:
        matched.extend(n for n in names if pat in n)
    matched = sorted(set(matched))
    count = len(matched)
    return {
        "observed": count,
        "passed": count >= min_count,
        "detail": f"{count} series names matching {patterns}",
        "observed_names": matched[:100],
    }


def instant_query_count(base: str, promql: str) -> int:
    q = urllib.parse.quote(promql, safe="")
    data = get_json(f"{base.rstrip('/')}/api/v1/query?query={q}")
    result = data.get("data", {}).get("result") or []
    return len(result)
