# TSDB → Relational Maturation Requirements

**Version:** 0.5 (CRP R1 triaged — 11 F-suggestions accepted & merged)
**Date:** 2026-07-08
**Status:** Draft
**Pilot:** the `gov_*` Michigan budget data (reference implementation already exists — see §Reference)

---

## Reference (load-bearing context)

This feature **generalizes a working, proven converter** rather than inventing one. Two artifacts anchor
every requirement below:

- **Reference implementation** — `~/Documents/politics/government-observability/Michigan-budget-dashboard/scripts/export_to_supabase.py`.
  A hand-authored Mimir→Postgres ETL that already implements the read (`last_over_time(gov_*[3000d])`),
  the flatten (`extract_labels`/`extract_value` → `{labels…, "amount": value}`), and the idempotent
  upsert (`CONFLICT_COLUMNS` composite keys + `deduplicate_rows`). It is the *proof the runtime pattern
  works*; this feature replaces its per-table hand-authoring with inference.
- **Inference golden** — `…/Michigan-budget-dashboard/supabase/migrations/20260313220000_michigan_budget_schema.sql`.
  Hand-authored DDL: `id` PK + typed label columns + `amount NUMERIC` measure + `source` + `etl_updated_at`
  + a composite `UNIQUE`. The exact shape a schema-inference pass must emit; validated against it (an
  executable golden test, per the §0 planning pass).

**SDK back-half to reuse (do not rebuild):** `languages/prisma_parser.py` (`parse_prisma_schema` →
`PrismaSchema`), `manifest_extraction/` (`render_prisma_schema`, `emit_schema_draft`, `promote_schema`,
`graph_from_prisma`), `backend_codegen/identity.py` (`IdentityKey`), `backend_codegen/import_codegen.py`
(`from_json`, `_COERCE`), `backend_codegen/assembler.py` (`render_backend`).

---

## 0. Planning Insights (Self-Reflective Update)

> This section documents what changed between v0.1 (pre-planning) and v0.2. The planning pass read the
> actual SDK seams + the michigan reference (`file:line` in the PLAN) and produced a `department_budgets`
> inference paper-diff against the golden DDL. It surfaced **four verified corrections** and **four new
> required seams** — the v0.1 draft's "pure reuse" story for the back-half was mostly right, but had
> concrete holes.

| v0.1 assumption | Planning discovery (verified) | Impact |
|-----------------|-------------------------------|--------|
| FR-3 emits via the existing `manifest_extraction` `EntityGraph → render_prisma_schema` path | `render_prisma_schema(graph)` is **not** prose-coupled, but the usual builder `extract_entities` **is** (needs `## Entities` markdown). The decoupled precedent is **`graph_from_prisma`** (entities.py:544). | FR-3 must build the `EntityGraph` **directly** (the `graph_from_prisma` way), not via `extract_entities`. Emitter reused verbatim; graph-builder is new. |
| Inference adds bookkeeping (`id`, `source`, `observed_at`) | The emitter **auto-injects six** bookkeeping fields — `id/ownerId/source/confirmed/createdAt/updatedAt` (prisma_emitter.py:53). Adding them in the graph → **duplicate-field structural error**. | FR-3 must NOT author `id`/`source`. `observed_at` is the *only* added field. Golden's `etl_updated_at` maps to the emitter's `updatedAt`. **The gov `source` LABEL collides with the injected `source` → the gate refuses** → new FR-11. |
| FR-8 backfill is "pure reuse — no new writer" | The importer is emitted **only when `imports.yaml` is present** (assembler.py:148); `imports.yaml` is only ever *parsed* or *extracted from prose* (extractors.py:885). **No programmatic writer exists.** Without one, `generate backend` emits **no importer** and TSDB rows (no stable `id`) dedup by `id` → **infinite duplication**. | **A new `imports.yaml` generator is required** (FR-14) — the one build v0.1 fully omitted. |
| "Reuse `identity.py`, but it must be inferred" | `identity.py` has **zero inference** — `parse_declared_identity` "never invents a key" (:132). | FR-4 is genuinely new code; it only reuses the `IdentityKey` *dataclass* as its output type. |
| FR-6: without aggregation "the upsert fails (*ON CONFLICT cannot affect row a second time*)" | That is a **PostgREST/SQL** error (michigan's path). The SDK's generated importer `_import_row` (import_codegen.py:270) is **silent last-writer-wins** — colliding rows overwrite, no error. | FR-6's consequence on the SDK path is **silent data loss**, not a crash → aggregation is *more* critical, and there's no DB tripwire. Also: aggregation depends on the inferred identity, so it runs **after** FR-4 (the ladder is not linear — OQ-13). |
| Type round-tripping needs work (FR-8) | `_COERCE` (import_codegen.py:30-37) already coerces **Decimal/DateTime**/Int/Float/Bool from the stringified payload. | FR-8 DateTime/Decimal backfill is **free** — the specimen's stringified `observed_at`/`amount` round-trip with no new code. |
| FR-7 "round-trip + parity" gate | Parity is computed only when a `live_text` exists; a **greenfield** TSDB app has none → the gate is **round-trip + non-empty + no-unrenderable** (prisma_emitter.py:465). | FR-7 clarified: parity only bites on a **re-promote** (schema evolution). Empty-materialization must be refused (OQ-6). |
| One metric → one table | michigan merges `_amount` + `_count` into one table (two measures, shared identity — export_to_supabase.py:181). | With **OQ-1 = auto-detect** (locked), FR-12 (metric-family grouper) is required; it couples FR-1 (reader issues N queries + index-joins by identity) and FR-3. |

**Resolved open questions:**
- **OQ-1 → Auto-detect by shared identity** (user). Metrics sharing the inferred identity merge into one
  multi-measure table → **FR-12**.
- **OQ-2 → Resolved by the code.** The **measure is always the metric value**; **every label is a
  dimension** regardless of numeric-ness (`fiscal_year` is an integral *label*, not a measure). The
  numeric-label-vs-measure ambiguity does not arise — the value slot is unambiguous.
- **OQ-3 → Auto top-N + loud warning** (user). FR-5 default is automatic `topk` by the measure with a
  logged warning; explicit `--reduce` overrides; a **silent-cap guard test** is required (Kaizen "no
  silent caps").
- **OQ-5 → Support both backfill modes** (user). FR-9 = lossless-source *and* TSDB-snapshot, each row
  grain/provenance-labeled.
- **OQ-6 → Refuse empty materialization.** FR-1 detects an empty `result` (names-in-index/samples-pruned,
  which recon hit); FR-7 refuses to promote an empty-tabled schema.
- **OQ-7 → In scope: histograms → a stats table** (user). `_bucket`/`_sum`/`_count` → **FR-13** (a
  distinct inference path; the largest addition; its own milestone M7).
- **OQ-11 → In scope for this capability.** The `imports.yaml` generator (FR-14) ships here (the app has
  no programmatic manifest writers today; this is the first).
- **OQ-13 → The ladder is not linear.** The specimen (FR-2) stores **raw** series; key-collapse
  aggregation (FR-6) runs at records-build time **after** identity inference (FR-4).

**Resolved open questions (v0.4 — user, "proceed with recommendations"):**
- **OQ-4 → Infer + require confirmation.** The inferred identity key is surfaced next to the michigan
  `CONFLICT_COLUMNS` golden and MUST be human-confirmed at the gate before promotion (a wrong key silently
  overwrites on backfill). Applied to FR-4.
- **OQ-8 → Rename + preserve** (`<name>` → `data<Name>`, e.g. `source` → `dataSource`). Dropping loses
  michigan's `hfa_mi`/`sigma_mi` provenance. Applied to FR-11.
- **OQ-9 → Measure defaults to `Decimal`.** Financial fidelity; `_COERCE` round-trips Decimal for free.
  Applied to FR-3.
- **OQ-10 → Keep it very simple: enum synthesis is OFF by default.** All labels stay `String` (matches the
  golden's TEXT). This **dissolves the slug/display-desync risk entirely** — it cannot arise while enums
  are off. A **minimal opt-in** (`--enums`, per-field) exists for the rare future case; only *then* is the
  `x`/`x_display` pairing rule needed, and it is **deferred** until an opt-in caller appears. (Risk is
  mostly theoretical; build the seam, don't invest in it now.) Applied to FR-3.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK lessons base before CRP (cheap: reading, not reviewing). Each changed the draft:

- **[Phantom-reference audit]** — grep-verified every symbol the spec + PLAN name against its owning
  module (see Reference Audit below). **Correction:** the design-time coercion constant is **`_COERCE_TAG`**
  (import_codegen.py:30), distinct from the **generated** `_COERCE` dict baked into the emitted importer
  (import_codegen.py:188) — the docs now name the right one. All other named symbols exist; the four
  to-build seams are marked as such.
- **[#97 consumer-parity / single-source vocabulary ownership]** — FR-11's collision set MUST be read from
  the **canonical `prisma_emitter._BOOKKEEPING`** (verified 6 fields), never a hardcoded copy in the
  inferrer — else the guard silently drifts the moment the emitter gains a bookkeeping field. (The exact
  shape of #97: an inference/validator must use the EXACT known-set its consumer uses.) Applied to FR-11.
- **[#115 fail-safe default]** — FR-9's `grain` marker defaults to the **least-trusted** value
  (`tsdb_aggregate`) when unknown, never `import_source`: a dropped/missing grain must degrade fidelity
  claims, not inflate them. Applied to FR-9.
- **[Prune phantom scope — checked]** — no FR is architecturally wrong for this mechanism. FR-13
  (histograms) is the largest and is deliberately sequenced **last (M7)** so it can be dropped without
  unshipping the core. Recorded, not pruned (user chose it in-scope).
- **[CRP steering]** — both docs are brand-new (least-reviewed = everything); the CRP **target is the
  requirements** (the PLAN is derivative). **Settled / do-not-relitigate:** the generalize-not-greenfield
  framing; reuse of the SDK back-half (grep-verified); the michigan converter as reference + its DDL as
  golden; the resolved OQ-1/2/3/5/6/7/11/13 (§0). CRP should focus on the **inference core** (FR-3/4/11/12)
  and the four remaining OQs.

### Reference Audit

| Symbol / capability | Exists? | Path |
|---------------------|---------|------|
| `render_prisma_schema(graph)` | ✅ | `manifest_extraction/prisma_emitter.py:266` |
| `emit_schema_draft` / `promote_schema` | ✅ | `prisma_emitter.py:439` / `:490` |
| `graph_from_prisma` (direct `EntityGraph`, non-prose) | ✅ | `manifest_extraction/entities.py:544` |
| `_BOOKKEEPING` (collision set — id/ownerId/source/confirmed/createdAt/updatedAt) | ✅ | `prisma_emitter.py:53` |
| `IdentityKey` / `parse_declared_identity` / `resolve_identity` | ✅ | `backend_codegen/identity.py:33` / `:115` / `:173` |
| `render_import` (importer generator) | ✅ | `backend_codegen/import_codegen.py:137` |
| generated `from_json` (idempotent upsert) | ✅ (emitted string) | `import_codegen.py:142` |
| `_COERCE_TAG` (design-time) / `_COERCE` (generated runtime) | ✅ | `import_codegen.py:30` / `:188` |
| `parse_imports` (imports.yaml parser) | ✅ | `backend_codegen/imports_manifest.py:59` |
| `extract_imports` (**prose-only** — confirms no programmatic writer) | ✅ | `manifest_extraction/extractors.py:879` |
| `render_backend` | ✅ | `backend_codegen/assembler.py:46` |
| TSDB reader (`last_over_time` / PromQL client) | ❌ **to-build** | — (FR-1 greenfield) |
| type inference from sampled values | ❌ **to-build** | — (FR-3, the novelty) |
| identity inference | ❌ **to-build** | — (FR-4) |
| `imports.yaml` programmatic **writer** | ❌ **to-build** | — (FR-14 — the hidden dep) |

---

## 1. Problem Statement

A time-series database (Prometheus/Mimir) is the right **proving ground** during the ideation stage of a
data product: schema-last, write-cheap, add-a-label-and-move-on. But it is structurally the *wrong*
system-of-record for a mature product — no update/delete/primary-key CRUD, it downsamples, and it
retention-prunes. (Recon 2026-07-08 confirmed the sharpest form: the `gov_*` metric *names* survive in
the Mimir index while the *samples* are pruned — the index remembers the shape long after the rows are
gone.)

There is a well-understood, already-*practiced* maturation path — TSDB → relational database — but today
it is **hand-authored per project** (michigan: ~8 exporter functions + hand DDL + hand conflict-map + a
hand-wired React/Supabase frontend). The SDK already ships the entire deterministic **back-half** that
generates the relational app for **$0**; what it lacks is the **front-half** that turns observed telemetry
into a `schema.prisma` contract.

| Component | Current State (michigan reference) | Gap for a general SDK capability |
|-----------|-----------------------------------|----------------------------------|
| Read TSDB back | `last_over_time([3000d])` (hand-written, gov PromQL) | No SDK read-back seam (`prometheus_client` is import-excluded) → FR-1 greenfield |
| Flatten to records | `extract_labels`/`extract_value` (hand-written per table) | No SDK specimen-materialization → FR-2 |
| **Infer the schema** | **None — DDL + label lists + keys all hand-authored** | **The real build (FR-3/4/11/12): labels→columns+types, value→measure, identity subset→key** |
| Identity / dedup | `CONFLICT_COLUMNS` (hand-declared) | Reuse `IdentityKey`, but *infer* it (FR-4) |
| Key-collapse aggregation | `deduplicate_rows` + `AGGREGATE_COLUMNS` | SDK importer has no sum-on-collision → **silent loss** → FR-6 |
| Carry identity to the importer | (implicit in the hand DDL) | No `imports.yaml` writer → FR-14 |
| Generate the app | hand-wired React + Supabase DDL | Reuse `generate backend` ($0) |
| Backfill rows | PostgREST upsert | Reuse `from_json` (Decimal/DateTime coercion free) |

**The maturation ladder** (rungs the SDK must own; note the non-linearity from OQ-13):

```
0. EMIT        experiment → OTel metrics (+ lossless source)      [exists]
1. OBSERVE     read the TSDB via last_over_time[huge]             [BUILD — FR-1]
2. SPECIMEN    flatten series → durable RAW records file          [BUILD — FR-2]
3. INFER       samples → columns+types + identity + families      [BUILD — FR-3/4/5/11/12/13, the core]
   └─ aggregate (FR-6) runs HERE, after identity is known ─┐
4. GATE        round-trip + non-empty + derivability → schema     [REUSE — FR-7]
5. GENERATE    schema.prisma → SQLModel app (+ imports.yaml)      [REUSE + FR-14]
6. BACKFILL    records → from_json (idempotent, coercion free)    [REUSE — FR-8]
```

---

## 2. Requirements

### Read + materialize (rungs 1–2)

- **FR-1 — TSDB read-back seam.** A bounded reader querying a Prometheus/Mimir-compatible endpoint for a
  metric (or family) via `last_over_time(<metric>[<lookback>])`; returns label-sets + latest value.
  Endpoint configurable (a Grafana datasource proxy **with auth** *or* a direct Mimir URL); `httpx` (dep,
  no `prometheus_client` revival). Lookback defaults wide (past staleness, michigan `3000d`). **Detects an
  empty result** and reports it, never silently yielding an empty specimen — **distinguishing two causes**
  (R1-F6): *names-in-index but samples-pruned* → the honest empty-materialization **refuse** (OQ-6), vs
  *metric genuinely absent from the index* → a distinct config/typo error message. **Auth** (R1-F11): a
  Grafana-proxy token/header comes from **env/secrets, never a CLI flag**; a `401`/`403` is a **distinct
  auth-error exit**, never the empty-result path (so an auth failure cannot masquerade as an empty refuse).
  For a metric family (FR-12) it issues one query per member and index-joins by identity.
- **FR-2 — Specimen materialization.** Flatten queried series to a **durable specimen file** (JSON): one
  record per series `{<label>:…, "value": <float>, "observed_at": <iso8601>}`, storing **raw** series
  (aggregation is deferred to FR-6, which needs the inferred identity — OQ-13). `--dry-run` reports counts
  + a sample and writes only the specimen.

### Infer the schema (rung 3 — the core build)

- **FR-3 — Column + type inference + direct graph construction.** From a specimen: each **label → a
  column**, typed by inspecting values — all-integral → `Int`, any-decimal → **`Decimal`** (financial
  fidelity; `_COERCE` round-trips it free — OQ-9), ISO-8601 → `DateTime`, else `String`. **Labels stay
  `String` by default — enum synthesis is OFF** (§0/OQ-10); a minimal `--enums` opt-in exists but the
  slug/display-pairing rule is deferred until a caller uses it. The metric **value → a `Decimal` measure
  column**, named from the metric (`gov_expenditure_amount` → `amount`). **Measure-name collisions**
  (R1-F8) are disambiguated deterministically — two metrics stripping to the same measure name, or a
  stripped name colliding with a label column (a label already named `amount`), get distinct suffixed
  names. Build the `EntityGraph` **directly** (the `graph_from_prisma` pattern), **not** via the
  prose-coupled `extract_entities`; the direct builder MUST replicate `extract_entities`' load-bearing
  post-conditions (reserved-name checks, relation handling — enumerated in the PLAN, R1-S8). **Do NOT
  author bookkeeping** (`id`/`ownerId`/`source`/`confirmed`/`createdAt`/`updatedAt`) — the emitter injects
  them; `observed_at` is the only added field. Emit through `render_prisma_schema` verbatim.
- **FR-4 — Identity inference.** Infer the **minimal label subset unique per series** → a composite
  `IdentityKey` (reuse the dataclass). A declared `--identity a,b,c` always wins.
  - **Deterministic tie-break (R1-F1):** "minimal" = **fewest columns** (not fewest characters); when
    several equally-minimal subsets exist, pick — in order — (1) the subset matching michigan
    `CONFLICT_COLUMNS` if a golden is supplied, else (2) lexicographic label order. Same specimen → same
    key, byte-identical, so the golden test cannot flap.
  - **Exclude functionally-dependent display columns (R1-F2):** a `x_display` column, or any `x`
    determined by a sibling slug column, is a **dimension only — never eligible for the key**. This
    prevents a display column from making a *wrong* subset appear unique.
  - **Raw-specimen input only (R1-F9):** identity is inferred from the **raw, pre-aggregation** specimen
    (record count == series count); feeding an already-aggregated specimen to FR-4 raises. This pins the
    ordering (specimen → identity → aggregate) so no cycle can form.
  - **Sample-uniqueness caveat:** uniqueness is observed *in the sampled series* and is not proof of
    uniqueness across all series or over time — hence the confirmation gate below is load-bearing, not
    cosmetic.
  - **Confirmation artifact (R1-F7):** the inferred key MUST be **surfaced next to the golden diff** and
    **human-confirmed at the gate before promotion** (§0/OQ-4); the confirmation is **recorded as a
    committed marker** (the kickoff `confirmed.yaml` pattern) so it can gate; a **re-promote whose inferred
    key changed requires re-confirmation**. A wrong key silently overwrites on backfill (no runtime
    tripwire).
- **FR-5 — Cardinality reduction policy.** Above a cardinality ceiling, **auto-apply `top-N` by the
  measure with a loud, logged warning** of what was dropped (OQ-3); an explicit `--reduce` (`top-N` /
  `sum by (<labels>)`, michigan's proven forms) overrides. A **silent-cap guard test** ensures the
  warning is not the only signal.
- **FR-6 — Key-collapse aggregation (mandatory, post-identity).** When reduction/identity projects
  **multiple series onto one identity key**, aggregate the measure at records-build time — **after** FR-4.
  On the SDK path the failure mode is **silent last-writer-wins data loss** (no DB tripwire), so this is
  non-optional. (Ports `deduplicate_rows`/`AGGREGATE_COLUMNS`.) **The aggregation function binds to metric
  semantics (R1-F5)** — summing is only valid for **additive** measures: a counter / `_amount` / `_sum`
  family → `sum`; a **gauge, ratio, or `_display`-derived measure → `last`/`avg` with a warning**, or
  require an explicit `--aggregate`. Blindly summing a non-additive measure is as wrong as overwriting it.
- **FR-11 — Bookkeeping-collision guard (hard gate).** Any label whose name collides with an injected
  bookkeeping field MUST be **renamed with its value preserved** (e.g. `source` → `dataSource`) before
  graph construction — **verified**: the gov `source` label otherwise triggers a duplicate-field error and
  the gate refuses. Dropping is not acceptable (loses michigan's per-row `hfa_mi`/`sigma_mi` provenance).
  The collision set MUST be read from the canonical reserved-names set (a **public accessor** the emitter
  exposes over `_BOOKKEEPING` — R1-S7 — not the private constant), so the guard cannot drift when a
  bookkeeping field is added (consumer-parity, §0.1). **The rename is itself collision-checked (R1-F10):**
  if the target name (`dataSource`) already exists as a label, or the rename re-collides with another
  reserved name, **fail loudly** (second-level disambiguation), never silently clobber or double-rename.
- **FR-12 — Metric-family grouper (auto-detect).** Metrics sharing the same inferred identity/label set
  merge into **one table with one measure column per metric** (the `_amount`/`_count`/`_sum` family). The
  reader (FR-1) issues one query per member; records are index-joined by identity (michigan `count_index`).
  **Member alignment (R1-F4):** the family identity is the **shared** label set; every member MUST project
  onto it, and a family whose members **disagree on the shared identity is rejected** (not silently
  merged). When a series exists in one member but not another, the missing measure is **`NULL` with the
  row preserved** (outer-join semantics) **and a warning logged** — never an inner-join that drops rows or
  a silent fabrication. (Inner vs outer join changes totals; the choice is specified, not left to chance.)
- **FR-13 — Histogram → stats table.** Detect `_bucket`/`_sum`/`_count` (native OTel histogram) families
  and materialize a **percentile/stats table** — a distinct inference path from the gauge/measure path.
  (In scope per OQ-7; the largest addition; sequenced last, M7.)

### Gate + generate + backfill (rungs 4–6 — reuse)

- **FR-7 — Gate + promote.** Validate the inferred graph through `emit_schema_draft` → `promote_schema`.
  For the **greenfield** case the gate is **round-trip + non-empty + no-unrenderable** (parity applies only
  on a re-promote / schema evolution). An un-typeable label → `UnrenderableField` (never silently
  dropped); an empty materialization → **refuse** (OQ-6). Promotion flips `prisma/schema.prisma` only on
  pass.
- **FR-8 — Generate + backfill.** `generate backend` off the promoted schema ($0); ingest the specimen
  records via generated `from_json` with the inferred `identity:` (idempotent — re-run upserts, never
  duplicates). DateTime/Decimal coercion is **free** (`_COERCE`).
- **FR-14 — `imports.yaml` generator (required).** Serialize the inferred `IdentityKey` (+ per-field
  coercion tags) into an `imports.yaml` that `parse_imports` accepts, so `generate backend` emits the
  importer **with the correct identity**. Without this, no importer is emitted and rows dedup by `id` →
  infinite duplication. (First programmatic manifest writer in the SDK — OQ-11.) **Round-trip contract
  (R1-F3):** `parse_imports(generate(IdentityKey))` MUST be **semantically equal** to the inferred key —
  same `kind` + **ordered** columns + coercion tags — not merely "parses". A manifest that parses but
  dedups on different columns/order is a **failure** (it silently re-introduces duplication); the
  acceptance test asserts semantic equality *and* that the emitted importer dedups on those exact columns.
- **FR-9 — Backfill source (two modes, grain-honest).** Support **(a)** lossless-source import and **(b)**
  TSDB-snapshot; each row's **grain/provenance is labeled** (a `source`/`dataSource` column + a `grain`
  marker: `import_source` vs `tsdb_aggregate`). Mode (b) MUST NOT be presented as faithful per-event data.
  An **unknown/missing `grain` defaults to the least-trusted value (`tsdb_aggregate`)**, never
  `import_source` — a dropped marker must degrade fidelity claims, not inflate them (fail-safe, §0.1).

### Surface

- **FR-10 — CLI pipeline.** `startd8 promote tsdb <metric-or-family>` (working name) wiring FR-1→FR-8,
  modeled on `generate contract`. `--dry-run` first (specimen only, no promote/generate). `--lookback`,
  `--reduce`, `--identity`, `--endpoint` options.

---

## 3. Non-Requirements

- **NR-1 — Not rebuilding the deterministic back-half.** `prisma_parser`, `render_prisma_schema`,
  `identity`, `import_codegen`, `assembler` are reused, not reimplemented.
- **NR-2 — Not the michigan frontend.** The SDK emits its own $0 FastAPI+SQLModel+HTMX app; React/Supabase
  is out of scope.
- **NR-3 — TSDB is not a system-of-record.** No write-back / no CRUD of metrics. The read is one-way.
- **NR-4 — Not raw per-event materialization by default.** Aggregate/rollup grain with a reduction policy;
  per-event ingestion is a separate opt-in.
- **NR-5 — Not Postgres/Supabase-specific.** Target the SDK's SQLModel path (SQLite/PG), not PostgREST.
- **NR-6 — Not a general PromQL builder / not reimplementing Grafana.** A bounded `last_over_time` read.
- **NR-7 — Not an autonomous "promote on a schedule" pipeline.** Promotion is human-gated (rung 4).

---

## 4. Open Questions

**None remaining.** OQ-1/2/3/5/6/7/11/13 resolved in §0; OQ-4/8/9/10 resolved in §0 (v0.4). The one
deliberately-deferred item is the enum slug/display-pairing rule (OQ-10), which cannot arise while enum
synthesis is off by default — to be specified only when a `--enums` caller appears.

---

*v0.5 — CRP R1 triaged: all 11 F-suggestions ACCEPTED and merged (dispositions in Appendix A). Sharpened
the inference core — FR-4 gained a deterministic tie-break (F1), display-column exclusion (F2), raw-specimen
input pin (F9), and a persisted confirmation artifact (F7); FR-6 binds aggregation to metric additivity
(F5); FR-12 specifies member-alignment/outer-join (F4); FR-14 gained a semantic round-trip contract (F3);
FR-1 splits pruned-vs-absent + auth-401 (F6/F11); FR-11 collision-checks its own rename (F10); FR-3 adds a
measure-name collision rule (F8). No rejections. Ready for build (or an optional adversarial R2).*

*v0.4 — All open questions resolved. OQ-4 (infer + confirm at gate), OQ-8 (rename+preserve), OQ-9 (measure
→ Decimal), OQ-10 (enums OFF by default — labels stay String, slug/display risk dissolved; minimal opt-in
seam, pairing deferred). Carries the v0.3 lessons hardening + v0.2 planning update (11 FRs total, 12 OQs
resolved, 0 remaining). The michigan converter (reference) + its DDL (golden) make this
generalize-and-validate, not greenfield.*

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
| R1-F1 | Deterministic tie-break for minimal-unique subset | CRP R1 | **ACCEPTED** → FR-4 bullet 1: "minimal" = fewest columns; ties → match `CONFLICT_COLUMNS` if golden supplied, else lexicographic. Test: same specimen → byte-identical key. | 2026-07-08 |
| R1-F2 | Exclude functionally-dependent display columns from the key | CRP R1 | **ACCEPTED** → FR-4 bullet 2: `x_display` / slug-determined columns are dimensions, never key-eligible. | 2026-07-08 |
| R1-F3 | imports.yaml semantic round-trip contract (not just "parses") | CRP R1 | **ACCEPTED** → FR-14: `parse_imports(generate(key)) ==` key on kind+ordered-cols+coerce; importer must dedup on those exact cols. | 2026-07-08 |
| R1-F4 | FR-12 member-alignment / join semantics | CRP R1 | **ACCEPTED** → FR-12: shared-identity projection; outer-join (missing measure = NULL, row kept, warn); reject disagreeing families. | 2026-07-08 |
| R1-F5 | Bind aggregation function to metric additivity | CRP R1 | **ACCEPTED** → FR-6: additive (`_amount`/counter) → sum; gauge/ratio → last/avg+warn or explicit `--aggregate`. | 2026-07-08 |
| R1-F6 | Distinguish pruned-samples vs genuinely-absent metric | CRP R1 | **ACCEPTED** → FR-1: pruned → refuse (OQ-6); absent-from-index → distinct config/typo error. | 2026-07-08 |
| R1-F7 | Define the confirmation artifact + re-confirm-on-change | CRP R1 | **ACCEPTED** → FR-4 confirmation bullet: surface key-vs-golden diff, record a committed marker (kickoff `confirmed.yaml` pattern), re-promote re-confirms if key changed. | 2026-07-08 |
| R1-F8 | Measure-name collision rule | CRP R1 | **ACCEPTED** → FR-3: deterministic disambiguation when two metrics strip to the same name or collide with a label. | 2026-07-08 |
| R1-F9 | Pin FR-4 to read the raw pre-aggregation specimen (no cycle) | CRP R1 | **ACCEPTED** → FR-4 bullet 3: input = raw specimen (record count == series count); aggregated specimen raises. | 2026-07-08 |
| R1-F10 | Rename (`source→dataSource`) must be collision-checked | CRP R1 | **ACCEPTED** → FR-11: fail loudly if target name taken or re-collides; no silent clobber/double-rename. | 2026-07-08 |
| R1-F11 | Specify Grafana-proxy auth + 401 handling | CRP R1 | **ACCEPTED** → FR-1: token/header from env/secrets (not flags); 401/403 = distinct auth-error exit, never empty-result path. | 2026-07-08 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-08

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-08 14:48:00 UTC
- **Scope**: Requirements review, weighted to the inference core (FR-3/4/11/12) per CRP_FOCUS. Settled items (generalize-not-greenfield, back-half reuse, OQ-1..13) not relitigated.

**Executive summary (top risks / gaps):**

- FR-4's "minimal label subset unique per series" is under-defined as an algorithm: "minimal" is ambiguous (fewest columns? fewest characters? first-found?) and multiple minimal-unique subsets can coexist — the spec must pin a deterministic tie-break, or inference is non-reproducible and the golden test flaps.
- FR-4 relies on uniqueness observed *in the specimen sample*, but a subset unique across sampled series is not proven unique across all series or over time — a coincidentally-unique subset becomes a wrong dedup key with no runtime tripwire (FR-6 aggregates it away silently).
- FR-3's `*_display` hazard from CRP_FOCUS #1 is acknowledged in the PLAN paper-diff but has **no requirement**: nothing tells inference to exclude display-looking columns from the identity search, so a functionally-dependent display column can make a wrong subset appear unique.
- FR-14 (imports.yaml writer) has no stated round-trip contract or acceptance test — "`parse_imports` accepts" is necessary but not sufficient; the generated manifest must also reproduce the *inferred* IdentityKey semantically, not just parse.
- FR-12 metric-family grouping is defined only for the happy path (shared identity). Mismatched/partially-overlapping label sets across `_amount`/`_count` (a key present in one metric, absent in another) has no specified behavior — inner vs outer join changes row counts and can fabricate or drop measures.
- FR-6 aggregation default (`sum`) is asserted but the per-measure aggregation function is not bound to metric semantics: summing a gauge/`_display`/ratio is wrong. FR-6 needs a rule for which measures are summable.
- FR-1's empty-result detection conflates two distinct failures (names-in-index-but-samples-pruned vs. genuinely-absent metric); only the former should be a hard refuse — the spec should distinguish them.
- FR-13 histogram path lacks a scope boundary (which percentiles? bucket-boundary inference? `le` label handling) — as the largest speculative add it needs either a tighter contract or an explicit "defer to v1.1" gate.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | critical | In FR-4, specify a **deterministic tie-break** when multiple minimal-unique label subsets exist (e.g. "smallest subset; ties broken by matching michigan `CONFLICT_COLUMNS` if present, else lexicographic label order"). State that "minimal" = fewest columns, not fewest characters. | "Infer the minimal label subset unique per series" (FR-4) admits several equally-minimal answers; without a tie-break, inference is non-deterministic and the golden test is non-reproducible run-to-run. | FR-4, after the first sentence | Golden test: same specimen twice → byte-identical IdentityKey; add a fixture with two minimal-unique subsets and assert the documented winner. |
| R1-F2 | Data | high | Add an explicit rule to FR-3/FR-4 to **exclude functionally-dependent display columns** from the identity search: a column `x_display` (or `x` where a sibling slug column determines it) is a dimension, never eligible for the key. | CRP_FOCUS #1's known hazard: a `*_display` column functionally dependent on a slug can make a *wrong* subset appear unique. The paper-diff notes it (`fund_source`/`fund_source_display`) but no FR forbids it entering the key. | New sentence in FR-4 (identity search constraints) cross-referenced from FR-3 | Fixture with `fund_source` + `fund_source_display`: assert the inferred key contains the slug and excludes `_display`; assert key matches `CONFLICT_COLUMNS`. |
| R1-F3 | Interfaces | high | FR-14 must state a **round-trip contract**: `parse_imports(generate_imports(IdentityKey)) == IdentityKey` (semantic equality on kind + ordered columns + coercion tags), not merely "parse_imports accepts". Name the equality and the failure behavior if the writer emits a key `parse_imports` accepts but that dedups differently. | CRP_FOCUS #2: the risk is the generated manifest *parses* but drifts from the inferred key (wrong column order / coercion), silently re-introducing duplication. "Accepts" does not catch semantic drift. | FR-14, second sentence | Property test: for N sampled IdentityKeys (composite/simple, with coercion tags), assert generate→parse→generate is a fixed point and the resulting importer dedups on the same columns. |
| R1-F4 | Data | high | FR-12 must specify **join semantics for mismatched member label sets**: define the family's identity as the *shared* label set, require every member to project onto it, and specify behavior when a series exists in one metric but not another (measure = NULL vs. row dropped). Reject families whose members disagree on the shared identity. | CRP_FOCUS #5: `_amount` and `_count` can have partially-overlapping series; inner-join drops rows, outer-join fabricates NULL measures — either silently corrupts totals. Currently only the aligned case is specified. | FR-12, add "Member alignment" paragraph | Fixture: `_amount` with series {A,B}, `_count` with {A,C}; assert documented outcome (e.g. B.count=NULL, C.amount=NULL, no row loss) and a warning is logged. |
| R1-F5 | Data | high | FR-6 must define **which measures are summable**. Default `sum` is only valid for additive measures; a gauge, ratio, or coerced `_display`-derived measure must not be summed. Bind the aggregation function to metric type (counter/`_amount` → sum; gauge → last/avg with a warning) or require explicit `--aggregate`. | CRP_FOCUS #4 warns the failure is silent data loss. Blindly summing on collision is as wrong as overwriting when the measure is non-additive; the spec asserts `sum` default without qualifying it. | FR-6, after "default `sum`; configurable" | Guard test: colliding specimen of a gauge metric → assert NOT summed (or summed-with-warning per policy); colliding `_amount` → assert summed totals. |
| R1-F6 | Risks | medium | FR-1 should **distinguish "names-in-index, samples-pruned" from "metric genuinely absent"** and specify different handling: the former is the honest empty-materialization refuse (OQ-6); the latter is arguably a config/typo error worth a distinct message. | "Detects an empty result (names-in-index/samples-pruned)" (FR-1) bundles two causes with one behavior; an operator debugging a typo'd metric name gets the same signal as one hitting retention. | FR-1, empty-result sentence | Two fixtures (index-hit/samples-empty vs. no-index-entry); assert distinct exit codes/messages; assert both refuse promotion. |
| R1-F7 | Validation | medium | FR-4's "human-confirmed at the gate" (OQ-4) needs an **acceptance criterion for the confirmation artifact**: what is shown (inferred key vs. golden diff), how confirmation is recorded (a committed marker, à la the kickoff `confirmed.yaml` pattern), and whether re-promote requires re-confirmation if the key changed. | "MUST be human-confirmed" is untestable without defining the confirmation mechanism and its persistence. An un-persisted confirmation cannot gate a re-promote. | FR-4, confirmation clause | Test: promote without confirmation → refused; with a recorded confirmation for key K → allowed; re-promote after K changes → re-confirmation required. |
| R1-F8 | Data | medium | FR-3 measure-naming (`gov_expenditure_amount` → `amount`) needs a **collision rule** for metric families: two metrics stripping to the same measure name (or a stripped name colliding with a label column) must be disambiguated deterministically. | FR-12 puts multiple measures in one table; naive suffix-stripping can collide (`_amount` and a label already named `amount`), and FR-3 gives no rule. | FR-3, measure-naming sentence | Fixture with a label `amount` + metric `*_amount`; assert distinct, deterministic column names. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F9 | Risks | high | State FR-4's **hidden-cycle guard explicitly**: the specimen (FR-2) stores raw series, identity (FR-4) is inferred from that raw specimen, aggregation (FR-6) needs identity — assert in the requirement that identity inference reads ONLY the raw pre-aggregation specimen, so no cycle (specimen→identity→aggregate→specimen) can form. | CRP_FOCUS #4 asks whether a hidden cycle exists. OQ-13 resolves ordering in prose, but no FR *pins* that FR-4 consumes the raw specimen; a future edit that aggregates before inferring identity would silently deadlock/mis-key. | FR-4 (input contract) and/or FR-2 | Test: assert FR-4's input is the raw specimen file (record count == series count, un-collapsed); an aggregated specimen fed to FR-4 raises. |
| R1-F10 | Data | medium | FR-11 rename `source → dataSource` (OQ-8) can itself **collide** if a `dataSource` label already exists, or produce a name that re-collides with a future bookkeeping field. Specify the rename is collision-checked and fails loudly rather than silently double-renaming. | The rename rule is stated as a fixed transform; it has no guard against the transformed name already being taken, which would re-trigger duplicate-field or silently shadow. | FR-11, rename clause | Fixture with both `source` and `dataSource` labels → assert loud failure / second-level disambiguation, not a silent clobber. |
| R1-F11 | Ops | medium | FR-1 Grafana-proxy **auth** is named but unspecified: state the auth mechanism (token/header/service-account), that credentials come from env/secrets (not flags), and the failure mode on 401/403 (distinct from empty-result). | "a Grafana datasource proxy with auth" (FR-1) is the only auth mention; without specifying credential source and 401 handling, an auth failure could masquerade as an empty result and trigger a wrong refuse. | FR-1, endpoint sentence | Test: 401 from proxy → distinct auth-error exit, never the empty-materialization path. |
