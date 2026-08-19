# Wire the Draft-Time Firing Seam (the one seam every metabolized theme queues at) — Requirements

**Project:** startd8-sdk (cross-repo: dev-os `det-req-kit` + the CRP review-prompt generator)   **Criticality:** high
**Version:** 0.1   **Date:** 2026-08-17
**Format:** det-req/0.1
**Backend:** python-cli-surface
**Pairs with:** *(plan deferred — spec-only; delivered via the Spec Delivery Loop)* · **`SYNTHESIS_crp-theme-metabolization-four-investigations.md`** (§1 convergence, §4 the two wires) · `ANALYSIS_crp-index-review-wisdom-into-grammar.md` · `CHARTER_det-doc-kit-family.md` · `REQ-22/23` (the fact-cell precedent this generalizes) · `REQ-25` (fact-rung/judgment-rung) · `REQ-07` (the precision gate + the 0-vs-2/2 false-positive data)
**Inherits standards:** det-req-kit · NAMING_CONVENTION / DIDL · REQ-06 (govern) · REQ-07 (advisory — never cry wolf) · Mottainai (own a format, cite a generator) · KAIZEN (don't discard lessons)
**Audience:** requirement author / reviewer / det-req-kit owner / CRP-generator owner
**Trust boundary:** local; advisory (candidate/gap), never blocking, never auto-applies; the review-prompt injection is read-only text; the draft-time lint extends an existing exit-unchanged advisory tier
**Data classification:** internal

> **Readable handle:** `feature/det-doc-kit-fires-metabolized-themes-at-draft-time-7b64892c`
> **Semantic name:** *The det-doc-kit family fires its metabolized review themes at draft time by wiring the single missing firing seam in two ends — injecting the settled-corpus-themes block from the CRP census into every generated review prompt, and landing the fact-rung theme lints as advisory content checks in the det-req extractor — then completing the REQ-01 FR-4 keyed-lookup hook and syncing the pattern catalog, so accumulated review wisdom surfaces before review instead of being re-derived, all advisory and reuse-only.*
> **Canonical ref:** `cc:intent:requirements-visualization:feature:req-32`

## 0. Why this exists — one seam, not N lints

Four parallel investigations metabolized the top ~1,700 of CRP-INDEX's 7,299 accepted review suggestions into
concrete grammar rules (ambiguity #2 · schema #3 · lifecycle #6 · error/security/concurrency/determinism). They
**converged**: every theme's rule lands at exactly one place — a *draft-time firing wire* — and that wire's
**absence is the re-seeking dormancy** the corpus keeps paying for (the same concern re-derived review after
review). The whole metabolization pipeline is already built end-to-end — census (`render_crp_index.py`) → catalog
(`PATTERN-CATALOG` + `pattern_catalog recall`) → metabolizer (`/metabolize-finding`) → host
(`det-req-kit/extract.py::collect_findings`) — and wired at the *routing* level by `LOOP_CATALOG #7`. **Only the
firing seam is missing.** This REQ wires it once so that (a) every theme lint becomes a small additive predicate,
and (b) the dormancy resolves as a side effect. It is the prerequisite for the ambiguity / atomic-write / security
fact-rungs and for REQ-30/REQ-31 (schema `Emits:` / lifecycle `Lifecycle:`).

## Design decisions

- **Wire once, add predicates forever.** The seam is the investment; each metabolized theme is then a single
  predicate (542 ambiguity re-derivations collapse to one lint). Do not build a per-theme engine.
- **Two ends of the same wire.** Fuel the **review** surface (inject settled themes into the generated prompt so
  a reviewer does not re-derive) *and* the **draft** surface (fire the fact-rung lint at authoring so the draft
  already satisfies the rule). The draft end is the true shift-left; the review end is the cheap high-leverage half.
- **Fact ships, judgment parks (REQ-25 / REQ-07 FR-7).** Only structural fact-rungs fire by default (they cannot
  cry wolf); semantic judgment-rungs stay parked behind the precision gate — the corpus's own 0-vs-2/2 data says
  an un-gated ambiguity heuristic will false-fire like weak-verify.
- **Reuse, don't build.** The census, the catalog, `recall`, and `collect_findings`' advisory tier all exist; this
  REQ connects them. The keyed-lookup hook is `REQ-01 FR-4` (currently *Partial*) — complete it, don't re-invent it.
- **Advisory, never blocking, never auto-applied.** Both ends emit advisory text/findings; nothing gates a build
  or edits a draft autonomously.

## Overview

Land two connections: (1) the CRP review-prompt generator injects a *"settled corpus themes — do not re-derive"*
block sourced from the census/catalog into every generated prompt; (2) the det-req extractor fires the fact-rung
theme lints as advisory (exit-unchanged) content checks in `collect_findings`, with judgment-rungs parked behind
the REQ-07 precision gate. Complete the `REQ-01 FR-4` keyed-lookup hook and run `pattern_catalog sync` so the
promoted themes (PC-16..18 and successors) are actually queryable, and register the closing loop as
`LOOP_CATALOG #8` with re-seek rate as its moving number. Additive, advisory, reuse-only.

## Objectives

- **O-1:** A settled theme surfaces before it is re-derived — target: a promoted theme appears in the generated review prompt and (for its fact-rung) as a draft-time advisory finding, instead of being re-sought in review.
- **O-2:** The seam is wired once and every theme is then additive — target: adding a new metabolized theme requires only one predicate + one catalog entry, no new engine and no change to the firing mechanism.
- **O-3:** Honest and non-disruptive — target: only fact-rungs fire by default; judgment-rungs park behind the precision gate; both ends are advisory, reuse existing pieces, and never auto-apply or block.

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | A judgment-rung lint cries wolf (the weak-verify 2-of-2 false-positive class) | FR-3: only fact-rungs fire by default; judgment-rungs park behind the REQ-07 precision gate and ship only as dismissible candidates | high |
| scope | Building a new per-theme engine instead of wiring the existing seam | NR-2: reuse the census / catalog / `recall` / `collect_findings`; each theme is one additive predicate | high |
| integrity | The wire auto-applies a lint or blocks the build | NR-1/NR-3: both ends are advisory text/findings; exit code unchanged; nothing edits a draft or gates a build autonomously | high |
| dependency | The keyed-lookup hook and catalog are half-built (REQ-01 FR-4 Partial; PC-16..18 not synced) | FR-4: complete FR-4 and run `pattern_catalog sync` so the promoted themes are queryable | medium |
| quality | The injected prompt block goes stale as the census changes | FR-1: the block is sourced from the live census/catalog at generation time, not a hand-copied snapshot | medium |

## Functional requirements

- **FR-1 — Review-surface wire (fuel the reviewer).** The CRP review-prompt generator injects a settled-corpus-themes block, sourced live from the census and catalog at generation time, into every generated prompt so a reviewer does not re-derive a concern the corpus has already settled. Name: The CRP review-prompt generator injects a live settled-themes block so reviewers stop re-deriving settled concerns. Touches: `~/.claude/skills/new-cnvrg-rvw-prmpt/SKILL.md`, `dev-os/CRP-INDEX.md`, `dev-os/PATTERN-CATALOG.md`. Lives: doc ~/.claude/skills/new-cnvrg-rvw-prmpt/SKILL.md. Approve?: does every generated review prompt carry a live settled-themes block from the census and catalog?. Verify: a generated prompt contains a settled-themes section whose entries derive from the current census and catalog, and regenerating after a catalog change reflects the change. Serves: O-1

- **FR-2 — Draft-surface wire (fuel the author).** The det-req extractor fires the fact-rung theme lints as advisory content checks in `collect_findings`, at the same exit-unchanged tier as the shipped `user_outcome_verify_advisory`, so a draft satisfies a metabolized rule before review runs. Name: The det-req extractor fires fact-rung theme lints as advisory content checks at draft time. Touches: `dev-os/det-req-kit/extract.py`, `dev-os/det-req-kit/SCHEMA.md`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: do the fact-rung theme lints fire as advisory findings at draft time without changing exit code?. Verify: a draft carrying a placeholder or open-enumeration or unresolved-binary marker yields the corresponding advisory finding; a clean draft yields none; the process exit code is unchanged either way. Serves: O-1, O-3

- **FR-3 — Fact ships, judgment parks (the honesty gate).** Only structural fact-rungs fire by default; semantic judgment-rungs are declared for column-completeness but execute nothing until they clear the REQ-07 precision threshold on a labeled fixture set, and even then ship only as dismissible candidates, never as GAPs. Name: Only fact-rungs fire by default and judgment-rungs stay parked behind the precision gate. Touches: `dev-os/det-req-kit/extract.py`, tests. Lives: code dev-os/det-req-kit/extract.py. Approve?: are judgment-rung lints parked by default and gated on a precision threshold?. Verify: a weasel-word or undefined-term draft yields no default finding; enabling the parked candidate tier surfaces it as an evidence-citing candidate, never a GAP; a false candidate is dismissible in one glance. Serves: O-3

- **FR-4 — Complete the keyed lookup and sync the catalog.** Complete the `REQ-01 FR-4` keyed lookup (replace the prose "consult the base" step with a `pattern_catalog recall` call at the reflective-loop draft slot, and run its stop/rollback gate) and run `pattern_catalog sync` so the promoted themes (PC-16..18 and successors) are actually in the recall store. Name: Complete the keyed-lookup hook and sync the catalog so promoted themes are queryable. Touches: `dev-os/REQ-01-Pattern-Promotion.md`, `dev-os/PATTERN-CATALOG.md`, `contextcore learning pattern_catalog`. Lives: code dev-os/det-req-kit/extract.py. Approve?: is the keyed lookup wired and are the promoted themes queryable via recall?. Verify: `pattern_catalog recall` on a promoted theme returns it; the promoted PC entries appear in the synced store; REQ-01 FR-4 is no longer Partial. Serves: O-1, O-2

- **FR-5 — Register the closing loop.** ✅ **LANDED** (`docs/LOOP_CATALOG.md` #8, the SDK-local slice). Register the census→promote→metabolize→lint→re-census loop as `LOOP_CATALOG #8` (Review-Theme Metabolizer), with re-seek rate for a metabolized theme as its moving number, and place it as a cross-kit family capability, not a det-req-kit-only loop. Name: The Review-Theme Metabolizer loop is registered in the loop catalog with re-seek rate as its moving number. Touches: `startd8-sdk/docs/LOOP_CATALOG.md`. Lives: doc startd8-sdk/docs/LOOP_CATALOG.md. Approve?: is the metabolizer loop registered with a re-seek-rate moving number as a cross-kit capability?. Verify: LOOP_CATALOG holds a #8 entry naming the census/catalog/metabolize/lint stages, its moving number is re-seek rate, and it is scoped cross-kit. Serves: O-2

- **FR-6 — Additive, advisory, one-predicate-per-theme, reuse-only.** The seam reuses the census, catalog, `recall`, and `collect_findings` (no new engine); adding a metabolized theme is one additive predicate plus one catalog entry; and the shipped extractor exit contract and byte-identical renders are unchanged. Name: The seam is reuse-only additive and adds each theme as a single predicate without changing existing contracts. Touches: `dev-os/det-req-kit/tests/`, `dev-os/det-req-kit/extract.py`. Lives: test dev-os/det-req-kit/tests/test_theme_lints.py. Approve?: is the wire reuse-only additive and one-predicate-per-theme with unchanged existing contracts?. Verify: the wiring imports the existing census/catalog/finding pieces with no new engine; a new theme is added as one predicate plus one catalog row; the extractor's existing findings and exit codes are unchanged. Serves: O-2, O-3

## Non-requirements

- **NR-1:** Does NOT auto-apply a lint or auto-edit a draft — the draft-time finding is advisory; a human resolves it (propose-don't-dispose).
- **NR-2:** Does NOT build a new metabolization engine — reuses `render_crp_index.py` (census), `PATTERN-CATALOG` + `pattern_catalog recall` (catalog), `/metabolize-finding` (metabolizer), and `det-req-kit/extract.py::collect_findings` (host).
- **NR-3:** Does NOT block a build or change the extractor's exit code — the fact-rung lints ride the existing exit-unchanged advisory tier.
- **NR-4:** Does NOT author the theme predicates themselves — the ambiguity / atomic-write / security fact-rungs and REQ-30/31 are their own deliverables; this REQ is the seam they fire through.
- **NR-5:** Does NOT un-park a judgment-rung — that is gated on a labeled-fixture precision pass (REQ-07 FR-7), tracked per theme, out of scope here.
- **NR-6:** Cross-repo — the lint host and generator live in dev-os and the skills tree; landing FR-1/FR-2/FR-4 is the respective owner's call. This spec is the emeritus direction, not a mechanical merge.
