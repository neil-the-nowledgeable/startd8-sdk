# Deterministic Generation — Vision

**Status:** Living vision document (the single home for this effort)
**Date:** 2026-06-03
**Scope:** The arc that maximizes deterministic assembly of service-web-app artifacts and reserves
LLM spend for the irreducibly non-deterministic residue — measured, targeted, and verified.

> This document is the *why* and the *whole*. The component requirements live beside it:
> `DETERMINISTIC_INGESTION_REQUIREMENTS.md`, `CONTROLLED_CORPUS_REQUIREMENTS.md`,
> `DETERMINISTIC_PROVIDER_REQUIREMENTS.md`, `SEMANTIC_COMPLIANCE_REVIEWER_REQUIREMENTS.md`.
> The longer-horizon controlled-English ambition is framed at the end.

---

## 1. The thesis

**An LLM call is only worth its cost when it adds information not recoverable deterministically from
its input.** Most code generation in a *stable, recurring domain* (service web apps; the SRE and
growth-marketer vocabularies around them) does not meet that bar on every run — the model reproduces
the same structure each time. The goal is to **push the deterministic frontier as far as the evidence
allows**, and pay the LLM only for genuine judgment: novel structure extraction, and the semantic
residue a controlled vocabulary can't yet pin down.

This is the cost-efficiency thesis made operational: not "use a cheaper model," but "don't make the
call at all when its output is already determined."

## 2. The principle that governs it

Precision is a virtue **in service of a beneficiary**. Two failure modes bound the work:
- **Zero Value Precision** (see `docs/design-princples/ZERO_VALUE_PRECISION_ANTI_PRINCIPLE.md`) —
  perfecting generation that no user needs, or that blocks a capability they could already use. Every
  step here must answer "who is served?" The deterministic-ingestion win shipped because it removed
  *overhead*; the provider step ships only once it removes *real* application-codegen cost with proof.
- **Templating the wrong thing** — making a binding deterministic that doesn't actually satisfy the
  requirement (a false-PASS). The oracle's two-axis classification exists precisely to refuse this.

## 3. The architecture (four moves, evidence-gated)

```
business/req docs
      │  PARSE (LLM — genuine structure extraction; kept)
      ▼
   features ──────────────────────────────────────────────────────────┐
      │  ASSESS / TRANSFORM  → DETERMINISTIC by default (overhead removed)│  [SHIPPED]
      ▼                                                                   │
   seed (tasks)                                                           │
      │                                                                   │
      ▼                                                                   │
  GENERATION (drafter)                                                    │
   ├─ route(target_file) via Controlled Corpus oracle ───────────────────┤
   │     • deterministic_candidate (stable, cross-run+model) → PROVIDER   │  [PROTOTYPE → wiring]
   │         emit proven content, $0, no LLM                              │
   │     • false_pass_risk / unproven → LLM  (never templated)           │
   │     • everything else → LLM                                          │
      ▼                                                                   │
   code on disk                                                          │
      │  postmortem → Controlled Corpus (accumulate determinism)  ───────┘  [SHIPPED — runs are producers]
      ▼
  Semantic Compliance Reviewer (the residue: false-PASS + intent gaps)     [SPEC'd]
```

Each arrow is gated by **evidence**, not optimism:
1. **Deterministic ingestion** *(shipped)* — ASSESS/TRANSFORM default to proven heuristic paths; LLM
   opt-in. ~62% of ingestion LLM cost removed. This is overhead, not application codegen — honest scope.
2. **Controlled Corpus + determinism oracle** *(shipped)* — every run is a producer; the corpus
   accumulates terms → bindings → **two-axis determinism** (structural stability × semantic
   compliance) and names the deterministic-ready files and the false-PASS ones to avoid.
3. **Corpus-driven deterministic provider** *(this step)* — serve the named deterministic-ready files
   from proven content with no LLM call; fall through to LLM for everything else. Turns measurement
   into application-codegen savings.
4. **Semantic Compliance Reviewer** *(spec'd)* — the LLM-driven backstop for the residue the corpus
   flags (`false_pass_risk`, `needs_semantic_review`), feeding fixes back into the next run.

## 4. Where we are (honest status, 2026-06-03)

| Move | Status | What actually fires |
|------|--------|---------------------|
| Deterministic ingestion | ✅ shipped, live default | ASSESS/TRANSFORM deterministic; ~62% ingestion-LLM cut |
| Corpus accumulation (write) | ✅ wired into prime postmortem | every prime run merges terms + determinism |
| Corpus read — generation authorities | ✅ wired (`project_root` threaded) | mature vocabulary injected into spec prompts |
| Corpus read — SCR triage | ⏳ no consumer yet | SCR is spec'd, not built |
| Deterministic provider | 🔬 prototype (this step) | routes proven files to content, no LLM — not yet in live loop |
| Live end-to-end (cap-dev-pipe) | ⏳ runbook + offline validation pass; live run pending | — |

**Net so far:** overhead made deterministic + the targeting system that proves *which* application
codegen is safe to make deterministic (~18/23 OB files). No application codegen converted yet — the
provider step is what makes the 78% real.

## 5. The longer horizon (controlled-English transformation)

The corpus is the seed of a larger ambition: a **deterministic English-language transformation across
a controlled word corpus** for the full artifact chain — business description → functional design →
technical design → tests/UAC → code. The same principle scales: constrain the *language* at each stage
to the corpus, and each stage-to-stage transform moves from interpretation toward parse — deterministic
to the degree the input conforms, with the LLM and the SCR handling only the off-corpus residue. We do
**not** claim English becomes deterministic; we make the *covered subset* deterministic and *measure*
coverage. The corpus + oracle built here are the substrate for that, and the online-boutique trove
(many runs, consistent inputs, cross-model) is its first empirical corpus.

## 6. Non-goals
- Making the LLM unnecessary — PARSE and the semantic residue are irreducibly LLM.
- Determinism in novel/unstable domains — the trade pays off only where the domain recurs.
- Templating anything the oracle hasn't proven (the false-PASS guardrail is load-bearing).

---

*Living document — update as moves ship. The next concrete step is the deterministic provider
(`DETERMINISTIC_PROVIDER_REQUIREMENTS.md`), prototyped now and wired after the live validation run.*
