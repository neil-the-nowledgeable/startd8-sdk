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
| **M2 inference spike** — rung-3 reproduces the michigan `department_budgets` golden vs the REAL emitter (12/12 GREEN) | ✅ done — `spike/spike_inference.py` |
| **Production code (`src/`)** | ⛔ not started — the spike is the M2 seed |

> **Spike verdict (2026-07-08, GREEN, committed `6e543fe4` on `spike/tsdb-relational-inference`):**
> inference independently found the exact 5-col identity key (no `*_display` leak), typed
> `fiscal_year`→`Int` / `amount`→`Decimal` / slugs→`String`, renamed `source`→`dataSource` to dodge the
> bookkeeping collision (zero emitter errors), and emitted a valid `schema.prisma` via the real
> `render_prisma_schema`. **M2 — the load-bearing risk — is de-risked.** Honest caveat: the specimen is
> full-factorial (independent dims), the clean minimal-unique case; on *correlated* real data a smaller
> subset can be coincidentally unique — which is exactly why the F1 golden tie-break + F7 confirmation gate
> exist (both paths exercised). The correlated-columns case is the first fixture to add when hardening M2.

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

- [x] **M0 — TSDB reader (FR-1).** ✅ **DONE** — `src/startd8/tsdb_maturation/reader.py` (`httpx` instant
      query + `last_over_time(<m>[<lookback>])`, `GrafanaProxyEndpoint`/`DirectMimirEndpoint`, env/secrets
      auth). Both CRP hardenings live + tested: **R1-F6** two-way empty split (`EmptyMaterialization`
      pruned-refuse vs `MetricNotFound` config/typo — distinct exception types) and **R1-F11** 401/403 →
      distinct `AuthError` short-circuiting *before* the index lookup (auth cannot masquerade as an empty
      refuse). **R1-S5** family fan-out (`read_family`, one query per member) gives M2/FR-12 its read
      capability. 19 tests green (`tests/unit/tsdb_maturation/test_reader.py`, `httpx.MockTransport`, no live
      TSDB). Recon scripts preserved at `spike/recon/` (`tsdb_recon.py` inventory, `tsdb_inspect.py` labels,
      `tsdb_range.py` query_range→specimen; the starting shape M0 generalized onto `httpx`).
- [x] **M1 — Specimen (FR-2, FR-9).** ✅ **DONE** — `src/startd8/tsdb_maturation/specimen.py`:
      `flatten_series` (one raw record per series `{<label>…, "value", "observed_at"}`), durable atomic
      JSON (`write_specimen`/`load_specimen`), and `summarize` (dry-run counts + per-label cardinality +
      sample). **R1-F9 raw invariant** enforced (`n_records == len(series)`, `aggregated=False`) + the FR-4
      input guard `Specimen.assert_raw()` (aggregated specimen → raises, pinning specimen→identity→aggregate,
      no cycle). **FR-9 grain honesty**: `Grain.coerce` defaults unknown/missing to least-trusted
      `tsdb_aggregate` (never inflates to `import_source`); TSDB reads default least-trusted, lossless via
      `from_records`. Reserved-key (`value`/`observed_at`) label collision refused loudly. 17 tests green;
      E2E-verified against the preserved recon specimen (28 records, high-card `project` surfaced for FR-5).
      (Aggregation still deferred to M5 — it needs the identity.)
- [~] **M2 — Inference core (FR-3/4/11 DONE; FR-5/FR-12 remaining) — THE RISK.** ✅ **Core SHIPPED** —
      `src/startd8/tsdb_maturation/infer.py` (`infer_schema` consuming an M1 `Specimen`). All spike
      productionization items landed: **R1-S7** public emitter accessor `reserved_field_names()` (no more
      private `_BOOKKEEPING` read; contract-tested against the injection set); **R1-S8** direct-graph
      invariant guard `assert_graph_invariants` (vocab/reserved/dupe/unique-declared + emitter-clean parity);
      **R1-F1** deterministic identity tie-break (fewest cols → golden → lexicographic); **R1-F2** display
      exclusion; **R1-F8** measure-name collision suffix; **R1-F9** raw-specimen input via `assert_raw`;
      **R1-F10** rename-collision check. **The two-gate golden test (R1-S1)** is live
      (`test_infer_golden.py`): gate (a) structural + gate (b) identity==michigan `CONFLICT_COLUMNS`, the
      **negative `*_display` fixture**, and the **correlated-columns fixture** (proves a coincidental smaller
      key slips past structural inference → the M2.5/M4 confirmation gate is load-bearing, not cosmetic).
      **R1-S2** four expected transforms asserted post-normalization. 33 M2 tests green (69 in the package);
      golden = `20260313220000_michigan_budget_schema.sql`. **Remaining M2 sub-tasks:** FR-5 reduction policy
      (auto top-N + loud warning, OQ-3) and FR-12 family grouper / member-alignment (multi-measure tables) —
      both additive and separable from the load-bearing identity risk, deferred to a follow-on slice.
- [x] **M2.5 — Confirmation gate (FR-4, R1-S6).** ✅ **DONE** —
      `src/startd8/tsdb_maturation/confirmation.py`, modeled on the kickoff `confirmed.yaml`
      committed-ledger pattern. Committed ledger at `docs/tsdb-maturation/confirmed.yaml` (outside any
      scanner glob), keyed by metric → confirmed identity. `confirmation_status` →
      CONFIRMED/UNCONFIRMED/**STALE** (key changed); `require_confirmation` is the hard gate M4 calls
      (raises `ConfirmationRequired` unless the current key is confirmed); `record_confirmation`/
      `confirm_inference` write the marker; `render_confirmation_surface` shows the inferred key next to
      the golden diff (R1-F7). **R1-S6 three-case acceptance green**: unconfirmed→refused, confirmed→allowed,
      key-changed-on-re-promote→re-confirm. Order-insensitive (composite key = set); tolerant ledger IO
      (absent/malformed → empty). 14 tests green (83 in the package).
- [x] **M3 — `imports.yaml` generator (FR-14).** ✅ **DONE** —
      `src/startd8/tsdb_maturation/imports_writer.py`, the first programmatic manifest writer in the SDK.
      `generate_imports_yaml([InferenceResult])` serializes the inferred identity into an `imports.yaml`
      (`format: json` + composite/field `identity:`) that `parse_imports` accepts. **R1-F3 semantic
      round-trip contract enforced** (self-checks its own output: `parse_imports(generate(key)).identity ==
      key` on kind + ordered cols; fails loud on drift). **Smoke-verified against the real `render_import`**:
      the generated manifest bakes a **composite** `_IDENTITY` into the importer, NOT `id` — so TSDB rows
      (no stable `id`) dedup on the inferred columns instead of infinitely duplicating. Decimal/DateTime
      coercion is free (`_COERCE`). 18 tests green (101 in the package). The E2E dedup proof (R1-S3, re-run
      twice → 0 new rows) lands with M5.
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

- **CRP (Phase 5) — done.** R1 ran + triaged (19 suggestions, all accepted & merged; see the "Where we
  are" table). The docs are hardened + OQ-clean; the R1 findings referenced throughout (R1-Fn / R1-Sn) are
  the accepted set. No further CRP round is gating the build.
- **The gov data is not in `o11y-dev` Mimir** (retention-pruned; recon confirmed 0 samples). M0/M2
  validation should use **a recorded specimen fixture** (or re-push from the michigan CSVs into a local
  Mimir — "an import away"), not assume live gov series.
- **Reference stays external.** The michigan repo (`~/Documents/politics/government-observability/…`) is
  read-only reference; do not vendor it. Port the *shape* of `query_mimir`/`extract_labels`/`extract_value`
  /`deduplicate_rows`, not the urllib/PostgREST specifics.
- **Recon artifacts** are preserved in `spike/recon/` (`tsdb_recon.py`, `tsdb_inspect.py`,
  `tsdb_range.py`, `specimen-startd8_cost_USD_total.json`) — the working starting shape for M0/M1 and a
  real specimen fixture for the M2 tests (read-only against a Grafana datasource proxy at :3000).
- **Capability-index:** on ship, add a capability entry (this is a new SDK surface — the front-half of the
  two generation paths' relational story).

---

## Sequencing + risk

Do M0→M1→M2(+golden test)→M3→M4→M5→M6, then M7. The one thing that can silently break production data is a
**wrong inferred identity key** (M2/OQ-4) → guarded by the golden test + human confirmation at the gate.
The one thing that silently no-ops the whole backfill is a **missing `imports.yaml`** (M3) → without it no
importer is emitted at all. Everything else is reuse of already-gated machinery.
