# CKG Phase 2 — Knowledge Provider Adherence Results

**Date:** 2026-06-02
**Requirement:** REQ-CKG-530 (D1: injection ≠ adherence) · resolves first data point for **OQ-2**
**Harness:** `scripts/ckg_adherence_harness.py --backend startd8` (core: `contractors/project_knowledge/adherence.py`)
**Status:** First empirical run — **Phase-2 premise validated on this sample; no escalation to Approach C.**

> One-line takeaway: **injecting the Knowledge Provider's authoritative context closes the model-tier
> gap** — `gemini-2.5-flash` + injection performs identically to `gemini-2.5-pro` + injection (perfect)
> on the RUN-011 invention classes, even though flash-without-help is meaningfully worse.

---

## 1. Method

- **Cases:** 4 reproductions of the RUN-011 M4 failure classes (`adherence.RUN011_CASES`):
  - **Gap A (Prisma field invention):** PI-001 (`enrich-capabilities`), PI-004 (`capability-card`).
  - **Gap B (module-path invention):** PI-002 (`@/lib/prisma`), PI-007 (`@/lib/ai/client`).
- **Two conditions per case:** `baseline` (bare spec prompt) vs `injected` (spec prompt + the Knowledge
  Provider section: scoped Prisma field sets + explicit module-path negatives + omissions). The injected
  content is produced by the *same* `DraftModeProducer`/`scoping`/`render` code the live pipeline injects.
- **Sampling:** N = 5 generations per (case, condition), per model.
- **Scoring (`measure_adherence`):** a completion is *adherent* iff it contains **none** of that case's
  literal RUN-011 invention tokens (denylist substring check).
- **Models:** `gemini-2.5-pro` and `gemini-2.5-flash` (both via the SDK `startd8` backend).

---

## 2. Results

### gemini-2.5-pro

| Case | Gap | Baseline | Injected |
|------|-----|----------|----------|
| PI-001 | A | 5/5 (1.00) | 5/5 (1.00) |
| PI-004 | A | 4/5 (0.80) | 5/5 (1.00) |
| PI-002 | B | **0/5 (0.00)** | 5/5 (1.00) |
| PI-007 | B | 5/5 (1.00) | 5/5 (1.00) |
| **Gap A** | | **0.90** | **1.00** |
| **Gap B** | | **0.50** | **1.00** |

### gemini-2.5-flash

| Case | Gap | Baseline | Injected |
|------|-----|----------|----------|
| PI-001 | A | 5/5 (1.00) | 5/5 (1.00) |
| PI-004 | A | **2/5 (0.40)** | 5/5 (1.00) |
| PI-002 | B | 1/5 (0.20) | 5/5 (1.00) |
| PI-007 | B | 5/5 (1.00) | 5/5 (1.00) |
| **Gap A** | | **0.70** | **1.00** |
| **Gap B** | | **0.60** | **1.00** |

### Lift (injected − baseline)

| | gemini-2.5-pro | gemini-2.5-flash |
|---|---|---|
| Gap A | +0.10 | **+0.30** |
| Gap B | +0.50 | +0.40 |

---

## 3. Analysis

1. **Injection reaches 1.00 on both Gaps for both tiers** (8/8 per-Gap rates perfect when injected). The
   provider is *sufficient* on this failure class, not merely necessary — D1's "necessary but not
   sufficient" worry does not bite here.
2. **Injection closes the model-tier gap.** Baseline degrades as the model gets cheaper
   (pro 0.90/0.50 → flash 0.70/0.60), but *injected* both land at 1.00/1.00. So **flash + injection ≈
   pro + injection** — direct empirical support for the "richer specs → cheaper models" strategy.
3. **The cheaper the model, the larger the lift** (flash Gap-A +0.30 = 3× pro's +0.10), because flash
   had more inventions to prevent (PI-004 baseline 2/5).
4. **Cleanest single signal — PI-002 / `@/lib/prisma` (D2 explicit negatives).** Both tiers reach for
   this canonical-name prior unprompted (pro 0/5, flash 1/5) and the explicit negative eliminates it
   entirely (5/5). This is the textbook validation of negatives as a first-class rendered output.

---

## 4. Caveats (read as directional evidence, not benchmark-grade proof)

- **N = 5** → coarse resolution; "1.00" means 0 failures in 5 draws (true failure rate could be up to
  ~45% by the rule of three). Encouraging, not conclusive.
- **Substring/denylist scoring** can **false-pass**: a model that invents a *different* wrong field/path
  not on the denylist still scores adherent. A structural check ("uses only real fields/paths") is stronger.
- **Synthetic cases + small schema**, not the real RUN-011 app context.
- **One provider family** (gemini); no Anthropic/OpenAI/Ollama tiers measured.
- **Harness is still a scaffold**: the `seed` is not wired to temperature/sampling, so the N draws are
  independent samples at the provider default, not seed-reproducible.

---

## 5. Verdict & next steps

- **OQ-2:** the ~0.9 threshold is reachable; injection is *most* valuable on the cheaper tier the pipeline
  routes simple tasks to. Premise **validated on sample → no Approach-C (contract-first) escalation required.**
- **Cheap hardening** (optional, raises confidence): N↑ to 10–20; structural scoring (delegate to the
  Phase-1 Verifier instead of substrings); wire seed→temperature; add Anthropic/Ollama tiers.
- **The only "more rigorous" step left** is the **end-to-end pipeline A/B** (run the same cases through the
  real `PrimeContractorWorkflow` with Verifier + build + repair active, baseline-vs-injected). This is the
  faithful answer to design **OQ-5 (prevent-vs-detect split)** and is currently **undefined** (no
  requirements/plan). Worth a `/reflective-requirements` cycle *if* end-to-end fidelity is wanted; the
  isolated harness already answers the prevention-layer question.
