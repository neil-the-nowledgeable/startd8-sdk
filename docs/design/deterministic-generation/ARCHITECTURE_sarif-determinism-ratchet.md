# Architecture: the SARIF Determinism Ratchet

**Date:** 2026-08-18 · **Type:** architecture + loop doc (prose, not a det-req) · **Status:** proposed

**Grounds in:**
- The TWIN loop (review side): `docs/design/requirements-visualization/SYNTHESIS_crp-theme-metabolization-four-investigations.md` + `SYNTHESIS_crp-other-and-cli-mining.md` — recurring review themes → draft-time grammar rules (shift-left).
- The shared finding-class registry: `src/startd8/rule_catalog_base.py` (`RuleCatalog`, `RuleSpec`).
- The findings IR sink: `src/startd8/coverage_map/findings_sarif.py` (`render_sarif_from_findings`, duck-types every SDK finding producer).
- The determinism-% scoreboard: `src/startd8/navigator/realization.py` (`determinism_pct`, `derive_realization`, `format_determinism_line`, `corpus_realization`) over `RealizationRegime` (`src/startd8/navigator/models.py`).
- The per-element routing manifest: `docs/design/requirements-visualization/SCHEMA_det-plan-0.1.md` (`costClass` / realization regime per iteration).
- The catalog: `docs/LOOP_CATALOG.md`.

---

## 0. One sentence

**The SARIF Determinism Ratchet is the generation-side twin of the CRP review-theme metabolizer: it censuses the recurring *finding-classes* that the polyglot LLM build path keeps producing, metabolizes the top recurring one into a per-language `$0` render-template or repair-step (shift-left the LLM work into determinism), re-measures the per-language determinism-%, and repeats — until it asymptotes on the irreducible business-logic tail.**

Where the review loop shifts *specification* work left (a re-derived review concern becomes a draft-time grammar rule so the draft is born satisfying it), this loop shifts *generation* work left (a re-derived generation defect becomes a deterministic capability so the code is born correct — at `$0`, no LLM call).

---

## 1. The tiered-projector architecture

The generation path is a **language-neutral SPINE** crossed with **per-language LEAVES**. The spine is the reusable, build-once machinery; the leaves are the irreducibly per-language surfaces the ratchet grows.

### 1.1 The SPINE (language-neutral, build once)

| Spine component | What it is | Grounded in |
|---|---|---|
| **Contract IR** | the language-neutral IDL both generation paths share — one `schema.prisma`/contract that every renderer, splicer, and validator reads. | `CLAUDE.md` "Two Generation Paths" — `.prisma`/contract is the shared IDL |
| **SARIF verify/repair** | the findings-half IR. Every producer (5 language semantic validators, `query_prime` security, `security_prime` gate, cross-file, todo, coverage) emits into ONE SARIF 2.1.0 shape. | `coverage_map/findings_sarif.py::render_sarif_from_findings` duck-types `.check`/`.check_type`, `.severity`, `.file_path`, `.line` — no per-producer adapter |
| **Finding-class registry** | the shared enumerable authority a new deterministic-finding-class registers into — data-only, one `RuleCatalog(...)` per producer. | `rule_catalog_base.py` (the rule-of-three distillation; a 4th+ producer is a data-only add — `startd8-obs` already did it) |
| **Finding→contract loop** (`sarif_to_req_stub`) | closes findings back to spec: a recurring SARIF finding-class becomes a *stub requirement / grammar demand* that the deterministic layer must satisfy. This is where the census output re-enters the design. | conceptual seam today — the census (§2) is its manual instance; parallels the review loop's `extract.py collect_findings` firing wire |
| **Realization-% scoreboard** | the moving number. Rolls a corpus's per-node realization regimes into `deterministic / total`, labeled `declared` until measured provenance grounds it. | `realization.py::determinism_pct` / `corpus_realization` / `format_determinism_line` over `RealizationRegime.{DETERMINISTIC,LLM,HUMAN,UNKNOWN,MIXED}` |

The spine's honesty property is load-bearing: `realization.py` **degrades to the declared regime and never asserts a measurement it cannot ground** (the `CONFIDENCE_THRESHOLD` firewall). The ratchet's scoreboard therefore cannot lie its determinism-% upward — a shifted-left capability only moves the number once its measured provenance clears the threshold.

### 1.2 The LEAVES (per-language, grown by the ratchet)

Each language (Python, Go, Node.js, Java, C#) contributes two leaf kinds:

- **Renderer** (the `$0` deterministic emitter) — **NEW** work per language. For a metabolized finding-class, the renderer emits the correct construct up front so the class cannot arise. (The deterministic `backend_codegen` path is the Python renderer at full maturity; the polyglot leaves grow renderer coverage class-by-class.)
- **Splicer** (the element-level merge) — **already built** for all 5 languages (`languages/{go,csharp,java,nodejs}_splicer.py`; Python AST splicer). The splicer is how a metabolized template lands into an existing file without a whole-file LLM regen.

Per-language SARIF producers (`*_semantic_checks.py`) and the ~45 language-organized `repair/steps/` are the leaf-level *closing* surfaces — a finding either becomes a **renderer** template (never emit the defect) or a **repair-step** (deterministically fix the defect post-gen). Both are `$0`; both retire an LLM iteration.

### 1.3 The four realization tiers — and how each CLOSES via SARIF

Every generation element routes to exactly one tier by complexity (the `complexity/classifier.py` TRIVIAL/SIMPLE/MODERATE/COMPLEX spine), and each tier closes its correctness through the same SARIF findings IR:

| Tier | Element complexity | Generator | Cost | How it closes via SARIF |
|---|---|---|---|---|
| **1 — Skeleton** | TRIVIAL structural | `$0` deterministic **render** (renderer leaf) | `$0` | rendered construct is correct by construction; SARIF verify confirms zero findings — the drift/`--check` gate |
| **2 — Simple** | SIMPLE, a known shape | `$0` deterministic **template** (a promoted exemplar / render-template) | `$0` | template output passes the per-language semantic SARIF checks by construction; a residual finding → a repair-step |
| **3 — Moderate** | MODERATE, decomposable | **micro-prime** (element-level local gen, all 5 langs) | cheap LLM, element-scoped | micro-prime output goes through per-language SARIF verify → `repair/steps/` route the findings deterministically before merge |
| **4 — Complex** | COMPLEX, business logic | **LLM** (Prime / drafter) | full LLM (bucket 3) | LLM output verified through the full SARIF battery; findings that RECUR across runs are the ratchet's census fuel (§2) |

**The ratchet's mechanic is tier demotion.** A finding-class that keeps recurring at tier 4 (LLM) and proves structurally decidable is metabolized into a tier-1/2 renderer template or a tier-3 repair-step — the element is **demoted to a cheaper tier**, and the corpus's deterministic-% rises. This is the shift-left, measured.

---

## 2. The ratchet loop (census → metabolize → re-measure)

```
   ┌──────────────────────────────────────────────────────────────────┐
   │  1. CENSUS      run the polyglot build path; collect SARIF        │
   │                 findings across runs; rank finding-CLASSES by     │
   │                 recurrence (rows / services / languages)          │
   │                        │                                          │
   │  2. METABOLIZE  take the top recurring, structurally-decidable    │
   │                 class → author ONE per-language renderer template │
   │                 or repair-step → register the class in            │
   │                 rule_catalog_base (data-only)                     │
   │                        │                                          │
   │  3. RE-MEASURE  re-run; recompute realization.py determinism-%    │
   │                 (or LLM-calls-per-service). Metabolized class     │
   │                 no longer recurs at tier 4 → number moved.        │
   │                        │                                          │
   │  4. repeat ─────────────┘   until the census long-tail is the     │
   │                             stop signal (§2.2)                    │
   └──────────────────────────────────────────────────────────────────┘
```

### 2.1 The twin-of-CRP framing (structural identity)

The two loops are the same shape on opposite halves of the pipeline. This is not analogy — it is the same census→metabolize→re-measure machine pointed at a different corpus:

| Axis | CRP Review-Theme Metabolizer (the twin) | SARIF Determinism Ratchet (this doc) |
|---|---|---|
| Corpus mined | 7,299 accepted **review suggestions** (`CRP-INDEX.md`) | recurring **SARIF findings** from the polyglot build path |
| Recurring unit | a **review theme** (specify/define, atomic-write, ambiguity…) | a **finding-class** (unchecked error, empty catch, SQL-injection, namespace drift…) |
| Metabolized into | a **draft-time grammar rule** (`extract.py` fact-rung lint) | a **`$0` render-template / repair-step** (renderer or `repair/steps/`) |
| Shifts left | specification work — the draft is born satisfying the concern | generation work — the code is born correct, at `$0` |
| Firing seam | the draft-time firing wire (`collect_findings`) | the deterministic renderer/repair leaf + `sarif_to_req_stub` |
| Shared registry | `PATTERN-CATALOG` / `pattern_catalog recall` | `rule_catalog_base.py` (`RuleCatalog`) |
| Moving number | re-seek rate for a metabolized theme → 0 | per-language determinism-% ↑ (or LLM-calls-per-service ↓) |
| Fact/judgment split | fact-rung ships loud; judgment-rung parked (REQ-25) | structurally-decidable class → template; semantic class → stays LLM |

The review loop's own synthesis names the discipline this loop inherits: **metabolize the structural half, park the semantic half.** A finding-class is a ratchet candidate only when it is *structurally decidable* (a Go unchecked-error, a Java empty-catch, a C# namespace misalignment — all already have deterministic `*_semantic_checks.py` detectors and `repair/steps/`). A finding that needs implementation-semantics judgment stays at tier 4 (LLM), exactly as the review loop parks a weasel-word judgment-rung.

### 2.2 The asymptote and stop signal

The determinism-% **asymptotes below 100% by design** — business logic is irreducibly LLM (bucket 4 content, bucket 3 integration glue). The stop signal is read directly off the census:

- **Stop when the census long-tail is flat** — when the top recurring finding-class is a one-off / project-heterogeneous defect rather than a repeated structural class, metabolizing it would be manufacturing a template for the tail. The review-side twin quantified this precisely: **~45% of the "other" review bucket is irreducible one-off noise** that must NOT be forced into a theme (`SYNTHESIS_crp-other-and-cli-mining.md §2c`). The generation-side long-tail is the same honest floor.
- **The over-abstraction guard:** *don't template the long tail.* A renderer template authored for a finding-class that recurs across ≥2 languages / ≥N services earns its place; a template for a single-service defect is accidental complexity (a framework for one use), which the SDK's own `/complexity-distiller` discipline flags. The registry's rule-of-three heritage (`rule_catalog_base.py`: extract the shared shape only "when a 3rd consumer appears") is the same brake — metabolize a class into the shared registry only once it has recurred enough to prove it is a class, not an instance.

The scoreboard's honesty firewall (`realization.py` degrades-to-declared) guarantees the asymptote is measured, not asserted: a class you *believe* you metabolized but whose provenance can't be grounded above threshold does not inflate the number.

---

## 3. The det-plan `costClass` as the routing manifest

`SCHEMA_det-plan-0.1.md §2` makes the det-plan the **per-element routing manifest**: each iteration/element carries a `costClass` ∈ `{deterministic-$0, llm-integration, human}`, **derived from the realization regime (REQ-18/19)** — not authored. The projector bands each FR by its `Touches` path + `Lives` type: a `$0`-codegen target → `deterministic-$0`; a no-code doc-only FR → `human`; else `llm-integration`.

That `costClass` **is the tier selector for §1.3's tiered projector.** The plan says, per element, *which tier builds it*:

- `deterministic-$0` → tier 1/2 (renderer / template) — no LLM
- `llm-integration` → tier 3/4 (micro-prime / LLM)
- `human` → out of the automated tiers (bucket 4)

The ratchet and the plan are coupled through this field in both directions:

1. **The plan drives the projector** — the tiered projector reads `costClass` to route each element to its cheapest sufficient tier.
2. **The ratchet moves the plan** — when a finding-class is metabolized into a `$0` renderer, elements that were `llm-integration` become `deterministic-$0` in the *next* projection. **The det-plan's `costClass` distribution is a forward projection of the same determinism-% the scoreboard measures backward** — and shifting-left literally rewrites the plan toward more `deterministic-$0` iterations.

The known limitation is honest and shared: today `costClass` is a **coarse band** (det-plan G-2) because the det-req carries no per-FR realization declaration. A finer band — and therefore a finer routing manifest — needs a per-FR realization regime in the det-req grammar. That gap is the same `Depends:`/`Emits:`/grammar-field batch the review loop's synthesis is already pushing upstream; a `Realization:` FR field is its natural sibling and would let the plan route at per-FR granularity.

---

## 4. Proposed LOOP_CATALOG entry

`docs/LOOP_CATALOG.md` has 7 active loops; the review-side twin is **proposed as #8** in the CRP synthesis (Review-Theme Metabolizer). This is its generation-side twin — propose as **#9**.

```
### 9. SARIF Determinism Ratchet  (the generation-side twin of #8)

- **What it does:** raises per-language determinism by metabolizing recurring generation
  findings into deterministic capabilities. census (rank SARIF finding-CLASSES from the polyglot
  build path by recurrence) → metabolize the top structurally-decidable class into a per-language
  $0 renderer-template or repair-step (demote it from tier 4 LLM to tier 1/2/3) + register the
  class in rule_catalog_base → re-measure the determinism-% → repeat. Asymptotes on the
  irreducible business-logic tail (the flat census long-tail is the stop signal).
- **Driver:** the census over persisted SARIF (coverage_map/findings_sarif.py producers) +
  rule_catalog_base.py (the finding-class registry) + realization.py (the scoreboard).
  Metabolization routes through /metabolize-finding; the finding→contract seam is sarif_to_req_stub.
- **Moving number:** per-language determinism-% (realization.py::determinism_pct, measured-labeled
  once provenance clears the CONFIDENCE_THRESHOLD firewall) — equivalently LLM-calls-per-service ↓.
- **Placement:** cross-cutting generation-path capability. Spine = language-neutral (contract IR +
  SARIF verify/repair + rule_catalog_base + realization scoreboard); leaves = per-language renderer
  (NEW) / splicer (built) + repair/steps. The findings-half twin of #8's specification-half loop.
- **Guard (anti-over-abstraction):** don't template the long tail — metabolize a class only after
  it recurs enough to be a class not an instance (the rule-of-three brake), per /complexity-distiller.
- **State:** persisted SARIF batches (Mottainai — generate-once, re-census $0, like rescore_behavioral).
- **Status:** PROPOSED.
```

The Mottainai reuse is direct: SARIF findings, once persisted per run, are re-censusable for `$0` as the ratchet advances — the same generate-once/re-score-free discipline as `rescore_behavioral.py` (LOOP_CATALOG "Related loops").

---

## 5. Cross-language determinism TRANSFER

A finding-class proven templatable in one language **transfers its CLASSIFICATION — not its template — across languages via the shared registry.**

The mechanism is `rule_catalog_base.py`: a finding-class is a data-only `RuleSpec` (`severity`, `domain`, `description`) registered once under a `RuleCatalog`. That entry is the language-neutral *identity* of the class. The per-language **template** (the Go renderer body vs the C# renderer body) is a leaf and stays per-language — but the knowledge *that this class is metabolizable, decidable, and worth shifting left* is registry data, shared instantly.

Concretely, the same underlying defect wears one classification across leaves:

- **"unchecked-error"** — Go's `go_unchecked_error` repair-step is the Go template; the *class* ("a fallible call whose error is discarded") registers once and predicts the Node.js / Java analogues.
- **"empty-catch / swallowed-exception"** — Java `empty catch` + C# analogues share one registered class; the template differs, the classification is one row.
- **"sql-injection"** — `java_sql_parameterize` + `sql_parameterize` + `query_prime verify_file` all close the same registered security class across languages.
- **"namespace/package misalignment"** — C# `csharp_namespace_fix` and Go `package dir` share the "declared-vs-path drift" class.

So the transfer rule is: **metabolize a class in language A → register the class → language B inherits the *census signal* (this class is high-recurrence and decidable, prioritize a B-renderer for it) for free, and only owes the leaf template.** This is why the ratchet's cost is sub-linear in languages: the expensive discovery ("is this class structurally decidable and worth a `$0` capability?") is paid once at the registry; each additional language pays only the cheap per-leaf template — the same economics as the review loop, where 542 ambiguity re-derivations collapse to one predicate authored once.

---

## 6. One-line conclusion

*The polyglot build path's recurring SARIF findings are the generation-side equivalent of the CRP corpus's recurring review themes — a ranked backlog of the deterministic capabilities the SDK should own. Census the finding-classes, metabolize the top structurally-decidable one into a per-language `$0` renderer-template or repair-step (demoting it from LLM tier 4 to a `$0` tier), re-measure the determinism-% through the honesty-firewalled scoreboard, and repeat — transferring each class's classification across languages via the shared registry while paying the leaf template only once — until the flat census long-tail signals the irreducible business-logic asymptote and the ratchet stops rather than over-templating the tail.*
