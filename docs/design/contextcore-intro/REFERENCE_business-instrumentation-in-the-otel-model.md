# Reference: business instrumentation in the OpenTelemetry model (+ how `business.flow` is created, and who else can do it)

**Type:** reference / positioning · **Date:** 2026-08-19 · **Audience:** technical evaluators, OTel-literate buyers
**Answers three questions:** (1) does business instrumentation *fit* the OTel signals model? (2) how is
`business.flow` actually created? (3) can/do existing observability solutions do this today? Honest about maturity
and about where we are *not* uniquely capable.

---

## 1. The OTel model — signals + cross-cutting layers

OTel is **signals** (data shapes, each with its own data model/API/SDK/pipeline) plus **cross-cutting layers**
(orthogonal to signal type):

- **Signals:** Traces, Metrics, Logs (stable); Profiles (stabilizing); Events (on Logs).
- **Cross-cutting:** **Context** (propagation substrate) · **Baggage** (KV pairs propagated in Context — *not*
  telemetry; attaching it to signals is an explicit, cautioned opt-in) · **Resource** (attributes describing the
  producer; on *every* signal) · **Semantic Conventions** (standardized attribute *meaning*, by domain: `http.*`,
  `db.*`, `rpc.*`, `k8s.*`, `deployment.*` …) · **Instrumentation Scope**.

**The test for "is X a signal?": does it have its own data model?** Traces = spans+causality; Metrics =
time-series; Logs = records.

## 2. Where business instrumentation fits — a dimension, not a signal

Business context (`business.criticality`, `business.flow`, `business.value`, `business.owner`) has **no independent
data model** — it's *attributes*. By OTel's own test it **is not a signal**; it **is** a cross-cutting attribute
dimension. It composes existing primitives:

| Business-instrumentation element | OTel layer it uses |
|---|---|
| Static, per-service context (annotation → attribute) | **Resource** |
| Dynamic, per-request context (`business.flow`) | **Baggage / Context** → materialized onto spans |
| The `business.*` vocabulary | **Semantic Conventions** (a *new* domain) |
| Enrichment / routing / derivation | **Collector processing** (OTTL), operating *on* signals |
| Result | rides **all** signals as attributes |

So: **not a fourth pillar — a business-semantic dimension carried by Resource (static) + Baggage (dynamic),
expressed as attributes on every signal, enforced at the SDK + collector.** The cross-cutting layers exist to carry
exactly this kind of orthogonal dimension.

## 3. It lives in the model's two under-populated seams (why "does it fit?" is a fair question)

1. **The missing `business.*` semantic-conventions domain.** OTel has rich *technical* namespaces and **no business
   one** — no `business.criticality`, no `business.flow`. Business instrumentation is the business-domain member of
   the semantic-conventions layer *that doesn't exist yet*. It fits the model's shape perfectly but has no ratified
   vocabulary — which is the "own the semconv standard" opportunity (doc 05). It populates a blank region; it
   doesn't extend the model.

   The namespace already has a **reserved home**: ContextCore's OTel **Weaver** registry manifest
   (`ContextCore/semconv/registry_manifest.yaml`) lists `# - registry/business.yaml` as a **planned Phase-2** group,
   alongside the shipped Phase-1/2 groups (task, project, sprint, agent, lesson). So the absent namespace is
   *reserved-not-yet-populated* — the slot exists, the group file does not. Weaver is its **governance mechanism**:
   `weaver registry check` validates the registry YAML (already the enforced check for the shipped groups) and
   `live-check` + Rego policy can gate real emitted telemetry against the declared conventions. Honest maturity:
   `business.yaml` is **planned, not shipped** — the reservation and the governance tooling exist; the ratified
   `business.*` group has not yet been authored.
2. **The opt-in Baggage→telemetry seam.** OTel keeps baggage *out* of telemetry by default (propagation-only, with
   security/cardinality cautions) while *providing* the `BaggageSpanProcessor` to bridge it on demand. Business
   instrumentation operationalizes that opt-in bridge as a disciplined practice — which is why the guardrails
   (trust boundary, low cardinality, materialize-first) are load-bearing.

## 4. Signal-agnostic strength

Because it's a *dimension*, it applies to **every signal, present and future** — the same `business.flow` rides
traces, metrics, logs, and by extension **Profiles** ("which flow was this CPU profile under?") and **Events**
("checkout completed, $X"). You never re-implement it per signal. A *new signal* would have to be integrated
pillar-by-pillar; a dimension is gained for free.

## 5. Deep-dive — how `business.flow` is created

A four-step chain; the hard step is the first:

1. **Declare the mapping** — a `route → flow (→ criticality)` table (*"`/cart/checkout` = the `checkout` flow,
   revenue-primary, critical"*). A **business/product judgment**; the single source of truth.
2. **Seed at a trusted boundary** — a mesh/gateway header rule (Istio/Envoy) stamps `baggage:
   business.flow=checkout` by route match — declarative, no app code. (App code only when the flow is determined by
   request *content*, not route.)
3. **Propagate** — it rides the W3C baggage header through every hop (SDK / auto-instrumentation propagator).
4. **Materialize** — the `BaggageSpanProcessor` copies it onto every span → queryable downstream.

**The creative act is step 1 — the classification** (*declared, not discovered*; nothing infers "this is a
checkout"). Two honest subtleties:
- **Per-request vs per-journey** — `business.flow` tags a *request's role* in a journey; a multi-request journey
  (add-to-cart → view-cart → place-order) also needs a **journey/session ID** to stitch steps.
- **Maturity** — the *dynamic* `business.flow` (baggage) is **roadmap**; the *static* business dimension
  (`business.criticality` via annotations + the `transform/business` OTTL processor) is **shipped**.

## 6. Can / do existing o11y solutions do this today?

**(a) The plumbing is open — so, technically, mostly yes via DIY.** Baggage, the `BaggageSpanProcessor`, mesh
header rules, OTTL, high-cardinality slicing — all available to anyone on OTel. No single component is proprietary.

**(b) But almost nobody does it as a *governed, declared, end-to-end* dimension** wired into RCA and cost. The gap
is the **discipline / control plane**: a single-source `route→flow→criticality` mapping, trusted-boundary seeding,
guaranteed propagation + materialization, and the wiring into fault-isolation RCA + value-based tiering. That
governed composition is the novelty — not any part of it.

**(c) The closest adjacent things, and how they differ:**

| Solution | What it does | Why it's not `business.flow` |
|---|---|---|
| Custom span attributes (every vendor) | add a `business.flow` tag anywhere | not *propagated* end-to-end, not governed/declared-once — on the entry span, not the deep redis call |
| Dynatrace Business Analytics / Business Events | capture business *outcomes* (orders, revenue) as events | outcomes-as-events, not *intent-as-a-dimension* propagated through the call graph to discriminate RCA |
| RUM session/journey tracking (Datadog RUM…) | front-end sessions/journeys, correlated to backend by ID | UX/session-centric, URL-inferred — not a governed business-journey dimension on backend spans |
| Honeycomb (wide events, BubbleUp) | superb substrate to *slice by* `business.flow` and discriminate faults | you bring the propagation + governance; it provides the analysis, not the discipline |
| Chronosphere / Cribl | pipeline cost tiering by *volume/cardinality* | would *consume* `business.flow`; tiers by data volume, not business value |

**Bottom line:** the differentiation is **not** "we emit an attribute nobody else can" (false — anyone can add a
tag). It's that we make `business.flow` a **governed, declared, propagated, end-to-end dimension with one source of
truth, wired into RCA and cost — a *discipline* (business instrumentation), not a DIY assembly.** Because the parts
are open, the moat is the **control plane + the category + first-mover**, not the mechanism. A team *can* DIY it;
the value is that they don't have to, and that it stays correct and single-sourced.

## 7. The honest tension + one-line

In strict OTel vocabulary none of these primitives is "instrumentation" — resource detection + baggage
materialization are *SDK config + context propagation*; OTTL is *collector processing*. So **"business
instrumentation" is a discipline that *composes* model primitives toward a business end — not a model-level
term.** It fits by composition; its home is the semantic-conventions layer.

**One-line:** *business instrumentation fits the OTel model as a cross-cutting business-semantic dimension —
Resource (static) + Baggage (dynamic), attributes on every signal — that populates OTel's absent `business.*`
namespace; it doesn't stretch the model, it completes an empty part of it.*
