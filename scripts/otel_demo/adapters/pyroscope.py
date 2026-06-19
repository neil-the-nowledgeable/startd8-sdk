"""Pyroscope adapter for §2 profiles coverage (profile tier only)."""
from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any

from .http_json import get_json


def count_profile_apps(base: str, *, min_count: int) -> dict[str, Any]:
    """Best-effort: Pyroscope exposes /api/apps on recent releases."""
    root = base.rstrip("/")
    apps: list[str] = []
    detail = ""
    for path in ("/api/apps",):
        try:
            data = get_json(f"{root}{path}")
            if isinstance(data, dict):
                if "data" in data and isinstance(data["data"], list):
                    apps = [str(x) for x in data["data"]]
                elif "apps" in data:
                    apps = [str(x) for x in data["apps"]]
            elif isinstance(data, list):
                apps = [str(x) for x in data]
            if apps:
                break
        except (urllib.error.URLError, OSError, ValueError):
            continue
    if not apps:
        try:
            with urllib.request.urlopen(f"{root}/ready", timeout=10) as resp:
                if 200 <= resp.status < 300:
                    apps = ["ready"]
                    detail = "/ready returned 2xx (apps API unavailable)"
        except (urllib.error.URLError, OSError):
            detail = "pyroscope unreachable"
    count = len(apps)
    return {
        "observed": count,
        "passed": count >= min_count,
        "detail": detail or f"{count} profile apps",
        "observed_names": apps[:50],
    }
