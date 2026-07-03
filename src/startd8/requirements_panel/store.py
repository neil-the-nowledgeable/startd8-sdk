# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Out-of-band staging for elicited requirement candidates (FR-RP-8).

Mirrors ``stakeholder_panel.proposals.ProposalStore``'s proven shape (R1-S5 on the sibling feature):
own subdir, atomic ``mkstemp`` + ``os.replace``, ``sort_keys``+``indent=2`` (diffable audit trail),
``0700`` dir at rest, session GC, and a path-traversal guard on the session id. Staged candidates hold
LLM-drafted prose tied to project internals, so the same at-rest posture applies.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import List, Optional

from startd8.logging_config import get_logger
from startd8.requirements_panel.models import RequirementCandidate

__all__ = ["CANDIDATES_DIR", "CandidateStore", "latest_session", "session_ids"]

logger = get_logger(__name__)

CANDIDATES_DIR = Path(".startd8") / "requirements-panel" / "candidates"
_FILE_PREFIX = "candidates-"


def _safe_session_component(session_id: str) -> str:
    if (
        not session_id
        or "/" in session_id
        or "\\" in session_id
        or session_id in (".", "..")
    ):
        raise ValueError(f"unsafe session_id: {session_id!r}")
    return session_id


class CandidateStore:
    """Persist / load one elicitation session's staged candidates."""

    def __init__(self, project_root: Path | str, session_id: str) -> None:
        self.session_id = _safe_session_component(session_id)
        self.dir = Path(project_root).expanduser() / CANDIDATES_DIR
        self.path = self.dir / f"{_FILE_PREFIX}{self.session_id}.json"

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # pragma: no cover - non-POSIX / permission quirk
            pass

    def save(self, candidates: List[RequirementCandidate]) -> None:
        """Write the whole session atomically (``0600``, sorted, ``indent=2``)."""
        self._ensure_dir()
        payload = json.dumps(
            [c.to_dict() for c in candidates],
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
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

    def load(self) -> List[RequirementCandidate]:
        """Load the session's candidates (empty list if absent or unreadable)."""
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("unreadable candidates file %s: %s", self.path, exc)
            return []
        if not isinstance(raw, list):
            return []
        return [RequirementCandidate.from_dict(d) for d in raw if isinstance(d, dict)]


def _session_files(project_root: Path | str) -> List[Path]:
    directory = Path(project_root).expanduser() / CANDIDATES_DIR
    if not directory.is_dir():
        return []
    return [p for p in directory.glob(f"{_FILE_PREFIX}*.json") if p.is_file()]


def session_ids(project_root: Path | str) -> List[str]:
    files = sorted(
        _session_files(project_root), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return [p.name[len(_FILE_PREFIX) : -len(".json")] for p in files]


def latest_session(project_root: Path | str) -> Optional[str]:
    ids = session_ids(project_root)
    return ids[0] if ids else None
