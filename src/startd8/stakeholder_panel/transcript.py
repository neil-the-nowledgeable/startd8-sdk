# Copyright 2026 Force Multiplier Labs
# SPDX-License-Identifier: LicenseRef-FSL-1.1-ALv2

"""Session transcript persistence (FR-12, Mottainai).

Panel Q&A is appended to ``.startd8/stakeholder-panel/<session_id>.json`` so it is auditable and
re-readable without re-spending. Each entry is a :class:`PanelAnswer` dict — which already carries
the ``brief_hash``+``roster_version`` that produced it (R2-F3), so an answer stays traceable after
the roster is edited.

Confidentiality is ``0600`` at rest; the directory is created ``0700``. Callers must add
``.startd8/stakeholder-panel/`` to ``.gitignore`` (the SDK's project scaffold already ignores
``.startd8/``). **Retention (R1-F5):** :func:`prune_sessions` keeps the N most-recent session files;
run it at session open to bound growth (this is the cleanup policy, not just at-rest perms).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import PanelAnswer

__all__ = ["TranscriptStore", "TRANSCRIPT_DIR", "prune_sessions"]

logger = get_logger(__name__)

TRANSCRIPT_DIR = Path(".startd8") / "stakeholder-panel"
_DEFAULT_KEEP_SESSIONS = 50


def _safe_session_component(session_id: str) -> str:
    """Reject a session_id that could escape the transcript dir (path-traversal guard)."""
    if (
        not session_id
        or "/" in session_id
        or "\\" in session_id
        or session_id in (".", "..")
    ):
        raise ValueError(f"unsafe session_id: {session_id!r}")
    return session_id


class TranscriptStore:
    """Append-and-load a single session's transcript under a project root."""

    def __init__(self, project_root: Path | str, session_id: str) -> None:
        self.session_id = _safe_session_component(session_id)
        self.dir = Path(project_root).expanduser() / TRANSCRIPT_DIR
        self.path = self.dir / f"{self.session_id}.json"

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # pragma: no cover - non-POSIX / permission quirk
            pass

    def append(self, answer: PanelAnswer) -> None:
        """Append one answer, rewriting the session file atomically with ``0600`` perms.

        The temp file is created via ``mkstemp`` (unique name, ``0600`` from birth — no
        world-readable window, no fixed-name collision between concurrent writers).
        """
        self._ensure_dir()
        entries = [a.to_dict() for a in self.load()]
        entries.append(answer.to_dict())
        payload = json.dumps(entries, indent=2, ensure_ascii=False)
        fd, tmp_name = tempfile.mkstemp(dir=str(self.dir), suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_name, self.path)
        except BaseException:
            # Never leave a stray temp behind on failure (disk-full, interrupt).
            try:
                os.unlink(tmp_name)
            except OSError:  # pragma: no cover
                pass
            raise

    def load(self) -> List[PanelAnswer]:
        """Load the session's answers (empty list if absent or unreadable)."""
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("unreadable transcript %s: %s", self.path, exc)
            return []
        if not isinstance(raw, list):
            return []
        return [PanelAnswer.from_dict(d) for d in raw if isinstance(d, dict)]


def prune_sessions(
    project_root: Path | str, *, keep: int = _DEFAULT_KEEP_SESSIONS
) -> List[Path]:
    """Retention policy (R1-F5): keep the *keep* most-recent session files, delete the rest.

    Returns the list of deleted paths. A no-op when at or under the cap. Idempotent and safe to call
    at session open.
    """
    directory = Path(project_root).expanduser() / TRANSCRIPT_DIR
    if not directory.is_dir():
        return []
    sessions = sorted(
        (p for p in directory.glob("*.json") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    deleted: List[Path] = []
    for stale in sessions[max(0, keep) :]:
        try:
            stale.unlink()
            deleted.append(stale)
        except OSError:  # pragma: no cover
            pass
    return deleted
