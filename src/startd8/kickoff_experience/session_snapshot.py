"""M1 — Durable agentic-session snapshot (FR-1 / FR-4 / FR-6b).

The agentic kickoff chats (`kickoff chat` / `concierge-chat` / `red-carpet`) run an
:class:`~startd8.agents.agentic.AgenticSession` whose transcript + cost live only in memory. This
module gives that session a **durable, dashboard-consumable snapshot** so the agentic Workbook
cockpit (M3) can *mirror* it read-only.

Contract (source of the requirements: ``AGENTIC_WORKBOOK_REQUIREMENTS.md`` FR-1/FR-4/FR-6b):

- **Deterministic artifact** at ``.startd8/kickoff/agentic-session.json`` (last session only; OQ-1).
- **``schema_version``** on every snapshot so the M2 read-model can degrade on drift (FR-3).
- **Turns**: ordered ``(role, text, tool-call NAME)`` — never free-text tool *arguments* (FR-1).
- **Redaction**: every persisted string passes through :func:`startd8.fde.redaction.redact` — the
  SAME redactor the VIPP inbox uses (``vipp_seam.py:_warn_if_secret``) — *before* it is written or
  emitted to Loki (R1-F1). A planted secret must not survive to disk or to a log line.
- **Overwrite/durability**: temp-then-rename (an interrupted overwrite leaves the prior snapshot
  readable); concurrent sessions against one root are last-writer-wins (R1-F5).
- **Full-transcript depth (FR-6b)**: the redacted turns are *also* emitted as structured JSON log
  lines via :func:`startd8.logging_config.get_logger` so a Grafana Loki ``logs`` panel can serve the
  complete transcript on demand. Best-effort; a logging failure never breaks the snapshot write.

Nothing here writes on its own outside an explicit call at session end — the loop stays write-free.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from ..fde.redaction import redact
from ..logging_config import get_logger

logger = get_logger(__name__)

# The dedicated logger name the FR-6b Loki `logs` panel selects on
# (`{job="startd8", logger="startd8.kickoff.transcript"}`). Kept as a module constant so the writer
# and the dashboard LogQL builder (M3) agree on one selector.
TRANSCRIPT_LOGGER_NAME = "startd8.kickoff.transcript"

# Bump when the on-disk shape changes incompatibly. The M2 read-model degrades (never raises) on any
# value it does not recognize (FR-3 version contract).
SNAPSHOT_SCHEMA_VERSION = 1

# Standing disclosure carried on every rendered surface (FR-4): the cockpit mirrors a snapshot, it is
# not a live agent.
SNAPSHOT_DISCLOSURE = "snapshot — not a live agent"

_SNAPSHOT_RELPATH = (".startd8", "kickoff", "agentic-session.json")


def snapshot_path(project_root: str | os.PathLike[str]) -> Path:
    """Canonical snapshot location for *project_root* (last-session-only; OQ-1)."""
    return Path(project_root).joinpath(*_SNAPSHOT_RELPATH)


# --------------------------------------------------------------------------- models


@dataclass(frozen=True)
class SnapshotTurn:
    """One normalized transcript turn. ``text`` is already redacted at construction of the snapshot.

    ``tool_calls`` carries tool **names** only (FR-1 — no free-text arguments). ``tool_name`` is the
    producing tool for a tool-result turn (``role == "tool"``) when it can be resolved.
    """

    index: int
    role: str  # "user" | "assistant" | "tool"
    text: str = ""
    tool_calls: Tuple[str, ...] = ()
    tool_name: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {"index": self.index, "role": self.role, "text": self.text}
        if self.tool_calls:
            d["tool_calls"] = list(self.tool_calls)
        if self.tool_name:
            d["tool_name"] = self.tool_name
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SnapshotTurn":
        return cls(
            index=int(d["index"]),
            role=str(d["role"]),
            text=str(d.get("text", "")),
            tool_calls=tuple(d.get("tool_calls", ()) or ()),
            tool_name=(str(d["tool_name"]) if d.get("tool_name") else None),
        )


@dataclass(frozen=True)
class SnapshotCost:
    """Per-session cost, mirroring ``chat.py:cost_line()``'s inputs."""

    model: Optional[str]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": self.cost_usd,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SnapshotCost":
        return cls(
            model=(str(d["model"]) if d.get("model") else None),
            input_tokens=int(d.get("input_tokens", 0)),
            output_tokens=int(d.get("output_tokens", 0)),
            total_tokens=int(d.get("total_tokens", 0)),
            cost_usd=float(d.get("cost_usd", 0.0)),
        )


@dataclass(frozen=True)
class AgenticSessionSnapshot:
    """The durable, dashboard-consumable session snapshot (FR-1)."""

    schema_version: int
    generated_at: str
    project: str
    session_id: str
    posture: str
    turns: Tuple[SnapshotTurn, ...]
    cost: SnapshotCost
    pending_proposal_ids: Tuple[str, ...] = ()
    disclosure: str = SNAPSHOT_DISCLOSURE
    # Why the loop stopped last (AgenticResult.stop_reason): completed | max_turns | repeated_calls |
    # budget | context_overflow | stream_error. Surfaced so the cockpit can explain a non-"completed"
    # stop (e.g. a budget cap) instead of leaving the user guessing (Tier-1 #4).
    stop_reason: Optional[str] = None

    @property
    def turn_count(self) -> int:
        """Number of assistant turns (the model's replies) — the ``turns=`` in the cost line."""
        return sum(1 for t in self.turns if t.role == "assistant")

    def tool_call_counts(self) -> "dict[str, int]":
        """Per-tool call tallies across the session (for the 'session at a glance' summary, Tier-1 #3)."""
        counts: dict[str, int] = {}
        for turn in self.turns:
            for name in turn.tool_calls:
                counts[name] = counts.get(name, 0) + 1
        return counts

    def at_a_glance(self) -> str:
        """A deterministic one-line session summary ($0) — far more scannable than the raw transcript.

        e.g. "5 replies · survey ×2, assess ×1 · 3 proposals pending · cost ≈$0.0031 · stopped: budget".
        """
        parts = [f"{self.turn_count} repl" + ("y" if self.turn_count == 1 else "ies")]
        tools = self.tool_call_counts()
        if tools:
            parts.append(", ".join(f"{k} ×{v}" for k, v in sorted(tools.items())))
        if self.pending_proposal_ids:
            n = len(self.pending_proposal_ids)
            parts.append(f"{n} proposal" + ("" if n == 1 else "s") + " pending")
        parts.append(f"cost ≈${self.cost.cost_usd:.4f}")
        if self.stop_reason and self.stop_reason != "completed":
            parts.append(f"stopped: {self.stop_reason}")
        return " · ".join(parts)

    def cost_line(self) -> str:
        """The FR-4 per-session cost line, matching ``chat.py:cost_line()``'s shape."""
        return (
            f"[{self.posture}] turns={self.turn_count} "
            f"tokens={self.cost.total_tokens} cost≈${self.cost.cost_usd:.4f}"
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at,
            "project": self.project,
            "session_id": self.session_id,
            "posture": self.posture,
            "disclosure": self.disclosure,
            "stop_reason": self.stop_reason,
            "cost": self.cost.to_dict(),
            "pending_proposal_ids": list(self.pending_proposal_ids),
            "turns": [t.to_dict() for t in self.turns],
        }

    def to_json(self) -> str:
        # Deterministic bytes: sorted keys + fixed indent so a frozen fixture is byte-stable across
        # runs (feeds the M4 audience byte-diff).
        return json.dumps(self.to_dict(), indent=2, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_dict(cls, d: dict) -> "AgenticSessionSnapshot":
        return cls(
            schema_version=int(d["schema_version"]),
            generated_at=str(d.get("generated_at", "")),
            project=str(d.get("project", "")),
            session_id=str(d.get("session_id", "")),
            posture=str(d.get("posture", "")),
            turns=tuple(SnapshotTurn.from_dict(t) for t in d.get("turns", []) or []),
            cost=SnapshotCost.from_dict(d.get("cost", {}) or {}),
            pending_proposal_ids=tuple(d.get("pending_proposal_ids", ()) or ()),
            disclosure=str(d.get("disclosure", SNAPSHOT_DISCLOSURE)),
            stop_reason=(str(d["stop_reason"]) if d.get("stop_reason") else None),
        )


# --------------------------------------------------------------------------- transcript normalization


def _stringify(content: Any) -> str:
    """Flatten a message ``content`` (str | list-of-blocks | other) to display text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                elif "content" in block:
                    parts.append(_stringify(block["content"]))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(p for p in parts if p)
    return str(content)


def normalize_messages(messages: Sequence[dict]) -> List[SnapshotTurn]:
    """Normalize an :class:`AgenticSession`'s provider-dialect ``messages`` into ordered turns.

    Handles both the Anthropic dialect (assistant content = list of ``text``/``tool_use`` blocks;
    tool results = ``user`` messages with ``tool_result`` blocks) and the OpenAI dialect (assistant
    ``tool_calls`` + ``role: tool`` results). Tool-call **names** are kept; arguments are dropped
    (FR-1). ``text`` is NOT redacted here — redaction happens once when the snapshot is built.
    """
    turns: List[SnapshotTurn] = []
    id_to_name: dict = {}
    idx = 0

    def _push(role: str, text: str = "", tool_calls: Tuple[str, ...] = (), tool_name: Optional[str] = None) -> None:
        nonlocal idx
        turns.append(SnapshotTurn(index=idx, role=role, text=text, tool_calls=tool_calls, tool_name=tool_name))
        idx += 1

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role == "assistant":
            names: List[str] = []
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        name = str(block.get("name", ""))
                        names.append(name)
                        if block.get("id"):
                            id_to_name[block["id"]] = name
            for tc in msg.get("tool_calls", []) or []:  # OpenAI dialect
                fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                name = str(fn.get("name", ""))
                names.append(name)
                if isinstance(tc, dict) and tc.get("id"):
                    id_to_name[tc["id"]] = name
            _push("assistant", _stringify(content), tuple(n for n in names if n))
        elif role == "tool":  # OpenAI tool result
            _push("tool", _stringify(content), tool_name=None)
        elif role == "user":
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        name = id_to_name.get(block.get("tool_use_id"))
                        _push("tool", _stringify(block.get("content")), tool_name=name)
                    else:
                        _push("user", _stringify([block] if isinstance(block, dict) else block))
            else:
                _push("user", _stringify(content))
    return turns


def _redact(text: str) -> str:
    """Redact one string with the VIPP-parity redactor; returns the scrubbed text only."""
    return redact(text)[0] if text else text


# --------------------------------------------------------------------------- build + write


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
    """Build a redacted snapshot from a session's raw state. Every persisted string is redacted."""
    raw_turns = normalize_messages(messages)
    redacted_turns = tuple(
        SnapshotTurn(
            index=t.index,
            role=t.role,
            text=_redact(t.text),
            tool_calls=t.tool_calls,  # names are an enum, not free text
            tool_name=t.tool_name,
        )
        for t in raw_turns
    )
    return AgenticSessionSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        generated_at=generated_at,
        project=_redact(project),
        session_id=session_id,
        posture=posture,
        turns=redacted_turns,
        cost=SnapshotCost(
            model=model,
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            total_tokens=int(total_tokens),
            cost_usd=float(cost_usd),
        ),
        pending_proposal_ids=tuple(pending_proposal_ids),
        stop_reason=stop_reason,
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
