# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Host-side VIPP proposal-serialization seam (VIPP FR-15) — **additive, opt-in**.

Serializes the in-memory-by-design :class:`~startd8.kickoff_experience.proposals.ProposalBuffer` to a
confined ``.startd8/vipp/proposals-inbox.json`` so a separate, **out-of-process** VIPP can read it
(the file IS the trust boundary; VIPP OQ-11 resolved out-of-process-only). This module is purely
additive — it does **not** modify ``proposals.py`` — and is **opt-in**: it only runs when a VIPP
posting exists (``.startd8/vipp/`` dir) or ``STARTD8_VIPP`` is set, so a host with no VIPP is
**byte-identical-when-absent** (VIPP NR-7 / SOTTO, proven by a dict-equality test).

It does **not** import ``startd8.vipp`` (the dependency is one-way, ``vipp`` → ``kickoff_experience``;
FR-8) — the wire dict is built **by shape**, mirroring ``vipp.models.ProposalEnvelope.from_json``. A
parity test asserts the two shapes/protocol versions stay in lockstep.

Security (VIPP OQ-9/OQ-10, CRP R1):
- ``params`` persist **UNREDACTED** — they are the bytes the applier writes and round-trip-gates;
  redacting would corrupt ``schema``/``brief``/``manifest`` writes. A secret-shaped token in params
  is **WARN-logged** (defense-in-depth via ``fde.redaction``), never altered.
- The inbox is mode **0600**, **gitignored**, and **no-clobber-of-undrained** (a pending inbox is not
  overwritten — the on-disk analogue of the buffer's ``BufferFull`` reject-don't-evict, R3-S4).
- Reads are **symlink-rejecting** (``O_NOFOLLOW`` + realpath-within-root, R3-F7). Writes ride
  ``safe_write.apply_write_plan`` (the existing ``O_NOFOLLOW`` TOCTOU-closed confinement).
- ``envelope_seq`` is **monotonic** (persisted counter that survives inbox shred) so a stale
  disposition from one cycle cannot be applied against the next (FR-18).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..concierge.safe_write import (
    ACTION_NEW,
    ACTION_OVERWRITE,
    PlannedWrite,
    SafeWriteError,
    WriteResult,
    apply_write_plan,
    resolve_confined_root,
)
from ..logging_config import get_logger
from .proposals import ProposalBuffer

logger = get_logger(__name__)

# Must match ``vipp.models.PROTOCOL_VERSION`` (a parity test enforces this — the host cannot import
# vipp, so the constant is duplicated by shape, and the lockstep is guarded in CI).
PROTOCOL_VERSION = "1.0"
ENVELOPE_KIND = "vipp-proposal-envelope"

VIPP_DIR = ".startd8/vipp"
INBOX_NAME = "proposals-inbox.json"
SEQ_NAME = "inbox-seq"
GITIGNORE_NAME = ".gitignore"

# The key whitelist (Lesson L11-#41): serialize exactly these per-proposal fields — never a whole
# object dump. Equals ProposedAction's field set (and vipp.models.HOST_PROPOSAL_FIELDS).
_PROPOSAL_FIELDS = ("kind", "params", "id", "base_sha")

_TRUTHY = {"1", "true", "yes", "on"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _vipp_dir(root: Path) -> Path:
    return Path(root) / VIPP_DIR


def inbox_path(project_root: Any) -> Path:
    return _vipp_dir(project_root) / INBOX_NAME


def vipp_opted_in(project_root: Any) -> bool:
    """True iff this project has opted into VIPP (posting dir exists, or ``STARTD8_VIPP`` is set)."""
    if os.environ.get("STARTD8_VIPP", "").strip().lower() in _TRUTHY:
        return True
    return _vipp_dir(project_root).is_dir()


# --- confined read (symlink-rejecting, R3-F7) -----------------------------------------------------


def _read_confined(root: Path, name: str) -> Optional[bytes]:
    target = _vipp_dir(root) / name
    if not os.path.lexists(target):  # lstat — does not follow a final symlink
        return None
    if _vipp_dir(root).is_symlink() or os.path.islink(target):
        raise SafeWriteError(f"refusing to read through a symlink: {target}")
    real_root = os.path.realpath(root)
    if not (os.path.realpath(target) + os.sep).startswith(real_root + os.sep):
        raise SafeWriteError(f"path escapes confined root: {target}")
    fd = os.open(str(target), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        with os.fdopen(fd, "rb") as fh:
            return fh.read()
    except OSError as exc:  # e.g. ELOOP if it raced into a symlink
        raise SafeWriteError(f"refusing to read {target}: {exc}") from exc


# --- monotonic sequence (survives inbox shred) ----------------------------------------------------


def _next_seq(root: Path) -> int:
    raw = _read_confined(root, SEQ_NAME)
    current = 0
    if raw:
        try:
            current = int(raw.decode("utf-8").strip())
        except (ValueError, UnicodeDecodeError):
            current = 0
    nxt = current + 1
    apply_write_plan(
        root,
        [PlannedWrite(f"{VIPP_DIR}/{SEQ_NAME}", ACTION_OVERWRITE, str(nxt), None)],
        force=True,
    )
    return nxt


def _content_checksum(proposals: List[Dict[str, Any]]) -> str:
    blob = json.dumps(proposals, sort_keys=True).encode("utf-8")
    return f"sha256:{sha256(blob).hexdigest()}"


def _warn_if_secret(envelope: Dict[str, Any]) -> None:
    """Defense-in-depth: WARN (never mutate) if a secret-shaped token is in the inbox (OQ-10)."""
    try:
        from ..fde.redaction import redact
    except Exception:  # pragma: no cover
        return
    _, found = redact(json.dumps(envelope))
    if found:
        logger.warning(
            "VIPP inbox carries a secret-shaped token in proposal params (%s); persisted "
            "verbatim under 0600 (params must round-trip to the applier, OQ-10). Rotate if real.",
            ", ".join(sorted(set(found))),
        )


def _chmod_600(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover
        logger.debug("VIPP: could not chmod 0600 %s", path, exc_info=True)


def serialize_buffer(
    buffer: ProposalBuffer,
    project_root: Any,
    *,
    project_id: Optional[str] = None,
    force: bool = False,
) -> WriteResult:
    """Serialize ``buffer``'s pending proposals to the confined inbox. No-clobber-of-undrained.

    If a pending inbox already exists it is **not** overwritten (unless ``force``) — the on-disk
    analogue of the buffer's reject-don't-evict rule (R3-S4); the returned result reports it as
    skipped. On a fresh write the inbox is chmod 0600 and a ``.gitignore`` is ensured.
    """
    root = resolve_confined_root(project_root)
    ip = _vipp_dir(root) / INBOX_NAME
    if os.path.lexists(ip) and not force:
        return WriteResult(
            skipped=[
                {
                    "path": str(ip),
                    "reason": "undrained inbox — consume before re-serializing",
                }
            ]
        )

    proposals: List[Dict[str, Any]] = []
    for p in buffer.pending():
        d = {k: getattr(p, k, None) for k in _PROPOSAL_FIELDS}
        d["params"] = dict(
            d.get("params") or {}
        )  # copy; carried verbatim/unredacted (OQ-10)
        proposals.append(d)

    envelope = {
        "kind": ENVELOPE_KIND,
        "protocol_version": PROTOCOL_VERSION,
        "project_id": project_id or Path(root).name,
        "envelope_seq": _next_seq(root),
        "generated_at": _utcnow(),
        "content_checksum": _content_checksum(proposals),
        "proposals": proposals,
    }
    _warn_if_secret(envelope)

    result = apply_write_plan(
        root,
        [
            PlannedWrite(f"{VIPP_DIR}/{GITIGNORE_NAME}", ACTION_NEW, "*\n", None),
            PlannedWrite(
                f"{VIPP_DIR}/{INBOX_NAME}",
                ACTION_NEW if not force else ACTION_OVERWRITE,
                json.dumps(envelope, indent=2),
                None,
            ),
        ],
        force=force,
    )
    if any(INBOX_NAME in w for w in result.written):
        _chmod_600(ip)
    return result


def maybe_serialize_buffer(
    buffer: ProposalBuffer, project_root: Any, **kwargs: Any
) -> Optional[WriteResult]:
    """Opt-in gate (NR-7): serialize only when VIPP is opted in; else ``None`` (writes nothing)."""
    if not vipp_opted_in(project_root):
        return None
    return serialize_buffer(buffer, project_root, **kwargs)


def read_inbox(project_root: Any) -> Optional[Dict[str, Any]]:
    """Symlink-rejecting confined read of the inbox → parsed dict, or ``None`` if absent (R3-F7)."""
    root = resolve_confined_root(project_root)
    raw = _read_confined(root, INBOX_NAME)
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8"))


def shred_inbox(project_root: Any) -> bool:
    """Delete the inbox once consumed (FR-15 shred-on-completion). Returns True if one was removed."""
    root = resolve_confined_root(project_root)
    ip = _vipp_dir(root) / INBOX_NAME
    if os.path.islink(ip):
        raise SafeWriteError(f"refusing to shred through a symlink: {ip}")
    if ip.exists():
        ip.unlink()
        return True
    return False
