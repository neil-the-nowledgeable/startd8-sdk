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
from . import schemas
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
    readiness: Any = None  # ReadinessView | None (cascade readiness; best-effort)
    next_action: Any = None  # NextAction | None — the single recommended next step (Tier-1 #1)
    # Convergence M1 — the state that only the classic Workbook surfaced, folded so AgenticView is the
    # single oracle every surface derives from (best-effort; None on absence).
    panel_answers: Any = None  # latest stakeholder-panel run answers (list[dict]) | None
    pipeline: Any = None  # {staged, inbox, dispositions} panel→bridge→VIPP funnel | None
    roster: Any = None  # stakeholder roster (personas) | None
    # Convergence Tier-D — the activation-ledger transition history, folded so momentum (readiness
    # slope) can be derived from the SAME oracle (best-effort; () on absence).
    ledger_entries: Tuple[dict, ...] = ()

    # --- FR-10 honest empty/unavailable messaging -------------------------------------------------

    @property
    def has_snapshot(self) -> bool:
        return self.snapshot is not None and self.snapshot_status == SNAPSHOT_PRESENT

    def readiness_percent(self) -> Optional[int]:
        """Field-level readiness as a whole percent (ok / total), from the folded state (Tier-1 #2).

        Uses the always-available field attention counts rather than the cascade score, so a stat
        renders even before the $0 cascade is assessable. ``None`` when there are no fields yet."""
        state = self.state
        if state is None:
            return None
        counts = state.attention_counts  # {ok, review, blocked, backlog}
        total = sum(counts.values())
        if total == 0:
            return None
        return round(100 * counts.get("ok", 0) / total)

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

    # --- convergence M1: compact summaries of the folded classic-Workbook state -------------------

    def pipeline_summary(self) -> Optional[str]:
        """One-line panel→bridge→VIPP funnel summary, or ``None`` when there's no pipeline activity."""
        p = self.pipeline
        if not p:
            return None
        parts = []
        staged = len(p.get("staged", []) or [])
        if staged:
            parts.append(f"{staged} staged")
        inbox = p.get("inbox", {}) or {}
        if inbox.get("present"):
            parts.append(f"{inbox.get('count', 0)} in VIPP inbox")
        disp = p.get("dispositions", {}) or {}
        if disp.get("present"):
            c = disp.get("counts", {}) or {}
            parts.append(
                f"dispositions {c.get('ACCEPT', 0)} accept · "
                f"{c.get('REJECT', 0)} reject · {c.get('COUNTER', 0)} counter"
            )
        return " · ".join(parts) if parts else None

    # --- convergence Tier-D: close-the-loop momentum + leverage -----------------------------------

    def momentum(self) -> Any:
        """Readiness slope (rising/stalled/falling) from the folded activation ledger (Tier-D)."""
        from .momentum import readiness_trend

        return readiness_trend(self.ledger_entries)

    def leverage(self) -> Tuple[Any, ...]:
        """The not-ok field classes ranked by how many fields resolving each would clear (Tier-D)."""
        from .momentum import leverage_groups

        return leverage_groups(self.state)

    def leverage_nudge(self) -> Optional[str]:
        """One-line highest-leverage next-batch nudge + momentum framing, or ``None`` (Tier-D)."""
        from .momentum import leverage_nudge

        return leverage_nudge(self.state, self.momentum())

    def stakeholder_summary(self) -> Optional[str]:
        """One-line stakeholder summary (roster size + latest-run answer count), or ``None``."""
        parts = []
        n = _roster_size(self.roster)
        if n:
            parts.append(f"{n} persona" + ("" if n == 1 else "s"))
        if self.panel_answers:
            parts.append(f"{len(self.panel_answers)} answers (latest run)")
        return " · ".join(parts) if parts else None

    def to_dict(self) -> dict:
        """A single machine-readable snapshot of the whole oracle — the platform-API surface.

        Everything the Grafana/terminal/readout surfaces render, as one JSON-serializable dict, so a
        tool/agent/CI can read "where does this project stand" from the same oracle instead of
        re-deriving it. Read-only, ``$0``, deterministic."""
        counts = dict(self.state.attention_counts) if self.state is not None else {}
        d: dict = {
            "schema": schemas.STATUS,
            "project_root": self.project_root,
            "readiness_percent": self.readiness_percent(),
            "attention_counts": counts,
            "field_count": sum(counts.values()),
            "next_action": self.next_action.to_dict() if self.next_action is not None else None,
            "snapshot_status": self.snapshot_status,
            "has_snapshot": self.has_snapshot,
            "snapshot": self.snapshot.to_dict() if self.has_snapshot else None,
            "at_a_glance": self.snapshot.at_a_glance() if self.has_snapshot else None,
            "cost_line": self.snapshot.cost_line() if self.has_snapshot else None,
            "proposals": [r.to_dict() for r in self.proposals],
            "proposals_present": self.proposals_present,
            "pipeline": self.pipeline,  # plain dict (staged/inbox/dispositions) or None
            "pipeline_summary": self.pipeline_summary(),
            "panel_answers": self.panel_answers,  # list[dict] (JSON-native) or None
            "roster_size": _roster_size(self.roster),
            "stakeholder_summary": self.stakeholder_summary(),
            # Tier-D close-the-loop: momentum (readiness slope) + leverage (highest-leverage batch).
            "momentum": self.momentum().to_dict(),
            "leverage": [g.to_dict() for g in self.leverage()],
            "leverage_nudge": self.leverage_nudge(),
            "hints": {  # honest empty/unavailable messaging (FR-10)
                "assistant": self.assistant_message(),
                "proposals": self.proposals_message(),
            },
        }
        return d


# --------------------------------------------------------------------------- loaders


def _roster_size(roster: Any) -> int:
    """Defensive count of personas in a roster object (shape-agnostic)."""
    if roster is None:
        return 0
    for attr in ("personas", "roster", "stakeholders"):
        v = getattr(roster, attr, None)
        if v is not None:
            try:
                return len(v)
            except TypeError:
                pass
    try:
        return len(roster)
    except TypeError:
        return 0


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


def _load_readiness(project_root: Path) -> Any:
    """Best-effort cascade readiness (feeds the Tier-1 #1 next-action). None on any absence."""
    try:
        from .readiness import build_readiness

        return build_readiness(project_root)
    except Exception:  # pragma: no cover - readiness degrades independently
        return None


def _compute_next_action(state: Any, readiness: Any) -> Any:
    """The single deterministic recommendation (Tier-1 #1) — the same oracle `field_states` uses."""
    if state is None:
        return None
    try:
        from .ranking import next_action

        return next_action(state, readiness)
    except Exception:  # pragma: no cover
        return None


def _load_ledger_entries(project_root: Path) -> Tuple[dict, ...]:
    """Best-effort read of the Tier-B activation ledger (feeds Tier-D momentum). () on any absence."""
    try:
        from .activation import ActivationLedger

        return tuple(ActivationLedger(project_root).entries())
    except Exception:  # pragma: no cover - momentum degrades independently
        return ()


def build_agentic_view(project_root: str | Path) -> AgenticView:
    """Fold KickoffState + FR-1 snapshot + FR-2 inbox into the one cockpit read-model (FR-3).

    Pure, deterministic, ``$0``. The single derivation point every rendered surface consumes.
    """
    root = Path(project_root)
    snapshot, status = _load_snapshot(root)
    proposals, present = _load_proposals(root)
    state = _load_state(root)
    readiness = _load_readiness(root)
    # Convergence M1 — fold the stakeholder/pipeline/roster state the classic Workbook surfaced, from
    # the shared loader home, so this one oracle is a superset of both boards (best-effort, never raises).
    panel_answers = pipeline = roster = None
    try:
        from .workbook_sources import load_panel_run, load_pipeline_state, load_roster

        panel_answers = load_panel_run(root)
        pipeline = load_pipeline_state(root)
        roster = load_roster(root)
    except Exception:  # pragma: no cover - the classic-state fold degrades independently
        pass
    return AgenticView(
        project_root=str(root),
        state=state,
        snapshot=snapshot,
        snapshot_status=status,
        proposals=proposals,
        proposals_present=present,
        readiness=readiness,
        next_action=_compute_next_action(state, readiness),
        panel_answers=panel_answers,
        pipeline=pipeline,
        roster=roster,
        ledger_entries=_load_ledger_entries(root),
    )


def kickoff_status(project_root: str | Path) -> dict:
    """The MCP/CLI-agnostic machine-readable kickoff project status — the oracle as an API.

    One callable behind three front doors (``kickoff status --json``, ``kickoff readout --format json``,
    and the ``startd8_kickoff_status`` MCP tool) so they can't drift. Read-only, ``$0``, never raises
    (the oracle degrades every source independently)."""
    return build_agentic_view(project_root).to_dict()
