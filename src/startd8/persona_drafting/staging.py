# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Generic atomic JSON session store (FR-PD-2 — the ``ProposalStore`` shape, extracted).

A behavior-preserving generalization of ``stakeholder_panel.proposals.ProposalStore``: own subdir,
``mkstemp`` + atomic ``os.replace`` (``0600`` at rest), ``sort_keys``+``indent=2`` (diffable audit
trail), ``0700`` dir, a path-traversal guard on the session id, and session enumeration + GC. Generic
over the record type: a subclass sets ``SUBDIR`` / ``FILE_PREFIX`` / ``RECORD_CLS`` (any class with
``to_dict()`` and a ``from_dict()`` classmethod).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, ClassVar, List, Optional

from startd8.logging_config import get_logger

__all__ = ["safe_session_component", "JsonSessionStore"]

logger = get_logger(__name__)

_DEFAULT_KEEP = 50


def safe_session_component(session_id: str) -> str:
    """Reject a session id that could escape the store dir (path traversal)."""
    if (
        not session_id
        or "/" in session_id
        or "\\" in session_id
        or session_id in (".", "..")
    ):
        raise ValueError(f"unsafe session_id: {session_id!r}")
    return session_id


class JsonSessionStore:
    """Persist / load one session's records atomically. Subclass and set the three class attrs."""

    SUBDIR: ClassVar[Path] = Path(".startd8") / "persona-drafting" / "records"
    FILE_PREFIX: ClassVar[str] = "records-"
    RECORD_CLS: ClassVar[Any] = None  # must expose to_dict() / from_dict()

    def __init__(self, project_root: Path | str, session_id: str) -> None:
        self.session_id = safe_session_component(session_id)
        self.dir = Path(project_root).expanduser() / self.SUBDIR
        self.path = self.dir / f"{self.FILE_PREFIX}{self.session_id}.json"

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # pragma: no cover - non-POSIX / permission quirk
            pass

    def save(self, records: List[Any]) -> None:
        """Write the whole session atomically (``0600``, sorted, ``indent=2``)."""
        self._ensure_dir()
        payload = json.dumps(
            [r.to_dict() for r in records], sort_keys=True, indent=2, ensure_ascii=False
        )
        fd, tmp_name = tempfile.mkstemp(dir=str(self.dir), suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, self.path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:  # pragma: no cover
                pass
            raise

    def load(self) -> List[Any]:
        """Load the session's records (empty list if absent or unreadable)."""
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("unreadable session file %s: %s", self.path, exc)
            return []
        if not isinstance(raw, list):
            return []
        return [self.RECORD_CLS.from_dict(d) for d in raw if isinstance(d, dict)]

    # ── session enumeration + GC (classmethods so callers need no instance) ──
    @classmethod
    def _session_files(cls, project_root: Path | str) -> List[Path]:
        directory = Path(project_root).expanduser() / cls.SUBDIR
        if not directory.is_dir():
            return []
        return [p for p in directory.glob(f"{cls.FILE_PREFIX}*.json") if p.is_file()]

    @classmethod
    def session_ids(cls, project_root: Path | str) -> List[str]:
        files = sorted(
            cls._session_files(project_root),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return [p.name[len(cls.FILE_PREFIX) : -len(".json")] for p in files]

    @classmethod
    def latest_session(cls, project_root: Path | str) -> Optional[str]:
        ids = cls.session_ids(project_root)
        return ids[0] if ids else None

    @classmethod
    def gc(cls, project_root: Path | str, *, keep: int = _DEFAULT_KEEP) -> List[Path]:
        """Keep the *keep* most-recent session files, delete the rest. Returns deleted paths."""
        files = sorted(
            cls._session_files(project_root),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        deleted: List[Path] = []
        for stale in files[max(0, keep) :]:
            try:
                stale.unlink()
                deleted.append(stale)
            except OSError:  # pragma: no cover
                pass
        return deleted
