# Deterministic Observability & TODO Completion — Requirements

**Version:** 3.0.0
**Created:** 2026-03-18
**Revised:** 2026-03-21 — v3: Eliminated separate workflow; TODO tasks are now first-class Prime Contractor seed tasks dispatched through existing complexity routing and shortcut infrastructure.
**Status:** Draft
**Depends on:** `PRIME_CONTRACTOR_REQUIREMENTS.md` (REQ-PC-001–014), `PRIME_EXECUTION_MODES_REQUIREMENTS.md` (REQ-PEM-000–012), Pipeline-Innate Requirements (REQ-CDP-OBS-001–007), ContextCore EXPORT stage
**Source:** Run-068/069 Java adservice analysis — observability stubs present but unimplemented; pipeline already produces all context needed to implement them. Run-079/084/094 execution analysis — separate workflow had 0% completion rate due to API mismatch, LLM overwrite of uncomment tasks, and first-failure abort.
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
**Status:** Implemented (2026-03-18) — revised to protocol-based derivation (REQ-ICD-100 in ContextCore)
**Implemented in:** ContextCore (`contextcore manifest export`)
**Source files:** `src/contextcore/utils/instrumentation.py`, `src/contextcore/utils/onboarding.py`

The EXPORT stage MUST derive required metrics from dashboard artifact specifications.

**Acceptance criteria:**
1. For each dashboard artifact in the artifact manifest, parse the panel definitions to extract PromQL metric names and label sets
2. For each Prometheus alerting rule artifact, parse the `expr` field to extract metric names, thresholds, and label selectors
3. Produce a `instrumentation_contract.metrics.required` list with: metric name, type (counter/histogram/gauge), required labels, source artifact reference
4. If no dashboard or alerting artifacts exist for a service, `metrics.required` is empty (graceful degradation — no instrumentation forced without external contracts)

#### REQ-TCW-001: Communication-Graph-to-Traces Derivation

**Priority:** P1
**Status:** Implemented (2026-03-18) — REQ-ICD-101 in ContextCore
**Implemented in:** ContextCore (`contextcore manifest export`)

The EXPORT stage MUST derive required trace spans from the service communication graph and logging configuration.

**Acceptance criteria:**
1. For each service in `service_communication_graph.services`, determine the transport protocol (gRPC, HTTP) and the downstream services it calls
2. For each RPC or HTTP endpoint, derive the expected span name pattern (e.g., `{service}/{method}` for gRPC)
3. From the logging configuration (if present in the generated code or plan), extract trace context field names that must be populated by the tracing SDK
4. Produce a `instrumentation_contract.traces.required` list with: span name pattern, required attributes, propagation format (W3C/B3), source reference

#### REQ-TCW-002: Language-Aware SDK Resolution

**Priority:** P1
**Status:** Implemented (2026-03-18) — REQ-ICD-102 + REQ-ICD-104 (language detection) in ContextCore
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
**Status:** Implemented (2026-03-18) — REQ-ICD-103 in ContextCore (emitted as `instrumentation_hints`)
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
**Status:** Implemented (2026-03-18) — `src/startd8/validators/todo_scanner.py` (603 lines, 30+ tests)
**Source files:** `src/startd8/validators/todo_scanner.py`

The pipeline MUST scan generated files for TODO markers and produce a structured inventory.

**Acceptance criteria:**
1. Detects `// TODO`, `# TODO`, `/* TODO */`, `@TODO`, and `// @TODO` patterns (case-insensitive)
2. Detects commented-out code blocks: contiguous runs of 3+ commented lines containing executable-looking content (imports, function calls, shell commands)
3. Detects empty method stubs: methods whose body contains only a TODO comment, `pass`, `return`, or variable declarations with no functional logic
4. For each TODO, captures: file path, line number, language, raw text, surrounding context (5 lines before/after), containing function/class name (if parseable)
5. Output is a `TodoInventory` dataclass serializable to JSON

#### REQ-TCW-101: TODO Classification

**Priority:** P1
**Status:** Implemented (2026-03-18) — `classify_todo()` in `todo_scanner.py`
**Depends on:** REQ-TCW-100 (implemented)

Each detected TODO MUST be classified into Category A (commented-out implementation), Category B (contract-derivable), or Category C (insufficient context).

**Acceptance criteria:**
1. **Category A detection:** TODO is adjacent to (within 3 lines of) a contiguous commented-out code block. The commented-out block contains language-appropriate syntax (imports, function calls, shell commands, configuration directives).
2. **Category B detection:** TODO is inside a method/function body that is otherwise empty or stub-like, AND an `instrumentation_contract` exists for this service in the onboarding metadata with non-empty `metrics.required` or `traces.required` that map to this method's purpose. The contract provides the behavioral specification.
3. **Category C detection:** Default. TODOs that match neither A nor B.
4. Classification is recorded in the `TodoInventory` with `category: "A" | "B" | "C"` and `rationale: str`.
5. Category B classification explicitly records the `instrumentation_contract` fields that apply, forming the `attachment_points` section of the contract.
6. **Category S annotation (Anzen, implemented 2026-03-19):** TODOs whose surrounding context (±5 lines) contains security vocabulary (`sql`, `query`, `database`, `credential`, `password`, `npgsql`, `spanner`, etc.) are annotated with `security_sensitive: bool = True`. Category S is a modifier, not a replacement — a TODO can be A+S, B+S, or C+S. `C+S` TODOs are excluded from auto-resolution and flagged for mandatory human review. `B+S` TODOs receive dual contract injection (instrumentation + security) via `derive_tasks_from_todos(security_contract=...)`. See [SECURITY_PRIME_REQUIREMENTS.md](../security-prime/SECURITY_PRIME_REQUIREMENTS.md) §10.

#### REQ-TCW-102: Requirement Cross-Reference

**Priority:** P1
**Status:** Implemented (2026-03-18) — contract_fields linkage in `classify_todo()`
**Depends on:** REQ-TCW-101 (implemented)

Each classified TODO MUST be cross-referenced against pipeline-innate requirements and the instrumentation contract.

**Acceptance criteria:**
1. Category B TODOs are linked to specific `instrumentation_contract` entries: `initStats()` → `metrics.required`, `initTracing()` → `traces.required`
2. Each link traces back to the source artifact: metric → dashboard panel → REQ-CDP-OBS-002; metric → alerting rule → REQ-CDP-OBS-003
3. Category A TODOs are linked to the infrastructure requirement they enable (e.g., Cloud Profiler uncomment → profiling capability)
4. Cross-references are recorded in the TODO inventory with full traceability: `todo_id → contract_field → source_artifact → pipeline_requirement`

#### REQ-TCW-103: TODO Inventory Persistence

**Priority:** P2
**Status:** Implemented (2026-03-18) — `TodoInventory.to_json()` + file write in workflow
**Depends on:** REQ-TCW-100 (implemented)

The TODO inventory MUST be persisted as a pipeline artifact.

**Acceptance criteria:**
1. Written to `{output_dir}/todo-inventory.json` alongside other pipeline artifacts
2. Schema includes: `schema_version`, `run_id`, `scan_timestamp`, `source_run_id` (the pass-one run), `instrumentation_contract_checksum`, `todos: List[TodoEntry]`
3. Each `TodoEntry` includes: `id` (stable hash of file_path + line), `file_path`, `line`, `language`, `raw_text`, `category`, `contract_fields` (what instrumentation contract entries this TODO implements), `matched_requirements`, `status` (`pending` | `planned` | `completed` | `deferred`), `security_sensitive` (bool, Anzen Category S), `security_contract_ref` (optional database ID)
4. Inventory is included in the kaizen index for cross-run tracking
5. Summary includes `security_todos` count alongside A/B/C counts

---

### Layer 2: Seed Injection (REQ-TCW-200–203)

TODO tasks are injected directly into the primary Prime Contractor seed. There is no separate workflow or second PrimeContractorWorkflow instance.

#### REQ-TCW-200: TODO Task Derivation into Primary Seed

**Priority:** P1
**Status:** Partially implemented — `derive_tasks_from_todos()` exists but writes a separate seed
**Depends on:** REQ-TCW-101 (implemented), REQ-TCW-102 (implemented), REQ-TCW-003 (implemented)
**Supersedes:** v2 REQ-TCW-200 (separate completion plan generation)

For each Category A and Category B TODO, the pipeline MUST derive seed tasks and append them to the primary `prime-context-seed.json`.

**Acceptance criteria:**
1. Category A TODOs produce tasks with `task_type: "uncomment"` and `mode: "edit"`. The task's `config.context` includes `todo_line`, `language`, `context_lines`, and `comment_block` (structured line range + content)
2. Category B TODOs produce tasks with `task_type: "implement"` and `mode: "edit"`. No per-task `instrumentation_contract` duplication — the contract is already loaded globally by `load_seed_context()` and injected by `_thread_supplemental_context()`
3. Dependency-addition tasks have `task_type: "dependency"` and `mode: "edit"`
4. Tasks are dependency-ordered: dependencies → uncomment → implement
5. Tasks are appended to the existing seed's `tasks` array (not a separate file), with `TODO-` prefix IDs to distinguish them from structural tasks
6. C+S TODOs (security-sensitive, insufficient context) are excluded and logged for human review

#### REQ-TCW-201: Queue Metadata Threading

**Priority:** P1
**Status:** Not implemented
**Supersedes:** v2 REQ-TCW-201 (per-task context composition)

The `FeatureQueue.add_features_from_seed()` MUST preserve `task_type` through the queue boundary so `develop_feature()` can dispatch on it.

**Acceptance criteria:**
1. `task_type` from the seed task is stored in `FeatureSpec.metadata["task_type"]`
2. For `task_type: "uncomment"`, the full `config.context` (including `comment_block`, `todo_line`, `language`) is preserved in `FeatureSpec.metadata`
3. No changes to the `FeatureSpec` dataclass — all TODO-specific data flows through the existing `metadata: Dict[str, Any]` field

#### REQ-TCW-202: Dependency Task Generation

**Priority:** P1
**Status:** Implemented (2026-03-18) — dependency tasks in `derive_tasks_from_todos()`

When a TODO implementation requires new dependencies, the seed MUST include a dependency-addition task. (Unchanged from v2 — dependency tasks are regular edit-mode tasks.)

**Acceptance criteria:**
1. Dependencies are sourced from `instrumentation_contract.dependencies.add`
2. Language-appropriate build file targeting (build.gradle, go.mod, package.json, requirements.txt)
3. Dependency tasks are edit-mode and ordered before the implementation tasks that need them

#### REQ-TCW-203: Scan Trigger Point

**Priority:** P1
**Status:** Not implemented
**Supersedes:** v2 REQ-TCW-203 (plan validation)

The TODO scan + derivation MUST run after pass-one generation completes and before postmortem.

**Acceptance criteria:**
1. After `PrimeContractorWorkflow.run()` completes its primary task queue, the workflow calls `scan_directory()` on the `generated/` output
2. If TODOs are found, `derive_tasks_from_todos()` produces tasks that are added to the queue via `add_features_from_seed()`
3. The workflow then processes the TODO tasks through the same `develop_feature()` dispatch loop
4. If no TODOs are found, no additional tasks are created (graceful no-op)
5. The TODO inventory is persisted to `{output_dir}/instrumentation/todo-inventory.json` regardless of whether tasks were derived
6. Max task limit (default: 20) applies — excess TODO tasks are logged and deferred

---

### Layer 3: Execution via Prime Contractor Dispatch (REQ-TCW-300–303)

TODO tasks execute through the existing `develop_feature()` 9-phase pipeline. Category A tasks use a zero-cost shortcut modeled on `_try_copy_shortcut()`. Category B tasks use the normal complexity-routed LLM generation path. No separate workflow class or execution method.

#### REQ-TCW-300: Uncomment Shortcut in develop_feature()

**Priority:** P1
**Status:** Not implemented
**Supersedes:** v2 REQ-TCW-300 (separate `_execute_plan()`), v2 REQ-TCW-301 (uncomment via LLM)

Category A tasks MUST be handled by a deterministic shortcut in `develop_feature()`, bypassing LLM generation entirely.

**Acceptance criteria:**
1. A new Phase 0.5 `_try_uncomment_shortcut(feature)` runs between Phase 0 (copy shortcut) and Phase 1 (preflight) in `develop_feature()`
2. It checks `feature.metadata.get("task_type") == "uncomment"` — returns `None` (not applicable) for all other tasks
3. When matched, it reads the target file, calls `uncomment_block()` from `todo_scanner.py`, writes the result, marks the feature as `GENERATED`, and returns `True`
4. Cost is $0.00 — no LLM calls, no spec/draft/review cycle
5. On failure (file not found, write error), it marks the feature as failed and returns `False` — same error contract as `_try_copy_shortcut()`
6. Per-task error isolation: a failed uncomment does NOT block independent subsequent tasks (existing Prime Contractor behavior)
7. The existing `TodoUncommentStep` in the repair pipeline remains as a fallback for LLM-generated code that contains commented-out blocks (different use case — repair runs on LLM output, this shortcut runs instead of LLM)

#### REQ-TCW-301: Category B via Normal Generation Path

**Priority:** P1
**Status:** Partially implemented — instrumentation contract injection exists, task_type threading does not
**Supersedes:** v2 REQ-TCW-302 (separate Category B execution)

Category B tasks MUST execute through the standard `develop_feature()` path with instrumentation contract context.

**Acceptance criteria:**
1. Category B tasks pass through Phase 0 (copy shortcut → `None`), Phase 0.5 (uncomment shortcut → `None`, because `task_type != "uncomment"`), and proceed to Phase 1+ normally
2. The instrumentation contract is already injected into `gen_context` by `_thread_supplemental_context()` at line 3534 — no additional wiring needed for the global contract
3. Per-task contract fields from `config.context.contract_fields` are preserved in `FeatureSpec.metadata` and available to the generation context via `_build_generation_context()` which reads `feature.metadata`
4. Complexity routing classifies these tasks based on their actual signals (estimated LOC, target file count, etc.) — no hardcoded tier override
5. The repair pipeline (including `TodoUncommentStep`) runs on the LLM output as usual

#### REQ-TCW-302: Instrumentation Contract Global Injection

**Priority:** P1
**Status:** Implemented (2026-03-18) — `load_seed_context()` line 1613 + `_thread_supplemental_context()` line 3534

The Prime Contractor MUST load the instrumentation contract from the seed's onboarding metadata and inject it into every task's generation context.

**Acceptance criteria:**
1. `load_seed_context()` reads `onboarding.instrumentation_hints`, normalizes via `normalize_instrumentation_data()`, stores as `self._instrumentation_contract`
2. `_thread_supplemental_context()` injects `instrumentation_contract` into `gen_context` for every task (not just TODO tasks) — already implemented
3. Per-task `config.context.instrumentation_contract` overrides take precedence (already handled by the `not in gen_context` guard)
4. This means Category B TODO tasks automatically receive the full contract without any per-task assembly in `todo_derivation.py`

#### REQ-TCW-303: Inventory Update on Completion

**Priority:** P2
**Status:** Not implemented
**Supersedes:** v2 REQ-TCW-303 (separate commit identity)

After TODO tasks execute, the TODO inventory MUST be updated with completion status.

**Acceptance criteria:**
1. After the TODO task batch completes, the workflow re-reads the inventory file and updates `status` for each entry: `completed` (task passed), `failed` (task failed), `deferred` (task not attempted due to max_tasks limit)
2. Updated inventory is written back to `{output_dir}/instrumentation/todo-inventory.json`
3. Separate commit identity is NOT required — TODO tasks produce output in the same `generated/` directory as structural tasks (they modify the same files)

---

### Layer 4: Pipeline Integration (REQ-TCW-400–402)

#### REQ-TCW-400: Opt-In Activation

**Priority:** P2
**Status:** Not implemented

**Acceptance criteria:**
1. `PrimeContractorWorkflow` accepts a `enable_todo_completion: bool` config flag (default: `False`)
2. When enabled, the post-generation TODO scan + task injection runs automatically
3. The flag is surfaced in `pipeline.env` as `ENABLE_TODO_COMPLETION=true` and in CLI as `--todo-completion`
4. `--todo-completion --scan-only` produces the inventory without executing tasks (dry run mode)

#### REQ-TCW-401: Kaizen Integration

**Priority:** P2
**Status:** Not implemented
**Supersedes:** v2 REQ-TCW-402

**Acceptance criteria:**
1. `kaizen-metrics.json` includes: `todo_count`, `todo_completed`, `todo_deferred`, `todo_completion_rate`
2. If instrumentation contract is present: `instrumentation_coverage` (percentage of contract entries satisfied by generated code, computed by `instrumentation_coverage.py`)
3. Cross-run trends track `todo_completion_rate` alongside success rate and cost

#### REQ-TCW-402: Closed-Loop Validation (Future)

**Priority:** P3
**Status:** Not implemented
**Supersedes:** v2 REQ-TCW-403

The pipeline SHOULD validate that generated instrumentation satisfies the external observability contracts.

**Acceptance criteria:**
1. For each `metrics.required` entry in the instrumentation contract, verify that the generated code contains a reference to that metric name (grep-level validation)
2. Mismatches are reported as `instrumentation_gaps` in the postmortem
3. This enables a future quality loop: dashboard evolves → contract updates → next generation fills gaps

---

## Data Flow (v3 — Single-Pass Integration)

```
ContextCore                              StartD8 SDK
──────────                               ───────────

Stage 0: CREATE
  .contextcore.yaml
  └── spec.observability + spec.targets
          │
          ▼
Stage 4: EXPORT
  onboarding-metadata.json
  ├── instrumentation_hints ──────────────────────────────┐
  ├── dashboard/alerting artifact specs                   │
  └── service_communication_graph                         │
          │                                               │
          ════════════════════════════════════════════     │
          │                                               │
          ▼                                               │
Stage 5: PLAN-INGESTION                                   │
  prime-context-seed.json                                 │
  ├── PI-001–007: structural tasks                        │
  └── onboarding.instrumentation_hints ───────────────────┘
          │
          ▼
Stage 6: CONTRACTOR — Primary Queue
  PrimeContractorWorkflow.run()
  ├── load_seed_context() ──→ self._instrumentation_contract
  ├── develop_feature(PI-001) ... develop_feature(PI-007)
  │   └── _thread_supplemental_context() injects contract
  │
  ├── generated/
  │   ├── AdService.java ──→ initStats() empty, initTracing() empty
  │   ├── build.gradle ──→ profiler commented out
  │   └── Dockerfile ──→ profiler download commented out
  │
  ├── ═══ POST-GENERATION TODO SCAN (REQ-TCW-203) ═══
  │   scan_directory(generated/) → todo-inventory.json
  │   derive_tasks_from_todos() → TODO-001–005 appended to queue
  │
  ├── develop_feature(TODO-001: uncomment profiler JVM)
  │   └── Phase 0.5: _try_uncomment_shortcut() → $0.00
  ├── develop_feature(TODO-002: uncomment profiler wget)
  │   └── Phase 0.5: _try_uncomment_shortcut() → $0.00
  ├── develop_feature(TODO-003: add OTel deps)
  │   └── Phase 5+7: complexity router → LLM edit
  ├── develop_feature(TODO-004: implement initStats)
  │   └── Phase 5+7: complexity router → LLM edit (contract in gen_context)
  └── develop_feature(TODO-005: implement initTracing)
      └── Phase 5+7: complexity router → LLM edit (contract in gen_context)
          │
          ▼
Postmortem (single run)
  ├── todo-inventory.json (status: completed/failed)
  ├── kaizen-metrics.json (todo_completion_rate, instrumentation_coverage)
  └── prime-postmortem-report.json (includes TODO tasks in feature list)
```

---

## The Bigger Picture: Deterministic Observability as a Property

When this is fully implemented, the pipeline guarantees:

1. **If a service has an SLO, it has a dashboard.** (Already true — REQ-CDP-OBS-002)
2. **If it has a dashboard, it has alerting rules.** (Already true — REQ-CDP-OBS-003)
3. **If it has a dashboard, its code emits the metrics the dashboard queries.** (NEW — REQ-TCW-000 + REQ-TCW-301)
4. **If it has RPCs, its code propagates trace context.** (NEW — REQ-TCW-001 + REQ-TCW-301)
5. **If its logging config has trace fields, the tracing SDK populates them.** (NEW — REQ-TCW-001)

This is the shift from intentional to deterministic. The human declares "this service has 99.9% availability SLO" in the manifest. Everything downstream — the dashboard, the alerts, the metrics emission, the trace propagation, the log correlation — is derived. The TODO stubs were always just a placeholder for this derivation chain. Now the chain is complete.

---

## v3 Architectural Rationale

### Why v2 failed (runs 079, 084, 092–094)

The v2 architecture ran TODO completion as a **separate workflow** (`TodoCompletionWorkflow`) that instantiated a **second `PrimeContractorWorkflow`** with its own queue, state file, and code generator. This produced three independent failure modes:

1. **API mismatch (run-079):** `_execute_plan()` passed `agents` kwarg that `PrimeContractorWorkflow.run()` doesn't accept → `TypeError`, 0% execution
2. **LLM overwrite (run-084):** Category A "uncomment" tasks were sent through the full LLM spec→draft→review cycle. The LLM rewrote the entire file instead of removing comment markers → `F821 Undefined name`, 0% pass rate
3. **First-failure abort (run-084):** After TODO-001 failed, TODO-002 through TODO-008 stayed at `pending` — no per-task error isolation in the separate workflow's execution loop

### Why v3 eliminates these failures

1. **No second workflow instance.** TODO tasks are appended to the primary queue and processed by the same `PrimeContractorWorkflow.run()` loop that already handles structural tasks. No API mismatch possible.
2. **Uncomment shortcut bypasses LLM.** Category A tasks hit `_try_uncomment_shortcut()` (Phase 0.5) which calls `uncomment_block()` deterministically — same pattern as `_try_copy_shortcut()`. The LLM never sees these tasks.
3. **Per-task isolation is inherited.** `develop_feature()` already wraps each task in try/except with `queue.fail_feature()`. Failed TODOs don't block others.

### What existing infrastructure is reused

| Existing capability | Location | Reuse for TODO |
|---|---|---|
| `_try_copy_shortcut()` | `prime_contractor.py:3314` | Architectural pattern for `_try_uncomment_shortcut()` |
| `_thread_supplemental_context()` | `prime_contractor.py:3534` | Already injects `instrumentation_contract` into gen_context |
| `load_seed_context()` | `prime_contractor.py:1613` | Already loads `instrumentation_hints` from onboarding |
| `TodoUncommentStep` | `repair/steps/todo_uncomment.py` | Repair fallback for LLM-generated commented-out code |
| `uncomment_block()` | `validators/todo_scanner.py` | Core uncomment function, shared with shortcut |
| `add_features_from_seed()` | `queue.py:228` | Queue boundary for injecting TODO tasks |
| Per-task error isolation | `develop_feature()` try/except | Inherited — no custom error handling needed |
| Complexity routing | `_route_complexity()` | Category B tasks routed by actual signals, not hardcoded |

### What is deleted

| File | Lines | Reason |
|---|---|---|
| `TodoCompletionWorkflow` class | 454 | Replaced by in-band dispatch in `develop_feature()` |
| `_execute_plan()` method | 138 | No separate execution — Prime Contractor handles all tasks |
| `scripts/run_todo_completion.py` | 249 | Replaced by `--todo-completion` flag on existing pipeline |
| Separate `instrumentation-seed.json` | — | TODO tasks live in primary seed |

### What is kept

| File | Lines | Reason |
|---|---|---|
| `validators/todo_scanner.py` | 723 | Detection + classification engine — solid, well-tested |
| `seeds/todo_derivation.py` | 322 | Task derivation — updated to append to existing seed |
| `repair/steps/todo_uncomment.py` | 39 | Repair fallback (different use case from shortcut) |
| `validators/instrumentation_coverage.py` | 234 | Kaizen metrics |

---

## Phasing

### Phase 1: Instrumentation Contract Derivation (ContextCore) — COMPLETE

**Requirements:** REQ-TCW-000–003 (implemented as REQ-ICD-100–104 in ContextCore)
**Status:** Implemented 2026-03-18. Emitted as `instrumentation_hints` (not `instrumentation_contracts`) in `onboarding-metadata.json`. Protocol-based derivation replaced PromQL parsing per implementation findings.
**Files:** `src/contextcore/utils/instrumentation.py` (273 lines, 25 tests)

### Phase 2: TODO Scanner + Inventory (StartD8 SDK) — COMPLETE

**Requirements:** REQ-TCW-100–103
**Status:** Implemented 2026-03-18. `normalize_instrumentation_data()` bridges ContextCore hints → StartD8 contract schema.
**Files:** `src/startd8/validators/todo_scanner.py` (723 lines, 30+ tests)

### Phase 3: Prime Contractor Integration (StartD8 SDK) — IN PROGRESS

**Requirements:** REQ-TCW-200, REQ-TCW-201, REQ-TCW-300, REQ-TCW-301, REQ-TCW-303
**Status:** Implementing. See plan: `docs/plans/todo-completion-v3-integration.md`
**Scope:** Queue metadata threading, uncomment shortcut, post-generation scan trigger, inventory update
**Files modified:**
- `src/startd8/contractors/queue.py` — thread `task_type` into metadata
- `src/startd8/contractors/prime_contractor.py` — `_try_uncomment_shortcut()`, post-generation scan hook
- `src/startd8/seeds/todo_derivation.py` — updated to return tasks (not write separate seed)

### Phase 4: Pipeline Integration + Kaizen (Both) — PLANNED

**Requirements:** REQ-TCW-400–402
**Status:** Not yet implemented.
**Scope:** Opt-in flag, Kaizen metrics emission, closed-loop validation
**Prerequisite:** Phase 3 complete

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Dashboard PromQL parsing complexity — queries may use functions, aggregations, label matchers that are hard to parse for metric names | Medium | Medium | Start with simple `metric_name{label=...}` extraction; complex queries fall back to regex-based metric name extraction |
| OTel SDK version drift — generated code may reference outdated SDK APIs | Medium | Low | Use `"latest_stable"` with language profile version resolution; advisory compilation where toolchain available |
| Category B implementation quality — LLM may produce incorrect SDK initialization | Medium | High | Instrumentation contract provides exact specification; post-generation stub detection catches incomplete implementations; advisory syntax check |
| Over-instrumentation — contract derives metrics the service doesn't meaningfully emit | Low | Low | Contract is derived from dashboards that humans designed; if the dashboard asks for it, the service should emit it |
| Queue ordering — TODO tasks appended after structural tasks may execute before their target files exist | Low | High | TODO scan runs after pass-one generation completes; target files verified before task creation (REQ-TCW-203 AC4) |
| ~~Instrumentation contract staleness~~ | ~~Low~~ | ~~Medium~~ | ~~v2 risk~~ — eliminated in v3 because TODO scan runs after generation, not before; attachment points derived from actual generated files |
| ~~API mismatch between workflows~~ | ~~High~~ | ~~Critical~~ | ~~v2 risk~~ — eliminated in v3 because there is only one PrimeContractorWorkflow instance |
| ~~LLM overwrite of uncomment tasks~~ | ~~High~~ | ~~Critical~~ | ~~v2 risk~~ — eliminated in v3 because uncomment tasks bypass LLM entirely via Phase 0.5 shortcut |
