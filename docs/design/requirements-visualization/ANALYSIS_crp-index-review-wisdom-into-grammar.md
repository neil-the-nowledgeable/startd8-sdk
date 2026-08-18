# Analysis: CRP-INDEX.md — the corpus's review wisdom is the draft-time grammar the det-*-kits are missing

**Date:** 2026-08-17 · **Type:** synthesis (grounded in `dev-os/CRP-INDEX.md`) · **Status:** feeds the next steps
**Relates:** `CHARTER_det-doc-kit-family.md` (det-crp-kit) · `RESEARCH_present-but-dead-lacuna-census.md` (verify-liveness) · the reflective-pairs index (the doc-pair twin) · `/audit-then-metabolize`

## What it is

The **findings-half twin** of the reflective-pairs index. Reflective-pairs censused the doc-*pair* half (REQ↔companion
→ grounded det-plan-kit); **CRP-INDEX censuses the review/findings half**: 1033 docs with captured review memory,
**7299 accepted suggestions across 463 docs**, strong/medium/weak Appendix-A/B/C conformance (802/243/213), a topic
census, and a **re-seeking** distribution (same target reviewed repeatedly). It is the demand + conformance ground
for **det-crp-kit** exactly as reflective-pairs was for det-plan-kit.

## The killer insight (the index states it itself)

> *"a theme accepted across many different docs is the same information sought repeatedly… capture it once so the
> lookup surfaces it at **draft** time instead of it being re-derived in review after review. Appendix A/B is only
> per-document memory; this is the cross-document layer it cannot reach."*

**The 7299 accepted suggestions are the accumulated review wisdom of the whole system, and the recurring themes are
exactly what the det-*-kit GRAMMARS should enforce at draft time** — the *shift-left* move: metabolize a recurring
review finding into a *format rule* (a required field / an `extract.py` lint), so the draft already satisfies it and
the review stops re-deriving it. It is KAIZEN (don't discard lessons) made concrete — 7299 reviews' worth of lessons
→ the grammar.

## The convergence that validates the session

The recurring-themes table (ranked by distinct docs) is a **ranked backlog of grammar-hardening rules** — and its top
two are *already what we built*:

| Theme | Distinct docs | Accepted rows | Metabolized as |
|-------|--------------:|--------------:|----------------|
| Validation / thresholds / verify | 274 | 767 | ✅ **REQ-22 verify-liveness** |
| **Ambiguity — specify / define / clarify** | 158 | **542** | ⬜ **un-metabolized — top new pick** |
| Schema / types / serialization | 168 | 323 | ⬜ |
| Observability / telemetry | 145 | 262 | ✅ **REQ-23 target-unmeasured + REQ-28** |
| State / lifecycle / resume-retry | 138 | 218 | ⬜ |
| Error handling / failure behavior | 122 | 231 | ⬜ |
| Security / authz / sanitization | 114 | 192 | ⬜ |
| Consistency / reconcile | 112 | 188 | ⬜ |
| Naming / terminology | 89 | 146 | ✅ (NAMING_CONVENTION / DIDL) |
| Concurrency · Determinism · Edge-cases · Performance | 77·77·75·24 | 116·96·105·26 | ⬜ |

**The liveness layer we built (REQ-22/23) IS the #1 + #4 review themes, metabolized** — independent convergence:
we built exactly what the review corpus sought 767+262 times. Convergence ⇒ essential structure (the session's
recurring signature), and it validates the liveness work against 7299 grounded data points.

## The dormant value path (present-but-dead, at the review altitude)

Re-seeking shows the CRP protocol's Appendix-A/B memory + `PATTERN-CATALOG` + the Phase-4.5/4.6 keyed lookup *exist*
but **aren't preventing re-derivation** (the same target reviewed at different times, the settled concern
re-sought). The cross-document memory infrastructure is a **dormant value path** — present, under-fueled — the exact
present-but-dead class one altitude up. The fix is not more memory; it is *fueling the draft-time lookup* so a
recurring theme surfaces before review.

## How it feeds the next steps

1. **Ground det-crp-kit in CRP-INDEX** (upgrade its spec from "assessed" to "census-grounded"): the strong/medium/weak
   Appendix conformance is `crp_lint`'s target (213 weak docs = the conformance backlog); the 1033 review-logs + 33
   saved prompts are the corpus; the topic clusters + re-seeking are the demand.
2. **NEW high-value thread — CRP-theme metabolization** (`/audit-then-metabolize` on the review corpus): mine the
   recurring themes, metabolize the top *un-metabolized* one into a det-req/det-plan grammar rule. **Top pick:
   an "ambiguity" lint** (theme #2 — 158 docs, 542 rows, largely un-metabolized): a det-req-kit `extract.py` check
   that flags a vague/undefined FR (an unspecified gate, an undefined term, a "clarify"-bait clause) *at draft time*,
   so 542 re-derivations don't happen. Then schema-artifact (168), lifecycle-completeness (138), error-behavior (122).
3. **The re-seeking dormancy** — investigate why the cross-doc lookup under-fuels draft time (a dormant value path);
   route to the retrospective/metabolize loop.

## The one-line conclusion

*CRP-INDEX is the accumulated review wisdom of the whole corpus, quantified — and it is a ranked backlog of the
draft-time rules the det-*-kit grammars should enforce so reviews stop re-deriving them. We already metabolized its
top two themes (verify-liveness, observability) into the liveness layer, which validates the method; the next pick
is the "ambiguity" lint (theme #2, 542 re-derivations un-prevented), and the whole index grounds det-crp-kit.*
