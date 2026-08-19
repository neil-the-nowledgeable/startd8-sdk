# ContextCore — Functional Description

**Doc 2 of 5 · "Introduction to ContextCore"**
*Audience: product managers and technical-but-not-deep evaluators. This describes **what ContextCore does** — its behaviors, what you give it, and what you get back — in plain functional terms. It deliberately avoids implementation detail (no config formats, no transform rules); those live in Docs 3–4.*

> **Set map:** [01 — ELI5](01_ELI5.md) · **02 — Functional description (you are here)** · [03 — High-level technical](03_TECHNICAL_description-high-level.md) · [04 — Technical details](04_TECH_details.md) · [05 — Go-to-market](05_GTM_swot-moat-commercialization.md)

---

## The approach in one line

**Declarative Business-Context Observability** — "business context as code."

> Declare business meaning **once** (importance/criticality, owner, SLOs, and the business "flows" your requests belong to); ContextCore makes **every telemetry signal business-aware, flow-scoped, and value-tiered** — with **zero application code**, **vendor-neutral**, on your **existing OpenTelemetry stack**.

Today, most observability data can tell you *that* a service is slow or erroring. It usually **cannot** tell you *whether that matters to the business* — which customer-facing flow it broke, whether that flow earns revenue, or who owns the fix. ContextCore closes that gap by letting you state the business facts up front and then projecting them across everything your monitoring already collects.

---

## Purpose

ContextCore exists to answer one question that raw telemetry can't: **"Does this matter, and to whom?"**

It turns a firehose of technically-true-but-business-blind signals into signals that carry business meaning — so incident response, cost decisions, and coverage reviews can be prioritized by **business value** instead of by raw error counts or gut feel.

---

## Inputs — what you declare

You provide a small amount of **business context** as declarations. You are describing *meaning*, not writing code.

1. **Per-service business context** — for each service, a compact set of facts:
   - **Criticality / importance** (how much this service matters to the business)
   - **Owner** (the team or person accountable)
   - **SLOs** (the reliability targets that matter for it)
   - **Cost-center** (who "pays" for it, for chargeback / value decisions)

2. **A flow map** — a mapping of **request-routes → business flows → criticality**. For example: `/checkout` belongs to the **revenue-primary** flow and is **critical**; `/help/faq` belongs to a **support** flow and is **low** priority.

That's the whole surface you own. You declare business facts you already know; ContextCore does the propagation and projection.

---

## Behaviors & capabilities — what the system does with your declarations

Given those inputs, ContextCore provides the following behaviors:

1. **Auto-tags all telemetry with business context — no code change.** Every trace, metric, and log your services already emit is enriched with the service's business facts (criticality, owner, SLOs, cost-center). Your application code is not modified.

2. **Carries a per-request "flow + criticality" tag through the whole call graph.** When a request enters via a known route, ContextCore attaches its **business flow** and that flow's **criticality**, and that tag rides along as the request fans out across downstream services. A deep internal service can therefore know it is currently serving *the checkout flow* even though it never sees the URL.

3. **Derives monitoring configuration from business criticality.** Sampling rates, alert severities, SLO targets, and dashboard scope are *derived* from how critical something is — so critical flows are watched closely and low-value flows aren't over-instrumented.

4. **Routes and tiers telemetry by business value.** Signals from critical flows can get premium retention; low-value chatter can be sampled hard or sent to cheap storage — telemetry spend follows business value instead of being uniform.

5. **Answers business-impact questions during root-cause analysis.** Because signals are flow-scoped, an investigation can ask *"which revenue flows failed?"* and *"who owns the failing service?"* rather than only *"which host threw 500s?"*

6. **Finds observability blind spots on critical services.** ContextCore can surface where high-criticality services are under-instrumented — the coverage gaps that matter most, ranked by business value rather than treated equally.

7. **Keeps human and AI-agent knowledge persistent and queryable in the observability stack.** Context, decisions, and notes — from people and from AI agents — are retained alongside the telemetry, so knowledge doesn't evaporate between shifts, sessions, or teams.

### The three criticality axes

Criticality is not a single number. ContextCore combines **three axes** — they layer, they don't replace each other:

- **Service importance (static)** — how important this service is in general.
- **Project importance (fallback)** — how important the owning project is, used when a more specific signal isn't present.
- **This request's flow importance (dynamic)** — how important the *specific in-flight flow* is right now (a request through `/checkout` is more critical than the same service serving a background job).

The dynamic flow axis is what lets the *same service* be treated as critical or routine depending on **what it's doing at that moment**.

### Single source of truth

Business importance is **declared once and projected everywhere** — into monitoring config, routing rules, dashboards, and RCA. A **consistency check flags drift**, so the alert severity, the retention policy, and the dashboard can't quietly disagree about how important something is.

---

## Outputs — what you get

- **Business-aware signals** — traces, metrics, and logs that carry `business.*` context (criticality, owner, SLOs, flow).
- **Flow-scoped attribution** — the ability to slice, alert, and investigate by business flow ("the revenue-primary flow", not "these 6 pods").
- **A per-service coverage / RCA view ranked by business value** — where to look first, and where the dangerous instrumentation gaps are.
- **Value-tiered telemetry egress** — retention and destination decisions that follow business value.
- **Derived alert, SLO, and dashboard configuration** — monitoring settings produced *from* your declared criticality, kept consistent with it.

---

## Vendor-neutral by design

ContextCore rides on **open OpenTelemetry standards**, so the business context it adds travels into whatever backends you already run — **Datadog, Splunk, Grafana, Prometheus, Loki, Tempo**. It is an enrichment and policy layer, **not** another monitoring silo to migrate to.

---

## What it does NOT do — scope boundaries

- **It is not a monitoring backend.** It rides on yours; it doesn't store or replace your metrics/traces/logs system.
- **It does not render your dashboards.** It supplies business-aware data and derived config; your existing tools still draw the charts.
- **It does not infer business meaning for you.** *You* declare importance, ownership, and flows. ContextCore propagates and projects those facts — it doesn't guess what's valuable.
- **The "which flow" tag needs the flow to be identifiable.** In practice a flow is recognized by its entry route; requests that can't be tied to a declared route can't be flow-scoped automatically.

---

## Maturity

Be honest about what's shipping versus roadmap:

**Available today**
- Auto-tagging of telemetry with per-service business context (no application code)
- No-code instrumentation of existing services
- Business-context propagation of the per-request flow + criticality tag
- Per-service criticality resolution across the three axes
- Value-based derivation of monitoring config from criticality
- A governed registry of telemetry destinations
- Coverage-driven, business-ranked root-cause / blind-spot analysis

**On the roadmap**
- Fully flow-aware RCA (end-to-end "which revenue flows failed" investigations)
- Per-flow value tiering of telemetry
- The full delivery / routing policy engine for value-tiered egress

---

*Next: [03 — High-level technical](03_TECHNICAL_description-high-level.md) explains the mechanism at an architectural level (how propagation and derivation actually work), before [04 — Technical details](04_TECH_details.md) gets concrete. For the business case and rollout story, see [05 — Go-to-market](05_GTM_swot-moat-commercialization.md).*
