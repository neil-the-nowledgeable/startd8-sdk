"""GE-M0 — the guided-experience routing seam (FR-GE-1/2/3/4).

This module owns the decision of *whether to OFFER* the guided experience. It is a small,
$0, read-only seam: no LLM, no writes, no new engine. It adds a *decision + one ignorable
offer line*; it does NOT build the guided flow (that is GE-M1+).

Semantic contract (FR-GE-3, R2-F3 / R3-S5)
------------------------------------------
The guided preference reuses the **precedence *pattern*** of the agent-spec ladder in
``concierge_agent.py`` — flag → per-project ``build-preferences.yaml`` → global
``~/.startd8/config.json`` → default — but it is expressed here as a **semantic contract**,
NOT a verbatim reuse. Crucially, the value domain differs:

* The agent-spec ladder resolves a *non-empty string* and *skips falsy layers* (``_usable``).
  Reusing that verbatim would silently drop an explicit ``guided: false`` at a higher layer
  and fall through to a lower layer's ``true`` — violating FR-GE-4.
* Here the preference is **tri-state**: ``on`` / ``off`` / ``unset``. An explicit ``off``
  (``--no-guided`` or project ``guided: false``) **terminates resolution** and never falls
  through to a lower ``on``. Only ``unset`` (``None``) falls through.

So ``off`` is *load-bearing* and distinct from ``unset`` — the property the string ladder
cannot express. This module does not import ``concierge_agent.py``; a contract test asserts
the tri-state semantics independently and detects upstream drift.

Routing signals (FR-GE-3), highest precedence first
---------------------------------------------------
1. **explicit preference** (flag > project > global > default) — authoritative; ``off`` here
   suppresses the offer no matter what the other signals say.
2. **surface** — a served/TUI invocation implies no-agent ⇒ offer. Overridable by (1).
3. **project-shape** — a greenfield-blank project (``build_assess``: no kickoff inputs present)
   ⇒ a stronger offer; a rich/brownfield project ⇒ quieter.

The result is an **offer**, never a forced path. Default bias is quiet: a wrong offer is one
ignorable line, never a gate. When the explicit preference is ``off``, or when stdout is
non-interactive (piped / CI / ``--json``), the offer line is suppressed entirely so the kernel
path stays byte-identical (FR-GE-1).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Optional

# Project preference path is pinned (mirrors ``concierge_agent._PROJECT_BUILD_PREFS``): this file
# only, never an examples/ or templates/ copy.
_PROJECT_BUILD_PREFS = ("docs", "kickoff", "inputs", "build-preferences.yaml")


class Tri(Enum):
    """A tri-state preference layer value. ``UNSET`` is distinct from ``OFF`` (FR-GE-4)."""

    ON = "on"
    OFF = "off"
    UNSET = "unset"


def coerce_tri(value: Any) -> Tri:
    """Coerce a heterogeneous preference value → :class:`Tri`, preserving the on/off/unset split.

    Accepts real bools (``build-preferences.yaml`` ``guided:`` is a validated bool), ``None``
    (absent ⇒ ``UNSET``), and tolerant string forms from the global JSON config
    (``"on"``/``"true"``/``"yes"`` ⇒ ON; ``"off"``/``"false"``/``"no"`` ⇒ OFF). An empty string
    or an unrecognized value degrades to ``UNSET`` (never crashes, never a silent ``OFF``).
    """
    if value is None:
        return Tri.UNSET
    if isinstance(value, bool):
        return Tri.ON if value else Tri.OFF
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"on", "true", "yes", "1"}:
            return Tri.ON
        if s in {"off", "false", "no", "0"}:
            return Tri.OFF
        return Tri.UNSET
    return Tri.UNSET


@dataclass(frozen=True)
class PreferenceResolution:
    """The resolved explicit-preference layer: the tri-state value + the layer that decided it."""

    value: Tri
    source: str  # "flag" | "project" | "global" | "default"


def _project_guided(project_root: str | Path) -> Tri:
    """Read tri-state ``guided`` from the project's ``build-preferences.yaml``; skip on any error."""
    path = Path(project_root).expanduser().joinpath(*_PROJECT_BUILD_PREFS)
    if not path.is_file():
        return Tri.UNSET
    try:
        from ..kickoff_inputs import parse_build_preferences

        return coerce_tri(parse_build_preferences(path.read_text(encoding="utf-8")).guided)
    except Exception:
        # Malformed sheet / IO error → skip this layer (degrade to the next), never crash.
        return Tri.UNSET


def _global_guided() -> Tri:
    """Read tri-state ``guided`` from the global ``~/.startd8/config.json`` preferences; skip on error."""
    try:
        from ..config import get_config_manager

        return coerce_tri(get_config_manager().get_preference("guided"))
    except Exception:
        return Tri.UNSET


def resolve_guided_preference(
    project_root: str | Path,
    flag: Optional[bool] = None,
) -> PreferenceResolution:
    """Resolve the explicit guided preference by the tri-state precedence ladder (FR-GE-3/4).

    Precedence: ``--guided/--no-guided`` flag > project ``build-preferences.yaml`` > global
    ``~/.startd8/config.json`` > default (``UNSET``). The **first layer that expresses an explicit
    value (ON or OFF) wins and terminates resolution** — an ``OFF`` never falls through to a lower
    ``ON`` (the tri-state guarantee; FR-GE-4). ``flag`` is a real tri-state: ``True`` (``--guided``),
    ``False`` (``--no-guided``), or ``None`` (neither flag passed ⇒ fall through).
    """
    flag_tri = coerce_tri(flag)
    if flag_tri is not Tri.UNSET:
        return PreferenceResolution(flag_tri, "flag")
    project_tri = _project_guided(project_root)
    if project_tri is not Tri.UNSET:
        return PreferenceResolution(project_tri, "project")
    global_tri = _global_guided()
    if global_tri is not Tri.UNSET:
        return PreferenceResolution(global_tri, "global")
    return PreferenceResolution(Tri.UNSET, "default")


class OfferStrength(Enum):
    """How strongly to surface the offer. ``NONE`` ⇒ no line at all (kernel byte-identical)."""

    NONE = "none"
    QUIET = "quiet"
    STRONG = "strong"


@dataclass(frozen=True)
class GuidedRoutingDecision:
    """The computed routing decision — an *offer*, never a gate (FR-GE-3)."""

    preference: PreferenceResolution
    offer: OfferStrength
    # True iff the flow should actually engage guided (only on an explicit force-on). GE-M0 never
    # engages a flow (there is none yet); this exists so callers can branch in GE-M1+ without
    # re-deriving the ladder. An offer is NOT engagement.
    engaged: bool
    reason: str

    @property
    def offered(self) -> bool:
        return self.offer is not OfferStrength.NONE


def _project_is_greenfield_blank(assess: Optional[Mapping[str, Any]]) -> bool:
    """Project-shape signal (3): greenfield-blank ⇒ no kickoff input domain is present.

    Reads only the ``build_assess`` payload the caller already computed (no recompute, no new
    engine — FR-GE-6). Absent/degraded assess ⇒ treat as *not* blank (bias quiet).
    """
    if not assess:
        return False
    try:
        domains = assess["kickoff_inputs"]["domains"]
    except (KeyError, TypeError):
        return False
    if not domains:
        return False
    # Greenfield-blank = nothing present yet (all absent). A single present domain ⇒ brownfield.
    return all(info.get("status") != "present" for info in domains.values())


def decide_guided_routing(
    project_root: str | Path,
    *,
    flag: Optional[bool] = None,
    served_surface: bool = False,
    assess: Optional[Mapping[str, Any]] = None,
    interactive: bool = True,
) -> GuidedRoutingDecision:
    """Compute whether to OFFER the guided experience — the GE-M0 routing seam (FR-GE-3).

    Signals, in precedence:
      1. explicit preference (``resolve_guided_preference``) — ``ON`` forces the offer (and marks
         ``engaged``); ``OFF`` suppresses it entirely, no matter the other signals (FR-GE-4).
      2. ``served_surface`` — a served/TUI invocation ⇒ offer (overridable by (1)).
      3. project-shape (``assess``) — greenfield-blank ⇒ a *stronger* offer.

    Non-interactive (``interactive=False``: piped / CI / ``--json``) suppresses the offer line
    but never blocks — the kernel path stays byte-identical (FR-GE-1). This function is pure and
    $0: it decides only; it writes nothing and calls no LLM.
    """
    pref = resolve_guided_preference(project_root, flag)

    # (1) explicit force-off — authoritative, terminates. Distinct from unset (tri-state).
    if pref.value is Tri.OFF:
        return GuidedRoutingDecision(pref, OfferStrength.NONE, False, "explicit force-off")

    # Non-interactive suppresses the *offer line* (but an explicit force-on below still engages).
    if not interactive:
        engaged = pref.value is Tri.ON
        return GuidedRoutingDecision(
            pref, OfferStrength.NONE, engaged,
            "non-interactive: offer suppressed" + ("; forced-on engages" if engaged else ""),
        )

    # (1) explicit force-on — offer + engage.
    if pref.value is Tri.ON:
        return GuidedRoutingDecision(pref, OfferStrength.STRONG, True, "explicit force-on")

    # pref is UNSET → fall to the softer signals. Default bias is quiet.
    blank = _project_is_greenfield_blank(assess)
    if served_surface:
        strength = OfferStrength.STRONG if blank else OfferStrength.QUIET
        reason = "served surface" + (" + greenfield-blank" if blank else "")
        return GuidedRoutingDecision(pref, strength, False, reason)
    if blank:
        return GuidedRoutingDecision(pref, OfferStrength.QUIET, False, "greenfield-blank project")

    # No signal argues for an offer → stay silent (byte-identical kernel path).
    return GuidedRoutingDecision(pref, OfferStrength.NONE, False, "no offer signal")


# The single, ignorable offer line (FR-GE-3): one line, no gate, no prompt. Callers emit it to the
# *error* stream so it never perturbs stdout / ``--json`` / kernel bytes (FR-GE-1).
_OFFER_LINE = (
    "[dim]Tip: a guided kickoff can walk you through this step by step — "
    "run [cyan]startd8 kickoff --guided[/cyan] (or [cyan]--no-guided[/cyan] to silence this).[/dim]"
)


def offer_line(decision: GuidedRoutingDecision) -> Optional[str]:
    """Return the one ignorable offer line to show, or ``None`` when no offer should surface.

    Rich markup string; the caller renders it on stderr. Returns ``None`` for ``OfferStrength.NONE``
    so the kernel path emits nothing (byte-identical).
    """
    if decision.offer is OfferStrength.NONE:
        return None
    return _OFFER_LINE
