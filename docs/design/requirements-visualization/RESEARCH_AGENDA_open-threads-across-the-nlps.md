# Research agenda — open threads across the NLPS analyses (consolidated)

**Date:** 2026-08-17 · **Type:** research agenda (consolidation) · **Status:** the standing research backlog
**Consolidates:** the scattered OQs across `RESEARCH_llm-interpreter-backend-and-realization-facet` (OQ-1..6) ·
`RESEARCH_retrospective-bookend-as-ir-feedback-edge` (OQ-R1..6) · `RESEARCH_cross-corpus-grammar-principles-vs-conventions` ·
`RESEARCH_present-but-dead-lacuna-census` · `ANALYSIS_corpus-self-study-five-threads` · `ANALYSIS_runtime-grounding-feature-and-ai-o11y`.
**Companion:** `NEXT_STEPS_det-doc-kit-family-effort.md` is the *build* roadmap; this is the *research* backlog.

## 0. The meta-finding: the research→spec pipeline worked

Most open questions the research notes raised **metabolized into specs** — evidence the pipeline (research → OQ →
REQ) is functioning. Recording the resolutions so they stop reading as open:

| OQ | Resolved by | 
|----|-------------|
| OQ-6 (realization on edge vs node) | **REQ-16** (edge-carried; node derived) |
| OQ-R1 (Lesson node/edge) · OQ-R2 (proposed/accepted) · OQ-R5 (loop termination) | **REQ-20 / REQ-21** (Lesson node + `revises` edge + status + auto-tier + human gate) |
| OQ-2 (invariant-9 presence vs blocking) | **REQ-22** (presence→liveness) |
| OQ-3 (provenance lift vs reference) | **REQ-28** (AI-o11y is the reference source via the REQ-19 seam) |
| the hypothesis cells | **REQ-25** · the runtime cell | **REQ-28** · plan-liveness | **SCHEMA_det-plan §6** |

## 1. The genuinely OPEN threads (by theme)

### A — Realization (the measured determinism-%)
- **OQ-1 · planned-vs-realized delta** — a node planned `$0` but realized `llm` = a cost-leak signal. REQ-28 FR-3
  surfaces the *finding*; the full **delta model** (a planned-realization field distinct from measured) is open.
- **OQ-4 · rollup semantics** — is the summary a count distribution (28/3/0), a single `%`, or both? How does an
  `llm` leaf with a *failing* verify render? *(Feeds the realization-facet REQ.)*
- **OQ-5 · cross-repo realization value set** — do non-SDK adopters (legal/benchmark) need different `realization`
  values, and does the shared schema enumerate a canonical set + allow extension (RouteState pattern)?

### B — Retrospective bookend (the feedback edge)
- **OQ-R4 · the general lesson-contract bridge** — lift `kaizen-suggestions.json` (and other outcomes) into
  `Lesson` nodes via a typed contract. SARIF/`sarif_to_req_stub` is the *machine* path; a Kaizen-native bridge is open.
- **OQ-R6 · `was` as raw material** — how `was`-deltas (REQ-17) seed Lessons; is a Lesson always `derived-from` a
  `was`-delta, or also from a single-increment outcome?

### C — Grammar / cross-corpus (the Craft Grammar) — the richest open vein
- **Concept-embedding mining** — the cross-corpus mining was *vocabulary*-based (kaizen scored 0% on grounding
  *despite being about it*). Cluster by *meaning* to beat the bias — would likely *raise* the principle count.
- **Convention-promotion tracking** — re-run the move-census after the next corpus; a req-viz-local convention
  (`trust-gate`/`reserve-slot`/`firewall`) that spreads **graduates to a principle**. Watch it.
- **Cross-corpus universality (the strategic one)** — is the grammar universal across *more* repos (legal ·
  benchmark · household)? This is what upgrades "req-viz is self-similar" → "the whole corpus obeys one grammar."
- **Corpus-as-Node-graph + strata overlay** — model each corpus through the navigator, overlay the grammar strata
  (universal / determinism-conditional / schema-family / local) as facets.

### D — Liveness stratification
- **Does liveness stratify FURTHER, beyond runtime?** The column is `FR-gate → REQ-verify → PAIR-companion →
  corpus → RUNTIME-feature-signal`. Is there a cell above runtime (e.g. *adoption* — is the feature actually
  *used*, not just emitting)? An adjudication like the census's is open.

### E — The two IRs (Node + SARIF) — the twin-seam reconciliation
- **Lesson node ↔ SARIF result** and **CRP review-log ↔ SARIF** are *twins* (charter inv. 6/7) — do they
  **reconcile onto one representation** or stay dual? A small design note (offered, not yet written) that prevents
  the retrospective bookend + det-crp-kit from *forking* the findings representation.
- **One unified IR vs two?** — strategic: is SARIF a *projection* of the Node findings, or a peer IR?

### F — The det-doc-kit family
- **When does demand warrant the far cells?** det-handoff / det-howto / det-ledger are deferred (correct-absence
  for now). The research question: what demand signal (companionless count at that altitude) triggers realization?

## 2. Prioritization — research-now vs build-informed

**Research-now (no build prerequisite; emeritus lane):**
1. **Concept-embedding mining** (C) — the flagged upgrade; highest-signal, unblocked.
2. **The two-IR twin reconciliation** (E) — small, prevents a fork before det-crp-kit + the retrospective build.
3. **Cross-corpus universality** (C) — the strategic validation of the Craft Grammar across more repos.

**Build-informed (the deps are now BUILT — REQ-18/19/20 shipped — so these are research-ready, not blocked):**
4. **OQ-1 / OQ-4** (A) — fold into the realization-facet REQ (the delta model + rollup semantics).
5. **OQ-R4 / OQ-R6** (B) — fold into the general retrospective-bridge work.

**Watch (re-run on a trigger):**
6. **Convention-promotion tracking** (C) — re-census after the next corpus lands.

## 3. The next-agent picks (one-liners)

- *"Re-mine the 6 corpora by concept-embedding, not keyword — does the principle count rise?"* (C)
- *"Write the twin-seam note: reconcile Lesson↔SARIF and CRP-log↔SARIF onto one findings representation."* (E)
- *"Extend the cross-corpus grammar census to legal + benchmark + household — universal or req-viz-local?"* (C)
- *"Spec the realization-facet REQ folding OQ-1 (planned-vs-realized delta) + OQ-4 (rollup semantics)."* (A)

**The one-line agenda:** *the research→spec pipeline resolved most OQs into REQs; what remains is a small, themed
backlog — concept-embedding mining and cross-corpus universality (the Craft-Grammar validation), the two-IR
twin reconciliation, and the realization delta/rollup — none blocked, all grounded, each a one-agent pickup.*
