# CRP Focus — TSDB → Relational Maturation

Weight the review toward these high-risk areas. **F-suggestions → requirements**
(`TSDB_TO_RELATIONAL_MATURATION_REQUIREMENTS.md`, FR-1..FR-14); **S-suggestions → plan**
(`TSDB_TO_RELATIONAL_MATURATION_PLAN.md`, milestones M0..M7).

**Settled — do NOT relitigate:** the generalize-not-greenfield framing; reuse of the SDK back-half
(`render_prisma_schema`/`emit_schema_draft`/`promote_schema`/`generate backend`/`from_json`/`identity.py`
— all grep-verified in the Reference Audit); the michigan converter as reference + its DDL as golden; the
resolved OQ-1..13 (§0). Focus your budget on the **inference core (FR-3/4/11/12)** and its coupling to the
reused back-half — that is the only real build and the only un-reviewed surface.

1. **Identity inference correctness (FR-4, M2) — the load-bearing risk.** The inferred "minimal label
   subset unique per series" becomes the dedup key. A wrong key silently overwrites on backfill (the SDK
   importer is last-writer-wins, no DB tripwire). Two known hazards: functionally-dependent `*_display`
   columns can make a *wrong* subset appear unique, and the true key may need a slug the naive search
   drops. Is "minimal-unique-subset + human-confirm-at-gate + validate-against-michigan-`CONFLICT_COLUMNS`"
   sufficient, or is the inference fundamentally unsafe to automate? Any better signal than pure
   uniqueness (e.g. exclude display-looking columns, prefer slugs)?

2. **The `imports.yaml` generator (FR-14, M3) — first programmatic manifest writer in the SDK.** Every
   manifest today comes from prose extraction; there is no programmatic writer. FR-14 must serialize the
   inferred `IdentityKey` + coerce tags into an `imports.yaml` that `parse_imports` round-trips, or
   `generate backend` emits **no importer** and rows dedup by `id` → infinite duplication. Is a bespoke
   writer for this capability the right call, or should it be a general SDK seam? What's the round-trip
   contract/test? Any risk the generated manifest drifts from what `parse_imports` accepts?

3. **Direct `EntityGraph` construction + bookkeeping collision (FR-3/FR-11, M2).** Inference must build the
   graph the `graph_from_prisma` way (NOT prose `extract_entities`) and must rename any label colliding
   with the canonical `_BOOKKEEPING` set (verified: gov `source` → duplicate-field → gate refuses). Is
   reading `_BOOKKEEPING` at runtime the right coupling, or should the emitter expose a "reserved names"
   API? Does building a graph outside `extract_entities` risk missing invariants the prose path enforces?

4. **Key-collapse aggregation ordering (FR-6, OQ-13, M1/M5).** Aggregation (sum on identity collision)
   depends on the inferred identity, so it cannot run at specimen time (M1) — it runs at records-build
   (M5), after M2. The v0.4 ladder is explicitly non-linear here. Is this ordering captured correctly, or
   is there a hidden cycle (specimen needs raw series; records need identity; identity needs the
   specimen)? On the SDK path the failure is silent data loss, not an error — is the guard test (colliding
   specimen → assert summed totals) adequate?

5. **Metric-family grouper + multi-query join (FR-12, FR-1).** Auto-merging `_amount`+`_count` families
   into one multi-measure table couples the reader (issue N PromQL queries) and the inferrer (index-join
   by identity, michigan `count_index`). How is "these metrics are one family" decided reliably (shared
   identity? name-stem? explicit)? What happens when member metrics have *mismatched* label sets or
   partially-overlapping series (a key present in `_amount` but absent in `_count`)?

6. **Reader robustness + histogram scope (FR-1/FR-13).** (a) FR-1 must detect empty results
   (names-in-index/samples-pruned — recon hit this) and handle Grafana-proxy auth; is `last_over_time`
   with a wide lookback the right/only read, and how is a partial materialization surfaced honestly?
   (b) FR-13 (histograms → stats table) is the largest, most speculative addition, sequenced last (M7) so
   it's droppable. Is a `_bucket`/`_sum`/`_count` → percentile-stats table well-enough defined to keep in
   scope, or should v1 defer it and ship the gauge/measure path first?
