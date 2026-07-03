# Persona-Drafting Family — Enhancement Backlog

**Date:** 2026-07-03
**Owner:** neil-the-nowledgeable
**Scope:** The three persona-drafting siblings — **Stakeholder Panel** (`stakeholder_panel/`, shipped),
**Requirements Panel** (`requirements_panel/`, built on `feat/requirements-panel`), **Manifest
Suggester** (`../kickoff/MANIFEST_SUGGESTER_*.md`, design-only) — plus the `$0` codegen cascade.

> **The core insight.** The three siblings + the cascade form a **latent greenfield pipeline** (idea →
> requirements → plan → screens → working app), but today they are **disconnected CLI islands**, and the
> free tier **dead-ends**: `startd8 requirements elicit` without `--roles` produces a baseline of
> `<needs-owner>` stubs the readiness gate (correctly) refuses to approve. The highest-leverage work is
> **connecting the chain** and **removing first-run friction** — not new engines.

Effort = S/M/L. Value audience = **user** (end-user of the SDK) / **dev** (SDK maintainer). Status =
`backlog` / `speccing` / `building` / `done`.

---

## Tier 1 — Highest value (end-user facing)

| # | Item | Why | Effort | Value | Status |
|---|------|-----|--------|-------|--------|
| 1 | **Default requirements roster** + `startd8 requirements init-roster` (resolve OQ-RP-7) | `elicit --roles` *fails* with "no roster" for exactly the greenfield users who'd benefit. `domains.py` already names default owning roles; there's just no shipped `stakeholders.yaml`. | S | user | **speccing → building** (FR-RP-10) |
| 2 | **Kill the free-tier dead-end** — `review` turns readiness blockers into a to-do list; add a fill-stub affordance | The user's *first* action (`$0` baseline) yields something structurally un-approvable. Turn the gate's blockers into next steps. | S–M | user | backlog |
| 3 | **Connect the chain** — `approve` auto-stages the CRP focus file + emits the reflective-requirements / wireframe next step (FR-RP-9 is only a printed pointer today) | Makes "greenfield in ~5 commands" feel like a product, not parts. | M | user | backlog |
| 4 | **Advisory readiness / coverage score** in `review` (resolve OQ-RP-8) — per-area drafted, grounding-flag count, unowned-stub count, near-duplicate count | "How done am I?" The data is already in the assembled doc; pure presentation. Answers Ask-5 (make the paid pass's value observable). | S | user | **speccing → building** (FR-RP-11) |

## Tier 2 — Functional quick wins

| # | Item | Why | Effort | Value | Status |
|---|------|-----|--------|-------|--------|
| 5 | `--json` on `synthesize`/`review`/`approve` (only `elicit` has it) | Scriptable/CI-able; the agentic/Concierge surface can drive the loop. | S | dev | backlog |
| 6 | `review --diff` against an existing doc | Turns the one-shot `O_EXCL` lifecycle from a limitation into an iteration story. | M | user | backlog |
| 7 | Surface grounding flags in the `elicit --roles` summary | Candidates stage *with* flags, but the summary prints only counts. | S | user | backlog |
| 8 | CLI-level tests (`CliRunner`) for elicit/synthesize/review/approve | Library + mock-panel elicit are tested; command wiring is not. | S | dev | backlog |
| 9 | `CandidateStore` session GC | Mirrored `ProposalStore`'s shape but not its `gc_stale_proposals`; sessions leak. | S | dev | **building** (folded into toolkit) |

## Tier 3 — Architectural quick wins

| # | Item | Why | Effort | Value | Status |
|---|------|-----|--------|-------|--------|
| 10 | **Extract a shared `persona_drafting` toolkit** — heading sanitization, the atomic session-store shape, bounded owner-resolution | These are **triplicated** across the three siblings (a second copy of the store shape was just written). Factoring them out **de-risks and speeds the Manifest Suggester build**. | M | dev | **speccing → building** (toolkit reqs) |
| 11 | Unify bounded owner-resolution (`resolve_bounded_owner(owning_role, aliases, symbol, briefs)`) | `input_domains.resolve_owner`, `resolve_requirement_owner`, and the Suggester's planned one are the same algorithm. | S | dev | **building** (in toolkit) |
| 12 | Shared provenance vocabulary (enum spanning `baseline`/`estimate`/`human` + panel tiers) | Per-feature ad-hoc strings drift; a shared enum enables a unified "AI-drafted vs human" view across artifacts. | S | dev | backlog |
| 13 | Capability-index + MCP exposure for the Requirements Panel | Invisible to the capability manifest/agent card today. `review` (read-only) + the `$0` baseline are natural MCP tools for the agentic surface. | S–M | dev | backlog |

## Tier 4 — Operational enhancements

| # | Item | Why | Effort | Value | Status |
|---|------|-----|--------|-------|--------|
| 14 | OTel metrics + a small Grafana panel (elicit cost, areas-drafted, flag-count) via `/dbrd-cr8r` | The `requirements.elicit_pass` span already fires; makes the paid-pass value observable (Ask-5). | M | dev | backlog |
| 15 | Persist the rendered doc + provenance manifest per session (Mottainai) | Only candidates are staged; the assembled artifact is re-synthesized each time — no audit trail, blocks `--diff`. | S | dev | backlog |
| 16 | P1 banner on the approved doc — "Draft — estimate provenance; you own the intent." | Reinforces the load-bearing bucket-4 boundary at the artifact level. | S | user | backlog |

## Tier 5 — Build-next (de-risked by the Requirements Panel)

| # | Item | Why | Effort | Value | Status |
|---|------|-----|--------|-------|--------|
| 17 | **Build the Manifest Suggester** | Triaged spec is ready; the Requirements Panel proved the exact pattern. Fast follow once the toolkit (#10) exists. | L | user | backlog |
| 18 | Wire `elicit` into `reflective-requirements` Phase 1 (seed v0.1) | Closes the P6 dogfood loop for real. | M | dev | backlog |

---

## Honest gaps surfaced while building (product decisions, not bugs)

1. **The `$0` free tier can never be approved as-is** — the readiness gate blocks unowned stubs by design,
   so the free tier is a *scaffold you must edit*, never a shippable doc. Items #2/#4 soften this;
   confirm it is the intended product shape.
2. **Synthesis dedupe is exact-slug keep-both** (never drops — R1-F3), so genuinely-duplicate FRs phrased
   differently accumulate as two. The coverage score (#4) surfaces "N near-duplicate titles" for the
   human to merge — deliberately advisory, never automatic.
3. **`entities_referenced` matching** in `elicit` uses a word-boundary regex on the body; a persona
   referencing an entity in a possessive/plural form ("Users'") may under-detect. Mitigated by the prompt
   supplying literal names (R2-F3); noted as a known limitation.

---

## This increment (M-series)

Building the three highest-leverage items now, requirements-first:

- **A — Default roster (FR-RP-10)** — `docs/design/requirements-panel/REQUIREMENTS_PANEL_REQUIREMENTS.md` v0.5.
- **B — Readiness/coverage score (FR-RP-11)** — same doc.
- **C — Shared `persona_drafting` toolkit** — `docs/design/persona-drafting/PERSONA_DRAFTING_TOOLKIT_REQUIREMENTS.md`.

Together: unblock the paid pass, make progress legible, and halve the cost of the next sibling.
