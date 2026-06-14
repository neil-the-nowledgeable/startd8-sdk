# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Fail-open redaction middleware for tracking telemetry (FR-19 / CRP R1-F2).

ContextCore task spans and agent insights can carry free text, evidence refs, and error strings
that may contain secrets or absolute home paths. This module wraps the existing prose redactor
(:func:`startd8.fde.redaction.redact`) so every tracking-emission path scrubs its payload before
it leaves the process.

Design (CRP R1-F2):
- **Fail-open.** If redaction raises, the offending field is *dropped* (replaced with a marker),
  never propagated raw and never raised into the caller — a redaction failure must not stall or
  fail a benchmark cell (consistent with FR-25 non-blocking).
- **Home-path scrubbing.** The base ``redact()`` covers 7 secret patterns; tracking telemetry adds
  absolute ``/Users/<name>/`` and ``/home/<name>/`` paths (evidence refs, exception strings) as a
  bypass path enumerated in FR-19.
- Covers the four enumerated bypass paths: ``fail_task(reason=...)`` free text, ``insight.evidence[]``
  refs, raw exception/``error`` strings, and span-event payloads.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from startd8.fde.redaction import redact as _redact_prose
from startd8.logging_config import get_logger

logger = get_logger(__name__)

# Absolute home paths leak the operator's username and machine layout. Scrub to the basename.
_HOME_PATH = re.compile(r"(?:/Users|/home)/[^/\s'\"]+/")
_DROPPED = "«REDACTION-FAILED:dropped»"


def redact_text(value: Optional[str]) -> Optional[str]:
    """Redact secrets + home paths from a single string. Fail-open: returns the drop marker on error.

    ``None`` passes through unchanged so callers can forward optional fields directly.
    """
    if value is None:
        return None
    try:
        redacted, _manifest = _redact_prose(str(value))
        redacted = _HOME_PATH.sub("…/", redacted)
        return redacted
    except Exception as exc:  # fail-open: drop the field, never raise into the emitter
        logger.warning("tracking redaction failed; dropping field (%s)", type(exc).__name__)
        return _DROPPED


def redact_attrs(attrs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Redact every string value in a flat attribute/event-payload dict (span-event bypass path).

    Non-string values pass through; nested dicts/lists are redacted recursively. Per-field
    fail-open: one bad field is dropped, the rest survive.
    """
    out: Dict[str, Any] = {}
    if not attrs:
        return out
    for key, val in attrs.items():
        try:
            if isinstance(val, str):
                out[key] = redact_text(val)
            elif isinstance(val, dict):
                out[key] = redact_attrs(val)
            elif isinstance(val, (list, tuple)):
                out[key] = [redact_text(v) if isinstance(v, str) else v for v in val]
            else:
                out[key] = val
        except Exception as exc:  # belt-and-suspenders: never let one key sink the dict
            logger.warning("tracking redaction failed on key %r; dropping (%s)", key, type(exc).__name__)
            out[key] = _DROPPED
    return out


def redact_evidence(evidence: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Redact a list of evidence dicts (``{type, ref, description?, query?}``).

    ``ref``/``description``/``query`` are the fields that carry absolute paths or pasted secrets;
    ``type`` is a controlled vocabulary and is left intact.
    """
    out: List[Dict[str, Any]] = []
    if not evidence:
        return out
    for item in evidence:
        if not isinstance(item, dict):
            continue
        red = dict(item)
        for field in ("ref", "description", "query"):
            if field in red and isinstance(red[field], str):
                red[field] = redact_text(red[field])
        out.append(red)
    return out
