"""M-CM4 — TUI Concierge driver.

Renders the **same** `build_concierge_view` payload the web surface renders (parity), and applies
writes through the **same** `apply_concierge_plan` (one write path, FR-CM-7) after an explicit human
confirmation. The confirm/prompt callables are injected so the flow is testable without a TTY and so
non-interactive use **fails closed** (R3-S5): when no foreground confirmation is possible
(`questionary` returns ``None`` on a non-TTY or interrupt), nothing is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from .concierge_apply import (
    ConciergeInputError,
    apply_concierge_plan,
    validate_friction,
)
from .concierge_view import build_concierge_view

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
