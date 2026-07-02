# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Out-of-band staging for drafted recommendations (FR-KIR-7, OQ-KIR-1/2).

The strict kickoff-input schemas hold **only a domain-level ``provenance_default``** and reject unknown
keys, so per-field ``estimate``/``authored`` status cannot live in the domain YAML. Drafts therefore
stage here — ``.startd8/stakeholder-panel/proposals/proposals-<session>.json`` — as the *sole* per-field
audit trail. Design points:

* **Own subdir.** Lives under ``proposals/`` so the transcript store's non-recursive ``*.json`` glob
  (and its ``prune_sessions``) never touches a proposals file, and vice-versa.
* **Deterministic serialization (R2-S4).** ``sort_keys=True`` + ``indent=2`` so the file diffs cleanly
  in git — it is the audit trail, so diffability is a hard requirement.
* **``0600`` at rest** via ``mkstemp`` + atomic ``os.replace`` (parity with the transcript store).
* **GC (R2-S3).** :func:`gc_stale_proposals` keeps the N most-recent files so sessions don't leak.
* **Provisioning independence (R1-F1).** Nothing here is read by the kickoff pre-flight score — that
  reads the in-file ``provenance_default`` only. This is an audit trail, not a scoring input.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from startd8.logging_config import get_logger
from startd8.stakeholder_panel.models import Recommendation

__all__ = [
    "PROPOSALS_DIR",
    "ProposalStore",
    "latest_session",
    "session_ids",
    "gc_stale_proposals",
]

logger = get_logger(__name__)

PROPOSALS_DIR = Path(".startd8") / "stakeholder-panel" / "proposals"
_FILE_PREFIX = "proposals-"
_DEFAULT_KEEP = 50


def _safe_session_component(session_id: str) -> str:
    if (
        not session_id
        or "/" in session_id
        or "\\" in session_id
        or session_id in (".", "..")
    ):
        raise ValueError(f"unsafe session_id: {session_id!r}")
    return session_id


class ProposalStore:
    """Persist / load / re-disposition one session's staged recommendations."""

    def __init__(self, project_root: Path | str, session_id: str) -> None:
        self.session_id = _safe_session_component(session_id)
        self.dir = Path(project_root).expanduser() / PROPOSALS_DIR
        self.path = self.dir / f"{_FILE_PREFIX}{self.session_id}.json"

    def _ensure_dir(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.dir, 0o700)
        except OSError:  # pragma: no cover - non-POSIX / permission quirk
            pass

    def save(self, recommendations: List[Recommendation]) -> None:
        """Write the whole session's recommendations atomically (``0600``, sorted, ``indent=2``)."""
        self._ensure_dir()
        payload = json.dumps(
            [r.to_dict() for r in recommendations],
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

    def load(self) -> List[Recommendation]:
        """Load the session's recommendations (empty list if absent or unreadable)."""
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("unreadable proposals file %s: %s", self.path, exc)
            return []
        if not isinstance(raw, list):
            return []
        return [Recommendation.from_dict(d) for d in raw if isinstance(d, dict)]

    def get(self, domain: str, value_path: str) -> Optional[Recommendation]:
        for rec in self.load():
            if rec.domain == domain and rec.value_path == value_path:
                return rec
        return None

    def update_disposition(
        self, domain: str, value_path: str, disposition: str
    ) -> bool:
        """Re-disposition one staged field (draft→approved/rejected/invalid). Returns True if found.

        The audit trail must not desync from an ``approve`` (R1-S4): the CLI calls this after a
        successful splice so the staging file reflects the promoted state.
        """
        return self.update_dispositions({(domain, value_path): disposition}) == 1

    def update_dispositions(self, updates: Dict[tuple, str]) -> int:
        """Batch-re-disposition many fields in a **single** load+save. Returns the count matched.

        ``approve --all`` promotes N fields; doing one file rewrite per field is O(N²) I/O on the
        audit trail. Keyed by ``(domain, value_path)`` → new disposition; unknown keys are ignored.
        """
        import dataclasses

        if not updates:
            return 0
        matched = 0
        out: List[Recommendation] = []
        for rec in self.load():
            new = updates.get((rec.domain, rec.value_path))
            if new is not None:
                out.append(dataclasses.replace(rec, disposition=new))
                matched += 1
            else:
                out.append(rec)
        if matched:
            self.save(out)
        return matched


def _session_files(project_root: Path | str) -> List[Path]:
    directory = Path(project_root).expanduser() / PROPOSALS_DIR
    if not directory.is_dir():
        return []
    return [p for p in directory.glob(f"{_FILE_PREFIX}*.json") if p.is_file()]


def session_ids(project_root: Path | str) -> List[str]:
    """All staged session ids, most-recent first (for the ambiguous ``--session`` check, R1-F2)."""
    files = sorted(
        _session_files(project_root), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return [p.name[len(_FILE_PREFIX) : -len(".json")] for p in files]


def latest_session(project_root: Path | str) -> Optional[str]:
    """The session id of the most-recently-modified proposals file, or ``None`` (R1-F2 default).

    Used by ``panel approve``/``review`` to resolve ``--session`` when unspecified.
    """
    files = sorted(
        _session_files(project_root), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not files:
        return None
    name = files[0].name  # proposals-<session>.json
    return name[len(_FILE_PREFIX) : -len(".json")]


def gc_stale_proposals(
    project_root: Path | str, *, keep: int = _DEFAULT_KEEP
) -> List[Path]:
    """Keep the *keep* most-recent proposals files, delete the rest (R2-S3). Returns deleted paths."""
    files = sorted(
        _session_files(project_root), key=lambda p: p.stat().st_mtime, reverse=True
    )
    deleted: List[Path] = []
    for stale in files[max(0, keep) :]:
        try:
            stale.unlink()
            deleted.append(stale)
        except OSError:  # pragma: no cover
            pass
    return deleted
