"""M-CM1 — generic typed applier for Concierge WritePlans.

Concierge mode reuses the existing write seam — `to_planned_writes` (`concierge/writes.py`) →
`apply_write_plan` (`concierge/safe_write.py`), the same 3-line pattern the CLI uses — behind one
typed result so the web, TUI, and telemetry share a stable reason-code vocabulary.

Two CRP-surfaced correctness points are baked in here:

* **`skipped`/`partial` outcomes (R1-F2/S3).** No-clobber instantiate of a file that already exists
  lands in `WriteResult.skipped` with `ok=True`. A flat OK can't tell "wrote 7 files" from "all 7
  existed, wrote 0" — so this maps the write counts into distinct codes.
* **Timestamp layer (R1-F1/S2).** The friction timestamp is NOT stamped here — `build_friction_entry`
  bakes the JSON line (incl. `ts`) into `append_text` at build time, so the **surface handler** passes
  `timestamp=` into the builder. This applier receives an already-serialized plan and only applies it.

Typed validation of user input (R2-F5) happens *before* a plan is built — see `validate_friction`
and `validate_posture`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

# Conservative cap on a friction free-text field before it is serialized into the append-only log.
FRICTION_FIELD_MAX = 4000


class ConciergeWriteCode:
    """Stable typed outcomes for a Concierge write (parallel to CaptureCode)."""

    OK = "ok"                       # all planned files written
    SKIPPED = "skipped"            # nothing written — every target already existed (no-clobber no-op)
    PARTIAL = "partial"           # some written, some skipped/blocked — retry is idempotent
    WRITE_BLOCKED = "write_blocked"   # confinement/symlink refusal (with the ALLOWED_ROOTS hint)
    WRITE_REFUSED = "write_refused"   # the writer refused everything (no file written)
    # pre-apply input validation (R2-F5)
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_POSTURE = "invalid_posture"
    INPUT_TOO_LARGE = "input_too_large"


_ALLOWED_ROOTS_HINT = (
    "set STARTD8_CONCIERGE_ALLOWED_ROOTS to the project's real path if it is under a symlinked "
    "directory (e.g. macOS /tmp → /private/tmp)"
)


class ConciergeInputError(ValueError):
    """A pre-apply validation failure carrying a stable :class:`ConciergeWriteCode`."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ConciergeWriteResult:
    """The shared result envelope both surfaces render (R4-S4)."""

    code: str
    written: tuple = ()
    skipped: tuple = ()
    warnings: tuple = ()
    message: Optional[str] = None
    hint: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.code in (ConciergeWriteCode.OK, ConciergeWriteCode.PARTIAL, ConciergeWriteCode.SKIPPED)

    @property
    def wrote_anything(self) -> bool:
        return len(self.written) > 0

    def to_dict(self) -> dict:
        d: Dict[str, Any] = {
            "code": self.code,
            "written_count": len(self.written),
            "skipped_count": len(self.skipped),
            "written": list(self.written),
            "warnings": list(self.warnings),
        }
        if self.message is not None:
            d["message"] = self.message
        if self.hint is not None:
            d["hint"] = self.hint
        return d


# --- pre-apply validation (R2-F5) --------------------------------------------------------------


def validate_friction(friction: str, what_happened: str, implication: str) -> None:
    """Validate the three friction fields before a plan is built. Raises ConciergeInputError."""
    for name, value in (("friction", friction), ("what_happened", what_happened),
                        ("implication", implication)):
        if not (value or "").strip():
            raise ConciergeInputError(
                ConciergeWriteCode.MISSING_REQUIRED_FIELD, f"{name} is required"
            )
        if len(value) > FRICTION_FIELD_MAX:
            raise ConciergeInputError(
                ConciergeWriteCode.INPUT_TOO_LARGE,
                f"{name} exceeds {FRICTION_FIELD_MAX} characters",
            )


def validate_posture(posture: str) -> None:
    from ..concierge.writes import VALID_POSTURES

    if posture not in VALID_POSTURES:
        raise ConciergeInputError(
            ConciergeWriteCode.INVALID_POSTURE,
            f"posture must be one of {VALID_POSTURES}, got {posture!r}",
        )


# --- the applier -------------------------------------------------------------------------------


def apply_concierge_plan(
    project_root: str | Path,
    plan: Mapping[str, Any],
    *,
    force: bool = False,
) -> ConciergeWriteResult:
    """Apply a Concierge WritePlan via the safe-writer; return a typed, counted result.

    Never raises for a write-side issue — confinement refusals and per-file blocks come back as a
    typed code the surface can render (mirrors the M6 capture pattern).
    """
    from ..concierge.safe_write import SafeWriteError, apply_write_plan
    from ..concierge.writes import to_planned_writes

    warnings = tuple(plan.get("warnings", ()) or ())
    try:
        result = apply_write_plan(Path(project_root).expanduser(), to_planned_writes(plan),
                                  force=force)
    except SafeWriteError as exc:
        return ConciergeWriteResult(
            code=ConciergeWriteCode.WRITE_BLOCKED,
            warnings=warnings,
            message=f"safe-writer refused the write: {exc}",
            hint=_ALLOWED_ROOTS_HINT,
        )

    written = tuple(result.written)
    skipped = tuple(s.get("path", "?") if isinstance(s, dict) else str(s) for s in result.skipped)
    has_failure = bool(result.blocked or result.errors)

    if has_failure:
        # Some files may still have been written before/after the failing one (non-atomic).
        code = ConciergeWriteCode.PARTIAL if written else ConciergeWriteCode.WRITE_REFUSED
        detail = (result.blocked or result.errors or [{}])[0]
        return ConciergeWriteResult(
            code=code, written=written, skipped=skipped, warnings=warnings,
            message=f"write incomplete: {detail}",
            hint=_ALLOWED_ROOTS_HINT if code == ConciergeWriteCode.WRITE_REFUSED else None,
        )
    if written and skipped:
        code = ConciergeWriteCode.PARTIAL          # some new, some already existed (idempotent retry)
    elif written:
        code = ConciergeWriteCode.OK
    elif skipped:
        code = ConciergeWriteCode.SKIPPED          # no-clobber no-op: everything already existed
    else:
        code = ConciergeWriteCode.OK               # empty plan
    return ConciergeWriteResult(code=code, written=written, skipped=skipped, warnings=warnings)
