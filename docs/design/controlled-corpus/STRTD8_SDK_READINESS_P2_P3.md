# SDK Readiness for the strtd8 app — Phase 2 / Phase 3

**Date:** 2026-06-03
**Purpose:** get the SDK's deterministic-generation work in front of the strtd8 app's P2/P3 needs.
The app's cost model *is* the determinism boundary ("anything the SDK generates is $0 LLM";
ceiling 60–75%, P2 ≈85% owned, P3 ≈90% owned). This tracks what's enabled, what's verified, and
the remaining sequence.

---

## Step 1 ✅ — Corpus accumulation (write) enabled on the app's runs
`strtd8/.cap-dev-pipe/pipeline.env` now exports `STARTD8_CORPUS_ENABLED=1` +
`STARTD8_CORPUS_CONTENT_STORE=1` (serving `STARTD8_CORPUS_DETERMINISTIC` left **off**). Every
M4/M5/M6 (then P2/P3) run is now a **corpus producer**: term accumulation + durable proven-content
store under `strtd8/.startd8/`. Write-only, non-fatal, off the generation hot path. By P2/P3 the
determinism oracle will have scored the app's real files and the content store can serve the
`deterministic_candidate` ones (after the I5 gate). The SDK at `SDK_ROOT` has the corpus code
(content_store + I3a/I3b wired).

## Step 2 🟡 — Knowledge Provider → their Python schema (verified working; gaps found)
Ran `DraftModeProducer.build({"prisma/schema.prisma": <their schema>}, app)` on the real 15-model
contract:
- ✅ **Field-set authority works on all 15 models** — exact field names + types, incl. P2's
  `JobDescription` / `TailoredMatch` / `TailoredAsset`, rendered as *"mirror these field names/types
  EXACTLY … do NOT invent fields"*. **This is the bulk of their hand-authored Block A, automated.**
- ❌ **Negatives are TS-shaped** — the 3 emitted negatives (`@/lib/prisma`→`@/lib/db`,
  `@/lib/ai/client`→`@/lib/ai/service`) are TypeScript module paths from the **retired** TS
  prototype. The app is now Python; these don't apply. `negatives.py` seeds are TS-only. **Gap:**
  Python-shaped negatives (or drop them for Python projects).
- ✅ **Enum-value authority — now SHIPPED (REQ-CKG-525).** The Knowledge Provider now emits an
  "## Enum values — use EXACTLY these" block from the contract's `enum` blocks (reuses the shared
  parser's `PrismaSchema.enums`; `EnumAuthority` model + producer `_enums` + render). Verified: a
  schema declaring `enum SubjectType {…}` / `enum Stage {…}` injects all values. **App-side action to
  benefit:** declare `subjectType`/`kind` (and the P3 `Stage`) as Prisma **enums** in `schema.prisma`
  (today they're `String`) — then the hand-authored enum block retires automatically.
- ✅ **Injection wiring — CONFIRMED already live (step 2a done).** The PK is built once per batch
  (`_build_project_knowledge`, cached) and injected per feature via
  `_collect_upstream_interfaces(feature)` → `gen_context["upstream_interfaces"]` → spec/draft prompt;
  field-set injection is **not** TS-gated, so it already reaches the Python app. **Gap found + fixed:**
  the per-feature scoped render rebuilt the PK with `field_sets` only, dropping the new `enums` — fixed
  by carrying `enums=pk.enums` through the scoping seam (`prime_contractor.py` ~4569). So **field + enum
  authority now both reach the app's prompts.** (8 seam tests + 74 seam/PK tests green.)

**Net:** the loudest ask (auto-inject real field names) is **solved by existing machinery** for the
field layer; finishing step 2 = (a) confirm/do the injection wiring into their pipeline, (b)
Python-ify or drop the negatives, (c) add enum-value authority.

## Step 3 ⏳ — I5 live validation (needs the app team's live run)
The provider serve-path (`STARTD8_CORPUS_DETERMINISTIC`) flips on only after a live cap-dev-pipe run
confirms $0 serving with no regression. This requires API keys + LLM budget on a real app run — it's
the human-gated step. Harness ready: `validate_corpus_integration.py postrun <run_dir> <app_root>`
+ `PIPELINE_VALIDATION_RUNBOOK.md`. Sequence: enable write (done) → accumulate over M4/M5/M6 → one
run with the serve flag on → postrun checker → decide default-on.

## Step 4 🟡 — Completeness signal generator (generator capability shipped)
**Reframe (examination):** `app/completeness.py` is **already a generated owned artifact**
(`# startd8-artifact: python-completeness`, via `startd8 generate backend`) — not hand-seeded. The
real gap was the deferred **domain-weighted** refinement (OQ-4). **Shipped:** `render_completeness`
now takes an optional manifest — per-entity `min_rows` + `weight` + an `exclude` set (drop join
tables/`AiCall`; require e.g. ≥3 ProofPoints). Score = weighted fraction of *included* entities
meeting threshold; nudges name the threshold. **No-manifest path is byte-identical** to the v1
presence rule → zero change for projects without a `completeness.yaml`. 3 new tests (incl. a
no-manifest regression); 41 backend_codegen tests green.
**Deferred (next sub-step, post-live-run):** wire the assembler **and drift checker** to read an
optional project `completeness.yaml` and pass it to `render_completeness` — must reach **both** paths
or drift false-flags the weighted file. Not done now to avoid touching the live generate/drift path
during the app's in-flight step-3 run.

---

## P3 contract decisions (from the app owner, 2026-06-03) — record for contract-first readiness
P3 (FR-30–34 opportunity pipeline) is **gated on a hand-authored `.prisma` delta**. The owner settled
the three open design decisions toward **maximum determinism / $0**:

| Decision | Choice | Generation consequence |
|----------|--------|------------------------|
| Pipeline `Stage` | **Fixed/hardcoded → Prisma `enum`** (not a configurable `Stage` model) | Stage values are contract-declared; transitions are owned/deterministic. *(Implies the SDK should add **enum-value authority** — see Step 2 gap — so the enum's values inject automatically.)* |
| `Activity.next_action` | **Plain text** (no reminders/due-dates/cron yet) | Pure owned CRUD field; no async workers, no LLM. |
| `Qualification` | **Deterministic MEDDICC rules** (not LLM scoring) to start | Fixed scoring rules → owned/$0 pure function; no LLM, no drift. |

**Implication:** with these choices, **P3's core is ~fully owned/$0** — models + CRUD + HTMX +
polymorphic links + enum stages + deterministic qualification are all contract-derived. The only
later-optional LLM is kanban copy / next-action nudges (deferred). This is the best case for the
deterministic ceiling. **Action for the app team:** hand-author the P3 `.prisma` delta
(`Opportunity`, `Stage`-enum, `Contact`, `Activity`, `Qualification`) before any P3 run.

---

## Sequenced plan (one increment at a time)
1. ✅ **Step 1** — corpus write enabled on the app.
2. ✅ **Step 2 (a + enum) done** — (a) ✅ injection wiring confirmed live + enums carried through the
   per-feature scoping seam (field + enum authority now reach the app's prompts); (c) ✅ enum-value
   authority shipped (REQ-CKG-525). **(b) negatives — deferred to data-driven seeding** (current
   TS-shaped negatives are inert-not-harmful for the Python app; seed a Python negative only when the
   accumulating corpus/postmortems surface a real recurring Python invention — not speculatively).
   App-side: declare `subjectType`/`kind`/`Stage` as Prisma enums to benefit.
3. ⏳ **Step 3 (I5)** — app team runs one live cap-dev-pipe run with the serve flag; postrun-validate.
4. ⏳ **Step 4** — completeness signal generator from a domain-manifest.
5. ⏳ **P3 prep** — app team authors the P3 `.prisma` delta per the decisions above.
