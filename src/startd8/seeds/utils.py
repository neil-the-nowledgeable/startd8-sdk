"""Shared seed utilities."""

from __future__ import annotations

from typing import Any

__all__ = ["KNOWN_GENERATION_PROFILES", "is_omitted", "safe_onboarding"]

# REQ-GPC-200: canonical set of generation profile values from ContextCore.
# Used for validation — unknown profiles default to "full" behavior with a warning.
KNOWN_GENERATION_PROFILES = frozenset({
    "source", "monitoring", "operator", "sponsor",
    "practitioner", "observability", "full",
})


def is_omitted(value: Any) -> bool:
    """Return True if value is a ContextCore profile-omitted marker.

    ContextCore replaces omitted onboarding sections with
    ``{"_omitted": "profile=<name>"}`` under non-full generation profiles.
    Consumers must detect these markers to avoid treating them as real data.
    """
    return isinstance(value, dict) and "_omitted" in value


def safe_onboarding(value: Any) -> Any:
    """Return *value* unless it is a profile-omitted marker, then ``None``.

    Use this when extracting onboarding fields into the pipeline context.
    Returning ``None`` activates existing fallback heuristics (LOC-based
    defaults, complexity-based calibration) rather than letting a marker
    dict silently pass ``isinstance(val, dict)`` guards downstream.
    """
    return None if is_omitted(value) else value
