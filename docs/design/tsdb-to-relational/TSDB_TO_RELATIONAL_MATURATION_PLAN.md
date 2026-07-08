# TSDB → Relational Maturation — Plan

**Version:** 1.1 (CRP R1 triaged — 8 S-suggestions merged)
**Date:** 2026-07-08
**Requirements:** `TSDB_TO_RELATIONAL_MATURATION_REQUIREMENTS.md` (v0.5)

Every claim is grounded in code read this session (`file:line` cited). The capability **generalizes the
michigan converter** (`export_to_supabase.py`) and **reuses the SDK's gated back-half**; the only real
build is rung 3 (inference).

## Planning summary

The SDK owns the entire deterministic back-half (parse → emit → gate → generate → import), so the build
concentrates in **rung 3 (inference)** plus two seams the v0.1 draft under-specified (an `imports.yaml`
generator; a bookkeeping-collision guard). The michigan schema DDL is an **executable golden**: the §3
paper-diff below becomes a test asserting the inferred `schema.prisma` reproduces it.

## FR → Seam map

| FR | Reuse / Build | Seam |
|----|---------------|------|
| FR-1 read-back | **BUILD (greenfield)** | No TSDB reader in `src/` (grep empty). New `tsdb_maturation/reader.py` (`httpx` instant query + `last_over_time(<m>[<lookback>])`). Generalize michigan `query_mimir` (export_to_supabase.py:57), don't port urllib. |
| FR-2 specimen | BUILD | `tsdb_maturation/specimen.py` `flatten_series` (generalizes `extract_labels`/`extract_value` :73-81); durable JSON (generalizes `--output-json` :598). Stores **raw** series (aggregation deferred — see FR-6/OQ-13). |
| FR-3 type+column infer | **BUILD (core)** | `_infer_scalar_type(values)` — *genuinely new* (michigan + `PLAIN_TYPES` entities.py:30 are declared-only). Build `EntityGraph` **directly** à la `graph_from_prisma` (entities.py:544), NOT `extract_entities` (prose-coupled). Reuse `render_prisma_schema(graph)` (prisma_emitter.py:266) verbatim. |
| FR-4 identity infer | BUILD | Minimal-unique label subset → `IdentityKey(kind="composite")` (identity.py:33). `identity.py` only *parses* declared keys — "never invents" (:132). Declared `--identity` → `parse_declared_identity` (:115). |
| FR-5 reduction | BUILD (policy) | `topk`/`sum by` in the PromQL (FR-1 layer), michigan-proven (:262-296). **Default: auto top-N + loud warning** (OQ-3). |
| FR-6 key-collapse agg | BUILD (port) | Port `deduplicate_rows`+`AGGREGATE_COLUMNS` (:385-422) into records-build. SDK importer `_import_row` (import_codegen.py:270) is **silent last-writer-wins**, not an error → aggregation is mandatory and runs **after** FR-4. |
| FR-7 gate+promote | **REUSE 100%** | `emit_schema_draft`→`EmitGateResult` (prisma_emitter.py:439), `promote_schema` (:490), `UnrenderableField` (:63). Greenfield gate = round-trip + non-empty + no-unrenderable (parity only bites on re-promote, :465). |
| FR-8 generate+backfill | REUSE + coercion free | `generate backend` (cli_generate.py:139) + generated `from_json` (import_codegen.py:292). `_COERCE` already round-trips **Decimal/DateTime**/Int/Float/Bool (:30-37) → backfill typing is free. |
| FR-9 grain honesty | BUILD (metadata) | `grain` marker (`tsdb_aggregate` vs `import_source`) + refusal to present aggregate as per-event. Two modes (OQ-5). |
| FR-10 CLI | BUILD (thin) | `startd8 promote tsdb <metric>` modeled on `generate contract` (cli_generate.py:734). |
| FR-11 bookkeeping-collision guard | **BUILD (hard gate)** | Rename/preserve any label ∈ `_BOOKKEEPING` (`id/ownerId/source/confirmed/createdAt/updatedAt`, prisma_emitter.py:53). **Verified collision:** gov `source` → duplicate-field error → gate refuses. |
| FR-12 metric-family grouper | BUILD | Shared-identity metrics → one multi-measure table (michigan `_amount`+`_count`→`historical_payments` :181-227). Reader issues N queries + index-joins by identity (`count_index` :202). |
| FR-13 histogram → stats table | **BUILD (largest add)** | Detect `_bucket`/`_sum`/`_count` → a percentile/stats table (distinct inference path). In scope per OQ-7. Candidate for its own milestone. |
| FR-14 imports.yaml generator | **BUILD (hidden dep)** | No programmatic writer exists (only prose extraction, extractors.py:885). Serialize inferred `IdentityKey` → `imports.yaml` `parse_imports` accepts (imports_manifest.py:57). Without it: no importer emitted (assembler.py:148) → `id`-dedup → infinite duplication. |

## Inference-taste (paper diff) — `department_budgets` → executable golden

Inference **can** reproduce the golden's structure (5-col composite key, measure column, dimensions), with
**four verified divergences** that are design decisions, not blockers:

1. **`source`-label ↔ bookkeeping collision** — HARD (blocks the gate). → FR-11 (rename+preserve).
2. **slug/display pairing** (`fund_source`/`fund_source_display`) — inference types them independently; if one → enum, they desync. → OQ-10.
3. **NUMERIC(15,2) → Float vs Decimal** — golden argues Decimal; `_COERCE` supports it free. → OQ-9.
4. **enum-vs-TEXT for low-cardinality labels** — golden keeps TEXT; inference can synthesize enums. → OQ-10.

The 5-column composite `@@unique` **is reproducible** iff identity inference finds the minimal-unique
subset without pulling in a functionally-dependent *display* column (michigan `CONFLICT_COLUMNS` :483 is
the ground truth). This is the load-bearing risk (M2). Casing (snake vs camel) is cosmetic but must be
decided so the specimen↔column mapping in the importer stays consistent.

## Milestones (dependency + risk ordered)

- **M0 — TSDB reader (FR-1).** `httpx` instant query + `last_over_time` + endpoint/lookback config +
  **empty-result detection** distinguishing pruned-vs-absent (R1-F6) + **auth** (env/secrets, 401≠empty —
  R1-F11). **Includes family-read support up front (R1-S5):** one-query-per-member + index-join by
  identity — FR-12 grouping (M2) depends on this M0 *capability*, not merely "M0 done". Validated vs a
  recorded fixture. Low risk.
- **M1 — Specimen (FR-2, FR-9).** `flatten_series` + durable JSON + `--dry-run` + `grain` metadata.
  Stores **raw** series (record count == series count — the input contract FR-4 asserts). Depends M0.
- **M2 — Inference core (FR-3/4/5/11/12) — THE RISK.** `_infer_scalar_type`, **direct `EntityGraph`**
  (replicating the `extract_entities` post-conditions the prose path enforces — reserved-name checks,
  relation handling — enumerated + tested, R1-S8), `infer_identity` (deterministic tie-break + display
  exclusion + raw-specimen input), bookkeeping-collision rename via a **public reserved-names accessor the
  emitter exposes** (R1-S7 — a one-line emitter seam, not importing the private `_BOOKKEEPING`), reduction
  policy, family grouper (member-alignment/outer-join). **Two exit gates, not one (R1-S1):** (a)
  *structural* — type/graph/collision correct; (b) *identity correct* — the inferred key asserted against
  michigan `CONFLICT_COLUMNS` **AND** a **negative fixture** where a `*_display` column would be wrongly
  picked. M2 must not pass on structure alone. **Golden test asserts the post-divergence normalized shape
  (R1-S2):** it applies the four *expected* transforms before comparing — `source`→`dataSource` rename,
  `Decimal` measure, TEXT-not-enum, display-excluded key.
- **M2.5 — Confirmation gate (FR-4/R1-S6).** Surface the inferred key next to the golden diff; record the
  confirmation as a **committed marker** (kickoff `confirmed.yaml` pattern); re-promote re-confirms if the
  key changed. A small but real milestone home between infer (M2) and gate (M4) — neither currently owns
  it. Depends M2.
- **M3 — imports.yaml generator (FR-14).** Serialize inferred identity → `imports.yaml` with a **semantic
  round-trip contract** (R1-F3): `parse_imports(generate(key)) ==` key on kind+ordered-cols+coerce.
  Depends M2.
- **M4 — Gate wiring (FR-7).** Reuse `emit_schema_draft`/`promote_schema` on the M2 graph; verify
  collision/unrenderable surfacing; enforce the M2.5 confirmation. Depends M2.5.
- **M5 — Backend + backfill (FR-6, FR-8).** `generate backend --imports <generated>` + `from_json`;
  records-build aggregation (after identity). **Explicit tests (R1-S3/S4):** an **E2E** proof that the
  generated `imports.yaml` makes the importer **dedup on the inferred identity** (re-run backfill twice →
  **0 new rows**), *not* just that `parse_imports` accepts it; a **key-collapse guard** (colliding specimen
  → assert summed totals, no last-writer-wins loss) **plus a non-additive negative** (a gauge metric →
  assert NOT blindly summed). Decimal/DateTime coercion round-trip (free). Depends M3, M4.
- **M6 — CLI (FR-10).** `startd8 promote tsdb <metric>` orchestrating M0→M5.
- **M7 — Histograms (FR-13).** `_bucket`/`_sum`/`_count` → stats table. Separated because it's the
  largest, most distinct inference path; keeps M2 bounded.

Risk concentrates in **M2** (now guarded by a two-part exit gate); M4/M5 are reuse + explicit E2E tests;
M0/M1 are proven-pattern ports; M2.5/M3/M7 are the new builds.

## Risks

1. **Identity inference picks the wrong subset** (includes a display column / drops a slug) → wrong dedup
   key → silent overwrite on backfill. Mitigation: the michigan `CONFLICT_COLUMNS` golden test + gate
   confirmation (OQ-4).
2. **Silent data loss on key collision** (SDK importer has no DB tripwire) — makes FR-6 non-optional; test
   with a deliberately-colliding specimen asserting summed totals.
3. **imports.yaml generator** is the one fully-new writer in a codebase where all manifests come from
   prose extraction — small but load-bearing (no importer without it).
4. **Histogram path (M7)** could balloon; keep it isolated and shippable-last.

## Traceability

| Req | Milestone |
|-----|-----------|
| FR-1 | M0 |
| FR-2, FR-9 | M1 |
| FR-3, FR-4, FR-5, FR-11, FR-12 | M2 |
| FR-4 confirmation gate | M2.5 |
| FR-14 | M3 |
| FR-7 | M4 |
| FR-6, FR-8 | M5 |
| FR-10 | M6 |
| FR-13 | M7 |

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

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Split M2 exit into structural + identity-correct gates | CRP R1 | **ACCEPTED** → M2 now has two gates; (b) asserts the key vs `CONFLICT_COLUMNS` + a negative `*_display` fixture. No pass on structure alone. | 2026-07-08 |
| R1-S2 | Golden test asserts post-divergence normalized shape | CRP R1 | **ACCEPTED** → M2: the golden applies the 4 expected transforms (rename, Decimal, TEXT-not-enum, display-excluded key) before comparing. | 2026-07-08 |
| R1-S3 | E2E test: generated imports.yaml → importer dedups on identity | CRP R1 | **ACCEPTED** → M5: re-run backfill twice → 0 new rows (not just "parse_imports accepts"). | 2026-07-08 |
| R1-S4 | Schedule key-collapse guard + non-additive negative into M5 | CRP R1 | **ACCEPTED** → M5: colliding specimen → summed totals; gauge metric → assert NOT blindly summed. | 2026-07-08 |
| R1-S5 | Capture M0↔M2 family-fan-out dependency | CRP R1 | **ACCEPTED** → M0 now includes one-query-per-member + index-join; M2's FR-12 depends on that M0 *capability*. | 2026-07-08 |
| R1-S6 | Give the FR-4 confirmation gate a milestone home | CRP R1 | **ACCEPTED** → new **M2.5** (surface key vs golden, committed marker, re-confirm on change); traceability updated. | 2026-07-08 |
| R1-S7 | Public reserved-names accessor instead of importing private `_BOOKKEEPING` | CRP R1 | **ACCEPTED** → M2 uses a public emitter accessor (one-line seam); FR-11 updated to match. | 2026-07-08 |
| R1-S8 | Direct EntityGraph builder must replicate `extract_entities` invariants | CRP R1 | **ACCEPTED** → M2: enumerate + test the prose-path post-conditions (reserved-name checks, relation handling); FR-3 cross-refs. | 2026-07-08 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-08

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-08 14:48:00 UTC
- **Scope**: Plan review, weighted to the inference core M2 (FR-3/4/11/12) and its coupling to the reused back-half, per CRP_FOCUS. Settled framing not relitigated.

**Executive summary (top risks / gaps):**

- M2 is correctly flagged "THE RISK" but is a single milestone bundling six FRs; the load-bearing identity-inference sub-risk (FR-4) has no isolated exit gate separate from the rest of M2, so a weak key can pass hidden behind a green paper-diff.
- The golden test is described as "reproduces the DDL structure" but the paper-diff lists four *intended* divergences — the plan must state the golden asserts on the *normalized* shape (post-divergence), else the test can never pass.
- M3 (imports.yaml generator) depends on M2 but there is no plan step proving the generated manifest actually drives `generate backend` to emit an importer keyed on the inferred identity — M3's round-trip test stops at parse, not at end-to-end dedup.
- M2→M5 ordering (aggregation deferred to records-build) is stated but the plan has no guard test wiring FR-6 to run after FR-4 in the actual pipeline; the "colliding specimen → summed totals" test is mentioned in Risks but not scheduled into a milestone.
- FR-12 family grouping is inside M2 but the reader's N-query index-join (FR-1 coupling) is scheduled in M0 — the cross-milestone dependency (M0 reader must support family fan-out before M2 can group) is not captured in the dependency ordering.
- No milestone owns the FR-4 human-confirmation gate mechanism/persistence; it falls between M2 (infer) and M4 (gate) with no home.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | critical | Split M2's exit into **two gates**: (a) type/graph/collision correct (structural), and (b) **identity key correct** — the latter asserted against michigan `CONFLICT_COLUMNS` AND a negative fixture where a `*_display` column would be wrongly picked. Do not let M2 pass on structure alone. | The PLAN calls M2 "THE RISK" and names identity as the load-bearing failure, but its only stated validation is "the paper-diff → an executable golden test" which checks structure. A wrong key can reproduce the DDL *structure* while being semantically wrong. | M2 milestone, add explicit "Exit gates" bullet | Two golden assertions: structural DDL match; IdentityKey == CONFLICT_COLUMNS. Plus a negative fixture (display column present) asserting it is excluded. |
| R1-S2 | Validation | high | State that the golden test asserts on the **post-divergence normalized shape**, and enumerate the four verified divergences (source→dataSource rename, Decimal measure, TEXT-not-enum, display-excluded key) as *expected* transforms the golden applies before comparison. | The paper-diff section lists four intentional divergences from the golden DDL; a naive byte-diff against `20260313220000_michigan_budget_schema.sql` would always fail. The plan must say the test normalizes for these. | "Inference-taste (paper diff)" section, closing paragraph | Golden test includes a documented normalization map; a divergence not in the map fails the test (catches unplanned drift). |
| R1-S3 | Validation | high | Add an **end-to-end M3+M5 test** proving the generated `imports.yaml` makes `generate backend` emit an importer that dedups on the inferred identity — not just that `parse_imports` accepts it. Re-run backfill twice → assert 0 new rows. | M3's stated validation is "round-trip" (parse-level). CRP_FOCUS #2's real failure is a manifest that parses but yields `id`-dedup → infinite duplication. Only an end-to-end idempotency run catches it. | M3 milestone (or M5 dependency note) | `generate backend --imports <generated>` → run `from_json` twice on the same specimen → assert row count stable and dedup columns == inferred key. |
| R1-S4 | Risks | high | Schedule the **key-collapse guard test into M5 explicitly** (colliding specimen → assert summed measure totals, no last-writer-wins loss), and add a companion negative test for a **non-additive** measure (assert not blindly summed). Currently this lives only in "Risks #2", not in a milestone. | Risk #2 makes FR-6 non-optional due to silent loss, but the mitigation test is not scheduled. Unscheduled tests slip. The non-additive case (see requirements R1-F5) is unhandled. | M5 milestone bullets | Deliberately-colliding specimen; assert sum for `_amount`; assert last/avg+warning (not sum) for a gauge fixture. |
| R1-S5 | Architecture | medium | Capture the **M0↔M2 family-fan-out dependency**: FR-12 grouping (M2) requires the FR-1 reader (M0) to already support one-query-per-member + index-join. Either pull family read support forward into M0's scope or mark M2 as depending on an M0 capability, not just "M0 done". | The dependency table maps FR-1→M0 and FR-12→M2 independently, but FR-12 cannot function unless M0's reader emits per-member joinable results. The milestone ordering hides this coupling. | Milestones section, M0 and M2 dependency notes | Integration test: M2 family grouper consumes M0 multi-query output for a real `_amount`+`_count` family. |
| R1-S6 | Ops | medium | Give the **FR-4 human-confirmation gate a milestone home** (its mechanism, the confirmation artifact, and its persistence) — likely a new sub-step between M2 and M4, since M2 infers and M4 gates but neither currently owns "surface key next to golden + record confirmation". | OQ-4 mandates human confirmation before promotion, but no milestone builds the confirmation surface or its persisted marker. It falls through the M2/M4 seam. | Milestones, new "M2.5 — Identity confirmation" or M4 scope note | Test: promotion refused without a recorded confirmation; allowed with one; re-confirmation forced when the inferred key changes on re-promote. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S7 | Architecture | medium | Reconsider reading `prisma_emitter._BOOKKEEPING` at runtime from the inferrer (FR-11): the plan couples inference to a private module constant. Propose the emitter expose a **public "reserved names" accessor** (a one-line seam) so the guard has a supported contract instead of importing a private. | CRP_FOCUS #3 asks if runtime `_BOOKKEEPING` coupling is right. Importing a leading-underscore constant across module boundaries is a fragile contract; a public accessor is the low-effort fix and prevents the guard silently breaking on refactor. | M2 (FR-11 sub-task) note | Test the guard against the public accessor; add a contract test that the accessor and the emitter's actual injection set agree. |
| R1-S8 | Risks | medium | Add a plan note that building the `EntityGraph` **directly** (not via `extract_entities`) risks **missing invariants** the prose path enforces (e.g. relation back-population, reserved-name checks beyond bookkeeping). Enumerate which `extract_entities` post-conditions the direct builder must replicate, and test the direct graph against them. | CRP_FOCUS #3: bypassing `extract_entities` for `graph_from_prisma`-style construction may skip validation the prose path applies. The plan asserts "reused verbatim" for the emitter but the graph *builder* is new and unvalidated against those invariants. | M2, FR-3 sub-task | Contract test: feed the direct-built graph through the same invariant checks `extract_entities` output satisfies; assert parity. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):
- (none — this is Round R1; no prior untriaged suggestions exist.)

---

## Requirements Coverage Matrix — R1

Analysis only (reviewer observations to inform orchestrator triage; not a triage disposition).

| Requirement | Plan Milestone/Section | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (TSDB read-back seam) | M0; FR→Seam map (FR-1) | Partial | Empty-result detection present, but names-in-index-vs-absent distinction (R1-F6) and Grafana-proxy auth/401 handling (R1-F11) unspecified; family fan-out coupling to FR-12 not captured (R1-S5). |
| FR-2 (specimen materialization) | M1; FR→Seam map (FR-2) | Full | Raw-series storage + dry-run covered; cycle-guard on FR-4 input is a requirements clarification (R1-F9), not a plan gap. |
| FR-3 (column+type infer, direct graph) | M2; Inference-taste; FR→Seam map (FR-3) | Partial | Direct-graph invariant parity vs `extract_entities` unvalidated (R1-S8); measure-name collision rule missing (R1-F8); Decimal/enum-off decisions captured. |
| FR-4 (identity inference) | M2; Risks #1; Inference-taste | Partial | No isolated identity exit gate (R1-S1); deterministic tie-break undefined (R1-F1); display-column exclusion not required (R1-F2); confirmation gate has no milestone home (R1-S6/R1-F7); sample-vs-global uniqueness unaddressed. |
| FR-5 (cardinality reduction) | M2; FR→Seam map (FR-5) | Full | Auto top-N + warning + silent-cap guard test specified. |
| FR-6 (key-collapse aggregation) | M5; Risks #2; FR→Seam map (FR-6) | Partial | Guard test not scheduled into a milestone (R1-S4); summable-vs-non-additive measure rule missing (R1-F5). |
| FR-7 (gate + promote) | M4; FR→Seam map (FR-7) | Full | Greenfield gate (round-trip + non-empty + no-unrenderable) clearly reused. |
| FR-8 (generate + backfill) | M5; FR→Seam map (FR-8) | Full | Coercion-free backfill covered; end-to-end idempotency partly overlaps FR-14 (R1-S3). |
| FR-9 (grain honesty, two modes) | M1; FR→Seam map (FR-9) | Full | Fail-safe default to least-trusted grain specified. |
| FR-10 (CLI pipeline) | M6; FR→Seam map (FR-10) | Full | Thin orchestration over M0→M5. |
| FR-11 (bookkeeping-collision guard) | M2; Risks; FR→Seam map (FR-11) | Partial | Rename rule present but rename-collision case (`dataSource` already exists) unhandled (R1-F10); public reserved-names accessor proposed (R1-S7). |
| FR-12 (metric-family grouper) | M2; FR→Seam map (FR-12) | Partial | Mismatched/partial-overlap member label sets have no join semantics (R1-F4); M0 reader coupling not scheduled (R1-S5). |
| FR-13 (histogram → stats table) | M7; FR→Seam map (FR-13) | Partial | Isolated + droppable-last is good, but scope boundary (percentiles, `le`/bucket handling) undefined; candidate for explicit v1.1 defer. |
| FR-14 (imports.yaml generator) | M3; Risks #3; FR→Seam map (FR-14) | Partial | Round-trip stops at parse; no semantic-equality contract or end-to-end dedup proof (R1-F3/R1-S3). |
