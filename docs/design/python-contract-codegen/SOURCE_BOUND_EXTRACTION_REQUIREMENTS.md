# Source-Bound Extraction — Requirements

**Version:** 0.1 (Post-spike — drafted from validated evidence)
**Date:** 2026-06-08
**Status:** Draft — **FR-SBE-1…6 IMPLEMENTED + green**, committed on branch
`docs/prisma-emitter-requirements` (`backend_codegen` suite **211 passed, 1 skipped**). The build
surfaced two further defects now fixed (the generated test referenced the wrong persist helper; the
harness cleared prior rows before the AI call → data-loss/keyless-crash — see `…_SPIKE_FINDINGS.md`
§7). Remaining: the FR-PE seam (OQ-SBE-2).
**Format:** SDK-internal requirements (REQ/FR), grounded against shipped `backend_codegen/ai_layer.py`
**Promoted from:** `SOURCE_BOUND_EXTRACTION_SPIKE_CHARTER.md` + `…_SPIKE_FINDINGS.md` (converged 2026-06-08)
**Companion:** `GENERATED_IMPORT_PATH_REQUIREMENTS.md` (deferred north-star — this is its mechanical
core, FR-IMP-4/5 + the source-scope member of FR-IMP-2), `PRISMA_EMITTER_REQUIREMENTS.md` (the
contract-IN seam — option 3), `../kickoff/KICKOFF_AUTHORING_CONTRACT.md` (the grammar the binding
derives from)
**First consumer:** strtd8 `docs/kickoff/CONTENT_IMPORT_REQUIREMENTS_v0.2-draft.md` FR-14

> **Objective.** Make a generated app's text-mode AI pass able to **extract structured rows from a
> stored source record, stamped with that record's id, idempotently by source** — the FR-14
> capability — as a **deterministic, $0, generated** behavior. The binding is **derived from
> already-extracted manifests, not authored**: a text-mode pass whose output entity carries a
> server-managed loose-reference field is source-bound on that field. New authored config appears
> only as a disambiguation/opt-out override (a clearly-defined kickoff input), never in the common
> case. This is **bucket 3 (integration)** of the CLAUDE.md scope separation — the one in-scope LLM
> touch (the `extract` pass) is **reused**, not reinvented; only its harness/persist glue is new.

> **Scope discipline.** This is the *converged* slice of the deferred import-path generalization. It
> deliberately excludes the round-trip `from_json` owned-kind, the `imports.yaml` grammar, the
> general identity-key vocabulary, and the import surface (all held in the north-star for a second
> consumer). It ships **only** what FR-14 needs and the spike proved small + isolated.

---

## 0. Planning Insights (from the spike, 2026-06-08)

> This doc is drafted *after* a converged spike, so its
> requirements are evidence-backed, not assumed. The spike corrected the charter's framing in five
> ways; each correction is folded into the FRs below.

| Charter assumption | Spike finding | Requirement impact |
|--------------------|---------------|--------------------|
| The binding is declared via a `source_binding:` manifest key. | It can be **derived** from the convergence of `ai_passes` (text-mode) + `human_inputs` (server-managed) + the contract (loose ref). Proven end-to-end through the real `extract_manifests()`. | **FR-SBE-1** makes derivation the primary path; the key is override-only. |
| Modify `_persist` to add the dedup key + stamp. | `_persist` is emitted from a **shared** helper into every pass; editing it breaks byte-identity for *all* passes. **Add a parallel `_persist_source`**; leave `_persist` untouched. | **FR-SBE-5** mandates add-don't-modify as a hard constraint. |
| Source-scope idempotency is a per-row dedup key. | It's **replace semantics** — a once-per-run "clear this source's prior *unconfirmed* rows" pre-step in the harness, then plain inserts. | **FR-SBE-3** specifies clear-then-insert, not per-row dedup. |
| Provenance = mark the field human-managed in `human_inputs`. | Omission keeps the AI from authoring it but **nothing stamps it** → it lands null. Omission **and** server-stamp are two requirements. | **FR-SBE-2** requires both (omit + stamp). |
| Isolation = `_persist` + `_render_pass_text` only (2 sites). | Actually **3 AI-layer sites** (harness + router + the binding marker); but `render_edge_schemas` / `render_export` / `manifest_extraction` untouched, and H-INT (router) is ~8 gated lines. | **FR-SBE-5** sets the isolation budget at the AI-layer generator. |

**Open questions resolved by the spike:** the binding is derivable (was OQ); the router threading
(H-INT) is small and gated; the edge-omission half is free (reuses `human_inputs`). **Still open:**
see §4 (OQ-SBE-1…3 — cardinality, the FR-PE precision tightening, and the route surface).

---

## 1. Problem Statement

A generated app's **text-mode** AI pass today is `def <pass>(text, session)` (`ai_layer.py`
`_render_pass_text`): free text in, rows out, deduped **by `name` only** (`_persist`,
`ai_layer.py:384`). For FR-14 — "extract proof points *from a stored document*, tagged with which
document, and re-runnable without duplicate explosion" — that shape is structurally insufficient on
three counts the spike confirmed:

| Need (FR-14) | Shipped gap |
|--------------|-------------|
| Know *which* stored record a row came from | No source parameter reaches the harness; nothing stamps a provenance field |
| Provenance field is never AI-invented | The edge schema hands every non-omitted scalar to the AI; an un-omitted id is hallucinated |
| Re-extract is idempotent by source | `_persist` dedups by `name`; an entity without a `name` column **appends duplicates** on every re-run |

The fix must be **$0/deterministic** (it's generated glue, not content), **isolated** to the
AI-layer generator, and — per the operator steer — **declared by deriving from the requirements
document**, not by new hand-authored config.

## 2. Requirements

> FR-SBE-1…6. One behavior each, with a `Verify:` line. The spike supplies the evidence each
> references; the build is a **test-first reimplementation**, not a merge of the spike branch.

- **FR-SBE-1 — Derive the source-binding from already-extracted manifests (no authored config).**
  The generator determines whether a text-mode pass is source-bound by **derivation**: a pass with
  no `input_entities` and exactly one output entity is bound to the **one** server-managed
  loose-reference field on that entity (optional scalar `String`, not the PK, present in
  `human_inputs.yaml`). Precedence is **explicit override > derived > none**. Touches:
  `effective_source_binding`, `_loose_ref_candidates`. Verify: given `ai_passes.yaml` (text-mode) +
  `human_inputs.yaml` (field marked) + a contract with that loose-ref field and **no `source_binding`
  key**, the generator binds to the field; a pass whose output entity has no such field is unbound;
  the whole chain holds end-to-end from a requirements doc through `extract_manifests()`.

- **FR-SBE-2 — Source-bound harness: stamp a server-managed provenance field (FR-IMP-4/5).** A bound
  pass emits `def <pass>(text, session, source_id)` that, on persist, **server-stamps** the derived
  provenance field with `source_id` (`source="ai"`, `confirmed=false`), via a persist path parallel
  to `_persist` (never modifying it). The provenance field is **omitted** from the AI edge schema
  (reusing the existing `human_inputs` omission — no edge-generator change), so the AI can neither
  see nor author it. Touches: `_render_pass_text_bound`, `_persist_source`. Verify: after a bound
  pass, every written row's provenance field equals `source_id` and is absent from the entity's edge
  model (existing `test_edge_privacy` assertion still holds).

- **FR-SBE-3 — Source-scoped idempotency (the source member of FR-IMP-2).** After a **successful**
  AI call, a bound pass **clears that source's prior *unconfirmed* rows** (replace semantics), then
  inserts; **confirmed rows are never touched.** The clear MUST run *after* `call_ai_service`
  returns, never before — a keyless/failed call raises first, so prior rows are **never deleted
  without replacement** (data-loss safety) and the keyless contract (polite 503) is preserved.
  Touches: `_render_pass_text_bound` (the post-call clear step). Verify: running a bound pass twice
  with the same `source_id` leaves the count of that source's unconfirmed rows stable (no duplicate),
  a different `source_id` is isolated, a pre-existing confirmed row survives both runs, **and a
  keyless call returns 503 with the prior unconfirmed rows intact (not deleted).**

- **FR-SBE-4 — Override + opt-out (the only authored input, kickoff-defined).** An explicit
  `source_binding: <field>` selects the provenance field when derivation is ambiguous;
  `source_binding: none` **disables** binding for an entity that matches the loose-ref shape by
  coincidence. **More than one candidate with no override fails loudly**, naming the fix. Touches:
  `parse_ai_passes`, `effective_source_binding`. Verify: two server-managed loose-refs + no override
  → `ValueError` naming `source_binding`; `source_binding: originId` selects it; `source_binding:
  none` yields an unbound (byte-identical) pass despite a candidate existing. The override key and
  its `none` value are documented in the kickoff-inputs guide.

- **FR-SBE-5 — Additive isolation; existing output byte-identical.** All changes are confined to the
  **AI-layer generator** (`ai_layer.py`); `render_edge_schemas`, `render_export`, and
  `manifest_extraction` are **not** touched, and `_persist` / `_PERSIST_HELPER` are **not** modified
  (parallel `_persist_source` instead). Every genuinely-unbound pass and every read-mode pass renders
  **byte-identical** to the prior version. Touches: the whole change set. Verify: rendering a pass
  whose output entity has no server-managed loose-ref produces output byte-identical to `main`; the
  full `backend_codegen` suite stays green.

- **FR-SBE-6 — The bound shape is self-testing (rung-4).** A generated app with a bound pass emits
  its own provenance + idempotency tests (extend the `ai-tests-pass` emitter), and the route is
  exercised over FastAPI TestClient (the spike's one untested seam). Touches: the AI-layer test
  emitters; `render_ai_routes`. Verify: a generated app's test suite contains, for each bound pass, a
  test asserting stamp + source-scoped idempotency, and an HTTP test POSTing `{text, source_id}` to
  the pass route and asserting a stamped row.

## 3. Non-Requirements (scope fence)

- **No `from_json` round-trip import, no `imports.yaml` grammar, no import surface.** Held in the
  north-star (`GENERATED_IMPORT_PATH_REQUIREMENTS.md`) for a second consumer.
- **No general identity-key vocabulary.** Only the **source-scope** member of FR-IMP-2 ships here;
  `id` upsert / arbitrary field / composite keys belong with the deferred `from_json`.
- **Single output entity, single provenance field per bound pass.** Multi-output and multi-field
  binding are out (parse rejects them); OQ-SBE-1 tracks cardinality.
- **No change to `_persist`, the edge-schema generator, or manifest extraction.** Add-don't-modify
  (FR-SBE-5).
- **No contract authorship.** Emitting the loose-ref field into `schema.prisma` from prose is the
  **Prisma emitter's** job (FR-PE); here the field is assumed present in the contract.
- **No binary source formats.** Text only (the pass consumes `text`); PDF/DOCX deferred with stated
  dependency cost (consumer OQ-2).

## 4. Open Questions

- **OQ-SBE-1 — Binding cardinality.** v1 binds one `source_id` → one provenance field. A future
  consumer needing multiple stamped fields would generalize to a `{context-key → field}` map. Keep
  single until a second need appears.
- **OQ-SBE-2 — Derivation precision vs the FR-PE loose-ref marker.** Today the loose-ref predicate is
  "optional `String`, not PK, in `human_inputs`." Once the **Prisma emitter** introduces an explicit
  loose-reference marker (FR-PE-5.3 / OQ-PE-3), tighten the predicate to use it (eliminates the
  coincidence case FR-SBE-4's opt-out exists for). Sequence: ship FR-SBE-4 opt-out now; tighten when
  FR-PE lands. **This is the option-3 seam.**
- **OQ-SBE-3 — Route surface for `source_id`.** v1 carries `source_id` in the JSON body
  (`_Request.source_id`). A path-param surface (`POST /ai/<pass>/{source_id}`) may read better for
  "extract from *this* stored record." Decide before FR-SBE-6's HTTP test crystallizes the contract.

## 5. The derivation rule *(spike-confirmed — the normative spec)*

```
For each AI pass P:
  if P.source_binding == "none":            -> UNBOUND (explicit opt-out, FR-SBE-4)
  elif P.source_binding is a field name:    -> BOUND to that field (explicit override)
  elif P has input_entities OR != 1 output: -> UNBOUND (read-mode/multi-output never auto-derived)
  else:
    candidates = output entity's fields that are
        (optional scalar String) AND (not the PK) AND (in human_inputs.yaml)
    if len(candidates) == 1: -> BOUND to candidates[0]      (DERIVED, zero config)
    elif len == 0:           -> UNBOUND                      (today's behavior, byte-identical)
    else:                    -> ERROR: ambiguous, name source_binding (a kickoff input)
```

**The three derivation inputs and where each is authored** (the "derive from extracted items" story):

| Input | Extracted by | Authored in the requirements doc as |
|-------|-------------|--------------------------------------|
| text-mode pass | `extract_ai_passes` | `## AI assists` row, prose `Reads` cell |
| field is server-managed | `extract_human_inputs` | `ONLY HUMANS ENTER THIS` note / `Only humans enter:` line |
| field is a loose ref | `parse_prisma_schema` | the entity-table field row (a `text` field, no relation) — **FR-PE-derived once the Prisma emitter lands** |

## 6. Dependencies & sequencing

- **Independent of the Prisma emitter (FR-PE) for build.** The spike ran against a hand-authored
  `schema.prisma`; this capability ships without waiting on FR-PE. FR-PE later makes the *third*
  derivation input (the loose-ref field's presence) prose-derived too, completing the chain.
- **Seam with FR-PE (option 3):** the provenance field is **declared once** — in the entity table
  (canonical); `human_inputs` omission **derives** from it, and this capability's stamp-binding
  **references** it. OQ-SBE-2 tightens the predicate to FR-PE's loose-ref marker when it lands.
- **Sequence:** FR-SBE-1 (derivation) + FR-SBE-2/3 (harness) → FR-SBE-4 (override/opt-out) →
  FR-SBE-5 (isolation guard, continuous) → FR-SBE-6 (self-testing) → strtd8 FR-14 acceptance.

## 7. Acceptance

1. **Derivation:** the five §5 cases as golden tests (derive / unbound-no-field / ambiguous-fail /
   override / opt-out), plus the end-to-end `extract_manifests()` → binding test.
2. **Runtime:** a bound pass over real SQLModel — stamp + source-scoped idempotency + confirmed-row
   safety (the spike's runtime acceptance, promoted into the suite).
3. **HTTP:** a TestClient run of the bound route (FR-SBE-6) — POST `{text, source_id}` → stamped row;
   re-POST → idempotent.
4. **Isolation:** genuinely-unbound + read-mode passes byte-identical to pre-change; no diff to
   `render_edge_schemas` / `render_export` / `manifest_extraction`; full `backend_codegen` suite green.
5. **End-to-end (strtd8 FR-14):** the `extract` pass, bound by derivation to `ProofPoint
   .sourceDocumentId`, extracts from a stored `ImportedDocument`'s text, stamps the id, and re-runs
   idempotently — zero hand-authored binding config.

---

*Draft 0.1 — promoted from a converged spike (2026-06-08). Ships FR-IMP-4/5 + the source-scope member
of FR-IMP-2 as a derivation-first, additive, AI-layer-isolated capability; the binding is derived from
already-extracted manifests with an override/opt-out as the only (rare) authored input. The `from_json`
round-trip, `imports.yaml` grammar, and general identity key stay deferred in the north-star. Ready for
test-first build; OQ-SBE-2 is the live seam with the Prisma emitter (option 3).*
