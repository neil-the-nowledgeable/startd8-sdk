# Cross-Cutting Context Loss Analysis

> **Date:** 2026-03-15
> **Scope:** Trace information loss from ContextCore export → cap-dev-pipe → plan ingestion → prime contractor → generated code
> **Method:** End-to-end artifact inspection across run-051 (17/17 PASS, $0.53), ContextCore CREATE stage code inspection
> **Principle:** [Mottainai](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) — every artifact produced by an earlier stage carries invested computation; discarding it is waste
> **Companion:** This document enables investigation in the [ContextCore project](~/Documents/dev/ContextCore) — see Section 9 for specific integration points

---

## 1. The Problem

Two of 17 generated files (PI-004 `email_client.py`, PI-007 `client.py`) consistently produce wrong proto import paths across all runs. The correct modules (`demo_pb2`, `demo_pb2_grpc`) are stated explicitly in at least 5 places in the pipeline artifacts. None of those 5 reach the generating LLM's prompt for these tasks.

This document traces **where** the information exists, **where** it's lost, and **which system** should own the fix — to enable investigation in the ContextCore project.

---

## 2. Pipeline Architecture (First Half → Second Half)

```
ContextCore                        cap-dev-pipe                      startd8-sdk
────────────                       ────────────                      ───────────
                                   Stage 0: CREATE
                                   Stage 1: POLISH (plan quality)
                                   Stage 1.5: ANALYZE-PLAN
ProjectContext.yaml ──────────────→ Stage 2: INIT (manifest bootstrap)
                                   Stage 3: VALIDATE (schema check)
onboarding-metadata.json ─────────→ Stage 4: EXPORT (contracts + provenance)
export-quality-report.json         │
validation-report.json             │
                                   ↓
                                   Stage 5: PLAN-INGESTION ──────────→ plan_ingestion_workflow.py
                                     parse → assess → transform       (5-phase LLM pipeline)
                                     → refine → emit
                                   ↓
                                   prime-context-seed.json ──────────→ Stage 6: PRIME CONTRACTOR
                                                                       PrimeContractorWorkflow
                                                                       context_resolution.py
                                                                       spec_builder.py → LLM
```

---

## 3. What ContextCore Produces vs What the Project Needs

### Domain Mismatch

ContextCore models this project as an **observability platform** — its artifact types are dashboards, SLOs, prometheus rules, runbooks, service monitors. Its derivation rules map `spec.business.criticality` → alert severity.

The plan document describes **Python microservices** — gRPC servers, Flask apps, locustfiles, Dockerfiles. The actual code generation task is source code, not observability artifacts.

This isn't wrong — the ContextCore manifest was originally created for the observability layer of the online-boutique project. But it means the onboarding metadata carries **zero information about the source code layer**:

| ContextCore Knows | ContextCore Doesn't Know |
|---|---|
| 8 observability artifact types | Python service structure |
| Dashboard/SLO/rule dependencies | Service-to-service gRPC dependencies |
| Parameter derivation rules | Proto module names (`demo_pb2`) |
| Metric naming conventions | Import conventions between services |
| Alert severity mapping | Shared code patterns (logging, OTel) |

### What This Means for the Pipeline

The onboarding metadata flows through to the seed faithfully (30 of 31 keys match between export and seed — only `refine_suggestions` is added). But the data is **observability-domain** data being injected into a **source-code-domain** pipeline. The `service_metadata` auto-derivation detects `transport_protocol: "http"` (wrong — most services are gRPC) because it scans the artifact manifest, not the plan document.

---

## 4. Information Existence Map

The proto module information exists at these locations:

| Location | Contains Proto Modules? | Reaches PI-004 Prompt? |
|---|---|---|
| **Plan document** (`python-plan.md`) Non-Goals section | Yes: "`demo_pb2.py`, `demo_pb2_grpc.py` are protoc output" | No — plan_context is truncated to 6K chars, Non-Goals not included |
| **Plan document** PI-003 Implementation Contract | Yes: `Imports: demo_pb2, demo_pb2_grpc` | No — per-task, only PI-003's spec gets this |
| **Seed** `forward_manifest.file_specs["src/emailservice/email_server.py"].elements[0].bases` | Yes: `["demo_pb2_grpc.EmailServiceServicer"]` | No — file_specs are only rendered for the task's own target file |
| **Seed** `service_metadata.api_signatures` | Yes: `"Class BaseEmailService(demo_pb2_grpc.EmailServiceServicer)"` | Indirectly — dumped as JSON in service_metadata, but buried in 80 signature entries |
| **Seed** tasks PI-003 `task_description` | Yes: full import list with `demo_pb2` | No — PI-003's description is only available to PI-003's generation |
| **ContextCore** `onboarding-metadata.json` | **No** — knows about observability, not source code | N/A |
| **ContextCore** `project-context.yaml` | **No** — 1 target, observability-typed | N/A |

### Key Finding

**ContextCore cannot fix this.** The proto module information originates in the plan document, not in the ContextCore manifest. ContextCore models the project at the artifact/observability level, not the source-code/import level. The fix belongs in **plan ingestion** (how the seed is built from the plan) or **context resolution** (how gen_context is built from the seed).

---

## 5. Where the Fix Should Live

### Not ContextCore

Expanding ContextCore to model Python source code structure (import graphs, proto modules, service hierarchies) would be accidental complexity. ContextCore's domain is project observability metadata — making it also model source code dependencies would conflate two concerns.

### Not the Plan Document (alone)

Enriching the plan document with `Imports: demo_pb2, demo_pb2_grpc` on every task is belt-and-suspenders but doesn't compound. New projects would need the same manual effort.

### The Seed — Specifically, Context Resolution

The information exists in the seed's forward manifest. `file_specs["src/emailservice/email_server.py"].elements[0].bases = ["demo_pb2_grpc.EmailServiceServicer"]`. The dependency graph says PI-004 depends on PI-003. PI-003 targets `email_server.py`.

The essential fix: **when building gen_context for PI-004, read the file_specs of PI-004's dependency targets and extract importable module names from base class references.**

This is ~15 lines in `context_resolution.py`. No new data structures. No ContextCore changes. No plan document changes. It uses three things that already exist: the dependency graph, the forward manifest, and the file specs.

---

## 6. Seed Complexity Audit

### Essential (used by Prime, required for generation)

| Section | Size | Purpose |
|---|---|---|
| `tasks` (17) | ~60KB | Task descriptions, target_files, dependencies |
| `forward_manifest.file_specs` (17 files, 51 elements) | ~30KB | Element specs with signatures, bases, kinds |
| `design_calibration` (17 entries) | ~5KB | Per-task token budgets |
| `artifacts.skeleton_sources` (8) | ~15KB | Pre-rendered code skeletons |
| `artifacts.element_tiers` (8) | ~3KB | Micro Prime tier classification |
| `service_metadata` | ~20KB | Runtime deps, API signatures |

### Accidental (carried but not consumed by Prime)

| Section | Size | Issue |
|---|---|---|
| `forward_manifest.contracts` (1,236) | ~400KB | No `file_path` field — `binding_constraints_for_task()` matches by `applicable_task_ids` but returns 0 bindings for most tasks. Duplicates element spec data. |
| `onboarding` (32 keys) | ~200KB | 21 of 32 keys are artisan/ContextCore observability metadata. 5 are Prime-relevant. |
| `architectural_context` (9 keys, 7 empty) | ~2KB | `shared_modules=[]`, `constraints=[]`, `preferences=[]` — structurally present but data-absent |
| `plan.parsed_plan` | ~30KB | Only 6K chars reach gen_context via truncation |

**Total seed: 1.3MB. Essential for Prime: ~130KB (~10%).** The remaining 90% is carried for artisan compatibility or is structurally present but empty.

---

## 7. Recommendations for ContextCore Investigation

### Question 1: Should ContextCore Model Source Code Structure?

Currently ContextCore models artifacts (dashboards, SLOs, rules) and their dependencies. If the pipeline generates source code (not just observability artifacts), should ContextCore also model:
- Service-to-service dependencies (emailservice → productcatalogservice via gRPC)
- Shared proto modules (`demo_pb2`, `demo_pb2_grpc`)
- Import conventions (per-service logging patterns)

**Our assessment:** No. This is source-code-domain knowledge that belongs in the plan + forward manifest, not the ContextCore manifest. ContextCore should stay focused on project observability metadata.

### Question 2: Is the Onboarding Metadata Format Efficient for Non-Observability Projects?

The onboarding schema (32 keys) was designed for observability artifact generation. For source code generation projects, 21 of 32 keys are unused. The `service_metadata` auto-derivation defaults to `http` when it should detect `grpc` from the plan.

**Possible improvement:** A lighter onboarding schema variant for source-code projects, or a `project_type` discriminator that suppresses observability-specific sections.

### Question 3: Where Should Cross-Service Import Knowledge Live?

Three options:
1. **ContextCore manifest** — add a `source_modules` section to `ProjectContext.spec`
2. **Plan document** — human-authored, project-specific
3. **Forward manifest** — derived by plan ingestion from the plan document

**Our recommendation:** Option 3. The forward manifest already has `file_specs` with `elements[].bases`. The import module names are derivable from base class references at zero additional cost. The plan ingestion EMIT phase should extract them.

### Question 4: Is the 1,236-Contract Overhead Justified?

The forward manifest carries 1,236 contracts. 752 are `function_name`, 207 are `class_name`. None have `file_path` set. `binding_constraints_for_task()` returns 0 bindings for most tasks. The contracts duplicate what's in `file_specs.elements`.

**For the Prime route:** The contracts add ~400KB of seed overhead with minimal value. The essential data is in `file_specs`. The contracts may serve the artisan route's DESIGN phase better.

---

## 8. Immediate Action Items (startd8-sdk, no ContextCore changes needed)

1. **Context resolution** (`context_resolution.py`): Extract import modules from dependency tasks' `file_specs.elements[].bases` (~15 lines)
2. **Token budget floor**: `max(implement_max_output_tokens, 32768)` (1 line)
3. **Plan document**: Add proto imports to PI-004/PI-007 descriptions (text edit)

These three changes use existing data, require no new abstractions, and fix the quality issue for this project. The ContextCore investigation can proceed independently on questions 1-4 above.

---

## Appendix: Data Flow Diagram (Run 051)

```
ContextCore ProjectContext.yaml
  └── spec.targets: 1 target (observability-typed)
  └── onboarding-metadata.json
        ├── artifact_types: 8 (all observability)
        ├── derivation_rules: 7 (dashboard, prometheus, SLO, etc.)
        ├── service_metadata: transport=http (wrong for gRPC services)
        ├── semantic_conventions: OTel attribute namespaces
        └── 21 more keys (parameter schemas, coverage, provenance, etc.)

cap-dev-pipe plan-ingestion
  ├── INPUT: python-plan.md (human-authored, 17 features)
  │     └── Contains: exact imports, class hierarchies, proto module names
  ├── INPUT: onboarding-metadata.json (from ContextCore export)
  │     └── Contains: observability domain metadata (not source code)
  ├── PARSE: LLM extracts ParsedFeatures (api_signatures, deps, runtime_deps)
  ├── TRANSFORM: Features → PI-001..PI-017 tasks
  ├── EMIT: Tasks + forward_manifest + onboarding → prime-context-seed.json
  │     ├── tasks.PI-003.task_description: has "Imports: demo_pb2, demo_pb2_grpc"
  │     ├── tasks.PI-004.task_description: has "Calls stub.SendOrderConfirmation()" — NO PROTO MODULES
  │     ├── forward_manifest.file_specs: has bases=["demo_pb2_grpc.EmailServiceServicer"]
  │     └── forward_manifest.contracts: 1,236 items, 0 with file_path
  └── OUTPUT: prime-context-seed.json (1.3MB)

startd8-sdk PrimeContractorWorkflow
  ├── load_seed_context(): reads onboarding, arch_context, design_cal, forward_manifest
  ├── PipelineContextStrategy.resolve_task_context():
  │     ├── forward_contracts: from binding_constraints_for_task() — often empty
  │     ├── forward_element_specs: from file_specs — only for THIS task's target file
  │     ├── service_metadata: runtime_deps, api_signatures (80 entries)
  │     ├── architectural_context: 7 of 9 keys empty
  │     └── ❌ DOES NOT: read dependency tasks' file_specs for import modules
  └── spec_builder.py → LLM prompt
        └── PI-004 prompt: no proto module names → LLM hallucinates imports
```

---

## 9. ContextCore CREATE Stage — Deep Examination

### What CREATE Actually Does

**File:** `ContextCore/src/contextcore/cli/core.py` lines 146-229

CREATE is a scaffolding command. It builds a minimal ProjectContext CRD from CLI flags (`--name`, `--project`, `--criticality`, `--owner`, `--target`) and writes `project-context.yaml`. It does NOT parse plan documents, requirements documents, source code, or proto files. The "intelligence" lives in later stages.

### Where Relationships Are Currently Built

| Stage | File | What It Parses | What Relationships It Builds |
|-------|------|---------------|------------------------------|
| **CREATE** (Stage 0) | `core.py:146` | CLI flags only | None — pure scaffolding |
| **ANALYZE-PLAN** (Stage 1.5) | `analyze_plan_ops.py:298` | Plan markdown | Phase-to-phase ordering graph, REQ traceability matrix |
| **INIT-FROM-PLAN** (Stage 2) | `init_from_plan_ops.py:273` | Plan + requirements text | SLO values, criticality, risk lines, guardrails, requirement IDs |
| **EXPORT** (Stage 4) | `manifest_v2.py:492` | Artifact manifest | artifact_dependency_graph (observability artifact ordering) |

**None of these stages parse source code, proto files, or import relationships.**

### The `artifact_dependency_graph` — Observability Only

**File:** `ContextCore/src/contextcore/utils/onboarding.py` lines 666-670

The dependency graph is hardcoded observability artifact ordering:
```
notification → [prometheus-rules]
prometheus-rules → [service-monitor]
runbook → [prometheus-rules, notification]
slo → [service-monitor]
```

This is "which observability artifact must be generated before which other." It is NOT a service-to-service or file-to-file dependency graph.

### The Knowledge Graph — Unimplemented Placeholder

**File:** `ContextCore/src/contextcore/graph/builder.py` line 217

```python
def _infer_dependencies(self) -> None:
    # Find Service resources that could indicate dependencies
    service_resources = [...]
    # Placeholder for future trace-based dependency inference
    pass
```

This is the closest thing to cross-service relationship detection. It's a stub.

### What Requirements Parsing Extracts

**File:** `ContextCore/src/contextcore/cli/init_from_plan_ops.py` lines 336-440

Currently extracted from requirements/plan text:
- SLO values (availability, latencyP99, throughput, errorBudget)
- Criticality indicators (P0-P4)
- Slack channels, owner/team names
- Risk lines, guardrails
- URLs (GitHub, Jira, Grafana)
- Requirement IDs (REQ-N, FR-N, NFR-N)

**NOT extracted:** import statements, service names, proto service definitions, RPC dependencies, file-to-file communication patterns.

### `ServiceMetadataEntry` — Has Schema Contract Field

**File:** `ContextCore/src/contextcore/models/service_metadata.py`

The model already has `schema_contract: Optional[str]` for proto file paths. But it lacks:
- `depends_on_services` — which services this service calls
- `exposes_rpcs` — what RPC methods are served
- `consumes_rpcs` — what RPC methods are called
- `shared_modules` — proto/schema modules shared across services

### `file_ownership` — Closest to Interconnectedness

**File:** `ContextCore/src/contextcore/utils/onboarding.py` lines 934-979

Maps output file paths to owning artifacts, classifies as "primary" (single owner) or "shared" (multiple owners). Designed for artifact conflict detection, not source code modeling. Only covers generated observability files.

### `resolve-provenance.py` — Proto File Discovery Exists

**File:** `cap-dev-pipe/resolve-provenance.py` lines 58-70

Already auto-discovers `*.proto` files from a `context/` directory and passes them as `context_files` to plan ingestion. The proto files are passed as opaque blobs — their service definitions and RPC methods are not parsed.

---

## 10. The Insight: Interconnectedness as Observability Foundation

The user's key insight reframed the problem:

> ContextCore's purpose is to make observability more deterministic. Source code is the first source of insights on importance or business context. A service serving ads is as important as the service submitting orders — equally important irrespective of revenue attribution. Understanding interconnectedness through requirements analysis is a key way to infer connectedness between services.

This means ContextCore should model **service interconnectedness** not as a source-code concern, but as a **prerequisite for correct observability**. If ContextCore knows that `emailservice` communicates with `productcatalogservice` via `demo_pb2_grpc`, it can:

1. Generate correct alert routing (email failures may cascade from catalog failures)
2. Derive trace context propagation requirements
3. Model blast radius for SLO definitions
4. **And as a downstream benefit: provide the import/communication graph that plan ingestion needs to thread cross-task context**

### Where the Information Already Exists

The online-boutique `python-plan.md` contains these statements:

- *"Pre-Provided Artifacts: `protos/demo.proto` → generated stubs `demo_pb2.py`, `demo_pb2_grpc.py`"*
- *PI-003: "Imports: `demo_pb2`, `demo_pb2_grpc`"*
- *PI-006: "Imports: `demo_pb2`, `demo_pb2_grpc`"*
- *PI-006: "Calls `product_catalog_stub.ListProducts(demo_pb2.Empty())`" — service-to-service dependency*
- *"Shared JSON Logger Utility" — shared module pattern*

These are **service interconnectedness signals** parseable from requirements text:
- `Imports: X, Y` → file-to-module dependencies
- `Calls service.Method()` → service-to-service RPC dependencies
- `"Shared ... Utility"` → cross-service shared module patterns
- `demo.proto` → shared schema defining the communication contract

### What ContextCore Could Extract (Before Plan Ingestion)

If `init_from_plan_ops.py` were extended to extract interconnectedness patterns:

```
FROM PLAN TEXT:
  "Imports: demo_pb2, demo_pb2_grpc"
  "Calls product_catalog_stub.ListProducts()"
  "Shared JSON Logger Utility"
  "protos/demo.proto"

DERIVES:
  service_communication_graph:
    emailservice:
      imports: [demo_pb2, demo_pb2_grpc, logger]
      calls: []  # no outbound RPCs
    recommendationservice:
      imports: [demo_pb2, demo_pb2_grpc, logger]
      calls: [productcatalogservice.ListProducts]
    shoppingassistantservice:
      imports: [flask, langchain, alloydb]
      calls: []  # HTTP, not gRPC
    loadgenerator:
      imports: [locust, faker]
      calls: []  # HTTP client, not gRPC

  shared_modules:
    demo_pb2: [emailservice, recommendationservice]
    demo_pb2_grpc: [emailservice, recommendationservice]
    logger: [emailservice, recommendationservice]
```

This graph would flow through `onboarding-metadata.json` → seed → gen_context, giving every task visibility into what modules its siblings import.

### Integration Points in ContextCore

| File | Line | Current Function | Enhancement |
|------|------|-----------------|-------------|
| `init_from_plan_ops.py` | 336-440 | Extracts SLOs, criticality, risks | Add `Imports:` and `Calls:` pattern extraction |
| `onboarding.py` | `build_onboarding_metadata()` | Produces 32-key onboarding dict | Add `service_communication_graph` section |
| `models/service_metadata.py` | `ServiceMetadataEntry` | Has `schema_contract` | Add `imports`, `rpc_dependencies` |
| `graph/builder.py` | `_infer_dependencies()` | Stub placeholder | Implement from plan-derived communication graph |
| `resolve-provenance.py` | 58-70 | Discovers proto files as blobs | Parse proto `service` definitions for RPC names |

### What This Would Enable Downstream

If ContextCore produces a `service_communication_graph` in `onboarding-metadata.json`:

1. **Plan ingestion** can populate `architectural_context.shared_modules` from it (currently empty)
2. **Task enrichment** can thread `imports` from the graph into each task's context
3. **Context resolution** can use it to inject sibling import context without scanning the filesystem
4. **Forward manifest** can generate `import_path` contracts from it
5. **Observability** benefits directly: SLO blast radius, alert routing, trace span relationships all derive from the same graph

The compound interest: one extraction in ContextCore → used by 5 downstream consumers → eliminates the proto import bug → and improves observability correctness.
