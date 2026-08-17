"""Render a projected :class:`DetPlan` to a ``det-plan/0.1`` markdown document.

Deterministic and idempotent — a **pure function of the** :class:`DetPlan` (no timestamps, no
randomness), so re-projecting the same req yields byte-identical output (the provider's drift check
and FR-8 byte-identity depend on this). Carries a machine marker so the deterministic-file provider
recognizes a projected plan without re-reading the source.
"""

from __future__ import annotations

from typing import List

from .models import DetPlan, Iteration

# The generated-file marker (SCHEMA §10 / provider ``owns``): its presence identifies a projected
# det-plan and must never appear in a hand-authored one.
GENERATED_MARKER = "<!-- GENERATED det-plan/0.1 — projected $0 from the paired det-req by startd8 plan_codegen; do not edit by hand -->"


def _cost_summary(plan: DetPlan) -> str:
    counts: dict = {}
    for it in plan.iterations:
        counts[it.cost_class] = counts.get(it.cost_class, 0) + 1
    return " · ".join(f"{n} {c}" for c, n in sorted(counts.items())) or "—"


def _render_iteration(it: Iteration) -> List[str]:
    lines = [f"### {it.id} — {it.name}", ""]
    lines.append(f"- **FRs:** {', '.join(it.frs)}")
    lines.append(
        f"- **targetFiles:** {', '.join(f'`{f}`' for f in it.target_files) or '—'}"
    )
    lines.append(
        f"- **dependsOn:** {', '.join(it.depends_on) if it.depends_on else '— (no authored dependency)'}"
    )
    lines.append(f"- **costClass:** {it.cost_class}")
    lines.append(f"- **status:** {it.status}")
    lines.append("- **gate (from the FRs' `Verify:`):**")
    if it.gate:
        for g in it.gate:
            lines.append(f"  - {g.fr}: {g.verify}")
    else:
        lines.append("  - — (no FR carried a `Verify:` clause)")
    lines.append("")
    return lines


def render_plan(plan: DetPlan) -> str:
    """Render *plan* as a ``det-plan/0.1`` markdown document (idempotent)."""
    lines: List[str] = [GENERATED_MARKER, ""]
    lines.append(f"# {plan.name} — Implementation Plan (det-plan/0.1)")
    lines.append("")
    lines.append(f"- **version:** {plan.version}")
    lines.append(f"- **formatVersion:** {plan.format_version}")
    lines.append(f"- **pairsWith:** `{plan.pairs_with}`")
    lines.append(f"- **companionKind:** {plan.companion_kind}")
    lines.append(f"- **maturity:** {plan.maturity}")
    lines.append(f"- **handle:** `{plan.handle}`")
    lines.append(f"- **ref:** `{plan.ref}`")
    lines.append("")
    lines.append(
        "> A **det-plan is a `$0` projection of a det-req** — this document is derived, never "
        "authored. Its FR grouping and ordering are the requirement's authored structure; the "
        "strategic build-ordering strategy is the human's to add (the human-gated residue)."
    )
    lines.append("")

    # §2 Iterations
    lines.append("## Iterations")
    lines.append("")
    lines.append(
        f"_{len(plan.iterations)} iteration(s); costClass rollup: {_cost_summary(plan)}._"
    )
    lines.append("")
    for it in plan.iterations:
        lines.extend(_render_iteration(it))

    # §3 Dependencies (the DAG)
    lines.append("## Dependencies (the iteration DAG)")
    lines.append("")
    dep_edges = [(it.id, d) for it in plan.iterations for d in it.depends_on]
    if dep_edges:
        for src, dst in dep_edges:
            lines.append(f"- {src} depends on {dst}")
    else:
        lines.append(
            "- — no authored `Depends:` edges; iterations are independent by the requirement's "
            "declared topology (ordering is the human-gated residue)."
        )
    lines.append("")

    # §4 Reuse (Mottainai) — the phantom audit
    lines.append("## Reuse / phantom audit (§4)")
    lines.append("")
    if plan.reuse_refs:
        for ref, resolved in plan.reuse_refs:
            mark = "✓ resolves" if resolved else "✗ PHANTOM (absent on disk)"
            lines.append(f"- `{ref}` — {mark}")
    else:
        lines.append("- — (no authored `Touches`/code-`Lives` refs)")
    lines.append("")

    # §5 Verify (whole change) — the rollup
    lines.append("## Verify (whole change) — the FR `Verify:` rollup (§5)")
    lines.append("")
    if plan.verify_rollup:
        for g in plan.verify_rollup:
            lines.append(f"- {g.fr}: {g.verify}")
    else:
        lines.append("- — (no FR carried a `Verify:` clause)")
    lines.append("")

    lines.append(
        f"_{plan.format_version} — projected `$0` from the paired det-req; maturity "
        f"`{plan.maturity}` (un-hardened). The projector owns the format's derived fields; the "
        "ordering strategy is the human-gated residue._"
    )
    lines.append("")
    return "\n".join(lines)
