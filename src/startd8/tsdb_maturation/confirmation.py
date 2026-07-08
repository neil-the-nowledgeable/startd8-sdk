"""M2.5 — Identity confirmation gate (FR-4 / R1-F7 / R1-S6).

The load-bearing safeguard between inference (M2) and promotion (M4): a **wrong inferred
identity key silently overwrites data on backfill** (no runtime tripwire — the generated
importer is last-writer-wins), and the correlated-columns fixture proves structural inference
alone can pick a coincidental key. So an inferred key MUST be **human-confirmed** and the
confirmation **recorded as a committed marker** before promotion.

Modeled on the kickoff ``confirmed.yaml`` pattern (:mod:`startd8.concierge.confirmation`): an
additive, committed YAML ledger, keyed by metric, holding the confirmed identity. Absent ledger
⇒ nothing confirmed ⇒ promotion refused.

Acceptance (R1-S6):
  * promote without a recorded confirmation → refused (:class:`ConfirmationRequired`);
  * with a confirmation for the current key → allowed;
  * re-promote after the inferred key **changed** → re-confirmation required (the stored key no
    longer matches → :attr:`ConfirmationStatus.STALE`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Mapping, Optional, Sequence

import yaml

from startd8.logging_config import get_logger

from .infer import InferenceResult

logger = get_logger(__name__)

#: Committed ledger, OUTSIDE any ``inputs/`` glob so specimen/wireframe scanners never match it.
#: Version-controlled beside the schema it gates.
LEDGER_REL = "docs/tsdb-maturation/confirmed.yaml"
LEDGER_SCHEMA = "tsdb.confirmed.v1"


class ConfirmationError(RuntimeError):
    """A confirmation could not be recorded (e.g. empty identity)."""


class ConfirmationRequired(RuntimeError):
    """Promotion was attempted without a matching recorded confirmation — the hard gate."""


class ConfirmationStatus(str, Enum):
    """The gate's verdict for a metric's currently-inferred identity key."""

    CONFIRMED = "confirmed"      # a recorded confirmation matches the current key → promotable
    UNCONFIRMED = "unconfirmed"  # no record for this metric → needs first confirmation
    STALE = "stale"              # a record exists but the key CHANGED → needs re-confirmation


@dataclass(frozen=True)
class ConfirmationRecord:
    """One committed confirmation: the human-blessed identity for a metric's table."""

    metric: str
    entity: str
    identity: tuple[str, ...]  # emitted identity field names (sorted, stable)
    confirmed_at: str          # ISO date (YYYY-MM-DD)
    schema_sha256: Optional[str] = None  # audit binding to the exact confirmed schema

    def to_dict(self) -> dict:
        d = {
            "entity": self.entity,
            "identity": list(self.identity),
            "confirmed_at": self.confirmed_at,
        }
        if self.schema_sha256:
            d["schema_sha256"] = self.schema_sha256
        return d

    @classmethod
    def from_dict(cls, metric: str, data: Mapping[str, object]) -> "ConfirmationRecord":
        return cls(
            metric=metric,
            entity=str(data.get("entity", "")),
            identity=tuple(data.get("identity") or ()),  # type: ignore[arg-type]
            confirmed_at=str(data.get("confirmed_at", "")),
            schema_sha256=data.get("schema_sha256"),  # type: ignore[arg-type]
        )


def _normalize_identity(identity: Sequence[str]) -> tuple[str, ...]:
    """Order-insensitive identity comparison — a composite key is a *set* of columns."""
    return tuple(sorted(identity))


# --------------------------------------------------------------------------- #
# Ledger IO (tolerant: absent/malformed ⇒ empty, never raises).                 #
# --------------------------------------------------------------------------- #
def _ledger_path(project_root: str | Path) -> Path:
    return Path(project_root) / LEDGER_REL


def load_ledger(project_root: str | Path) -> dict[str, ConfirmationRecord]:
    """Load the confirmed map ``{metric: ConfirmationRecord}``. ``{}`` if absent or malformed."""
    path = _ledger_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("tsdb confirmation ledger unreadable at %s: %s", path, exc)
        return {}
    entries = data.get("confirmed", {}) if isinstance(data, dict) else {}
    out: dict[str, ConfirmationRecord] = {}
    for metric, entry in (entries or {}).items():
        if isinstance(entry, Mapping):
            out[str(metric)] = ConfirmationRecord.from_dict(str(metric), entry)
    return out


def _write_ledger(project_root: str | Path, records: Mapping[str, ConfirmationRecord]) -> Path:
    """Atomically write the ledger (temp file + ``os.replace``), sorted for a stable diff."""
    path = _ledger_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": LEDGER_SCHEMA,
        "confirmed": {m: records[m].to_dict() for m in sorted(records)},
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(payload, sort_keys=False, default_flow_style=False), encoding="utf-8")
    os.replace(tmp, path)
    return path


# --------------------------------------------------------------------------- #
# The gate.                                                                      #
# --------------------------------------------------------------------------- #
def confirmation_status(
    project_root: str | Path,
    metric: str,
    inferred_identity: Sequence[str],
) -> ConfirmationStatus:
    """Classify a metric's currently-inferred identity against the committed ledger."""
    record = load_ledger(project_root).get(metric)
    if record is None:
        return ConfirmationStatus.UNCONFIRMED
    if _normalize_identity(record.identity) == _normalize_identity(inferred_identity):
        return ConfirmationStatus.CONFIRMED
    return ConfirmationStatus.STALE


def is_confirmed(project_root: str | Path, metric: str, inferred_identity: Sequence[str]) -> bool:
    return confirmation_status(project_root, metric, inferred_identity) is ConfirmationStatus.CONFIRMED


def require_confirmation(
    project_root: str | Path,
    metric: str,
    inferred_identity: Sequence[str],
) -> None:
    """Hard gate (M4 calls this before promote): raise unless the current key is confirmed."""
    status = confirmation_status(project_root, metric, inferred_identity)
    if status is ConfirmationStatus.CONFIRMED:
        return
    if status is ConfirmationStatus.STALE:
        record = load_ledger(project_root)[metric]
        raise ConfirmationRequired(
            f"inferred identity for {metric!r} changed since it was confirmed "
            f"(confirmed {sorted(record.identity)} on {record.confirmed_at}, now "
            f"{sorted(inferred_identity)}) — re-confirm before promoting (a changed key "
            "silently overwrites data on backfill)"
        )
    raise ConfirmationRequired(
        f"identity for {metric!r} ({sorted(inferred_identity)}) is not confirmed — "
        f"review it against the golden and record a confirmation before promoting"
    )


def record_confirmation(
    project_root: str | Path,
    metric: str,
    entity: str,
    identity: Sequence[str],
    *,
    schema_sha256: Optional[str] = None,
    today: Optional[str] = None,
) -> ConfirmationRecord:
    """Record (or update) a committed confirmation for ``metric``. Returns the written record.

    ``today`` is injectable for deterministic tests; defaults to the current UTC date.
    """
    ident = _normalize_identity(identity)
    if not ident:
        raise ConfirmationError(f"cannot confirm an empty identity for {metric!r}")
    record = ConfirmationRecord(
        metric=metric,
        entity=entity,
        identity=ident,
        confirmed_at=today or date.today().isoformat(),
        schema_sha256=schema_sha256,
    )
    ledger = load_ledger(project_root)
    ledger[metric] = record
    _write_ledger(project_root, ledger)
    logger.info("recorded tsdb identity confirmation: %s → %s", metric, list(ident))
    return record


def confirm_inference(
    project_root: str | Path,
    result: InferenceResult,
    metric: str,
    *,
    today: Optional[str] = None,
) -> ConfirmationRecord:
    """Convenience: record a confirmation directly from an :class:`InferenceResult`."""
    return record_confirmation(
        project_root, metric, result.entity, result.identity_fields,
        schema_sha256=result.schema.schema_sha256, today=today,
    )


# --------------------------------------------------------------------------- #
# The confirmation surface (what a human reviews before confirming).            #
# --------------------------------------------------------------------------- #
def render_confirmation_surface(
    result: InferenceResult,
    *,
    golden_key: Optional[Sequence[str]] = None,
    status: Optional[ConfirmationStatus] = None,
) -> str:
    """Surface the inferred identity next to the golden diff (R1-F7), for human review.

    ``golden_key`` is a known reference key (raw label names); when supplied, the surface shows
    the diff between the inferred key and the golden so a divergence is obvious. ``status``, when
    given, is echoed so the reviewer sees whether this is a first confirmation or a re-confirm.
    """
    lines = [
        f"Identity confirmation — {result.entity} (metric: infer target)",
        f"  inferred key: {list(result.identity_fields)}",
        f"  raw labels:   {list(result.identity_labels)}",
        f"  measure:      {result.measure_field} (Decimal)",
    ]
    if golden_key is not None:
        from .infer import camel

        golden_fields = {camel(c) for c in golden_key}
        inferred = set(result.identity_fields)
        missing = sorted(golden_fields - inferred)   # in golden, not inferred
        extra = sorted(inferred - golden_fields)      # inferred, not in golden
        if not missing and not extra:
            lines.append(f"  golden diff:  MATCHES golden {sorted(golden_fields)}")
        else:
            lines.append(f"  golden diff:  DIVERGES from golden {sorted(golden_fields)}")
            if missing:
                lines.append(f"    - missing (in golden, not inferred): {missing}")
            if extra:
                lines.append(f"    - extra (inferred, not in golden):   {extra}")
    if status is not None:
        lines.append(f"  status:       {status.value}")
    lines.append("  → confirm this key before promotion (a wrong key silently overwrites on backfill)")
    return "\n".join(lines)
