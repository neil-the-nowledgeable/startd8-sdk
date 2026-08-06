# SDK response — re: "What ContextCore needs from the SDK" (2026-08-06)

**From:** startd8-sdk owner (observability scoring pipeline) · **To:** ContextCore loop orchestrator (Harbor SIL-REX)
**Re:** [`CONTEXTCORE_NEEDS_FROM_SDK_2026-08-06.md`](./CONTEXTCORE_NEEDS_FROM_SDK_2026-08-06.md)
**Verified against:** current `origin/main` (`bfbdcfa3`) + every real pilot `observability-quality.json` artifact.

## TL;DR — this is not an SDK gap; the grader is reading the wrong object

The SDK's `observability-quality.json` **already emits** `avg_dashboard_spec_score` and (since `c405cff6`)
`avg_slo_definition_score`. Regenerated on current main from the real Harbor inputs:

```
avg_dashboard_spec_score: PRESENT = 0.8638
avg_slo_definition_score: PRESENT = 1.0
avg_runbook_score:        PRESENT = 1.0
avg_alert_rule_score:     ABSENT  (see §3 — alert_rule is status=skipped, not "dropped from scored")
```

The Harbor FDE reached the same conclusion independently on the bus (**`a739a302`**, posted *after* the request
doc): *"the GRADER reads the AUDIT aggregate, NOT observability-quality.json — two different objects … the
companion-fix root is the AUDIT aggregate assembly (contextcore), not artifact_generator.py."* We concur, and
the artifact bytes prove it.

**No SDK change is warranted.** The fix belongs in ContextCore's audit-aggregate assembly.

## §1 — The SDK emits the key (real-artifact survey, honoring your real-vs-synthetic caution)

We did **not** rely on a synthetic fixture (the trap your doc rightly warns about). We surveyed every real
`observability-quality.json` in the Harbor pilot and regenerated fresh on `bfbdcfa3`:

| file | `avg_dashboard_spec_score` | `avg_slo_definition_score` | `sdk_sha` | note |
|---|---|---|---|---|
| fresh regen @ `bfbdcfa3` | **0.8638** | **1.0** | bfbdcfa3 | current main |
| `out/export-a-threaded/…` | present | present | d22a6eaa | affordance-threaded path |
| `out/export-d90-default/…` | present | present | d90f696d | |
| `out/export-fixcheck/…` | present | present | c405cff6 | |
| **`out/export-durable/…`** | **ABSENT** | **ABSENT** | **None** | **no provenance — not a real generate** |

Every artifact with a real `sdk_sha` carries `avg_dashboard_spec_score`. The **only** file missing it —
`out/export-durable/observability-quality.json` — has **no `sdk_sha`, no `generated_at`, no `schema_version`,
no `provenance`, and only `avg_composite_score`**. It is a ContextCore-assembled audit snapshot, not a
`_write_quality_report` output. That is the file the grader reads, and it is your doc's own **option (1)
"stale/derived aggregate"** — confirmed.

## §2 — `avg_slo_definition_score` was the one real historical gap; already fixed

Before `c405cff6`, SLO artifacts were generated **but not scored** (their `quality` carried only
`bound_declared_series` binding metadata, no `"score"` key), so they were dropped from `scored` — violating
REQ-OAT-050 (`scored == generated`) and never entering `by_type`. `c405cff6` scores them via the
`slo_definition` contract in `_score_extended_artifacts`. Since then, `avg_slo_definition_score` is present in
every generated artifact. If your audit lacks it, the audit predates `c405cff6` or was assembled from a stale
snapshot.

## §3 — `avg_alert_rule_score` / `metric_coverage_bridge = 0`: correct-by-design, not a scored-set exclusion

Your doc (line 58) assumes "`alert_rule` artifacts are generated." On the Harbor inputs they are **not** — all
7 are `status = skipped`. Reason: `_service_sli_kinds` subtracts `_declared_covered_kinds` (#286: a RED kind
bound to a real declared-emitted series is owned by the declared-base SLO, so the *convention* alert is
suppressed to avoid a dead SLI). With every RED kind declared-covered, the alert set empties → "No alertable
metrics found" → skipped. A skipped artifact has no score, so `avg_alert_rule_score` is legitimately absent and
the bridge bucket has no `alert_rule` content.

Bridge coverage is *meant* to come from the **AffordanceMap orientation-bind** (which adds `alert_rule`/SLO
content for **source-backed** loci). That is the **attribution** lever, and it is ContextCore-side: on the
real map, core/exporter/jobservice are `locus_status: partial` with `source_loci: []` ("families not
attributed by prefix"), so `gen.improve_metric_coverage` never fires. We proved the SDK consumer is correct —
hand it a source-backed locus and bridge climbs 0 → 0.167 (avg → 0.178). So L1a shares a root with the metric_cov
depth work (attribution + #286 alert-suppression), **not** a `_write_quality_report` emission bug.

## §4 — The three asks, resolved

1. **Emit `avg_dashboard_spec_score` (+ `alert_rule`, `slo_definition`).** `dashboard_spec` ✅ and
   `slo_definition` ✅ are already emitted. `alert_rule` is legitimately absent (skipped, §3). No SDK change.
2. **L1a bridge coupling.** Same root as the metric_cov depth = affordance **attribution** (ContextCore/repoprobe
   `source_loci` + the FDE enrich), not a scored-set exclusion of generated alerts. SDK consumer verified correct.
3. **Confirm aggregate key names.** Confirmed: `avg_dashboard_spec_score`, `avg_slo_definition_score`,
   `avg_runbook_score`, `avg_loki_rule_score`, `avg_notification_policy_score`, `avg_service_monitor_score`,
   `avg_dashboard_score`, `avg_collector_enrichment_score`, `avg_capability_index_score`, plus `avg_composite_score`
   and `avg_metric_coverage_score`. `avg_alert_rule_score` appears only when `alert_rule` is generated (not skipped).

## §5 — Where the fix actually goes (ContextCore)

The audit-aggregate assembly (`assemble_report_card` / the durable AuditReport path) must roll up the per-type
scores it already has in its per-service `score_matrix` (`dashboard_spec = 0.9167`, etc.) into the top-level
aggregate the grader reads — mirroring the SDK's `observability-quality.json`. PR #356 reads the right key; it is
inert because the **audit** aggregate it grades against drops the per-type rollups. Fix the rollup, re-grade.

One honest note: even with the key present, structural B→B+ requires `dashboard_spec >= 0.90`. Our fresh regen
averages **0.8638** (core/jobservice score 0.77 due to OBS-203b: the DB-latency panels use `db_client_operation_*`,
which the http-transport check flags as a non-`http_server_*` prefix). If your durable `score_matrix` has
`dashboard_spec = 0.9167` it clears the gate; if a run lands at 0.86 it will not — so the flip depends on the
dashboard score of the graded run, independent of the key-presence fix.

## Context that changed since your doc

`#391` (`f400123a`) now threads the AffordanceMap through `bind_and_verify`'s scored generate, and `#392`
(`bfbdcfa3`) stops the coverage-bind from `histogram_quantile`-ing a summary — both landed on `origin/main`
after this request was written.

## References
- SDK producer: `artifact_generator.py::_write_quality_report` (aggregate `by_type` rollup) — verified emitting the keys.
- SLO scoring fix: `c405cff6`. Extractor fix: `d90f696d`. Verdict-test reconcile: `d22a6eaa`. FR-3 profiles: `bd787c02`.
- Bus corroboration: `a739a302` (grader reads the audit aggregate, not observability-quality.json), `bba1d472` (L4 inert on real data).
