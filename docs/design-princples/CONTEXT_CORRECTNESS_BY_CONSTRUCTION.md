# Context Correctness by Construction

**Status:** Active design document
**Date:** 2026-02-15
**Author:** Force Multiplier Labs
**Confidence:** 0.92

> *"Silent degradation — no errors, reduced quality — is the hardest failure mode
> to detect. A contract system makes it structurally impossible for context to
> degrade without generating a signal."*

---

## Purpose

Define the theoretical foundation and architectural strategy for ContextCore's
approach to **context correctness** in distributed and agent-based systems.

This document argues that context propagation is not a feature to be added to
observability — it is a **structural property** that must be enforced at design
time, the same way type systems enforce correctness in programming languages.
It identifies the family of cross-cutting concerns that share this property,
establishes a unified contract framework for addressing them, and positions
ContextCore as the **type checker for service architectures**.

## Audience

- System architects evaluating ContextCore's value proposition
- Contributors designing new contract layers
- Operators seeking to understand why traditional observability misses these failures

---

## The Problem: Silent Degradation at Scale

Modern service architectures have a failure mode that no existing tool
adequately addresses: **silent degradation of cross-boundary information flow**.

Consider a workflow pipeline with seven phases. Phase 1 classifies a domain as
`web_application`. Phase 5 uses that classification to select code generation
constraints. The classification must traverse phases 2, 3, and 4 to reach phase
5. If any intermediate phase drops or corrupts the field:

- No exception is thrown
- No error appears in logs
- No alert fires
- The downstream phase receives a default value and produces **subtly worse output**

This failure mode is endemic to every distributed system. It affects
microservices, agent pipelines, data processing workflows, and CI/CD chains.
And it scales with system complexity — the more boundaries information must
cross, the more opportunities for silent loss.

### Why Observability Tools Miss This

Traditional observability answers **"what happened?"** — it collects traces,
metrics, and logs after execution. But silent degradation doesn't produce
anomalous signals. The trace looks normal. The metrics show normal latency.
The logs show no errors. The only signal is that the output is slightly worse,
and "slightly worse" doesn't trigger any alert.

The gap is fundamental: observability tools are **descriptive** (they record
what occurred) rather than **prescriptive** (they declare what should occur and
verify that it did). Solving silent degradation requires shifting from
description to prescription — from "collect and hope" to "declare and verify."

---

## The Insight: Context Flow as a Type System

ContextCore's foundational ADR ([ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md))
established that tasks and spans share the same structure. This design document
extends that insight to a broader claim:

> **Context flow through service boundaries shares the same structure as data
> flow through a type system.**

In a typed programming language:

| Type System | Context Flow |
|---|---|
| **Declaration**: `fn foo(x: int) -> str` | **Contract**: Phase X requires field Y of type Z |
| **Check**: Compiler verifies types at every call site | **Validate**: Boundary checker verifies fields at every phase transition |
| **Error**: Compile error when types don't match | **Signal**: Span event when context doesn't propagate |
| **Guarantee**: Well-typed programs don't go wrong (Milner) | **Guarantee**: Contract-valid pipelines don't silently degrade |

Type systems moved software from "run it and hope" to "prove it before running."
ContextCore moves distributed context from "propagate and hope" to "declare and verify."

The parallel is not metaphorical — it is structural. In programming language
theory, **type soundness** guarantees that if a program type-checks, evaluation
preserves types at every reduction step. In ContextCore, **contract soundness**
guarantees that if a pipeline satisfies its contract at every boundary,
context integrity is preserved at every phase transition.

---

## The Family: Cross-Cutting Concerns That Degrade Silently

Context propagation is one instance of a broader family of problems. All share
the same pathology:

1. Information is produced at a **source**
2. It must flow through a **channel** of intermediate services
3. It is consumed at a **sink** that makes decisions based on it
4. **Silent degradation** occurs when the channel drops or corrupts information without signaling

This is the distributed systems analog of **information flow properties** in
security theory, where the concern is ensuring that classified data doesn't leak
to unclassified outputs. Here, the concern is reversed: ensuring that
*required* context doesn't *fail to reach* its destination.

### 1. Context Propagation

The canonical instance. A field is set in service A, needed in service F,
passes through B→C→D→E. Any intermediate service can drop it.

**Why it's hard:** No compile-time guarantee. No runtime error. The downstream
service gets a default value and produces subtly worse output.

**The observability gap:** Distributed traces show *that* a call happened, not
*what context traveled with it*. OpenTelemetry baggage exists but is opt-in,
unchecked, and has no contract system.

**ContextCore solution:** Layer 1 — `PropagationChainSpec` declares end-to-end
field flow. `BoundaryValidator` checks fields at every boundary.
`PropagationTracker` stamps provenance. `ChainStatus` (INTACT/DEGRADED/BROKEN)
provides the signal.

**Implementation:** `src/contextcore/contracts/propagation/` (62 tests).

### 2. Schema Evolution and Contract Drift

Service A produces `{"status": "active"}`, service B expects
`{"state": "running"}`. Both validate their own schema. Nobody validates the
contract *between* them.

**Why it's hard:** Each service is internally consistent. The inconsistency
only manifests at integration boundaries, and often only as degraded behavior
rather than errors.

**The CS parallel:** The distributed systems version of the **Liskov
Substitution Principle** — the interface matches but the behavioral contract
is violated. Also related to **protocol conformance** in session types, where
two processes agree on message types but disagree on message semantics.

**ContextCore approach:** Schema compatibility contracts that declare the
*semantic* contract between services, not just the structural schema. A
`SchemaCompatibilitySpec` would declare "Service A's `status: active` maps to
Service B's `state: running`" and validate the mapping at integration test time.

### 3. Semantic Convention Drift

Team A emits `user.id`, Team B emits `user_id`, Team C emits `userId`. All
three mean the same thing. Dashboards query one spelling and miss 2/3 of the
data.

**Why it's hard:** No central authority. No validation. Each service is
internally consistent. The problem only appears when you try to correlate
across services.

**The observability gap:** This is *why* OpenTelemetry created semantic
conventions. But enforcement is voluntary — there's no tool that says "your
`user_id` attribute violates the convention and will be invisible to dashboards."

**ContextCore approach:** The Weaver cross-repo alignment plan
([WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md](../plans/WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md))
addresses this with a shared semconv registry and CI validation. Convention
specs declare the canonical attribute names, and `validate_enum_consistency.py`
enforces them across repos.

### 4. Causal Ordering Violations

Event A must be processed before Event B, but under load, B arrives first.
Systems that depend on ordering produce incorrect results — silently.

**Why it's hard:** In distributed systems, total ordering requires consensus,
which destroys performance. Most systems use eventual consistency and hope that
ordering violations are rare enough not to matter.

**The CS parallel:** **Lamport clocks** and **vector clocks** solve this for
detecting ordering violations, but not for *preventing* them. **Session types**
in process algebra provide compile-time ordering guarantees for message-passing
protocols. ContextCore's phase-sequential execution model naturally enforces
ordering within a pipeline, but cross-pipeline causal constraints remain
unsolved.

**ContextCore approach:** An `OrderingConstraintSpec` would declare "event A
must be processed before event B across any execution path." At runtime, the
constraint would be checked against provenance timestamps. Violations would
produce BROKEN chain status with a causal explanation.

### 5. Capability and Permission Propagation

User has permission P in service A. Service A calls service B on behalf of the
user. Does B know about P? Often the permission is either dropped
(over-permissive via default-allow) or over-restricted (user gets an unexplained
403).

**Why it's hard:** Identical structural problem to context propagation —
metadata must travel across trust boundaries. OAuth scopes and JWT claims are
the mechanism, but there is no *contract* that says "this call chain REQUIRES
scope X to reach service D."

**The CS parallel:** **Capability-based security** (Dennis & Van Horn, 1966)
solves this in single-process systems by making permissions unforgeable tokens
that travel with the call chain. In distributed systems, the analog is
**macaroons** (Google, 2014) — bearer tokens with attenuation. But neither
provides a *declaration* of what capabilities a pipeline requires end-to-end.

**ContextCore approach:** A `CapabilityChainSpec` using the same primitives as
`PropagationChainSpec` — source phase declares available capabilities,
destination phase declares required capabilities, chain validation verifies the
capability survived the channel. `FieldSpec(name="auth.scopes",
severity=BLOCKING)` at every boundary.

### 6. SLO Budget Propagation

Service A has a 200ms p99 SLO. It calls B (50ms budget), C (100ms budget), D
(50ms budget). But B calls E, which nobody accounted for. The budget doesn't
propagate — it just overflows.

**Why it's hard:** Latency budgets are set at the edge but consumed at every
hop. No system tracks "how much budget remains for downstream calls." Adaptive
systems (circuit breakers, retry budgets) react *after* the budget is blown,
not before.

**The CS parallel:** **Deadline propagation** in real-time systems (Rate
Monotonic Analysis) solves this for fixed-priority scheduling. Google's
**deadline propagation** in gRPC propagates a wall-clock deadline across hops,
but this is a mechanism, not a contract system — there's no declaration of
"service B should consume at most 50ms."

**ContextCore approach:** A `BudgetPropagationSpec` that declares per-phase
budget allocations. The tracker stamps `remaining_budget_ms` at each boundary.
DEGRADED status fires when a hop consumes more than its allocation. BROKEN
fires when the remaining budget goes negative.

### 7. Data Lineage and Provenance

A machine learning model makes a prediction. Which data was used? Which
transformations were applied? If the input data was stale or wrong, how do you
trace back to the source?

**Why it's hard:** Data flows through pipelines (ETL, feature stores, model
servers) exactly like context flows through workflow phases. Each stage
transforms but rarely stamps provenance. When something goes wrong, the
forensic effort to reconstruct the data's path is enormous.

**The CS parallel:** **Provenance** in database theory (Buneman et al., 2001)
— tracking the origin and transformation history of data. **Differential
dataflow** (McSherry et al., 2013) provides incremental computation with
provenance. **OpenLineage** is the emerging standard for data pipeline lineage.

**ContextCore approach:** The `PropagationTracker.stamp()` method already
records `FieldProvenance(origin_phase, set_at, value_hash)` — the same
primitives that data lineage systems use. A `ProvenanceChainSpec` would extend
this to declare expected data transformations at each stage and verify that the
transformation history matches the declaration.

### 8. Error Context Enrichment

Service F throws an error. The stack trace shows what happened in F. But the
root cause is that Service A sent malformed input six hops ago. The error in F
lacks the context from A.

**Why it's hard:** Errors are caught and re-thrown at each boundary. Each
re-throw loses context. By the time a human sees the error, the causal chain
is gone.

**The CS parallel:** **Exception chaining** (Java's `cause`, Python's
`__cause__`) solves this within a single process. In distributed systems,
**distributed tracing** partially addresses it by linking spans, but the trace
shows *that* Service A was called, not *what* it contributed to the failure.

**ContextCore approach:** If every boundary stamps provenance, an error in
phase F can be traced back to "this field was set by phase A at timestamp T
with value hash H." The provenance trail turns opaque failures into causal
narratives.

---

## The Unifying Theory

These eight concerns share a common theoretical structure that can be expressed
as a single framework.

### Formal Structure

In information flow theory, a system has a set of **security levels** (labels)
and a **flow relation** that determines which information can flow where. A
system satisfies **noninterference** if low-security outputs are independent of
high-security inputs.

ContextCore inverts this: instead of preventing information from leaking
*out*, it prevents information from failing to propagate *through*. The
formal dual:

| Information Flow Security | Context Correctness |
|---|---|
| Prevent secret data from reaching public outputs | Prevent required context from failing to reach consumers |
| Labels: classification levels (secret, public) | Labels: severity levels (BLOCKING, WARNING, ADVISORY) |
| Policy: high cannot flow to low | Policy: source must flow to destination |
| Violation: information leak | Violation: silent degradation |
| Check: taint analysis | Check: boundary validation |

Both are instances of **labeled transition systems with flow properties**:

1. A **source** produces information with a label
2. A **channel** of intermediate nodes transforms/relays it
3. A **sink** consumes it and makes decisions based on it
4. A **flow property** declares what must (or must not) reach the sink
5. A **checker** verifies the property at each transition

### Why This Hasn't Been Solved

In single-process systems, these properties are enforced by **compilers** (type
systems), **runtimes** (taint tracking), and **operating systems** (capability
checks). The solutions are mature, well-understood, and automatic.

In distributed systems, there is no compiler. Each service is compiled
independently. The "program" is the *composition* of services, and that
composition is defined at deployment time, not compile time. No tool validates
the composition's information flow properties.

This is the gap ContextCore fills: **it is the compiler for service
compositions.**

---

## Architecture: 7-Layer Defense-in-Depth

Each cross-cutting concern maps to a contract layer. All layers share the same
four primitives:

| Primitive | Purpose | Implementation |
|---|---|---|
| **Declare** | YAML contract specifying what must flow where | `ContextContract` / `*Spec` models |
| **Validate** | Boundary checking with severity (BLOCKING/WARNING/ADVISORY) | `BoundaryValidator` |
| **Track** | Provenance stamping as context flows through phases | `PropagationTracker` |
| **Emit** | OTel span events for observability of the contract system itself | `emit_*_result()` helpers |

### Layer Map

```
Layer 7: Data Lineage / Provenance
         ProvenanceChainSpec — transformation history verification
         ┃
Layer 6: SLO Budget Propagation
         BudgetPropagationSpec — per-hop budget allocation and tracking
         ┃
Layer 5: Capability / Permission Propagation
         CapabilityChainSpec — end-to-end permission flow verification
         ┃
Layer 4: Causal Ordering
         OrderingConstraintSpec — cross-boundary event ordering contracts
         ┃
Layer 3: Semantic Convention Alignment
         ConventionSpec — attribute naming and enum consistency (Weaver)
         ┃
Layer 2: Schema Evolution / Contract Drift
         SchemaCompatibilitySpec — cross-service semantic contract validation
         ┃
Layer 1: Context Propagation                              ◄── IMPLEMENTED
         PropagationChainSpec — end-to-end field flow contracts
         ┃
     ┏━━━┻━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
     ┃  Shared primitives: Declare · Validate · Track · Emit      ┃
     ┃  Shared types: ConstraintSeverity · ChainStatus · FieldSpec ┃
     ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

### Layer Dependencies

Layers are **independent** — each can be implemented and deployed without the
others. However, they compose naturally:

- Layer 1 + Layer 3: "Did the field propagate?" + "Is it spelled correctly?"
- Layer 1 + Layer 5: "Did the context reach the destination?" + "Did the permission reach it too?"
- Layer 1 + Layer 6: "Is the field present?" + "Did it arrive within the budget?"
- Layer 7 wraps Layer 1: "The field propagated, and here's the full transformation history."

### Why This Ordering

Layer 1 (context propagation) is the keystone because every other layer depends
on the same structural question: "did information X flow correctly from point A
to point F?" The layers above add increasingly specific semantics to that
question:

- Layer 2 adds: "...and is it the *right shape*?"
- Layer 3 adds: "...and is it *named correctly*?"
- Layer 4 adds: "...and did it arrive *in the right order*?"
- Layer 5 adds: "...and does the receiver have *permission* to use it?"
- Layer 6 adds: "...and did it arrive *within the time budget*?"
- Layer 7 adds: "...and can we prove *where it came from*?"

---

## Design Principles

### 1. Prescriptive Over Descriptive

Traditional observability describes what happened. ContextCore prescribes what
should happen and verifies that it did. Contracts are the prescriptions.

### 2. Design Time Over Runtime

Catch context correctness issues when the pipeline is designed, not when it
fails in production. YAML contracts are reviewed in PRs alongside code.

### 3. Graceful Degradation Over Hard Failure

Not all context fields are equally critical. The severity model
(BLOCKING/WARNING/ADVISORY) mirrors how real systems work: some fields are
load-bearing, some are optimization hints, some are diagnostic aids.

### 4. Composable Primitives Over Monolithic Solutions

Every layer uses the same four primitives (Declare, Validate, Track, Emit).
New layers are new contract types plugged into the same framework, not new
frameworks.

### 5. Opt-In Over Mandatory

Every layer is opt-in. Existing systems work unchanged. Contracts add
verification on top, they don't replace existing validation. This is critical
for adoption — you can add Layer 1 to one pipeline without touching anything
else.

### 6. Observable Contracts Over Invisible Guarantees

The contract system itself emits OTel events. You can build a dashboard that
shows "85% of propagation chains are INTACT, 10% are DEGRADED, 5% are BROKEN."
The meta-observability makes the contract system trustworthy.

---

## Relationship to Existing Work

### OpenTelemetry Baggage

OTel Baggage propagates key-value pairs across service boundaries. It is a
*mechanism* for propagation, not a *contract system* for verifying propagation.
ContextCore could use Baggage as a transport layer while adding declaration,
validation, and tracking on top.

### OpenTelemetry Semantic Conventions

Semantic conventions standardize attribute names. They are Layer 3 in our
model. ContextCore's Weaver plan extends them with cross-repo CI enforcement.

### Service Mesh Policies (Istio, Linkerd)

Service meshes enforce network-level policies (mTLS, rate limiting, traffic
routing). They operate at Layer 4 (transport) in the OSI model. ContextCore
operates at Layer 7 (application) — it's concerned with the *content* of
messages, not their delivery.

### Contract Testing (Pact, Spring Cloud Contract)

Consumer-driven contract testing validates API schemas between services. This
is close to Layer 2 in our model but limited to request/response schemas. It
doesn't address enrichment field propagation, causal ordering, or SLO budgets.

### Data Lineage (OpenLineage, Apache Atlas, Marquez)

Data lineage tools track dataset provenance through ETL pipelines. This is
Layer 7 specialized for data processing. ContextCore generalizes the same
provenance primitives to any service pipeline.

### Session Types (Scribble, Links)

Session types in programming language theory provide compile-time guarantees
for message-passing protocols. They ensure that communicating processes agree
on the types and ordering of messages. This is the theoretical ideal that
ContextCore approximates for practical systems — session types for a service
mesh would be the "compiler" we described above.

---

## The Critical Differentiator

The reason ContextCore exists — and the reason it's built on observability
infrastructure rather than as a standalone tool — is this:

**Every other approach to context correctness operates after the fact.**

- Observability tools show you that context was lost — after it was lost.
- Contract testing validates schemas — at test time, not at every boundary in production.
- Service meshes enforce network policies — but know nothing about application context.
- Data lineage tracks provenance — but doesn't declare what provenance *should* look like.

ContextCore is the only system that:

1. **Declares** what context must flow where (YAML contracts, reviewed in PRs)
2. **Validates** at every boundary in production (not just in tests)
3. **Tracks** provenance as context flows (not reconstructed after the fact)
4. **Emits** signals when contracts are violated (not silent degradation)
5. **Uses observability infrastructure as the enforcement substrate** (not a separate system)

Point 5 is why ADR-001 matters. By modeling everything as spans and events in
the same infrastructure that handles runtime traces, ContextCore's contract
enforcement is automatically:

- **Queryable** — TraceQL for contract violations alongside runtime errors
- **Dashboardable** — Grafana panels for context correctness alongside latency
- **Alertable** — Alertmanager rules for broken chains alongside error rates
- **Retainable** — Same retention policies, same storage, same backup

You don't need a separate system to monitor your context correctness. It lives
in the same place as everything else. That's what "business observability" means:
grounding observability in business context, and grounding context correctness
in observability infrastructure.

**ContextCore shifts context correctness from runtime hope to design-time
guarantee, enforced continuously in production, observable through the same
infrastructure you already use.**

---

## Implementation Status

> **Updated 2026-02-16:** The contract system has two orthogonal axes:
> **Contract Domains** (what correctness properties are enforced) and
> **Defense-in-Depth Layers** (when enforcement runs in the lifecycle).
> All 7 contract domains are now implemented. Defense-in-depth lifecycle
> integration (wiring domains into preflight/runtime/postexec/regression
> stages) is complete for L1–L2 and pending for L3–L7.

### Table A — Contract Domains (the "what")

| Layer | Domain | Status |
|-------|--------|--------|
| 1 | Context Propagation | **IMPLEMENTED** — `contracts/propagation/` |
| 2 | Schema Compatibility | **IMPLEMENTED** — `contracts/schema_compat/` |
| 3 | Semantic Conventions | **IMPLEMENTED** — `contracts/semconv/` (20 tests) |
| 4 | Causal Ordering | **IMPLEMENTED** — `contracts/ordering/` (22 tests) |
| 5 | Capability Propagation | **IMPLEMENTED** — `contracts/capability/` (18 tests) |
| 6 | SLO Budget Tracking | **IMPLEMENTED** — `contracts/budget/` (19 tests) |
| 7 | Data Lineage | **IMPLEMENTED** — `contracts/lineage/` (21 tests) |

### Table B — Defense-in-Depth Layers (the "when")

| Layer | Stage | Phase | Status |
|-------|-------|-------|--------|
| 1–2 | Propagation + Schema | BEFORE | **IMPLEMENTED** — `contracts/propagation/`, `contracts/schema_compat/` |
| 3 | Pre-Flight Validation | BEFORE | **IMPLEMENTED** — `contracts/preflight/` |
| 4 | Runtime Guards | DURING | **IMPLEMENTED** — `contracts/runtime/` |
| 5 | Post-Execution Checks | AFTER | **IMPLEMENTED** — `contracts/postexec/` |
| 6 | Observability Contracts | CONTINUOUS | **IMPLEMENTED** — `contracts/observability/` |
| 7 | Regression Detection | CI/CD | **IMPLEMENTED** — `contracts/regression/` |

### Domains × Lifecycle Matrix

Each domain can be enforced at multiple lifecycle stages. Cells marked ✓ are
fully integrated; cells marked ● have domain logic implemented (schema,
loader, validator, tracker, OTel) but lifecycle wiring is pending;
cells marked ○ are designed but not yet built.

|                         | Pre-Flight | Runtime | Post-Exec | Observability | Regression |
|-------------------------|:----------:|:-------:|:---------:|:-------------:|:----------:|
| Context Propagation     | ✓          | ✓       | ✓         | ✓             | ✓          |
| Schema Compatibility    | ✓          | ✓       | ✓         | ✓             | ✓          |
| Semantic Conventions    | ●          | ●       | ●         | ●             | ●          |
| Causal Ordering         | ●          | ●       | ●         | ●             | ●          |
| Capability Propagation  | ●          | ●       | ●         | ●             | ●          |
| SLO Budget Tracking     | ●          | ●       | ●         | ●             | ●          |
| Data Lineage            | ●          | ●       | ●         | ●             | ●          |

### Extension Concerns (Designed)

9 extension concerns have full requirements documents
(`docs/design/requirements/REQ_CONCERN_*.md`):

| Extension | Concern | Requirements |
|---|---|---|
| 4E | Temporal Staleness | `REQ_CONCERN_4E_TEMPORAL_STALENESS.md` |
| 5E | Delegation Authority | `REQ_CONCERN_5E_DELEGATION_AUTHORITY.md` |
| 6E | Multi-Budget Coordination | `REQ_CONCERN_6E_MULTI_BUDGET.md` |
| 7E | Version Lineage | `REQ_CONCERN_7E_VERSION_LINEAGE.md` |
| 9 | Quality Propagation | `REQ_CONCERN_9_QUALITY_PROPAGATION.md` |
| 10 | Checkpoint Recovery | `REQ_CONCERN_10_CHECKPOINT_RECOVERY.md` |
| 11 | Config Evolution | `REQ_CONCERN_11_CONFIG_EVOLUTION.md` |
| 12 | Graph Topology | `REQ_CONCERN_12_GRAPH_TOPOLOGY.md` |
| 13 | Evaluation-Gated Propagation | `REQ_CONCERN_13_EVALUATION_GATED_PROPAGATION.md` |

### Layer 1 Architecture (Implemented)

```
artisan-pipeline.contract.yaml     (Example YAML declaration — may not exist
         │                          in repo; used here as reference format)
         ▼
    ContractLoader                 (Parse + cache)
         │
    ┌────┴────┐
    ▼         ▼
BoundaryValidator    PropagationTracker    (Validate + Track)
    │                     │
    ▼                     ▼
ContractValidationResult  PropagationChainResult
    │                     │
    └────────┬────────────┘
             ▼
    emit_boundary_result()         (OTel span events)
    emit_chain_result()
    emit_propagation_summary()
```

**Key types:**
- `FieldSpec` — severity (BLOCKING/WARNING/ADVISORY), default value, source phase
- `PropagationChainSpec` — source → waypoints → destination with verification expression
- `ChainStatus` — INTACT / DEGRADED / BROKEN
- `FieldProvenance` — origin_phase, timestamp, value_hash

---

## References

### ContextCore

- [ADR-001: Tasks as Spans](../adr/001-tasks-as-spans.md) — Foundational architecture decision
- [A2A Contracts Design](A2A_CONTRACTS_DESIGN.md) — Contract-first agent coordination
- [Weaver Cross-Repo Alignment Plan](../plans/WEAVER_CROSS_REPO_ALIGNMENT_PLAN.md) — Layer 3 design
- [Semantic Conventions](../semantic-conventions.md) — Attribute naming standards

### Computer Science Theory

- Milner, R. (1978). *A Theory of Type Polymorphism in Programming*. JCSS 17.
  — Type soundness: "well-typed programs don't go wrong."
- Denning, D.E. (1976). *A Lattice Model of Secure Information Flow*. CACM 19(5).
  — Information flow as lattice properties.
- Dennis, J.B. & Van Horn, E.C. (1966). *Programming Semantics for Multiprogrammed Computations*. CACM 9(3).
  — Capability-based security.
- Lamport, L. (1978). *Time, Clocks, and the Ordering of Events in a Distributed System*. CACM 21(7).
  — Causal ordering in distributed systems.
- Buneman, P., Khanna, S., & Tan, W.C. (2001). *Why and Where: A Characterization of Data Provenance*. ICDT.
  — Provenance theory for databases.
- Honda, K., Yoshida, N., & Carbone, M. (2008). *Multiparty Asynchronous Session Types*. POPL.
  — Session types for message-passing protocols.

### Industry Practice

- OpenTelemetry. *Baggage Specification*. https://opentelemetry.io/docs/specs/otel/baggage/
- OpenLineage. *The Open Standard for Data Lineage*. https://openlineage.io/
- Birgisson, A. et al. (2014). *Macaroons: Cookies with Contextual Caveats for Decentralized Authorization in the Cloud*. NDSS.
  — Google's capability token system.
- McSherry, F., Murray, D.G., Isaacs, R., & Isard, M. (2013). *Differential Dataflow*. CIDR.
  — Incremental computation with provenance.
