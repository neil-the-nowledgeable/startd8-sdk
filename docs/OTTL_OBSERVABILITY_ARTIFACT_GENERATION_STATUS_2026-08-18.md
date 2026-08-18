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
| **(D)** An **OTTL-connected vertical** — OTTL produces/labels the **metrics** that the co-generated **dashboards + SLOs** share | ❌ Not built — the three ARE co-generated from one manifest, but the SLO↔dashboard link is the *metric-descriptor* layer; OTTL and that vertical share only the *manifest*, not the metrics |

Net: **we generate one class of OTTL (business-attribute enrichment); we do not use OTTL to drive
downstream generation, we do not generate arbitrary OTTL transforms, and the co-generated SLOs/dashboards
are connected by the metric-descriptor layer — not by OTTL.**

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

## (D) The specific question — an OTTL-connected metric → dashboard → SLO vertical ❌

We **do co-generate** dashboards + SLOs + the OTTL enrichment from one manifest (`generate_observability_artifacts`
off the same `observability.yaml`), so they're coherent and share a source. But the vertical is **not connected
through OTTL** — three distinct facts, each grounded:

1. **The dashboard ↔ SLO connection is the metric-descriptor layer, not OTTL.** What links a dashboard panel
   to its SLO is the shared **metric series** — bound via `MetricDescriptor` / declared-emitted real series /
   RED convention / span-metrics, with a `declared > suppress > convention` precedence (`_descriptor_for`
   `:284`, `generate_declared_base_slos` `:1577`, `generate_declared_functional_slos` `:1771`). OTTL is
   nowhere in that binding.

2. **The metrics are not OTTL-derived.** Metric derivation here is: error-rate from a counter, a counter from
   a histogram `_count` suffix (`:2466`), and span→metric via the **spanmetrics *connector*** — and that last
   one is a *documented manual step* ("append the spanmetrics `dimensions` to your existing connector",
   `:3435`), **not** generated. There is **no OTTL metric-derivation**.

3. **OTTL and the dashboard/SLO vertical share only the *manifest*, not the *metrics*.** The OTTL processor
   *stamps* `business.criticality`/`business.owner` onto telemetry at the collector. The dashboard/SLO
   generators *also* use `business.criticality` — but they read it from the **manifest** at generation time to
   pick alert severity / availability targets / runbook text (`:900`, `:3133`, `:3141`), **not** by querying the
   OTTL-stamped label. No generated PromQL uses a `{business_criticality=…}` selector.

**So the OTTL-stamped `business.*` label is generated for downstream / human / ad-hoc consumers, but is
*not queried* by the SDK's own generated dashboards/SLOs — they bake the business context in at generation
time instead.** OTTL and the dashboard/SLO vertical run in **parallel off the shared manifest**; they are not
wired through the metrics. That is why the honest answer to reading (D) is **no**.

### The latent wire (a real, small, additive build)

The generated dashboards/SLOs *could* `group_by` / filter on the OTTL-stamped `business.criticality` — which
would make this a genuinely **OTTL-connected vertical**: OTTL labels the telemetry → dashboards slice by it →
SLOs gate per-criticality. That is the missing wire, and it's additive: teach the dashboard/SLO generators to
emit a `by (business_criticality)` grouping (or a `{business_criticality=…}` filter) **when the enrichment is
present**, gated on the same business context the OTTL emitter already consumes — so **absent enrichment ⇒
byte-identical** (the empty-default discipline `collector_enrichment` already uses). This is the concrete,
highest-value form of "OTTL-driven" worth building, and is smaller than either (B) or (C).

> **Why this beats reading (B).** (B) — making OTTL the SSOT other artifacts are *derived from* — inverts the
> real SSOT (the manifest) for no clear gain. (D)'s wire keeps the manifest as SSOT and simply makes the
> generated dashboards/SLOs *consume the label OTTL already produces* — closing a stamped-but-unqueried gap
> rather than re-architecting the source of truth.

---

## If we wanted to build (B), (C), or (D)

Both fit the **existing, well-trodden `artifact_generator` pattern** — no new framework:

1. **A new `ArtifactTypeSpec`** in `artifact_generator_context.py` (id, category, priority).
2. **A `generate_<kind>(...)` emitter** in `artifact_generator_generators.py` that projects a manifest/spec
   section into OTTL, reusing `_ottl_str` for escaping.
3. **A validation + parity gate** (mirror `collector_enrichment_validation.py` /
   `collector_enrichment_parity.py`) so the generated OTTL is checked, and a cutover from any hand-written
   block is byte/semantically safe.
4. **Wire into `generate_observability_artifacts`** and add a CLI surface.

**Recommended order of value:**

- **(D) — the OTTL-connected vertical wire** is the **highest-value, smallest** build: no new artifact type,
  no new OTTL emitter — just teach the *existing* dashboard/SLO generators to `group_by` / filter on the
  `business.*` label the enrichment already stamps, gated on the same business context, byte-identical when
  absent. It closes a concrete stamped-but-unqueried gap.
- **(C) — general transforms** (a spec section → filter/route/redact OTTL) is the natural next *emitter*
  build: additive, each transform class an independent emitter behind an opt-in spec field, byte-identical
  when the field is absent (the empty-default discipline `collector_enrichment` uses).
- **(B) — OTTL as a derivation driver** is a bigger conceptual change (make OTTL the SSOT other artifacts
  read) and is likely *lowest* value: the manifest is already the SSOT, so deriving dashboards from transform
  statements inverts that without clear benefit. Prefer (D), then (C), unless there's a concrete driver for (B).

---

## Evidence index (verified 2026-08-18)

- OTTL emitter + escaping: `artifact_generator_generators.py:3299-3444` (`generate_collector_enrichment`, `_ottl_str`, `_COLLECTOR_ENRICHMENT_PATH`)
- Artifact-type registration: `artifact_generator_context.py:46,49`
- Suite wiring + dispatch: `artifact_generator.py:1991,509`
- Input contract: `artifact_generator_models.py:176-184`
- Validation / parity / runtime-fidelity: `collector_enrichment_validation.py`, `collector_enrichment_parity.py`, `runtime_fidelity.py`
- CLI: `observability enrichment-parity` (`cli.py:808`)
- Handoff / live proof: `docs/design/COLLECTOR_ENRICHMENT_SDK_HANDOFF.md` (commit `5896a15e`, #321)
- **(D)** SLO↔metric binding (descriptor layer, not OTTL): `_descriptor_for` `:284`, `generate_slo_definitions` `:2424`, `generate_declared_base_slos` `:1577`, `generate_declared_functional_slos` `:1771`
- **(D)** metric derivation is counter/histogram/spanmetrics-connector, not OTTL: `:2466` (`_count` fallback), `:3435` (manual spanmetrics `dimensions` step)
- **(D)** business context read from the manifest at generation time (not queried from the OTTL label): `artifact_generator_generators.py:900,3133,3141`; input at `artifact_generator_models.py:176-184`
