# Golden Seed Requirements

**Date:** 2026-03-10 (updated 2026-03-15)
**Status:** Ready for Development
**Author:** Human + Agent collaboration
**Domain:** Plan Ingestion → Designed Seed for Implementation Tuning

---

## 1. Problem Statement

The plan ingestion pipeline (PARSE → ASSESS → TRANSFORM → REFINE → EMIT) produces an enriched seed (`prime-context-seed-enriched.json`) that is significantly richer than the source plan and requirements documents it was derived from. Across 50 runs of the online-boutique calibration workload, the pipeline has iteratively discovered and encoded improvements that do not exist in the source documents:

| Signal | Source Documents | Enriched Seed (run-024) |
|--------|-----------------|------------------------|
| Feature decomposition | 7 coarse features (F-001–F-007) | 17 fine-grained features (F-001a, F-001b, F-002a–c, etc.) |
| API signatures | Prose descriptions | Structured `api_signatures` arrays |
| Runtime dependencies | Scattered across requirements | Per-feature `runtime_dependencies` with pinned versions |
| Negative scope | Implicit in Non-Goals section | Per-feature `negative_scope` arrays |
| Protocol classification | Not present | Per-feature `protocol` (grpc, library, flask, locust, none) |
| Design doc sections | Not present | Per-feature `design_doc_sections` arrays |
| Labels | Not present | Per-feature `labels` arrays (grpc, service, otel, etc.) |
| Target files | In plan only, not per-feature in reqs | Per-feature `target_files` with exact paths |
| Estimated LOC | In plan only | Per-feature `estimated_loc` |

These improvements are **ephemeral** — they exist only in the JSON seed artifact of each run. When the next run starts, the pipeline re-derives everything from the source documents, potentially losing improvements or re-discovering them at cost. This violates the Kaizen principle: don't discard lessons across runs.

### The Feedback Loop Gap

```
Source Documents (plan.md + requirements.md)
    │
    ▼
Plan Ingestion Pipeline
  PARSE (LLM) ──► features = SOURCE OF TRUTH for tasks
    │             (_derive_tasks_from_features: title=feature.name,
    │              task_description=feature.description)
    ├─ ASSESS    (deterministic by default; telemetry-only composite)
    ├─ TRANSFORM (deterministic by default; YAML is NOT the task source)
    └─ REFINE → deterministic ENRICH → EMIT
    │   NOTE: seed tasks derive from PARSE features, not the TRANSFORM YAML.
    │   See docs/design/plan-ingestion/DETERMINISTIC_INGESTION_REQUIREMENTS.md (FR-1/FR-3).
    ▼
Enriched Seed (prime-context-seed-enriched.json)  ← improvements live here
    │
    ▼
Prime Contractor (code generation)
    │
    ▼
Kaizen Investigation (learnings captured in docs)
    │
    ✗ NO FEEDBACK to source documents
```

### Current State (2026-03-15)

The Prime Contractor now reliably processes all 17 tasks on every run — runs 041 through 050 produced 12 consecutive PASSes with 17/17 completion. The pipeline is **structurally stable**. However, comparative analysis of runs 049 and 050 (identical plan, identical requirements, same pipeline) revealed significant quality variance across runs:

- Run-049: 14/16 files byte-identical to reference implementation
- Run-050: 4 files with critical bugs (phantom imports, duplicate functions, missing return statements) despite 17/17 PASS scores

The root cause: validation gates check syntactic properties (AST validity, stub count, import presence) but not **semantic** correctness. LLM non-determinism means each run produces different code, and the pipeline cannot distinguish good output from bad. See [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](../kaizen/SEMANTIC_VALIDATION_GAP_ANALYSIS.md) for the full bug inventory.

This shifts the golden seed's purpose: rather than feeding improvements back into source documents for re-ingestion, the golden seed should be a **hand-designed, directly-consumed seed** that eliminates ingestion-phase variance entirely, allowing implementation quality to be tuned in isolation.

---

## 2. Goals

1. **Design the golden seed by hand** as the canonical, frozen representation of the online-boutique workload — incorporating the best enrichments discovered across 50 pipeline runs
2. **Bypass plan ingestion entirely** — the golden seed IS the seed; it does not need to be derived from source documents via PARSE → TRANSFORM → REFINE
3. **Eliminate ingestion-phase variance** — by removing the LLM-driven ingestion phases, the only remaining variable is implementation quality, which can be tuned independently
4. **Establish a stable baseline for semantic validation development** — with a consistent seed, improvements to the validator (import resolution, cross-scope duplicates, Dockerfile digest checks) can be measured against a fixed input
5. **Preserve provenance** — track which enrichments came from which run, enabling audit and rollback

### Non-Goals

- Automating golden seed generation from source documents (the seed IS the artifact)
- Modifying the plan ingestion pipeline code
- Making the golden seed consumable by plan ingestion — once finalized, the golden seed is **designed, not derived**, and may be intentionally inconsumable by the ingestion pipeline (it encodes knowledge that the LLM-driven pipeline cannot reliably reproduce)
- Generalizing beyond the online-boutique calibration workload (Phase 1)

---

## 3. Definitions

| Term | Definition |
|------|-----------|
| **Source documents** | The human-authored plan.md and requirements.md that served as original pipeline input |
| **Enriched seed** | The `prime-context-seed-enriched.json` output of plan ingestion — machine-generated, per-run, ephemeral |
| **Golden seed** | A hand-designed `prime-context-seed.json` that incorporates the best enrichments from multiple pipeline runs, authored directly as a JSON artifact. **Designed, not derived.** Once finalized, it is the canonical input to the Prime Contractor — plan ingestion is bypassed entirely. |
| **Designed seed** | Synonym for golden seed — emphasizes that the seed is authored intentionally, not generated by an LLM pipeline |
| **Calibration workload** | A stable plan+requirements pair used repeatedly to measure pipeline quality (e.g., online-boutique) |
| **Semantic validation** | Post-generation checks that verify import resolution, cross-scope correctness, and runtime viability — beyond AST/syntax validation |

---

## 4. Requirements

### REQ-GS-100: Golden Seed Content Requirements

The golden seed is a hand-authored `prime-context-seed.json` that must contain all enrichment categories discovered across pipeline runs. Each feature entry must include:

| ID | Field | Source | Required |
|----|-------|--------|----------|
| REQ-GS-101 | `task_id` | Canonical PI-xxx identifier | Yes |
| REQ-GS-102 | `title` | Human-readable feature name | Yes |
| REQ-GS-103 | `target_files` | Exact output file path(s) | Yes |
| REQ-GS-104 | `api_signatures` | Structured list of class/function signatures from reference implementation | Yes |
| REQ-GS-105 | `negative_scope` | Per-feature exclusion list (what NOT to generate) | Yes |
| REQ-GS-106 | `protocol` | `grpc`, `flask`, `library`, `locust`, or `none` | Yes |
| REQ-GS-107 | `labels` | Classification tags (service, otel, dependencies, etc.) | Yes |
| REQ-GS-108 | `depends_on` | Dependency ordering (acyclic DAG) | Yes |
| REQ-GS-109 | `estimated_loc` | Target line count from reference implementation | Yes |
| REQ-GS-110 | `design_doc_sections` | Key implementation constraints and design decisions | Yes |
| REQ-GS-111 | `runtime_dependencies` | Correct PyPI package names (NOT local module names) | Yes |
| REQ-GS-112 | `implementation_contract` | Verbatim code block showing expected file structure | Recommended |
| REQ-GS-113 | `environment_variables` | Per-feature env var table with defaults | Where applicable |
| REQ-GS-114 | `import_map` | Mapping of imports to their source (stdlib/pip/proto/local) | **New — enables L1 validation** |

### REQ-GS-200: Golden Seed Design Principles

**REQ-GS-201: Designed, Not Derived**
The golden seed is authored by hand (human + agent), not produced by the plan ingestion pipeline. It incorporates the best enrichments discovered across runs but is not constrained by what the LLM-driven pipeline can reproduce. It may encode knowledge (exact import paths, exact API signatures, cross-file consistency constraints) that the pipeline's PARSE → TRANSFORM phases cannot reliably derive.

**REQ-GS-202: Intentionally Inconsumable**
Once finalized, the golden seed is NOT a valid input to the plan ingestion pipeline. It bypasses ingestion entirely and is consumed directly by the Prime Contractor via `--seed` flag. The golden seed may use field names, structures, or enrichment levels that the ingestion pipeline would reject or mangle. This is by design — the seed is optimized for implementation quality, not for round-trip compatibility with ingestion.

**REQ-GS-203: Provenance Tracking**
The golden seed must include a `_provenance` section recording:
- Source enriched seed paths and run IDs that contributed enrichments
- Date of each curation session
- Rationale for non-obvious design decisions (e.g., why a specific API signature was chosen over alternatives seen across runs)

**REQ-GS-204: Frozen Input, Tunable Output**
The purpose of the golden seed is to **freeze the input** so that output quality can be measured and improved in isolation. Changes to improve code generation (prompt templates, repair steps, semantic validators) should be tested against the same golden seed. The seed itself changes only when the target workload's reference implementation changes.

**REQ-GS-205: Reference-Grounded**
Every field in the golden seed must be grounded in the reference implementation. API signatures must match the actual reference code. Import maps must reflect real module paths. Estimated LOC must match reference file lengths. The golden seed is a specification, not a wish list.

### REQ-GS-300: Online-Boutique Golden Seed (Phase 1 Deliverable)

The first golden seed targets the online-boutique calibration workload (17 features across 4 services).

**REQ-GS-301: Feature Decomposition**
The 17-feature structure established across 50 pipeline runs:

| Source Feature | Golden Seed Features |
|---------------|---------------------|
| F-001 | PI-001 (emailservice logger), PI-002 (recommendationservice logger — identical copy) |
| F-002 | PI-003 (gRPC server), PI-004 (test client), PI-005 (HTML template) |
| F-003 | PI-006 (gRPC server), PI-007 (test client) |
| F-004 | PI-008 (shopping assistant server) |
| F-005 | PI-009 (load generator) |
| F-006 | PI-010–PI-013 (per-service Dockerfiles) |
| F-007 | PI-014–PI-017 (per-service requirements.in) |

**REQ-GS-302: Import Maps (New — Enables L1 Semantic Validation)**
Each feature must include an `import_map` classifying every import in the target file:

```json
{
  "import_map": {
    "grpc": "pip:grpcio",
    "demo_pb2": "proto:demo.proto",
    "demo_pb2_grpc": "proto:demo.proto",
    "logger": "local:logger.py",
    "grpc_health.v1.health_pb2": "pip:grpcio-health-checking",
    "opentelemetry.trace": "pip:opentelemetry-api",
    "jinja2": "pip:jinja2",
    "os": "stdlib",
    "time": "stdlib"
  }
}
```

Classification values: `stdlib`, `pip:<package-name>`, `proto:<proto-file>`, `local:<filename>`, `copy:<source-task-id>`.

This enables the L1 import resolution validator to check generated code against the golden seed's import map, catching phantom imports, wrong module paths, and repair-mangled imports.

**REQ-GS-303: Negative Scope (Validated Across Runs)**
Per-feature negative scope curated from the best entries across runs 023–050:
- PI-001/PI-002: "Not shared as a package — intentionally duplicated per reference implementation", "No file handler — stdout only", "Not used by shoppingassistantservice or loadgenerator"
- PI-003: "Google Cloud Mail API `send_email` is a no-op stub (body is `pass`)", "Cloud Profiler import is commented out — not functional (TODO #3196)", "`HealthCheck` does NOT inherit from `health_pb2_grpc.HealthServicer` — standalone class"
- PI-004: "Does NOT import from `emailservice.email_server` — imports from `demo_pb2_grpc`", "`__main__` block does not make actual RPC call — test harness only"
- PI-006: "`RecommendationService` inherits from `RecommendationServiceServicer` ONLY — NOT from `HealthServicer`", "`ListRecommendations` has NO try/except around `ListProducts` call"
- PI-007: "Imports from `demo_pb2`/`demo_pb2_grpc` — NOT from `recommendationservice.*`"
- PI-008: "Uses `langchain_google_alloydb_pg` and `langchain_google_genai` — NOT `langchain.vectorstores` or `langchain.chains`", "`create_app()` must return the Flask app", "Embedding model is `models/embedding-001` (NOT `embedding-0o01`)"

**REQ-GS-304: Runtime Dependencies (Correct PyPI Names)**
Per-feature dependency lists with validated PyPI package names. Example for PI-003:
```
grpcio
grpcio-health-checking
jinja2
google-api-core
opentelemetry-api
opentelemetry-sdk
opentelemetry-instrumentation-grpc
opentelemetry-exporter-otlp-proto-grpc
```

**REQ-GS-305: Environment Variable Tables**
Per-feature environment variable tables with defaults:

```
| Variable | Purpose | Default |
|----------|---------|---------|
| PORT | gRPC server port | 8080 |
| ENABLE_TRACING | Enable OTLP tracing | unset (disabled) |
| DISABLE_PROFILER | Skip Cloud Profiler init | unset (profiler attempted) |
| COLLECTOR_SERVICE_ADDR | OTLP collector endpoint | localhost:4317 |
```

**REQ-GS-306: Implementation Contracts (Reference-Grounded)**
Each feature's `implementation_contract` must be derived from the actual reference implementation, not from LLM-generated approximations. The contract is the authoritative specification for code generation.

---

## 5. Success Criteria

| Criterion | Metric | Target |
|-----------|--------|--------|
| Completion rate | Features passing Prime Contractor postmortem | 17/17 (already achieved — runs 041–050) |
| Reference fidelity | Files byte-identical to reference implementation | >= 14/16 (run-049 baseline) |
| Semantic validation pass rate | Files passing L1 import resolution + L2 duplicate detection | 17/17 |
| No phantom imports | Generated imports that resolve to non-existent modules | 0 |
| No phantom dependencies | `requirements.in` entries that aren't real PyPI packages | 0 |
| Cost stability | Prime Contractor generation cost | < $0.60 per run |
| Cross-run consistency | Files identical between consecutive golden-seed runs | >= 14/16 |

---

## 6. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Over-specification — golden seed so detailed that the LLM copies it verbatim without adaptation | Medium | Low | Design contracts at the structural level (signatures, imports), not the implementation level |
| Seed drift — reference implementation evolves but golden seed is not updated | Medium | High | Tie golden seed updates to reference implementation commits; version the seed |
| LLM ignores negative scope — negative scope fields are present but generators don't consume them | High | Medium | Validate prompt templates thread negative scope into spec/draft prompts; add Kaizen correlation for negative_scope_word_count |
| Import map becomes maintenance burden | Medium | Low | Auto-generate import map from reference implementation AST; only hand-curate exceptions |
| Golden seed locks in suboptimal decomposition | Low | Medium | The 17-feature decomposition has been stable across 50 runs — it's the natural structure |

---

## 7. Implementation Plan

### Phase 1: Golden Seed Design (Current — Ready to Start)

**Prerequisites achieved:**
- Prime Contractor reliably processes all 17 tasks (12 consecutive 17/17 PASSes)
- Semantic validation gap analysis complete ([SEMANTIC_VALIDATION_GAP_ANALYSIS.md](../kaizen/SEMANTIC_VALIDATION_GAP_ANALYSIS.md))
- 50 pipeline runs providing enrichment data to curate from

**Steps:**
1. Start from run-049's enriched seed (highest reference fidelity: 14/16 files byte-identical)
2. Hand-curate each feature entry against the reference implementation:
   - Verify `api_signatures` match actual reference code
   - Add `import_map` for every import in each target file (REQ-GS-302)
   - Add reference-grounded `negative_scope` from cross-run analysis (REQ-GS-303)
   - Validate `runtime_dependencies` are correct PyPI names, not local modules (REQ-GS-304)
   - Add `implementation_contract` with verbatim code structure from reference (REQ-GS-306)
3. Add `_provenance` section documenting source runs and curation decisions (REQ-GS-203)
4. Run Prime Contractor with `--seed golden-seed.json` (bypassing plan ingestion)
5. Validate against success criteria (Section 5)
6. Iterate: compare output against reference, tighten negative scope and contracts for failing features

### Phase 2: Semantic Validation Development (Parallel)

Implement the validation layers identified in the gap analysis, tested against the golden seed's consistent output:

| Layer | Validator | Implementation Target |
|-------|-----------|----------------------|
| L1 | Import resolution | `forward_manifest_validator.py` → `_validate_import_resolution()` |
| L2 | Cross-scope duplicate detection | `forward_manifest_validator.py` → extend `_count_duplicate_definitions()` |
| L3 | Dockerfile digest validation | `forward_manifest_validator.py` → extend `_validate_dockerfile()` |
| L4 | Factory return value check | `forward_manifest_validator.py` → `_validate_factory_returns()` |
| L5 | Requirements-to-import cross-check | `forward_manifest_validator.py` → `_validate_requirements_coverage()` |

### Phase 3: Cross-Workload Golden Seeds (Future)
- Apply the golden seed methodology to other calibration workloads
- Build tooling to auto-generate import maps from reference implementation AST
- Establish a golden seed registry with versioning

---

## 8. Architectural Insight: Why Designed > Derived

The key insight from 50 runs is that **LLM-driven plan ingestion is inherently non-deterministic**. The same source documents produce different enriched seeds on every run (different seed checksums, different transform-phase outputs, different enrichment quality). This non-determinism cascades into implementation quality — run-049 produced near-perfect code while run-050 produced files with critical bugs, from the same source documents.

The golden seed eliminates this variance by replacing the stochastic ingestion pipeline with a deterministic, hand-designed artifact. This is not a failure of the ingestion pipeline — it successfully discovered the 17-feature decomposition, the enrichment categories, and the structural patterns. But once those discoveries are made, they should be **frozen** into a designed artifact rather than re-derived on every run.

```
OLD: Source Documents → [LLM Ingestion] → Ephemeral Seed → [Generation] → Code
                              ↑ non-deterministic

NEW: Golden Seed (designed) ──────────────→ [Generation] → Code
          ↑ frozen                              ↑ only remaining variable
```

This separation of concerns enables independent tuning:
- **Seed quality**: Improved by hand-curation against reference implementation
- **Generation quality**: Improved by prompt templates, repair steps, semantic validation
- **Validation quality**: Improved by L1–L5 semantic validators tested against consistent input

---

## 9. Cross-References

| Document | Relationship |
|----------|-------------|
| [SEMANTIC_VALIDATION_GAP_ANALYSIS.md](../kaizen/SEMANTIC_VALIDATION_GAP_ANALYSIS.md) | Validation gap analysis from run-049 vs run-050 comparison — defines L1–L7 validators |
| [KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md](../kaizen/KAIZEN_QUALITY_PHASE_REQUIREMENTS_VALIDATION.md) | Quality phase requirements that motivated this analysis |
| [KAIZEN_INVESTIGATION_RUN023_ONLINE_BOUTIQUE.md](../kaizen/KAIZEN_INVESTIGATION_RUN023_ONLINE_BOUTIQUE.md) | Run-023 analysis revealing enrichment gaps |
| [KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md](../kaizen/KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) | Seed utilization requirements (downstream consumption) |
| [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md) | Deterministic enrichment (Option A) — pipeline-side complement |
| `run-049` | Highest reference fidelity run (14/16 byte-identical) — golden seed starting point |
| `run-050` | Degraded run despite same pipeline — evidence for designed-over-derived approach |
| [SEED_UNIFICATION_REQUIREMENTS.md](../../SEED_UNIFICATION_REQUIREMENTS.md) | Architectural anchor: REQ-SU-300 refactors the "designed, not derived" concept (REQ-GS-201/202) into an authoring mode classification that separates how seeds are created from how they are consumed |
