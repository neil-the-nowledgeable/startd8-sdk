# ContextCore — The Nuts and Bolts

*Doc 4 of 5 — "Introduction to ContextCore." The deep technical reference. Audience: SREs and
platform engineers who will actually wire this into a cluster. Docs → [01 (ELI5)](01_ELI5_how-it-works-and-why-better.md)
· [02 (features)](02_FUNCTIONAL_description.md) · [03 (architecture)](03_TECHNICAL_description-high-level.md) · **04 (you are here)** ·
[05 (business case)](05_GTM_swot-moat-commercialization.md).*

> **Every YAML/OTTL snippet below is ILLUSTRATIVE — adapt namespaces, ports, selectors, and versions
> to your cluster. Nothing here was generated from a live cluster; treat it as a shape to start from,
> not a copy-paste manifest.** Ground truth for the ContextCore specifics is cited inline
> (`detector.py`, `criticality.py`, `telemetry_sink.py`).

The whole design is one pipeline in four roles, and this doc walks each in order:

```
ORIGINATE  → PROPAGATE → MATERIALIZE → POLICY
(annotations   (baggage    (span attrs   (OTTL routes /
 + baggage      rides        land on       tail-samples /
 seed)          every hop)   telemetry)    tiers by them)
```

Two context flavors ride this pipeline into the **same `business.*` attribute namespace**: a **STATIC**
per-service half (K8s annotations → resource attributes, *shipped*) and a **DYNAMIC** per-request half
(baggage → span attributes, *planned*). Keep them mentally distinct — different granularity, different
OTel layer, same namespace.

### Classical instrumentation vs business instrumentation — two axes

There are **two axes** to the word "instrumentation," and this doc wires up both. Keep them distinct or
you will mis-scope what each mechanism does.

- **Axis 1 — classical (technical) instrumentation** = *source-side signal generation*: code, the
  Operator-injected SDK (§1), or **eBPF** that observes the running system and **emits telemetry that
  didn't exist before**. This is the base-signal generator.
- **Axis 2 — business instrumentation** = making the *business dimension* of a system observable by
  projecting **declared** business meaning — criticality, flow, value — onto the telemetry classical
  instrumentation already emits. Its mechanism here is the generated OTTL **`transform/business`**
  processor (§4), which stamps that declared meaning onto **already-emitted** signal so business
  questions become answerable. **The coverage RCA is the proof** ("are our *critical* services observed?"
  — unanswerable before the enrichment, answerable after). The `k8sattributes` enrichment (§2) is the
  static-half instance of business instrumentation.

**The honest caveat (do not soften it):** business instrumentation is **not** source-side signal
generation — its information is **declared, not discovered**, and it **rides on** classical
instrumentation's base signal (axis 1). We do not redefine instrumentation; business instrumentation is a
distinct discipline added alongside it.

This double-nature is why ContextCore's `utils/instrumentation.py` does **double duty**: it derives what
a service **should emit** (the classical signal-generation concern — feeding `scaffold_codegen`'s
`instrumentation-gen` fallback) *and* generates the business-instrumentation **`transform/business`
enrichment processor** that stamps the declared business dimension onto that signal. The generated
processor is **shipped**; `coverage/snapshot.py` (EC-10) consumes its `business_criticality` label for
the coverage RCA. Flow-scoped baggage criticality (§3) is the **roadmap** extension of business
instrumentation — the same declared-dimension move, made per-request.

---

## 1. Origination A — the OTel Operator `Instrumentation` CRD (propagation + materialization)

The default way to get **baggage propagation** and **materialization** into polyglot pods with **zero
application code** is the OpenTelemetry Operator. One `Instrumentation` CRD declares the propagator
array and the span processor; a **pod annotation** triggers a mutating webhook that injects the real
language SDK at pod start.

```yaml
# ILLUSTRATIVE — adapt to your cluster. OTel Operator Instrumentation CRD.
apiVersion: opentelemetry.io/v1alpha1
kind: Instrumentation
metadata:
  name: contextcore-baggage
  namespace: boutique
spec:
  exporter:
    endpoint: http://otel-collector.observability:4317
  # The propagator array is the TRANSPORT config. tracecontext = W3C trace ids;
  # baggage = the W3C baggage header that carries business.* key/values every hop.
  propagators:
    - tracecontext
    - baggage
  # MATERIALIZE: the BaggageSpanProcessor copies selected baggage keys onto EVERY
  # span as span attributes. Without this, baggage propagates but never lands on
  # telemetry — the #1 mistake (see §6).
  python:
    env:
      - name: OTEL_PROPAGATORS
        value: "tracecontext,baggage"
      # Vendored/community BaggageSpanProcessor, wired via a startup hook.
      # Copies only the allow-listed business.* keys (NOT all baggage — see §6 cardinality).
      - name: OTEL_BAGGAGE_KEYS_TO_COPY
        value: "business.flow,business.criticality,business.tier"
```

Opt a workload in with a **pod-template annotation** (not a collector concern — this is the injection
trigger):

```yaml
# ILLUSTRATIVE — pod template of the checkout Deployment.
spec:
  template:
    metadata:
      annotations:
        instrumentation.opentelemetry.io/inject-python: "true"
        # Same trigger family per language: inject-java / inject-nodejs / inject-dotnet.
```

**Go eBPF caveat.** Injection for Python/Java/Node/.NET is a mature mutating-webhook path. **Go is the
rough edge**: it has no runtime SDK auto-injection, so the Operator uses an **eBPF-based** auto-instr
(`inject-go`) whose **baggage context-propagation support is less mature** than the SDK path. For Go
services on critical flows, plan on either (a) accepting reduced baggage fidelity, or (b) the
`instrumentation-gen` fallback with an explicit SDK + `BaggageSpanProcessor` in-code (§7). Do not
assume a Go pod carries baggage just because you annotated it.

---

## 2. Origination B — the `k8sattributes` processor (static business context)

The **static** half — a service's *general* criticality/owner/SLOs — does not need app code or baggage
at all. The collector's `k8sattributes` processor reads the very `contextcore.io/*` pod annotations that
ContextCore's own `ProjectContextDetector` reads, and stamps them onto **resource attributes** on every
signal. This is the collector-side twin of `detector.py`, and for the static half it is *cleaner* than
the in-SDK detector (any language, zero SDK dependency).

The mapping below **mirrors ContextCore's real `ANNOTATION_TO_ATTRIBUTE` map** in
`ContextCore/src/contextcore/detector.py:182-222` — keep the two single-sourced so the collector path
and the SDK-detector path agree:

```yaml
# ILLUSTRATIVE — collector config. k8sattributes processor pulling contextcore.io/* annotations.
processors:
  k8sattributes:
    auth_type: serviceAccount
    passthrough: false
    extract:
      metadata:
        - k8s.namespace.name
        - k8s.pod.name
        - k8s.deployment.name
      annotations:
        # tag_name = the resource attribute to write; key = the pod annotation to read.
        # These MIRROR detector.py's ANNOTATION_TO_ATTRIBUTE exactly (single-source it).
        - { tag_name: business.criticality,        key: contextcore.io/criticality,       from: pod }
        - { tag_name: business.owner,               key: contextcore.io/owner,             from: pod }
        - { tag_name: business.value,               key: contextcore.io/business-value,    from: pod }
        - { tag_name: business.cost_center,         key: contextcore.io/cost-center,       from: pod }
        - { tag_name: project.id,                   key: contextcore.io/project,           from: pod }
        - { tag_name: project.epic,                 key: contextcore.io/epic,              from: pod }
        - { tag_name: project.task,                 key: contextcore.io/task,              from: pod }
        - { tag_name: design.doc,                   key: contextcore.io/design-doc,        from: pod }
        - { tag_name: design.adr,                   key: contextcore.io/adr,               from: pod }
        - { tag_name: requirement.availability,     key: contextcore.io/slo-availability,  from: pod }
        - { tag_name: requirement.latency_p99,      key: contextcore.io/slo-latency-p99,   from: pod }
        - { tag_name: requirement.latency_p50,      key: contextcore.io/slo-latency-p50,   from: pod }
        - { tag_name: requirement.error_budget,     key: contextcore.io/error-budget,      from: pod }
        - { tag_name: deployment.environment.name,  key: contextcore.io/environment,       from: pod }
        - { tag_name: risk.type,                    key: contextcore.io/risk-type,         from: pod }
        - { tag_name: risk.priority,                key: contextcore.io/risk-priority,     from: pod }
```

And the annotations themselves, on the workload (the **static home** for criticality — see §5):

```yaml
# ILLUSTRATIVE — checkout Deployment pod annotations = the static per-service business context.
metadata:
  annotations:
    contextcore.io/criticality: critical
    contextcore.io/owner: "team-checkout"
    contextcore.io/slo-availability: "99.95"
    contextcore.io/slo-latency-p99: "250ms"
    contextcore.io/environment: production
```

Note the vendor-neutrality baked into the map: `deployment.environment.name` is standard OTel semconv
that Datadog reads as `env`, Splunk as `deployment.environment`, Grafana as `deployment_environment`
(`detector.py:184-188`). You declare context once, portably.

---

## 3. The flow SEED — service-mesh header manipulation (Istio/Envoy)

The static half tells you *what a service is*. The **dynamic** half tells you *which business flow a
given request serves*. For **route-discriminable** flows (the common case), you seed the baggage in the
**mesh, not the app** — an Istio/Envoy header-manipulation rule keyed on the route:

```yaml
# ILLUSTRATIVE — Istio VirtualService seeding business baggage at the trusted boundary.
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: frontend-flow-seed
  namespace: boutique
spec:
  hosts: ["frontend.boutique.svc.cluster.local"]
  http:
    - match:
        - uri: { prefix: /cart/checkout }
      headers:
        request:
          set:
            # W3C baggage header format: comma-separated key=value.
            # SET (overwrite) — never `add` — so any client-supplied baggage is replaced.
            baggage: "business.flow=checkout,business.criticality=critical,business.tier=revenue-primary"
      route:
        - destination: { host: frontend.boutique.svc.cluster.local }
    - match:
        - uri: { prefix: /product }
      headers:
        request:
          set:
            baggage: "business.flow=browse,business.criticality=low,business.tier=discovery"
      route:
        - destination: { host: frontend.boutique.svc.cluster.local }
```

Two properties make this correct and safe:

- **Trusted-boundary requirement (overwrite, not merge).** Business baggage is set/**overwritten** at a
  single trusted ingress, never trusting client-supplied baggage. A client that self-labels
  `criticality=critical` to jump the sampling queue — or to buy premium retention on your dime (§6) —
  is a real abuse; the mesh `set` at the boundary neutralizes it.
- **Route-vs-content discriminable boundary.** The mesh can seed the flow **only when the flow is
  derivable from the route** (path/host/method). When the flow depends on request *content* (a body
  field, a feature flag, a cart segment), the route rule can't see it — that is the one case that falls
  to app-code / `instrumentation-gen` seeding (§7). Draw this line deliberately: most flows are
  route-discriminable; the content-discriminable minority is the exception, not the default.

---

## 4. Policy — OTTL in the collector (the MATERIALIZE-FIRST rule)

Once business attributes are **on the spans** (materialized by §1's span processor and/or §2's
`k8sattributes`), the collector's OTTL becomes the runtime **policy engine** — routing, tail-sampling,
and deriving by `flow.business.criticality`.

> **MATERIALIZE-FIRST — non-negotiable.** **OTTL cannot read runtime baggage.** By the time telemetry
> reaches the collector, baggage is *not on the span* unless a span processor already copied it there.
> Order is: **materialize (SDK/Operator) → then OTTL (collector).** Every OTTL example below assumes the
> `business.*` attributes already exist as span attributes. If your OTTL conditions never match, this is
> the first thing to check.

**Route critical flows to a premium path + derive `business.impact`:**

```yaml
# ILLUSTRATIVE — transform processor. Assumes business.* ALREADY materialized onto spans.
processors:
  transform/business_impact:
    trace_statements:
      - context: span
        statements:
          # Derive an impact flag: critical flow AND an error status.
          - set(attributes["business.impact"], "high")
            where attributes["flow.business.criticality"] == "critical" and status.code == STATUS_CODE_ERROR
          # Cross-signal copy: stamp flow criticality onto spanmetrics dimension so metrics/logs pivot too.
          - set(attributes["business.criticality"], attributes["flow.business.criticality"])
            where attributes["flow.business.criticality"] != nil
```

**Tail-sample: keep every critical-flow trace, sample browse hard:**

```yaml
# ILLUSTRATIVE — tail_sampling processor keyed on the materialized flow criticality.
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: keep-critical-flows
        type: string_attribute
        string_attribute: { key: flow.business.criticality, values: [critical], enabled_regex_matching: false }
      - name: sample-everything-else
        type: probabilistic
        probabilistic: { sampling_percentage: 5 }
```

**Tier telemetry to sinks by flow (routing/exporter selection):**

```yaml
# ILLUSTRATIVE — routing connector: premium retention for critical flows, cheap tier for browse.
connectors:
  routing:
    default_pipelines: [traces/cheap]
    table:
      - statement: route() where attributes["flow.business.criticality"] == "critical"
        pipelines: [traces/premium]
service:
  pipelines:
    traces/premium: { exporters: [otlp/premium-sink] }   # 100% retention, P1-eligible
    traces/cheap:   { exporters: [otlp/sampled-sink] }    # sampled / cheap
```

The load-bearing symmetry: this OTTL is the **runtime twin** of ContextCore's design-time
`DerivationRule` (`critical → P1`, `99.9%` SLO thresholds). Same criticality→severity mapping, applied
to the dynamic flow-criticality that only exists at runtime. §6 mandates single-sourcing that mapping.

---

## 5. The three criticality axes and their resolution precedence

Criticality is not one value — it is **three orthogonal axes**. Do not collapse `flow.*` into
`service.*`, or you reintroduce the drift the authoring lint exists to guard.

| Axis | Question | Home | Nature |
|---|---|---|---|
| `service.business.criticality` | how critical is this service, in general | resource attr · pod annotation · `build_criticality_map` | **static** |
| `project.business.criticality` | how critical is the initiative | manifest fallback (`spec.business.criticality`) | **static** |
| **`flow.business.criticality`** | how critical is **this request** | **baggage** (seeded §3) | **dynamic** |

**Per-service resolution precedence** is authoritative in ContextCore's
`coverage/criticality.py::build_criticality_map` — read it as the source of truth
(`criticality.py:73-105`):

1. `spec.targets[].criticality` — the authored **per-service override** (`TargetSpec`)
2. `live` label — a per-service value observed from a live metric label (the collector-enriched
   `business_criticality` dimension, EC-10)
3. `spec.business.criticality` — the **project-level fallback**
4. `"unknown"` — an **explicit sentinel**, its own bucket, **never silently coerced to `"low"`**
   (Context-Correctness-by-Construction: `criticality.py:24`, `:88-99`)

The **pod annotation** (`contextcore.io/criticality`) is the **static home** that materializes the
service axis onto telemetry (§2). It is a *third authoring home* alongside `spec.targets[].criticality`
and `spec.business.criticality` — which is exactly why §6's single-source lint must span all three.

---

## 6. Guardrails (the discipline that keeps it safe and cheap)

1. **Single-source the criticality→severity/tier mapping.** One authored `business.criticality` now
   feeds *five* consumers: the design-time `DerivationRule`, the baggage seed (§3), the OTTL policy
   (§4), the RCA weighting, and the sink filter (§4b/telemetry_sink). The `critical→P1` / sampling-rate
   / SLO-threshold mapping MUST have **one home**, or design-time and runtime drift (a flow sampled one
   way at gen, another at runtime). The **authoring lint** (`HANDOFF_criticality-authoring-lint.md`)
   guards the *authoring* homes — its drift check spans **manifest `spec.business.criticality` ↔
   `spec.targets[].criticality` ↔ pod annotation `contextcore.io/criticality`**. Don't hand-maintain two.

2. **Cardinality — flow tags on traces/logs, NOT high-cardinality onto metrics.** Low-cardinality dims
   (`flow`, `criticality`, `tier`) are safe as metric dimensions. **Never** materialize high-cardinality
   keys (`transaction_id`, `user_id`) onto metrics — that is a cardinality explosion. Put those on
   **traces/logs only**. Consequence for cost tiering: per-flow sink routing is a **traces/logs lever**
   (each record routes by its own materialized criticality); **metrics are pre-aggregated**, so per-flow
   metric routing is lossy unless `flow` becomes a (bounded) metric dimension. Treat metrics separately.

3. **Trust boundary is also a COST-abuse vector.** Because premium egress is *bought* by flow criticality
   (§4), a client stamping `criticality=critical` in baggage buys premium retention on your bill. The fix
   is the same as the security fix: **set/overwrite** business baggage **only at the trusted entry** (§3),
   never trust inbound client baggage.

4. **The governed sink registry.** Egress destinations are not free-form. ContextCore's
   `pilot/models/telemetry_sink.py` validates every sink **with zero network side effects**
   (`telemetry_sink.py:66-113`): an **allow-listed scheme** only
   (`https`/`grpc`/`grpcs`/`otlp`/`otlphttp` — `:31`), a host that is **not** loopback / private /
   link-local / cloud-metadata (`:33-34`, `:98-109`), and an `auth_reference` that must be an **opaque
   handle, never a secret value** (bearer tokens, `sk-`/`ghp_`/JWT shapes, embedded URL creds, and long
   high-entropy blobs are rejected — `:39-63`, `:111-112`). The registry is deliberately **Phase-1 inert**
   (schema + validation, **no** `send`/`route`/`deliver` — `:129-134`); the versioned schema exists so a
   Phase-2 delivery-policy router (the "sink filter") can add routing without reinterpreting a v1 field.
   Net: no secrets in sink configs, no private/metadata egress, fail-closed validation before anything is
   stored.

---

## 7. The coverage matrix — who covers what

No single mechanism covers everything. The four instrumentation surfaces partition the work; the fifth,
`instrumentation-gen`, is the **gap fallback**.

| Concern | Operator auto-instr (§1) | eBPF (Beyla/Odigos) | `k8sattributes` (§2) | manual SDK / `instrumentation-gen` (§7) |
|---|:--:|:--:|:--:|:--:|
| Base traces/metrics (polyglot) | ✅ | ✅ | — | fallback |
| **Baggage propagation** | ✅ | ◐ maturing | — | ✅ |
| Static business context | (via SDK detector) | — | ✅ **best** | — |
| Flow seed | — (mesh does it, §3) | — | — | only if **not** route-discriminable |
| **Absent** metrics no probe can infer | ✕ | ✕ | ✕ | ✅ **its niche** |
| Unsupported languages / no-injection env | ✕ | partial | — | ✅ |
| Custom app-semantic business spans | ✕ | ✕ | ✕ | ✅ |

**`instrumentation-gen` is NOT obsolete — it is the coverage-gap fallback.** The default is
**declarative** (annotate the pod, configure the collector, add the mesh rule). Code is the exception,
reserved for the three cells only `instrumentation-gen` can fill:

- **Absent metrics** a business needs but no probe can infer (generate the emitter — the SDK's
  `scaffold_codegen/instrumentation_gen.py`, language-agnostic renderer registry).
- **Unsupported languages / no-injection environments** where the Operator webhook can't reach.
- **Custom business spans** with app-semantic meaning (a "cart valued > $X" span) that no auto-instr
  knows to emit — and **content-discriminable flow seeds** (§3) the mesh can't derive from the route.

---

## 8. Maturity and caveats (shipped vs roadmap — stated plainly)

| Piece | Status |
|---|---|
| **Static half** — `contextcore.io/*` annotations → resource attributes via `ProjectContextDetector` | ✅ **shipped** (`detector.py`) |
| Per-service criticality resolution + precedence (`build_criticality_map`) | ✅ **shipped** (`criticality.py`) |
| `k8sattributes`-based static enrichment (collector twin of the detector) | ✅ standard OTel; wire it today |
| Governed sink **registry** (schema + fail-closed validation) | ✅ **shipped, Phase-1 inert** (`telemetry_sink.py`) |
| **Dynamic half** — baggage propagator + `BaggageSpanProcessor` + trusted-entry seed | 📄 **planned** (P1/P2) |
| OTTL flow-criticality policy (route / tail-sample / tier / derive impact) | 📄 **planned** (P3, ContextCore) |
| Flow-aware RCA (weight by flow criticality; business-impact blast radius; journey-step attribution) | 📄 **planned** (P4) |
| **Sink filter** — Phase-2 delivery-policy router over the registry | ⬜ **planned seam** (P5) |

Operational caveats to size into any rollout:

- **Go auto-instrumentation** is eBPF-based, not SDK-injection; **baggage context-propagation on Go is
  the maturity rough edge** (§1). Validate Go pods actually carry baggage before trusting flow attribution
  through them.
- **eBPF context-propagation maturity** (Beyla/Odigos) is improving but trails the SDK path for baggage.
  Use it for base traces; don't assume full baggage fidelity yet.
- **Baggage size / header-cost discipline.** Baggage is an HTTP header on **every hop**. Put only the
  *minimal flow-discriminating* keys (`flow`, `criticality`, `tier`) on the wire — **not** the whole
  project context. Header bytes multiply across the call graph; PII / high-cardinality / secrets never
  go in baggage.
- **The materialization gotcha** (restated because it is the #1 mistake): baggage without the span
  processor **propagates but never lands on telemetry** — silently invisible. If a flow attribute is
  "missing," check materialization before you suspect the seed.

---

**Cross-references:** the ELI5 framing is [01](01_ELI5_how-it-works-and-why-better.md); the feature list
is [02](02_FUNCTIONAL_description.md); the architecture shape is [03](03_TECHNICAL_description-high-level.md); the ROI / cost
argument (per-flow sink tiering as a cost lever) is [05](05_GTM_swot-moat-commercialization.md). The full design note
this doc condenses is
`docs/design/business-context-propagation/DESIGN_baggage-flow-criticality-rca.md`; the static-half
reference is `REFERENCE_contextcore-annotation-context-detection.md` in the same directory.
