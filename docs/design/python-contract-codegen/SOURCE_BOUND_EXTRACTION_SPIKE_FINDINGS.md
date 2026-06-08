# Source-Bound Extraction — Spike Findings

**Version:** 1.0
**Date:** 2026-06-08
**Status:** Spike complete — **CONVERGES** (promote to a narrow requirements doc)
**Charter:** `SOURCE_BOUND_EXTRACTION_SPIKE_CHARTER.md`
**Where it landed:** committed on `docs/prisma-emitter-requirements` (the spike was built out test-first
into the FR-SBE-1…6 capability — see §7/§8; `ai_layer.py` +197/−7, additive). *(The `spike/source-bound-extraction`
branch was created early but the working tree drifted onto `docs/prisma-emitter-requirements`; the work
was committed there.)*
**North-star:** `GENERATED_IMPORT_PATH_REQUIREMENTS.md` (deferred; this validates its mechanical core only)
**Design steer (operator, 2026-06-08):** *extract config from a formatted requirements document
with maximum simplicity; DERIVE from already-extracted manifests wherever possible; only when
unavoidable, a required input clearly defined in the kickoff inputs.* §4b records how the spike was
re-shaped to meet this — the binding is **derived, not authored**.

---

## 1. Answer to the spike question (one paragraph)

**Yes — and more cleanly than the charter assumed.** FR-14-class idempotent-by-source,
provenance-stamped extraction is delivered by a **small, additive** change to the **AI-layer
generator alone** (`+113/−3` in `ai_layer.py`), with **all existing generated code byte-identical**
and **`_persist` itself untouched**. The charter's "modify `_persist` + `_render_pass_text`" framing
was wrong in two instructive ways: (a) `_persist` is emitted from a **shared** `_PERSIST_HELPER`
string into *both* read- and text-mode harnesses, so editing it would have broken byte-identity for
**every** existing pass — the right move is **add a parallel `_persist_source` helper** emitted only
into bound harnesses; (b) source-scope idempotency is **not per-row dedup** — it's a once-per-run
"clear this source's prior *unconfirmed* rows" pre-step in the harness plus plain inserts. The
edge-schema generator, the export generator, and the entire `manifest_extraction` grammar were
**not touched**; the existing `human_inputs.yaml` omission already keeps the provenance field out of
the AI edge schema, so only the *stamp* half was new. The one genuine surprise (H-INT) fired but is
~8 gated lines.

## 2. Success criteria (§5 of the charter)

| Criterion | Result | Evidence |
|-----------|--------|----------|
| **Idempotency line** — re-extract same source ⇒ unconfirmed count stable, confirmed untouched | ✅ PASS | runtime: `run1`→1 unconfirmed; `run2`→still 1 (v1 replaced by v2, no dup); hand-confirmed row survived both |
| **Provenance** — field `== source_id`, `source="ai"`, `confirmed=false`, **absent from edge** | ✅ PASS | runtime stamp == `doc-A`; `ProofPointEdge` fields = `{name}` only (human_inputs omission, unchanged) |
| **Isolation** — no diff to `render_export` / `render_edge_schemas` / `manifest_extraction` | ✅ PASS | diff touches only `ai_layer.py`; those three generators untouched |
| ↳ *strict* "only `_persist` + `_render_pass_text`" | ⚠️ REFINED | 3 AI-layer sites: `_render_pass_text` (fork), `render_ai_routes` (H-INT), `AiPass`/`parse_ai_passes` (the binding marker). `_persist` **not** modified (parallel helper). |
| **No regression** — unbound byte-identical; AI-layer suite green | ✅ PASS | unbound pass+routes byte-identical (log-line aside); `100 passed, 1 skipped` |
| **H-INT resolved** | ✅ resolved, small | see §3 |

## 3. H-INT (the predicted surprise) — fired, and it's small

The text-mode route handler is generated, so a 3rd `source_id` argument has to come from the
request. Resolution: the shared `_Request` model gains **one optional field** `source_id: str | None
= None`, emitted **only when a bound pass exists** (so apps with no bound pass render byte-identical),
and the bound route threads `body.source_id`. ~8 lines inside `render_ai_routes`. The alternative
(path param / per-pass request model) was not needed. **H-INT does not bleed past the router** — no
edge-schema or extraction-grammar change.

## 4. Per-hypothesis findings

- **H1 (declarable identity key) — PARTIAL / REFINED.** Only the **`source:<field>`** member of the
  FR-IMP-2 vocabulary was built and proven — because it's the only one FR-14 needs. Its semantics
  are **replace-by-source** (clear prior unconfirmed, re-insert), which lives in the **harness**, not
  in a `_persist` dedup key. The broader vocabulary (`id` upsert / `<field>` / `[composite]` /
  `none`) is **unproven** and deferred — it belongs to the `from_json` round-trip half (FR-IMP-1),
  not to source-bound extraction. *Net: FR-IMP-2 should be split — the source-scope member ships
  here; the general identity key ships with FR-IMP-1.*
- **H2 (byte-identical unbound) — CONFIRMED.** Achieved by **add-don't-modify**: the unbound branch
  of `_render_pass_text`, the read-mode harness, and `_persist`/`_PERSIST_HELPER` are untouched.
  This is the load-bearing design rule — modifying the shared helper would have failed this.
- **H3 (stamp + edge omission) — CONFIRMED.** Stamp is one `setattr` in the new `_persist_source`;
  omission is the **existing** `human_inputs.yaml` path, reused with zero generator change.
- **H-INT (router) — CONFIRMED small** (§3).

## 4b. Derivation-first — the binding is *not* authored (the operator steer)

The charter's `source_binding:` manifest key was a throwaway stand-in. The steer demanded better:
the binding must **fall out of already-extracted facts**, with new authored config only as a
last-resort kickoff input. It does — fully:

**Derivation rule (zero new authored config).** A text-mode pass becomes source-bound when its
single output entity carries a **server-managed loose-reference** field — the convergence of three
facts the existing extractors already produce:

| Fact | Already extracted by | From the requirements doc's… |
|------|----------------------|------------------------------|
| pass is **text-mode** (prose `Reads`, no `input_entities`) | `extract_ai_passes` | `## AI assists` table (`Reads: uploaded resume`) |
| field is **server-managed** | `extract_human_inputs` | `ONLY HUMANS ENTER THIS` field-note **or** `Only humans enter:` line |
| field is a **loose ref** (optional scalar `String`, not PK, not a relation FK) | `parse_prisma_schema` | the entity table's field row |

That field **is** the provenance target. The author writes **nothing new** — declaring the field
and marking it human-owned (which FR-14 requires anyway) is the entire "config."

**End-to-end proof (the real extractor, not a stub).** A requirements-doc fragment → `extract_manifests()`
→ `ai_passes.yaml` (text-mode) + `human_inputs.yaml` → `effective_source_binding()` ⇒ `sourceDocumentId`,
**with no `source_binding:` key anywhere**. Derivation precedence is **explicit > derived > none**:

| Case | Result |
|------|--------|
| loose-ref + human-marked, no key | ✅ **derived** → `sourceDocumentId` (zero config) |
| field present but not human-marked | unbound (today's behavior) |
| **two** server-managed loose-refs, no key | ✅ **loud fail** naming the fix: *"add `source_binding: <field>` … (declare it as a kickoff input)"* |
| explicit `source_binding:` override | always wins (the kickoff-input escape hatch) |

So the answer to "how is it declared?" is: **it isn't, in the normal case.** The `source_binding:`
key survives only as the disambiguation override for the rare >1-candidate case — the single,
clearly-defined kickoff input the steer allows.

## 5. What was built (the throwaway evidence)

All in `src/startd8/backend_codegen/ai_layer.py`, additive (+173/−5):
1. **`effective_source_binding()` + `_loose_ref_candidates()`** — the derivation (§4b): explicit >
   derived > none; >1 candidate → loud fail naming the kickoff input.
2. `AiPass.source_binding: Optional[str]` + `_PASS_KEYS` + strict parse — now the **override** only.
3. `_render_pass_text(ps, source_binding)` forks; new `_render_pass_text_bound(ps, prov)` emits
   `def <pass>(text, session, source_id)` with the once-per-run **clear-prior-unconfirmed** pre-step.
4. New `_PERSIST_SOURCE_HELPER` (`_persist_source`) — stamps `_PROVENANCE_FIELD`, skips name-dedup;
   emitted **only** into bound harnesses. `_persist` unchanged.
5. `render_ai_pass` / `render_ai_routes` compute the binding via `effective_source_binding`;
   `_Request.source_id` + bound-route threading gated on a derived binding existing (H-INT).

## 6. Decision (§6 of the charter)

**Row: "Converges except H-INT (router work needed)" → PROMOTE,** folding the measured ~8-line
router cost in. Recommend a **narrow** requirements doc — **FR-IMP-4 + FR-IMP-5 + the source-scope
member of FR-IMP-2 only** — with these as hard constraints:
- **Derivation-first (§4b)**: the binding is derived from `ai_passes` + `human_inputs` + the
  contract; `source_binding:` is the override-only escape hatch. Add `source_binding: none` (opt-out)
  in the promoted work (§7).
- **Add-don't-modify**: parallel bound shapes; `_persist`/`_PERSIST_HELPER` and all unbound/read
  output stay byte-identical (a drift/regression guard, not just a nicety).
- **Isolation budget**: AI-layer generator only (3 sites). Any creep into `render_edge_schemas` or
  `manifest_extraction` is out of scope and a redesign trigger.
- **Split FR-IMP-2**: source-scope ships with extraction; the general identity key ships with the
  deferred `from_json` (FR-IMP-1), not here.

## 7. Residual gaps / honest limitations

> **Update 2026-06-08 (post-promotion build): the first two residuals are CLOSED, and the build of
> the narrow requirements (`SOURCE_BOUND_EXTRACTION_REQUIREMENTS.md`) surfaced + fixed two further
> defects.** Suite now **211 passed, 1 skipped**. Details below.

- ✅ **CLOSED — opt-out (`source_binding: none`).** Added in `effective_source_binding` (sentinel
  ahead of the override return) + `parse_ai_passes` (exempts `none` from the strict text-mode/single-
  output rejections). Routes through the one binding chokepoint, so no raw `"none"` leaks. 10 tests.
- ✅ **CLOSED — end-to-end HTTP test.** `tests/unit/backend_codegen/test_source_bound_extraction.py`
  boots a generated app and over a live `TestClient` asserts stamp + source-scoped idempotency +
  confirmed-row safety on the actual route.
- ✅ **CLOSED + FIXED — generated `test_ai_passes.py` referenced the wrong helper (correctness bug).**
  The pass-test emitter emitted `mod._persist(...)` for *every* pass; a **bound** harness defines
  `_persist_source`, not `_persist`, so a generated app with a bound pass shipped a **broken test**
  (AttributeError). `render_ai_pass_tests` is now bound-aware (calls `_persist_source`, asserts the
  stamp). Guarded by `test_emitted_bound_ai_tests_run_green` (writes the app to disk, runs its tests).
- ✅ **CLOSED + FIXED — harness cleared prior rows BEFORE the AI call (data-loss + keyless crash).**
  The bound harness ran the clear-prior-unconfirmed query *before* `call_ai_service`. Two bugs: a
  **keyless** call hit the DB first → 500 instead of the polite 503 (caught by the generated keyless
  boot test); and worse, **a failed AI call would delete the user's prior extraction without
  replacing it** (data loss). Fixed by reordering: the clear now runs **only after a successful
  call**. *This is the highest-value catch of the whole exercise — found only because FR-SBE-6 runs
  the generated app's own test suite.*
- **Still open — `schema.prisma` is hand-authored today.** Two of three derivation inputs are
  prose-derived (ai_passes, human_inputs); the loose-ref field's presence in the contract is
  hand-authored until the **Prisma emitter (FR-PE)** lands — then the whole chain is prose-derived.
  The option-3 seam with `PRISMA_EMITTER_REQUIREMENTS.md` (tracked as OQ-SBE-2).
- **Only single-output, single-provenance-field** bound passes (parse rejects multi-output;
  OQ-IMP-2 cardinality stays open — matches the consumer's one-field need).
- **`source_id` arrives in the JSON body**; a path-param surface (`POST /ai/extract/{source_id}`)
  was not explored and may read better for a "extract from *this* stored doc" affordance.
- ✅ **CLOSED — generated bound-pass tests now emitted.** `render_ai_pass_tests` is bound-aware; the
  rung-4 guarantee is self-testing per app (FR-SBE-6), and fixing it caught the two correctness bugs.

## 8. Disposition

The spike was **built out test-first into the FR-SBE-1…6 capability** and **committed on
`docs/prisma-emitter-requirements`** (suite 211 passed / 1 skipped) — it is no longer throwaway. The
objections that made it un-mergeable (no generated tests, the two correctness bugs) are resolved.
Remaining before any squash/merge to `main`: the FR-PE seam (OQ-SBE-2). *(The early
`spike/source-bound-extraction` branch is now vestigial — empty of this work.)*

---

*Spike complete 2026-06-08. Converges: the mechanical core is small (+113/−3, additive), isolated to
the AI-layer generator, byte-identical for all existing output, and runtime-proven on the FR-14
acceptance line. Promote FR-IMP-4/5 + source-scope FR-IMP-2 to a narrow requirements doc; keep the
`imports.yaml` grammar + `from_json` half (FR-IMP-1/3/6) deferred in the north-star until consumer #2.*
