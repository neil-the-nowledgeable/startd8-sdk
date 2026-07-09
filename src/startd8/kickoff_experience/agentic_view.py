"""M2 — the agentic cockpit read-model (FR-3 / FR-10).

ONE deterministic, ``$0`` builder folds the three sources the cockpit mirrors — the kickoff
``KickoffState`` (Status), the FR-1 session snapshot (Assistant), and the existing VIPP proposal
inbox (Proposals) — into a single :class:`AgenticView`. The dashboard (M3) and any future CLI/TUI
view derive from this one oracle, so they cannot drift (parity, mirroring ``state.py``'s
single-derivation discipline).

Honesty contracts (never raise, never mis-parse):

- **Version contract (FR-3 / R1-F2):** a snapshot whose ``schema_version`` this build does not know
  degrades to ``snapshot_status = "unsupported_version"`` with ``snapshot = None`` — it is NOT parsed.
- **Malformed/unreadable (FR-10 / R1-F6):** a truncated or invalid ``agentic-session.json`` degrades
  to ``snapshot_status = "unavailable"`` — never a traceback, never a blank panel.
- **Absent (FR-10):** no snapshot / no proposals yield honest hint messages, not errors.

FR-7 confirm-command honesty lives here too: :func:`confirm_command` renders a real, copy-safe,
id-bound command and :func:`parse_confirm_command` is its inverse (the round-trip the dashboard test
asserts). The dashboard shows the command; it never acts (NR-2).
"""

from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

from ..logging_config import get_logger
from .session_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    AgenticSessionSnapshot,
    snapshot_path,
)

logger = get_logger(__name__)

# Snapshot presence/health states (FR-3 / FR-10). The dashboard maps each to an honest panel.
SNAPSHOT_ABSENT = "absent"  # no session yet
SNAPSHOT_PRESENT = "present"  # a valid, known-version snapshot
SNAPSHOT_UNAVAILABLE = "unavailable"  # present but malformed/unreadable
SNAPSHOT_UNSUPPORTED = "unsupported_version"  # present but a schema_version we do not know

# schema_versions this build can parse. Anything else degrades (does not parse) — FR-3.
_KNOWN_SNAPSHOT_VERSIONS = frozenset({SNAPSHOT_SCHEMA_VERSION})

# Machine-parseable, shell-comment annotation that binds a rendered confirm command to its proposal
# (FR-7). Lives in a trailing `# ...` comment so it never affects command execution.
_CONFIRM_MARKER = "startd8-proposal:"


# --------------------------------------------------------------------------- confirm command (FR-7)


def confirm_command(proposal_id: str, *, kind: str = "", value_path: Optional[str] = None) -> str:
    """Render the real, copy-safe, id-bound command to act on one inbox proposal (FR-7 / R1-F4).

    The VIPP inbox is adjudicated + applied at the **envelope** level, so the actionable command is
    the real two-step ``negotiate`` → ``apply --apply``. The specific proposal is bound via a
    shell-safe trailing annotation (``# startd8-proposal: id=… kind=… path=…``) so a copy-paste both
    runs correctly *and* is traceable to exactly this proposal. Any ``value_path`` (host-controlled,
    may contain spaces/quotes) is ``shlex``-escaped.
    """
    ann = f"{_CONFIRM_MARKER} id={shlex.quote(proposal_id)}"
    if kind:
        ann += f" kind={shlex.quote(kind)}"
    if value_path is not None:
        ann += f" path={shlex.quote(str(value_path))}"
    return f"startd8 vipp negotiate && startd8 vipp apply --apply --yes  # {ann}"


def parse_confirm_command(command: str) -> dict:
    """Inverse of :func:`confirm_command` — extract the bound ``{id, kind, path}`` (R1-F4 round-trip).

    Returns an empty dict if the annotation is absent. Reverses the ``shlex`` escaping, so a
    ``value_path`` with spaces/quotes survives the round-trip byte-for-byte.
    """
    idx = command.find(_CONFIRM_MARKER)
    if idx < 0:
        return {}
    annotation = command[idx + len(_CONFIRM_MARKER):]
    out: dict = {}
    for token in shlex.split(annotation):
        if token.startswith("id="):
            out["id"] = token[3:]
        elif token.startswith("kind="):
            out["kind"] = token[5:]
        elif token.startswith("path="):
            out["path"] = token[5:]
    return out


# --------------------------------------------------------------------------- models


@dataclass(frozen=True)
class ProposalRow:
    """One pending inbox proposal, normalized for the Proposals tab (FR-7)."""

    id: str
    kind: str
    target: str  # value_path / source_label / posture / kind — the human-meaningful target
    summary: str
    confirm_command: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "target": self.target,
            "summary": self.summary,
            "confirm_command": self.confirm_command,
        }


@dataclass(frozen=True)
class AgenticView:
    """The single cockpit read-model (FR-3). Everything the M3 tabs render derives from this."""

    project_root: str
    state: Any  # KickoffState | None (folded Status oracle; best-effort)
    snapshot: Optional[AgenticSessionSnapshot]
    snapshot_status: str
    proposals: Tuple[ProposalRow, ...]
    proposals_present: bool  # the inbox file was readable (independent of whether it has rows)

    # --- FR-10 honest empty/unavailable messaging -------------------------------------------------

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot is not None and self.snapshot_status == SNAPSHOT_PRESENT

    def assistant_message(self) -> Optional[str]:
        """The honest Assistant-tab hint when there is nothing to render (else ``None``)."""
        if self.snapshot_status == SNAPSHOT_ABSENT:
            return "No session yet — run `startd8 kickoff chat` to begin."
        if self.snapshot_status == SNAPSHOT_UNAVAILABLE:
            return "Snapshot unavailable — the session file is unreadable or malformed."
        if self.snapshot_status == SNAPSHOT_UNSUPPORTED:
            return (
                "Snapshot unavailable — written by a newer kickoff (unsupported snapshot version). "
                "Upgrade startd8 to view it."
            )
        return None

    def proposals_message(self) -> Optional[str]:
        """The honest Proposals-tab hint when there are no rows (else ``None``)."""
        if not self.proposals:
            return "No proposals awaiting confirmation."
        return None


# --------------------------------------------------------------------------- loaders


def _load_snapshot(project_root: Path) -> Tuple[Optional[AgenticSessionSnapshot], str]:
    """Load + version-gate the snapshot. Never raises (FR-3/FR-10)."""
    path = snapshot_path(project_root)
    if not path.is_file() or path.is_symlink():
        return None, SNAPSHOT_ABSENT
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # truncated / invalid JSON → honest unavailable
        return None, SNAPSHOT_UNAVAILABLE
    if not isinstance(data, dict):
        return None, SNAPSHOT_UNAVAILABLE
    try:
        version = int(data.get("schema_version"))
    except (TypeError, ValueError):
        return None, SNAPSHOT_UNAVAILABLE
    if version not in _KNOWN_SNAPSHOT_VERSIONS:
        return None, SNAPSHOT_UNSUPPORTED  # degrade, do NOT attempt to parse an unknown shape
    try:
        return AgenticSessionSnapshot.from_dict(data), SNAPSHOT_PRESENT
    except Exception:  # a known version that still fails to parse → unavailable, not a crash
        return None, SNAPSHOT_UNAVAILABLE


def _redact(text: str) -> str:
    from ..fde.redaction import redact

    return redact(text)[0] if text else text


def _proposal_target(params: dict, kind: str) -> str:
    for key in ("value_path", "source_label", "contract_path", "posture"):
        v = params.get(key)
        if v:
            return str(v)
    return kind


def _proposal_summary(kind: str, params: dict) -> str:
    if kind == "capture":
        return f"set {params.get('value_path', '?')} = {params.get('value', '')}".strip()
    if kind == "friction":
        return str(params.get("friction") or params.get("what_happened") or "log friction")
    if kind == "instantiate":
        return f"scaffold the kickoff package ({params.get('posture', 'default')})"
    if kind in ("schema", "brief", "manifest"):
        label = params.get("source_label") or params.get("contract_path") or kind
        return f"{kind}: {label}"
    return kind


def _load_proposals(project_root: Path) -> Tuple[Tuple[ProposalRow, ...], bool]:
    """Load pending proposals from the existing VIPP inbox (FR-2). Never raises."""
    inbox = project_root / ".startd8" / "vipp" / "proposals-inbox.json"
    if not inbox.is_file() or inbox.is_symlink():
        return (), False
    try:
        from ..vipp.models import ProposalEnvelope

        env = ProposalEnvelope.from_json(inbox.read_text(encoding="utf-8"))
    except Exception:  # malformed inbox → honest empty (present=False), never a traceback
        return (), False
    rows: List[ProposalRow] = []
    for p in env.proposals:
        params = dict(p.params or {})
        value_path = params.get("value_path")
        target = _redact(_proposal_target(params, p.kind))
        rows.append(
            ProposalRow(
                id=p.id,
                kind=p.kind,
                target=target,
                summary=_redact(_proposal_summary(p.kind, params)),
                confirm_command=confirm_command(p.id, kind=p.kind, value_path=value_path),
            )
        )
    return tuple(rows), True


def _load_state(project_root: Path) -> Any:
    """Best-effort fold of the KickoffState Status oracle. None on any absence (never raises)."""
    try:
        from .docs import live_schema_text, load_kickoff_docs
        from .state import build_kickoff_state

        docs = load_kickoff_docs(str(project_root))
        return build_kickoff_state(docs, live_schema_text=live_schema_text(str(project_root)))
    except Exception:  # pragma: no cover - Status degrades independently
        return None


def build_agentic_view(project_root: str | Path) -> AgenticView:
    """Fold KickoffState + FR-1 snapshot + FR-2 inbox into the one cockpit read-model (FR-3).

    Pure, deterministic, ``$0``. The single derivation point every rendered surface consumes.
    """
    root = Path(project_root)
    snapshot, status = _load_snapshot(root)
    proposals, present = _load_proposals(root)
    return AgenticView(
        project_root=str(root),
        state=_load_state(root),
        snapshot=snapshot,
        snapshot_status=status,
        proposals=proposals,
        proposals_present=present,
    )
