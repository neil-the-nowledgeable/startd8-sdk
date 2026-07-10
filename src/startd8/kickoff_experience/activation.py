"""Kickoff activation surface (roadmap Tier B) — turn the oracle's readiness/attention signal into a
portable **check gate** plus an append-only **activation ledger**.

Two capabilities, both pure reads over the single :class:`AgenticView` oracle ($0, deterministic):

1. :func:`evaluate_activation` → :class:`ActivationReport` — the "alert as a CLI gate". It evaluates
   the oracle payload against activation conditions (blocked fields, pending proposals, review
   backlog, readiness below target, no inputs) and yields an overall **severity** + **exit code**.
   It works with or without the Grafana/Mimir stack, so CI/cron can gate on kickoff readiness the
   same way ``polish check`` gates on style drift — the stack-based Grafana alert (via the
   ``kickoff.activation.*`` gauges) and this portable gate read the *same* conditions.

2. :class:`ActivationLedger` — an append-only JSONL audit trail of oracle-derived state
   **transitions** (readiness crossings, block/unblock, proposals applied, snapshot promotion):
   *how a project got ready*, not just where it stands. A row is appended only when the signal
   actually changes, so the ledger is a clean event stream, not a poll log.

The ledger is the ONLY writer here and only ever appends to ``.startd8/kickoff/activation-ledger.jsonl``
— it never touches kickoff inputs. Evaluation is read-only. Neither introduces LLM generation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logging_config import get_logger
from . import schemas

logger = get_logger(__name__)

ACTIVATION_SCHEMA = schemas.ACTIVATION
LEDGER_SCHEMA = schemas.ACTIVATION_LEDGER

# Activation-ledger row field names — the ONE definition the producer (`_signature`/`record`) and the
# consumers (momentum, retrospective) share, so the row contract can't drift silently across modules.
LR_READINESS = "readiness_percent"
LR_BLOCKED = "blocked"
LR_REVIEW = "review"
LR_BACKLOG = "backlog"
LR_OK = "ok"
LR_PROPOSALS = "proposals_pending"
LR_SNAPSHOT = "snapshot_status"
LR_NEXT_ACTION = "next_action_key"
LR_TS = "ts"

# Default readiness target below which the gate raises an attention condition. 100 = "fully ready".
DEFAULT_MIN_READINESS = 100

# Severity ordering (internal rank → the higher wins for the overall verdict). The rank IS the
# 0/1/2 severity code surfaced to metrics (see ``ActivationReport.severity_code``).
_SEV_OK = "ok"
_SEV_ATTENTION = "attention"
_SEV_BLOCKED = "blocked"
_SEV_RANK = {_SEV_OK: 0, _SEV_ATTENTION: 1, _SEV_BLOCKED: 2}

# Overall severity → process exit code. Mirrors cli_concierge's convention:
#   0 = ok/activated · 1 = attention (like drift) · 3 = blocked. (2 stays reserved for tool error.)
_SEV_EXIT = {_SEV_OK: 0, _SEV_ATTENTION: 1, _SEV_BLOCKED: 3}


@dataclass(frozen=True)
class ActivationCondition:
    """One evaluated activation condition (an 'alert' that may or may not be firing)."""

    key: str
    severity: str  # _SEV_* — the severity IF met
    met: bool
    title: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "severity": self.severity,
            "met": self.met,
            "title": self.title,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class ActivationReport:
    """The activation verdict for one project: which conditions fire + the overall severity."""

    project_root: str
    readiness_percent: Optional[int]
    conditions: Tuple[ActivationCondition, ...]

    @property
    def open(self) -> Tuple[ActivationCondition, ...]:
        """The conditions currently firing (met)."""
        return tuple(c for c in self.conditions if c.met)

    @property
    def overall(self) -> str:
        """Highest severity among firing conditions; ``ok`` when none fire."""
        sev = _SEV_OK
        for c in self.open:
            if _SEV_RANK[c.severity] > _SEV_RANK[sev]:
                sev = c.severity
        return sev

    @property
    def ready(self) -> bool:
        return self.overall == _SEV_OK

    @property
    def exit_code(self) -> int:
        return _SEV_EXIT[self.overall]

    @property
    def severity_code(self) -> int:
        """The 0=ok / 1=attention / 2=blocked code (for the ``kickoff.activation.severity`` gauge)."""
        return _SEV_RANK[self.overall]

    def to_dict(self) -> dict:
        return {
            "schema": ACTIVATION_SCHEMA,
            "project_root": self.project_root,
            "overall": self.overall,
            "ready": self.ready,
            "exit_code": self.exit_code,
            "readiness_percent": self.readiness_percent,
            "open_count": len(self.open),
            "open": [c.to_dict() for c in self.open],
            "conditions": [c.to_dict() for c in self.conditions],
        }


def evaluate_activation(
    status: Dict[str, Any],
    *,
    min_readiness: int = DEFAULT_MIN_READINESS,
) -> ActivationReport:
    """Evaluate the oracle ``status`` payload (from :func:`kickoff_status`) into an activation report.

    ``status`` is the ``startd8.kickoff.status.v1`` dict. Conditions degrade safely on absent stores
    (empty counts / no proposals ⇒ those conditions simply don't fire)."""
    counts = status.get("attention_counts") or {}
    readiness = status.get("readiness_percent")
    field_count = int(status.get("field_count", 0) or 0)
    proposals_pending = len(status.get("proposals") or [])
    blocked = int(counts.get("blocked", 0) or 0)
    review = int(counts.get("review", 0) or 0)

    conditions: List[ActivationCondition] = [
        ActivationCondition(
            key="no_inputs",
            severity=_SEV_ATTENTION,
            met=field_count == 0,
            title="No kickoff inputs captured yet",
            detail="Start with `startd8 kickoff` to capture your first inputs.",
        ),
        ActivationCondition(
            key="blocked_fields",
            severity=_SEV_BLOCKED,
            met=blocked > 0,
            title=f"{blocked} field(s) blocked",
            detail="Blocked fields cannot advance until resolved.",
        ),
        ActivationCondition(
            key="review_backlog",
            severity=_SEV_ATTENTION,
            met=review > 0,
            title=f"{review} field(s) awaiting review",
            detail="Confirm or revise fields flagged for review.",
        ),
        ActivationCondition(
            key="pending_proposals",
            severity=_SEV_ATTENTION,
            met=proposals_pending > 0,
            title=f"{proposals_pending} proposal(s) awaiting confirmation",
            detail="Review with `startd8 kickoff proposals`.",
        ),
        ActivationCondition(
            key="readiness_below_target",
            severity=_SEV_ATTENTION,
            met=readiness is not None and readiness < min_readiness,
            title=(
                f"Readiness {readiness}% below target {min_readiness}%"
                if readiness is not None
                else f"Readiness below target {min_readiness}%"
            ),
            detail="Capture the remaining fields to reach the readiness target.",
        ),
    ]
    return ActivationReport(
        project_root=str(status.get("project_root", "")),
        readiness_percent=readiness,
        conditions=tuple(conditions),
    )


# --- Activation ledger (append-only transition log) ---------------------------------------------

# The signature fields whose change constitutes a recordable state transition.
_SIGNATURE_KEYS = (
    LR_READINESS, LR_BLOCKED, LR_REVIEW, LR_BACKLOG, LR_OK, LR_PROPOSALS, LR_SNAPSHOT, LR_NEXT_ACTION,
)


def ledger_path(project_root: str | Path) -> Path:
    """Location of the append-only activation ledger for a project."""
    from .paths import KICKOFF, startd8_dir

    return startd8_dir(project_root) / KICKOFF / "activation-ledger.jsonl"


def _signature(status: Dict[str, Any]) -> Dict[str, Any]:
    """The oracle-derived state signature used for transition detection."""
    counts = status.get("attention_counts") or {}
    na = status.get("next_action") or {}
    return {
        LR_READINESS: status.get("readiness_percent"),
        LR_BLOCKED: int(counts.get("blocked", 0) or 0),
        LR_REVIEW: int(counts.get("review", 0) or 0),
        LR_BACKLOG: int(counts.get("backlog", 0) or 0),
        LR_OK: int(counts.get("ok", 0) or 0),
        LR_PROPOSALS: len(status.get("proposals") or []),
        LR_SNAPSHOT: status.get("snapshot_status"),
        LR_NEXT_ACTION: (na.get("key") or na.get("title")) if isinstance(na, dict) else None,
    }


def readiness_readings(entries: Any) -> List[int]:
    """The ordered readiness observations from ledger rows — the ONE ledger-series extraction both
    momentum (slope) and the retrospective (journey) consume, so the row is parsed in one place."""
    out: List[int] = []
    for e in entries or ():
        v = e.get(LR_READINESS) if isinstance(e, dict) else None
        if v is None:
            continue
        try:
            out.append(int(v))
        except (TypeError, ValueError):
            continue
    return out


@dataclass
class ActivationLedger:
    """Append-only JSONL ledger of oracle-derived state transitions for one project."""

    project_root: Path
    _path: Path = field(init=False)

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root)
        self._path = ledger_path(self.project_root)

    @property
    def path(self) -> Path:
        return self._path

    def entries(self) -> List[Dict[str, Any]]:
        """All ledger rows (malformed lines skipped). Empty when the ledger doesn't exist yet."""
        if not self._path.exists():
            return []
        out: List[Dict[str, Any]] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # pragma: no cover - tolerate a corrupt row
                logger.debug("skipping malformed activation-ledger row")
        return out

    def _last_signature(self) -> Optional[Dict[str, Any]]:
        entries = self.entries()
        if not entries:
            return None
        last = entries[-1]
        return {k: last.get(k) for k in _SIGNATURE_KEYS}

    def record(
        self, status: Dict[str, Any], *, now: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Append a transition row IFF the oracle signature changed since the last row.

        Returns the appended entry, or ``None`` when nothing changed (no duplicate rows). ``now`` is
        an ISO timestamp override for deterministic testing."""
        sig = _signature(status)
        prev = self._last_signature()
        if prev is not None and prev == sig:
            return None
        changed = (
            [k for k in _SIGNATURE_KEYS if prev.get(k) != sig.get(k)]
            if prev is not None
            else list(_SIGNATURE_KEYS)
        )
        ts = now or datetime.now(timezone.utc).isoformat()
        entry: Dict[str, Any] = {"schema": LEDGER_SCHEMA, "ts": ts, "changed": changed, **sig}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        return entry
