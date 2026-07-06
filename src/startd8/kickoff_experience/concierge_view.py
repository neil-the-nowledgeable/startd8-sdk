"""M-CM — the consolidated Concierge view + apply module (GE-M2 detangle).

This is the ONE Concierge module (GE-M2 / FR-GE-7 "one vocabulary, one write path"). It folds the
former quartet — the parity view-model (this file), the typed applier (`concierge_apply`), the TUI
driver (`tui_concierge`), and the agent-spec resolver (`concierge_agent`) — into a single surface so
the web, TUI, and CLI share one view payload, one write path, and one agent-resolution ladder. The
old module names remain importable as thin compat shims re-exporting from here (one-release window,
coupled to the M1 alias retirement).

Four concerns live here, top to bottom:

1. **Agent resolution** (`resolve_concierge_agent_spec`) — which provider/model the agentic Concierge
   uses, by the FR-PC-4 precedence.
2. **The typed applier** (`apply_concierge_plan` + `ConciergeWriteCode`/`ConciergeWriteResult` +
   pre-apply validation) — every Concierge write rides `concierge/safe_write.py` (FR-GE-13); this is
   the one write path.
3. **The parity view-model** (`build_concierge_view`) — the one read-only payload both the web
   (M-CM3) and the TUI (M-CM4) render, so parity is a property of a single fold. Never re-derives
   readiness (FR-CM-4 / FR-GE-6 no-new-engine).
4. **The TUI driver** (`run_concierge`) — renders the same view payload and applies via the same
   `apply_concierge_plan`.

**Not the MCP surface (R1-F7/S9):** the view aggregator carries write-affordance metadata
(`instantiate_offer`, `friction_form`); MCP exposes only the bare `build_survey` shape.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

# ================================================================================================
# 1. Agent resolution (folded from `concierge_agent.py`)
# ================================================================================================
#
# Precedence (FR-PC-4) — first present, non-placeholder, resolvable-as-a-string layer wins:
#
#     1. the explicit ``--agent`` flag            → source "flag"
#     2. per-project ``docs/kickoff/inputs/build-preferences.yaml`` ``concierge_agent`` → "project"
#     3. global ``~/.startd8/config.json`` ``preferences.concierge_agent``              → "global"
#     4. the catalog default ``Models.CLAUDE_SONNET_LATEST``                            → "default"
#
# This returns the chosen **spec string + source label only** — it does NOT validate the spec or
# build an agent (FR-PC-5 / OQ-6). A malformed/unreadable project file is skipped, never fatal
# (FR-PC-9); angle-bracket template placeholders are treated as unset (FR-PC-10).

# Project config path is pinned (FR-PC-8): this file only, never an examples/ or templates/ copy.
_PROJECT_BUILD_PREFS = ("docs", "kickoff", "inputs", "build-preferences.yaml")


def _usable(spec: Optional[str]) -> Optional[str]:
    """A config value is usable iff it's a non-empty string that is not a `<…>` placeholder (FR-PC-10)."""
    if not spec:
        return None
    s = spec.strip()
    if not s or (s.startswith("<") and s.endswith(">")):
        return None
    return s


def _project_concierge_agent(project_root: str | Path) -> Optional[str]:
    """Read `concierge_agent` from the project's build-preferences.yaml; skip on any error (FR-PC-9)."""
    path = Path(project_root).expanduser().joinpath(*_PROJECT_BUILD_PREFS)
    if not path.is_file():
        return None
    try:
        from ..kickoff_inputs import parse_build_preferences

        return _usable(parse_build_preferences(path.read_text(encoding="utf-8")).concierge_agent)
    except Exception:
        # Malformed sheet / IO error → skip this layer (degrade to the next), never crash.
        return None


def _global_concierge_agent() -> Optional[str]:
    try:
        from ..config import get_config_manager

        return _usable(get_config_manager().get_preference("concierge_agent"))
    except Exception:
        return None


def resolve_concierge_agent_spec(
    project_root: str | Path,
    flag: Optional[str] = None,
) -> Tuple[str, str]:
    """Return ``(spec, source)`` for the agentic Concierge per the FR-PC-4 precedence."""
    from ..model_catalog import Models

    flag_spec = _usable(flag)
    if flag_spec:
        return flag_spec, "flag"
    project_spec = _project_concierge_agent(project_root)
    if project_spec:
        return project_spec, "project"
    global_spec = _global_concierge_agent()
    if global_spec:
        return global_spec, "global"
    return Models.CLAUDE_SONNET_LATEST, "default"   # catalog reference, not a literal (FR-PC-6)


# ================================================================================================
# 2. The typed applier (folded from `concierge_apply.py`)
# ================================================================================================
#
# Concierge mode reuses the existing write seam — `to_planned_writes` (`concierge/writes.py`) →
# `apply_write_plan` (`concierge/safe_write.py`), the same 3-line pattern the CLI uses — behind one
# typed result so the web, TUI, and telemetry share a stable reason-code vocabulary.
#
# Two CRP-surfaced correctness points are baked in here:
#
# * **`skipped`/`partial` outcomes (R1-F2/S3).** No-clobber instantiate of a file that already
#   exists lands in `WriteResult.skipped` with `ok=True`. A flat OK can't tell "wrote 7 files" from
#   "all 7 existed, wrote 0" — so this maps the write counts into distinct codes.
# * **Timestamp layer (R1-F1/S2).** The friction timestamp is NOT stamped here —
#   `build_friction_entry` bakes the JSON line (incl. `ts`) into `append_text` at build time, so the
#   **surface handler** passes `timestamp=` into the builder. This applier receives an
#   already-serialized plan and only applies it.
#
# Typed validation of user input (R2-F5) happens *before* a plan is built — see `validate_friction`
# and `validate_posture`.

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


# ================================================================================================
# 3. The parity view-model (the read-only payload both surfaces render)
# ================================================================================================
#
# `build_concierge_view` is the one representation the web (M-CM3) and TUI (M-CM4) both render, so
# parity is a property of a single payload (mirrors `state.to_dict()`). It composes existing
# read-only machinery — never re-derives readiness (FR-CM-4):
#
# * `survey`     — `concierge.build_survey` (brownfield triage), **memoized** (R1-S6: it walks
#   `root.rglob("*")`, an O(repo) cost; a short TTL keeps repeated `GET /concierge` cheap).
# * `readiness`  — `ReadinessView.from_assess(build_assess())`, reused.
# * `instantiate_offer` — `{needed, package_state, postures}` where `package_state` ∈
#   `missing | partial | complete` is **restart-safe** (R5-F1): computed from the instantiate plan's
#   per-file stat, so a half-scaffolded package (some files present) reads `partial`, not a boolean
#   keyed only to `inputs/`.
# * `friction_form` — the field spec (with the length cap).
# * `next_action` — a derived CTA both surfaces show (R2-F2).

SCHEMA_VERSION = 1

POSTURE_BANNER = (
    "🛈 Concierge — assist, not operate. I survey the project, assess readiness, scaffold a kickoff "
    "package, and log friction. I never run the build or record gates; writes happen only at your "
    "explicit confirmation."
)

PACKAGE_MISSING = "missing"
PACKAGE_PARTIAL = "partial"
PACKAGE_COMPLETE = "complete"

# Survey memo: {root: (monotonic_stamp, survey_dict)}. Cheap TTL guard for repeated GET /concierge.
_SURVEY_TTL_S = 5.0
_SURVEY_CACHE_MAX = 64  # bound entries so a multi-root process can't accumulate stale surveys
_survey_cache: Dict[str, Tuple[float, dict]] = {}


def cached_survey(project_root: str, *, ttl: float = _SURVEY_TTL_S, clock: Callable[[], float] = time.monotonic) -> dict:
    """`build_survey` behind a short TTL memo (R1-S6) — bounds the O(repo) rglob on repeated views."""
    from ..concierge import build_survey

    now = clock()
    hit = _survey_cache.get(project_root)
    if hit is not None and (now - hit[0]) < ttl:
        return hit[1]
    survey = build_survey(project_root)
    if project_root not in _survey_cache and len(_survey_cache) >= _SURVEY_CACHE_MAX:
        _survey_cache.pop(next(iter(_survey_cache)), None)  # evict oldest
    _survey_cache[project_root] = (now, survey)
    return survey


def _package_state(project_root: str) -> str:
    """Restart-safe package detection (R5-F1) from the instantiate plan's per-file stat."""
    from ..concierge.writes import build_instantiate_plan

    plan = build_instantiate_plan(project_root)  # stat-only, no write
    statuses = [w.get("status") for w in plan.get("writes", [])]
    if not statuses:
        return PACKAGE_MISSING
    if all(s == "exists" for s in statuses):
        return PACKAGE_COMPLETE
    if all(s == "new" for s in statuses):
        return PACKAGE_MISSING
    return PACKAGE_PARTIAL


def _next_action(package_state: str, readiness: Optional[dict]) -> Dict[str, str]:
    if package_state == PACKAGE_MISSING:
        return {"kind": "instantiate", "title": "Create the kickoff package",
                "detail": "This project has no kickoff inputs yet — scaffold them to begin."}
    if package_state == PACKAGE_PARTIAL:
        return {"kind": "instantiate", "title": "Complete the kickoff package",
                "detail": "Some kickoff files are missing — re-run instantiate to fill them in."}
    # FR-NU-3: the readiness-blocker CTA via the SHARED formatter (module-qualified so the parity
    # monkeypatch of `ranking.blocker_cta` is effective — CRP R1-S1). `readiness` is a dict here (or
    # None on the build_readiness exception path); `blocker_cta` normalizes both and returns None → the
    # "ready" branch (R1-S6). NOTE: the blocker `detail` is now the consequence|status (was a fixed
    # string) — a user-visible copy change (CRP R1-F3).
    from . import ranking

    cta = ranking.blocker_cta(readiness)
    if cta is not None:
        return cta.to_dict()
    return {"kind": "ready", "title": "Kickoff is build-ready", "detail": "No blocking gaps remain."}


def _friction_form() -> dict:
    return {
        "fields": [
            {"name": "friction", "label": "What friction did you hit?", "required": True,
             "max_length": FRICTION_FIELD_MAX, "widget": "textarea"},
            {"name": "what_happened", "label": "What happened?", "required": True,
             "max_length": FRICTION_FIELD_MAX, "widget": "textarea"},
            {"name": "implication", "label": "Implication for the SDK / role?", "required": True,
             "max_length": FRICTION_FIELD_MAX, "widget": "textarea"},
        ],
    }


def build_concierge_view(
    project_root: str,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> Dict[str, Any]:
    """The shared Concierge payload both surfaces render (read-only, ``$0``)."""
    from .readiness import build_readiness

    root = str(project_root)
    survey = cached_survey(root, clock=clock)
    try:
        readiness = build_readiness(root).to_dict()
    except Exception:
        readiness = None
    package_state = _package_state(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "action": "concierge_view",
        "project_root": root,
        "posture_banner": POSTURE_BANNER,
        "survey": survey,
        "readiness": readiness,
        "instantiate_offer": {
            "needed": package_state != PACKAGE_COMPLETE,
            "package_state": package_state,
            "postures": ["prototype", "production"],
        },
        "friction_form": _friction_form(),
        "next_action": _next_action(package_state, readiness),
    }


# ================================================================================================
# 4. The TUI driver (folded from `tui_concierge.py`)
# ================================================================================================
#
# Renders the **same** `build_concierge_view` payload the web surface renders (parity), and applies
# writes through the **same** `apply_concierge_plan` (one write path, FR-CM-7) after an explicit
# human confirmation. The confirm/prompt callables are injected so the flow is testable without a
# TTY and so non-interactive use **fails closed** (R3-S5): when no foreground confirmation is
# possible (`questionary` returns ``None`` on a non-TTY or interrupt), nothing is written.

# Confirm returns True/False, or None when no foreground confirmation is possible (fail closed).
ConfirmFn = Callable[[str], Optional[bool]]
# Prompt returns the entered text, or None on interrupt/non-TTY.
PromptFn = Callable[[str], Optional[str]]
PrintFn = Callable[[str], None]

CONFIRM_UNAVAILABLE = "confirm_unavailable"


@dataclass
class ConciergeRunResult:
    """What the TUI run did — for tests and a final summary line."""

    package_state: str
    instantiate: Optional[str] = None   # a ConciergeWriteCode, CONFIRM_UNAVAILABLE, or None (declined)
    friction: Optional[str] = None
    lines: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"package_state": self.package_state, "instantiate": self.instantiate,
                "friction": self.friction}


def run_concierge(
    project_root: str,
    *,
    confirm: ConfirmFn,
    prompt: PromptFn,
    emit_line: PrintFn,
    posture: str = "prototype",
) -> ConciergeRunResult:
    """Render the Concierge view and offer instantiate + friction, applying via the shared path."""
    from ..concierge.writes import build_friction_entry, build_instantiate_plan
    from .telemetry import (
        EV_CONCIERGE_WRITE_REFUSED,
        EV_FRICTION_LOGGED,
        EV_KICKOFF_INSTANTIATED,
        EV_SURVEY_VIEWED,
        emit,
    )

    view = build_concierge_view(project_root)
    emit(EV_SURVEY_VIEWED, source="tui")
    s = view["survey"]
    offer = view["instantiate_offer"]
    na = view["next_action"]
    result = ConciergeRunResult(package_state=offer["package_state"])

    def out(line: str) -> None:
        result.lines.append(line)
        emit_line(line)

    out(view["posture_banner"])
    out(f"Survey: {len(s.get('requirement_docs', []))} req docs · "
        f"{len(s.get('model_files', []))} models · {len(s.get('pii_risk_flags', []))} PII flags")
    out(f"Kickoff package: {offer['package_state']}")
    out(f"Next: {na['title']} — {na['detail']}")

    # Instantiate (only if the package is missing/partial).
    if offer["needed"]:
        decision = confirm(f"Create/complete the kickoff package ({posture})?")
        if decision is None:
            result.instantiate = CONFIRM_UNAVAILABLE  # fail closed — no write
            out("No interactive confirmation available — not writing (use the CLI to apply).")
        elif decision:
            res = apply_concierge_plan(project_root, build_instantiate_plan(project_root, posture))
            result.instantiate = res.code
            if res.ok and res.wrote_anything:
                emit(EV_KICKOFF_INSTANTIATED, source="tui", posture=posture, code=res.code,
                     written_count=len(res.written))
                out(f"Instantiated: {res.code} ({len(res.written)} written, {len(res.skipped)} skipped)")
            elif not res.ok:
                emit(EV_CONCIERGE_WRITE_REFUSED, source="tui", action="instantiate", code=res.code)
                out(f"Refused: {res.code} — {res.message or ''} {res.hint or ''}".strip())
            else:
                out(f"No-op: {res.code} (package already present)")

    # Friction (always offered).
    if confirm("Log a friction item?"):
        fr = prompt("What friction did you hit?")
        wh = prompt("What happened?")
        im = prompt("Implication for the SDK / role?")
        try:
            validate_friction(fr or "", wh or "", im or "")
        except ConciergeInputError as exc:
            result.friction = exc.code
            out(f"Friction not logged: {exc.code} — {exc}")
            return result
        plan = build_friction_entry(
            project_root, friction=fr, what_happened=wh, implication=im,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        res = apply_concierge_plan(project_root, plan)
        result.friction = res.code
        if res.ok:
            emit(EV_FRICTION_LOGGED, source="tui", code=res.code)
            out("Friction logged.")
        else:
            emit(EV_CONCIERGE_WRITE_REFUSED, source="tui", action="friction", code=res.code)
            out(f"Friction refused: {res.code} — {res.message or ''} {res.hint or ''}".strip())

    return result


def _questionary_confirm(message: str) -> Optional[bool]:
    import questionary

    return questionary.confirm(message, default=False).ask()


def _questionary_prompt(message: str) -> Optional[str]:
    import questionary

    return questionary.text(message).ask()


# ================================================================================================
# 5. The guided-experience view-model (GE-M4 — the ONE Orient→Guide→Deepen parity oracle)
# ================================================================================================
#
# `build_guided_view` is the single canonical view-model for the guided experience (FR-GE-9). It was
# promoted here (out of the `kickoff guided` CLI body, where it lived inline as `kickoff.guided.v1`)
# so all three surfaces — CLI, TUI, and the local served web UI — render from ONE payload and differ
# only in *rendering*, not in *content*. It is **pure composition** of existing read-only producers
# (no new engine — FR-GE-6): Orient = the kernel `build_assess`; Guide = `orchestrator.build_kickoff_plan`
# (the advisor's no-LLM ranked playbook); Deepen = a read-only projection of a *persisted* facilitation
# session (GE-M3b's halted-session + per-round/total-cost transcript states). It calls no LLM and
# writes nothing.
#
# Parity is a property of this single fold: `guided_parity_digest` extracts the surface-independent
# semantic content every surface must present (phases, Guide blockers/next-commands, the Deepen halt
# banner, the session cost figure); `render_guided_lines` is the shared text projection both the CLI
# (Deepen block) and the TUI render; `render_deepen_lines` renders the Deepen phase; the web surface's
# `_render_guided` renders the same payload as HTML. `format_cost` is shared so the "same cost figure"
# is a byte-identical substring across surfaces.

GUIDED_SCHEMA = "kickoff.guided.v1"
GUIDED_SCHEMA_VERSION = 1
# The optional Deepen surface a user drives to run the facilitation panel (named, not invoked here).
DEEPEN_SURFACE = "startd8 kickoff panel ask-all"


def format_cost(usd: float | int | None) -> str:
    """The one cost-figure format every surface uses, so parity is a literal shared substring."""
    return f"${float(usd or 0.0):.4f}"


def project_deepen_state(session: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """Project a persisted facilitation session → the Deepen phase's semantic summary (read-only).

    ``None`` (no session yet) → the available-but-not-engaged pointer (GE-M1 behaviour preserved:
    ``engaged is False``). A session carries GE-M3b's first-class ``status="halted"`` state, the
    ``halt`` banner, and the per-round/session-total ``cost_total_usd`` — surfaced identically on
    every surface. Never re-derives anything; a pure read of the transcript dict.
    """
    if not session:
        return {
            "available": True,
            "engaged": False,
            "surface": DEEPEN_SURFACE,
            "session_id": None,
            "status": None,
            "halted": False,
            "halt": None,
            "cost_total_usd": 0.0,
            "budget_usd": 0.0,
            "n_rounds": 0,
        }
    halt = session.get("halt") or None
    status = session.get("status")
    return {
        "available": True,
        "engaged": True,
        "surface": DEEPEN_SURFACE,
        "session_id": session.get("session_id"),
        "status": status,
        "halted": status == "halted",
        # Only the human-facing reason+message travel to the surfaces (the full detail stays in the
        # transcript the observability-UX viewer renders).
        "halt": ({"reason": halt.get("reason"), "message": halt.get("message")} if halt else None),
        "cost_total_usd": float(session.get("cost_total_usd") or 0.0),
        "budget_usd": float(session.get("budget_usd") or 0.0),
        "n_rounds": len(session.get("rounds") or ()),
    }


def load_latest_deepen_session(project_root: str | Path) -> Optional[Dict[str, Any]]:
    """Read the most-recently-written persisted facilitation session, or ``None`` (read-only, ``$0``).

    Reads the transcript contract path the facilitator writes (``.startd8/kickoff-panel/*.json``);
    any IO/parse error degrades to ``None`` (the Deepen phase falls back to the pointer, never crashes
    the guided view). Does NOT import the facilitator (avoids pulling the LLM stack into a $0 read).
    """
    d = Path(project_root).expanduser() / ".startd8" / "kickoff-panel"
    if not d.is_dir():
        return None
    try:
        files = [p for p in d.glob("*.json") if p.is_file()]
        if not files:
            return None
        newest = max(files, key=lambda p: p.stat().st_mtime)
        import json

        data = json.loads(newest.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


# FR-1/FR-4/clauses A,B — the intro + posture the guided experience must surface (information only;
# the guided flow writes nothing, FR-GE-1). Posture is shown, never recorded here — the actionable
# choice stays on `instantiate --posture` (FR-4). Kept as module constants so every surface is byte-
# identical and single-sourced.
INTRO_EXPLAIN_COMMAND = "startd8 kickoff explain --intro"
POSTURE_HINT = "startd8 kickoff instantiate --posture <prototype|production>"
POSTURE_OPTIONS: tuple = (
    {"posture": "prototype", "deployment_mode": "installed",
     "summary": "solo/dogfood — every value pre-filled, no humans required to start; local-first."},
    {"posture": "production", "deployment_mode": "deployed",
     "summary": "named human roles validate each value; multi-user, behind a gateway."},
)


def _inputs_present(orient: Mapping[str, Any]) -> bool:
    """Read-only heuristic (FR-10): is the project already past onboarding (any input domain present)?"""
    domains = ((orient.get("kickoff_inputs") or {}).get("domains")) or {}
    return any((info or {}).get("status") == "present" for info in domains.values())


def _build_intro_block(orient: Mapping[str, Any], brief: bool) -> Dict[str, Any]:
    """Clause A — the compact process intro. ``full`` on a first run; ``brief`` pointer once the
    project has inputs or when ``brief`` is forced (FR-10). Read-only; no write informs the decision."""
    mode = "brief" if (brief or _inputs_present(orient)) else "full"
    text = f"New to kickoff? {INTRO_EXPLAIN_COMMAND} explains the process and its inputs."
    if mode == "full":
        try:
            from ..concierge import load_experience_doc

            text = load_experience_doc("intro", compact=True)
        except Exception:  # fall back to the brief pointer if the packaged doc can't be read
            mode = "brief"
    return {"mode": mode, "text": text, "explain_command": INTRO_EXPLAIN_COMMAND}


def _build_posture_block(orient: Mapping[str, Any]) -> Dict[str, Any]:
    """Clause B — posture as INFORMATION (FR-4): the two options + the current declared mode (if any)
    + the actionable hint pointing at `instantiate`. The guided flow never records the choice."""
    deployment = orient.get("deployment") or {}
    return {
        "current_mode": deployment.get("mode"),
        "options": [dict(o) for o in POSTURE_OPTIONS],
        "actionable_hint": POSTURE_HINT,
    }


def build_guided_view(
    project_root: str | Path,
    *,
    assess: Optional[Mapping[str, Any]] = None,
    plan: Optional[Any] = None,
    deepen_session: Optional[Mapping[str, Any]] = None,
    load_deepen: bool = True,
    brief: bool = False,
) -> Dict[str, Any]:
    """The ONE guided-experience view-model — Orient → Guide → Deepen (read-only, ``$0``, no LLM).

    Composition only (FR-GE-6, no new engine):
      * **Orient** = ``build_assess`` (the kernel readiness surface).
      * **Guide**  = ``build_kickoff_plan`` (the advisor's deterministic ranked playbook).
      * **Deepen** = ``project_deepen_state`` over a *persisted* facilitation session.

    ``assess``/``plan`` may be supplied by a caller that already computed them (the CLI does) to avoid
    a recompute; otherwise they are built here. ``deepen_session`` may be injected (tests / a live
    run); otherwise, when ``load_deepen`` is set, the latest persisted session is read from disk.
    """
    from ..concierge import build_assess as _build_assess
    from .orchestrator import build_kickoff_plan

    orient = dict(assess) if assess is not None else _build_assess(project_root)
    guide = plan if plan is not None else build_kickoff_plan(project_root)
    guide_dict = guide.to_dict() if hasattr(guide, "to_dict") else dict(guide)

    session = deepen_session
    if session is None and load_deepen:
        session = load_latest_deepen_session(project_root)

    return {
        "schema": GUIDED_SCHEMA,
        "schema_version": GUIDED_SCHEMA_VERSION,
        "action": "guided_view",
        "project_root": orient.get("project_root", str(project_root)),
        "intro": _build_intro_block(orient, brief),
        "posture": _build_posture_block(orient),
        "orient": orient,
        "guide": guide_dict,
        "deepen": project_deepen_state(session),
    }


def guided_parity_digest(view: Mapping[str, Any]) -> Dict[str, Any]:
    """The surface-independent semantic content every surface MUST present (the FR-GE-9 oracle).

    A structural/content contract, not a pixel contract: the three phases, the Guide readiness +
    blockers/next-commands, and the Deepen halt banner + session cost figure. The parity test asserts
    each surface's rendering carries exactly these.
    """
    guide = view.get("guide") or {}
    deepen = view.get("deepen") or {}
    steps = guide.get("steps") or []
    halt = deepen.get("halt") or None
    intro = view.get("intro") or {}
    posture = view.get("posture") or {}
    return {
        "phases": ("Orient", "Guide", "Deepen"),
        "intro_mode": intro.get("mode"),
        "posture_hint": posture.get("actionable_hint"),
        "readiness_score": guide.get("readiness_score"),
        "unmet_gates": tuple(guide.get("unmet_gates") or ()),
        "next_commands": tuple(s["command"] for s in steps if s.get("command")),
        "deepen_engaged": bool(deepen.get("engaged")),
        "deepen_status": deepen.get("status"),
        "deepen_halted": bool(deepen.get("halted")),
        "deepen_halt_message": (halt.get("message") if halt else None),
        "deepen_cost_figure": format_cost(deepen.get("cost_total_usd")),
    }


def render_deepen_lines(deepen: Mapping[str, Any], *, deepen_flag: bool = False) -> List[str]:
    """Render the Deepen phase as text — the SHARED projection the CLI and TUI both emit.

    Engaged (a persisted session exists) → its status, the halt banner (if halted), and the
    per-round/session-total cost. Not engaged → the optional pointer (GE-M1 wording preserved so the
    default/``--deepen`` hints are byte-stable): ``--deepen`` names the surface; ``later step`` marks
    the not-yet-live stub.
    """
    if deepen.get("engaged"):
        lines = [f"  session {deepen.get('session_id')} — status: {deepen.get('status')}"]
        if deepen.get("halted") and deepen.get("halt"):
            lines.append(f"  ⛔ HALTED ({deepen['halt'].get('reason')}): {deepen['halt'].get('message')}")
        cap = deepen.get("budget_usd") or 0.0
        cap_str = f" of {format_cost(cap)} cap" if cap else ""
        lines.append(
            f"  cost: {format_cost(deepen.get('cost_total_usd'))}{cap_str} "
            f"over {deepen.get('n_rounds')} round(s)"
        )
        return lines
    if deepen_flag:
        return [
            "  The facilitation panel (a multi-round risk/gap discovery pass) is coming as a "
            "first-class phase in a later step. For now, drive it via "
            f"{DEEPEN_SURFACE} (paid, synthetic — unratified input).",
        ]
    return [
        "  optional — pass --deepen to surface the facilitation panel pointer. "
        "Skipped by default; nothing is spent or written.",
    ]


def render_guided_lines(view: Mapping[str, Any], *, deepen_flag: bool = True) -> List[str]:
    """The shared plain-text projection of the guided view (the TUI surface; the CLI Deepen block).

    All three phases in order, each with the same semantic content the served surface carries, so a
    parity assertion over the tokens holds across surfaces (FR-GE-9). Pure; no IO.
    """
    orient = view.get("orient") or {}
    guide = view.get("guide") or {}
    deepen = view.get("deepen") or {}
    intro = view.get("intro") or {}
    posture = view.get("posture") or {}
    lines: List[str] = [
        "Guided kickoff — one experience, three phases (Orient → Guide → Deepen)",
        "",
    ]
    if intro.get("text"):
        lines += [intro["text"], ""]
    lines.append("1. Orient — where you are (readiness)")
    score = guide.get("readiness_score")
    if score is not None:
        # Fraction of $0-cascade generators (scaffold/backend/views) ready — a distinct axis from the
        # manifest gates below; labeled explicitly so 1.0 doesn't read as "done" while gates are unmet.
        lines.append(f"  cascade generators ready: {score} (scaffold/backend/views)")
    domains = ((orient.get("kickoff_inputs") or {}).get("domains")) or {}
    for name, info in domains.items():
        lines.append(f"  • {name}: {info.get('status')}")
    unmet = guide.get("unmet_gates") or []
    lines.append(f"  unmet gates: {', '.join(unmet) if unmet else '(none)'}")
    # FR-B3 — surface "what will be built" from the same plan (the wireframe cross-ref for detail).
    _cascade = orient.get("cascade") or {}
    _paths = _cascade.get("claimed_paths") or []
    if _paths:
        _cov = (_cascade.get("content_coverage") or {}).get("overall") or {}
        _cov_s = f"; content {_cov['authored']}/{_cov['total']}" if _cov.get("total") else ""
        lines.append(f"  will build: {len(_paths)} files{_cov_s}  (→ startd8 wireframe for the full plan)")
    if posture.get("actionable_hint"):
        cur = posture.get("current_mode")
        state = f"current mode = {cur}" if cur else "not yet chosen"
        lines.append(f"  posture: {state} — set it when you instantiate: {posture['actionable_hint']}")

    lines += ["", "2. Guide — the $0 conductor (deterministic, no LLM)"]
    for s in guide.get("steps") or []:
        lines.append(f"  {s.get('rank')}. [{s.get('cost')}] {s.get('title')} ({s.get('stage')})")
        if s.get("command"):
            lines.append(f"     $ {s['command']}")

    lines += ["", "3. Deepen — optional multi-perspective facilitation"]
    lines += render_deepen_lines(deepen, deepen_flag=deepen_flag)
    return lines


def run_guided(
    project_root: str | Path,
    *,
    emit_line: PrintFn,
    deepen_session: Optional[Mapping[str, Any]] = None,
    load_deepen: bool = True,
    deepen_flag: bool = True,
) -> Dict[str, Any]:
    """The TUI leg of the guided experience (GE-M4, the surviving TUI surface — R3-S6).

    Builds the ONE ``build_guided_view`` payload and emits ``render_guided_lines`` of it — so the TUI
    is, byte-for-byte, the shared text projection of the same view-model the CLI and web render.
    Returns the view for tests / a caller that wants the payload.
    """
    view = build_guided_view(
        project_root, deepen_session=deepen_session, load_deepen=load_deepen
    )
    for line in render_guided_lines(view, deepen_flag=deepen_flag):
        emit_line(line)
    return view
