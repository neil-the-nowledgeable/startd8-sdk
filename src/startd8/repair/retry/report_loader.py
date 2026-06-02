"""Load + extract cross-file violations from a prime-postmortem report (Inc 1, FR-2).

Accepts a ``prime-postmortem-report.json`` path or a run directory containing one,
and normalizes each failed feature's ``unresolvable_import`` semantic issues into
``RetryViolation`` records.

**Specifier-parse contract (R1-F1).** The specifier is the backtick-quoted token
immediately following ``imports`` in the structured message
(`` `<file>` imports `<specifier>` which resolves to neither … ``). A message from
which no specifier can be parsed is **not dropped** — it is returned with
``parse_ok=False`` so a downstream consumer can route it to a ``needs_regen``
worklist entry (never a silent loss, NFR-3).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional, Union

from ...logging_config import get_logger
from .models import RetryViolation

logger = get_logger(__name__)

_REPORT_NAME = "prime-postmortem-report.json"
# `<importer>` imports `<specifier>` which resolves to neither …
_SPECIFIER_RE = re.compile(r"imports\s+`([^`]+)`")
# v1 acts only on this category; others (duplicate_require, etc.) are ignored here.
_TARGET_CATEGORY = "unresolvable_import"


def _resolve_report(report_or_dir: Union[str, Path]) -> Path:
    """Resolve *report_or_dir* to a postmortem report file.

    A file path is used directly; a directory is searched for
    ``**/prime-postmortem-report.json`` (preferring a ``plan-ingestion`` match).
    """
    p = Path(report_or_dir)
    if p.is_file():
        return p
    if p.is_dir():
        candidates = sorted(p.rglob(_REPORT_NAME))
        if not candidates:
            raise FileNotFoundError(f"No {_REPORT_NAME} found under {p}")
        # Prefer a plan-ingestion location (the canonical run layout).
        for c in candidates:
            if "plan-ingestion" in c.parts:
                return c
        return candidates[0]
    raise FileNotFoundError(f"Report path does not exist: {p}")


def _parse_specifier(message: str) -> Optional[str]:
    """Return the imported specifier from a structured message, or None."""
    m = _SPECIFIER_RE.search(message or "")
    return m.group(1) if m else None


def load_violations(report_or_dir: Union[str, Path]) -> List[RetryViolation]:
    """Extract ``unresolvable_import`` violations from a postmortem report.

    Iterates failed features (``success is False``) and their
    ``disk_compliance.semantic_issues``; keeps only ``unresolvable_import`` issues.
    Unparseable messages are returned with ``parse_ok=False`` (R1-F1), never dropped.
    """
    report = _resolve_report(report_or_dir)
    data = json.loads(report.read_text(encoding="utf-8"))

    violations: List[RetryViolation] = []
    for feature in data.get("features", []):
        if feature.get("success") is not False:
            continue
        feature_id = feature.get("feature_id") or ""
        disk = feature.get("disk_compliance") or {}
        file_path = disk.get("file_path") or ""
        for issue in disk.get("semantic_issues") or []:
            if issue.get("category") != _TARGET_CATEGORY:
                continue
            message = issue.get("message") or ""
            specifier = _parse_specifier(message)
            if specifier is None:
                logger.warning(
                    "repair-retry: unparseable unresolvable_import message for %s "
                    "(routed to needs-regen, not dropped)",
                    feature_id,
                )
            violations.append(
                RetryViolation(
                    feature_id=feature_id,
                    file_path=file_path,
                    category=_TARGET_CATEGORY,
                    specifier=specifier or "",
                    message=message,
                    parse_ok=specifier is not None,
                )
            )
    return violations
