"""Presentation-neutral agentic-session snapshot core (roadmap Tier 3 promotion).

Any :class:`~startd8.agents.agentic.AgenticSession` — kickoff concierge, multi-model consultation,
future Prime sessions — can serialize itself into a durable, dashboard-consumable
:class:`AgenticSessionSnapshot` via this one layer (see ``AgenticSession.to_snapshot``). It owns the
neutral model + transcript normalization + the generic builder; **redaction is dependency-injected**
(a ``redactor`` callable) so this layer stays free of any product-specific policy (the kickoff layer
passes ``fde.redaction.redact``; other surfaces pass their own or none).

Layering: this module imports only stdlib — never ``kickoff_experience`` / ``fde`` — so
``agents`` → (neutral snapshot) has no cycle. ``kickoff_experience.session_snapshot`` re-exports these
names (compat) and adds the kickoff-specific bits (redaction, Loki emit, on-disk persistence).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, Sequence, Tuple

# Bump when the on-disk shape changes incompatibly. Read-models degrade (never raise) on any value
# they do not recognize (the FR-3 version contract).
SNAPSHOT_SCHEMA_VERSION = 1

# Standing disclosure carried on every rendered surface: a snapshot mirror is not a live agent.
SNAPSHOT_DISCLOSURE = "snapshot — not a live agent"

# Canonical, presentation-neutral explanation of a non-"completed" stop (mirrors AgenticResult's
# stop_reason vocabulary in agents/agentic.py). ONE source so every surface explains a stop identically.
STOP_REASON_HINT = {
    "budget": "stopped at the cost/token budget cap — raise `--max-cost` / `--max-total-tokens`, "
    "or continue in a new `kickoff chat` session",
    "max_turns": "hit the turn limit — continue in a new `kickoff chat` session",
    "repeated_calls": "the assistant was repeating a tool call and stopped — try rephrasing",
    "context_overflow": "the conversation outgrew the context window even after compaction",
    "stream_error": "ended on a stream error — the transcript may be incomplete",
}


def stop_reason_hint(reason: Optional[str]) -> Optional[str]:
    """Human explanation for a non-"completed" ``stop_reason`` (``None`` when it completed cleanly)."""
    if not reason or reason == "completed":
        return None
    return STOP_REASON_HINT.get(reason, f"stopped: {reason}")


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
    # budget | context_overflow | stream_error. Surfaced so a cockpit can explain a non-"completed"
    # stop (e.g. a budget cap) instead of leaving the user guessing.
    stop_reason: Optional[str] = None

    @property
    def turn_count(self) -> int:
        """Number of assistant turns (the model's replies) — the ``turns=`` in the cost line."""
        return sum(1 for t in self.turns if t.role == "assistant")

    def tool_call_counts(self) -> "dict[str, int]":
        """Per-tool call tallies across the session (for the 'session at a glance' summary)."""
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
        # Deterministic bytes: sorted keys + fixed indent so a frozen fixture is byte-stable across runs.
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


# --------------------------------------------------------------------------- builder (redactor-injected)


def build_snapshot(
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
    redactor: Optional[Callable[[str], str]] = None,
) -> AgenticSessionSnapshot:
    """Build a snapshot from a session's raw state. Every persisted string passes through *redactor*
    (a ``str -> str`` scrubber) — pass one for surfaces that persist untrusted transcript text; the
    default is identity (no redaction)."""
    red = redactor or (lambda s: s)
    raw_turns = normalize_messages(messages)
    scrubbed_turns = tuple(
        SnapshotTurn(
            index=t.index,
            role=t.role,
            text=red(t.text),
            tool_calls=t.tool_calls,  # names are an enum, not free text
            tool_name=t.tool_name,
        )
        for t in raw_turns
    )
    return AgenticSessionSnapshot(
        schema_version=SNAPSHOT_SCHEMA_VERSION,
        generated_at=generated_at,
        project=red(project),
        session_id=session_id,
        posture=posture,
        turns=scrubbed_turns,
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
