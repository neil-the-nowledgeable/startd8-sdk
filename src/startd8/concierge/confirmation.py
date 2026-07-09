# Copyright 2026 StartD8 Contributors
# SPDX-License-Identifier: LicenseRef-Equitable-Use-1.0

"""Kickoff value-input confirmation — the kernel-native, $0 way to confirm a defaulted value-input.

Confirming a defaulted field (a) captures a *real* value into its input YAML via the existing
replace-only splice (`kickoff_experience/capture.py`) and (b) records the decision in an **additive,
committed ledger** at ``docs/kickoff/confirmed.yaml`` (OUTSIDE ``inputs/`` so no input scanner glob
matches it). Confirmation is a *decision act, not a value-lock*: a later hand-edit does not
un-confirm the field (staleness is surfaced separately). See
``docs/design/kickoff/VALUE_INPUT_CONFIRMATION_{REQUIREMENTS,PLAN}.md``.

The ledger IS the per-field confirmation state (per-field provenance does not exist in the domain
YAMLs). Absent ledger ⇒ nothing confirmed ⇒ byte-identical to today.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from startd8.logging_config import get_logger

logger = get_logger(__name__)

#: Committed ledger, OUTSIDE ``docs/kickoff/inputs/`` (so the ``inputs/*.yaml`` glob + survey/wireframe
#: scanners never match it — OQ-6 decision). Version-controlled beside the inputs it annotates.
LEDGER_REL = "docs/kickoff/confirmed.yaml"
#: The base (legacy) schema. An all-explicit ledger — every entry a human ``kickoff confirm`` — stays
#: ``v1`` **byte-for-byte as before** (A-FR6d): the audience M2 change is a pure superset.
LEDGER_SCHEMA = "kickoff.confirmed.v1"
#: Emitted ONLY once the ledger holds at least one ``audience-default:*`` provenance entry (A-FR6).
#: The bump is **conditional** so a user who never sets an audience sees no schema-line change (FR-2).
LEDGER_SCHEMA_V2 = "kickoff.confirmed.v2"

#: Per-decision provenance (M2, FR-6). It is an **additive, optional** ledger-entry field; its
#: **absence means ``explicit``** (a human confirmation) — the fail-open default (A-FR6). A machine
#: writer (the M3 pre-pass) stamps ``audience-default:<slug>``; ``kickoff confirm`` never stamps
#: anything, so promoting an audience-default to explicit simply drops the field (A-FR6b).
AUDIENCE_DEFAULT_PREFIX = "audience-default:"


def audience_default_provenance(slug: str) -> str:
    """The provenance string a machine writer stamps for an audience-default (``audience-default:<slug>``)."""
    return f"{AUDIENCE_DEFAULT_PREFIX}{slug}"


def is_audience_default(entry: Any) -> bool:
    """True iff a ledger entry was written by the audience pre-pass (an ``audience-default:*`` provenance).

    The public predicate (FR-9) consumers outside this module use to read provenance without reaching a
    private symbol. Tolerant by design: a non-dict entry, or an entry lacking the optional ``provenance``
    key (the common ``{value, at, mode}`` shape), returns ``False`` — never raises.
    """
    if not isinstance(entry, dict):
        return False
    prov = entry.get("provenance")
    return isinstance(prov, str) and prov.startswith(AUDIENCE_DEFAULT_PREFIX)


def audience_default_slug(entry: Any) -> Optional[str]:
    """The ``<slug>`` an audience-default entry was stamped for, or ``None`` if the entry is not one."""
    if not is_audience_default(entry):
        return None
    return entry["provenance"][len(AUDIENCE_DEFAULT_PREFIX) :]


#: Back-compat private alias — internal callers (``_dump_ledger``) predate the public name (FR-9).
_is_audience_default = is_audience_default


#: A field is "confirmable" (worth a human decision) when its template provenance is a default.
_CONFIRMABLE_PROVENANCE = frozenset({"estimate", "config-default"})
VALID_MODES = ("set", "as-is")


class ConfirmError(ValueError):
    """A confirmation failure carrying a stable code (mirrors CaptureError/ConciergeError style)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


# --- ledger IO (tolerant; absent/malformed ⇒ empty, never raises) -------------------------------


def _ledger_path(project_root: str | Path) -> Path:
    return Path(project_root) / LEDGER_REL


def load_ledger(project_root: str | Path) -> Dict[str, dict]:
    """The confirmed map ``{value_path: {value, at, mode}}``. ``{}`` if absent or malformed."""
    path = _ledger_path(project_root)
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        logger.warning("kickoff confirmation ledger unreadable at %s: %s", path, exc)
        return {}
    confirmed = data.get("confirmed") if isinstance(data, dict) else None
    return dict(confirmed) if isinstance(confirmed, dict) else {}


def confirmed_value_paths(project_root: str | Path) -> set:
    return set(load_ledger(project_root).keys())


def _dump_ledger(confirmed: Dict[str, dict]) -> str:
    """Serialize the ledger, **schema-aware** (A-FR6d, R4-F35): the single writer emits ``v2`` only
    when the map holds an ``audience-default:*`` entry, else ``v1`` — so an all-explicit ledger is
    byte-for-byte identical to the pre-audience behavior (FR-2)."""
    schema = LEDGER_SCHEMA_V2 if any(_is_audience_default(e) for e in confirmed.values()) else LEDGER_SCHEMA
    return yaml.safe_dump(
        {"schema": schema, "confirmed": confirmed}, sort_keys=True, allow_unicode=True
    )


# --- confirmable-field inventory (the SET is a template fact; confirmed-ness is project state) ----


def _domain_slug(write_target_file: str) -> str:
    return write_target_file[:-5] if write_target_file.endswith(".yaml") else Path(write_target_file).stem


def confirmable_fields(config: Optional[Any] = None) -> List[dict]:
    """Every defaulted, writable field a human can confirm — from the static SDK config (a template
    fact). Each carries its domain slug, canonical ``value_path``, label, widget, and choices."""
    from ..kickoff_experience.manifest import default_config

    cfg = config or default_config()
    out: List[dict] = []
    for f in cfg.writable_fields():
        if f.provenance_default not in _CONFIRMABLE_PROVENANCE or f.write_target is None:
            continue
        out.append({
            "value_path": f.value_path,   # THE canonical key — also the ledger key (R1-S7)
            "label": f.label,
            "domain": _domain_slug(f.write_target.file),
            "widget": f.widget,
            "choices": list(f.choices),
        })
    return out


def _scalar_eq(recorded: Any, on_disk: str) -> bool:
    """Compare a ledger-recorded scalar to an on-disk scalar YAML-semantically, so numeric
    normalization (e.g. ``"5.00"`` vs the parsed ``5.0``) is NOT reported as a hand-edit."""
    if str(recorded) == on_disk:
        return True
    try:
        return yaml.safe_load(str(recorded)) == yaml.safe_load(on_disk)
    except yaml.YAMLError:
        return False


def _read_field_value(project_root: str | Path, file: str, dotted_key: str) -> Optional[str]:
    """The on-disk scalar at ``file#/dotted_key`` (for as-is capture + stale detection), or None."""
    path = Path(project_root) / "docs" / "kickoff" / "inputs" / file
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None
    node: Any = data
    for part in dotted_key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return None if isinstance(node, (dict, list)) else str(node)


def field_current_value(
    project_root: str | Path, value_path: str, *, config: Optional[Any] = None
) -> Optional[str]:
    """The current on-disk scalar for a confirmable field's ``value_path`` (read-only), or None.

    A public getter over ``_read_field_value`` for surfaces that show "the current default" (e.g. the
    guided confirm walk). Additive — does not touch ``build_confirm_plan``/``apply_confirm``/the ledger."""
    from ..kickoff_experience.manifest import default_config

    cfg = config or default_config()
    field = cfg.field_by_value_path(value_path)
    if field is None or field.write_target is None:
        return None
    return _read_field_value(project_root, field.write_target.file, field.write_target.key)


def domain_confirmation(project_root: str | Path, config: Optional[Any] = None) -> Dict[str, dict]:
    """Per-domain honest count from PROJECT STATE (ledger + inputs), not the static template.

    ``{slug: {confirmable, confirmed, awaiting, stale[, audience_defaulted]}}``. The buckets
    ``confirmed`` / ``awaiting`` / ``audience_defaulted`` **partition** the confirmable set
    (``confirmed + awaiting + audience_defaulted == confirmable``, A-FR13b): a ledger entry with an
    ``audience-default:*`` provenance counts as ``audience_defaulted`` (a machine default the user
    hasn't ratified), NOT as ``confirmed``. ``stale`` is an **overlay** (a subset flag, never a fourth
    partition) counting either-bucket entries whose on-disk value diverged from the recorded value —
    display only (FR-9), never auto-rewritten; an audience-default is thus ``audience_defaulted`` AND
    possibly ``stale``, never double-counted.

    **No-regression (A-FR13 / R2-F26):** when a domain has **no** audience-default entries, the
    ``audience_defaulted`` key is **omitted entirely** — so the returned shape (and any serialization
    of it) is byte-identical to the pre-audience behavior for every user who never sets an audience.
    """
    from ..kickoff_experience.manifest import default_config

    cfg = config or default_config()
    by_vp = {f.value_path: f for f in cfg.writable_fields()}
    ledger = load_ledger(project_root)
    out: Dict[str, dict] = {}
    for field in confirmable_fields(cfg):
        slug = field["domain"]
        # ``_audef`` is an internal accumulator; it is promoted to (or dropped from) the public shape
        # after the loop so the no-audience case stays byte-identical to today.
        counts = out.setdefault(
            slug, {"confirmable": 0, "confirmed": 0, "awaiting": 0, "stale": 0, "_audef": 0}
        )
        counts["confirmable"] += 1
        vp = field["value_path"]
        entry = ledger.get(vp)
        if entry is None:
            counts["awaiting"] += 1
            continue
        if _is_audience_default(entry):
            counts["_audef"] += 1
        else:
            counts["confirmed"] += 1
        # stale overlay — applies to BOTH the confirmed and audience-defaulted buckets (A-FR13b).
        fdef = by_vp.get(vp)
        if fdef is not None and fdef.write_target is not None:
            on_disk = _read_field_value(project_root, fdef.write_target.file, fdef.write_target.key)
            if on_disk is not None and not _scalar_eq(entry.get("value"), on_disk):
                counts["stale"] += 1
    # Finalize: surface ``audience_defaulted`` only when non-zero (else keep today's exact shape).
    for counts in out.values():
        n = counts.pop("_audef")
        if n:
            counts["audience_defaulted"] = n
    return out


# --- plan + apply --------------------------------------------------------------------------------


@dataclass(frozen=True)
class ConfirmPlan:
    value_path: str
    mode: str                 # "set" | "as-is"
    value: str                # the value recorded in the ledger
    at: str
    capture_plan: Optional[Any]   # a CapturePlan for the value write, or None when mode == "as-is"
    ledger_text: str          # the full ledger content to write
    #: Per-decision provenance (M2, FR-6): ``None`` ⇒ **explicit** (a human confirmation; no field
    #: written), or ``audience-default:<slug>`` for a machine default (the M3 pre-pass). Absence in the
    #: ledger entry is the fail-open "explicit" default (A-FR6).
    provenance: Optional[str] = None


def build_confirm_plan(
    project_root: str | Path,
    value_path: str,
    value: Optional[str] = None,
    *,
    mode: str = "set",
    timestamp: Optional[str] = None,
    config: Optional[Any] = None,
    provenance: Optional[str] = None,
) -> ConfirmPlan:
    """Plan a confirmation (no write). ``mode="set"`` captures *value*; ``mode="as-is"`` confirms the
    current on-disk default unchanged. ``timestamp`` injectable for deterministic tests.

    ``provenance`` (M2, FR-6): ``None`` (default) writes an **explicit** entry with **no** provenance
    field — so a human ``kickoff confirm`` that promotes a prior audience-default **strips** the
    provenance (the entry is rebuilt wholesale; A-FR6b). A machine writer (the M3 pre-pass) passes
    ``audience-default:<slug>`` to stamp the entry (A-FR6c write-path invariant)."""
    from ..kickoff_experience.capture import CaptureError, build_capture_plan
    from ..kickoff_experience.manifest import default_config

    if mode not in VALID_MODES:
        raise ConfirmError("bad_mode", f"mode must be one of {VALID_MODES}, got {mode!r}")
    cfg = config or default_config()
    field = cfg.field_by_value_path(value_path)
    if field is None or field.write_target is None or field.provenance_default not in _CONFIRMABLE_PROVENANCE:
        known = ", ".join(sorted(f["value_path"] for f in confirmable_fields(cfg)))
        raise ConfirmError(
            "unknown_field",
            f"{value_path!r} is not a confirmable value-input field (known: {known})",
        )
    at = timestamp or date.today().isoformat()

    capture_plan = None
    if mode == "set":
        if value is None:
            raise ConfirmError("missing_value", "mode 'set' requires a value (--value)")
        if field.choices and value not in field.choices:
            raise ConfirmError("bad_value", f"value for {value_path!r} must be one of {field.choices}")
        try:
            capture_plan = build_capture_plan(project_root, value_path, value, config=cfg)
        except CaptureError as exc:
            raise ConfirmError(getattr(exc, "code", "capture_failed"), str(exc))
        recorded = value
    else:  # as-is
        recorded = _read_field_value(project_root, field.write_target.file, field.write_target.key)
        if recorded is None:
            raise ConfirmError(
                "missing_value", f"cannot confirm-as-is: no on-disk value at {value_path!r}"
            )

    # Rebuild the entry wholesale — an explicit confirm (provenance=None) therefore carries NO
    # provenance field, so promoting a prior audience-default drops it (A-FR6b).
    entry: Dict[str, Any] = {"value": recorded, "at": at, "mode": mode}
    if provenance is not None:
        entry["provenance"] = provenance
    ledger = load_ledger(project_root)
    ledger[value_path] = entry
    return ConfirmPlan(
        value_path=value_path, mode=mode, value=recorded, at=at,
        capture_plan=capture_plan, ledger_text=_dump_ledger(ledger), provenance=provenance,
    )


def apply_confirm(project_root: str | Path, plan: ConfirmPlan) -> Dict[str, Any]:
    """Apply a confirmation: value write first (if any), then the ledger — with a defined
    partial-failure contract. ``safe_write.apply_write_plan`` does NOT raise on a per-file error, so
    we inspect the ``WriteResult`` and fail LOUD if the ledger did not land (never a silent
    under-count). Raises :class:`ConfirmError` on any failure."""
    from ..kickoff_experience.capture import CaptureError, apply_capture
    from .safe_write import ACTION_OVERWRITE, PlannedWrite, SafeWriteError, apply_write_plan

    root = Path(project_root)

    # 1. Value write first — so a ledger entry never claims a write that didn't land.
    if plan.capture_plan is not None:
        try:
            apply_capture(root, plan.capture_plan)
        except CaptureError as exc:
            raise ConfirmError(getattr(exc, "code", "capture_failed"), f"value not written: {exc}")

    # 2. Ledger write (upsert = ACTION_OVERWRITE ⇒ needs force=True, else silent skip — R1-S8).
    write = PlannedWrite(path=LEDGER_REL, content=plan.ledger_text, action=ACTION_OVERWRITE)
    try:
        result = apply_write_plan(root, [write], force=True)
    except SafeWriteError as exc:
        raise ConfirmError("ledger_refused", f"value written, confirmation NOT recorded: {exc}")
    if not result.ok or LEDGER_REL not in result.written:
        detail = (result.blocked or result.errors or result.skipped or [{"reason": "unknown"}])[0]
        raise ConfirmError("ledger_not_recorded", f"value written, confirmation NOT recorded: {detail}")

    return {"value_path": plan.value_path, "mode": plan.mode, "value": plan.value, "confirmed": True}


# --- M5: Advanced confirm-all (FR-12/FR-18, A-FR12b) --------------------------------------------

#: A template placeholder default (e.g. ``$<5.00>`` / ``<free-during-demo | live>``) — an angle-bracket
#: token. Confirm-all MUST NOT ledger these as real values (R4-F33); they stay ``awaiting``.
_PLACEHOLDER_RE = re.compile(r"<[^>]*>")


def _is_placeholder(value: Optional[str]) -> bool:
    return value is not None and bool(_PLACEHOLDER_RE.search(value))


@dataclass(frozen=True)
class ConfirmAllPlan:
    """The PREVIEW of a confirm-all (FR-18): the decisions, computed with **no writes** (A-FR12
    two-phase). ``to_confirm`` = ``(value_path, on_disk_value)`` that would be confirmed as-is;
    ``skipped_placeholder`` = ``(value_path, on_disk_value)`` left awaiting because the on-disk value
    is a ``<…>`` placeholder (A-FR12b)."""

    to_confirm: Tuple[Tuple[str, str], ...]
    skipped_placeholder: Tuple[Tuple[str, str], ...]

    @property
    def rows(self) -> List[Tuple[str, str]]:
        return list(self.to_confirm)


def build_confirm_all_plan(
    project_root: str | Path, *, config: Optional[Any] = None
) -> ConfirmAllPlan:
    """Phase 1 (preview, no writes): decide which awaiting fields a confirm-all would confirm as-is.

    Skips any field whose on-disk value is a ``<…>`` placeholder (A-FR12b/R4-F33 — never ledger
    garbage) or is missing. This is the table FR-18 shows before anything is written.
    """
    from ..kickoff_experience.manifest import default_config
    from .confirm_walk import awaiting_fields

    cfg = config or default_config()
    to_confirm: List[Tuple[str, str]] = []
    skipped: List[Tuple[str, str]] = []
    for f in awaiting_fields(project_root, cfg):
        vp = f["value_path"]
        fdef = cfg.field_by_value_path(vp)
        on_disk = (
            _read_field_value(project_root, fdef.write_target.file, fdef.write_target.key)
            if fdef is not None and fdef.write_target is not None else None
        )
        if on_disk is None:
            continue
        if _is_placeholder(on_disk):
            skipped.append((vp, on_disk))
            continue
        to_confirm.append((vp, on_disk))
    return ConfirmAllPlan(tuple(to_confirm), tuple(skipped))


def apply_confirm_all(
    project_root: str | Path,
    plan: ConfirmAllPlan,
    *,
    timestamp: Optional[str] = None,
    config: Optional[Any] = None,
) -> List[str]:
    """Phase 2 (commit): confirm each ``to_confirm`` field as-is, **sequentially against the live
    ledger** — so each entry is byte-identical to a single ``kickoff confirm --as-is`` and later
    fields never clobber earlier batch writes (``test_confirm_all_equals_single``). Returns the
    confirmed value_paths. The caller is responsible for the FR-18 explicit-confirmation gate."""
    confirmed: List[str] = []
    for vp, _on_disk in plan.to_confirm:
        p = build_confirm_plan(project_root, vp, mode="as-is", timestamp=timestamp, config=config)
        apply_confirm(project_root, p)
        confirmed.append(vp)
    return confirmed
