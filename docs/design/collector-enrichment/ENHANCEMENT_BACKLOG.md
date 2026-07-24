# collector_enrichment — Enhancement Backlog

**Last refreshed:** 2026-07-24 (fresh pass after #321–#324).
**Method:** grounded against current code on `feat/collector-enrichment-followups`; leads with the
2–3 findings that matter, appendix below the fold.

## Delivered log

| Ref | Shipped |
|---|---|
| #321 | Generator (FR-1b + FR-2–11): `ServiceHints.{criticality,owner}`, presence-gated OTTL `transform/business`, escaping, determinism, fail-fast validation, semantic parity gate |
| #322 | `startd8 observability enrichment-parity` CLI (QW-1) + this backlog |
| #323 | Live proof: `collector_config()` enrichment seam + `find_collector_binary`-gated integration test (LH-1/EC-2 harness half) |
| #324 | `DEPLOYING.md` (QW-2), `fr_coverage` counts (QW-3/OB-1), per-service alert severity + runbook owner (EC-1), generator emits spanmetrics dimension (EC-2) |

---

## Top findings (do these first)

**1. 🌱 A business-context change is invisible to `check_drift` — one derivation closes it. ✅ DONE.**
`Confirmed:` `generate_collector_enrichment` emits **zero** `DerivationTrace`s (grep of the function =
0), and `check_drift` (`artifact_generator.py:1633-1664`) detects drift by artifact **keys**
(`(type, service_id)`, add/remove) + **derivation rules** (`field,source → transformation`). It does
**not** hash artifact content. So when a service's business context changes — e.g. `cartservice`
criticality `critical→high` — the artifact key is unchanged, no derivation exists to compare, and
`check_drift` prints **"No drift detected"** even though the committed enrichment file is now stale. The
fix rides existing plumbing: emit **one** `DerivationTrace(field="collector_enrichment.business",
source="instrumentation_hints[*].business", transformation="sha256:<provenance>")` — the provenance hash
is already computed (`_business_provenance`), and `check_drift`'s derivation-rule comparison (`:1660`)
then flags a business-context change **for free**. → so an operator's `--check`/CI gate **catches a stale
committed enrichment** instead of silently passing. This is the deferred FR-10b drift detection, now
reachable for near-nothing. **XS/S.**

**2. ⚡ The emitted `connectors:` block is a replace-footgun — mark it append-only inline. ✅ DONE.**
`Confirmed:` the generated file ends with a bare `connectors:\n  spanmetrics:\n    dimensions:` block
(verified by rendering it). It *looks* like a complete, copyable spanmetrics connector — but an operator
who copies that `connectors:` section **replaces** their real spanmetrics connector, losing
`histogram`/`namespace`/`metrics_flush_interval` and breaking span-metrics. The append instruction lives
in the header comment 8 lines above and is easy to miss when scrolling to the YAML. Add a one-line
inline comment directly above the block: `# APPEND these dimensions to your EXISTING spanmetrics
connector — do not replace it (see DEPLOYING.md).` → so an operator **can't silently break their metrics
pipeline** by copy-pasting the wrong block. High blast radius, fresh code, trivial fix. **XS.**

**3. 🌱 `fr_coverage["collector_enrichment"]` is written but no surface reads it.**
`Confirmed:` `compare.py` has **0** references to `collector_enrichment` (it reads only its `_GAP_CLASSES`
divergence keys), and nothing else consumes the block — so OB-1's "make the $0 pass legible" goal is only
half-met: the counts (`statements`, `services_enriched`) sit in the manifest, unread. Surface them in the
run's console summary / index roll-up ("collector_enrichment: 13 services enriched, 26 statements, 1
dimension"). → so a human **sees the pass did something** without opening the manifest YAML. **S.**

*(No built-but-unwired **defect**: the generator is wired into `generate_observability_artifacts`, written
on non-dry-run, and stamped; the parity CLI and live seam are wired. Finding #1 is a drift-coverage **gap**,
not a broken path — verified by tracing both ends of the `check_drift` comparison and confirming the
generator's zero-derivation output.)*

---

<details>
<summary><b>Backlog appendix</b> (supporting; draw from over later increments)</summary>

### ⚡ Quick wins
- **QW-4 — inline append-only comment on the `connectors:` block** — ✅ **DELIVERED** (inline `# APPEND …` above the block). Top finding #2. **XS.**
- **QW-5 — provenance derivation for drift** — ✅ **DELIVERED** (one stable-keyed `DerivationTrace` carrying the provenance; `check_drift` now flags a business-context change, end-to-end tested). Top finding #1. **XS/S.**

### 🌱 Low-hanging fruit
- **LH-2 — surface the coverage counts** — ✅ **DELIVERED** (logger.info at generation + `summary.collector_enrichment` in the index manifest). **S.**
- **LH-3 — score the artifact like its siblings.** ✅ **DELIVERED**. `validate_collector_enrichment_artifact`
  (CE-100a/100b/101/102/103 checklist, reuses `extract_enrichment_map` + the enum) + a `collector_enrichment`
  branch in `_repair_and_validate`; the artifact is routed through it in the wiring, so it now carries a
  `quality` dict in the run report. **S.**

### 🏗️ Architectural quick win (≤1)
- **AQ-1 — extract the semantic-parity pattern on 2nd use (still deferred).** `extract_enrichment_map` +
  map-diff is the reusable "parse two collector configs → compare resolved meaning" shape. No 2nd
  `transform/*` consumer exists yet → duplication-of-one is correct; **do not pre-abstract.** **M, deferred.**

### 🚀 Enhanced capabilities
- **EC-3 — `enrichment-parity` against a LIVE collector.** Today the CLI diffs two files. A `--live-config
  <url>` that pulls a running collector's effective config (zpages/config endpoint) would let an operator
  verify the *deployed* processor, not just a file. Justified by the parity parser already being
  transport-agnostic (it takes YAML text). **M.**
- **EC-4 — single-source the dimension name.** The spanmetrics dimension is the hardcoded literal
  `business.criticality` in **two** places now (generator connectors block + `runtime_fidelity` seam
  default). If a 3rd business attr ever becomes a dimension, that's a 2-site edit. Single-source it when
  the 2nd dimension appears (not before). **S, deferred.**

</details>

---

## Honest gaps (decisions surfaced while grounding — not bugs)

- **The provenance hash is only *partially* redundant with `check_drift`.** I first assumed it was fully
  redundant (deterministic file → content-hash ≡ business-hash). Grounding corrected this: `check_drift`
  is **key + derivation** based, not content-based, so it misses content changes entirely — which is
  exactly why Top finding #1 is real, not redundant.
- **`owner` is deliberately not a spanmetrics dimension** (unbounded cardinality). Stays a span attribute
  for trace-level RCA. Confirm that's the intended shape before anyone "adds owner to the dashboard."
- **Runbook owner precedence: structured `business.owners` before per-service `service.owner`** — a
  product decision (structured escalation contacts are the actionable "who to page"); per-service owner is
  a fallback enrichment. Revisit only if per-service ownership should override project escalation.
