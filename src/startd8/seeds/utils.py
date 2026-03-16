"""Shared seed utilities."""

from __future__ import annotations

from typing import Any

__all__ = ["is_omitted"]


def is_omitted(value: Any) -> bool:
    """Return True if value is a ContextCore profile-omitted marker.

    ContextCore replaces omitted onboarding sections with
    ``{"_omitted": "profile=<name>"}`` under non-full generation profiles.
    Consumers must detect these markers to avoid treating them as real data.
    """
    return isinstance(value, dict) and "_omitted" in value
