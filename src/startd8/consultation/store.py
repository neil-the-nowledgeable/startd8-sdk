"""Consultation session storage (M2.2 / FR-MMC-6, FR-MMC-13a).

Sessions live under ``<storage>/.startd8/consultations/<session-id>/`` (sibling to
``responses/`` and ``benchmarks/``), one ``session.json`` + a human ``summary.md`` per
session. Concurrency contract from the CRP:

* **Process-unique id (R2-S6 / FR-MMC-13a):** :func:`new_session_id` combines a sortable
  UTC timestamp with the pid and random bytes, so a CLI and a TUI starting in the same
  second cannot collide.
* **Exclusive creation (R2-S6):** :meth:`create_session_dir` uses ``mkdir(exist_ok=False)``
  and fails loud on a pre-existing id rather than silently overwriting.
* **Atomic write (R1-S6):** :meth:`save` writes ``session.json.tmp`` then ``os.replace``.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from ..logging_config import get_logger
from .models import ConsultationSession, TurnRole, TurnStatus

logger = get_logger(__name__)


class SessionCollisionError(RuntimeError):
    """Raised when a session id directory already exists (fail-loud, R2-S6)."""


def new_session_id() -> str:
    """Process-unique, lexicographically-sortable session id (FR-MMC-13a).

    Shape: ``<UTC ts>-<pid>-<rand>`` e.g. ``20260703T184455-40213-9f2a1c``. The timestamp
    prefix keeps ids sortable; the pid+random suffix makes them process-unique across the
    concurrent CLI+TUI writers.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{ts}-{os.getpid()}-{secrets.token_hex(3)}"


class ConsultationStore:
    """Filesystem store for consultation sessions."""

    def __init__(self, base_dir: str | Path = ".startd8") -> None:
        self.root = Path(base_dir) / "consultations"

    def session_dir(self, session_id: str) -> Path:
        return self.root / session_id

    def create_session_dir(self, session_id: str) -> Path:
        """Create the session directory **exclusively** — fail loud on collision."""
        d = self.session_dir(session_id)
        try:
            d.mkdir(parents=True, exist_ok=False)
        except FileExistsError as e:  # R2-S6: never clobber an existing session
            raise SessionCollisionError(
                f"consultation session id already exists: {session_id}"
            ) from e
        return d

    def save(self, session: ConsultationSession) -> Path:
        """Persist ``session.json`` (atomically) + ``summary.md``."""
        d = self.session_dir(session.id)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "session.json"
        tmp = d / "session.json.tmp"
        tmp.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        os.replace(tmp, path)  # atomic (R1-S6)
        (d / "summary.md").write_text(render_summary(session), encoding="utf-8")
        return path

    def load(self, session_id: str) -> ConsultationSession:
        path = self.session_dir(session_id) / "session.json"
        return ConsultationSession.model_validate_json(path.read_text(encoding="utf-8"))

    def list_sessions(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "session.json").exists())


def render_summary(session: ConsultationSession) -> str:
    """Render a human-readable ``summary.md`` for side-by-side reading (M2.2)."""
    lines = [
        f"# Consultation {session.id}",
        "",
        f"- **Created:** {session.created_at}",
        f"- **Updated:** {session.updated_at}",
        f"- **Models:** {', '.join(session.roster)}",
        f"- **Images:** {len(session.images)}"
        + (f" ({', '.join(i.mime_type for i in session.images)})" if session.images else ""),
        "",
        "## Prompt",
        "",
        session.prompt,
        "",
    ]
    for model_id in session.roster:
        turns = session.turns_by_model.get(model_id, [])
        status = session.latest_status(model_id)
        lines.append(f"## {model_id} — {status.value if status else 'untried'}")
        lines.append("")
        for turn in turns:
            if turn.role == TurnRole.user:
                imgs = f" [+{len(turn.images)} image(s)]" if turn.images else ""
                lines.append(f"**> user{imgs}:** {turn.text}")
            elif turn.status == TurnStatus.ok:
                usage = ""
                if turn.input_tokens is not None or turn.output_tokens is not None:
                    usage = f"  _(in={turn.input_tokens} out={turn.output_tokens} {turn.time_ms}ms)_"
                lines.append(f"**assistant:**{usage}")
                lines.append("")
                lines.append(turn.text)
            else:
                err = turn.error
                detail = f"{err.type}" + (f" [{err.code}]" if err and err.code else "") if err else ""
                lines.append(f"**assistant ({turn.status.value}):** {detail} — {err.message if err else ''}")
            lines.append("")
    return "\n".join(lines)
