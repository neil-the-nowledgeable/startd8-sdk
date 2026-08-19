# ContextCore — Executive Capabilities Overview

*What it is, and why it matters to you. Written for decision-makers, not engineers.*

---

## In one line

**ContextCore turns your observability stack into the single source of truth for *business* context** — so
monitoring, root-cause analysis, cost, project status, and even AI-agent knowledge all speak the same language and
stay current, without manual upkeep and without vendor lock-in.

## The problem it solves

Two expensive gaps sit in every modern engineering org:

1. **Ops doesn't know the business.** Your dashboards and alerts know *services* (`payment-svc is slow`) but not
   *value* (`revenue-primary checkout is degraded`). So teams over-monitor what's cheap and under-monitor what
   pays the bills, and every incident starts with "how bad is this, really?"
2. **Knowledge dies in silos.** Project status lives in tickets nobody updates; AI-agent insights vanish when the
   chat closes; the "why" behind decisions is lost. Every new person — or agent — starts from zero.

ContextCore closes both by **attaching business meaning to the telemetry you already collect** and **persisting
knowledge where it's queryable** — in your OpenTelemetry stack.

---

## Capability clusters

### A. Business-context observability *(the differentiator)*

> **Classical instrumentation vs business instrumentation — two axes.** Classical (technical) instrumentation *generates signal at the source* (the telemetry every tool already produces). ContextCore adds a second, distinct discipline — **business instrumentation**: making the *business dimension* observable by projecting **declared** business meaning (criticality, flow, value) onto that already-emitted signal, so a class of business questions becomes answerable — **the coverage RCA is the proof** ("are our *critical* services observed?" — unanswerable before, answerable after). Honest caveat: business instrumentation's meaning is **declared, not discovered**, and it **rides on** classical instrumentation's base signal.

| Capability | What it is | Why it matters to you |
|---|---|---|
| **Context enrichment via annotations** | Declare business context (criticality, owner, SLOs, cost-center) once as a Kubernetes annotation; every metric/trace/log from that workload inherits it. *(Shipped.)* | **Zero code change.** Your existing telemetry instantly becomes business-aware — no re-instrumentation project. |
| **Value-based observability** | Monitoring config (sampling, alert severity, SLO targets, dashboards) is *derived* from business criticality — `critical → P1, 100% capture`. *(Shipped.)* | **Right-size the spend.** Pay for full fidelity on what matters, sample the rest — and stop hand-tuning hundreds of alert rules. |
| **Coverage-driven RCA** | Answers *"are our critical services actually observable?"* — finds the **blind spots** (uninstrumented critical services) and ranks what to fix by criticality × gap × risk. *(Shipped.)* | **Find the gaps before the incident does.** Turn "we didn't have data" into a prioritized, closeable list. |
| **Flow-aware RCA + per-flow cost tiering** | Business context that travels *with the request* — so a failure is attributed to the **revenue flow** it broke, and premium telemetry retention is spent per-flow (full fidelity on checkout, cheap on browse — same services). *(Roadmap.)* | **Answer the CFO's question:** "which revenue flows were affected, and what did it cost?" — and cut observability bills without losing the signal that matters. |
| **Vendor-neutral by design** | Everything maps to open OpenTelemetry standards; context is portable across Datadog, Splunk, Grafana, Prometheus, Loki, Tempo. *(Shipped.)* | **No lock-in.** Switch or mix backends without re-doing your business context. |

### B. Human–agent knowledge parity *(the AI-readiness story)*

| Capability | What it is | Why it matters to you |
|---|---|---|
| **Agent knowledge that persists** | AI agents emit their insights (decisions, root causes, recommendations) as queryable telemetry — not chat logs that vanish. *(Shipped.)* | **Stop paying for the same analysis twice.** Agent findings become a durable, searchable asset the whole team (and the next agent) can build on. |
| **Human-to-agent guidance** | Set constraints and focus areas once (e.g., "no auth changes without approval"); every agent session respects them. *(Shipped.)* | **Govern your AI agents.** Consistent guardrails without re-briefing every session. |

### C. Project management built on operations *(no more stale tickets)*

| Capability | What it is | Why it matters to you |
|---|---|---|
| **Status from real activity** | Project/task status is derived from commits, PRs, and CI — not manual ticket updates. *(Shipped.)* | **Status you can trust,** with zero PM busywork — because it reflects what actually happened. |
| **One system, every audience** | The same underlying data is presented for executives, engineers, and agents — always current. *(Shipped.)* | **End the "which dashboard is right?" problem.** One source of truth, personalized per reader. |

### D. Cloud-native, enterprise-ready foundation

| Capability | What it is | Why it matters to you |
|---|---|---|
| **CRD-native + GitOps** | Business context and project definitions are Kubernetes resources, version-controlled and declarative. *(Shipped.)* | **Fits how you already run infra** — reviewable, auditable, reproducible. |
| **Governed telemetry routing** | A validated, org-scoped registry of telemetry destinations, with fail-closed security (no secrets, no private-network egress). *(Shipped; policy router on the roadmap.)* | **Control where your data goes** — multi-tenant, secure, and ready to route by business value. |

---

## Why it matters — the business outcomes

- **Faster incident resolution (lower MTTR).** RCA starts from business impact and known blind spots, not a blank map.
- **Lower observability cost.** Spend fidelity where value is; sample or drop the rest — increasingly *per revenue flow*.
- **No vendor lock-in.** Open standards mean your business context outlives any single tool contract.
- **Knowledge that compounds.** Agent insights and decisions persist and stay queryable instead of resetting each session.
- **Project status that reflects reality.** Derived from activity, not from whoever remembered to update the ticket.
- **AI-agent ready.** Governed, persistent, shared context is the foundation for trustworthy human-agent collaboration.

## Who it's for

- **Platform / SRE leaders** drowning in alerts and observability bills who need value-based prioritization.
- **Engineering leaders adopting AI agents** who need agent work to be governed, persistent, and shared.
- **Cost-conscious observability buyers** who want vendor neutrality and per-value spend control.

## Maturity at a glance

**Shipped today:** annotation-based context enrichment · value-based observability · coverage-driven RCA ·
agent-knowledge persistence · human-to-agent guidance · status-from-activity · CRD/GitOps · governed sink registry ·
vendor-neutral OTel foundation.
**On the roadmap:** flow-aware RCA + per-flow cost tiering (business-context propagation) · the sink delivery-policy
router · vendor-neutral dashboard generation.

---

*References for the technically curious: `docs/design/business-context-propagation/` (enrichment + RCA),
`docs/design/dashboard-vendor-neutrality/` (neutral dashboards). Roadmap items are marked; nothing here oversells
what isn't shipped.*
