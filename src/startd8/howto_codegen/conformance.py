"""det-howto/0.1 conformance validation + SARIF (STANDARD Part 3, SCHEMA §7).

``validate_howto(...)`` checks a projected ``Howto`` against the SCHEMA §7 conformance rules and
liveness (§3). ``findings_to_sarif(...)`` emits the findings as SARIF 2.1.0 by **importing** the ONE
``coverage_map/findings_sarif.render_sarif_from_findings`` — never vendoring a copy (STANDARD Part 3
/ charter §5). ``HowtoFinding`` is duck-typed for that renderer.
"""

from __future__ import annotations

from typing import Any, List

# STANDARD Part 3 / charter §5: import the ONE SARIF renderer — never vendor a copy.
from ..coverage_map.findings_sarif import render_sarif_from_findings
from .models import (
    COMPANION_KIND,
    FORMAT_VERSION,
    INITIAL_MATURITY,
    Howto,
    HowtoFinding,
)

#: The closed maturity ladder (SCHEMA §4) — a projected howto starts at 0.1 and must not inflate.
_MATURITY_LADDER = ("0.1", "0.2", "0.3", "0.4-post-CRP", "0.5")


def validate_howto(howto: Howto, *, doc_path: str = "<howto>") -> List[HowtoFinding]:
    """Validate a ``Howto`` against SCHEMA §7 conformance + §3 liveness.

    Returns a list of ``HowtoFinding`` (empty ⇒ conformant). Each rule maps to a §7 clause:

    - ``formatVersion == det-howto/0.1`` and ``companionKind == HOWTO``;
    - ``pairsWith`` resolves LIVE (§3) — a howto documenting a PHANTOM/ABSENT REQ is a survivorship
      lie;
    - every ``commands[]`` entry traces to an authored surface (has a ``source``) — no invented
      command;
    - ``prerequisites[]`` mark each ref honestly (a PHANTOM ref surfaces as a finding — the howto
      references something absent, §3);
    - ``maturity`` is not inflated above the projected 0.1 rung (§4);
    - the narrative is NOT machine-asserted as derived (the residue placeholder is present).
    """
    findings: List[HowtoFinding] = []

    def add(check: str, severity: str, message: str) -> None:
        findings.append(
            HowtoFinding(
                check=check, severity=severity, message=message, file_path=doc_path
            )
        )

    if howto.format_version != FORMAT_VERSION:
        add(
            "format-version",
            "error",
            f"formatVersion must be {FORMAT_VERSION!r}, got {howto.format_version!r}.",
        )
    if howto.companion_kind != COMPANION_KIND:
        add(
            "companion-kind",
            "error",
            f"companionKind must be {COMPANION_KIND!r}, got {howto.companion_kind!r}.",
        )

    # §3 liveness — the paired REQ must resolve LIVE.
    if howto.pairs_with_liveness != "LIVE":
        add(
            "pairs-with-liveness",
            "error",
            f"pairsWith {howto.pairs_with!r} is {howto.pairs_with_liveness}, not LIVE — "
            "a howto documenting a non-live REQ is a survivorship lie (§3).",
        )

    # §5 never-inferred — no command may be present without an authored source.
    if not howto.commands:
        add(
            "no-command-surface",
            "error",
            "a det-howto must document at least one command (SCHEMA §5 solo-vs-gap) — "
            "a surfaceless doc should not have been projected.",
        )
    for c in howto.commands:
        if not c.source:
            add(
                "invented-command",
                "error",
                f"command {c.name!r} has no authored source — every command must trace to a "
                "`## Contract projection` row or a CLI-declaring FR (§7).",
            )

    # §2/§3 — a PHANTOM prerequisite is an honest finding (the howto references something absent).
    for p in howto.prerequisites:
        if p.liveness == "PHANTOM":
            add(
                "phantom-prerequisite",
                "warning",
                f"prerequisite {p.ref!r} (declared by {p.declared_by or '?'}) resolves PHANTOM — "
                "the howto references something absent on disk (§3).",
            )

    # §4 anti-inflation — a projected howto starts at 0.1 and must not claim a higher rung.
    if howto.maturity != INITIAL_MATURITY:
        # An inflated stamp is a conformance error unless it's a real ladder rung earned by evidence
        # the projector cannot produce — a *projected* doc is always 0.1 (§4).
        if howto.maturity not in _MATURITY_LADDER or howto.maturity != INITIAL_MATURITY:
            add(
                "inflated-maturity",
                "error",
                f"maturity {howto.maturity!r}: a projected howto starts at {INITIAL_MATURITY!r} "
                "and never claims unearned hardening (§4).",
            )

    # §5 — the narrative must be present as an explicit HUMAN-RESIDUE placeholder, NOT machine-
    # asserted as derived. An empty placeholder would silently imply the narrative was projected.
    if not howto.residue_placeholder.strip():
        add(
            "missing-residue-placeholder",
            "error",
            "the when/why/troubleshooting narrative must be emitted as a human-residue placeholder, "
            "not silently omitted (§5).",
        )

    return findings


def findings_to_sarif(
    findings: List[HowtoFinding], *, tool_version: str = "0.1"
) -> dict[str, Any]:
    """Render conformance findings as SARIF 2.1.0 via the imported renderer (never vendored)."""
    return render_sarif_from_findings(
        findings,
        tool_name="det-howto-projector",
        tool_version=tool_version,
    )
