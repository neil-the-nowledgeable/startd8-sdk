# OTTL in Observability Artifact Generation — Status & Scope

**Date:** 2026-08-18 · **Scope:** `src/startd8/observability/` · **Kind:** capability status / analysis
**Question answered:** *"Do we have OTTL-driven o11y artifact generation yet?"*

> **OTTL** = the [OpenTelemetry Transformation Language](https://github.com/open-telemetry/opentelemetry-collector-contrib/tree/main/pkg/ottl),
> the statement language the Collector's `transform`/`filter`/`routing` processors use to mutate telemetry
> in flight (e.g. `set(attributes["x"], "y") where resource.attributes["service.name"] == "svc"`).

The answer depends on which of **three** distinct capabilities "OTTL-driven" means. This doc pins each to
the actual code so the status can't drift.

---

## TL;DR

| Reading of "OTTL-driven o11y artifact generation" | Status |
|---|---|
| **(A)** The SDK **generates OTTL** as a first-class o11y artifact | ✅ **Shipped + live-proven** — the `collector_enrichment` business processor |
| **(B)** OTTL is the **driver/SSOT** other artifacts (dashboards/alerts/SLOs) are **derived from** | ❌ Not built — OTTL is a co-generated *output*, not an *input* |
| **(C)** The SDK generates **general-purpose OTTL transforms** (filter / route / redact / metric-derive / severity-remap) from a spec | ❌ Not built — only the *one* enrichment class exists |

Net: **we generate one class of OTTL (business-attribute enrichment); we do not use OTTL to drive
downstream generation, and we do not generate arbitrary OTTL transforms.**

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

## If we wanted to build (B) or (C)

Both fit the **existing, well-trodden `artifact_generator` pattern** — no new framework:

1. **A new `ArtifactTypeSpec`** in `artifact_generator_context.py` (id, category, priority).
2. **A `generate_<kind>(...)` emitter** in `artifact_generator_generators.py` that projects a manifest/spec
   section into OTTL, reusing `_ottl_str` for escaping.
3. **A validation + parity gate** (mirror `collector_enrichment_validation.py` /
   `collector_enrichment_parity.py`) so the generated OTTL is checked, and a cutover from any hand-written
   block is byte/semantically safe.
4. **Wire into `generate_observability_artifacts`** and add a CLI surface.

**(C) — general transforms** is the more natural next step (a spec section → filter/route/redact OTTL), and
is additive: each transform class is an independent emitter behind an opt-in spec field, byte-identical when
the field is absent (the same empty-default discipline `collector_enrichment` uses).

**(B) — OTTL as a derivation driver** is a bigger conceptual change (make OTTL the SSOT other artifacts read)
and would likely be *lower* value than (C): the manifest/spec is already the SSOT, and deriving dashboards
from transform statements inverts that without clear benefit. Prefer (C) unless there's a concrete driver.

---

## Evidence index (verified 2026-08-18)

- OTTL emitter + escaping: `artifact_generator_generators.py:3299-3444` (`generate_collector_enrichment`, `_ottl_str`, `_COLLECTOR_ENRICHMENT_PATH`)
- Artifact-type registration: `artifact_generator_context.py:46,49`
- Suite wiring + dispatch: `artifact_generator.py:1991,509`
- Input contract: `artifact_generator_models.py:176-184`
- Validation / parity / runtime-fidelity: `collector_enrichment_validation.py`, `collector_enrichment_parity.py`, `runtime_fidelity.py`
- CLI: `observability enrichment-parity` (`cli.py:808`)
- Handoff / live proof: `docs/design/COLLECTOR_ENRICHMENT_SDK_HANDOFF.md` (commit `5896a15e`, #321)
