"""Shared urllib JSON helper for Tier 0 adapters."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

REQUEST_TIMEOUT = 15


def get_json(url: str, timeout: int = REQUEST_TIMEOUT) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def reachable(base: str, path: str = "") -> bool:
    try:
        get_json(f"{base.rstrip('/')}{path}")
        return True
    except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError):
        return False
