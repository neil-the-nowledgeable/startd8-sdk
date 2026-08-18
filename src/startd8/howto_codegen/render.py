"""Idempotent render of a ``Howto`` model → the det-howto/0.1 doc text (STANDARD Part 2).

``render_howto(howto)`` is a pure, **idempotent** projection: given the same model it emits the
same bytes. It carries a ``GENERATED_MARKER`` (so the provider's ``owns()`` can recognize it) and
contains **no timestamps** — byte-identity across runs depends on it (STANDARD Part 2, the
``test_render_has_no_timestamp`` invariant). The when/why/troubleshooting narrative is emitted as a
single HUMAN-RESIDUE placeholder (SCHEMA §5), never invented prose.
"""

from __future__ import annotations

from .models import Howto

#: The generated-file marker the provider's ``owns()`` matches (STANDARD Part 4). A stable comment,
#: no timestamp / version-of-generator (which would break byte-identity).
GENERATED_MARKER = "<!-- GENERATED det-howto/0.1 — $0 projection of an authored REQ; do not edit the skeleton by hand -->"


def _render_commands(howto: Howto) -> str:
    if not howto.commands:
        return "_No projected commands._\n"
    lines = [
        "| Command / option | Kind | Note | Source |",
        "|------------------|------|------|--------|",
    ]
    for c in howto.commands:
        note = c.note or "—"
        src = c.source or "—"
        lines.append(f"| `{c.name}` | {c.kind} | {note} | {src} |")
    return "\n".join(lines) + "\n"


def _render_prerequisites(howto: Howto) -> str:
    if not howto.prerequisites:
        return "_No declared prerequisites._\n"
    lines = [
        "| Reference | Liveness | Declared by |",
        "|-----------|----------|-------------|",
    ]
    for p in howto.prerequisites:
        lines.append(f"| `{p.ref}` | {p.liveness} | {p.declared_by or '—'} |")
    return "\n".join(lines) + "\n"


def render_howto(howto: Howto) -> str:
    """Render the ``Howto`` model to its det-howto/0.1 markdown (idempotent, no timestamps)."""
    parts: list[str] = []
    parts.append(GENERATED_MARKER)
    parts.append("")
    parts.append(f"# HOWTO — {howto.title}")
    parts.append("")

    # --- §1 header (core) ---
    parts.append(f"**formatVersion:** `{howto.format_version}`  ")
    parts.append(f"**companionKind:** {howto.companion_kind}  ")
    parts.append(f"**version:** {howto.version}  ")
    parts.append(f"**maturity:** {howto.maturity}  ")
    parts.append(f"**pairsWith:** `{howto.pairs_with}` ({howto.pairs_with_liveness})")
    parts.append("")
    parts.append(f"> **Semantic name:** *{howto.name}*  ")
    parts.append(f"> **Readable handle:** `{howto.handle}`  ")
    parts.append(f"> **Canonical ref:** `{howto.ref}`")
    parts.append("")

    # --- §2 command reference (the projected skeleton) ---
    parts.append("## Command reference")
    parts.append("")
    parts.append(_render_commands(howto).rstrip("\n"))
    parts.append("")
    parts.append("## Prerequisites (reuse / phantom audit)")
    parts.append("")
    parts.append(_render_prerequisites(howto).rstrip("\n"))
    parts.append("")

    # --- §5 human-residue narrative (NOT projected) ---
    parts.append("## When / why / troubleshooting — HUMAN-RESIDUE")
    parts.append("")
    parts.append(f"> {howto.residue_placeholder}")
    parts.append("")
    parts.append(
        "_The command-reference skeleton above is `$0`-projected from the paired REQ's declared "
        "surface. The operator narrative (when to use this, why, and how to recover from failure) "
        "is human-residue — the projector emits this placeholder and never invents guidance._"
    )
    parts.append("")

    return "\n".join(parts)
