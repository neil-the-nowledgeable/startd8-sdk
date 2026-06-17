# Harder Single-File Benchmark Tasks (Hardened Difficulty Tier) — Requirements

**Version:** 0.4 (Post-implementation-planning — self-reflective)
**Date:** 2026-06-17
**Status:** Draft (pre-CRP)
**Plan:** `BENCHMARK_TASK_DIFFICULTY_PLAN.md` v1.0 (the pass that drove the §0.2 updates below)
**Owner:** neil-the-nowledgeable
**Related:** `docs/design/model-benchmark/`, `docs/design/benchmark-scoring/` (Track 2), `scripts/gen_ob_benchmark_seeds.py`, `src/startd8/benchmark_matrix/`
**Supersedes scope of:** v0.1 (multi-file task-granularity knob) — abandoned; see §0.

---

## 0. Planning Insights (Self-Reflective Updates)

### 0.0 — First pass: the scope pivot (multi-file granularity → single-file difficulty)

> v0.1 aimed to make tasks harder by **enlarging granularity** (raise plan-ingestion Gate 2a `max_files`,
> rewire the benchmark to ingest fresh plans). Planning falsified the premise:

| v0.1 Assumption | Discovery | Impact |
|-----------------|-----------|--------|
| Plan-ingestion granularity logic shapes benchmark tasks | **Benchmark never runs plan-ingestion** — it loads pre-built committed `seed-{service}.json` (`runner.py`); granularity is frozen in `gen_ob_benchmark_seeds.py` | Gate 2a knob irrelevant to benchmark. Abandoned. |
| Complexity/micro-prime decomposition shrink benchmark tasks | Both **already neutralized in benchmark mode** (`--benchmark-mode` incompatible with `--micro-prime`, `run_prime_workflow.py:385`; `decomposition_enabled` defaults False). Model gets the **whole file in one shot**. | No intra-file decomposition to tune. Maximally coarse already. |
| "One task = multi-file feature" is tunable | **Single-file-per-task is hard at 3 layers**: Gate 2a, `_process_decomposed_feature` (`prime_contractor.py:2421`), 1:1 integration (`integration_engine.py:2759`) | Multi-file = invasive core surgery. Deferred (NR-2). |
| Difficulty ≈ size | **Structural scoring is a weak discriminator** (stubs compile); the **behavioral channel** is what separates flagship/mid-tier | Difficulty must route through behavioral scoring. |

**Pivot:** additive **hardened single-file difficulty tier** across axes A/B (behavioral suites),
C (stringent spec), D (orchestration), E (contamination resistance).

### 0.1 — Second pass: the behavioral harness (refines axis priority + effort)

| v0.2 Assumption | Discovery | Impact |
|-----------------|-----------|--------|
| Only `charge_suite` exists (1/9) | **4 suites already exist + a registry** (`execute.py:28-33` `_SUITES`: payment, currency, shipping, ad), dispatched by service name (`execute.py:104`). Client is a **language-agnostic Python gRPC client** — one suite scores all server languages. | A/B is mostly **enrich existing suites**, not build infra. OQ-1/OQ-5 resolved. Big de-risk. |
| Any service can be behaviorally hardened | **Java & C# cannot be launched** — `provision.py` has no serve/build strategy for them; they always degrade. `adservice`(Java) has a suite that never actually runs; `cartservice`(C#) can't run. | Behavioral hardening limited to **Go/Node/Python** until provisioning added (FR-22). |
| Hardened scoring is new work | Scoring **already** folds the functional term at `FUNCTIONAL_WEIGHT=0.5`, per-assertion (coverage=passing/total), degrade-not-zero (FR-32). An unused **expose-defects** scorer exists (`scoring.py:390-426`). | FR-9 largely satisfied; "hardening" = richer suites, not scoring rework. |
| Orchestration (D) is moderate | `run_service_sandboxed` is **strictly single-process**; mocked deps need a `run_services_sandboxed` refactor (multi-launch, readiness sequencing, port map, group teardown). | **Defer D** to a later tier (FR-13..15 → deferred). |
| Contamination-resistance via renaming (E) is buildable | The rename probe is **not in this repo** (edge-brains). The task is **proto-bound**: RPC/message/field/service names come from `demo.proto` and bind the suite client — **cannot be renamed**. Only free local identifiers are renameable, and the **model picks those itself ⇒ zero added difficulty**. `contamination.py` already provides a **CodeBLEU memorization signal** (static, $0). | **Axis E downgraded**: from "rename perturbation" to "**report existing memorization signal**." True perturbation needs a *non-OB* corpus — separate effort (OQ-3, NR-7). |

**Resolved:** OQ-1 (registry exists), OQ-4 (tier = new `tier_states` axis, backward-compatible like
`leverage`), OQ-5 (language-agnostic client). **Reframed:** OQ-2 (orchestration deferred), OQ-3
(contamination perturbation infeasible on OB).

**Phasing that falls out of the planning (priority order):**
- **P1 (MVP, low effort, high signal):** tier dimension + enrich behavioral suites + stringent spec
  on **launchable, trap-rich Go/Node/Python services** — lead with **currencyservice** (Node, `Money`
  units/nanos arithmetic, suite already exists) and **paymentservice** (Node, suite exists).
- **P2:** Java/C# provisioning so `cartservice`/`adservice` can be behaviorally hardened (FR-22).
- **P3 (deferred):** orchestration with mocked deps (multi-process sandbox, FR-13..15).
- **Eo (downgraded):** surface the CodeBLEU memorization signal in hardened reports; treat true
  contamination-resistance as a separate non-OB effort.

### 0.2 — Third pass: writing the implementation plan (robustness, value, flexibility, quick wins)

> Authoring `BENCHMARK_TASK_DIFFICULTY_PLAN.md` at file/function granularity surfaced exact mechanisms
> and several opportunities that were invisible at requirements-time. These tighten robustness, raise
> value, add flexibility, and expose low-hanging fruit. New/changed requirements: **FR-23 … FR-31**.

| Planning realization | Why it matters | Requirement change |
|----------------------|----------------|--------------------|
| `spec_hash()` adds K2/K3 axes **only when non-default** (verified); `expose_defects` is already a wired spec field | The exact, proven backward-compat pattern — not a guess | FR-2 sharpened: mirror conditional inclusion; **tier is an open string axis** (not baseline/hardened boolean) → future variants (`adversarial`, `minimal-spec`) reuse the machinery (flexibility). FR-9 notes `expose_defects` is a ready flag. |
| **Silent baseline fallback** when a hardened seed is missing would mislabel a baseline run as hardened | Corrupts the entire baseline-vs-hardened comparison — a correctness hazard, not a nicety | **FR-4 hardened to fail-closed** (`infra_fail` + named reason; never silently substitute baseline under a hardened label). |
| `rescore_behavioral.py` re-launches persisted servers and re-runs the **current** suite for $0 — but is **tier-blind** today | Generation and suite-authoring are **decoupled** | **FR-23 (value/flexibility/quick win):** generate hardened servers **once**, then enrich suite assertions and re-score for **$0**. **FR-20 expanded:** rescore must become tier-aware (+ `--suite-tier` override). |
| Tier-aware rescore can run the **hardened suite against existing *baseline* servers** | A happy-path baseline server should fail hardened assertions → confirms the suite discriminates **before** spending on hardened generation | **FR-24 (quick win, de-risk):** $0 pre-validation of suite discrimination via cross-tier rescore. |
| The discriminator is **raw functional coverage**, not the composite (50% structural dilutes it) | Measuring the composite would understate/obscure the flagship/mid-tier gap | **FR-25 (value):** the success metric (was OQ-6) is the **functional-coverage gap** on the hard-assertion subset, not composite. |
| Hardened suite as a **superset** of the baseline suite | Coverage degrades monotonically → the per-model baseline→hardened delta is interpretable | **FR-26:** hardened suite = baseline assertions ∪ hard assertions. |
| **Invariant/property** assertions beat golden-value assertions (e.g. currency: X→X identity, round-trip, nanos sign/range) | Rate/data-independent ⇒ robust, deterministic, language-agnostic, hard to game, cheap to author (no embedded ECB rates) | **FR-7 sharpened + FR-27:** prefer invariant/structural probes; forbid suite coupling to external data. |
| **Joint** memorization signal: hardened coverage × CodeBLEU similarity | high coverage + low similarity = skill; high coverage + high similarity = suspected recall — near-free, more informative than either alone | **FR-16/18 refined → FR-28.** |
| `adservice`'s registered suite is **dead today** (Java never launches → always degraded, silently) | Pre-existing waste + silent degradation, independent of hardening | **FR-29 (low-hanging fruit):** log launch-degrade reasons **loudly** (un-silence the dead suite). Reframes FR-22's value: it *fixes a dead suite*, not just enables hardening. |
| A checked-in **naive stub** (e.g. currency impl ignoring nanos) makes a perfect unit test | Proves the hardened suite discriminates and documents the difficulty delta — cheap | **FR-30 (quick win):** discrimination unit test (baseline passes the stub, hardened fails it). |
| Node/Go already launch via `_DEFAULTS`; the 4 baseline suites already run + score | Hardening Node/Go is **suite + spec work, not enablement**; baseline gap is measurable **now** | **FR-8 clarified** (explicit `startup` only where defaults don't fit). **FR-31 (quick win):** measure the *existing* baseline functional-coverage gap now (via rescore of existing batches) to establish the success-metric baseline before any new spend. |

**Net:** the MVP got *cheaper and safer* — most A/B infra exists, the expensive step (generation)
happens once and suites iterate free, and the whole premise can be $0-pre-validated before spending.
Two correctness hazards (silent fallback, tier-blind rescore) were caught at document cost.

---

## 1. Problem Statement

The benchmark measures model skill by building Online Boutique gRPC services (one service per single
file). Today the tasks may not discriminate flagship from mid-tier models:

1. **Difficulty is encoded only in seed content** (`gen_ob_benchmark_seeds.py`); there's a natural
   gradient (recommendation ~120 LOC … checkout ~320 LOC) but it's neither parameterized nor paired
   with discriminating scoring.
2. **Structural scoring is satisfied by compiling stubs.** The strong discriminator — executed
   behavioral suites (Track 2) — already works for 4 services, but the *baseline* suites largely test
   happy paths, so they don't yet stress the flagship/mid-tier gap.

**Goal:** an additive, opt-in **hardened tier** that raises the behavioral correctness bar in ways the
scoring can *see*, while preserving the byte-stable baseline and the benchmark's determinism.

### Constraints (load-bearing, from planning)

- **Proto is fixed and faithful** (`demo.proto`, Apache-2.0, pinned FR-31). No new/altered RPCs;
  difficulty comes from raising the correctness bar *within* the contract.
- **Baseline seeds are byte-stable + hashed** (FR-19/R1-S9). Hardened variants are additive/opt-in.
- **Behavioral execution works only for Go/Node/Python** today (Java/C# degrade).
- **Reuse the harness** (`run_service_sandboxed`, `StartupContract`, `_SUITES` registry, language-
  agnostic gRPC client, FUNCTIONAL_WEIGHT scoring) — don't rebuild.

---

## 2. Requirements

### A. Hardened-tier mechanism (additive, deterministic) — **P1**

- **FR-1 — Additive hardened seed variant.** Emit `seed-{service}.hardened.json` *in addition to* the
  byte-identical baseline. Baseline seeds + hashes unchanged.
- **FR-2 — Tier as a run-matrix dimension.** Add `tier_states: Tuple[str,...] = ("baseline",)` to
  `BenchmarkRunSpec`; nest it innermost in `cells()`; thread `tier` through `MatrixCell`, `cell_id`,
  and `sandbox_dir_name` (segment appended only when `tier != "baseline"` → byte-identical default).
  Record tier in cell provenance. **`spec_hash()` adds `tier_states` to the identity dict ONLY when
  `!= ("baseline",)`** — the verified K2/K3 conditional-inclusion precedent, so archived
  spec_hashes/cell_ids stay byte-stable. **Tier is an open string axis** (validator: non-empty +
  unique; value set NOT restricted) so future difficulty variants (`adversarial`, `minimal-spec`)
  reuse the same machinery (flexibility).
- **FR-3 — Deterministic, byte-stable generation.** Extend `gen_ob_benchmark_seeds.py` to emit hardened
  seeds (sorted keys, no timestamps), hashed in `seeds-index.json`, `--check`-verifiable.
- **FR-4 — Seed selection per cell, fail-closed.** `SubprocessCellExecutor` selects
  `seed-{service}-{tier}.json` when `tier != "baseline"`, else `seed-{service}.json`. **If a hardened
  seed is absent, the cell is classified `infra_fail` with a named reason — it MUST NOT silently run
  the baseline seed under a hardened label** (that would corrupt the baseline-vs-hardened comparison).
  Baseline fallback is allowed *only* for `tier == "baseline"`.
- **FR-4a — Baseline is the default and byte-identical.** No tier selected ⇒ today's behavior exactly.

### B. Behavioral-suite-driven difficulty (axes A/B — core discriminator) — **P1**

- **FR-5 — Enrich/author suites following the `_SUITES` pattern.** Reuse the existing registry
  (`execute.py:28-33`) and language-agnostic gRPC client. *Enrich* existing suites (payment, currency,
  shipping, ad) for the hardened tier and/or add new ones (e.g. productcatalog).
- **FR-6 — Tier-aware suite selection.** A (service, tier) → suite binding so the harness runs the
  *hardened* suite for hardened cells and the baseline suite otherwise. (Registry already keys by
  service; extend the key or the suite to branch on tier.)
- **FR-7 — Probes target hard cases, not happy path — invariant-first.** boundary/negative/zero
  amounts, **`Money` units/nanos arithmetic & precision**, currency mismatch, malformed/missing input,
  idempotency, required gRPC status codes/error semantics. **Prefer rate/data-independent
  invariant/property assertions** (X→X identity, round-trip, sign/range rules) over golden-value
  assertions — see FR-27.
- **FR-8 — Every hardened service is executable.** Hardened cells must launch under
  `run_service_sandboxed`. Node/Go already launch via `_DEFAULTS`, so an explicit `startup` contract is
  required **only where the language default doesn't fit**; include it explicitly anyway so hardened
  seeds are self-describing. (Limited to Go/Node/Python until FR-22.)
- **FR-9 — Reuse existing scoring.** The functional term (FUNCTIONAL_WEIGHT=0.5, per-assertion,
  degrade-not-zero, compile-floor-first) already supports this — no scoring rework; optionally enable
  the existing **expose-defects** scorer (`scoring.py:390-426`).

### C. Stringent specification (axis C) — **P1**

- **FR-10 — Hardened `requirements_text` raises the bar within the fixed proto.** Explicit non-happy-
  path requirements (status codes, validation, error handling, idempotency, precision/rounding) — no
  RPC additions.
- **FR-11 — Cross-language parity of stringency** (preserves FR-31 comparability).
- **FR-12 — Spec ⇄ suite coupling.** Every added requirement is backed by a behavioral probe (FR-7).

### D. Orchestration tasks (axis D) — **P3 (DEFERRED)**

- **FR-13 — Single-file orchestration under hardened tier** (checkout-style coordination + partial-
  failure handling). *Deferred.*
- **FR-14 — Multi-process sandbox for mocked downstream deps.** Requires refactoring
  `run_service_sandboxed` → `run_services_sandboxed` (multi-launch, readiness sequencing, port map,
  process-group teardown). *Deferred — primary cost of axis D.*
- **FR-15 — Orchestration suite probes coordination correctness** (e.g. payment fails → no email).
  *Deferred.*

### E. Contamination resistance (axis E) — **DOWNGRADED**

- **FR-16 — Report the existing memorization signal.** Surface `contamination.py`'s CodeBLEU
  similarity-to-canonical-OB per (model, service, tier) in hardened reports as a memorization control.
  *(Already-built scorer; this is wiring + reporting, not perturbation.)*
- **FR-17 — (Removed) identifier-rename perturbation** — infeasible on proto-bound OB (renamable
  identifiers don't affect difficulty; proto identifiers can't be renamed). See NR-7.
- **FR-18 — Memorization delta is reported** (high CodeBLEU + high score ⇒ possible recall, not skill).

### F. Cross-cutting — **P1**

- **FR-19 — Determinism & integrity preserved** on the hardened path (zero deterministic skips in
  benchmark mode; infra-fail classification; reproducible seed hashes).
- **FR-20 — Persist-then-rescore (Mottainai), tier-aware.** `rescore_behavioral.py` must thread `tier`
  (read from `cells.json`; load `seed-{service}-{tier}.json`; `sandbox_dir_name(..., tier=)`; pass
  `tier` into `run_behavioral_cell`) so hardened persisted servers re-score for $0 as suites improve.
  Add a `--suite-tier {baseline|hardened}` override that scores persisted servers with a suite tier
  **decoupled from their generation tier** (enables FR-24). *(Today's rescore is tier-blind — required
  work, not free.)*
- **FR-21 — Tier-labeled results.** Aggregation distinguishes baseline vs hardened so the dial's effect
  on the flagship/mid-tier gap is measurable (the success metric, OQ-6).
- **FR-22 — (P2) Java/C# launch provisioning.** Add `provision.py` serve/build strategies + `_DEFAULTS`
  for Java and C# so `adservice`/`cartservice` can be behaviorally executed and hardened. Until then,
  hardened behavioral coverage is explicitly Go/Node/Python only (logged, not silent). **Note (FR-29):
  this also revives `adservice`'s currently-dead suite — value beyond hardening.**

### G. Planning-derived additions (v0.4) — robustness, value, flexibility, quick wins

- **FR-23 — Generate-once / iterate-suite-free (Mottainai sequencing).** Hardened server *generation*
  (the only LLM spend) happens once; suite assertions are then enriched and re-scored for **$0** via
  rescore (FR-20). Implementation must keep generation and suite richness decoupled (don't bake suite
  logic into generation). *Value + flexibility + quick win.*
- **FR-24 — $0 suite-discrimination pre-validation.** Before committing to hardened generation spend,
  validate that hardened assertions discriminate by running the **hardened suite against existing
  baseline persisted servers** (FR-20 `--suite-tier`). A happy-path baseline server should score lower
  on hardened assertions. *Quick win / de-risk; mitigates R4.*
- **FR-25 — Success metric = functional-coverage gap, not composite.** The effort succeeds iff the
  **flagship − mid-tier functional-coverage gap on the hard-assertion subset** is larger under
  `hardened` than `baseline`, on the P1 services across ≥2 model cohorts. Report raw functional
  coverage; do **not** judge success on the composite (its 50% structural term is passed by both
  tiers and dilutes the signal). *(Resolves OQ-6.)*
- **FR-26 — Hardened suite is a superset of baseline.** Hardened runs the baseline assertions **plus**
  the hard ones, so per-assertion coverage degrades monotonically and the per-model baseline→hardened
  delta is interpretable. *Robustness of the metric.*
- **FR-27 — Invariant/structural assertions; no external-data coupling.** Hardened assertions must be
  rate/data-independent properties (identity, round-trip, sign/range, error-on-invalid) and must not
  embed or depend on external datasets (e.g. ECB rates). Deterministic, language-agnostic, hard to
  game, cheap to author. *Robustness + flexibility + lower authoring cost.*
- **FR-28 — Joint memorization signal.** Report hardened functional coverage **together with**
  `contamination.py` CodeBLEU similarity per `(model, service, tier)`: low similarity + high coverage =
  genuine skill; high similarity + high coverage = suspected recall. Supersedes the standalone framing
  of FR-16/FR-18. *Value, near-free.*
- **FR-29 — Un-silence launch degradation (low-hanging fruit, pre-existing bug).** When a service can't
  launch (today: Java/C#), the harness must **log the degrade reason loudly** rather than silently
  scoring structural-only. Surfaces that `adservice`'s registered suite is currently dead. Independent
  of hardening; fix regardless. *Quick win + robustness.*
- **FR-30 — Discrimination unit test (naive-stub fixture).** Check in a deliberately naive
  implementation (e.g. a currency service that ignores `nanos`); assert the **baseline** suite passes
  it (~1.0) and the **hardened** suite fails the relevant invariants (<1.0). Proves discrimination and
  documents the difficulty delta in CI. *Quick win.*
- **FR-31 — Establish the baseline gap now ($0).** Before any new spend, measure the **existing**
  baseline functional-coverage gap between model cohorts (rescore existing batches; 4 suites already
  run). This is the reference the hardened tier must widen (FR-25). *Quick win — uses what already
  exists.*

---

## 3. Non-Requirements

- **NR-1.** No changes/extensions to `demo.proto` (no new/altered RPCs).
- **NR-2.** No multi-file-in-one-shot tasks (v0.1 scope; hard 3-layer assumption). Deferred.
- **NR-3.** No changes to plan-ingestion Gate 2a/PARSE, complexity tiers, or micro-prime decomposer.
- **NR-4.** No mutation of committed baseline seeds or hashes.
- **NR-5.** No real end-user/company content (bucket 4).
- **NR-6.** Not hardening all 9 services at once — start with launchable, trap-rich P1 services.
- **NR-7.** No identifier-rename perturbation on the OB corpus (infeasible — see §0.1). True
  contamination-resistance is out of scope here and would require a separate non-OB task corpus.

---

## 4. Open Questions

- **OQ-2 (deferred).** Exact shape of the multi-process sandbox for orchestration (FR-14) — port
  allocation, readiness DAG, teardown hierarchy. Revisit when P3 is scheduled.
- **OQ-3 (reframed).** Is a separate **non-OB perturbable corpus** worth building for true
  contamination-resistance, or is the CodeBLEU signal (FR-16) sufficient? (Out of this doc's scope.)
- **OQ-6 (success metric) — RESOLVED by FR-25.** Compare the flagship − mid-tier **functional-coverage
  gap on the hard-assertion subset**, hardened vs baseline. Still open: the *threshold* delta that
  counts as "successful" — calibrate against FR-31's measured baseline gap.
- **OQ-7 (P1 service subset).** Confirm P1 set: **currencyservice** (Node, nanos arithmetic, suite
  exists) + **paymentservice** (Node, suite exists) first; then **productcatalogservice** (Go, search
  semantics — needs a new suite) and **shippingservice** (Go, suite exists). Cartservice/adservice wait
  on FR-22.
- **OQ-8 (suite-tier encoding) — RESOLVED in plan.** Decision: a `tier` **parameter** on the existing
  suite fn + `run_behavioral_cell`, with the suite running a baseline∪hard **superset** (FR-26). Shares
  client setup; threads cleanly through rescore (FR-20).

---

*v0.4 — Three reflective passes (scope-pivot → harness → implementation plan). Scope: additive
hardened single-file difficulty tier. Implementation planning added FR-23…FR-31 — caught two
correctness hazards (silent seed fallback, tier-blind rescore), reframed the success metric to
functional-coverage gap, and exposed several $0 quick wins (generate-once/iterate-suite-free,
pre-validate discrimination, measure the baseline gap now, naive-stub discrimination test, un-silence
the dead adservice suite). MVP is cheaper and safer than at v0.2. Next: optional CRP review, then
implement P1 — M0 (tier axis) → M1 (hardened seeds) → minimal M2 → generate once → iterate suites $0
(lead with currencyservice).*
