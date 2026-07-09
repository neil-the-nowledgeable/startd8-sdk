# Role-Based Project Input — Enhancement Roadmap

**Date:** 2026-07-09
**Status:** Roadmap (proposals, prioritized by value/effort)
**Scope:** the stakeholder-panel + `synthesis_bridge` + kickoff-portal subsystem built across PRs
#172–181 (postures, residual/unstructured capture lane, `input_kind` typing, backlog render + guarded
append, opt-in LLM refinement, renderer polish).

> **Strategic thread.** The differentiator is the SDK's ability to produce **useful role-based input on
> a project**. The highest-value moves make that input easier to *elicit*, richer to *structure*, more
> *actionable* downstream, and more *visible* to stakeholders.

---

## Quick wins (hours–1 day; high value)

| ID | Idea | Value | Grounded in |
|----|------|-------|-------------|
| **Q1** | **Triage the single-question ask-all too** — run extract→classify→backlog on `.startd8/stakeholder-panel/` sessions, not only the facilitation synthesis. | The cheap ($0.006) Grafana-drivable survey becomes a first-class, typed input source. Thin edge of A1. | The two stores don't cross-feed; the pipeline only consumes the facilitation synthesis. |
| **Q2** | **`--init` on `kickoff panel backlog --append`** — create a minimal backlog scaffold if the target is missing, then append. | Removes the "hand-create the file first" friction (append is fail-closed on a missing target). | `backlog.py` fails closed on a missing/absent file. |
| **Q3** | **Surface run cost + coverage in the report/backlog header** — one line: cost, item count, coverage %, cross-family corroboration count. | Self-justifying output; proves the "nothing dropped" contract inline. | `TriageReport` has counts; cost lives in the transcript. |
| **Q4** | **Cheap-tier facilitation flag** (`--tier cheap`) — haiku/mini/flash instead of the hard-coded premium de-correlated trio. | ~10× cheaper early-exploration panels → run them more often. | `facilitation.py` FAMILIES = opus-4.8/gpt-5.5/gemini-3.1-pro (~$0.43/run). |
| **Q5** | **Corroboration score as structured data** — parse "CROSS-FAMILY (claude+gpt+gemini)" into a numeric field; sort strongest-signal-first. | Prioritized backlog; the strongest role-consensus rises to the top. | render currently keeps corroboration as raw prose. |

## Functional enhancements (new end-user capability)

- **F1 — Facilitation over HTTP (Grafana-drivable).** *Biggest structural gap:* the multi-round
  facilitation + posture selection is **CLI-only** (no HTTP route), so the prototype-posture UX flow can't
  be driven from the Grafana Workbook. Add `POST /stakeholders/facilitate` + a posture selector in the
  interactive panel → the differentiator becomes a one-click, in-dashboard action.
- **F2 — Ratification / "acted-on" tracking.** Everything is SYNTHETIC & UNRATIFIED with no
  accepted→in-progress→shipped status. Add a lightweight per-item status (or export to ContextCore
  tasks / GitHub issues) → panel output becomes a tracked worklist; closes input→outcome.
- **F3 — Cross-session accumulation + dedup + delta.** Merge N sessions, dedupe near-identical items
  (normalized text/kind), show **delta since last run** → a living, converging backlog, not append-only
  snapshots.
- **F4 — Posture library (extensible).** `prototype`/`scrutiny` proved the pattern; add
  `security-review`, `accessibility`, `cost-review`, `ops-readiness` — role-based input specialized by
  lens.
- **F5 — Export adapters.** Typed backlog → ContextCore tasks (OTel spans), GitHub/Linear issues, CSV.

## Architectural

- **A1 — Unify the two panel artifacts behind one `PanelInput` model + a single triage entry point.**
  The ask-all vs facilitation split (two stores, one pipeline) is an accidental fork; unifying removes
  the "which store?" class and lets every producer feed every consumer. (Q1 is the thin edge.)
- **A2 — Structured synthesis (retire prose-parsing).** The sub-bullet-noise (FR-16) and title-truncation
  (H-6) bugs were symptoms of heuristic markdown parsing. Have R5 emit **structured JSON** (latent
  `kickoff_view` FR-UX-15/16) as the source of truth; keep prose parsing as fallback → eliminates a
  fragility class.
- **A3 — `input_kind` + corroboration as the routing substrate** — declarative per-kind routing (backlog
  / VIPP / issues) once typing is structured.

## Operational / observability

- **O1 — Emit panel metrics** (OTel): `panel_items_total{kind}`, `panel_coverage_ratio`,
  `panel_dropped_lines` (=0 now), `panel_cost_usd`, `corroboration_cross_family_total` — proves the
  contract at runtime; feeds Grafana.
- **O2 — "Panel input status" row on the Digital Project Workbook** — how much role-based input captured,
  by kind, by session → the differentiator made visible to stakeholders.
- **O3 — Cost guardrails surfaced** — projected vs actual + per-project running total.

## Higher-value end-user outputs

- **V1 — Prioritized, corroboration-ranked, deduped backlog** (Q5 + F3) — the single most useful artifact.
- **V2 — A one-page "decision brief"** per session: open tensions + open questions + outside-view base
  rate = *the decisions the human must make* (distinct from the improvement list). Make the household §7
  hand-craft a renderer.
- **V3 — Per-item provenance** (which personas/rounds/models said it) as structured metadata → trust +
  traceability.

## Recommended sequence (value / risk)

1. **Q1** — triage the ask-all → unlocks the cheap Grafana survey as typed input; tiny; de-risks A1.
2. **F1** — facilitation over HTTP + posture in the panel → the highest-leverage capability gap.
3. **Q5 + F3** — corroboration ranking + cross-session dedup/delta → a living prioritized backlog (V1).
4. **A2** — structured synthesis → retires the prose-parsing fragility class.

> **Note (to verify before committing a direction):** confirm current-state assumptions — whether any
> OTel is already emitted by the bridge, whether a ContextCore export path already exists, and the exact
> ask-all session shape — via a grounded audit (done in the paired requirements doc's §0/Reference Audit).
