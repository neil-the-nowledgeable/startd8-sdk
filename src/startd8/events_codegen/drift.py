"""Drift helpers for events overlay artifacts."""

from __future__ import annotations

import re
from typing import Optional

from .engine import render_events_artifacts

_KINDS = frozenset({"python-events-producer", "python-events-consumer"})
_KIND_RE = re.compile(r"#\s*startd8-artifact:\s*(\S+)")
_EVENTS_SHA_RE = re.compile(r"#\s*events-sha256:\s*([0-9a-f]{64})")
_SCHEMA_SHA_RE = re.compile(r"#\s*schema-sha256:\s*([0-9a-f]{64})")


def embedded_kind(text: str) -> Optional[str]:
    m = _KIND_RE.search(text or "")
    return m.group(1) if m else None


def is_owned_events_file(text: str) -> bool:
    t = text or ""
    kind = embedded_kind(t)
    return (
        kind in _KINDS
        and _EVENTS_SHA_RE.search(t) is not None
        and _SCHEMA_SHA_RE.search(t) is not None
    )


def events_file_in_sync(
    events_text: str,
    schema_text: str,
    rel_path: str,
    ondisk_text: str,
    *,
    messaging_backend: str = "aiokafka",
    package: str = "app",
) -> bool:
    if not is_owned_events_file(ondisk_text):
        return False
    try:
        expected = {
            rel: content
            for rel, content in render_events_artifacts(
                events_text,
                schema_text,
                messaging_backend=messaging_backend,
                package=package,
            )
        }
    except ValueError:
        return False
    norm = rel_path.replace("\\", "/")
    content = expected.get(norm)
    if content is None:
        return False
    return content == ondisk_text
