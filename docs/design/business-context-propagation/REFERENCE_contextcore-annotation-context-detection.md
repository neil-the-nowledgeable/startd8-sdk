# Reference: how ContextCore uses / enables K8s annotations for context detection

**Type:** reference (documents a shipped ContextCore mechanism) · **Date:** 2026-08-19
**Source of truth:** `ContextCore/src/contextcore/detector.py` (`ProjectContextDetector`, `ANNOTATION_TO_ATTRIBUTE`)
**Role:** the **static origination** half of business-context enrichment (companion to the dynamic baggage half — see `DESIGN_baggage-flow-criticality-rca.md` and this dir's `README.md`).

---

## What it is

ContextCore's `ProjectContextDetector` is an **OTel `ResourceDetector`** that reads **Kubernetes pod annotations**
and converts them into **OTel resource attributes** — so business/project context declared on a workload flows
onto *every signal that workload emits*, set once at process start. This is how ContextCore **enables** annotation:
a team annotates a pod (or its `ProjectContext` CRD → pod), and every trace/metric/log from it self-describes with
`business.criticality`, `project.id`, SLOs, risk, etc. — with **zero application code change**.

> **Classical instrumentation vs business instrumentation — two axes.** **Classical (technical)
> instrumentation** = *source-side signal generation* (code, auto-instrumentation, or **eBPF** emitting
> telemetry that didn't exist before). The annotation→attribute enrichment documented here is the second
> axis — **business instrumentation** (its **static half**): making the *business dimension* observable
> by projecting **declared** business meaning (criticality, owner, SLOs) onto the telemetry classical
> instrumentation already emits, so business questions become answerable. **The coverage RCA is the
> proof.** The honest caveat: business instrumentation is **not** source-side signal generation — the
> context is **declared, not discovered**, and it **rides on** classical instrumentation's base signal.
> We don't redefine instrumentation; business instrumentation is a distinct axis added alongside it.

## The mechanism

- **Annotation namespace:** `ANNOTATION_PREFIX = "contextcore.io/"` (`detector.py:179`). Only keys under this prefix
  are read; everything else is ignored.
- **Two sources, with fallback** (`detector.py:225-235`):
  1. **Direct pod annotation reading** when running in Kubernetes (reads `pod.metadata.annotations`).
  2. **Environment-variable fallback** for local development (no cluster required).
- **Deterministic mapping** — each `contextcore.io/<key>` annotation maps to a fixed OTel resource-attribute name
  (`ANNOTATION_TO_ATTRIBUTE`, `detector.py:182-222`):

| Annotation (`contextcore.io/…`) | → OTel resource attribute | Group |
|---|---|---|
| `environment` · `env` · `deployment-environment` | `deployment.environment.name` | deployment (OTel semconv) |
| `project` · `project-id` | project id | project |
| `epic` · `epic-id` | `project.epic` | project |
| `task` · `task-id` | `project.task` | project |
| `trace-id` | `project.trace_id` | project |
| `design-doc` · `adr` · `api-contract` | `design.doc` / `design.adr` / `design.api_contract` | design |
| **`criticality`** | **`business.criticality`** | business |
| `business-value` · `owner` · `cost-center` | `business.value` / `business.owner` / `business.cost_center` | business |
| `slo-availability` · `slo-latency-p99` · `slo-latency-p50` · `error-budget` | `requirement.availability` / `requirement.latency_p99` / `requirement.latency_p50` / `requirement.error_budget` | requirements / SLO |
| `risk-type` · `risk-priority` | `risk.type` / `risk.priority` | risk |
| `projectcontext` | `k8s.projectcontext.name` | k8s |

## Vendor-neutrality (a deliberate property)

The mapping targets **standard OTel semantic conventions**, not a vendor's schema. The comment on the environment
key (`detector.py:184-188`) is explicit: `deployment.environment.name` maps to **Datadog `env`**, **Splunk
`deployment.environment`**, and **Grafana `deployment_environment`**. So context declared once as a
`contextcore.io/*` annotation is portable across observability vendors — the same vendor-neutrality principle the
Perses dashboard ADR and the baggage note pursue.

## Where it fits — the STATIC half of business-context enrichment

| | Annotation detector (this) | Baggage (planned) |
|---|---|---|
| Scope | per-pod / per-service | per-request / per-flow |
| OTel layer | **resource** attributes (set once) | **span** attributes (per record) |
| Answers | *what static business context does this service carry* | *which business FLOW is this request serving* |
| Status | ✅ shipped | 📄 planned |

The detector answers the **`service.business.criticality`** axis of the three-axis model; baggage adds the dynamic
**`flow.business.criticality`** axis. Both write the same `business.*` namespace, at different granularities.

## The single-source note (important)

`contextcore.io/criticality` is a **third static authoring home** for criticality — alongside the ContextCore
manifest's `spec.business.criticality` and `spec.targets[].criticality`. If the pod annotation and the manifest
disagree, a service's criticality is annotation-dependent. The criticality-authoring lint
(`ContextCore/HANDOFF_criticality-authoring-lint.md`) should treat the pod annotation as an authoring home too —
its dual-authoring / drift check now spans **manifest ↔ targets[] ↔ pod annotation**. Author criticality once,
project it to the annotation (and the baggage seed) — don't hand-maintain both.

## Related

- `README.md` (this dir) — the high-level enrichment summary.
- `DESIGN_baggage-flow-criticality-rca.md` — the dynamic (baggage) half + RCA + sink filter.
- `ContextCore/HANDOFF_criticality-authoring-lint.md` — the single-source guard (extend to the annotation home).
