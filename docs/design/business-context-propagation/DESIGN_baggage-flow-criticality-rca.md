# Design note + cross-repo handoff: propagate business context via OTel baggage to enable flow-scoped RCA

**Date:** 2026-08-19 · **Type:** design note / cross-repo handoff · **Status:** direction, ready to scope
**Owners:** startd8-sdk (origination · propagation · materialization) + ContextCore (OTTL policy · flow-criticality RCA)
**Relates:** the criticality-authoring model (`ContextCore/src/contextcore/coverage/criticality.py`, REQ-TCP-103) ·
`HANDOFF_criticality-authoring-lint.md` (the single-source guard) · `EXPORT_ENRICHMENT_PLAN` (design-time DerivationRules) ·
`scaffold_codegen/instrumentation_gen.py` + `telemetry_renderer.py` (per-language instrumentation gen)

---

## 0. Diagnosis — business context today is entirely STATIC (grounded)

Three facts from the code establish the gap precisely:

1. **The SDK configures no cross-service propagators.** `startd8-sdk/src/startd8/otel.py` has only *in-process
   thread-context* helpers — no W3C `baggage`/`tracecontext` composite propagator. So
   `io.contextcore.business.criticality` sits on the *project/session span* and **does not propagate** across
   service boundaries.
2. **ContextCore's "value-based observability" is a design-time codegen projection.** The mechanism is
   `DerivationRule` (`plans/EXPORT_ENRICHMENT_PLAN.md`): business metadata → generated artifacts via
   `transformation` mappings (`"critical → P1"`, `"SLO threshold: 99.9%"`). The *"criticality → 100% sampling,
   P1 alerts"* effect is achieved by **generating the Prometheus/Loki/alert configs**, not by transforming live
   telemetry.
3. **The one runtime piece is per-service static enrichment** — the collector stamps a `business_criticality`
   metric dimension via a lookup (EC-10, `coverage/snapshot.py`). Per-service, not per-request.

**Every business-context path is static (design-time or per-service-static). There is no request-scoped business
context anywhere — criticality is a property of *services*, never of *flows*.** That is the gap this fills.

## 1. Core insight — baggage adds the missing DYNAMIC (flow) axis

Baggage propagates request-scoped context through the *live call graph*, turning criticality from a **service
property** into a **flow property**:

> `productcatalogservice` is statically `high`. But a productcatalog call **inside a checkout flow**
> (revenue-primary, `critical`) is more business-critical than the same call inside a browse flow. Baggage
> seeded at the entry (`business.flow=checkout`, `business.criticality=critical`, `business.tier=revenue-primary`)
> rides *every downstream span* — so each span knows *which business flow it serves*.

This is the **third orthogonal axis** to the per-service-vs-project criticality model (keep them distinct — do
NOT collapse `flow.*` into `service.*`, or you reintroduce the drift the criticality lint guards):

| Axis | Question | Home | Nature |
|---|---|---|---|
| `service.business.criticality` | how critical is this service, in general | resource attr · `build_criticality_map` · EC-10 label | static |
| `project.business.criticality` | how critical is the initiative | manifest fallback | static |
| **`flow.business.criticality`** ⭐ | how critical is **this request** | **baggage** | **dynamic** |

## 2. Architecture — four roles (and where baggage / propagator array / OTTL fit)

*Clarification:* the propagator array and baggage are **not alternatives** — the array is the transport config,
baggage is the payload. The real "or" is **standard W3C baggage** (interoperable, low-effort — the right call)
vs a **custom propagator** carrying a structured blob (over-engineering unless baggage genuinely can't express it).

```
1. ORIGINATE  — seed business baggage at a TRUSTED entry, from the ContextCore resolution
                (build_criticality_map / the manifest): flow · criticality · tier.
2. PROPAGATE  — add the `baggage` propagator to the array (absent in the SDK today). Rides every hop.
3. MATERIALIZE— a BaggageSpanProcessor (per language) copies selected baggage → span attributes on
                every span. This is where propagated context becomes queryable telemetry.
4. POLICY     — OTTL in the collector routes / tail-samples / derives BY those attributes.
```

**The load-bearing symmetry:** step 4's OTTL is the *runtime twin* of the design-time `DerivationRule`. The rule
`"critical → P1"` is the **static** policy (baked into generated configs); OTTL applies the **same** policy to
the **dynamic** flow-criticality that only exists at runtime. Design-time = *projection* (manifest → o11y
artifacts); runtime = *propagation* (business context → every span) — **two projections of one business-context
source.** The mapping MUST be single-sourced across both (see §8).

### 2c. Carrier selection — baggage is not the only way to get `flow` onto a span (metabolized: synthesis C5)

Baggage propagation (steps 2–3) is **one carrier**, not the only one. `business.flow` is *recoverable post-hoc*
from the assembled trace's **root span**, which already carries the entry route — so a **collector-side
trace-derivation pass** can stamp `flow` *down* onto the trace's spans with **zero baggage propagation**. That
splits the levers by *timing*: baggage is strictly necessary only for the **real-time-at-ingest** levers (tail-sample
retention, the §4b premium-sink cost tiering, live P1 alerting — decisions taken *before* the trace is assembled);
the **analysis/RCA** levers (§4's blast-radius, flow-aware prioritization, cross-signal pivot — taken *after*
assembly) can use trace-derivation and **dominate on brownfield/async/polyglot fleets** where a propagator rollout
is expensive or where baggage structurally breaks across queue/batch/serverless/third-party hops.

| Carrier | Timing it serves | Levers | Rollout cost | Fails when |
|---|---|---|---|---|
| **Baggage** (steps 2–3) | **real-time / at-ingest** | tail-sample, §4b premium-sink tiering, live alerting | needs the propagator on *every* hop (§5 chain fragility) | async/queue/batch/serverless/3rd-party hops break the chain |
| **Trace-derivation** (collector, post-assembly) | **analysis / RCA** | §4 blast-radius, prioritization, cross-signal pivot | **$0 propagator rollout** (collector-only) | can't inform a decision that must be made *before* the trace assembles |

Both carriers **read the one declared `route→flow→criticality` map** (§7) — so trace-derivation is a *sixth*
consumer of that single source, and a hybrid deployment (baggage where real-time is needed, trace-derivation
elsewhere) is the honest default: brownfield shops get most of the RCA value with no propagator rollout at all.
*(Maturity: trace-derivation carrier = roadmap; baggage carrier = the P1 build above.)*

## 2b. Materialization is DECLARATIVE-first (k8s-derived) — code only for the gaps

The earlier framing implied per-language SDK code. In a k8s + OTel environment, almost all of it is **declarative,
zero-app-code** — which dissolves most of the polyglot chain-fragility guardrail. Two mechanisms do the work, and
both are **pod-annotation-driven**, so they align natively with ContextCore's `contextcore.io/*` annotation model:

- **Generation + baggage propagation → the OTel Operator.** An `Instrumentation` CRD declares the propagators
  (`OTEL_PROPAGATORS=tracecontext,baggage`) and the `BaggageSpanProcessor`; a pod annotation
  (`instrumentation.opentelemetry.io/inject-<lang>`) makes a mutating webhook inject the real SDK. Generation,
  propagation, and materialization become **CRD config, not code**. *(Go is the rough edge — eBPF-based, less
  mature than Python/Java/Node/.NET injection.)*
- **Static business context → the `k8sattributes` processor.** Collector-side, it pulls named `contextcore.io/*`
  pod annotations onto every signal — zero SDK code, any language. Cleaner than the in-SDK `detector.py` for the
  static half.
- **The flow SEED can be MESH config, not app code.** For route-discriminable flows (most), an Istio/Envoy header
  rule stamps the baggage at the trusted boundary: `route =~ /cart/checkout → baggage:
  business.flow=checkout,business.criticality=critical`. App code is only needed when the flow depends on request
  *content* (body/segment/flag), not the route. So the truly-irreducible piece is **authoring the route → flow →
  criticality mapping** — business knowledge (the same criticality source-of-truth), expressed declaratively.

| Concern | Operator auto-instr | eBPF (Beyla/Odigos) | `k8sattributes` | manual SDK / `instrumentation-gen` |
|---|:--:|:--:|:--:|:--:|
| Base traces/metrics (polyglot) | ✅ | ✅ | — | fallback |
| Baggage propagation | ✅ | ◐ maturing | — | ✅ |
| Static business context | (via SDK) | — | ✅ **best** | — |
| Flow seed | — (mesh does it) | — | — | only if not route-discriminable |
| **Absent** metrics / custom business spans | ✕ | ✕ | ✕ | ✅ **its niche** |

**`instrumentation-gen` is NOT obsolete — it is the coverage-gap fallback:** absent metrics no probe can infer,
unsupported languages / no-injection environments, and custom app-semantic business spans. **The default is
declarative** (annotate the pod, configure the collector, add the mesh rule); code is the exception, not the rule.

> **Classical instrumentation vs business instrumentation — two axes.** There are **two axes** to the
> word "instrumentation," and this design lives on the second. **Classical (technical) instrumentation**
> is *source-side signal generation*: code, auto-instrumentation, or **eBPF** that observes the running
> system and emits telemetry that didn't exist before. **Business instrumentation** is the second,
> distinct discipline: making the *business dimension* of a system observable by projecting **declared**
> business meaning (criticality, flow, value) onto the telemetry your classical instrumentation already
> emits — the collector-side move the OTTL `transform/business` processor below performs — so business
> questions become answerable. **The coverage RCA is the proof** ("are our *critical* services observed?"
> — unanswerable before the enrichment, answerable after). The honest caveat: business instrumentation is
> **not** source-side signal generation — its information is **declared, not discovered**, and it **rides
> on** classical instrumentation's base signal. We do not redefine instrumentation; business
> instrumentation is a distinct axis added alongside it.

## 3. What OTTL can and can't do (the materialize-first rule)

**OTTL cannot read runtime baggage** — by the time telemetry reaches the collector, baggage is not on the span
unless the span processor already materialized it. Order is non-negotiable: **materialize (SDK) → then OTTL
(collector).** Once the business attributes exist, OTTL is the collector-side **policy engine**:

- **Route** critical-flow telemetry to a hot path (100% retention, P1-eligible) vs sampled browse — the per-*flow*
  version of ContextCore's per-*service* sampling.
- **Tail-sample** by `flow.business.criticality` (keep every critical-flow trace).
- **Cross-signal copy** — stamp the flow business attrs onto spanmetrics + correlate to logs, so RCA pivots by
  business context across all three signals (extends "Loki queryable by business.criticality" to flow-scoped).
- **Derive** `business.impact` (e.g. criticality × error).

## 4. The RCA payoff (grounded in ContextCore `coverage_rca` / `remediation`)

Today RCA picks *"the highest-criticality dark service"* (static). With flow-baggage:

1. **Flow-aware prioritization** — a dark/failing service *on live critical flows* outranks the same service seen
   only on browse. Static "critical dark service" → dynamic "dark service on the most critical flows."
2. **Business-impact blast radius** — *"which revenue-primary flows failed?"* becomes answerable, because every
   span carries flow criticality. Business-impact RCA, not technical-service RCA.
3. **Journey-step attribution** — carry `business.journey_step` (the Round-3 journey: browse→addToCart→checkout)
   and RCA attributes a failure to *"the checkout step"* across services.
4. **Cross-signal pivot** — one business context on traces + metrics + logs → correlate by `flow=checkout,
   criticality=critical`.

## 4b. The sink filter — the concrete egress home for flow routing

ContextCore's `pilot/models/telemetry_sink.py` (FR-16) is a per-app registry of telemetry EGRESS destinations
(vendor/scheme/endpoint), deliberately **Phase-1 inert** — schema + validation only, no router/sender/deliver. Its
versioned schema exists so *"a Phase-2 **router** can add delivery policy without reinterpreting Phase-1 fields"*
(`:26-28`, `:132-134`). **That Phase-2 delivery-policy router IS the "sink filter"** — it decides *which telemetry
egresses to which sink* — and it is the natural, concrete home for §3's flow routing:

| Layer | What it is | Status |
|---|---|---|
| `TelemetrySink` registry | the destinations | ✅ Phase-1 built |
| **Phase-2 delivery-policy router** | **the sink filter** (which telemetry → which sink) | ⬜ planned seam |
| OTTL (collector) | a candidate *implementation* of that router | ⬜ |
| **`flow.business.criticality`** (baggage) | the dynamic **predicate** it routes on | ⬜ |

**Payoff — per-FLOW cost/value tiering at egress.** A sink filter on *static per-service* criticality sends all
`productcatalogservice` telemetry to one tier (the service is `high`). With flow-criticality the *same service's*
spans route by the flow they serve — a productcatalog span in a checkout flow → the premium high-retention sink;
in a browse flow → the cheap/sampled sink (or dropped). You pay for fidelity on revenue-primary flows and next to
nothing on browse **even though both traverse the same services** — a cost lever static per-service criticality
structurally cannot pull.

**Honest nuance — a TRACES/LOGS lever, not a metrics one.** Traces and logs are per-record → route each by its
materialized `flow.business.criticality`. **Metrics are pre-aggregated** → per-flow sink routing is lossy unless
`flow` becomes a metric dimension (reintroducing the cardinality guardrail). Flow-aware egress shines on traces
(route + tail-sample the premium sink) and logs; treat metrics separately.

**Trust boundary → now a COST-abuse vector.** If the sink filter buys premium egress by flow-criticality, a client
stamping `criticality=critical` in baggage buys premium retention on your dime. Same fix as §5: set/overwrite
business baggage only at a trusted entry.

## 5. Guardrails (the discipline that makes it safe)

- **Trust boundary** — baggage travels in headers; **set/overwrite business baggage at a trusted entry**, never
  trust client-supplied baggage (a client claiming `criticality=critical` to jump the sampling queue is a real abuse).
- **Chain fragility** — *every* service must carry the baggage propagator; one polyglot gap = silent context loss
  downstream of it. (§7 mitigates via generation.)
- **Materialization gotcha** — baggage without the span processor propagates but never lands on telemetry
  (invisible). The #1 mistake.
- **Cardinality** — low-cardinality dims (flow/criticality/tier) are fine on metrics; high-cardinality
  (`transaction_id`) → traces only, never materialize onto metrics.
- **Minimalism** — put the *minimal flow-discriminating* dimensions in baggage, not the whole project context
  (header bytes on every hop).

## 6. Cross-repo ownership + phased work

| Phase | Owner | Work |
|---|---|---|
| **P0 — the contract** | both | Fix the minimal baggage key set (`business.flow`, `business.criticality`, `business.tier`) + the trusted seeding point. Everything else is elaboration. |
| **P1 — propagate + materialize** | **startd8-sdk** | (a) configure a composite propagator (`tracecontext` + `baggage`) in `otel.py`; (b) a `BaggageSpanProcessor` that materializes the agreed keys → span attributes; (c) seed the baggage at the trusted entry from `build_criticality_map` / the ContextCore resolution. |
| **P2 — materialization (DECLARATIVE-first)** | **startd8-sdk + platform** | Default = **k8s-derived, zero app code** (§2b): OTel **Operator** `Instrumentation` CRD (propagators + BaggageSpanProcessor, pod-annotation inject) + **`k8sattributes`** for the static half + a **mesh header rule** for the flow seed. `scaffold_codegen/instrumentation_gen.py` is demoted to the **coverage-gap fallback** (absent metrics, unsupported langs, custom business spans). |
| **P3 — OTTL policy** | **ContextCore** | collector OTTL: route/tail-sample by `flow.business.criticality`; copy business attrs onto spanmetrics + log correlation. Reuse the DerivationRule mapping (§8). |
| **P4 — flow-aware RCA** | **ContextCore** | extend `coverage_rca` / `remediation` to weight by *flow* criticality (baggage) alongside *service* criticality (`build_criticality_map`); add the business-impact blast-radius + journey-step queries. |
| **P5 — sink filter** | **ContextCore** | the Phase-2 delivery-policy router over `telemetry_sink.py` (§4b): route/tier telemetry to sinks by `flow.business.criticality` (traces/logs; metrics separately). OTTL is a candidate implementation. |

## 7. Single-source-of-truth mandate (ties to the criticality lint)

One authored criticality now feeds **five** consumers: the design-time `DerivationRule`, the runtime **baggage
seed**, the **OTTL** policy, the **authoring lint** (`HANDOFF_criticality-authoring-lint.md`), and the **sink
filter** (Phase-2 delivery router, §4b), plus — per §2c — a **sixth**: the trace-derivation carrier. The
**criticality→severity mapping** (`critical→P1`, sampling rates, SLO thresholds) MUST be authored once and shared
by the DerivationRule (design-time) and the OTTL (runtime) — else the two drift and a critical flow is sampled
one way at design and another at runtime. Extend the lint's spirit: guard that the mapping has one home.

### 7a. From linted table to GOVERNED REGISTRY — the map is a decision-point, not a shared table (metabolized: synthesis C1)

The framing above treats the `route→flow→criticality` map as a shared table guarded by a **consistency lint**.
Three independent analogy domains — FinOps tag-policy, zero-trust OPA (PDP/PEP), and product-analytics
tracking-plans — **converge** that a declared vocabulary feeding N consumers needs a *governed, versioned, enforced
**registry***, not merely a consistent table. The load-bearing artifact is the **registry itself** (declared-table
× join-key × stage × consumers), *not* the `BaggageSpanProcessor` — which **vindicates and sharpens the moat
thesis: the moat is the registry, not the mechanism.** The four properties a governed registry adds over a linted
table:

- **Allowed-values enum** — `flow`, `criticality`, `tier` are closed vocabularies; unknown values are rejected at
  authoring time, not discovered at query time.
- **Coverage %** — *"what fraction of live traffic carries a mapped flow?"* — the reach metric FR-6 needs.
- **An unmapped bucket** — the **honest denominator**: traffic that matched *no* declared route→flow rule is
  explicitly bucketed, never silently dropped or mis-attributed.
- **A lifecycle** — `draft → active → deprecated`, so a flow can be retired without a big-bang rename across all
  six consumers.

**The Weaver connection — the governance home already exists.** ContextCore already runs an **OTel Weaver semconv
registry** (`ContextCore/semconv/registry_manifest.yaml`), and `# - registry/business.yaml` is **reserved as a
planned Phase-2 group** in that manifest today. Weaver's design admits `weaver registry check` running **Rego
policies** — i.e. an externalized **PDP the consumers query**, the zero-trust-mature answer to the very §7 drift
this note already fears, **one rung past a consistency lint**. So the metabolized target is concrete: the
`route→flow→criticality` map becomes a Weaver **`business.yaml` registry group + policy**, not an ad-hoc table each
consumer copies. *(Maturity — honest: the Weaver registry is **ContextCore-shipped** for `task.*`/`lesson.*` today;
`business.yaml` is a **planned Phase-2 group** (reserved in the manifest, not yet authored); `weaver registry
check` + Rego policies are **roadmap** for ContextCore — no `.rego` policy files exist there yet.)*

**Over-abstraction guard (load-bearing).** Externalize to a full queryable PDP **only at ≥2 declared tables or on
real observed drift.** At **one** declared table (`business.*`), the **lint + `weaver registry check`** is the
right rung — a full PDP for a single vocabulary would itself be accidental complexity. The registry *structure*
(enum, coverage %, unmapped bucket, lifecycle) is worth adopting now; the *externalized decision engine* is not,
until a second declared table earns it in (see §7b).

### 7b. The deeper invariant — declarative context joins over telemetry (metabolized: synthesis C3)

`detector.py` (SDK-side, static business context) and the `k8sattributes` processor (collector-side) already run
the **same operation** at two different stages: a **join** of a *declared attribute table* against a *live signal*
on a **key** (the pod / service identity). "Dimension" is just the *output shape* of that join — the primitive is
**join-on-key**. Seen this way, `business.*` is the **beachhead, not the ceiling**: the same machinery admits other
authored tables joining on service / route / flow keys —

- **org-chart / on-call** (join → owner, escalation target),
- **service-catalog / CMDB** (join → team, lifecycle, dependencies),
- **cost model** (join → $/unit, budget owner),
- **SLO** (join → objective, error budget),
- **compliance / data-classification** (join → residency, obligation).

Each is a declared table joined onto telemetry on a key the signal already carries — the registry of §7a is the
general artifact, and `business.flow` criticality is one instance of it.

**Over-abstraction guard (load-bearing).** Generalize the **registry/contract now** — it is cheap, mostly *renaming*
existing artifacts (the map is already a declared-table × join-key × consumers shape; §7a's registry properties
apply unchanged to any of these tables). But **DEFER any generic join *engine*** until table #2 is *actually wired*:
a framework built for a single use (`business.*` today) is exactly the accidental complexity this note forbids.
Ship the beachhead, keep the framing, build the engine only when the second table pays for it.

## 8. Coherence / tie-ins

- **instrumentation-gen** is the answer to chain fragility (P2): generate the baggage plumbing per language.
- **Single-source criticality** (the lint) becomes more load-bearing: 4 consumers of one authored value.
- **Narrow-waist symmetry** — OTel is the telemetry waist; baggage is how the *business* waist's payload rides
  *through* it at runtime, the twin of the design-time codegen projection.

## 9. The one decision first + non-goals

- **Decide first:** the minimal baggage key set (`flow`/`criticality`/`tier`) and the trusted seeding point.
- **Non-goals:** no custom propagator (standard W3C baggage); no PII/high-cardinality/secret in baggage; do NOT
  collapse `flow.*` into `service.*`; OTTL does NOT read baggage (materialize first); do not put the whole project
  context on the wire.
