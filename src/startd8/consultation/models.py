"""Consultation session schema (M2 / FR-MMC-6).

A ``ConsultationSession`` is a **new artifact kind** — it does not reuse or extend
``AgentResponse`` (NR-8). It carries the prompt, persist-safe image references (no bytes,
FR-MMC-6a), the roster, and an independent per-model conversation thread.

Design points from the CRP:

* **Per-turn state (R1-S5):** each ``Turn`` has a ``status`` enum
  (``pending|ok|failed|skipped-non-vision``), so "failed this turn but has prior turns"
  is distinguishable from "never succeeded".
* **Structured error (R2-S8):** a failed turn stores a ``TurnError`` (type + code +
  message), not a flattened string, so retry / cost / history logic can branch on code.
* **Persist-safe images (R1-S4 / FR-MMC-6a):** :class:`SessionImageRef` has no bytes —
  a session JSON never contains base64.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from ..agents.multimodal import ImageRef


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TurnRole(str, Enum):
    user = "user"
    assistant = "assistant"


class TurnStatus(str, Enum):
    pending = "pending"
    ok = "ok"
    failed = "failed"
    skipped_non_vision = "skipped-non-vision"


class TurnError(BaseModel):
    """Structured provider error (R2-S8)."""

    type: str
    code: Optional[str] = None
    message: str = ""


class SessionImageRef(BaseModel):
    """Persist-safe image reference — hash + mime + path, **no bytes** (FR-MMC-6a)."""

    sha256: str
    mime_type: str
    source_path: Optional[str] = None
    size_bytes: Optional[int] = None

    @classmethod
    def from_ref(cls, ref: ImageRef) -> "SessionImageRef":
        return cls(
            sha256=ref.sha256,
            mime_type=ref.mime_type,
            source_path=ref.source_path,
            size_bytes=ref.size_bytes,
        )


class Turn(BaseModel):
    """One turn in a per-model thread (a user prompt or an assistant answer)."""

    role: TurnRole
    text: str = ""
    images: list[SessionImageRef] = Field(default_factory=list)
    status: TurnStatus = TurnStatus.ok
    error: Optional[TurnError] = None
    # Cost/usage signal recorded per assistant turn (M2.5 / R1-S9).
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    time_ms: Optional[int] = None
    created_at: str = Field(default_factory=_utcnow_iso)


class ConsultationSession(BaseModel):
    """A parallel multi-model consultation with independent per-model threads."""

    id: str
    prompt: str
    images: list[SessionImageRef] = Field(default_factory=list)
    roster: list[str] = Field(default_factory=list)
    turns_by_model: dict[str, list[Turn]] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_utcnow_iso)
    updated_at: str = Field(default_factory=_utcnow_iso)

    # ── convenience accessors (used by the engine, retry, and the comparison view) ──
    def latest_status(self, model_id: str) -> Optional[TurnStatus]:
        """Status of the most recent *assistant* turn for a model (``None`` if untried)."""
        for turn in reversed(self.turns_by_model.get(model_id, [])):
            if turn.role == TurnRole.assistant:
                return turn.status
        return None

    def failed_models(self) -> list[str]:
        """Roster models whose last assistant turn failed (retry targets, FR-MMC-11)."""
        return [m for m in self.roster if self.latest_status(m) == TurnStatus.failed]

    def last_user_prompt(self, model_id: str) -> Optional[str]:
        """The most recent user prompt sent to a model (for retrying that same turn)."""
        for turn in reversed(self.turns_by_model.get(model_id, [])):
            if turn.role == TurnRole.user:
                return turn.text
        return None

    def valid_history(self, model_id: str) -> list[Turn]:
        """Prior turns safe to replay: user turns and *ok* assistant turns only (R1-S8).

        Excludes failed/skipped assistant turns so a retried thread never replays a
        malformed history (e.g. an empty-assistant turn) to the provider.
        """
        history: list[Turn] = []
        pending_user: Optional[Turn] = None
        for turn in self.turns_by_model.get(model_id, []):
            if turn.role == TurnRole.user:
                pending_user = turn
            elif turn.status == TurnStatus.ok:
                if pending_user is not None:
                    history.append(pending_user)
                    pending_user = None
                history.append(turn)
            else:
                # failed/skipped assistant → drop its paired user from replay
                pending_user = None
        return history
