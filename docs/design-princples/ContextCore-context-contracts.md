ContextCore Context Contracts.md

Let me think through this carefully. This is an architectural design question that deserves deep analysis before any code.

  The Core Insight

  Context propagation failures are a fundamentally different class of bug from what traditional monitoring catches:

  ┌──────────────────────────┬───────────────────────────────────────────────┐
  │     Traditional Bug      │            Context Propagation Bug            │
  ├──────────────────────────┼───────────────────────────────────────────────┤
  │ System fails             │ System succeeds                               │
  ├──────────────────────────┼───────────────────────────────────────────────┤
  │ Error logged             │ No error                                      │
  ├──────────────────────────┼───────────────────────────────────────────────┤
  │ Alert fires              │ Silence                                       │
  ├──────────────────────────┼───────────────────────────────────────────────┤
  │ User notices immediately │ Quality degrades invisibly                    │
  ├──────────────────────────┼───────────────────────────────────────────────┤
  │ Fix is obvious           │ Root cause is upstream, symptom is downstream │
  └──────────────────────────┴───────────────────────────────────────────────┘

  This is isomorphic to distributed tracing context loss — when a microservice drops the traceparent header, downstream services still respond, but you lose
   correlation, sampling decisions, and routing. The system works. It just works worse.

  The insight that makes this a potential differentiator: no workflow framework treats context propagation as a first-class concern. They all treat it as
  "pass the dict along and hope for the best."

  Defense in Depth: Seven Layers

  Let me map the layers from most proactive (prevent) to most reactive (detect):

  PREVENT                                              DETECT
    │                                                    │
    ▼                                                    ▼
    L1 ──→ L2 ──→ L3 ──→ L4 ──→ L5 ──→ L6 ──→ L7
    │       │       │       │       │       │       │
    │       │       │       │       │       │       └─ Regression gates
    │       │       │       │       │       └─ Observability/alerting
    │       │       │       │       └─ Post-execution validation
    │       │       │       └─ Runtime boundary checks
    │       │       └─ Pre-flight verification
    │       └─ Static analysis (plan-time)
    └─ Context contracts (declarations)

  Layer 1: Context Contracts (Declaration)

  The foundation. Phase handlers declare what they require and produce:

  class ImplementPhaseHandler(AbstractPhaseHandler):
      context_requires = ContextContract({
          "domain": Field(type=str, critical=True, default="unknown"),
          "enriched_seed_path": Field(type=str, critical=True),
          "domain_constraints": Field(type=list, critical=False),
      })

      context_produces = ContextContract({
          "implementation": Field(type=dict, critical=True),
          "generation_results": Field(type=dict, critical=True),
      })

  This is analogous to function type signatures — you're declaring the interface, not just hoping callers pass the right things.

  Key design question: Do contracts live in code (Python decorators/classes) or in configuration (YAML/JSON schemas)? I think both — code for enforcement,
  config for tooling/static analysis.

  Layer 2: Static Analysis (Plan-Time)

  Before any code runs, analyze the propagation graph for completeness:

  DomainPreflight ──produces──→ domain, domain_constraints
         │
         ▼ (written to seed)
  PlanPhase ──requires──→ enriched_seed_path
         │──produces──→ tasks, enriched_seed_path
         ▼
  DesignPhase ──requires──→ domain (critical)
         │──produces──→ design_results
         ▼
  ImplementPhase ──requires──→ domain_constraints (critical!)
         │
         ✗ GAP: No phase produces domain_constraints into context

  The static analyzer walks the requires/produces graph and finds:
  - Dangling reads: Phase requires X but no upstream phase produces X
  - Dead writes: Phase produces X but no downstream phase requires X
  - Shadow defaults: Critical field falls through to default because producer is conditional

  This runs at contextcore manifest validate or contextcore polish time — before any workflow executes.

  Layer 3: Pre-Flight Verification

  Just before a workflow run starts, validate:
  - All critical requires fields have non-default values in the initial context
  - The enriched seed actually contains the expected enrichment keys
  - The dependency graph of phases matches the contract graph

  # Before workflow.execute():
  violations = workflow.verify_propagation_contracts(initial_context)
  if violations.critical:
      raise PropagationContractViolation(violations)
  if violations.warnings:
      for w in violations.warnings:
          logger.warning("Pre-flight: %s", w)

  Layer 4: Runtime Boundary Checks (partially implemented — WCP-003)

  At each phase boundary, verify and emit:
  - context.propagated when critical field successfully forwarded
  - context.defaulted when field falls back to default
  - context.failed when field should be present but isn't

  What we have: Span events in _execute_chunk() and from_seed_entry().
  What we need: Systematic boundary checking driven by contracts (Layer 1), not hand-written checks in each handler.

  Layer 5: Post-Execution Validation (implemented — WCP-004)

  _validate_propagation_completeness() in FINALIZE. Already done.

  Layer 6: Observability & Alerting (implemented — WCP-010/011)

  Dashboard panels and TraceQL queries. Already done.

  What we need: Alerting rules that fire when propagation completeness drops below threshold.

  Layer 7: Regression Prevention (CI/CD)

  Self-validating test suite pattern (already done with SV tests), plus:
  - CI gate that runs propagation graph analysis on PR
  - Regression test: propagation completeness must not decrease
  - Contract drift detection: if a phase changes its produces/requires, validate graph

  What We Already Have vs What We Need

  > **Updated 2026-02-17:** All 7 layers are now implemented (100 tests for L3–L7, 496 total). See
  > [CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md](CONTEXT_CORRECTNESS_BY_CONSTRUCTION.md)
  > for the theoretical foundation and
  > [CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md](CONTEXT_PROPAGATION_CONTRACTS_DESIGN.md)
  > for Layer 1's detailed design.

  ┌───────────────────────────────────┬──────────────────────────────────────┬──────────────────────────────────────┐
  │              Layer                │              Status                  │          Implementation              │
  ├───────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
  │ L1: Context Propagation           │ Implemented (62 tests)               │ contracts/propagation/               │
  ├───────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
  │ L2: Schema Compatibility          │ Implemented (~68 tests)              │ contracts/schema_compat/             │
  ├───────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
  │ L3: Semantic Conventions          │ Implemented (20 tests)               │ contracts/semconv/                   │
  ├───────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
  │ L4: Causal Ordering               │ Implemented (22 tests)               │ contracts/ordering/                  │
  ├───────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
  │ L5: Capability Propagation        │ Implemented (18 tests)               │ contracts/capability/                │
  ├───────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
  │ L6: SLO Budget Tracking           │ Implemented (19 tests)               │ contracts/budget/                    │
  ├───────────────────────────────────┼──────────────────────────────────────┼──────────────────────────────────────┤
  │ L7: Data Lineage / Provenance     │ Implemented (21 tests)               │ contracts/lineage/                   │
  └───────────────────────────────────┴──────────────────────────────────────┴──────────────────────────────────────┘

  Additionally, 9 extension concerns have been designed (requirements docs in
  docs/design/requirements/REQ_CONCERN_*.md) but not yet implemented.

  The Key Architectural Decision

  The entire system hinges on Layer 1: Context Contracts. Without declared contracts, every other layer is hand-written and brittle. With contracts, the
  other layers become mechanical derivations.

  The question is: where do contracts live and how are they enforced?

  Three approaches:

  A. Code-first — Contracts as Python classes/decorators on phase handlers
  - Pro: Enforced by the runtime, discoverable via introspection
  - Con: Only works for Python phases, requires SDK adoption

  B. Config-first — Contracts as YAML/JSON alongside pipeline definitions
  - Pro: Language-agnostic, works with static analysis tools, human-readable
  - Con: Can drift from code, no runtime enforcement without a validator layer

  C. Dual-declaration (recommended) — Config as source of truth, code validates against it
  - Pro: Static analysis AND runtime enforcement, progressive adoption
  - Con: More complex, but aligns with ContextCore's existing YAML-native patterns

  This aligns with how ContextCore already works: .contextcore.yaml is the config source of truth, and the Python SDK validates against it.

  Why This Is Differentiated

  1. No workflow framework does this. Airflow, Prefect, Temporal, LangGraph — none of them model context propagation as a typed, verifiable concern.
  2. It's the same insight as tasks-as-spans. ContextCore's core thesis is that tasks share structure with OTel spans. Context propagation contracts are the
   natural extension: workflow context shares structure with OTel context propagation (W3C Trace Context, Baggage).
  3. Progressive adoption. Start with detection (L4-L6, already done), add contracts when ready (L1), get prevention for free (L2-L3). This mirrors
  TypeScript's adoption path — you don't need strict mode on day one.
  4. Multi-agent systems need this desperately. As LLM-based agent workflows get more complex, silent context loss between agents becomes the dominant
  failure mode. ContextCore is positioned at exactly the right layer to solve this.

  ---
  Want me to enter plan mode to design the implementation, starting with Layer 1 (Context Contracts) as the keystone?