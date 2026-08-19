# Introduction to ContextCore — Declarative Business-Context Observability

A five-document set introducing the approach at five altitudes. **Declare business meaning once**
(Kubernetes annotations + ContextCore CRDs + a route→flow→criticality mapping) and every telemetry signal
becomes **business-aware, flow-scoped, and value-tiered** — with **zero application code**, **vendor-neutral**,
riding on your existing OpenTelemetry stack.

## Read in the order that fits you

| # | Doc | For | What it gives you |
|---|-----|-----|-------------------|
| 01 | [ELI5 — how it works & why it's better](01_ELI5_how-it-works-and-why-better.md) | anyone | the plain-language analogy |
| 02 | [Functional description](02_FUNCTIONAL_description.md) | product / evaluators | what it *does* (inputs → behaviors → outputs), no mechanics |
| 03 | [Technical description (high level)](03_TECHNICAL_description-high-level.md) | architects | the components + data flow (declare→inject→propagate→enrich→seed→policy→sink) |
| 04 | [Tech details](04_TECH_details.md) | implementing SREs | the CRDs, `k8sattributes`, mesh rules, OTTL, guardrails, coverage matrix (with illustrative config) |
| 05 | [GTM · SWOT · moat](05_GTM_swot-moat-commercialization.md) | exec team / investors | commercialization value + the competitive moat |

## The through-line

The plumbing — OTel Operator auto-instrumentation, the `k8sattributes` processor, service-mesh header rules,
OTTL — is all open and commoditized. **That's a strength, not a weakness.** ContextCore's value is the
**business-context control plane** that turns those open parts into one governed, vendor-neutral, business-aware,
agent-shared system of record: the single source of truth (criticality/owner/SLO/flow) projected consistently to
instrumentation, routing, dashboards, and RCA — and drift-guarded so it stays correct.

> **Classical instrumentation vs business instrumentation — two axes.** **Classical (technical)
> instrumentation** = *source-side signal generation* (code, auto-instrumentation, or **eBPF** emitting
> telemetry that didn't exist before). ContextCore's second axis is **business instrumentation** —
> making the *business dimension* observable by projecting **declared** business meaning (criticality,
> flow, value) onto the telemetry classical instrumentation already emits (the collector-side
> **enrichment**), so business questions become answerable. **The coverage RCA is the proof.** The
> honest caveat: business instrumentation is **not** source-side signal generation — **declared, not
> discovered**, and it **rides on** classical instrumentation's base signal. We don't redefine
> instrumentation; business instrumentation is a distinct axis added alongside it.

## Deeper design docs

- `../business-context-propagation/` — the baggage/flow-criticality design note (originate→propagate→materialize→
  OTTL→sink-filter→RCA, phases, guardrails), the enrichment summary, and the annotation-detection reference.
- `../dashboard-vendor-neutrality/` — the Perses (vendor-neutral dashboard IR) ADR.
- `../EXECUTIVE_contextcore-capabilities-overview.md` — the broader ContextCore capabilities overview.

## Honesty note

Maturity is marked throughout: **available today** — annotation-based context, no-code auto-instrumentation,
business-context propagation, coverage-driven RCA, value-based-observability derivation, the governed sink
registry; **on the roadmap** — flow-aware RCA, per-flow value tiering, the sink delivery-policy router;
**maturing upstream** — Go auto-instrumentation and eBPF context propagation. Nothing here oversells what isn't
shipped.
