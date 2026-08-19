# ContextCore — High-Level Technical Description

*Doc 3 of 5 — "Introduction to ContextCore." Audience: architects and technical evaluators. This
doc describes the **architecture and data flow** — the components, how they connect, and why. It
deliberately stays above the config layer; the actual YAML/CRD/OTTL mechanics live in
[**04 — the nuts and bolts**](04_TECH_details.md). For the plain-language version see
[**01 — ELI5**](01_ELI5_how-it-works-and-why-better.md); for the feature catalog see
[**02 — what it does**](02_FUNCTIONAL_description.md); for the business case see [**05 — GTM**](05_GTM_swot-moat-commercialization.md).*

---

## 1. The approach: Declarative Business-Context Observability

**ContextCore is "business context as code."** You declare business meaning **once** — in pod
annotations, CRDs, and collector/mesh config — and from then on **every telemetry signal becomes
business-aware**: it knows which *service* it came from, which business *flow* it is serving, and
how much that flow is *worth*. There is **zero application code** to write, it is **vendor-neutral**,
and it runs **on your existing OpenTelemetry stack**.

The design goal that shapes the whole architecture: business context should be a **declarative
property of your platform config**, not something engineers hand-thread through every service. The
consequence is that the four architectural mechanisms below are all driven by
pod-annotation / CRD / collector config — never by application source.

### The problem it solves

Conventional observability answers *technical* questions ("service X is down"). It cannot answer
*business* questions ("**which revenue-primary flows** just failed?") because the signals carry no
business meaning. Bolting that meaning on by hand — editing every service — is expensive, drifts,
and breaks in polyglot fleets. ContextCore makes the business meaning **declared config that the
telemetry pipeline materializes for you**.

### Three orthogonal criticality axes

The architecture keeps **three distinct axes** of "how critical is this?" — never collapse them:

| Axis | Question it answers | Where it lives | Nature |
|---|---|---|---|
| `service.business.criticality` | how critical is this *service*, in general | resource attribute (pod annotation) | **static** |
| `project.business.criticality` | how critical is the *initiative* | manifest fallback | **static** |
| `flow.business.criticality` | how critical is **this request** | **baggage** (per-request) | **dynamic** |

The static axes are a property of *services*; the dynamic axis is a property of *flows*. The same
`productcatalogservice` is statically `high`, but a call to it **inside a checkout flow** is more
business-critical than the same call inside a browse flow. That flow distinction is the axis only
baggage can carry.

---

## 2. The four-mechanism declarative stack

Four declarative mechanisms, layered from origination to policy. Each is config, not code.

**① OTel Operator auto-instrumentation** — an `Instrumentation` CRD declares the propagators
(`tracecontext,baggage`) and the `BaggageSpanProcessor`; a single pod annotation
(`instrumentation.opentelemetry.io/inject-<lang>`) makes a mutating webhook **inject the real OTel
SDK** into the workload. This one mechanism delivers three things at once: telemetry **generation**,
**baggage propagation** across hops, and **materialization** of baggage onto span attributes. Works
for Python/Java/Node/.NET via injection; **Go is the rough edge** (eBPF-based, less mature).

**② `k8sattributes` processor** (in the collector) — pulls named `contextcore.io/*` pod annotations
onto every signal the pod emits. This is the **static business-context half**: `criticality`,
`owner`, SLOs, `project.id`, etc., landing as resource attributes. Any language, **zero SDK**. (In
ContextCore this is the shipped `ProjectContextDetector` / annotation→attribute mapping, movable
collector-side for language-independence.)

**③ Service-mesh header rule** (Istio/Envoy) — the **flow seed**. At a trusted boundary a route rule
stamps the baggage: `route =~ /cart/checkout → baggage: business.flow=checkout,
business.criticality=critical`. Declarative; **application code is required only** when the flow is
not route-discriminable (it depends on request body/segment/flag rather than the path).

**④ OTTL** (in the collector) — the downstream **policy engine**. It routes, tail-samples, and tiers
telemetry **by** `flow.business.criticality` (and the static axes). OTTL is the **runtime twin** of
ContextCore's design-time `DerivationRule`: the same `criticality → severity/tier` mapping applied
to live telemetry that the codegen path bakes into generated configs.

**Plus two supporting pieces:**

- **`instrumentation-gen`** — the **coverage-gap fallback**, not the default. It *generates*
  instrumentation to make a subject emit what the declarative path can't cover: absent metrics no
  probe can infer, unsupported languages / no-injection environments, and custom app-semantic
  business spans.
- **The governed sink registry** (`telemetry_sink.py`) — a per-app registry of telemetry egress
  destinations. Its planned **Phase-2 delivery router** is where OTTL-driven per-flow routing lands
  (which telemetry egresses to which sink).

---

## 3. Architecture and data flow

The end-to-end path runs **declare → inject → propagate → enrich → seed → policy → sink**. Static
business context (②) and dynamic flow context (③) originate separately, converge onto span
attributes at materialization, and are then acted on by policy (④).

```
 DESIGN-TIME (declare once)                          RUNTIME (per request)
 ┌─────────────────────────────┐
 │ contextcore.io/* pod annots │  service.criticality, owner, SLOs, project.id
 │ Instrumentation CRD         │  propagators = tracecontext,baggage + BaggageSpanProcessor
 │ Mesh route → flow rule      │  /cart/checkout → flow=checkout, criticality=critical
 │ (one authored criticality   │
 │  map — single source §5)    │
 └──────────────┬──────────────┘
                │ declares
                ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │  ①  INJECT  — OTel Operator mutating webhook injects the real SDK        │
   │             (generation + baggage propagator + BaggageSpanProcessor)     │
   └────────────────────────────────────────────────────────────────────────┘
                │
   trusted entry (mesh / gateway)
                │  ⑤ SEED  business.flow / criticality / tier  (③ header rule)
                ▼
   ┌──────────┐  baggage rides every hop   ┌──────────┐   ┌──────────┐
   │ frontend │ ─────② PROPAGATE──────────▶ │ cart svc │──▶│ payment  │─ ... ▶
   └────┬─────┘                             └────┬─────┘   └────┬─────┘
        │ MATERIALIZE (BaggageSpanProcessor copies baggage → span attrs)
        │  +  static resource attrs already stamped by ④ k8sattributes / detector
        ▼                                        ▼              ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │              every span now carries  business.*  (flow + service)        │
   └────────────────────────────────────────┬───────────────────────────────┘
                                             ▼
   COLLECTOR
   ┌────────────────────────────────────────────────────────────────────────┐
   │  ⑥ ENRICH  k8sattributes → static business.* onto every signal           │
   │  ⑦ POLICY  OTTL: route / tail-sample / tier / derive impact              │
   │            BY flow.business.criticality  (runtime twin of DerivationRule)│
   └────────────────────────────────────────┬───────────────────────────────┘
                                             ▼
   ┌────────────────────────────────────────────────────────────────────────┐
   │  ⑧ SINK   delivery router over telemetry_sink.py                         │
   │           checkout-flow traces → premium high-retention sink             │
   │           browse-flow traces   → cheap / sampled sink (or dropped)       │
   └────────────────────────────────────────────────────────────────────────┘

   → RCA / dashboards pivot by  flow=checkout, criticality=critical  across
     traces + metrics + logs  (vendor-neutral OTel semconv)
```

### Walking the flow

1. **Declare** — business meaning is authored once as pod annotations, an `Instrumentation` CRD, and
   a mesh route→flow rule. One authored criticality map is the source of truth (§5).
2. **Inject** — the OTel Operator's mutating webhook injects the real SDK (with the baggage
   propagator + `BaggageSpanProcessor`) at pod start. No code change.
3. **Propagate** — the composite propagator (`tracecontext,baggage`) carries the baggage payload
   across **every** service hop over W3C-standard headers.
4. **Enrich** — the collector's `k8sattributes` processor stamps the **static** `business.*`
   (service criticality, owner, SLOs) onto every signal.
5. **Seed** — at a **trusted entry** (mesh/gateway) the flow rule stamps the **dynamic** baggage:
   `business.flow`, `business.criticality`, `business.tier`.
6. **Materialize** — the `BaggageSpanProcessor` copies the selected baggage keys onto **span
   attributes** on every span. *This is the step that turns propagated context into queryable
   telemetry* (see the materialize-first rule, §4).
7. **Policy** — OTTL in the collector routes, tail-samples, tiers, and derives impact by the now-
   materialized `flow.business.criticality`.
8. **Sink** — the delivery router over the sink registry sends telemetry to cost/value-tiered
   destinations by flow criticality.

**Why static and dynamic converge but originate apart:** the static half describes the *workload*
(set once, at process start, resource-scoped) and the dynamic half describes the *request* (set per
call, span-scoped, propagated). Keeping their origination separate is what preserves the three-axis
distinction; they only merge as `business.*` attributes at materialization, where both become
queryable side by side.

---

## 4. The load-bearing architectural rules

Four rules make the architecture correct and safe. They constrain component ordering and trust — the
config details are in doc 04, but an evaluator needs the rules to judge the shape.

- **Materialize-first.** **OTTL cannot read runtime baggage.** By the time telemetry reaches the
  collector, baggage is only visible if the `BaggageSpanProcessor` already copied it onto spans.
  Order is non-negotiable: **materialize (SDK/span processor) → then OTTL (collector).** Baggage
  without the span processor propagates but never lands on telemetry — the #1 mistake.
- **Single-source the criticality mapping.** One authored `criticality → severity/tier` mapping
  (`critical → P1`, sampling rates, SLO thresholds) feeds *both* the design-time `DerivationRule`
  (generates configs) *and* the runtime OTTL (transforms live telemetry) — plus the baggage seed, the
  sink router, and the authoring lint. If it is authored twice it drifts, and a critical flow gets
  sampled one way at design-time and another at runtime. A dedicated **authoring lint** guards that
  the mapping has exactly one home.
- **Trust boundary.** Baggage travels in headers, so **set/overwrite business baggage only at a
  trusted entry** (the mesh/gateway seed). Never trust client-supplied baggage — otherwise a client
  can stamp `criticality=critical` to jump the sampling queue or **buy premium retention on your
  dime** (a real cost-abuse vector once §8 routes egress by flow criticality).
- **Cardinality.** Flow-tag routing is a **traces/logs** lever: those are per-record, so route each
  by its materialized flow criticality. **Metrics are pre-aggregated** — per-flow routing is lossy
  unless `flow` becomes a metric dimension, which reintroduces cardinality cost. Keep baggage keys
  low-cardinality (flow/criticality/tier); never put `transaction_id`-class values on metrics.

---

## 5. Vendor-neutrality

Every mechanism is **OTel-native**. The annotation→attribute mapping targets **standard OTel
semantic conventions** (e.g. `deployment.environment.name`), not a vendor schema — so the same
declared context is portable across **Datadog, Splunk, Grafana, Prometheus, Loki, and Tempo**.
Baggage uses **standard W3C baggage** (no custom propagator). You are not locked into one vendor's
whole stack; ContextCore makes the OTel stack you already run business-aware.

---

## 6. Maturity — what's real today vs roadmap

Stated plainly, so an evaluator can calibrate:

| Capability | Status |
|---|---|
| Telemetry **generation** + **static** business context (`k8sattributes` / annotation detector) + baggage **propagation** | **Declaratively achievable today** |
| `instrumentation-gen` coverage-gap fallback | Shipping (Go lane built; other languages piloting) |
| **Flow-aware RCA**, **per-flow tiering**, the **sink policy router** | **Roadmap** (planned seam over `telemetry_sink.py`) |
| **Go** auto-instrumentation + **eBPF** context propagation | **Maturing** (rougher than Python/Java/Node/.NET) |

The declarative origination, static enrichment, and propagation are the solid core; the flow-scoped
policy/RCA/tiering payoff and the Go/eBPF edge are the parts still being hardened.

---

*Next: [**04 — the nuts and bolts**](04_TECH_details.md) drills into the actual CRD,
`k8sattributes`, mesh-rule, and OTTL configuration this architecture is built from.*
