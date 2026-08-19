# OTTL in Observability Artifact Generation — Status & Scope

**Date:** 2026-08-18 · **Scope:** `src/startd8/observability/` · **Kind:** capability status / analysis
**Question answered:** *"Do we have OTTL-driven o11y artifact generation yet?"* — including the sharper
form: *"do we generate Grafana SLOs + dashboards + the metrics that connect them, based on OTTL?"* (reading **(D)**).

> **OTTL** = the [OpenTelemetry Transformation Language](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/pkg/ottl),
> the statement language the Collector's `transform`/`filter`/`routing` processors use to mutate telemetry
> in flight (e.g. `set(attributes["x"], "y") where resource.attributes["service.name"] == "svc"`).

The answer depends on which of **four** distinct capabilities "OTTL-driven" means. This doc pins each to
the actual code so the status can't drift.

---

## TL;DR

| Reading of "OTTL-driven o11y artifact generation" | Status |
|---|---|
| **(A)** The SDK **generates OTTL** as a first-class o11y artifact | ✅ **Shipped + live-proven** — the `collector_enrichment` business processor |
| **(B)** OTTL is the **driver/SSOT** other artifacts (dashboards/alerts/SLOs) are **derived from** | ❌ Not built — OTTL is a co-generated *output*, not an *input* |
| **(C)** The SDK generates **general-purpose OTTL transforms** (filter / route / redact / metric-derive / severity-remap) from a spec | ❌ Not built — only the *one* enrichment class exists |
| **(D)** An **OTTL-connected vertical** — the co-generated **dashboards + SLOs** query the `business_criticality` label the enrichment stamps | ✅ **Built** — `generate_business_criticality_dashboard` (pre-existing) + `generate_business_criticality_slos` (`f4f5fd9c`), both consume `calls_total{business_criticality=…}` |

> **Correction (2026-08-18):** the first cut of this doc claimed (D) was ❌ and that the stamped label
> "isn't even queried by the generated dashboards/SLOs." **That was wrong — a verification miss.**
> `generate_business_criticality_dashboard` already consumed the span-metrics dimension; the SLO
> counterpart (`generate_business_criticality_slos`) has now been added. See §(D) for the corrected map.

Net: **we generate one class of OTTL (business-attribute enrichment) AND a project-level dashboard + SLO
set that CONSUME the label it stamps — the (D) vertical. We do not use OTTL to *drive* downstream
generation (B), and we do not generate arbitrary OTTL transforms (C). Caveat: per-*service* dashboards/SLOs
are still connected by the metric-descriptor layer, not the OTTL label — (D) is the project-level *tier* view.**

---

## (A) What EXISTS — `collector_enrichment` (generating OTTL) ✅

A first-class observability artifact that emits an OTel Collector **`transform`/business processor** — OTTL
statements that stamp business-domain attributes onto telemetry at the collector, keyed by `service.name`,
so downstream queries/dashboards can slice by business dimensions.

**The emitted OTTL shape** (one statement per present `(service, attr)`):

```
set(attributes["business.<attr>"], "<value>")
  where resource.attributes["service.name"] == "<svc>"
```

**Where it lives (grounded):**

| Concern | Location |
|---|---|
| Artifact type registration | `artifact_generator_context.py:46,49` — `ArtifactTypeSpec("collector_enrichment", …, priority 85)` |
| Generator | `artifact_generator_generators.py:3349` — `generate_collector_enrichment(...)`; output path `_COLLECTOR_ENRICHMENT_PATH = "collector-enrichment/otelcol-business-enrichment.yaml"` (`:3303`) |
| Wired into the suite | `artifact_generator.py:1991` (FR-3) + dispatch `:509` |
| Input source (the values) | `artifact_generator_models.py:176-184` — per-service `instrumentation_hints[svc].business = {criticality?, owner?}`, **resolved upstream by the ContextCore producer** (NR-2, no SDK-side project fallback); absent ⇒ no statement (byte-identical to pre-feature) |
| OTTL literal escaping | `artifact_generator_generators.py:3306` — `_ottl_str` (Go-style: backslash-first), two layers (OTTL literal + `yaml.dump`) |
| Fail-fast validation | `collector_enrichment_validation.py` (FR-8) |
| Semantic parity gate (cutover) | `collector_enrichment_parity.py` (FR-10a/11) + CLI `observability enrichment-parity` (`cli.py:808`) |
| Runtime fidelity | `runtime_fidelity.py` (emits the same OTTL shape for a live-fidelity check) |

**Status:** built, tested, on `main` (`5896a15e`, #321). **Live-proven** —
`test_live_enrichment_promotes_business_label` boots `otelcol-contrib` 0.158.0, emits a real span, and
verifies the `business.*` label is promoted (infra-gated: skips without `otelcol-contrib` on
`$OTELCOL_CONTRIB_BIN`/PATH). See `docs/design/COLLECTOR_ENRICHMENT_SDK_HANDOFF.md`.

**Note on ownership:** this is the *generate-Collector-config-from-manifest* class. The business context it
stamps is **resolved by the ContextCore producer** and forwarded on `instrumentation_hints`; the SDK's job
is to project that into valid, escaped, parity-checked OTTL. (See memory `project_collector_enrichment`.)

---

## (B) What does NOT exist — OTTL as a *driver* ❌

OTTL here is an **output**, co-generated from the manifest **alongside** the other artifacts
(`generate_dashboard_spec`, `generate_alert_rules`, `generate_*_slos`, `generate_service_monitor`,
`generate_loki_rule`, … all in `artifact_generator_generators.py`) — they are **siblings** sourced from the
same spec, not a chain.

Nothing **parses** OTTL to **derive** downstream artifacts. The only OTTL-as-input code is:
- a content hash computed on raw (pre-escape) values for drift tracking (`artifact_generator_generators.py:3319`), and
- the parity **un-escaper** that reads generated OTTL back to compare against a reference block (`collector_enrichment_parity.py:35`, `_unescape_ottl`).

Neither reads OTTL to *generate* a dashboard/alert/SLO. So: **no "OTTL → derive the rest of the o11y
artifacts" path.**

---

## (C) What does NOT exist — general OTTL transform generation ❌

Exactly **one** OTTL class is generated: business-attribute **enrichment**. There is no generation of other
Collector transform classes from a spec:

- `filter` (drop/keep by predicate),
- `routing` (fan telemetry to different pipelines),
- redaction / PII-scrub (`delete_key`, `replace_pattern`),
- metric derivation (`extract_count_metric`, span→metric),
- severity/status remap.

All of those would be new OTTL emitters.

---

## (D) The specific question — an OTTL-connected metric → dashboard → SLO vertical ✅ (project tier)

We co-generate dashboards + SLOs + the OTTL enrichment from one manifest (`generate_observability_artifacts`
off the same `observability.yaml`). A **project-level tier vertical that consumes the stamped label is built**:

1. **Dashboard (pre-existing).** `generate_business_criticality_dashboard` (`:3505`) emits a project dashboard
   whose panels are `sum by (business_criticality) (rate(calls_total[5m]))` + an error-ratio-by-tier panel
   (`:3539,3547`) — i.e. it **queries the span-metrics dimension the enrichment stamps**. Presence-gated on
   ≥1 service with criticality; wired at `artifact_generator.py:1946`.
2. **SLO (added `f4f5fd9c`).** `generate_business_criticality_slos` — one OpenSLO availability SLO per
   criticality *tier*, SLI = `sum(rate(calls_total{business_criticality="<tier>"}[5m]))` good/total, a stricter
   tier getting a tighter target (`critical` 99.9 → `low` 95.0). Same presence gate + `_repair_and_validate`,
   wired right after the dashboard. So the enriched label now **gates an error budget per tier**, not just a view.
3. **Metrics — still a manual deploy step.** The `business_criticality` label reaches Prometheus via the
   **spanmetrics *connector*** (`dimensions: [business.criticality]`, `:3424`), which the SDK emits as a YAML
   fragment but the operator wires into their connector (`:3435`). So the metric itself isn't SDK-generated;
   the SDK generates the dashboard + SLOs that consume it once the connector is deployed.

**Scope caveat (still true).** This vertical is **project-level, by tier**. The per-*service* dashboards/SLOs
are still bound by the **metric-descriptor layer** (`_descriptor_for` `:284`, `generate_declared_base_slos`
`:1577`) — they scope by `service`, not the OTTL label, which is correct (service already implies its tier).
So "OTTL-connected" holds for the tier roll-up, not for every per-service artifact.

> **This is why (D) beat (B).** (B) — making OTTL the SSOT other artifacts are *derived from* — would invert
> the real SSOT (the manifest). (D) keeps the manifest as SSOT and simply has the generated tier dashboard +
> SLOs *consume the label OTTL already produces* — the smaller, higher-value move, now shipped.

---

## If we wanted to build (B) or (C)

Both fit the **existing, well-trodden `artifact_generator` pattern** — no new framework:

1. **A new `ArtifactTypeSpec`** in `artifact_generator_context.py` (id, category, priority).
2. **A `generate_<kind>(...)` emitter** in `artifact_generator_generators.py` that projects a manifest/spec
   section into OTTL, reusing `_ottl_str` for escaping.
3. **A validation + parity gate** (mirror `collector_enrichment_validation.py` /
   `collector_enrichment_parity.py`) so the generated OTTL is checked, and a cutover from any hand-written
   block is byte/semantically safe.
4. **Wire into `generate_observability_artifacts`** and add a CLI surface.

**Recommended order of value:**

- **(D) — the OTTL-connected tier vertical — ✅ DONE** (`f4f5fd9c` added the SLO half; the dashboard half
  pre-existed). No new artifact type, no new OTTL emitter — the *existing* project dashboard + the new
  per-tier SLOs `group_by`/filter on the `business_criticality` label the enrichment stamps, presence-gated,
  byte-identical when absent. Remaining sub-part: the `business_criticality` *metric* still arrives via the
  operator's spanmetrics connector (a documented deploy step), not SDK generation.
- **(C) — general transforms** (a spec section → filter/route/redact OTTL) is the natural next *emitter*
  build: additive, each transform class an independent emitter behind an opt-in spec field, byte-identical
  when the field is absent (the empty-default discipline `collector_enrichment` uses).
- **(B) — OTTL as a derivation driver** is a bigger conceptual change (make OTTL the SSOT other artifacts
  read) and is likely *lowest* value: the manifest is already the SSOT, so deriving dashboards from transform
  statements inverts that without clear benefit. Prefer (C), unless there's a concrete driver for (B).

---

## Evidence index (verified 2026-08-18)

- OTTL emitter + escaping: `artifact_generator_generators.py:3299-3444` (`generate_collector_enrichment`, `_ottl_str`, `_COLLECTOR_ENRICHMENT_PATH`)
- Artifact-type registration: `artifact_generator_context.py:46,49`
- Suite wiring + dispatch: `artifact_generator.py:1991,509`
- Input contract: `artifact_generator_models.py:176-184`
- Validation / parity / runtime-fidelity: `collector_enrichment_validation.py`, `collector_enrichment_parity.py`, `runtime_fidelity.py`
- CLI: `observability enrichment-parity` (`cli.py:808`)
- Handoff / live proof: `docs/design/COLLECTOR_ENRICHMENT_SDK_HANDOFF.md` (commit `5896a15e`, #321)
- **(D)** the tier vertical that CONSUMES the stamped label: `generate_business_criticality_dashboard` `:3505` (`sum by (business_criticality)` panels `:3539,3547`), `generate_business_criticality_slos` (`f4f5fd9c`, per-tier `calls_total{business_criticality=…}` SLIs), wired at `artifact_generator.py:1946`+
- **(D)** per-*service* artifacts still bind via the descriptor layer (correct — service implies tier): `_descriptor_for` `:284`, `generate_declared_base_slos` `:1577`
- **(D)** the metric arrives via the spanmetrics *connector* (operator deploy step), not SDK-generated: `:3424` (dimension), `:3435` (manual wiring note)
- **(D)** business context read from the manifest at generation time (not queried from the OTTL label): `artifact_generator_generators.py:900,3133,3141`; input at `artifact_generator_models.py:176-184`
