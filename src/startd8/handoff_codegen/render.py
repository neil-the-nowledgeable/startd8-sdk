"""Render a projected :class:`Handoff` to a ``det-handoff/0.1`` markdown document.

Deterministic + idempotent — a pure function of the :class:`Handoff` (no timestamps, no randomness),
so re-projecting the same REQ yields byte-identical output (provider drift-check + byte-identity).
Carries a machine marker so the deterministic-file provider recognizes a projected handoff.
"""

from __future__ import annotations

from typing import List

from .models import Handoff

GENERATED_MARKER = "<!-- GENERATED det-handoff/0.1 — projected $0 from the paired REQ + ledger by startd8 handoff_codegen; do not edit by hand -->"


def render_handoff(handoff: Handoff) -> str:
    """Render *handoff* as a ``det-handoff/0.1`` markdown document (idempotent)."""
    h = handoff
    lines: List[str] = [GENERATED_MARKER, ""]
    lines.append(f"# Handoff: {h.name}")
    lines.append("")
    lines.append(f"- **version:** {h.version}")
    lines.append(f"- **formatVersion:** {h.format_version}")
    lines.append(f"- **pairsWith:** `{h.pairs_with}`")
    lines.append(f"- **base:** {h.base}")
    lines.append(f"- **companionKind:** {h.companion_kind}")
    lines.append(f"- **maturity:** {h.maturity}")
    lines.append(f"- **handle:** `{h.handle}`")
    lines.append(f"- **ref:** `{h.ref}`")
    lines.append("")
    lines.append(
        "> A **det-handoff is a `$0` projection of a REQ + the delivery ledger** — this document is "
        "derived, never authored. Its spine (spec · build order · exit criteria · prerequisites · "
        "pointers · hand-back) is projected; the Gotchas + framing are the human's to fill (§5)."
    )
    lines.append("")

    lines.append("## Spec")
    lines.append("")
    lines.append(f"- {h.spec}")
    lines.append("")

    lines.append("## Build order (the REQ's FRs, in sequence)")
    lines.append("")
    if h.build_order:
        for step in h.build_order:
            lines.append(f"- **{step.fr}** — {step.name}")
    else:
        lines.append("- — (the REQ declares no FRs)")
    lines.append("")

    lines.append("## Hard exit criteria (from the FRs' `Verify:`)")
    lines.append("")
    have = [s for s in h.build_order if s.verify]
    if have:
        for step in have:
            lines.append(f"- {step.fr}: {step.verify}")
    else:
        lines.append("- — (no FR carried a `Verify:` clause)")
    lines.append("")

    lines.append("## Prerequisite status (reuse audit — build-ready iff all resolve)")
    lines.append("")
    if h.prerequisites:
        for p in h.prerequisites:
            mark = "✓ resolves" if p.resolved else "✗ PHANTOM (absent on disk)"
            lines.append(f"- `{p.ref}` — {mark}")
    else:
        lines.append("- — (no authored reuse refs)")
    lines.append("")

    lines.append("## Pointers (where to look)")
    lines.append("")
    if h.pointers:
        for ref in h.pointers:
            lines.append(f"- `{ref}`")
    else:
        lines.append("- — (none)")
    lines.append("")

    lines.append("## What to hand back (the REQ's objectives)")
    lines.append("")
    if h.hand_back:
        for hb in h.hand_back:
            lines.append(f"- {hb}")
    else:
        lines.append("- — (the REQ declares no objectives)")
    lines.append("")

    # §5 human-residue — placeholders, NEVER projected content.
    lines.append("## Gotchas (this repo / this session)")
    lines.append("")
    lines.append(h.gotchas_placeholder)
    lines.append("")
    lines.append("## Why now / framing")
    lines.append("")
    lines.append(h.framing_placeholder)
    lines.append("")

    lines.append(
        f"_{h.format_version} — projected `$0` from the paired REQ + ledger; maturity "
        f"`{h.maturity}` (un-hardened). The spine is derived; the Gotchas + framing are human-residue._"
    )
    lines.append("")
    return "\n".join(lines)
