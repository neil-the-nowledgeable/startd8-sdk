"""Kickoff presentation / information-architecture layer (KICKOFF_UX spec) — the SINGLE source of
user-facing naming and the progress spine. Pure, `$0`, surface-neutral (CLI now; the web rail later).

Owns the plain-language vocabulary (`GLOSSARY`) so no surface hardcodes a plain name (FR-UX-2), and the
"three things + Build" spine + headline derived from the existing `RedCarpetState` (FR-UX-1/4/6/7/8) —
**renaming, not restructuring** (the spine IS the 5 stages, glossary-named).

Design honesty (CRP R1):
- **Build never renders "✓ done"** — `run.status=="done"` means *offerable, not built* → a distinct
  `ready` status (R1-F1). `content` is an optional add-on, de-emphasized, not a peer.
- The completion % is **"% filled," not "buildable"** — presence-based, counts defaults; the headline
  annotates "not yet buildable" / "N to review" so 100% never misleads (R1-F3).
- `error`-severity advisories are **never** hidden — the headline carries their count (R1-F4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional

# ── The single-source glossary (FR-UX-2) ──────────────────────────────────────────────────────────
GLOSSARY = {
    "data_model": "Your data",
    "manifests": "Your screens",
    "value_inputs": "Your settings",
    "content": "Placeholder content",
    "run": "Build",
}
WHAT_IS = {
    "data_model": "the things your app stores",
    "manifests": "the pages & views built from your data",
    "value_inputs": "a few choices — language, money format, budget…",
    "content": "starter copy / test data (optional)",
    "run": "generate the app ($0)",
}
# The "three things the user provides" (FR-UX-1) — data → screens → settings. content/run are not peers.
PROVIDES = ("data_model", "manifests", "value_inputs")

# Jargon the no-jargon guard forbids in user-facing (non-`--json`) copy (FR-UX-2, expanded per CRP R1-F2).
JARGON_TOKENS = (
    "cascade", "manifest", "value_path", "prisma", "schema", "@relation", "@@id",
    "provenance", "gate", "bookend", "buckets", "data_model", "value_inputs", "pydantic",
)


def plain(stage_key: str) -> str:
    """The single plain name for an internal stage key (FR-UX-2)."""
    return GLOSSARY.get(stage_key, stage_key)


def has_jargon(text: str) -> Optional[str]:
    """Return the first forbidden token found in *text* (case-insensitive), or None. The no-jargon guard."""
    low = str(text or "").lower()
    return next((t for t in JARGON_TOKENS if t in low), None)


@dataclass(frozen=True)
class SpineNode:
    key: str
    plain_name: str
    status: str                    # done | next | todo | later | ready
    filled: Optional[int] = None
    total: Optional[int] = None
    optional: bool = False         # content — an add-on, not a peer

    def to_dict(self) -> dict:
        d = {"key": self.key, "name": self.plain_name, "status": self.status, "optional": self.optional}
        if self.filled is not None:
            d["filled"] = self.filled
            d["total"] = self.total
        return d


def build_spine(state: Any) -> List[SpineNode]:
    """The three-things + Build spine (FR-UX-1/6) — the 5 stages, glossary-named, status corrected:
    Build → `ready` (never `done`); content → `later` (optional add-on)."""
    comp_stages = {s.get("stage"): s for s in ((getattr(state, "completion", None) or {}).get("stages") or [])}
    next_stage = getattr(state, "next_stage", None)
    nodes: List[SpineNode] = []
    for st in getattr(state, "stages", ()):
        key = st.key
        if key == "run":
            status = "ready" if st.status == "done" else "todo"   # offerable ≠ built (CRP R1-F1)
        elif key == "content":
            status = "later"
        else:
            status = "done" if st.status == "done" else ("next" if key == next_stage else "todo")
        c = comp_stages.get(key) or {}
        nodes.append(SpineNode(
            key, plain(key), status,
            filled=c.get("filled"), total=c.get("total"), optional=(key == "content"),
        ))
    return nodes


def _first_gap(spine: List[SpineNode]) -> Optional[SpineNode]:
    """The first real gap among the three things the user provides (the 'you are here')."""
    for n in spine:
        if n.key in PROVIDES and n.status in ("next", "todo"):
            return n
    return None


# The resolvable next-action commands. Post-M0 the red-carpet metaphor moved to `kickoff-legacy`, so a
# bare `startd8 kickoff red-carpet …` NO LONGER RESOLVES ("No such command 'red-carpet'"). This is the
# "every emitted command MUST resolve" trap that already bit concierge/core.py and red_carpet_advisor.py
# (fix c2ab1864) — this headline was the third emitter still on the stale form. Single-sourced here so a
# rename can't silently re-introduce it; a resolution guard test locks it in.
CMD_WIZARD = "startd8 kickoff-legacy red-carpet --wizard"
CMD_REVIEW = "startd8 kickoff-legacy red-carpet --verbose"
CMD_BUILD = "startd8 generate backend"


def headline(state: Any) -> dict:
    """The one-line status headline (FR-UX-4/7/8): the '% filled' meter (honest annotations), the plain
    'you are here', the single next action (derived from the spine — jargon-free by construction, not from
    playbook prose), and the never-hidden error count (CRP R1-F3/F4)."""
    comp = getattr(state, "completion", None) or {}
    pct = comp.get("overall_pct")
    n_def = comp.get("n_defaulted", 0)
    unmet = tuple(getattr(state, "unmet_gates", ()) or ())
    buildable = bool(getattr(state, "cascade_offerable", False))
    advs = getattr(state, "advisories", ()) or ()
    n_err = sum(1 for a in advs if getattr(a, "severity", None) == "error")

    spine = build_spine(state)
    gap = _first_gap(spine)
    greenfield = (pct == 0) and ("schema" in unmet)

    # The single next action — plain by construction (spine name + a fixed command, never playbook prose,
    # so no jargon can leak in). Any incomplete state → the guided $0 wizard; done → Build.
    if greenfield:
        na_title = "Not started — begin with Your data"
        cmd = CMD_WIZARD
    elif gap is not None:
        na_title = f"{'Start with' if gap.key == 'data_model' else 'Add'} {gap.plain_name}"
        cmd = CMD_WIZARD
    elif buildable:
        na_title = "Ready to Build"
        cmd = CMD_BUILD
    else:
        na_title = "Review remaining gaps"
        cmd = CMD_REVIEW

    # "% filled," honestly annotated (CRP R1-F3).
    label = "—" if pct is None else f"{pct}% filled"
    if pct == 100 and not buildable:
        label += " · not yet buildable"
    if n_def and pct:
        label += f" · {n_def} to review"

    return {
        "pct": pct,
        "pct_label": label,
        "you_are_here": (gap.plain_name if gap else ("Build" if buildable else "—")),
        "next_action": {"title": na_title, "command": cmd},
        "n_errors": n_err,               # never hidden (CRP R1-F4)
        "greenfield": greenfield,
    }


def render_wizard_step(state: Any) -> List[str]:
    """FR-UX-9 (CRP R1-S1) — the compact per-step render the driver calls as ``render_state(state)``.
    Consumes ``state`` (the action is computed by the driver after this call). Just the spine header +
    'you are here' — the found/needed/action lines are emitted by the driver from the (now
    glossary-translated) WizardAction."""
    # The three things the user provides (exclude the `content` add-on and the `run`/Build destination),
    # so the dot row and the "N/M done" count are over the SAME set.
    real = [n for n in build_spine(state) if not n.optional and n.key != "run"]
    done = sum(1 for n in real if n.status == "done")
    hl = headline(state)
    dots = "".join("●" if n.status == "done" else ("◉" if n.status == "next" else "◌") for n in real)
    return [
        f"  {dots}   {done}/{len(real)} done · {hl['pct_label']}",
        f"  → {hl['you_are_here']}",
    ]
