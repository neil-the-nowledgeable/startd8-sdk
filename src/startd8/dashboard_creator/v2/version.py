"""Grafana version gating for v2 dynamic dashboards (dynamic-dashboards M5, FR-11).

The shipped ``GrafanaClient.check_version`` parses only the **major** version — it cannot tell 13.0 from
13.1, the exact section-variables GA boundary (R1-F1/R1-S3). These helpers add **minor-aware** parsing
and the v2-support gate, read against the M0 baseline (``verified_on`` = 13.1.0). A target below 13.1
MUST be refused before a v2 board is provisioned — never ship a board it renders broken.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

#: The minimum version that supports dynamic dashboards + section variables (GA in 13.1; M0-verified).
MIN_V2_MAJOR = 13
MIN_V2_MINOR = 1

_VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?")


def parse_version(version_str: str) -> Optional[Tuple[int, int, int]]:
    """Parse a Grafana version string (e.g. ``"13.1.0"``, ``"v13.1"``) → ``(major, minor, patch)``.

    Returns ``None`` on an unparseable string (the caller degrades / refuses, never crashes).
    """
    if not isinstance(version_str, str):
        return None
    m = _VERSION_RE.match(version_str)
    if not m:
        return None
    major, minor, patch = m.group(1), m.group(2), m.group(3)
    return (int(major), int(minor), int(patch) if patch else 0)


def supports_v2_dynamic(version_str: str) -> bool:
    """True iff ``version_str`` is **≥ 13.1** (minor-aware) — the v2 dynamic-schema gate (FR-11)."""
    parsed = parse_version(version_str)
    if parsed is None:
        return False
    major, minor, _patch = parsed
    return (major, minor) >= (MIN_V2_MAJOR, MIN_V2_MINOR)


def version_gate_reason(version_str: str) -> Optional[str]:
    """``None`` if the target supports v2, else a concise, actionable refusal reason (FR-11)."""
    if supports_v2_dynamic(version_str):
        return None
    return (
        f"Grafana {version_str!r} does not support v2 dynamic dashboards — requires "
        f"≥ {MIN_V2_MAJOR}.{MIN_V2_MINOR} (dynamic dashboards + section variables GA). "
        "Upgrade the target, or emit a classic dashboard instead."
    )
