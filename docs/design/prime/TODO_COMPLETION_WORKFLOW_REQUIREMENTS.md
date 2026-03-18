# Deterministic Observability & TODO Completion — Requirements

**Version:** 2.0.0
**Created:** 2026-03-18
**Status:** Draft
**Depends on:** `PRIME_CONTRACTOR_REQUIREMENTS.md` (REQ-PC-001–014), `PRIME_EXECUTION_MODES_REQUIREMENTS.md` (REQ-PEM-000–012), Pipeline-Innate Requirements (REQ-CDP-OBS-001–007), ContextCore EXPORT stage
**Source:** Run-068/069 Java adservice analysis — observability stubs present but unimplemented; pipeline already produces all context needed to implement them
**Scope:** Cross-system — ContextCore (Stages 0–4) and StartD8 SDK (Stages 5–6)

---

## Vision

**Every service produced by the Capability Delivery Pipeline is deterministically observable.**

Not because a developer remembered to add metrics. Not because someone wrote a TODO and followed up. Because the pipeline structurally cannot produce a service without internal instrumentation that matches its external observability contracts.

Today the pipeline produces external observability artifacts deterministically — dashboards, alerting rules, SLO definitions, service monitors — all derived from the `.contextcore.yaml` manifest. But the internal instrumentation — the code inside the service that emits the metrics and traces those artifacts consume — is left as TODO stubs for humans to fill in. The dashboards declare the PromQL queries they expect; the services don't emit the metrics those queries reference.

This document closes that gap by deriving an **instrumentation contract** from the existing observability artifacts and feeding it into code generation as first-class task context. The result: the dashboard says "I need `rpc_server_duration_seconds` by `grpc_method`," and the generated `initStats()` configures an OTel MeterProvider with a gRPC interceptor that emits exactly that metric. Not because someone told it to — because the pipeline derived it.

---

## Problem Statement

### What exists today

The pipeline produces two kinds of observability:

1. **External artifacts** (deterministic): Grafana dashboards, Prometheus rules, ServiceMonitors, Loki rules, SLO definitions, runbooks — all auto-generated from the manifest via pipeline-innate requirements (REQ-CDP-OBS-001–007). These are correct, complete, and require no human intervention.

2. **Internal instrumentation** (intentional → absent): The generated source code contains TODO stubs (`initStats()`, `initTracing()`) and commented-out infrastructure blocks (Cloud Profiler agent). These exist because the reference implementation has them. The pipeline faithfully reproduces them as empty shells.

### The disconnect

The external artifacts *assume* the internal instrumentation exists. A Grafana dashboard with a panel querying `rpc_server_duration_seconds{grpc_service="hipstershop.AdService"}` is useless if the service doesn't emit that metric. The dashboard is a contract; the instrumentation is the implementation of that contract. Today, the contract is fulfilled on the dashboard side and broken on the service side.

### Why this is solvable

By the time Stage 6 (Contractor) runs, the pipeline has accumulated everything needed to implement the instrumentation:

| Source | Available at | What it provides |
|--------|-------------|-----------------|
| `.contextcore.yaml` | Stage 0 (CREATE) | Service identity, SLOs, criticality, `spec.observability` config (metrics interval, alert channels, log level, OTLP endpoint) |
| Plan + proto files | Stage 2 (INIT-FROM-PLAN) | RPC contract (service names, method names, request/response types), service communication graph |
| `onboarding-metadata.json` | Stage 4 (EXPORT) | `semantic_conventions` (metric names, attribute namespaces), `derivation_rules`, `service_metadata` (transport protocol), `parameter_schema` |
| Dashboard artifact specs | Stage 4 (EXPORT) | PromQL queries → required metric names and label dimensions |
| Alerting rule specs | Stage 4 (EXPORT) | Alert expressions → required metric names and thresholds |
| Language profile | Stage 5/6 | OTel SDK for the target language, dependency coordinates, interceptor patterns |
| Generated source code | Stage 6 (pass one) | Attachment points (empty method bodies, import locations, build file dependency blocks) |

The gap is not context. The gap is a **derivation step** that computes the instrumentation contract from these sources, and a **generation step** that implements it.

---

## Core Concept: The Instrumentation Contract

An **instrumentation contract** is a structured specification derived from the pipeline's external observability artifacts that declares what internal instrumentation a service must have. It bridges the external (dashboards, alerts) and internal (SDK initialization, interceptors, log context) sides of observability.

### What it contains

```yaml
instrumentation_contract:
  service_id: "hipstershop.AdService"
  language: "java"
  transport: "grpc"

  metrics:
    required:
      - name: "rpc_server_duration_seconds"
        type: "histogram"
        labels: ["grpc_service", "grpc_method", "grpc_status_code"]
        source: "dashboard:adservice-dashboard:panel-latency"
      - name: "rpc_server_requests_total"
        type: "counter"
        labels: ["grpc_service", "grpc_method", "grpc_status_code"]
        source: "prometheus_rule:adservice-alerts:HighErrorRate"
    sdk:
      package: "io.opentelemetry:opentelemetry-sdk"
      interceptor: "io.grpc:grpc-opentelemetry"
      exporter: "io.opentelemetry:opentelemetry-exporter-otlp"

  traces:
    required:
      - span_name: "{grpc_service}/{grpc_method}"
        attributes: ["rpc.system", "rpc.service", "rpc.method"]
        source: "dashboard:adservice-dashboard:panel-traces"
    propagation: "W3C"
    sdk:
      package: "io.opentelemetry:opentelemetry-sdk"
      interceptor: "io.grpc:grpc-opentelemetry"

  logging:
    trace_context_fields:
      - field: "logging.googleapis.com/trace"
        source: "log4j2.xml:KeyValuePair"
      - field: "logging.googleapis.com/spanId"
        source: "log4j2.xml:KeyValuePair"
    structured_format: "json"

  dependencies:
    add:
      - group: "io.opentelemetry"
        artifact: "opentelemetry-sdk"
        version: "latest_stable"
      - group: "io.opentelemetry"
        artifact: "opentelemetry-exporter-otlp"
        version: "latest_stable"
      - group: "io.grpc"
        artifact: "grpc-opentelemetry"
        version: "${grpcVersion}"

  attachment_points:
    - method: "initStats"
      file: "src/adservice/src/main/java/hipstershop/AdService.java"
      action: "implement"
      implements: ["metrics.required"]
    - method: "initTracing"
      file: "src/adservice/src/main/java/hipstershop/AdService.java"
      action: "implement"
      implements: ["traces.required", "logging.trace_context_fields"]
    - block: "defaultJvmOpts"
      file: "src/adservice/build.gradle"
      action: "uncomment"
      implements: ["profiler"]
    - block: "profiler_download"
      file: "src/adservice/Dockerfile"
      action: "uncomment"
      implements: ["profiler"]
```

### How it's derived

The contract is not written by hand. It is computed:

1. **Metrics:** Parse the dashboard artifact spec's PromQL queries → extract metric names and label dimensions → these become `metrics.required` entries. Parse alerting rule expressions → extract additional metric names and thresholds.

2. **Traces:** From `service_communication_graph` → which services call which → trace spans needed at service boundaries. From `semantic_conventions.attributeNamespaces` → required span attributes. From `log4j2.xml` / logging config → trace context fields that must be populated.

3. **Dependencies:** From the language profile → OTel SDK coordinates for the target language. Version resolution from the existing build file's dependency patterns.

4. **Attachment points:** From TODO scanner (REQ-TCW-100) → which methods are stubs, which blocks are commented out.

---

## Requirements

### Layer 0: Instrumentation Contract Derivation — ContextCore (REQ-TCW-000–003)

These requirements are implemented in **ContextCore** as part of the EXPORT stage (Stage 4). They extend `onboarding-metadata.json` with the instrumentation contract.

#### REQ-TCW-000: Dashboard-to-Metrics Derivation

**Priority:** P1
**Status:** Planned
**Implemented in:** ContextCore (`contextcore manifest export`)
**Source files:** `src/contextcore/utils/onboarding.py` (new section), dashboard artifact templates

The EXPORT stage MUST derive required metrics from dashboard artifact specifications.

**Acceptance criteria:**
1. For each dashboard artifact in the artifact manifest, parse the panel definitions to extract PromQL metric names and label sets
2. For each Prometheus alerting rule artifact, parse the `expr` field to extract metric names, thresholds, and label selectors
3. Produce a `instrumentation_contract.metrics.required` list with: metric name, type (counter/histogram/gauge), required labels, source artifact reference
4. If no dashboard or alerting artifacts exist for a service, `metrics.required` is empty (graceful degradation — no instrumentation forced without external contracts)

#### REQ-TCW-001: Communication-Graph-to-Traces Derivation

**Priority:** P1
**Status:** Planned
**Implemented in:** ContextCore (`contextcore manifest export`)

The EXPORT stage MUST derive required trace spans from the service communication graph and logging configuration.

**Acceptance criteria:**
1. For each service in `service_communication_graph.services`, determine the transport protocol (gRPC, HTTP) and the downstream services it calls
2. For each RPC or HTTP endpoint, derive the expected span name pattern (e.g., `{service}/{method}` for gRPC)
3. From the logging configuration (if present in the generated code or plan), extract trace context field names that must be populated by the tracing SDK
4. Produce a `instrumentation_contract.traces.required` list with: span name pattern, required attributes, propagation format (W3C/B3), source reference

#### REQ-TCW-002: Language-Aware SDK Resolution

**Priority:** P1
**Status:** Planned
**Implemented in:** ContextCore (`contextcore manifest export`) with language hints from plan metadata

The EXPORT stage MUST resolve the OTel SDK dependency coordinates for the target language.

**Acceptance criteria:**
1. From plan metadata or `service_metadata`, determine the primary language for each service
2. Map language → OTel SDK packages: Java (`io.opentelemetry:opentelemetry-sdk`), Go (`go.opentelemetry.io/otel`), Node.js (`@opentelemetry/sdk-node`), Python (`opentelemetry-sdk`), C# (`OpenTelemetry`)
3. Map language + transport → interceptor/instrumentation packages: Java+gRPC (`io.grpc:grpc-opentelemetry`), Go+gRPC (`go.opentelemetry.io/contrib/instrumentation/google.golang.org/grpc/otelgrpc`), etc.
4. Produce `instrumentation_contract.metrics.sdk` and `instrumentation_contract.traces.sdk` with resolved package coordinates
5. Version resolution: use `"latest_stable"` as default; if the build file already pins a compatible version (e.g., `grpcVersion`), reference that variable

#### REQ-TCW-003: Instrumentation Contract Emission

**Priority:** P1
**Status:** Planned
**Implemented in:** ContextCore (`contextcore manifest export`)

The EXPORT stage MUST emit the instrumentation contract as a section of `onboarding-metadata.json`.

**Acceptance criteria:**
1. `onboarding-metadata.json` includes a top-level `instrumentation_contracts` key: a dict keyed by service ID, each value being the instrumentation contract for that service
2. Each contract includes: `service_id`, `language`, `transport`, `metrics` (with `required` and `sdk`), `traces` (with `required`, `propagation`, `sdk`), `logging` (with `trace_context_fields`), `dependencies` (with `add` list)
3. `attachment_points` are NOT in the export — they are computed in Stage 5/6 after code generation produces the actual files with TODO stubs
4. The contract is checksummed and included in the provenance chain
5. If no observability artifacts exist for a service, the contract is present but empty (schema present, arrays empty)

---

### Layer 1: TODO Detection and Inventory (REQ-TCW-100–103)

These requirements are implemented in **StartD8 SDK** and run after pass-one code generation.

#### REQ-TCW-100: TODO Scanner

**Priority:** P1
**Status:** Planned
**Source files:** New module: `src/startd8/contractors/todo_scanner.py`

The pipeline MUST scan generated files for TODO markers and produce a structured inventory.

**Acceptance criteria:**
1. Detects `// TODO`, `# TODO`, `/* TODO */`, `@TODO`, and `// @TODO` patterns (case-insensitive)
2. Detects commented-out code blocks: contiguous runs of 3+ commented lines containing executable-looking content (imports, function calls, shell commands)
3. Detects empty method stubs: methods whose body contains only a TODO comment, `pass`, `return`, or variable declarations with no functional logic
4. For each TODO, captures: file path, line number, language, raw text, surrounding context (5 lines before/after), containing function/class name (if parseable)
5. Output is a `TodoInventory` dataclass serializable to JSON

#### REQ-TCW-101: TODO Classification

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-100

Each detected TODO MUST be classified into Category A (commented-out implementation), Category B (contract-derivable), or Category C (insufficient context).

**Acceptance criteria:**
1. **Category A detection:** TODO is adjacent to (within 3 lines of) a contiguous commented-out code block. The commented-out block contains language-appropriate syntax (imports, function calls, shell commands, configuration directives).
2. **Category B detection:** TODO is inside a method/function body that is otherwise empty or stub-like, AND an `instrumentation_contract` exists for this service in the onboarding metadata with non-empty `metrics.required` or `traces.required` that map to this method's purpose. The contract provides the behavioral specification.
3. **Category C detection:** Default. TODOs that match neither A nor B.
4. Classification is recorded in the `TodoInventory` with `category: "A" | "B" | "C"` and `rationale: str`.
5. Category B classification explicitly records the `instrumentation_contract` fields that apply, forming the `attachment_points` section of the contract.

#### REQ-TCW-102: Requirement Cross-Reference

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-101

Each classified TODO MUST be cross-referenced against pipeline-innate requirements and the instrumentation contract.

**Acceptance criteria:**
1. Category B TODOs are linked to specific `instrumentation_contract` entries: `initStats()` → `metrics.required`, `initTracing()` → `traces.required`
2. Each link traces back to the source artifact: metric → dashboard panel → REQ-CDP-OBS-002; metric → alerting rule → REQ-CDP-OBS-003
3. Category A TODOs are linked to the infrastructure requirement they enable (e.g., Cloud Profiler uncomment → profiling capability)
4. Cross-references are recorded in the TODO inventory with full traceability: `todo_id → contract_field → source_artifact → pipeline_requirement`

#### REQ-TCW-103: TODO Inventory Persistence

**Priority:** P2
**Status:** Planned
**Depends on:** REQ-TCW-100

The TODO inventory MUST be persisted as a pipeline artifact.

**Acceptance criteria:**
1. Written to `{output_dir}/todo-inventory.json` alongside other pipeline artifacts
2. Schema includes: `schema_version`, `run_id`, `scan_timestamp`, `source_run_id` (the pass-one run), `instrumentation_contract_checksum`, `todos: List[TodoEntry]`
3. Each `TodoEntry` includes: `id` (stable hash of file_path + line), `file_path`, `line`, `language`, `raw_text`, `category`, `contract_fields` (what instrumentation contract entries this TODO implements), `matched_requirements`, `status` (`pending` | `planned` | `completed` | `deferred`)
4. Inventory is included in the kaizen index for cross-run tracking

---

### Layer 2: Instrumentation Task Planning (REQ-TCW-200–203)

#### REQ-TCW-200: Completion Plan Generation

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-101, REQ-TCW-102, REQ-TCW-003

For each Category A and Category B TODO, the workflow MUST generate a completion plan consumable by the Prime Contractor.

**Acceptance criteria:**
1. Category A TODOs produce `uncomment` tasks: target file, line range of commented-out block, validation method (syntax check, build check)
2. Category B TODOs produce `implement` tasks: target file, method signature, behavioral specification derived from the `instrumentation_contract`, required dependency additions
3. Dependency-addition tasks are generated before implementation tasks (e.g., add OTel SDK to `build.gradle` before implementing `initStats()`)
4. Tasks are dependency-ordered: dependencies → implementations → configuration changes
5. Plan is written as a standard Prime Contractor seed JSON, compatible with `run-prime-contractor.sh`
6. Each task carries its `instrumentation_contract` context in `gen_context` — the LLM receives the exact metrics, traces, and SDK packages it must use

#### REQ-TCW-201: Context Composition for Category B

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-200

Category B task specs MUST compose context from the instrumentation contract and pipeline sources.

**Acceptance criteria:**
1. **Metrics tasks** (`initStats`-like): spec includes the exact metric names, types, labels from `instrumentation_contract.metrics.required`; the SDK package coordinates from `metrics.sdk`; the OTLP exporter endpoint from `spec.observability`; and the metrics interval from the manifest
2. **Tracing tasks** (`initTracing`-like): spec includes the span name patterns, required attributes, propagation format from `instrumentation_contract.traces.required`; the SDK and interceptor packages from `traces.sdk`; the exporter endpoint
3. **Logging tasks** (if applicable): spec includes the trace context field names from `instrumentation_contract.logging.trace_context_fields` that must be populated when the tracing SDK is active
4. **Server wiring**: spec includes guidance on where to attach interceptors — derived from the existing server initialization code in the generated file (e.g., `ServerBuilder.forPort(port).addService(...)` → add `.intercept(...)` for OTel gRPC interceptor)
5. All context is assembled into the task's `gen_context` dict following standard Prime Contractor structure

#### REQ-TCW-202: Dependency Task Generation

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-200

When a TODO implementation requires new dependencies, the plan MUST include a dependency-addition task.

**Acceptance criteria:**
1. Dependencies are sourced from `instrumentation_contract.dependencies.add`
2. For Java/Gradle: generates a task to add dependencies to `build.gradle` using the existing `${grpcVersion}` variable pattern where applicable
3. For Go: generates a task to add dependencies to `go.mod`
4. For Node.js: generates a task to add dependencies to `package.json`
5. For Python: generates a task to add dependencies to `requirements.txt` or `pyproject.toml`
6. Dependency tasks are edit-mode (modify existing file, not replace)
7. Version resolution: `"latest_stable"` in the contract is resolved to a specific version at plan time using the language profile's version resolution capability, or left as a range for the LLM to resolve

#### REQ-TCW-203: Plan Validation

**Priority:** P2
**Status:** Planned
**Depends on:** REQ-TCW-200

The generated completion plan MUST be validated before execution.

**Acceptance criteria:**
1. All target files referenced in the plan exist on disk
2. All dependency tasks precede their dependent implementation tasks in the queue
3. No task targets a file that is also targeted by another task in the same plan (conflict detection) — except dependency + implementation pairs targeting the same build file, which are allowed in order
4. The instrumentation contract checksum matches the one recorded in the TODO inventory (no stale contract)
5. Plan size is bounded: if the plan exceeds a configurable task limit (default: 20), it is split into prioritized batches with Category A tasks first

---

### Layer 3: Execution (REQ-TCW-300–303)

#### REQ-TCW-300: Execution via Prime Contractor

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-200

TODO completion tasks MUST be executed using the standard Prime Contractor workflow.

**Acceptance criteria:**
1. The completion plan seed is passed to `PrimeContractorWorkflow` via the same entry point as any other prime run
2. All tasks run in edit mode — the target files already exist from pass one
3. The run is tagged with `source: "instrumentation"` and `parent_run_id: "{pass_one_run_id}"` for traceability
4. Postmortem evaluation runs on the completion results using the standard Kaizen pipeline

#### REQ-TCW-301: Category A Execution (Uncomment)

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-300

Category A tasks MUST uncomment the specified block and validate the result.

**Acceptance criteria:**
1. The task's spec prompt identifies the exact line range to uncomment
2. The drafter produces the uncommented version of the block
3. Post-generation validation: language-appropriate syntax check on the modified file
4. If uncommenting introduces a dependency not present in the build file, a warning is emitted and the dependency task (REQ-TCW-202) must have already run

#### REQ-TCW-302: Category B Execution (Implement from Contract)

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-300, REQ-TCW-201

Category B tasks MUST generate instrumentation code that satisfies the instrumentation contract.

**Acceptance criteria:**
1. The task's spec prompt includes: method signature, the specific `instrumentation_contract` entries to implement, SDK package coordinates, server wiring guidance
2. The drafter generates the method body implementation
3. The generated code replaces the TODO stub (empty method body → functional implementation)
4. Post-generation validation: syntax check, import resolution, stub detection (the implemented method should have zero stubs remaining)
5. **Contract validation (advisory):** if the generated code references metric names or span attributes, they SHOULD match the `instrumentation_contract` entries. Mismatches are logged as warnings, not failures (LLM output is not fully deterministic).

#### REQ-TCW-303: Separate Commit Identity

**Priority:** P1
**Status:** Planned
**Depends on:** REQ-TCW-300

Instrumentation output MUST be committed separately from pass-one output.

**Acceptance criteria:**
1. Completion results are written to `{output_dir}/instrumentation/` (separate from `generated/`)
2. If auto-commit is enabled, the commit message follows: `feat(instrumentation): implement observability for {service_name} from {pass_one_run_id}`
3. The commit does not include any pass-one files that were not modified by the instrumentation workflow
4. The TODO inventory is updated with `status: completed` for each successfully implemented TODO

---

### Layer 4: Pipeline Integration (REQ-TCW-400–403)

#### REQ-TCW-400: CLI Integration

**Priority:** P2
**Status:** Planned

**Acceptance criteria:**
1. `run-prime-contractor.sh --instrumentation --provenance {run-provenance.json}` triggers the workflow
2. `--instrumentation --scan-only` produces the TODO inventory without executing (dry run)
3. `--instrumentation --category A` limits to Category A only (conservative mode)
4. `--instrumentation --category A,B` executes both categories (full mode, default)

#### REQ-TCW-401: Pipeline Stage Integration

**Priority:** P2
**Status:** Planned

**Acceptance criteria:**
1. Opt-in via `pipeline.env`: `ENABLE_INSTRUMENTATION=true`
2. When enabled, runs automatically after the primary Prime Contractor stage completes with `verdict: PASS`
3. Does not run if the primary stage fails
4. Stage produces its own provenance entry in the run chain

#### REQ-TCW-402: Kaizen Integration

**Priority:** P2
**Status:** Planned

**Acceptance criteria:**
1. `kaizen-metrics.json` includes: `todo_count`, `todo_completed`, `todo_deferred`, `todo_completion_rate`, `instrumentation_coverage` (percentage of `instrumentation_contract` entries satisfied by generated code)
2. Cross-run trends track instrumentation coverage alongside success rate and cost
3. Instrumentation contract satisfaction becomes a Kaizen quality dimension

#### REQ-TCW-403: Closed-Loop Validation (Future)

**Priority:** P3
**Status:** Planned

The pipeline SHOULD validate that generated instrumentation satisfies the external observability contracts.

**Acceptance criteria:**
1. For each `metrics.required` entry in the instrumentation contract, verify that the generated code contains a reference to that metric name (grep-level validation)
2. For each dashboard panel PromQL query, verify that every metric name referenced in the query appears in either `metrics.required` or the generated code
3. Mismatches are reported as `instrumentation_gaps` in the postmortem — the dashboard expects a metric that the service doesn't emit
4. This enables a future quality loop: if the dashboard evolves (new panels), the instrumentation contract updates, and the next generation pass fills the new gaps

---

## Data Flow

```
ContextCore                              StartD8 SDK
──────────                               ───────────

Stage 0: CREATE
  .contextcore.yaml
  ├── spec.observability.metricsInterval
  ├── spec.observability.alertChannels
  ├── spec.requirements.availability
  └── spec.targets[].services
          │
          ▼
Stage 4: EXPORT
  onboarding-metadata.json
  ├── semantic_conventions.metrics     ──┐
  ├── derivation_rules                   ├──→ NEW: instrumentation_contracts
  ├── service_metadata.transport         │    ├── metrics.required (from dashboards)
  ├── dashboard artifact spec      ──────┤    ├── traces.required (from comm graph)
  ├── alerting rule artifact spec  ──────┘    ├── dependencies.add (from lang profile)
  └── service_communication_graph             └── logging.trace_context_fields
          │
          ════════════════════════════════════════════
          │
          ▼
Stage 5: PLAN-INGESTION
  prime-context-seed.json
  ├── Tier 1 tasks (structural — from plan)
  │   ├── PI-001: AdService.java (with TODO stubs)
  │   ├── PI-002: AdServiceClient.java
  │   └── PI-003–007: configs, Dockerfile
  └── instrumentation_contracts (forwarded from export)
          │
          ▼
Stage 6: CONTRACTOR (Pass One)
  generated/
  ├── AdService.java ──→ initStats() empty, initTracing() empty
  ├── build.gradle ──→ profiler commented out
  └── Dockerfile ──→ profiler download commented out
          │
          ▼
TODO Scanner (REQ-TCW-100)
  todo-inventory.json
  ├── TODO-1: initStats()      → Category B (contract: metrics.required)
  ├── TODO-2: initTracing()    → Category B (contract: traces.required)
  ├── TODO-3: profiler JVM     → Category A (uncomment)
  └── TODO-4: profiler wget    → Category A (uncomment)
          │
          ▼
Completion Plan (REQ-TCW-200)
  instrumentation-seed.json
  ├── Task 1: add OTel deps to build.gradle
  ├── Task 2: uncomment profiler JVM flags
  ├── Task 3: uncomment profiler download
  ├── Task 4: implement initStats() ← contract: metrics.required
  └── Task 5: implement initTracing() ← contract: traces.required
          │
          ▼
Stage 6: CONTRACTOR (Instrumentation Pass)
  instrumentation/
  ├── build.gradle (OTel deps + profiler)
  ├── Dockerfile (profiler download)
  └── AdService.java (OTel MeterProvider + TracerProvider + gRPC interceptors)
          │
          ▼
Postmortem + Closed-Loop Validation
  ├── todo-inventory.json (status: completed)
  ├── kaizen-metrics.json (instrumentation_coverage: 100%)
  └── instrumentation_gaps: [] (dashboard metrics ⊆ emitted metrics)
```

---

## The Bigger Picture: Deterministic Observability as a Property

When this is fully implemented, the pipeline guarantees:

1. **If a service has an SLO, it has a dashboard.** (Already true — REQ-CDP-OBS-002)
2. **If it has a dashboard, it has alerting rules.** (Already true — REQ-CDP-OBS-003)
3. **If it has a dashboard, its code emits the metrics the dashboard queries.** (NEW — REQ-TCW-000 + REQ-TCW-302)
4. **If it has RPCs, its code propagates trace context.** (NEW — REQ-TCW-001 + REQ-TCW-302)
5. **If its logging config has trace fields, the tracing SDK populates them.** (NEW — REQ-TCW-001)

This is the shift from intentional to deterministic. The human declares "this service has 99.9% availability SLO" in the manifest. Everything downstream — the dashboard, the alerts, the metrics emission, the trace propagation, the log correlation — is derived. The TODO stubs were always just a placeholder for this derivation chain. Now the chain is complete.

---

## Phasing

### Phase 1: Instrumentation Contract Derivation (ContextCore)

**Requirements:** REQ-TCW-000–003
**Scope:** Extend `contextcore manifest export` to derive and emit `instrumentation_contracts` in `onboarding-metadata.json`
**Prerequisite for:** Everything else
**Estimated effort:** Medium (new derivation logic in export, language→SDK mapping table)

### Phase 2: TODO Scanner + Inventory (StartD8 SDK)

**Requirements:** REQ-TCW-100–103
**Scope:** New `todo_scanner.py` module; read-only, can be deployed immediately to collect data
**Prerequisite for:** Layers 2–3
**Estimated effort:** Small (pattern matching + classification logic)

### Phase 3: Category A Completion (StartD8 SDK)

**Requirements:** REQ-TCW-200 (partial), REQ-TCW-300, REQ-TCW-301, REQ-TCW-303
**Scope:** Uncomment workflow — lowest risk, highest certainty
**Prerequisite for:** None (independent of Category B)
**Estimated effort:** Small (plan generation for uncomment + execution)

### Phase 4: Category B Completion (StartD8 SDK)

**Requirements:** REQ-TCW-200 (full), REQ-TCW-201, REQ-TCW-202, REQ-TCW-302
**Scope:** Context-composition and implementation from instrumentation contract — the high-value path
**Prerequisite for:** Phase 1 (needs instrumentation contracts from export)
**Estimated effort:** Medium (context composition + task generation)

### Phase 5: Pipeline Integration + Closed-Loop (Both)

**Requirements:** REQ-TCW-400–403
**Scope:** CLI, pipeline stage, Kaizen integration, contract validation
**Prerequisite for:** Phases 2–4 complete
**Estimated effort:** Small (plumbing + validation logic)

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dashboard PromQL parsing complexity — queries may use functions, aggregations, label matchers that are hard to parse for metric names | Medium | Medium | Start with simple `metric_name{label=...}` extraction; complex queries fall back to regex-based metric name extraction |
| OTel SDK version drift — generated code may reference outdated SDK APIs | Medium | Low | Use `"latest_stable"` with language profile version resolution; advisory compilation where toolchain available |
| Category B implementation quality — LLM may produce incorrect SDK initialization | Medium | High | Instrumentation contract provides exact specification; post-generation stub detection catches incomplete implementations; advisory syntax check |
| Over-instrumentation — contract derives metrics the service doesn't meaningfully emit | Low | Low | Contract is derived from dashboards that humans designed; if the dashboard asks for it, the service should emit it |
| Instrumentation contract staleness — export runs before code generation, contract may not reflect generated code structure | Low | Medium | Attachment points are computed after pass-one generation (REQ-TCW-101), not at export time (REQ-TCW-003 criterion 3) |
