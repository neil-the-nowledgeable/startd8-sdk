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
- ❓ **Injection wiring** — the producer *exists and works*, but it must be confirmed that the app's
  generation actually calls it and injects `render(pk)` into the spec/draft prompts (P2_BATCH_PLANS
  §0 lists the Knowledge Provider as "one build away" / pending — likely **not yet wired into their
  runs**). This is the real remaining work to retire Block A.

**Net:** the loudest ask (auto-inject real field names) is **solved by existing machinery** for the
field layer; finishing step 2 = (a) confirm/do the injection wiring into their pipeline, (b)
Python-ify or drop the negatives, (c) add enum-value authority.

## Step 3 ⏳ — I5 live validation (needs the app team's live run)
The provider serve-path (`STARTD8_CORPUS_DETERMINISTIC`) flips on only after a live cap-dev-pipe run
confirms $0 serving with no regression. This requires API keys + LLM budget on a real app run — it's
the human-gated step. Harness ready: `validate_corpus_integration.py postrun <run_dir> <app_root>`
+ `PIPELINE_VALIDATION_RUNBOOK.md`. Sequence: enable write (done) → accumulate over M4/M5/M6 → one
run with the serve flag on → postrun checker → decide default-on.

## Step 4 ⏳ — Completeness signal generator (build)
The app hand-seeds `app/completeness.py` (M5) from a `completeness_signals.yaml`; the SDK should
generate it from the contract/domain-manifest (this is also the SDK's OQ-4 completeness
domain-manifest). Next build increment.

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
2. 🟡 **Step 2 finish** — (a) wire/confirm Knowledge-Provider injection into the app's generation;
   (b) Python-ify or drop negatives; (c) ✅ **enum-value authority shipped** (REQ-CKG-525) — app
   declares enums in `schema.prisma` to benefit; also unblocks P3's `Stage` enum.
3. ⏳ **Step 3 (I5)** — app team runs one live cap-dev-pipe run with the serve flag; postrun-validate.
4. ⏳ **Step 4** — completeness signal generator from a domain-manifest.
5. ⏳ **P3 prep** — app team authors the P3 `.prisma` delta per the decisions above.
