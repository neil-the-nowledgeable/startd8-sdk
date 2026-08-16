# Research: cross-corpus grammar — separating principles from conventions (empirical)

**Date:** 2026-08-16 · **Type:** pattern analysis / data modeling (emeritus) · **Status:** measured result
**Follows:** `PROMPT_corpus-pattern-analysis-and-data-modeling.md` (analysis #5, the highest-value follow-on)
**Tests:** the Craft-Grammar self-similarity claim (`project_craft_grammar`) — *empirically*, not by assertion.

## Method

Mined **6 corpora** with one identical design-move regex set and compared **move frequency** (% of docs in
the corpus using each move): two SDK generation paths (deterministic `python-contract-codegen` vs LLM
`prime`), the `kaizen` quality system, the `requirements-visualization` baseline, and **two cross-repo
dev-os corpora** (`dev-os/`, `dev-os/visual-editor/`). A move universal across ≥3 corpora *including
cross-repo* = a **principle**; a move strong only in req-viz = a **convention**.

## The frequency matrix (measured)

| move | req-viz | kaizen | py-codegen ($0) | prime (LLM) | dev-os (xrepo) | dev-os/vis |
|------|--------:|-------:|----------------:|------------:|---------------:|-----------:|
| byte-identical | **69%** | 9% | **48%** | 18% | 19% | 31% |
| additive | 56% | 9% | 21% | 18% | 16% | 8% |
| honest-grounding | **73%** | 0%* | **55%** | 3%* | **89%** | **58%** |
| mirror/self-similar | **69%** | 9% | **72%** | 15% | **68%** | 46% |
| seam | 45% | 0% | **62%** | 3% | 35% | 38% |
| no-fork/Kagami | 18% | 0% | 0% | 3% | 22% | 31% |
| trust-gate/human | 18% | 0% | 3% | 0% | 3% | 0% |
| reserve-a-slot | 13% | 0% | 0% | 3% | 0% | 4% |
| firewall/contract | 11% | 0% | 0% | 3% | 0% | 0% |
| confidence/degrade | 20% | 40% | 38% | 41% | 27% | 12% |

\* vocabulary bias — see caveat.

## Findings

**Cross-corpus PRINCIPLES** (converged across ≥3 corpora including cross-repo, on shared vocabulary):
- **mirror/self-similar** (46–72% across req-viz · codegen · dev-os ×2) — the strongest universal. *The
  self-similarity is itself self-similar.* This is the empirical validation of the Craft-Grammar claim.
- **honest-grounding** (55–89% across the design corpora) — universal design discipline.
- **seam** (35–62%) — architectural principle across repos.

**The headline result — `byte-identical` tracks DETERMINISM.** 69% req-viz + 48% py-codegen (deterministic
output) vs 18% prime + 9% kaizen (LLM / analysis). The prose-mining **independently rediscovered the
two-generation-paths split** — byte-identity is the *signature of the deterministic corpora*, near-absent in
the LLM ones. A core architectural fact recovered from word-frequency alone (the method measures something
real). byte-identical is therefore a **determinism-conditional principle**: present exactly where byte-stable
output exists.

**Schema-family principle:** `no-fork/Kagami` (18% req-viz, 22–31% dev-os, **0%** generation corpora) — a
principle *within the Node/navigator family* req-viz and dev-os share, not universal.

**req-viz-local CONVENTIONS (promotion candidates):** `trust-gate/human` (18%), `reserve-a-slot` (13%),
`firewall/contract` (11%) — the recent NLPS-arc moves (REQ-16→21), ~0% elsewhere. If a next corpus adopts
them they **graduate to principles** (Yokoten). Track this.

## The caveat (itself a finding)

The mining is **vocabulary-based** → it measures *shared concept AND shared name*. `kaizen` scores **0%** on
honest-grounding *despite being entirely about grounding* (it says "disk-quality / assembly-delta," not
"grounded / cruft"). So concept-only convergence (same idea, different words) is **undercounted** — the
principles found are *conservative*. The next-agent upgrade: **concept-embedding mining** (cluster by meaning,
not keyword) to catch same-concept/different-vocabulary convergence, which would likely *raise* the principle
count.

## The model: a stratified Craft Grammar

The grammar is real but **layered**, not flat:
1. **Universal core** — self-similar · honest-grounding · seam (everywhere).
2. **Determinism-conditional** — byte-identical (present ⟺ byte-stable output).
3. **Schema-family** — Kagami/no-fork (the Node/navigator family).
4. **Local / emerging** — the NLPS-arc moves (promotion candidates).

This stratification is the actionable output: a **govern rule** should enforce layer 1 corpus-wide, layer 2
*only* on deterministic-output specs, layer 3 within the schema family — not one flat checklist. And the
layer-4 conventions are a watchlist for promotion.

## Next (for another agent)
- **Concept-embedding mining** to beat the vocabulary bias (raise the principle count honestly).
- **Track convention promotion** — re-run after the next corpus and see if trust-gate/reserve-slot/firewall spread.
- **Model each corpus as a Node graph** (analysis #1) and overlay the grammar strata as facets.
