"""Drift helpers for owned Alembic revision files (Tier-1 migration provider)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from .generator import (
    _SNAPSHOT_RE,
    _decode_snapshot,
    _find_revision_path,
    plan_migration,
    render_revision,
)

_ARTIFACT = "alembic-revision"
_KIND_RE = re.compile(r"#\s*startd8-artifact:\s*(\S+)")
_REVISION_RE = re.compile(r"^revision = ['\"](\d+)['\"]", re.M)
_DOWN_RE = re.compile(r"^down_revision = (.+)$", re.M)
_DOC_RE = re.compile(r'^"""([^"\n]+)', re.M)


def embedded_kind(text: str) -> Optional[str]:
    m = _KIND_RE.search(text or "")
    return m.group(1) if m else None


def is_owned_migration_file(text: str) -> bool:
    t = text or ""
    return embedded_kind(t) == _ARTIFACT and _SNAPSHOT_RE.search(t) is not None


def _parse_down_revision(raw: str) -> Optional[str]:
    value = raw.strip()
    if value == "None":
        return None
    return value.strip("'\"")


def rerender_revision(path: Path, versions_dir: Path) -> Optional[str]:
    """Re-render the revision at *path* from its embedded snapshot chain."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not is_owned_migration_file(text):
        return None
    snap = _SNAPSHOT_RE.search(text)
    rev_m = _REVISION_RE.search(text)
    down_m = _DOWN_RE.search(text)
    if snap is None or rev_m is None:
        return None
    current_text = _decode_snapshot(snap.group(1))
    revision_id = rev_m.group(1)
    down_revision = _parse_down_revision(down_m.group(1)) if down_m else None
    previous_text: Optional[str] = None
    if down_revision:
        prev_path = _find_revision_path(versions_dir, down_revision)
        if prev_path is None:
            return None
        prev_snap = _SNAPSHOT_RE.search(prev_path.read_text(encoding="utf-8"))
        if prev_snap is None:
            return None
        previous_text = _decode_snapshot(prev_snap.group(1))
    plan = plan_migration(current_text, previous_text)
    doc_m = _DOC_RE.search(text)
    message = doc_m.group(1).strip() if doc_m else "migration"
    return render_revision(
        revision_id=revision_id,
        down_revision=down_revision,
        message=message,
        plan=plan,
        current_text=current_text,
    )


def migration_revision_in_sync(path: Path, ondisk_text: str, versions_dir: Path) -> bool:
    expected = rerender_revision(path, versions_dir)
    if expected is None:
        return False
    return expected == ondisk_text
