# TSDB → Relational Maturation — Next Steps

**Date:** 2026-07-08
**Owner docs:** `TSDB_TO_RELATIONAL_MATURATION_REQUIREMENTS.md` (v0.4), `…_PLAN.md` (v1.0). This file is
the running to-do; the FR/AC detail lives in those specs.

**One-line:** turn observed time-series metrics into a generated relational app by **inferring a
`schema.prisma`** from the metric label structure, then reusing the SDK's shipped `$0` back-half
(`generate backend` + importer). The michigan converter (`export_to_supabase.py`) is the proven
**reference**; its hand DDL is the **golden** the inference is tested against.

---

## Where we are

| Stage | State |
|---|---|
| Recon spike (rungs 1→2 proven; gov data confirmed TSDB-pruned; michigan reference located) | ✅ done |
| Reflective-requirements loop (draft → plan → reflect → harden → OQs resolved) | ✅ **v0.5**, plan v1.1 |
| Every named seam grep-verified (Reference Audit) | ✅ |
| **CRP (Phase 5)** — R1 run + triaged (19 suggestions, all accepted & merged) | ✅ done |
| **Any code** | ⛔ **not started — design only** |

**Nothing is built.** This is a fully-specced, un-implemented capability.

---

## Decisions locked (don't relitigate)

- **Generalize, not greenfield.** Reuse `render_prisma_schema` / `emit_schema_draft` / `promote_schema` /
  `generate backend` / `from_json` / `identity.py` verbatim; build only the front-half (inference).
- **OQ-1** metric families auto-merge by shared identity → multi-measure tables (FR-12).
- **OQ-3** high cardinality → auto `top-N` + loud warning (+ silent-cap guard test).
- **OQ-4** inferred identity key → **human-confirmed at the gate** before promote.
- **OQ-5** two backfill modes (lossless-source **and** TSDB-snapshot), grain-labeled; unknown grain →
  least-trusted default.
- **OQ-7** histograms in scope → a stats table (FR-13, sequenced last).
- **OQ-8** bookkeeping collision → **rename+preserve** (`source`→`dataSource`).
- **OQ-9** measure column → **`Decimal`**.
- **OQ-10** **enums OFF by default** — labels stay `String` (matches golden TEXT; slug/display risk
  dissolved). Minimal `--enums` opt-in seam only; pairing rule deferred until a caller needs it.

---

## Build roadmap (from PLAN §5)

Risk is entirely in **M2 (inference)**; M4/M5 are reuse; M0/M1 are proven-pattern ports; M3/M7 are the two
genuinely-new writers.

- [ ] **M0 — TSDB reader (FR-1).** New `tsdb_maturation/reader.py`: `httpx` instant query +
      `last_over_time(<m>[<lookback>])` + endpoint config (Grafana proxy **with auth** / direct Mimir) +
      **empty-result detection** (OQ-6). *Validate vs a recorded fixture or a live/local Mimir.* — **reuse
      the recon scripts in `/tmp/tsdb_*.py` as the starting shape.**
- [ ] **M1 — Specimen (FR-2, FR-9).** `specimen.py`: `flatten_series` → durable **raw** JSON + `--dry-run`
      + `grain` metadata. (Aggregation deferred to M2/M5 — it needs the identity.)
- [ ] **M2 — Inference core (FR-3/4/5/11/12) — THE RISK.** `_infer_scalar_type(values)` (measure→Decimal,
      labels→String, enums OFF), **direct `EntityGraph`** (the `graph_from_prisma` pattern — NOT
      `extract_entities`), `infer_identity` → composite `IdentityKey`, **bookkeeping-collision rename**
      (via a **public emitter reserved-names accessor**, R1-S7), reduction policy, family grouper
      (member-alignment/outer-join). **Two-gate exit (R1-S1):** structural AND identity-correct (key vs
      `CONFLICT_COLUMNS` + a negative `*_display` fixture) — don't pass on structure alone. Golden test
      applies the 4 expected transforms before comparing (R1-S2); replicate `extract_entities` invariants
      (R1-S8). Validated against `20260313220000_michigan_budget_schema.sql`.
- [ ] **M2.5 — Confirmation gate (FR-4, R1-S6).** Surface the inferred key next to the golden diff; record
      a **committed confirmation marker** (kickoff `confirmed.yaml` pattern); re-promote re-confirms if the
      key changed. Small new milestone between infer (M2) and gate (M4).
- [ ] **M3 — `imports.yaml` generator (FR-14).** Serialize the inferred `IdentityKey` (+ coerce tags) into
      an `imports.yaml` that `parse_imports` accepts round-trip. *Without this, `generate backend` emits no
      importer → `id`-dedup → infinite duplication.* First programmatic manifest writer in the SDK.
- [ ] **M4 — Gate wiring (FR-7).** Reuse `emit_schema_draft`→`promote_schema` on the M2 graph; surface the
      inferred identity next to the golden for **confirmation** (OQ-4); refuse empty/unrenderable.
- [ ] **M5 — Backend + backfill (FR-6, FR-8).** `generate backend --imports <generated>` + `from_json`;
      records-build **aggregation** (post-identity; **bound to metric additivity** — gauge≠sum, R1-F5).
      **E2E dedup test (R1-S3):** generated `imports.yaml` → importer dedups on the inferred identity,
      re-run twice → **0 new rows**. **Key-collapse guard + non-additive negative (R1-S4).** Decimal/
      DateTime coercion is free (`_COERCE`).
- [ ] **M6 — CLI (FR-10).** `startd8 promote tsdb <metric>` orchestrating M0→M5, modeled on `generate
      contract`. `--dry-run` / `--lookback` / `--reduce` / `--identity` / `--endpoint`.
- [ ] **M7 — Histograms (FR-13).** `_bucket`/`_sum`/`_count` → a percentile/stats table. Isolated + last so
      it can be dropped without unshipping the core.

**Recommended first move:** M0 → M1 → **M2 with the golden test up front** (write the
`department_budgets` assertion *before* the inference code, so rung 3 is red-green against real DDL). M3
must land before M5 (the importer depends on it).

---

## The load-bearing test

`test_inference_reproduces_golden`: feed a specimen built from michigan's `export_department_budgets`
label list → assert the inferred `schema.prisma` model matches the golden `department_budgets` DDL on:
(a) the **5-column composite** `@@unique(department, fiscalYear, budgetStatus, fundSource,
dataCompleteness)` — *without* pulling in a `*_display` column; (b) `amount` = `Decimal` measure; (c)
`fiscalYear` = `Int` dimension; (d) the `source` label renamed to `dataSource` (no bookkeeping collision).
This single test is the empirical proof of rung 3.

---

## Cross-cutting / dependencies

- **CRP (Phase 5) not yet run.** The docs are hardened + OQ-clean. CRP target = the requirements; focus =
  the inference core (FR-3/4/11/12). Offered; run before M2 if desired (the inference is the part most
  worth an external read).
- **The gov data is not in `o11y-dev` Mimir** (retention-pruned; recon confirmed 0 samples). M0/M2
  validation should use **a recorded specimen fixture** (or re-push from the michigan CSVs into a local
  Mimir — "an import away"), not assume live gov series.
- **Reference stays external.** The michigan repo (`~/Documents/politics/government-observability/…`) is
  read-only reference; do not vendor it. Port the *shape* of `query_mimir`/`extract_labels`/`extract_value`
  /`deduplicate_rows`, not the urllib/PostgREST specifics.
- **Recon artifacts** (`/tmp/tsdb_recon.py`, `tsdb_inspect.py`, `tsdb_range.py`,
  `specimen-startd8_cost_USD_total.json`) are throwaway but are the working starting shape for M0/M1.
- **Capability-index:** on ship, add a capability entry (this is a new SDK surface — the front-half of the
  two generation paths' relational story).

---

## Sequencing + risk

Do M0→M1→M2(+golden test)→M3→M4→M5→M6, then M7. The one thing that can silently break production data is a
**wrong inferred identity key** (M2/OQ-4) → guarded by the golden test + human confirmation at the gate.
The one thing that silently no-ops the whole backfill is a **missing `imports.yaml`** (M3) → without it no
importer is emitted at all. Everything else is reuse of already-gated machinery.
