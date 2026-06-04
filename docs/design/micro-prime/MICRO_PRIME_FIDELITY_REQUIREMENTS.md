# Micro-Prime Fidelity — Requirements

**Version:** 0.3 (distillation pass — essential-complexity review against the live code)
**Date:** 2026-06-04
**Status:** Draft (planning-corrected + distilled). Pairs with `MICRO_PRIME_FIDELITY_PLAN.md` (v0.3).
**Owns:** the two *remaining* fidelity gaps on the cheapest generation tier (micro-prime), after
`CONVENTION_AWARE_REPAIR` Phase C sub-step **8b** (static convention authority) landed (`24893fcc`).
**Relationship to existing specs:**
- **Gap A** below **is** the unshipped half of **FR-CAR-5 / Phase C 8a** in
  `../repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md`. This doc does **not** redesign the seam
  (CAR already nails it); it **completes** it with corrected status + sharpened, measurable acceptance.
- **Gap B** is explicitly a **Non-Requirement** of CAR ("routing convention-strict views away from
  micro-prime is a sibling change") and is only gestured at by **FR-CAR-9** ("D3 — SIMPLE + strict
  house-style → not micro-prime"). No requirement owned it. This doc gives it a home.

---

## 0. Planning Insights (Self-Reflective Update: v0.1 → v0.2)

> The planning pass (3 parallel code explorations) tested v0.1's assumptions against the actual
> micro-prime prompt/truncation, classifier, and decomposer code. It resolved **5 of 6 open questions** and
> forced **2 substantive requirement corrections** + **1 reframe** — the loop working as intended (the
> alternative was discovering these during implementation at 10× the cost).

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| FR-MPF-1 is a clean wiring change; OQ-1 asks "does the field-set block *fit* the ~1024-token budget?" | `domain_constraints` (where `convention_guidance` and the new block merge, rendered as "# Domain constraints (MUST follow these)") is **explicitly excluded from `_truncate_to_budget`'s `_REMOVABLE` list** — the budget trimmer cuts few-shot → sibling stubs → design-doc only, **never** domain_constraints (`prompt_builder.py:1115-1167`). The block is never truncated. | **OQ-1 inverts.** The risk isn't "gets trimmed," it's "an oversized un-trimmable block evicts every removable section and *still* overflows 1024, starving the skeleton." FR-MPF-1 **MUST self-bound** the block (referenced-entity scope + hard cap + enum-names-only fallback). Truncation will not save us — new **acceptance** added. |
| FR-MPF-3: a rich spec "MUST NOT be SIMPLE" (implicitly → MODERATE) | The classifier order is COMPLEX-triggers → SIMPLE-eligibility → relaxed-SIMPLE → **default COMPLEX** (`classifier.py:299`); the existing `has_fillable_elements is False` precedent emits **COMPLEX**. Reusing that shape (or relying on the default) sends rich specs to the **premium** tier. | **FR-MPF-3 corrected:** emit an explicit **MODERATE floor** (standard-LLM), not COMPLEX. A rich-but-well-specified file needs an LLM, not the most expensive one; over-provisioning to COMPLEX is a cost regression that defeats the thesis. |
| OQ-4: unknown whether the surface guard overrides `complexity_tier_override` | `complexity_tier_override` **short-circuits the classifier entirely** (`contractors/context_seed/core.py`): a valid override wins, the classifier (and our guard) never runs; invalid → falls through to classify. | **OQ-4 resolved:** the guard yields to explicit human override **by existing design** — no special handling. FR-MPF-3 note added. |
| OQ-3: convention-strict is knowable at classify time via `CANONICAL_LAYOUT` | `CANONICAL_LAYOUT` lives in `backend_codegen` and maps **kind→path**; the classifier sees `manifest.file_specs` (pre-gen contracts) + seed metadata. Ownership isn't readable from the manifest, but `SeedTask.artifact_types_addressed` **maps to a CANONICAL_LAYOUT kind** at classify time. | **OQ-3 resolved (reframe):** FR-MPF-4's **preventive** signal derives from `artifact_types_addressed`→kind, not manifest inspection; the FR-CAR-9 Kaizen per-tier signal is the **reactive** fallback. Both feasible pre-generation. |
| OQ-5: decomposed SIMPLE sub-elements might bypass the new field (structural-bypass-one-level-down) | The merge at `process_file_with_context` (`engine.py:2568-2570`) sets `self._current_domain_constraints` (`process_file:2257`), and **every** prompt-build site reads it — file-whole, element, AND decomposed sub-elements (`_generate_sub_elements`→`_handle_simple`→`_generate_with_retry:4361/4372`). | **OQ-5 resolved positive** for the PrimeContractor path: decomposition does **not** bypass the field. Caveat: the standalone public `process_element()` API leaves `_current_domain_constraints=None` (documented, `engine.py:1823-26`) — but `convention_guidance` (8b) has the **identical** limitation, so FR-MPF-1 doesn't regress it; standalone is an explicit **non-goal**. |
| FR-MPF-2 element-count might mis-fire on empty framework-config specs (RUN_007) | Framework-config files (`next.config`, `tsconfig`) carry `elements:[]` → `len(elements)=0` → below any positive threshold → stay SIMPLE-eligible (correct). The existing FR-7 `has_fillable_elements` already exempts them via `framework_provenance_for_path`. | **FR-MPF-2 confirmed safe** — the count guard is structurally inert on legitimately-empty framework files; no special-casing needed. |

**Resolved open questions**
- **OQ-1 → resolved.** Self-bound the field-set block (scope + cap + fallback); the budget trimmer won't touch domain_constraints. Cap policy is now part of FR-MPF-1, not a deferred question.
- **OQ-2 → method resolved, value still open.** Derivation is the `has_fillable_elements` precedent (sum `len(spec.elements)` over covered targets). The threshold *value* still needs empirical calibration (RUN_007 stub'd files as should-elevate cases vs a known-good SIMPLE corpus) → ship **permissive** (no-op) and calibrate under FR-MPF-5.
- **OQ-3 → resolved (partial).** Preventive via `artifact_types_addressed`→`CANONICAL_LAYOUT` kind; reactive via Kaizen. Direct manifest-ownership read is **not** available pre-gen.
- **OQ-4 → resolved.** `complexity_tier_override` short-circuits the classifier; guard yields automatically.
- **OQ-5 → resolved.** Covered for the PrimeContractor path incl. decomposition; standalone `process_element()` is a pre-existing, equally-affecting (convention_guidance) non-goal.
- **OQ-6 → still open.** The injection-efficacy metric for FR-MPF-4/5 — adopt the CKG **structural-adherence** methodology, but class granularity (per artifact-kind vs per-domain) and N remain to define.

---

## 0.1 Code-state & distillation pass (v0.2 → v0.3)

> Read the live code these requirements touch, to (a) reconcile against work that landed mid-spec and
> (b) actively avoid accreting accidental complexity. Two outcomes: a **status correction** and a
> **scope reduction** (one requirement demoted, two debt items named-and-deferred rather than bundled).

**Code-state correction — FR-MPF-1 wiring already landed (uncommitted), but WITHOUT the cap.** A
concurrent session implemented the context+merge wiring from v0.2: `MicroPrimeContext.upstream_interfaces`
(`context.py:33`) + `from_prime` forward (`:92`) + the merge in `process_file_with_context`
(`engine.py:2571-2575`, appends `upstream_interfaces` then `convention_guidance` into `domain_constraints`).
**The self-bounding cap (the load-bearing v0.2 correction) was NOT included** — it is a naked
`constraints.append(context.upstream_interfaces)`. Since `_truncate_to_budget` (`prompt_builder.py:1130`)
trims only `_REMOVABLE` (few-shot → sibling → design-doc) and **leaves `domain_constraints` untouched**,
the live tree now carries the exact risk v0.2 flagged: a large field-set block **evicts the few-shot
examples** (a primary cheap-model adherence lever) and can still overflow the 1024-token budget. **So
FR-MPF-1's remaining work is NOT the wiring — it is the cap + the budget-non-regression test + the efficacy
measurement.** Requirement updated accordingly.

**Distillation decisions:**

| Finding (in the live code) | Decision |
|---|---|
| **FR-MPF-4 is a speculative second lever.** RUN-032's micro-prime failures were convention (now covered by 8b `convention_guidance`) + field-invention (covered by FR-MPF-1). No evidence yet exists of a class that *injected* micro-prime still can't handle. Building an efficacy-gated route-away now is complexity ahead of need. | **FR-MPF-4 DEMOTED to contingent** — do not build until FR-MPF-1's measured residual demonstrates a concrete class injection cannot fix. Keeps v1 to its essential core: inject (capped) + surface-route. |
| **Two near-duplicate constraint renderings.** `_build_element_prompt_core` emits BOTH `# Domain constraints (MUST follow these):` (the merged `binding_constraints`+`upstream_interfaces`+`convention_guidance`) AND `# Constraints:` (from `_render_constraints(contracts)`) — two similarly-named authority blocks, provenance lost, and a junk-drawer merge that grows one ad-hoc `append` per authority. | **Named as Deferred Debt D-1, NOT bundled.** Consolidating is a *prompt-shape* change → it moves cheap-tier adherence numbers, so it must ride FR-MPF-1's measurement gate, not be smuggled into the wiring. |
| **`_truncate_to_budget` is the accidental twin of `enforce_prompt_budget`.** Micro-prime budgets by a hardcoded *exclusion list* and simply **gives up (logs debug) when still over** — no cap on protected sections. The lead path (`implementation_engine/budget.py`) already solves this correctly with **priority-ordered** P0–P3 removal. Two budget engines for one essential problem. | **Named as Deferred Debt D-2.** The FR-MPF-1 self-cap is the **anti-deepening** move (stops the junk drawer from overflowing); full unification onto one budget model is the real fix — large, deferred, must not be bundled into this change. |
| **`signals.py` walks `manifest.file_specs` ~3× per call** (edit-mode set, `_compute_manifest_coverage`, `has_fillable_elements`). | **FR-MPF-2 refined:** compute `manifest_element_count` **inside the existing `has_fillable_elements` loop** (`signals.py:245-256` already accesses `file_specs[tf].elements`) — no 4th scan. |
| **A second, vestigial signal-extractor exists** (`signals.py` ~480-630, the Artisan-chunk path; Artisan is ON HOLD). | **FR-MPF-2 scope guard:** do NOT add the signal to the chunk extractor — spreading a new signal into dead code is pure accidental complexity. Derive it once, on the active feature path. |
| **MODERATE/COMPLEX default mismatch:** `models.py` documents MODERATE as the default tier, but `classifier.py:299` falls through to **COMPLEX**. FR-MPF-3 introduces the *first explicit MODERATE emit*. | **FR-MPF-3 note added** — the MODERATE floor is new ground, not a well-trodden path; do not assume an existing MODERATE branch. Do **not** attempt to fix the global default in this change (risky, out of scope). |

---

## 0.5 Problem statement

Micro-prime is the **cheapest** tier (local Ollama / no-LLM template paths) and the tier with the
**largest validated adherence lift** from authority injection (CKG Phase 2: cheap-tier field-set adherence
**0.05–0.40 → ~1.0**). It is therefore the highest-leverage place to improve requirement→code fidelity at
the lowest cost. Two gaps keep it from realizing that leverage:

### Gap A — the validated authority never crosses into micro-prime (incomplete FR-CAR-5)

The lead/drafter path threads `gen_context["upstream_interfaces"]` — a per-feature-scoped block of
**Prisma field-sets + enums + module-path negatives** produced by
`contractors/prime_contractor.py::_collect_upstream_interfaces()` (set at `prime_contractor.py:4439-4441`).
That is the exact string whose injection produced the 0.05→1.0 lift on the lead path.

Micro-prime never receives it. `MicroPrimeContext.from_prime()` (`micro_prime/context.py:54-91`) reads
`domain_constraints`, `existing_files`, `dependency_imports`, `ollama_model`, and (since `24893fcc`)
derives a **static** `convention_guidance` from `repair.convention` — but it **drops**
`gen_context["upstream_interfaces"]`. A grep of `micro_prime/` for
`project_knowledge` / `upstream_interface` / `field_set` returns **zero hits**.

> **Convention authority ≠ field-set authority.** `convention_guidance` (landed, FR-CAR-5b/8b) is
> *static, per-language* idiom — "use FastAPI not Flask, `app.tables` not `app.models`,
> `session.exec(select())` not `session.query`." The field-set/enum authority (this gap, FR-CAR-5b/8a) is
> *dynamic, per-project, per-feature* data-model truth — *this* project's actual entities and their
> authoritative scalar field sets + enum value sets. The first prevents the framework/ORM/module class
> (RUN-028/032); the second prevents the **field-invention** class (RUN-011 Gap A: invented `aiRefId`,
> `label`, Prisma↔Zod field-name disagreement). 8b shipped; 8a did not.

For a Python project the TS/JS portion of `_collect_upstream_interfaces` is empty (its producer is gated to
`.ts/.tsx/.js/...`); the **load-bearing** payload is the Prisma field-set/enum block, which is produced
regardless of target language. So "forward the string" is necessary but not sufficient — the acceptance
must assert the **field-set block** reaches a schema-referencing micro-prime element, not merely that a
(possibly empty) string was forwarded.

### Gap B — the classifier routes by text-heuristics, with no surface-area or house-style signal

`extract_signals_from_feature()` (`complexity/signals.py`) derives `TaskComplexitySignals`
(`complexity/models.py:52-83`) from `estimated_loc`, `blast_radius`, `manifest_coverage`,
`has_fillable_elements` — **but never counts the elements in the target file's `ForwardFileSpec`**, even
though the manifest is already passed in. `has_fillable_elements` (RUN-007 FR-7) is a *lower* guard — it
stops **empty/under-specified** specs from reaching the no-LLM SIMPLE tier. There is **no symmetric upper
guard**: a *rich, fidelity-critical* spec (a full schema mirror, a CRUD layer) with a low LOC estimate
still classifies SIMPLE and lands on the cheapest tier. RUN_007 is the proof: a full Zod-schema mirror and
a full React form were routed SIMPLE → emitted 3-line empty-class stubs → scored **0.94 PASS**. The
requirement was perfectly specified; the **routing decision discarded it before any prompt was built**.

### Why both, and in this order

Gap A and Gap B are two levers on one axis — *can we trust the cheapest tier?*:
- **Lever 1 — inject** (Gap A): make micro-prime *competent* by giving it the same authority the lead path
  has.
- **Lever 2 — route** (Gap B): for work where even injected micro-prime is too risky (high surface area,
  strict house-style), send it to a stronger tier.

They compose. The correct sequence is **inject first, then calibrate routing on the residual** — tightening
routing-away *before* measuring injection efficacy would push work to expensive tiers that cheap+injected
could have handled, defeating the cost thesis. This sequencing is itself a requirement (FR-MPF-5).

---

## 1. Functional Requirements

### FR-MPF-1 — Field-set/enum authority reaches the micro-prime generation prompt (completes FR-CAR-5b/8a)
The per-feature-scoped **Prisma field-set + enum + module-path-negative** block produced by
`_collect_upstream_interfaces()` and currently surfaced only as `gen_context["upstream_interfaces"]` on the
lead path MUST reach the micro-prime generation prompt.
> **Status (v0.3): wiring landed uncommitted; the CAP is the remaining work.** `context.py` +
> `engine.py:2571-2575` already forward and merge `upstream_interfaces` (no longer "dropped"). What
> remains — and is now the substance of this requirement — is the **self-bounding cap** below, its
> **budget-non-regression test**, and the **efficacy measurement**. The wiring without the cap is a latent
> few-shot-eviction / budget-overflow regression (see §0.1).

- **Seam (from CAR, not re-derived):** add a field to the **frozen** `MicroPrimeContext`
  (`context.py:11`); read it from `gen_context` in `from_prime`; merge it into `constraints` in
  `process_file_with_context` (`engine.py:2557-2579`) alongside the already-landed `convention_guidance`;
  render it through the existing prompt builders (`_build_element_prompt_core`, `_build_file_whole_prompt`).
- **Scoping parity:** reuse the lead path's per-feature entity scoping (`referenced_entities` →
  `field_sets` for referenced entities, full-set fallback for whole-model mirrors). Do **not** re-derive
  scoping and do **not** inject the full project field-set for every element.
- **Self-bounding (v0.2, from OQ-1 inversion — load-bearing):** the merged block lands in
  `domain_constraints`, which `_truncate_to_budget` **never trims** (`prompt_builder.py:1115-1167` —
  `_REMOVABLE` excludes it). Therefore FR-MPF-1 MUST bound the block **itself**, or it will evict the
  removable sections (few-shot, sibling stubs, design-doc) and still overflow the ~1024-token
  `input_token_budget`, starving the skeleton. Bound order: (1) referenced-entity scope (already);
  (2) hard char/token cap on the rendered block; (3) degraded fallback (enum-names + field-names only,
  drop types/comments) when the cap is hit. A skeleton-evicting block is a **regression**, not a feature.
- **Acceptance (presence):** after this change, `grep -r project_knowledge|upstream_interface|field_set
  micro_prime/` returns **> 0**; for a Python feature whose name/description/target-stem references a schema
  entity, the rendered micro-prime prompt **contains that entity's authoritative scalar field set**.
- **Acceptance (budget non-regression, v0.2):** with the field-set block present, the skeleton and the
  few-shot/sibling sections are **not** evicted on a representative element at the default 1024 budget
  (i.e. the block fits within its cap, not by displacing required context).
- **Coverage scope (v0.2, OQ-5 resolved):** the merge at `process_file_with_context` covers all
  PrimeContractor paths **including decomposed MODERATE→SIMPLE sub-elements** (verified:
  `_current_domain_constraints` is read by every prompt site). The standalone public `process_element()`
  API (which leaves `_current_domain_constraints=None`) is an explicit **non-goal** — it already bypasses
  `convention_guidance` (8b) identically, so this requirement neither covers nor regresses it.
- **Acceptance (efficacy — the load-bearing one):** the **RUN-011 Gap-A field-invention class** (a
  micro-prime-generated schema mirror / CRUD layer inventing field names absent from the Prisma model) does
  **not recur** on the SIMPLE tier, measured by structural adherence scoring (CKG methodology, not a
  denylist). *Injection ≠ adherence* (the `adherence.py` guardrail): forwarding the string is necessary,
  not sufficient — the requirement is met by the measured lift, not by the wiring alone.
- **Honesty note:** 8b (`convention_guidance`) already landed (`24893fcc`); this requirement is the
  field-set half. The two render into the **same** prompt section ("house-style — generate to these, do not
  invent"); this requirement only adds the second source.

### FR-MPF-2 — Surface-area complexity signal
`TaskComplexitySignals` MUST carry a manifest-derived **surface metric** — the count of contract-bearing
elements (functions/classes/methods/constants) in the target file's `ForwardFileSpec`. It MUST be derived
inside `extract_signals_from_feature` from the **manifest already passed in** (no new inputs, no LLM). This
complements `has_fillable_elements` (lower guard for empty specs); FR-MPF-2 is the structural input to the
upper guard (FR-MPF-3).
**v0.2 (verified safe):** derivation follows the `has_fillable_elements` precedent exactly (sum
`len(getattr(spec, "elements", []) or [])` over `target_files` present in `manifest.file_specs`; `None`
when no manifest). Empty framework-config specs (`next.config`/`tsconfig`, `elements:[]`) yield count `0`
→ below any positive threshold → stay SIMPLE-eligible (correct); FR-7's `framework_provenance_for_path`
already exempts them. No special-casing needed.
**v0.3 (single-pass; no dead-code spread):** compute the count **inside the existing
`has_fillable_elements` loop** (`signals.py:245-256` already walks `file_specs[tf].elements`) — `signals.py`
already passes over `file_specs` ~3×; do not add a 4th. Derive it **only on the active feature path**
(`extract_signals_from_feature`); do **not** add it to the vestigial Artisan-chunk extractor
(`signals.py` ~480-630; Artisan is ON HOLD) — spreading a signal into dead code is accidental complexity.

### FR-MPF-3 — Surface-aware routing guard (rich specs are not SIMPLE)
The classifier MUST NOT classify a target as **SIMPLE** (the cheap / no-LLM / micro-prime path) when its
forward-manifest surface metric (FR-MPF-2) exceeds a configured threshold
(`ComplexityRoutingConfig.manifest_element_simple_max`), **regardless** of what the LOC / blast-radius
heuristics say. It MUST emit a forensic reason (`manifest_element_count {n} > {threshold}`). Rationale:
element count is a structural truth the LOC estimate misses (RUN_007).
**v0.2 (corrected — MODERATE floor, NOT COMPLEX):** the classifier's default fall-through is **COMPLEX**
(`classifier.py:299`) and the existing `has_fillable_elements is False` precedent emits COMPLEX. A rich
spec MUST NOT inherit that shape — over-specified ≠ under-specified. A rich-but-well-specified file needs an
**LLM**, not the **premium** tier; routing it to COMPLEX is a cost regression that defeats the
cost-minimization thesis. So the guard disqualifies SIMPLE and emits an explicit **MODERATE floor**,
evaluated *after* the COMPLEX-trigger block so a genuine COMPLEX trigger still wins. Contrast with
`has_fillable_elements` (empty spec → COMPLEX, because under-specification needs max capability): rich spec
→ MODERATE, empty spec → COMPLEX — complementary rules, not the same one.
**v0.2 (OQ-4 resolved):** the guard runs only on the auto-classification path; a valid
`complexity_tier_override` short-circuits the classifier upstream (`context_seed/core.py`), so an explicit
human override always wins — no precedence handling needed here.

### FR-MPF-4 — House-style-strict route-away (CONTINGENT — do not build until the residual demands it)
> **v0.3: DEMOTED from a v1 requirement to a contingency.** This is a *second* lever (route away) layered
> on FR-MPF-1 (inject). RUN-032's micro-prime failures were convention (covered by landed 8b) +
> field-invention (covered by FR-MPF-1). There is **no current evidence** of a class that *injected*
> micro-prime still mishandles — so building an efficacy-gated route-away now is complexity ahead of need.
> **Trigger to build:** FR-MPF-1's measurement (FR-MPF-5) shows a concrete convention-strict class whose
> adherence stays below threshold *after* injection. Until then this requirement is **not implemented**.

When (and only when) triggered: for a **convention-strict** target the classifier treats "SIMPLE + strict
house-style" as **ineligible** for the no-LLM/micro-prime path **unless** FR-MPF-1 injection has
demonstrated adherence ≥ a configured threshold on that class (so injection competence buys back cheap-tier
eligibility). This is the "route away" lever (postmortem A1 / deterministic-first review D3).
**v0.2 (OQ-3 resolved — how "convention-strict" is known at classify time):** `CANONICAL_LAYOUT` ownership
is **not** readable from `manifest.file_specs` (those are pre-gen contracts). Two feasible sources instead:
(a) **preventive** — map `SeedTask.artifact_types_addressed` to a `CANONICAL_LAYOUT` kind (e.g.
`pydantic-models`→`app/models.py`), available pre-generation from seed metadata; (b) **reactive** — the
FR-CAR-9 Kaizen per-tier convention-violation signal for that domain/kind. (a) is the primary preventive
path; (b) is the fallback when the kind can't be inferred pre-gen. Neither requires post-generation data.

### FR-MPF-5 — Inject-first sequencing with a measurement gate
FR-MPF-1 MUST ship and its adherence lift on the micro-prime tier MUST be **measured** (structural scoring,
CKG methodology, against the RUN-028/RUN-032 + Controlled-Corpus `false_pass_risk` fixtures) **before** the
FR-MPF-3 / FR-MPF-4 routing thresholds are tightened from their initial (permissive / advisory) values.
Routing-away is calibrated on the **residual** failures *after* injection, never pre-emptively. The
permissive→active flip for FR-MPF-3/4 follows the CAR FR-CAR-11 discipline: a stated numeric precondition,
not a judgment call.

### FR-MPF-6 — Deterministic, reuse-not-rebuild
No new LLM calls; the classifier stays deterministic. FR-MPF-1 reuses `_collect_upstream_interfaces` +
the `MicroPrimeContext` threading seam (the FR-CAR-5 path). FR-MPF-2/3 reuse `TaskComplexitySignals` /
`extract_signals_from_feature` / `ComplexityRoutingConfig`. Same tree → same routing decision + same
prompt.

---

## 2. Non-Requirements

- **Not** re-implementing the adherence injection or the field-set extraction — reuse `project_knowledge` /
  `_collect_upstream_interfaces` verbatim; FR-MPF-1 only wires the **existing** output to a new consumer.
- **Not** the convention-authority half (8b) — landed (`24893fcc`).
- **Not** a change to the lead/drafter path — it already receives both authorities.
- **Not** removing or weakening `has_fillable_elements` — FR-MPF-2/3 are the complementary **upper** guard.
- **Not** routing-away-by-default — FR-MPF-3/4 ramp from permissive→active behind config + the FR-MPF-5
  measurement gate (mirrors the CAR advisory→gating posture).
- **Not** a general intent-inference engine — the surface metric is a structural element count, not a
  semantic complexity judgment.

---

## 3. Open Questions

> **v0.2: 5 of 6 resolved by the planning pass** (see §0). Retained below with resolutions inline, per the
> reflective-loop discipline: modify, don't delete.

- **OQ-1 (token budget) — ✅ RESOLVED (inverted).** The merge target `domain_constraints` is **never
  truncated** (`_truncate_to_budget._REMOVABLE` excludes it), so the question is not "does it fit?" but
  "the block must not evict the removable sections." FR-MPF-1 now **self-bounds** the block (scope + hard
  cap + enum/field-names-only fallback). No longer open.
- **OQ-2 (threshold calibration) — 🟡 PARTIAL.** Derivation method resolved (`has_fillable_elements`
  precedent). The `manifest_element_simple_max` **value** still needs empirical calibration against the
  RUN_007 stub'd files vs a known-good SIMPLE corpus → ship **permissive** (no-op) and calibrate under
  FR-MPF-5. Still open: the number.
- **OQ-3 (convention-strict at classify time) — ✅ RESOLVED (reframe).** Not via `CANONICAL_LAYOUT`
  manifest ownership (unavailable pre-gen); via `SeedTask.artifact_types_addressed`→kind mapping
  (preventive) + Kaizen per-tier signal (reactive). Folded into FR-MPF-4.
- **OQ-4 (override precedence) — ✅ RESOLVED.** `complexity_tier_override` short-circuits the classifier
  entirely (`context_seed/core.py`); the guard yields to an explicit override by existing design.
- **OQ-5 (decomposer inheritance) — ✅ RESOLVED (positive).** Decomposed SIMPLE sub-elements **do** inherit
  the field via `self._current_domain_constraints` (every prompt site reads it). Standalone
  `process_element()` is a pre-existing, identically-affecting (convention_guidance) non-goal. Folded into
  FR-MPF-1 "Coverage scope."
- **OQ-6 (efficacy metric) — 🟡 STILL OPEN.** FR-MPF-4/5's "adherence ≥ threshold" gate: adopt the CKG
  **structural-adherence** scoring methodology, but the **class granularity** (per artifact-kind vs
  per-domain) and **N** for statistical validity remain to define before FR-MPF-4 can flip from advisory.

---

## 4. Deferred accidental-complexity debt (named, not bundled)

> Found while reading the live code (§0.1). Recorded so they are not lost, and explicitly **excluded** from
> this change — each has adherence or blast-radius implications that make bundling them *into* FR-MPF-1
> reckless. The FR-MPF-1 self-cap is chosen precisely so it does not *deepen* either.

- **D-1 — Two near-duplicate constraint sections + the junk-drawer merge.** The micro-prime element prompt
  renders both `# Domain constraints (MUST follow these):` (merged `binding_constraints` +
  `upstream_interfaces` + `convention_guidance`) and `# Constraints:` (from `_render_constraints(contracts)`)
  — two similarly-named authority blocks with lost provenance, fed by an `if X: constraints.append(X)` chain
  that grows per authority. **Fix (deferred):** one labelled, ordered authority section. **Why not now:** a
  prompt-shape change moves cheap-tier adherence numbers → it must ride FR-MPF-1's measurement gate, not the
  wiring change.
- **D-2 — Micro-prime re-implements prompt budgeting, worse.** `_truncate_to_budget` (`prompt_builder.py:
  1115`) budgets by a hardcoded exclusion list and **gives up (debug-logs, returns over-budget) when still
  over** — there is no cap on the protected sections, which is *why* must-keep content migrated into the
  never-trimmed `domain_constraints`. The lead path already solves this with priority-ordered P0–P3 removal
  (`implementation_engine/budget.py::enforce_prompt_budget`). **Fix (deferred):** converge micro-prime onto
  one budget model. **Why not now:** large refactor; the FR-MPF-1 self-cap is the minimal anti-deepening
  move that removes the immediate overflow risk without it.

---

*v0.3 — Distillation pass against the live code. Status corrected (FR-MPF-1 wiring already landed
uncommitted **without** the cap → the cap + tests + measurement is the real remaining work); **FR-MPF-4
demoted** to a contingency (speculative second lever — build only if the measured residual demands it);
**FR-MPF-2** refined to a single manifest pass with no dead-code spread; **2 deferred-debt items** (D-1
duplicate constraint sections, D-2 the accidental second budget engine) named and explicitly **not
bundled**. Net: v1 surface shrank — inject (cap the one real risk) + surface-route + measure; everything
else is deferred or reuse.*

*v0.2 — Post-planning self-reflective update. 5 of 6 open questions resolved by the planning pass;
**2 requirements corrected** (FR-MPF-1 must self-bound the field-set block — the budget trimmer never
touches `domain_constraints`, so an oversized block evicts required context; FR-MPF-3 emits a **MODERATE
floor**, not COMPLEX — over-provisioning the premium tier is a cost regression); **1 reframed** (FR-MPF-4's
classify-time convention-strict signal comes from `artifact_types_addressed`, not manifest ownership);
FR-MPF-2 verified safe on empty framework specs; OQ-5's structural-bypass-one-level-down risk verified
**absent** for the PrimeContractor path. Net: the work is mostly clean wiring over verified seams, with one
real design constraint (self-bounding) the v0.1 draft missed.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

Append-only. Reviewers add to Appendix C; the orchestrator records dispositions in A (applied) / B
(rejected, with rationale). Do not delete A/B — they are the cross-model memory that stops re-proposal.

### Reviewer Instructions (for humans + models)
- **Before suggesting**: scan Appendix A and B; do not re-suggest applied or rejected items.
- **When proposing**: append a `#### Review Round R{n}` block under Appendix C with IDs `R{n}-F{k}`
  (requirements) / `R{n}-S{k}` (plan).
- **When validating (orchestrator)**: append a row to Appendix A or B referencing the suggestion ID.
- **If rejecting**: record the specific rationale.

### Appendix A: Applied Suggestions
| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) | | | | |

### Appendix B: Rejected Suggestions (with Rationale)
| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) | | | | |

### Appendix C: Incoming Suggestions (Untriaged, append-only)
_(awaiting first review round)_
