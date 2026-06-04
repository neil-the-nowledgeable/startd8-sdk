# Sapper — Pre-Execution Plan Validation (Tunnel-Alignment Survey) — Requirements

**Version:** 0.7 (Post-implementation — FR-SAP-7 reconciled with the shipped `startd8.fde`: ground-truth oracle + compose seam)
**Date:** 2026-06-04
**Status:** Draft — no production code yet. v0.1 (pre-planning) corrected against the actual `domain-preflight`,
`preflight_rules`, `python_toolchain`, `forward_manifest`, `project_knowledge`, and `element_fillability`
code (**7 corrections**, §0); the **two mechanism routes were spike-validated** against the real RUN-028 fixture
(existence bore §0.6, conformance route §0.7); **five convergent-review rounds** (§0.8, Appendix A–C) hardened the
design layer; then the **companion implementation plan** was drafted and its planning pass tightened 4 boundaries
(§0.9). Feasibility, design, and build-sequencing are all evidence-backed. Pairs with
`SAPPER_PREEXECUTION_VALIDATION_PLAN.md`.

**Role name:** *Sapper* — the combat/tunnel engineer who goes ahead of the main force to **prove and prepare the
ground before anyone commits to it**. The near-side survey crew. Pairs with the **Forward Deployed Engineer
(FDE)** — the far-side / project-side ground-truth crew (defined here as a *query interface*, built thin/later —
see §3 NR-1). *(Renamed from the working title "Nemawashi" at v0.6; historical review rounds in Appendix C predate
the rename — their `FR-NEM-*` ids map 1:1 to today's `FR-SAP-*`.)*

**Locked scope decisions (this doc):**
1. **Near-side role only.** The FDE is a defined collaborating *query interface* (FR-SAP-7), not built here.
2. **Advisory-first** (FR-SAP-8). v1 emits a ranked friction report + escalations and **never blocks**;
   the graduation path to a Hayai hard-block on `REFUTED`-high is specified but gated off.
3. **Deterministic skeleton-compile "pilot bore" is the lead mechanism** (FR-SAP-4). LLM/FDE only for
   assumptions code cannot answer.

**Serves:** `docs/design-princples/HAYAI_DESIGN_PRINCIPLE.md` (don't defer enforcement — pull it to the
earliest stage: the pseudo-code/decomposition layer, before any body is generated).

**Aligns with / depends on:**
- `../repair-pipeline/CONVENTION_AWARE_REPAIR_REQUIREMENTS.md` (FR-CAR-0 Python convention authority; FR-CAR-5
  micro-prime injection) and `../micro-prime/MICRO_PRIME_FIDELITY_REQUIREMENTS.md` (FR-MPF-1). Sapper is the
  **pre-execution sibling** of those *post-generation* levers, and consumes the same authority when it lands.

**Motivating evidence:** `strtd8/docs/P2_RUN_028_POSTMORTEM.md` and the convention-repair doc's RUN-032
baseline — micro-prime emitted Flask-not-FastAPI / `session.query` / `app.models`-not-`app.tables`, and **one
un-prevented micro-prime file cascaded to a boot failure that zeroed three features sharing `app/jobs.py`**.
Every one of those was a *false assumption about the other side of the tunnel*, already latent in the plan,
discovered only at integration/boot time. Sapper is the gate that interrogates those assumptions at
**document cost, not refactoring cost.**

---

## 0. Planning Insights (Self-Reflective Update: v0.1 → v0.2)

> The planning pass (codebase exploration of the reuse targets) tested v0.1's assumptions against the actual
> pre-generation machinery. It revealed **7 corrections**.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| The pilot bore "compiles the skeleton" via `python_toolchain` directly. | `run_project_check()` (`validators/python_toolchain.py:152`) operates over a **project *directory*** (compileall → mypy → pytest), not an in-memory stub. Its power to catch *cross-module* misalignment (the actual tunnel test) comes from **mypy**, which is **off by default** (`STARTD8_PY_TYPECHECK`, line 284) and may be **absent**. `compileall` alone only verifies the stub's own syntax — it cannot detect that a stub calls a function the real codebase doesn't expose. | **FR-SAP-4 reshaped:** the bore must (a) *materialize* signature/import/type-stub skeletons into a **throwaway overlay of the real project** and run `run_project_check(run_pytest=False)`, and (b) adopt the module's **loud-degradation** contract — mypy-absent ⇒ reduced fidelity (syntax+import only), **never a silent `VALIDATED`**. mypy availability becomes a stated soft-dependency + open question (OQ-2). |
| The empty `startd8.preflight_rules` seam hosts the gate and emits the friction report. | The rule system is **per-(file, domain)**: `PreflightRule.evaluate(ctx)` → `RuleContribution{checks, constraints, validators, validator_fns}` (`preflight_rules/_base.py`), aggregated per file by `evaluate_all`. `RuleContribution` carries **enrichment** (prompt constraints + post-gen validator specs), *not* a ranked cross-task finding with severity / who-validates / resolution. | **FR-SAP-6 narrowed + FR-SAP-1/2/3 are new:** reuse the seam for **per-element deterministic checks**, but the **unified whole-decomposition gate**, the `VALIDATED/REFUTED/UNRESOLVED` trichotomy, cost-ranking, and FDE routing are **new orchestration + new models** layered on top, not rules alone. |
| `ProjectKnowledge` can answer the Python framework/ORM/module-source assumptions (it's the FDE's brain). | The producer reads **`.ts/.tsx/.js` + `schema.prisma` + `@/` aliases — TS/Prisma-ONLY** and encodes **no framework/ORM idiom** (per the convention-repair doc's own §0). For a Python target it yields little today. Its **`omissions` list is first-class**, though. | **FR-SAP-7 reframed:** the FDE is a *capability contract* `answer → {VALIDATED \| REFUTED \| OMIT}`; for Python, the backing authority is currently thin, so many assumptions correctly land **`UNRESOLVED`** (escalated) rather than `VALIDATED`. Early value concentrates in the **deterministic pilot bore + cross-contract consistency**; FDE escalation is the explicit "we don't know yet" channel. Aligns Sapper with the in-flight FR-CAR-0 / FR-MPF-1 authority work. |
| `VALIDATED/REFUTED/UNRESOLVED` maps onto the existing `CheckStatus`. | `CheckStatus` is `pass/warn/fail/skip` (`domain_preflight_models.py:36`) — there is **no `UNRESOLVED` equivalent** (an assumption needing a *ruling*). | **FR-SAP-2 is a new trichotomy.** `UNRESOLVED` is the load-bearing novel state — the escalation surface that *pairs with the FDE*. `REFUTED`≈cited contradiction; `VALIDATED`≈evidence-backed; `UNRESOLVED`≈question routed out-of-band. |
| Forward Manifest already cross-checks contracts before generation. | Contracts are **injected** pre-gen (as `[BINDING]` constraints) but **validation runs post-gen only** (`validate_forward_manifest`); there is **no cross-contract or contract-vs-codebase consistency check at plan time**. | **FR-SAP-5 is new:** a plan-time deterministic validator over `InterfaceContract`s — contradictory contracts for one id, and contracts that conflict with an existing codebase symbol — distinct from the post-gen validator, reusing the same data model. |
| Sapper is a new standalone workflow. | `domain-preflight` (`workflows/builtin/domain_preflight_workflow.py`, 825 LOC) is **already** the deterministic, zero-LLM pre-gen stage (`load→scan→classify→check→enrich`) with `PreflightState` checkpointing, `EventBus` `QUALITY_GATE_RESULT` emission, and a `TaskEnrichment` output. | **FR-SAP-9 reuses it as host:** Sapper is a **new phase** consuming the same seed + `AvailableDeps` + manifest, reusing checkpoint/EventBus/loud-degradation conventions — not a parallel pipeline. |
| `element_fillability` is unrelated. | `is_fillable_spec` / `is_empty_fillable_spec` (`element_fillability.py`) is **already a pre-gen "is this buildable" predicate** (catches `class value-model {}`-style non-implementable types). | **FR-SAP-6 composes it:** a non-fillable empty type is a `REFUTED` "this element cannot be built" finding — reuse, don't duplicate. |

**Resolved open questions** (from v0.1):
- **OQ-A (host) → reuse `domain-preflight` as a new phase** (FR-SAP-9). Not a standalone pipeline.
- **OQ-B (verdict model) → new trichotomy** `VALIDATED/REFUTED/UNRESOLVED` (FR-SAP-2); does not fit `CheckStatus`.
- **OQ-C (FDE backing) → ProjectKnowledge + human escalation, with OMIT⇒UNRESOLVED** (FR-SAP-7); thin for Python today, by design.
- **OQ-D (cross-contract) → new plan-time validator** (FR-SAP-5); post-gen `validate_forward_manifest` is the wrong stage.

Remaining open questions are carried to §4.

---

## 0.6 Spike: FR-SAP-4 feasibility (v0.2 → v0.3)

> Before committing to a plan, the lead mechanism was run for real: the RUN-028 `app/jobs.py` (surviving as
> `strtd8/app/jobs.py.backup`) was reduced to a **skeleton** (imports + signatures, bodies → `...`), overlaid
> onto the real `strtd8` `app/` package (ground truth: `tables.py`, `models.py`), and checked with the actual
> toolchain (`mypy`, the engine inside `python_toolchain.run_project_check`). Spike tree: `/tmp/sapper_spike`.

**Result: FR-SAP-4 is feasible and precise on its true axis — but that axis is *existence*, not *convention*.**

| Assumption in the RUN-028 skeleton | Ground truth | Bore verdict | Correct? |
|---|---|---|---|
| `from app.tables import Match` | `Match` **not defined** in schema | `REFUTED` — `Module "app.tables" has no attribute "Match" [attr-defined]` | ✅ true positive |
| `from app.tables import JobDescription` | **exists** (`tables.py:665`) | silent (`VALIDATED`) | ✅ true negative |
| `from app.models import JobDescriptionSchema` | **exists** (`models.py:193`) | silent (`VALIDATED`) | ✅ true negative |
| `from app.models import JobDescription` (wrong module-source) | name is in `tables`, not `models` | `REFUTED` — *"has no attribute 'JobDescription'; maybe 'JobDescriptionSchema'?"* | ✅ true positive (+ suggested the fix) |
| `from flask import Blueprint` (wrong framework) | Flask is a real, importable package | **silent — MISSED** | ❌ blind spot |
| `from sqlalchemy.orm import Session` (wrong ORM idiom) | `sqlalchemy.orm.Session` is real | **silent — MISSED** | ❌ blind spot |

**Three corrections this forces into the requirements:**

1. **The coverage axis is existence vs. conformance, NOT import-line vs. body (corrects the v0.2 §0 prediction).**
   The bore deterministically catches references to things that **don't exist** in ground truth (invented entity
   `Match`; a name imported from the wrong-but-real module when that module lacks the name). It is **structurally
   blind to "exists but is the wrong choice"** — `flask`/`sqlalchemy.orm` are real, so the typechecker has no
   opinion. → **FR-SAP-1 routing reframed** (existence → bore; conformance → authority/FDE), **FR-SAP-4 scope
   narrowed**, **FR-SAP-10 reinforced** (convention is the authority's job, not the bore's — the bore is the
   existence backstop, FR-CAR is the conformance lever).
2. **Diagnostics MUST be scoped to the skeleton-under-test file(s).** With `sqlmodel` absent, mypy emitted **15
   false `table=True` errors in the ground-truth `tables.py`** — noise from a *ground-truth* module, not the
   skeleton. Filtering diagnostics to those whose path is a skeleton file made the signal exact (one diagnostic).
   `run_project_check` collects *all* diagnostics, so **FR-SAP-4 must add file-scoping** (and OQ-7 covers whether
   to instead require the project venv so framework stubs resolve).
3. **The bore's precision depends on ground-truth modules being parseable, not the framework being installed.**
   `mypy` resolved `app.tables` attribute membership correctly **even with `sqlmodel` uninstalled** (class names
   exist at module scope regardless of base-class resolution). So the existence check is cheap and venv-light;
   only conformance/type-accuracy would need the real deps. This *strengthens* the $0-LLM, low-setup thesis.

**Net:** the lead mechanism works and earns its place — it caught the genuine RUN-028 domain miss (`Match`) at
skeleton stage with no false positives — but v0.2 over-claimed its reach. Convention misalignment
(Flask/SQLAlchemy) is **out of scope for the bore by construction** and belongs to FR-SAP-7 (FDE) / the FR-CAR
authority. Carried as OQ-7.

---

## 0.7 Spike 2: conformance route at plan time (v0.3 → v0.4)

> Spike 1 made the conformance route *load-bearing* (the bore is blind to wrong-but-valid imports). Spike 2 tests
> whether the **already-landed** FR-CAR convention detector (`repair/convention.py` `detect_conventions` /
> `PythonConventionAuthority`, from `24893fcc`) can run at **plan time** over a skeleton and cover that blind
> spot. Same RUN-028 fixture; ran the real detector on (A) the full pre-repair file and (B) its body-stripped
> skeleton.

**Result: the route IS plan-time-capable — `detect_conventions(code: str, …)` takes raw source — and on the
skeleton it caught the *headline* RUN-028 failures: `from flask import` (framework) and `from app.models import
JobDescription` (module_source). But it caught only what lives on the *declaration surface*; the body-internal
idioms vanished with the bodies.**

| RUN-028 violation | kind | lives in | full file (A) | skeleton (B) |
|---|---|---|:---:|:---:|
| `from flask import Blueprint` | framework | import | ✅ | **✅ caught** |
| `from app.models import JobDescription` | module_source | import | ✅ | **✅ caught** |
| `@app.route(...)` | framework | decorator | ✅ | ⚠️ only if skeleton keeps decorators |
| `session.query(...).get(...)` / `.query(...)` | orm_idiom | body call | ✅ | ❌ gone (no body) |
| `render_template(...)` | template_idiom | body call | ✅ | ❌ gone (no body) |
| `from sqlalchemy.orm import Session` | — | import | ❌ | ❌ no rule exists for it |

**This sharpens the coverage model into a 2×2** (superseding v0.3's single existence-vs-conformance axis):

|  | **Existence** (symbol absent from ground truth) | **Conformance** (symbol valid but wrong choice) |
|---|---|---|
| **Declaration surface** (import / signature / decorator) — *in the skeleton* | bore / typecheck (FR-SAP-4) — e.g. invented `Match` | convention authority (FR-SAP-10) — e.g. `flask`, `app.models`-source |
| **Body-internal** (call / statement) — *not in the skeleton* | — | **out of scope → post-gen FR-CAR** — e.g. `session.query`, `render_template` |

**Sapper owns the whole declaration-surface column** — *both* existence and conformance — at plan time, $0
LLM. **Body-internal idioms are out of scope by construction** (no bodies to read) and remain FR-CAR's post-gen
job. The two are **complementary, not redundant**: together they cover the full RUN-028 class; neither alone does.

**Two actionable findings:**
1. **Authority gap (concrete, cheap):** `_IDIOM_RULES` has **no import-level rule for `from sqlalchemy.orm import
   Session`** — SQLAlchemy is caught only via the `.query(` *body* call. A skeleton that imports SQLAlchemy
   before bodies exist slips through. **Adding a declaration-surface SQLAlchemy import rule** completes
   conformance coverage for the RUN-028 class at plan time → OQ-6 (now a plan task, not just a question).
2. **Skeleton fidelity = coverage:** whether `@app.route` is caught depends on the manifest-rendered skeleton
   **retaining decorators**. FR-SAP-4 must specify that skeletons preserve the full declaration surface (imports
   + signature + **decorators**) — that surface *is* Sapper's detection field → OQ-8.

**Net:** the load-bearing dependency is real and works; OQ-6 resolves to "yes — reuse `detect_conventions` at
plan time, plus one new import rule." Both empirical hinges are retired — mechanism feasibility (existence *and*
conformance routes) is evidence-backed. **CRP is now the right next step.**

---

## 0.8 Convergent-review corrections (v0.4 → v0.5)

> Five independent CRP rounds (R1 = claude-opus-4-8; R2–R5 = gemini-3.1-pro) appended **32 suggestions** to
> Appendix C, focused (per the focus file) on the *design* layer the spikes couldn't resolve — not feasibility,
> not locked scope. Cross-model convergence was strong: R2–R5 independently **endorsed** R1's schema/security/
> degradation items (R1-F1/F3/F4/F7/F10). Triage (Appendix A/B): **26 merged into the spec, 5 routed to the
> plan, 1 rejected** (R5-F4, presentation detail).

**Material changes:**
- **Schema hardened (R1-F1/F2/F3/F4, R3-F3, R2-F3, R4-F4):** `FrictionFinding` gains a canonical payload —
  verdict **`reason` enum**, `fingerprint`, `suggested_fix` (advisory only), `context_snippet`, `expected`/`found`
  — a fixed `kind → avoidable_cost_stage` table with deterministic tie-break, and a versioned report artifact.
  **The `reason` enum is the keystone**: it lets a consumer separate a genuine FDE escalation from a tooling gap,
  which gating, observability, and EMIT-degradation all now depend on.
- **Safety surfaced (R1-F7, R3-F4, R4-F2, R5-F1/F3):** overlay isolation (no secrets/symlinks, guaranteed
  cleanup) + syntax-invalid / oversized / non-Python skeletons degrade **loudly** instead of crashing preflight.
- **"Advisory" made to mean something (R3-F2 → new FR-SAP-12):** findings are forwarded into the downstream
  generation prompts — an advisory gate nobody reads is worthless.
- **Graduation & observability made measurable (R1-F9; R2-F4/R1-F6/R5-F5 → FR-SAP-12):** per-`kind` gating with
  a precision bar; OTel metrics + `unresolved_rate` + a `bore_degraded` alert.
- **FDE contract typed (R1-F5, R4-F5)** and **edge cases closed** — EMIT absent/stale (R1-F10), greenfield
  (R2-F5), versioned/overloaded contracts (R2-F2), valid overrides (R3-F5).

Deferred to the plan (accepted, not requirements-level): mypy-cache reuse (R2-F1), `--sapper-only` dry-run +
`--min-severity` filter (R4-F1/R5-F2), timeout value-tuning (R4-F3). *(R3-F1 batching was here at v0.5 but the
plan pass promoted it to a correctness requirement — see §0.9 / FR-SAP-4.)*

---

## 0.9 Plan-pass insights (v0.5 → v0.6)

> Writing the companion implementation plan (`SAPPER_PREEXECUTION_VALIDATION_PLAN.md`) — the reflective loop's
> *planning pass* — surfaced **4 corrections**. One reverses a v0.5 triage decision; the rest sharpen boundaries
> the spikes/CRP hadn't forced. (Role also renamed **Nemawashi → Sapper** at this version.)

| v0.5 position | Plan-pass discovery | Impact |
|---|---|---|
| R3-F1 (batch the bore into one `run_project_check`) was triaged to **plan-scope perf** and deferred. | A skeleton for feature A may reference a symbol only feature B's (also un-generated) skeleton defines. The bore must overlay **all sibling skeletons together** + the real tree, or it false-`REFUTED`s valid intra-plan cross-references — so batching is required for **soundness**, not speed. | **Reverses the deferral. FR-SAP-4 now mandates a single overlay of all skeletons + one `run_project_check`** as a correctness requirement; only mypy-cache reuse stays plan-scope perf. |
| FR-SAP-1 listed "emitted skeletons" as a co-equal extraction source alongside the structured manifest. | Two representations exist: the **structured** `ForwardElementSpec`/`InterfaceContract` (what cross-contract, per-element, and the convention-authority lookups read) and the rendered **skeleton text** (only the bore needs text → mypy). | **FR-SAP-1 sharpened:** assumptions extract from the *structured* manifest; skeleton text is **bore-only**. Removes an ambiguity that would have led to brittle text-parsing. |
| FR-SAP-2's `reason` enum used one `authority_absent` value for both "no convention authority" and "missing EMIT input." | These are operationally different: greenfield-no-convention is a *legitimate new project*; missing/stale EMIT is a *broken upstream pipeline*. A consumer (gating, alerting) must distinguish them. | **Split the enum:** `authority_absent` (greenfield, FR-SAP-10) vs **`input_absent`** (broken EMIT, FR-SAP-9). FR-SAP-2/9/10 updated. |
| FR-SAP-9 assumed it could emit through the host's existing output. | `domain-preflight`'s output is **per-task `TaskEnrichment`**; the Sapper report is **cross-task** (ranks across the whole plan). | **FR-SAP-9 adds a cross-task output channel** (the `FrictionReport`) alongside per-task enrichment, rather than overloading `TaskEnrichment`. |

**No open questions changed status** (OQ-6/8 remain plan tasks; OQ-1/2/3/5/7 open). This was a <30% revision —
the v0.5 spec was largely sound; the plan pass tightened four boundaries rather than exposing premature
requirements, which is the expected outcome *after* two spikes and a 5-round CRP.

---

## 1. Problem Statement

The SDK's quality machinery is **bimodal**: rich *design-time capture* (forward contracts injected into prompts)
and rich *post-generation* enforcement (forward-manifest validation, semantic checks, convention-aware repair,
disk-quality scoring, post-mortem/Kaizen). The **earliest gate — interrogating the plan itself before any body
is generated — is thin**: `domain-preflight` checks domain/deps/environment readiness, and `element_fillability`
checks buildability, but nothing reconciles the plan's **assumptions about the existing codebase** against
ground truth. So a plan that assumes Flask (codebase is FastAPI), `app.models` (it's `app.tables`),
`session.query` (it's SQLModel `session.exec`), or a writable field the domain forbids, is generated, integrated,
and **discovered wrong at boot/integration time** — the most expensive, most avoidable failure class.

The tunnel analogy: two crews bore toward each other. The **plan/design crew** holds the `ForwardManifest` /
`ForwardElementSpec` / skeletons ("here's what I intend to build"); the **implementation-reality crew** holds
the real conventions, interfaces, domain rules, runtime ("here's the ground I'm boring into"). When their
assumptions about each other are wrong, the crews miss at the middle — that miss *is* the implementation-time bug.
Sapper runs the **alignment survey** at the pseudo-code stage so the miss is caught at document cost.

| Component | Current State | Gap |
|---|---|---|
| Pre-gen environment readiness | `domain-preflight` (deps, domain, env checks) | Doesn't reconcile **plan assumptions vs codebase ground truth** |
| Buildability predicate | `element_fillability.is_fillable_spec` | Single-element only; no whole-plan friction report |
| Forward contracts | Injected pre-gen; validated **post-gen** | **No plan-time** cross-contract / contract-vs-codebase consistency |
| Skeleton emission | Skeletons emitted before generation (`forward_manifest`) | **Never compiled/typechecked** against the real codebase |
| Ground-truth authority | `ProjectKnowledge` (TS/Prisma) + omissions list | No **queryable FDE role**; Python framework/ORM idiom not encoded |
| Convention enforcement | Post-gen (FR-CAR-*) detect+escalate+repair | **No pre-gen** plan-level convention catch (and micro-prime bypasses injection — RUN-028) |

---

## 2. Requirements

### Model (foundational)

- **FR-SAP-1 — Assumption extraction.** Define an `Assumption`: a claim the plan makes about "the other side of
  the tunnel," extracted deterministically from the **structured** decomposition artifacts (`ForwardManifest` /
  `ForwardElementSpec` / `InterfaceContract`) — **not** by re-parsing rendered skeleton text (plan §6.2). The
  rendered `skeleton_sources` are consumed **only** by the pilot bore (text → mypy, FR-SAP-4); every other
  validator reads the typed manifest. Each `Assumption` carries: `id`, `kind` ∈
  {`interface_signature`, `import_availability`, `module_source`, `framework_idiom`, `orm_idiom`,
  `field_authority`, `domain_rule`, `identity_collision`, `decomposition_integrity`, `reachability`}, the claim
  text, a ref to the source artifact, and a `validator_class` ∈ {`deterministic`, `pilot_bore`, `fde_query`}.
  **Routing is by the existence/conformance axis the spike established (§0.6):** *existence* assumptions
  (`import_availability`, `interface_signature`, `field_authority`, `identity_collision`,
  `decomposition_integrity`, and the existence half of `module_source` — a name absent from its named module) →
  `pilot_bore`/`deterministic`; *conformance* assumptions (`framework_idiom`, `orm_idiom`, and the residual of
  `module_source` where the name exists in **both** the named and the correct module) → `fde_query` (the bore is
  structurally blind to these — the referenced symbol exists, it is merely the wrong choice). **The bore runs
  first; only its residual escalates** — a `module_source` assumption is `REFUTED` deterministically when the
  name is absent from the named module, and routed to `fde_query` only when the name exists in *both* modules
  (R1-F11).
- **FR-SAP-2 — Verdict trichotomy.** `AssumptionVerdict` ∈ {`VALIDATED`, `REFUTED`, `UNRESOLVED`} (a **new**
  model — `CheckStatus` has no `UNRESOLVED`). `VALIDATED` cites the confirming ground-truth; `REFUTED` cites the
  contradiction (`expected` vs `found`); `UNRESOLVED` carries the question + *why code cannot answer it* via a
  **machine-readable `reason` ∈ {`needs_ruling` | `bore_degraded` | `authority_absent` | `input_absent` | `omit`}**
  (R1-F3; `input_absent` split out per plan §6.3) — so a consumer can tell a genuine FDE escalation
  (`needs_ruling`/`omit`) from a *tooling gap*: `bore_degraded` = mypy absent/timeout; `authority_absent` = no
  convention authority for this project (e.g. greenfield, FR-SAP-10); `input_absent` = missing/stale upstream EMIT
  artifacts (FR-SAP-9, a *broken pipeline*, distinct from a legitimately new project). Only the former routes to
  the FDE
  (FR-SAP-7). No assumption is silently dropped. *(This `reason` enum is the keystone the gating (FR-SAP-8),
  observability (FR-SAP-12), and EMIT-degradation (FR-SAP-9) requirements all build on.)*
- **FR-SAP-3 — `FrictionFinding` schema + avoidable-cost ranking.** Each non-`VALIDATED` assumption → a
  `FrictionFinding`. **Canonical payload** (R1-F4 / R3-F3 / R2-F3 / R4-F4): `id`, `kind`, `verdict` + `reason`
  (FR-SAP-2), `severity`, `expected`/`found`, `avoidable_cost_stage`, a stable **`fingerprint`** (deterministic
  hash over `kind`+file+symbol, for cross-run dedup and Kaizen "time-to-resolve"), an optional **`suggested_fix`**
  (when the validator yields one — e.g. mypy's *"maybe 'JobDescriptionSchema'?"* — advisory data only, never
  auto-applied; NR-8), and an optional **`context_snippet`** (offending line ±2). The report artifact
  (`sapper-friction-report.json`) carries a **`schema_version`** and a documented top-level shape with a stated
  consumer-stability policy (R1-F4). **Avoidable-cost mapping (R1-F1)** — every `kind` maps to exactly one stage:

  | stage (cost ↑) | kinds |
  |---|---|
  | `repair` | `import_availability`, `identity_collision` |
  | `integration` | `interface_signature`, `module_source`, `decomposition_integrity`, `reachability` |
  | `boot` | `framework_idiom`, `orm_idiom`, `field_authority` |
  | `cross-feature-cascade` | `domain_rule` (and any finding on a file ≥2 features import — RUN-032 boot-cascade evidence) |

  The report ranks by `avoidable_cost_stage` **descending**, **tie-broken by `severity` then `id`** (deterministic
  ordering); an **unmapped `kind` defaults to `integration`** and never raises (R1-F2). The static table seeds
  OQ-3; Kaizen may re-weight later.

### Mechanism

- **FR-SAP-4 — Deterministic skeleton "pilot bore" (lead mechanism, $0-LLM).** **Reuse the skeletons
  plan-ingestion EMIT already renders** (`plan_ingestion_emitter.py` `_run_mottainai_pre_assembly` →
  `DeterministicFileAssembler.render_specs(forward_manifest)` → `skeleton_sources`); the bore does **not**
  re-render them. **Overlay ALL sibling skeletons in the plan *together*, on top of the real project tree** (plan
  §6.1) — an `import`-or-`signature` reference from feature A's skeleton may resolve only against feature B's
  (also not-yet-generated) skeleton, so the bore must see the whole plan at once or it false-`REFUTED`s valid
  intra-plan references. Then run `python_toolchain.run_project_check(run_pytest=False)` **once** over that
  overlay. Map `mypy`/`compileall`
  diagnostics → `REFUTED` findings **on the existence axis only** (spike-validated, §0.6): a stub that references
  a symbol the real codebase **does not define** fails the typecheck (`attr-defined`/`name-defined`) — the
  cheapest possible alignment test. **Scope diagnostics to the skeleton-under-test file(s)** (`PyDiagnostic.file`
  ∈ skeletons) — the spike showed a ground-truth module with absent framework stubs emits false positives that
  would otherwise pollute the report; file-scoping made the signal exact. **Out of scope by construction:**
  conformance errors (a *valid* import that is the wrong framework/ORM — `flask`, `sqlalchemy.orm`) typecheck
  clean and route to `fde_query` (FR-SAP-1), not the bore. **Loud degradation (load-bearing):** when `mypy` is
  unavailable, the bore runs at syntax+import-resolution fidelity only and the report **states the reduced
  fidelity** — an unverifiable assumption is `UNRESOLVED`, never a silent `VALIDATED`. Mirrors `python_toolchain`'s
  `checked/unavailable` contract. (Spike confirmed existence checks resolve correctly even with the framework
  uninstalled — venv-light; OQ-7 covers when full deps are warranted.)
  **Robustness & isolation (CRP R1/R3/R4/R5):** (a) the overlay MUST be a **unique per-run temp dir that excludes
  secrets/`.env`/VCS dirs, never follows symlinks, and is cleaned up on success *and* failure** (R1-F7, NR-8);
  (b) **filter `skeleton_sources` by language profile** before overlaying — non-Python skeletons are tagged
  `unavailable`, not fed to mypy (R5-F1, NR-7); (c) **normalize relative↔absolute imports** to the overlay's
  package root so a valid `from .models import X` does not yield a false `REFUTED` (R5-F3); (d) a **syntax-invalid**
  skeleton yields a `REFUTED` (`SyntaxError`) finding, never a crashed preflight stage (R4-F2); (e) a
  **skeleton-size bound** rejects runaway hallucinated files as `UNRESOLVED` (`reason=bore_degraded`) and the
  subprocess runs under a **strict timeout** mapping to the same, rather than hanging mypy (R3-F4 / R4-F3 —
  `run_project_check` already accepts `timeout`). **Batching is required for *soundness*, not just speed
  (corrected from v0.5, plan §6.1):** the single overlay-wide `run_project_check` above is what lets intra-plan
  cross-references resolve — R3-F1 is therefore a **correctness** requirement here, not a deferred optimization.
  **Latency:** mypy-cache reuse (R2-F1) remains a plan-level perf mechanism on top of the required batching.
- **FR-SAP-5 — Plan-time cross-contract / contract-vs-codebase consistency.** A new deterministic validator over
  the `ForwardManifest`'s `InterfaceContract`s: detect (a) **contradictory contracts** — two contracts
  prescribing incompatible signatures/schemas for the same `contract_id`; and (b) **contract-vs-codebase
  conflicts** — a prescribed `function_name`/`class_name`/`import_path` that collides with or contradicts an
  existing definition. Reuses `InterfaceContract`; distinct from post-gen `validate_forward_manifest`.
  **Versioned/overloaded contracts (R2-F2):** equality is on the *resolved* contract identity, not the raw
  `contract_id` string — two valid versions or overloads of the same endpoint must not be false-flagged as
  contradictory.
- **FR-SAP-6 — Deterministic per-element checks via the `preflight_rules` seam.** Register Sapper rules on the
  **empty `startd8.preflight_rules` entry point**, *composing* existing predicates: `element_fillability`
  (non-buildable empty type ⇒ `REFUTED` `decomposition_integrity`), **identity/reserved-name collision** (the
  `metadata`-class crash ⇒ `REFUTED` `identity_collision`), and import availability against `AvailableDeps`
  (⇒ `REFUTED` `import_availability`). Per-element findings feed the FR-SAP-3 report. **Valid overrides (R3-F5):**
  the identity/collision check must not `REFUTE` *intentional* shadowing/overrides (a subclass method overriding a
  base, a deliberate built-in shadow) — only true reserved-name / duplicate-definition collisions.
- **FR-SAP-7 — Project ground-truth oracle (defined, not built — NR-1).** Define a capability contract:
  `answer(question) → {VALIDATED(evidence) | REFUTED(evidence) | OMIT}`. v1 backs it with `ProjectKnowledge`
  (including its first-class `omissions` list) + a human-escalation channel; `OMIT`/omission ⇒ `UNRESOLVED`.
  Assumptions that are neither deterministically checkable nor pilot-borable (framework/orm idiom on Python,
  domain rules like "AI never writes `Metric.value`") route here. The near-side role only **consumes** this
  contract. **Typed contract (R1-F5):** `question` and `evidence` are typed payloads (assumption `id` + `kind` +
  claim + ground-truth refs), and **`OMIT` is operationally distinct from a timeout** — both yield `UNRESOLVED`
  but with different `reason` (`omit` vs `bore_degraded`). FDE answers are **cached across runs** keyed by
  question fingerprint, so an unchanged plan does not re-query a possibly human-in-the-loop oracle (R4-F5). OQ-5
  governs the sync-vs-async escalation channel. **Reconciliation with the shipped FDE (v0.7):** the SDK shipped
  a `startd8.fde` package whose authority domain is *SDK mechanism* ("which tier runs, what model by role") —
  **not** project ground truth. Per Tekizai-Tekisho they are the two halves (MECHANISM vs OBSERVED) and
  **compose** rather than subsume: this contract is implemented as a project **ground-truth oracle**
  (`sapper.ground_truth`, `GroundTruthQuery`/`ProjectKnowledgeOracle`), and `sapper.fde_bridge` expresses its
  findings as the FDE's OBSERVED `LabeledClaim`s so the *deployed* FDE fronts the pair. Sapper depends on
  `startd8.fde`, never the reverse (no cycle). RUN-028 is the proof case: the FDE flags the **mechanism** landmine
  (routed to micro-prime → convention injection bypassed); Sapper flags the **ground-truth** refutation (Flask,
  invented `Match`); composed = the whole failure.

### Enforcement & integration

- **FR-SAP-8 — Advisory-first posture.** v1 emits a ranked friction report artifact
  (`sapper-friction-report.json` + `.md`) and `EventBus` event; it **never blocks generation**. The
  graduation path — hard-block on `REFUTED`-high-severity (full Hayai) — is **specified but gated off** behind an
  env flag (mirroring `STARTD8_CONVENTION_GATING`), to be flipped once precision is proven (same trust-earning
  path as the Semantic Compliance Reviewer v1). **Measurable graduation (R1-F9):** the flip requires a stated
  **precision bar over a measurement window with a minimum sample floor**, scored against ground truth recorded in
  the report; and gating is **selectable per `kind` / `validator_class`**, not one global switch — the spike shows
  existence and `framework` findings are high-precision while `UNRESOLVED` is structurally noisy, so the precise
  paths can gate before the noisy ones ever do.
- **FR-SAP-9 — Hosted on the `domain-preflight` stage.** Runs after `classify`/`check`, before generation;
  consumes the same seed + `AvailableDeps` (from preflight) **plus the `ForwardManifest` + `skeleton_sources`
  already produced upstream by plan-ingestion EMIT** — both inputs are available at this stage (OQ-4 resolved),
  so no new pipeline position is required; domain-preflight is extended to load the upstream EMIT artifacts.
  Reuses `PreflightState` checkpointing, `EventBus` emission, and the loud-degradation convention. The deterministic half (FR-SAP-4/5/6) is **zero-LLM**; LLM
  enters only inside the FR-SAP-7 FDE-query path. **Cross-task output channel (plan §6.4):** `domain-preflight`'s
  existing output is **per-task `TaskEnrichment`**, but the Sapper friction report is **cross-task** (it ranks
  findings across the whole plan) — so the host adds a **new cross-task output channel** (the `FrictionReport`
  artifact, FR-SAP-3) alongside the per-task enrichment, rather than overloading `TaskEnrichment`.
  **Absent/stale/low-fidelity EMIT inputs (R1-F10):** if the upstream `ForwardManifest`/`skeleton_sources` are
  missing, **stale** (provenance/timestamp mismatch against the seed), or lack declaration-surface fidelity
  (OQ-8), the gate emits **loud `UNRESOLVED` (`reason=input_absent`)** with a provenance note — **never a silent
  empty `VALIDATED` report** (the exact failure the loud-degradation convention forbids).
- **FR-SAP-10 — Declaration-surface conformance via the FR-CAR authority (spike-validated, §0.7).** Run
  `repair/convention.py` `detect_conventions(skeleton_code, build_python_convention_authority())` over each
  skeleton at plan time. The spike confirmed this catches the **declaration-surface** conformance violations —
  `from flask import` (framework) and `from app.models import <Table>` (module_source), i.e. the *headline*
  RUN-028 failures — as deterministic `REFUTED` findings, $0 LLM. Findings already carry the shared
  `convention_kind`/`expected` vocabulary, so they compose with post-gen FR-CAR. **Scope boundary (load-bearing,
  not a hedge):** body-internal idioms (`session.query`, `render_template`) are absent from a skeleton and remain
  FR-CAR's *post-gen* job — Sapper and FR-CAR are complementary halves of one convention story (the 2×2 in
  §0.7), not competitors. **Extend the authority:** add a declaration-surface `from sqlalchemy.orm import …` rule
  to `_IDIOM_RULES` (OQ-6) so SQLAlchemy is caught at plan time, not only via its `.query(` body call.
  **Greenfield fallback (R2-F5):** a project with no established conventions yields **zero convention findings
  gracefully** (not a crash, not a false `REFUTED`); the authority's absence is itself surfaced as `UNRESOLVED` /
  `authority_absent`, consistent with FR-SAP-9.
- **FR-SAP-11 — RUN-028 structural safety net (the *why* this matters).** Because Sapper validates the
  **plan**, FR-SAP-4/10 catch declaration-surface violations destined for the **micro-prime tier regardless of
  whether adherence injection reached that tier's prompt** — closing the bypass the convention-repair doc
  documents (micro-prime has zero `project_knowledge` refs). The advisory report is the backstop the injection
  path structurally cannot be.
- **FR-SAP-12 — Report delivery & observability (CRP R1/R2/R3/R5).** An advisory report only has value if it
  reaches a reader. (a) **Downstream injection (R3-F2):** the report's `REFUTED`/`UNRESOLVED` findings are
  forwarded into the generation prompts (lead/drafter **and** micro-prime) so the generator is warned and does
  not blindly reproduce the misalignment — that forwarding *is* what "advisory" means here (it warns; FR-SAP-8/NR-2
  keep it from blocking). (b) **Observability (R2-F4 / R1-F6 / R5-F5):** emit OTel metrics
  `sapper.findings.count{severity,stage,verdict,reason}` and an **`unresolved_rate`** (so the "FDE becomes a
  dumping ground" failure is visible, not silent), plus an **alert when `reason=bore_degraded` spikes** (silent
  toolchain breakage — e.g. mypy uninstalled in CI).

---

## 3. Non-Requirements

- **NR-1 — Does NOT build the FDE agent.** Interface/contract only (FR-SAP-7). The project-side ground-truth
  agent is a separate, later effort.
- **NR-2 — Does NOT block generation in v1.** Advisory only (FR-SAP-8). The block path is specified-but-gated.
- **NR-3 — Does NOT generate bodies or call the LLM for the deterministic half.** Not a generation step; the
  pilot bore emits *stubs*, not implementations.
- **NR-4 — Does NOT replace post-generation validation.** `forward_manifest_validator`, semantic checks, and
  convention-aware repair remain; Sapper is the *earliest* gate, not the only one.
- **NR-5 — Does NOT build the Python convention authority.** Depends on / aligns with FR-CAR-0 / FR-MPF-1. Where
  no authority exists yet, framework/orm-idiom assumptions route to `UNRESOLVED` (escalate, don't invent a verdict).
- **NR-6 — Not Service-Assistant work.** SA is *post-run* triage of completed runs; Sapper is *pre-run* plan
  validation. Distinct lifecycle position — which is exactly why it warrants a separate role.
- **NR-7 — v1 is Python-first.** The pilot bore rides `python_toolchain`. Polyglot bores (Go/Java/C#/Node
  toolchains) are deferred; for non-Python targets v1 runs FR-SAP-5/6 only and labels the bore `unavailable`.
  **Mixed-language plans** are handled by filtering `skeleton_sources` by language (FR-SAP-4) — Python skeletons
  are bored, non-Python tagged `unavailable`, neither crashes the other (R5-F1).
- **NR-8 — Does NOT auto-apply fixes.** A `FrictionFinding.suggested_fix` is **advisory data passthrough** (e.g.
  mypy's near-match hint), surfaced for a human or the downstream generator/FR-CAR to act on. Sapper never
  mutates the plan or code — applying a fix is FR-CAR's *post-gen* job (R2-F3 scope guard; preserves the NR-3 /
  advisory-first boundary).

---

## 4. Open Questions (remaining after the planning pass)

> **Status legend (R1-F12):** OQ-4 **resolved**; OQ-6 & OQ-8 **resolved → plan tasks**; OQ-1/2/3/5/7 **open**.
> Each OQ-n appears once with exactly one status.

- **OQ-1 — Skeleton overlay strategy (now incl. the isolation axis, R1-F8).** Full throwaway project copy vs.
  **MYPYPATH/overlay without a full copy** vs. synthetic stub package — evaluated on **three** axes: correctness,
  cost, **and isolation/secret-exposure** (a full copy drags `.env`/secrets into temp; an MYPYPATH overlay may
  avoid the copy entirely). *Lean:* measure copy-cost vs. secret-exposure vs. concurrency on the RUN-028 fixture;
  prefer the copy-free overlay if correctness holds. Pairs with the FR-SAP-4 isolation clause / NR-8.
- **OQ-2 — mypy-absent fidelity floor.** Is `compileall` + import-resolution alone worth running, or should the
  bore mark itself `unavailable` and route everything to `UNRESOLVED`? *Lean:* run it, label reduced fidelity
  (some import/syntax misalignment is still caught cheaply).
- **OQ-3 — Avoidable-cost calibration.** Static heuristic (`kind → stage`) vs. learned from Kaizen history.
  *Lean:* static seed table from the RUN-028/032 cascade, refined via Kaizen feedback later.
- **OQ-4 — Input availability / sequencing → RESOLVED.** Planning-pass code check found the `ForwardManifest`
  **and rendered skeletons are produced *upstream* during plan-ingestion EMIT** (`plan_ingestion_emitter.py`
  `_extract_forward_manifest` + `_run_mottainai_pre_assembly` → `skeleton_sources`), which runs **before**
  `domain-preflight` (`scripts/run_artisan_workflow.py:858`). Both inputs (seed/deps *and* manifest/skeletons)
  are therefore available at the host stage — **FR-SAP-9 holds**: extend `domain-preflight` to load the EMIT
  artifacts; no new pipeline slot needed. Bonus: FR-SAP-4 reuses EMIT's skeletons rather than re-rendering.
- **OQ-5 — FDE escalation mechanics for v1.** Synchronous human prompt vs. async escalation artifact resolved
  out-of-band. *Lean:* async artifact + `EventBus`, consistent with advisory-first.
- **OQ-6 — Shared convention authority → RESOLVED + scoped to a plan task (§0.7).** Confirmed: Sapper reuses
  `repair/convention.py` `detect_conventions` at plan time over skeletons — it caught Flask + module_source on
  the RUN-028 skeleton. **Remaining work (now a plan task, not an open question):** add one declaration-surface
  `from sqlalchemy.orm import …` rule to `_IDIOM_RULES` so SQLAlchemy import is caught at plan time (today only
  its `.query(` body is). No architectural unknown remains here.
- **OQ-7 — Bore mypy config / deps (from the spike).** Two sub-decisions surfaced by §0.6: (a) **diagnostic
  scoping** — filter to skeleton-file diagnostics (chosen) vs. require the project venv so framework stubs resolve
  and the ground-truth-module noise disappears at the source; and (b) **`--ignore-missing-imports`** — keep it
  (existence checks against intra-project modules still fire; only genuinely-missing third-party is silenced) vs.
  provision deps for higher-fidelity type accuracy. *Lean:* scope-by-file + `--ignore-missing-imports` for the
  v1 existence bore (venv-light, $0); revisit deps only if FR-SAP-5 needs signature-level type matching.
- **OQ-8 — Skeleton declaration-surface fidelity (from §0.7) → plan task.** Sapper's entire detection field is
  the declaration surface the manifest-rendered skeleton emits. Confirm `DeterministicFileAssembler.render_specs`
  preserves **imports + signatures + decorators** (the `@app.route` catch depends on decorators surviving into
  the skeleton). If decorators are dropped, FR-SAP-10 loses decorator-level framework detection. *Lean:* require
  full declaration-surface fidelity in the skeleton contract; verify against `ForwardElementSpec.decorators`.

---

*v0.6 — Post-plan-pass. The full reflective arc: v0.2 corrected 7 assumptions against code; v0.3/v0.4
spike-validated both mechanism routes (§0.6/§0.7); v0.5 triaged 5 CRP rounds / 32 suggestions (§0.8); v0.6 drafted
the companion plan and folded back 4 planning discoveries (§0.9) — one reversing a triage call (bore batching is
correctness, not perf). **12 FRs, 8 NRs, 8 OQs**; `UnresolvedReason` now 5-valued (`input_absent` split out).
Feasibility + design + build-sequencing all closed. **Next: Phase 0 implementation** (`sapper/models.py` —
schema/enum/cost-table, the foundation every other phase depends on) per plan §2. A second CRP is not warranted —
v0.6's deltas are narrow boundary-tightenings on an already-reviewed spec. Role named **Sapper** (was "Nemawashi").*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

**Triage:** R1 (claude-opus-4-8) + R2–R5 (gemini-3.1-pro), 32 suggestions → **26 merged into the spec** (below),
**5 accepted as plan-scope**, **1 rejected** (Appendix B). Cross-model convergence (R2–R5 endorsements of R1)
noted where it raised confidence. Orchestrator: claude-opus-4-8, 2026-06-04.

_Merged into requirements prose:_

| ID | Suggestion (short) | Merged into | Date |
|----|------------|--------|------|
| R1-F1 | `kind → avoidable_cost_stage` mapping table | FR-SAP-3 (table) | 2026-06-04 |
| R1-F2 | ranking tie-break + unmapped-kind default | FR-SAP-3 | 2026-06-04 |
| R1-F3 | `UNRESOLVED` `reason` enum (keystone; endorsed R2/R5) | FR-SAP-2 | 2026-06-04 |
| R1-F4 | report `schema_version` + artifact contract (endorsed R2) | FR-SAP-3 | 2026-06-04 |
| R1-F5 | typed FDE `question`/`evidence` + OMIT-vs-timeout | FR-SAP-7 | 2026-06-04 |
| R1-F6 | `unresolved_rate` observability | FR-SAP-12 | 2026-06-04 |
| R1-F7 | overlay isolation: secrets/symlink/cleanup (endorsed R2) | FR-SAP-4 + NR-8 | 2026-06-04 |
| R1-F8 | OQ-1 rescope: isolation axis + MYPYPATH alt | OQ-1 | 2026-06-04 |
| R1-F9 | measurable gating bar + per-`kind` gating | FR-SAP-8 | 2026-06-04 |
| R1-F10 | EMIT absent/stale → loud `UNRESOLVED` (endorsed R2) | FR-SAP-9 | 2026-06-04 |
| R1-F11 | `module_source` bore-first routing | FR-SAP-1 | 2026-06-04 |
| R1-F12 | reconcile OQ inventory (single status each) | §4 status legend | 2026-06-04 |
| R2-F2 | versioned/overloaded contracts not false-flagged | FR-SAP-5 | 2026-06-04 |
| R2-F3 | `suggested_fix` field (scope-guarded: advisory only) | FR-SAP-3 + NR-8 | 2026-06-04 |
| R2-F4 | OTel `sapper.findings.count{…}` metrics | FR-SAP-12 | 2026-06-04 |
| R2-F5 | greenfield / no-convention graceful fallback | FR-SAP-10 | 2026-06-04 |
| R3-F2 | inject report into downstream gen prompts (endorsed R4) | FR-SAP-12 | 2026-06-04 |
| R3-F3 | `fingerprint` for cross-run dedup / Kaizen | FR-SAP-3 | 2026-06-04 |
| R3-F4 | skeleton size bound → `UNRESOLVED` (DOS guard; endorsed R4) | FR-SAP-4 | 2026-06-04 |
| R3-F5 | `identity_collision` allows valid overrides/shadowing | FR-SAP-6 | 2026-06-04 |
| R4-F2 | syntax-invalid skeleton → `REFUTED`, not crash (endorsed R5) | FR-SAP-4 | 2026-06-04 |
| R4-F4 | `context_snippet` in finding payload (endorsed R5) | FR-SAP-3 | 2026-06-04 |
| R4-F5 | cache FDE answers across runs | FR-SAP-7 | 2026-06-04 |
| R5-F1 | polyglot: filter `skeleton_sources` by language | FR-SAP-4 + NR-7 | 2026-06-04 |
| R5-F3 | normalize relative↔absolute imports (false-`REFUTED` guard) | FR-SAP-4 | 2026-06-04 |
| R5-F5 | alert on `reason=bore_degraded` spike | FR-SAP-12 | 2026-06-04 |

_Accepted but scoped to the implementation plan (not requirements-level — recorded for `…_PLAN.md`):_

| ID | Suggestion (short) | Disposition | Date |
|----|------------|--------|------|
| R2-F1 | preserve `.mypy_cache` across runs (latency) | plan; noted in FR-SAP-4 latency clause | 2026-06-04 |
| R3-F1 | batch all skeletons into one `run_project_check` | plan; noted in FR-SAP-4 latency clause | 2026-06-04 |
| R4-F1 | `--sapper-only` CLI dry-run mode | plan (CLI/UX) | 2026-06-04 |
| R4-F3 | strict subprocess timeout | partly merged (timeout→`UNRESOLVED`, FR-SAP-4); value-tuning → plan; `run_project_check` already takes `timeout` | 2026-06-04 |
| R5-F2 | `--sapper-min-severity` CLI filter | plan (CLI/UX) | 2026-06-04 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| R5-F4 | Render a side-by-side/unified **diff** in the human-readable `.md` report for `REFUTED` findings. | R5 (gemini-3.1-pro) | **Presentation detail, not a requirement.** The `expected`/`found` fields in the FR-SAP-3 schema already carry the data; how the `.md` renders it (diff vs. table vs. inline) is an implementation/UX choice for the plan, not a spec-level requirement. Not re-propose at requirements level; may resurface as a plan/CLI task. | 2026-06-04 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-06-04

- **Reviewer**: claude-opus-4-8 (claude-opus-4-8[1m])
- **Date**: 2026-06-04 19:30:00 UTC
- **Scope**: Single-document requirements review. Focus-file asks (friction-report schema, FDE contract, overlay ops/security, advisory→gating graduation, host-stage integration), then standard F-prefix suggestions. Feasibility/locked-scope explicitly out per focus file.

##### Focus-file asks (answered first; orchestrator triages)

**Ask 1 — Friction-report schema (FR-SAP-1/2/3): complete and unambiguous?**
- **Summary answer:** Partial — the trichotomy and routing are well-specified, but the avoidable-cost ranking, the artifact contract, and the `UNRESOLVED`-vs-degraded distinction are under-specified.
- **Rationale:** FR-SAP-3 names the cost ladder (`repair < integration < boot < cross-feature-cascade`) and OQ-3 commits to a static `kind → stage` seed, but no requirement defines *which* `kind` maps to *which* stage, the tie-break rule, or the unknown-stage default. FR-SAP-2 says `UNRESOLVED` "carries the question + why code cannot answer it," but FR-SAP-4's loud-degradation also produces `UNRESOLVED` ("an unverifiable assumption is `UNRESOLVED`") — the schema does not let a consumer tell "genuinely needs a ruling" from "validator was degraded/absent." FR-SAP-8 names `sapper-friction-report.json` but no requirement fixes its schema version or stability contract.
- **Assumptions / conditions:** The report is intended to be consumed by other tooling (Kaizen, gating graduation, dashboards), not just read by a human — which the gating path (FR-SAP-8) and Kaizen calibration (OQ-3) both imply.
- **Suggested improvements:** See R1-F1 (cost-stage mapping table), R1-F2 (tie-break + unknown-stage), R1-F3 (`UNRESOLVED` reason enum distinguishing degraded from needs-ruling), R1-F4 (artifact schema version + stability contract).

**Ask 2 — FDE query contract (FR-SAP-7): buildable consumer?**
- **Summary answer:** No — the contract specifies the *verdict* shape but not the *question/evidence payload* shape, nor the async/latency semantics the focus file flags.
- **Rationale:** FR-SAP-7 gives `answer(question) → {VALIDATED(evidence) | REFUTED(evidence) | OMIT}` but never types `question`, `evidence`, or how `OMIT` differs operationally from a timeout. OQ-5 defers escalation mechanics (sync vs async) with a *lean* toward async artifact, but a consumer cannot be built against a "lean." The "dumping ground" risk (every hard assumption → `UNRESOLVED`) is real and unmeasured.
- **Assumptions / conditions:** v1 backs FDE with `ProjectKnowledge` + human escalation (FR-SAP-7); the near-side gate is synchronous and $0 (focus file).
- **Suggested improvements:** See R1-F5 (type the question/evidence payload + OMIT-vs-timeout), R1-F6 (UNRESOLVED-rate ceiling / observability so the dumping-ground failure is visible).

**Ask 3 — Overlay ops/security (FR-SAP-4): risks surfaced?**
- **Summary answer:** No — FR-SAP-4 and OQ-1/OQ-7 treat the throwaway copy as a cost/correctness tradeoff only; the operational and security risks (secrets in the copy, subprocess over project code, cleanup/leakage, concurrency, symlink escape) are unstated.
- **Rationale:** FR-SAP-4 says "Overlay those skeletons into a throwaway copy of the real project, then run `python_toolchain.run_project_check`." mypy/compileall import and execute nothing at runtime, but `.env`/secrets are copied into a temp dir that the requirements never scope for cleanup, permissions, or exclusion; concurrent runs and symlink-following `copytree` are unaddressed. OQ-1 frames overlay strategy purely as "correctness/cost," omitting the isolation/security axis the focus file raises.
- **Assumptions / conditions:** Runs may execute on shared/CI hosts and on large real repos (RUN-028 fixture is a real app).
- **Suggested improvements:** See R1-F7 (add an NR or FR-SAP-4 clause: exclude `.env`/secrets/VCS, guaranteed cleanup, unique per-run temp dir, no symlink-follow) and R1-F8 (re-scope OQ-1 to include the isolation/security axis, evaluate MYPYPATH-overlay as a copy-free alternative).

**Ask 4 — Advisory→gating graduation (FR-SAP-8): precision bar defined/measurable?**
- **Summary answer:** No — the graduation is gated behind an env flag but no precision threshold, evidence source, or false-positive guard is specified.
- **Rationale:** FR-SAP-8 says the block path flips "once precision is proven (same trust-earning path as the Semantic Compliance Reviewer v1)" but states no target precision, no measurement window, no sample-size floor, and no per-`kind` carve-out — yet the spike already shows `module_source` (existence-half) and `framework` produce defensible true positives while `UNRESOLVED` is structurally noisy. A single global flag risks gating the noisy path with the precise one.
- **Assumptions / conditions:** The friction report must record verdict outcomes vs. ground truth for precision to be measurable at all (depends on Ask 1 schema).
- **Suggested improvements:** See R1-F9 (define a measurable precision bar + window + sample floor, and make gating per-`kind`/per-`validator_class` rather than a single global flag).

**Ask 5 — Host-stage integration (FR-SAP-9): coupling sound + EMIT-absent/stale handling?**
- **Summary answer:** Partial — OQ-4 soundly resolves *availability/sequencing*, but the absent/stale/low-fidelity EMIT failure modes and checkpoint/EventBus failure semantics are not specified.
- **Rationale:** FR-SAP-9 assumes the upstream EMIT `ForwardManifest` + `skeleton_sources` are present, but states no behavior when they are missing, stale, or (per OQ-8) lack decorator fidelity that FR-SAP-10 depends on. The loud-degradation convention is cited for mypy-absence (FR-SAP-4) but not applied to absent/stale EMIT inputs — risking a silent empty-report `VALIDATED`, the exact failure the Context-Correctness principle forbids.
- **Assumptions / conditions:** EMIT runs before domain-preflight (OQ-4, `run_artisan_workflow.py:858`); EMIT artifacts can be skipped/fail upstream.
- **Suggested improvements:** See R1-F10 (specify absent/stale/low-fidelity EMIT degradation as loud `UNRESOLVED`-with-reason, with a staleness/provenance check), endorsing OQ-8's decorator-fidelity verification as the gate.

##### Suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | Add an explicit `kind → avoidable-cost-stage` mapping table to FR-SAP-3 (all 10 `kind` values from FR-SAP-1 mapped to one of `repair`/`integration`/`boot`/`cross-feature-cascade`). | FR-SAP-3 defines the cost ladder and OQ-3 commits to a "static seed table," but no requirement states the actual per-`kind` assignment, so two implementers will rank the same report differently. | FR-SAP-3, after "seeded from the RUN-028/032 cascade evidence" | Unit test: every `kind` enum member has exactly one stage; report ordering is deterministic across runs on a fixed input. |
| R1-F2 | Data | medium | Specify the tie-break rule and the unknown/unmapped-stage default for the avoidable-cost ranking. | FR-SAP-3 ranks "by avoidable cost descending" but is silent on equal-cost ties (stable secondary key?) and on a `kind` with no mapped stage — non-determinism and a crash/None risk. | FR-SAP-3 | Test: two findings at the same stage produce a stable, documented order (e.g. by `severity` then `id`); an unmapped `kind` lands at a defined default (e.g. `integration`) not an exception. |
| R1-F3 | Interfaces | high | Make `UNRESOLVED` carry a machine-readable `reason` enum distinguishing "needs FDE ruling" from "validator degraded/absent" (e.g. `needs_ruling` \| `bore_degraded` \| `authority_absent` \| `omit`). | FR-SAP-2 and FR-SAP-4 both emit `UNRESOLVED` for semantically different causes; a consumer (gating, Kaizen, FDE router) cannot currently tell a real question from a tooling gap. Focus-file Ask 1 explicitly calls this out. | FR-SAP-2, in the `UNRESOLVED` clause | Test: a mypy-absent run tags its `UNRESOLVED` findings `bore_degraded`; a framework-idiom-on-Python assumption tags `needs_ruling`/`authority_absent`. |
| R1-F4 | Interfaces | medium | Define the `sapper-friction-report.json` artifact contract: a `schema_version` field, a stated consumer-stability policy, and a minimal documented top-level shape. | FR-SAP-8 names the artifact and FR-SAP-9/OQ-3 imply downstream consumers (Kaizen, gating), but no requirement fixes its schema or versioning — guaranteeing silent breakage when the model evolves. | New clause under FR-SAP-8 or a "Report Artifact" subsection in §2 | Test: report validates against a versioned JSON schema; a schema change without a `schema_version` bump fails CI. |
| R1-F5 | Interfaces | high | Type the FDE `question` and `evidence` payloads and define `OMIT` vs. timeout semantics in FR-SAP-7. | The consumer (near-side router) cannot be built against `answer(question)` without the `question`/`evidence` shapes; FR-SAP-7 and OQ-5 leave both as prose/lean. Focus-file Ask 2. | FR-SAP-7 | Contract test: a fixture `question` round-trips through the typed interface; `OMIT` and a simulated timeout both map to `UNRESOLVED` with distinct `reason` (ties to R1-F3). |
| R1-F6 | Validation | medium | Add an observable `UNRESOLVED`-rate ceiling (or at least a required metric) so the "FDE becomes the dumping ground" failure is detectable, not silent. | Focus-file Ask 2 names this risk; on Python today FR-SAP-7/NR-5 route *most* conformance assumptions to `UNRESOLVED` by design, so an unbounded rate would mean Sapper quietly validates nothing. | New clause in FR-SAP-7 or §4 OQ | Test: report emits `unresolved_rate`; a synthetic plan where all assumptions are conformance-class surfaces a high rate in the report/EventBus. |
| R1-F7 | Security | high | Add an explicit safety clause to FR-SAP-4 (or a new NR): the throwaway overlay MUST exclude secrets/`.env`/VCS dirs, use a unique per-run temp dir, never follow symlinks on copy, and guarantee cleanup on success and failure. | FR-SAP-4 copies "the real project" into a temp dir and runs a subprocess over it; secrets-in-temp, leaked temp dirs, concurrent-run collisions, and symlink escape are unaddressed. Focus-file Ask 3. | FR-SAP-4, new "isolation" clause, and/or NR-8 | Test: overlay of a fixture repo containing `.env` and a symlink produces a temp dir with neither; temp dir is removed even when `run_project_check` raises. |
| R1-F8 | Ops | medium | Re-scope OQ-1 to include the isolation/security axis (not just correctness/cost) and add MYPYPATH/overlay-without-full-copy as an evaluated alternative. | OQ-1 frames overlay strategy as correctness/cost only; the focus file asks whether "throwaway copy" is even the right isolation primitive vs. an overlay/MYPYPATH approach. | OQ-1 | Decision record: OQ-1 resolution explicitly compares copy-cost, secret-exposure, and concurrency for each option on the RUN-028 fixture. |
| R1-F9 | Validation | high | Define a measurable graduation bar for FR-SAP-8 gating: target precision, measurement window, minimum sample size, and make gating selectable per-`kind`/`validator_class` rather than one global env flag. | FR-SAP-8 flips on "once precision is proven" with no metric; the spike shows existence/`framework` findings are high-precision while `UNRESOLVED` is structurally noisy, so a single global flag would gate the noisy path with the precise one. Focus-file Ask 4. | FR-SAP-8 | Test: gating config rejects flip when measured precision < bar or N < floor; a per-`kind` flag blocks only the configured kinds. |
| R1-F10 | Risks | high | Specify FR-SAP-9 behavior when the upstream EMIT `ForwardManifest`/`skeleton_sources` are absent, stale, or low-fidelity (missing decorators): emit loud `UNRESOLVED` (reason `authority_absent`/`bore_degraded`) with a provenance/staleness check — never a silent empty `VALIDATED`. | FR-SAP-9 assumes EMIT inputs are present; absent/stale inputs would silently produce an all-clear report, violating the loud-degradation convention FR-SAP-4 already adopts and the doc's stated Context-Correctness alignment. Focus-file Ask 5; couples with OQ-8. | FR-SAP-9 | Test: domain-preflight run with EMIT artifacts removed/stale-timestamped yields a report whose findings are `UNRESOLVED` with an input-provenance reason, not an empty pass. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F11 | Architecture | medium | Resolve the FR-SAP-1 routing ambiguity for `module_source`: the *same* `kind` is split across `pilot_bore` (existence-half) and `fde_query` (conformance-half), but no requirement says *who decides the split or when*. State that the bore runs first and only the residual (name exists in both modules) escalates. | FR-SAP-1 describes the split conceptually but leaves the decision procedure implicit; an implementer could route all `module_source` to one validator. The spike (§0.6) shows the bore can only classify after it runs (REFUTED vs silent). | FR-SAP-1, the `module_source` clause | Test: a `module_source` assumption whose name is absent everywhere → bore REFUTED; one whose name exists in both modules → escalated `fde_query`. |
| R1-F12 | Validation | low | OQ-6 and OQ-8 are labeled "now plan tasks, not open questions" but remain in the §4 Open Questions list, and the §0 numbering skips OQ-2→OQ-3 in the resolved block while §4 lists OQ-1..OQ-8 with no OQ stably cross-referenced — reconcile the OQ inventory so each ID appears once with a single status. | The closing summary claims "6 OQs (OQ-4/6 resolved; OQ-6/8 now plan tasks)" — OQ-6 is listed as both resolved and a plan task, and the count (6) does not match the visible OQ-1..OQ-8 span. An implementer cannot tell which OQs still block. | §4 and the closing v0.4 summary paragraph | Manual check: each OQ-n appears once with exactly one of {open, resolved, plan-task}; the stated count matches the list. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — Appendix C had no prior rounds at R1.

**Disagreements** (untriaged prior items this reviewer would reject): none — no prior rounds exist.


#### Review Round R2

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-04 19:45:00 UTC
- **Scope**: Gap-hunting, robustness, low-hanging fruit, and operational enhancements.

**Executive Summary:**
- Identified a major performance risk in the throwaway dir strategy (cold mypy starts).
- Proposed structured `suggested_fix` for auto-repairability.
- Added OTel metrics for immediate observability value.
- Handled edge cases for greenfield projects and overloaded contracts.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Ops | high | Preserve `mypy` cache (`.mypy_cache`) across pilot bore runs instead of completely cold throwaway dirs. | FR-SAP-4 implies a cold start for `mypy` every time. Cold mypy on large repos is slow (10-30s), destroying the fast-feedback value of pre-execution checks. Warm mypy takes <1s. | FR-SAP-4 | Measure bore execution time on a large repo with and without cache preservation; verify <2s target. |
| R2-F2 | Risks | medium | Specify how FR-SAP-5 (cross-contract consistency) handles versioned or overloaded contracts. | FR-SAP-5 detects "contradictory contracts for the same `contract_id`". If a system uses API versioning or valid overloads, simplistic ID matching will false-flag. | FR-SAP-5 | Test validator with two valid versions of an endpoint contract; verify it does not false-flag. |
| R2-F3 | Interfaces | medium | Enhance `FrictionFinding` to include a structured `suggested_fix` field when the deterministic bore catches a near-miss. | The spike notes mypy caught "maybe 'JobDescriptionSchema'?". Structuring this into a `suggested_fix` field allows the orchestrator/LLM to auto-apply the fix to the plan without human parsing. Massive quick win for auto-repair. | FR-SAP-3 | Verify that the JSON schema for the report includes `suggested_fix` and that typo-catches populate it. |
| R2-F4 | Ops | low | Emit the friction report summary as OTel metrics (e.g., `sapper.findings.count{severity, stage, verdict}`). | FR-SAP-8 emits an EventBus event. Emitting OTel metrics leverages existing platform infrastructure for instant Grafana visibility into "how much friction are we catching?" at near-zero cost. | FR-SAP-8 | Verify OTel metrics are emitted and visible in the local observability stack during a run. |
| R2-F5 | Architecture | medium | Define fallback behavior for FR-SAP-10 (Convention Authority) when the project is greenfield with no established conventions. | If a project is brand new, there are no conventions. FR-SAP-10 doesn't state if this yields an empty report, `UNRESOLVED`, or fails. A "greenfield bypass" prevents crashes on empty projects. | FR-SAP-10 | Run pipeline on an empty directory and verify it gracefully yields 0 convention findings. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R1-F1: Absolutely needed to make avoidable-cost deterministic.
- R1-F3: Essential for routing; tooling failures shouldn't look like FDE escalations.
- R1-F4: Schema stability is critical for downstream consumers.
- R1-F7: Copying `.env` into a temp dir is a major security risk; explicit exclusion is mandatory.
- R1-F10: Failsafe for missing upstream artifacts aligns perfectly with Context-Correctness.


#### Review Round R3

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-04 19:50:00 UTC
- **Scope**: Gap-hunting, robustness, low-hanging fruit, and operational enhancements.

**Executive Summary:**
- Proposed batching skeleton typechecks to heavily optimize pipeline latency.
- Identified a missing link in the advisory flow: ensuring findings reach the downstream generator.
- Added deterministic fingerprinting for friction findings to support cross-run tracking.
- Added runaway-skeleton size limits to prevent preflight DOS.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Ops | medium | Batch skeleton typechecking into a single `run_project_check` invocation rather than sequential runs. | `run_project_check` overhead is high. Running it once over a directory containing *all* skeletons is significantly faster than invoking the subprocess per skeleton, a classic low-hanging fruit for pipeline latency. | FR-SAP-4 | Measure execution time of 10 skeletons batched vs sequential; verify batched is significantly faster. |
| R3-F2 | Interfaces | high | Explicitly define how the `sapper-friction-report.json` is injected into the downstream generation prompts. | FR-SAP-8 says the gate is advisory and doesn't block. But if the friction report isn't forwarded to the micro-prime/generator agent, the generator will blindly reproduce the error. Advisory must mean "warn the implementer." | FR-SAP-8 | End-to-end test: verify the text of a `REFUTED` finding appears in the rendered prompt passed to the generation LLM. |
| R3-F3 | Data | medium | Add a deterministic fingerprint/hash to `FrictionFinding` to enable cross-run deduplication. | In iterative development, the same `REFUTED` finding will fire repeatedly until fixed. Without a stable fingerprint, Kaizen and dashboards cannot track "time to resolve" or deduplicate noise. | FR-SAP-3 | Generate the report twice on the same broken plan; verify the findings have identical fingerprints across runs. |
| R3-F4 | Risks | medium | Add a size/complexity bounds check (e.g., max lines or file size) on skeletons before overlaying. | A hallucinated LLM plan could produce a massive skeleton file. Running `mypy` on runaway generated code risks OOM or hanging the `domain-preflight` stage. A simple guardrail prevents DOS. | FR-SAP-4 | Feed a synthetic 50MB skeleton to the bore; verify it rejects it instantly with `UNRESOLVED` (size limit exceeded) rather than hanging mypy. |
| R3-F5 | Architecture | medium | Clarify how `Identity Collision` (FR-SAP-6) handles valid overrides/shadowing in Python. | FR-SAP-6 checks for reserved-name collisions. In Python, shadowing built-ins or overriding class attributes is sometimes valid and intentional. A naive collision check might falsely REFUTE valid designs. | FR-SAP-6 | Test a skeleton that intentionally overrides a base class method; verify it does not trigger a false `identity_collision`. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R2-F1: Preserving mypy cache is critical for latency.
- R2-F3: Structured `suggested_fix` enables auto-repair without LLM reasoning.
- R2-F4: OTel metrics provide immediate dashboard value.

#### Review Round R4

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-04 19:55:00 UTC
- **Scope**: Robustness, value to end-user, quick wins, and operational enhancements.

**Executive Summary:**
- Identified the need for a CLI dry-run mode to give developers rapid feedback.
- Added graceful degradation for syntactically invalid skeletons to prevent pipeline crashes.
- Suggested subprocess timeouts and FDE caching for stability and performance.
- Improved the finding payload with context snippets for better readability.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Ops | medium | Add a CLI flag (e.g., `--sapper-only`) to run just the pre-execution alignment survey and exit. | Developers need a fast feedback loop when tweaking plans. Running the whole pipeline to see if the plan is aligned takes too long. A dry-run mode provides immediate value to the end-user. | FR-SAP-9 | Run the CLI with the flag; verify it emits the friction report and exits 0 before generation starts. |
| R4-F2 | Architecture | high | Specify how the pilot bore handles syntax-invalid skeletons (e.g. mismatched parentheses in signatures). | If the LLM hallucinates invalid Python syntax in the skeleton, `mypy` or `compileall` will crash entirely. The bore must catch `SyntaxError` and emit a `REFUTED` finding rather than crashing the preflight stage. | FR-SAP-4 | Feed a syntactically invalid skeleton; verify it emits a `REFUTED` finding and the pipeline continues gracefully. |
| R4-F3 | Risks | medium | Add a strict timeout to the `python_toolchain.run_project_check` subprocess invocation. | Subprocesses can hang (e.g., infinite loops in typechecking edge cases). A strict timeout ensures the `domain-preflight` stage remains bounded and doesn't block CI or local dev indefinitely. | FR-SAP-4 | Mock the `run_project_check` to sleep for 60s; verify the bore times out and emits an `UNRESOLVED` finding. |
| R4-F4 | Data | low | Include a short `context_snippet` (e.g. 2-3 lines of code) in the `FrictionFinding` payload. | When humans or LLMs read the friction report, seeing exactly which line caused the `REFUTED` finding reduces cognitive load and speeds up resolution. | FR-SAP-3 | Inspect the `sapper-friction-report.json`; verify the `REFUTED` findings include a `context_snippet`. |
| R4-F5 | Validation | medium | Cache FDE query results (`answer(question)`) across runs for identical assumptions. | Conformance assumptions routed to the FDE (e.g., "is Flask used?") don't change often. Caching these responses avoids repeatedly pinging the FDE (which might involve human-in-the-loop) for unchanged plans. | FR-SAP-7 | Run Sapper twice on the same plan; verify the FDE is only queried once and the second run uses the cache. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R3-F1: Batching is a massive win for speed and avoids redundant subprocess overhead.
- R3-F2: Injecting the report downstream is required; otherwise, the LLM will just repeat the errors.
- R3-F4: Size bounds are a crucial security/reliability guardrail against hallucination DOS.

#### Review Round R5

- **Reviewer**: gemini-3.1-pro
- **Date**: 2026-06-04 20:00:00 UTC
- **Scope**: Robustness, value to end-user, quick wins, and operational enhancements.

**Executive Summary:**
- Added a safeguard for mixed-language plans to prevent crashes on non-Python skeletons.
- Suggested CLI severity filtering to improve user experience and reduce noise.
- Proposed import path normalization before the pilot bore to prevent false-positive `REFUTED` findings.
- Recommended human-readable diffs in the markdown report for quicker comprehension.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R5-F1 | Architecture | high | Explicitly define how the Python-first pilot bore (NR-7) gracefully skips non-Python skeletons in a polyglot plan. | NR-7 states v1 is Python-first, but a plan might contain both Python and TypeScript files. If the pilot bore tries to feed TS skeletons to `mypy`, it will crash. It must filter `skeleton_sources` by language profile before overlaying. | FR-SAP-4 | Feed a mixed Python/TS plan to Sapper; verify TS skeletons are tagged `unavailable` while Python skeletons are typechecked. |
| R5-F2 | Ops | low | Add CLI filtering for the friction report (e.g., `--sapper-min-severity=high`). | If a plan produces 50 low-severity convention warnings and 1 critical existence miss, the user will ignore the report. Filtering lets developers focus on what matters most for their current workflow. | FR-SAP-8 | Run the CLI with the filter; verify the emitted report only contains findings at or above the requested severity. |
| R5-F3 | Robustness | medium | Normalize import paths (absolute vs relative) in the skeleton before running the pilot bore. | The LLM might write `from .models import X` instead of `from app.models import X`. If the overlay isn't perfectly structured, this could yield a false `REFUTED` from mypy. Normalizing or explicitly handling relative imports makes the bore more resilient to LLM quirks. | FR-SAP-4 | Provide a skeleton with a valid relative import; verify mypy correctly resolves it without throwing a false positive. |
| R5-F4 | Interfaces | low | Include a side-by-side or unified "diff" view in the human-readable markdown report for `REFUTED` findings. | Reading JSON `expected` vs `found` is tedious for humans. Rendering a small text diff in the `.md` report drastically improves the developer experience when reviewing friction. | FR-SAP-8 | Inspect the generated `.md` report; verify it contains a readable diff snippet for contradictions. |
| R5-F5 | Validation | medium | Emit specific telemetry alerts when `UNRESOLVED` findings with reason `bore_degraded` spike. | R1-F3 distinguishes `needs_ruling` from `bore_degraded`. If the environment breaks (mypy uninstalled from CI), `bore_degraded` will spike. Alerting specifically on this reason catches silent quality degradation instantly. | FR-SAP-8 | Trigger a run without mypy; verify the `bore_degraded` metric fires an alert in the local Prometheus/Grafana stack. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- R4-F1: CLI dry-run mode is a phenomenal developer experience quick win.
- R4-F2: Catching `SyntaxError` prevents total pipeline failure from a single hallucination.
- R4-F4: `context_snippet` is essential for rapid debugging.
