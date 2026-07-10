"""Kickoff-facing agentic-session snapshot (FR-1 / FR-4 / FR-6b).

The presentation-neutral snapshot core (model + normalization + generic builder) was **promoted to
the agents layer** (`startd8.agents.session_snapshot`) so any :class:`AgenticSession` can snapshot
itself (roadmap Tier 3). This module re-exports those names for the kickoff import path (compat) and
adds the kickoff-specific policy the neutral layer deliberately leaves out:

- **Redaction** via :func:`startd8.fde.redaction.redact` — the SAME redactor the VIPP inbox uses
  (``vipp_seam.py:_warn_if_secret``) — injected into the neutral builder before any string is written
  or emitted to Loki (R1-F1). A planted secret must not survive to disk or to a log line.
- **On-disk persistence** at ``.startd8/kickoff/agentic-session.json`` (last session only; OQ-1) via
  temp-then-rename (an interrupted overwrite leaves the prior snapshot readable; R1-F5).
- **Full-transcript depth (FR-6b)**: the redacted turns are also emitted as structured JSON log lines
  so a Grafana Loki ``logs`` panel can serve the complete transcript; best-effort.

Nothing here writes on its own outside an explicit call at session end — the loop stays write-free.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Optional, Sequence

# The neutral core, re-exported so `from ...session_snapshot import AgenticSessionSnapshot` (etc.)
# keeps working for every existing kickoff consumer.
from ..agents.session_snapshot import (  # noqa: F401  (re-exported for the kickoff import path)
    SNAPSHOT_DISCLOSURE,
    SNAPSHOT_SCHEMA_VERSION,
    STOP_REASON_HINT,
    AgenticSessionSnapshot,
    SnapshotCost,
    SnapshotTurn,
    build_snapshot,
    normalize_messages,
    stop_reason_hint,
)
from ..fde.redaction import redact
from ..logging_config import get_logger

logger = get_logger(__name__)

# The dedicated logger name the FR-6b Loki `logs` panel selects on
# (`{job="startd8", logger="startd8.kickoff.transcript"}`). Kept as a module constant so the writer
# and the dashboard LogQL builder agree on one selector.
TRANSCRIPT_LOGGER_NAME = "startd8.kickoff.transcript"

def snapshot_path(project_root: str | os.PathLike[str]) -> Path:
    """Canonical snapshot location for *project_root* (last-session-only; OQ-1)."""
    from .paths import KICKOFF, startd8_dir

    return startd8_dir(project_root) / KICKOFF / "agentic-session.json"


def _redact(text: str) -> str:
    """Redact one string with the VIPP-parity redactor; returns the scrubbed text only."""
    return redact(text)[0] if text else text


def build_session_snapshot(
    *,
    messages: Sequence[dict],
    model: Optional[str],
    input_tokens: int,
    output_tokens: int,
    total_tokens: int,
    cost_usd: float,
    posture: str,
    project: str,
    session_id: str,
    generated_at: str,
    pending_proposal_ids: Sequence[str] = (),
    stop_reason: Optional[str] = None,
) -> AgenticSessionSnapshot:
    """Build a **redacted** kickoff snapshot — the neutral builder with the VIPP-parity redactor wired
    in, so every persisted string is scrubbed (R1-F1)."""
    return build_snapshot(
        messages=messages,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_usd=cost_usd,
        posture=posture,
        project=project,
        session_id=session_id,
        generated_at=generated_at,
        pending_proposal_ids=pending_proposal_ids,
        stop_reason=stop_reason,
        redactor=_redact,
    )


def write_snapshot(project_root: str | os.PathLike[str], snapshot: AgenticSessionSnapshot) -> Path:
    """Persist *snapshot* via temp-then-rename (R1-F5).

    An interrupted write never touches the real path — the prior snapshot stays readable and no
    partial ``agentic-session.json`` is left behind. The temp file is removed on any failure.
    """
    path = snapshot_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_json()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".agentic-session.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)  # atomic on POSIX; the reader sees old-or-new, never partial
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def emit_transcript_to_loki(snapshot: AgenticSessionSnapshot) -> int:
    """Emit each redacted turn as a structured JSON log line for the FR-6b Loki depth panel.

    Best-effort: returns the number of lines emitted; swallows any logging failure so it can never
    break session exit or block the snapshot write. Turns are already redacted (build-time), so Loki
    never receives a secret.
    """
    emitted = 0
    try:
        tlog = get_logger(TRANSCRIPT_LOGGER_NAME)
        for turn in snapshot.turns:
            tlog.info(
                json.dumps(
                    {
                        "event": "kickoff_transcript_turn",
                        "project": snapshot.project,
                        "session_id": snapshot.session_id,
                        "turn_index": turn.index,
                        "role": turn.role,
                        "text": turn.text,
                        "tool_calls": list(turn.tool_calls),
                        "tool_name": turn.tool_name,
                        "schema_version": snapshot.schema_version,
                    },
                    ensure_ascii=False,
                )
            )
            emitted += 1
    except Exception as exc:  # pragma: no cover - defensive; Loki emit is never load-bearing
        logger.debug("transcript Loki emit skipped: %s", exc)
    return emitted


# --------------------------------------------------------------------------- CLI adapter


def _posture_for_chat(chat: Any) -> str:
    """Mirror ``chat.py:cost_line()``'s posture tag from a KickoffChat-like object (duck-typed)."""
    if getattr(chat, "red_carpet", False):
        return "red-carpet · propose-only"
    if getattr(chat, "agentic", False) or getattr(chat, "buffer", None) is not None:
        return "concierge · propose-only"
    return "kickoff · read-only"


def persist_snapshot_for_chat(
    project_root: str | os.PathLike[str],
    chat: Any,
    *,
    session_id: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> Optional[Path]:
    """Build + write the snapshot for a finished chat, then emit its turns to Loki (FR-6b).

    Presence-gated (FR-1): a session that never produced a turn writes **no** file. Fully best-effort
    — any failure is swallowed so it can never break session exit (the caller has already done its
    inbox handoff; a snapshot hiccup must not undo that). Returns the written path or ``None``.
    """
    try:
        if session_id is None:
            import uuid

            session_id = uuid.uuid4().hex[:12]
        if generated_at is None:
            from datetime import datetime, timezone

            generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        session = getattr(chat, "session", None)
        if session is None:
            return None
        buffer = getattr(chat, "buffer", None)
        pending_ids = tuple(
            str(getattr(a, "id", "")) for a in (buffer.pending() if buffer is not None else ())
        )
        snap = build_session_snapshot(
            messages=list(getattr(session, "messages", []) or []),
            model=getattr(getattr(session, "agent", None), "model", None),
            input_tokens=getattr(session, "total_input_tokens", 0),
            output_tokens=getattr(session, "total_output_tokens", 0),
            total_tokens=getattr(session, "total_tokens", 0),
            cost_usd=getattr(session, "total_cost_usd", 0.0),
            posture=_posture_for_chat(chat),
            project=str(project_root),
            session_id=session_id,
            generated_at=generated_at,
            pending_proposal_ids=pending_ids,
            stop_reason=getattr(chat, "last_stop_reason", None),
        )
        if not snap.turns:  # nothing was said → presence-gated: no artifact
            return None
        path = write_snapshot(project_root, snap)
        emit_transcript_to_loki(snap)
        return path
    except Exception as exc:  # never break session exit on a snapshot hiccup
        logger.debug("session snapshot skipped: %s", exc)
        return None
