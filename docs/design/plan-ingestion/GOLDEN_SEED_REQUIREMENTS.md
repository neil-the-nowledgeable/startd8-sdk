# Golden Seed Requirements

**Date:** 2026-03-10
**Status:** Draft
**Author:** Human + Agent collaboration
**Domain:** Plan Ingestion → Source Document Feedback Loop

---

## 1. Problem Statement

The plan ingestion pipeline (PARSE → ASSESS → TRANSFORM → REFINE → EMIT) produces an enriched seed (`prime-context-seed-enriched.json`) that is significantly richer than the source plan and requirements documents it was derived from. Across 26 runs of the online-boutique calibration workload, the pipeline has iteratively discovered and encoded improvements that do not exist in the source documents:

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
Plan Ingestion Pipeline (PARSE → TRANSFORM → REFINE)
    │
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

---

## 2. Goals

1. **Define "golden seed"** as the canonical representation of a plan+requirements pair that incorporates validated improvements from pipeline runs
2. **Establish a merge-back workflow** for applying enriched seed improvements to source plan and requirements documents
3. **Ensure idempotency** — re-running plan ingestion against golden-seed-improved source documents should produce equivalent or better enriched seeds, not regressions
4. **Preserve provenance** — track which improvements came from which run, enabling audit and rollback

### Non-Goals

- Automating the merge-back (Phase 1 is manual/agent-assisted)
- Modifying the plan ingestion pipeline code
- Creating a new file format — golden seed improvements are applied directly to existing plan.md and requirements.md
- Golden seed as a runtime artifact — it is a process for improving source documents, not a new artifact type

---

## 3. Definitions

| Term | Definition |
|------|-----------|
| **Source documents** | The human-authored plan.md and requirements.md that serve as pipeline input |
| **Enriched seed** | The `prime-context-seed-enriched.json` output of plan ingestion — machine-generated, per-run |
| **Golden seed** | The state of source documents after validated enrichments have been merged back from one or more enriched seeds |
| **Merge-back** | The process of applying enriched seed improvements to source documents |
| **Calibration workload** | A stable plan+requirements pair used repeatedly to measure pipeline quality (e.g., online-boutique) |

---

## 4. Requirements

### REQ-GS-100: Source Document Enrichment Categories

The following categories of enrichment from the enriched seed are eligible for merge-back into source documents:

| ID | Category | Target Document | Merge Strategy |
|----|----------|----------------|---------------|
| REQ-GS-101 | Feature decomposition | plan.md | Split coarse features into fine-grained sub-features matching enriched seed structure |
| REQ-GS-102 | API signatures | requirements.md | Add structured `api_signatures` to each requirement's acceptance criteria |
| REQ-GS-103 | Runtime dependencies | requirements.md | Add per-feature pinned dependency lists to relevant requirements |
| REQ-GS-104 | Negative scope | plan.md | Add per-feature `**Negative scope:**` sections extracted from enriched seed |
| REQ-GS-105 | Protocol classification | plan.md | Add `**Protocol:**` field to each feature header |
| REQ-GS-106 | Design doc sections | plan.md | Add or refine `**Implementation contract:**` with design doc section summaries |
| REQ-GS-107 | Labels/tags | plan.md | Add `**Labels:**` field to each feature for classification |
| REQ-GS-108 | Target file refinement | plan.md | Ensure `**Output files:**` matches enriched seed `target_files` exactly |
| REQ-GS-109 | Estimated LOC refinement | plan.md | Update `**Estimated LOC:**` to match enriched seed values |
| REQ-GS-110 | Environment variables | requirements.md | Add structured env var tables to cross-cutting requirements |

### REQ-GS-200: Merge-Back Workflow

**REQ-GS-201: Diff Generation**
Before modifying source documents, produce a human-readable diff showing:
- Which enrichments will be applied
- Which source document sections will be modified
- Any conflicts between source content and enriched content (e.g., different LOC estimates)

**REQ-GS-202: Provenance Tracking**
Each merge-back session must record:
- Source enriched seed path and `generated_at` timestamp
- Run ID (e.g., `run-024-20260310T0939`)
- Categories applied (REQ-GS-101 through REQ-GS-110)
- Date of merge-back

Format: Add a `## Golden Seed Provenance` section to the bottom of each modified source document.

**REQ-GS-203: Idempotency Validation**
After merge-back, re-running plan ingestion against the updated source documents must:
- Produce a seed quality score >= the pre-merge score (no regression)
- Preserve all merged-back enrichments (they should pass through PARSE → TRANSFORM without loss)
- Not introduce new quality warnings that weren't present before

**REQ-GS-204: Incremental Application**
Merge-back may be applied incrementally — not all categories need to be applied at once. The workflow supports:
- Applying a single category (e.g., only REQ-GS-104 negative scope)
- Applying a subset of features (e.g., only F-002a through F-002c)
- Multiple merge-back sessions from different runs

### REQ-GS-300: Online-Boutique Golden Seed (Phase 1 Deliverable)

The first golden seed application targets the online-boutique calibration workload:

**REQ-GS-301: Feature Decomposition**
Split the 7 source features into the 17-feature structure established by the enriched seed:

| Source Feature | Golden Seed Features |
|---------------|---------------------|
| F-001 | F-001a (emailservice logger), F-001b (recommendationservice logger) |
| F-002 | F-002a (gRPC server), F-002b (test client), F-002c (HTML template) |
| F-003 | F-003a (gRPC server), F-003b (test client) |
| F-004 | F-004a (shopping assistant server) |
| F-005 | F-005a (load generator) |
| F-006 | F-006a–d (per-service Dockerfiles) |
| F-007 | F-007a–d (per-service requirements.in) |

**REQ-GS-302: Negative Scope Addition**
Add per-feature negative scope to plan.md for all 17 features. Examples from the enriched seed:
- F-001a: "Not shared as a package — intentionally duplicated per reference implementation", "No file handler — stdout only", "Not used by shoppingassistantservice or loadgenerator"
- F-002a: "Google Cloud Mail API is not functionally implemented", "Cloud Profiler is commented out — not functional"
- F-002b: "__main__ block does not make actual RPC call — test harness only"

**REQ-GS-303: API Signatures**
Add structured API signature lists to requirements.md acceptance criteria. Example for REQ-PMS-001:
```
**API signatures:**
- `class BaseEmailService(demo_pb2_grpc.EmailServiceServicer)`
- `def BaseEmailService.__init__(self) -> None`
- `class EmailService(BaseEmailService)`
- `def DummyEmailService.SendOrderConfirmation(self, request, context)`
- `class HealthCheck()`
- `def start(dummy_mode: bool) -> None`
- `def initStackdriverProfiling() -> None`
```

**REQ-GS-304: Runtime Dependencies**
Add per-feature runtime dependency sections to plan.md with pinned versions matching the enriched seed. Example for F-002a:
```
**Runtime dependencies:**
- grpcio==1.76.0
- grpcio-health-checking==1.76.0
- jinja2==3.1.6
- python-json-logger==4.0.0
- google-api-core==2.28.1
- opentelemetry-distro==0.60b1
- opentelemetry-instrumentation-grpc==0.60b1
- opentelemetry-exporter-otlp-proto-grpc==1.39.1
```

**REQ-GS-305: Environment Variable Tables**
Add structured environment variable tables to requirements.md cross-cutting requirements (REQ-PMS-006, REQ-PMS-007) and to plan.md per-feature sections. Format:

```
| Variable | Purpose | Default |
|----------|---------|---------|
| PORT | gRPC server port | 8080 |
| ENABLE_TRACING | Enable OTLP tracing | unset (disabled) |
```

**REQ-GS-306: Protocol and Labels**
Add `**Protocol:**` and `**Labels:**` fields to each plan.md feature header.

---

## 5. Success Criteria

| Criterion | Metric | Target |
|-----------|--------|--------|
| Seed quality preservation | Post-merge seed quality score | >= 0.9485 (run-023 baseline) |
| Feature count stability | Features extracted by PARSE | 17 (matching enriched seed) |
| Enrichment retention | Fields surviving PARSE round-trip | 100% of merged-back fields preserved |
| No new warnings | Quality warnings delta | 0 new warnings |
| Cost stability | Plan ingestion cost delta | < 10% increase |

---

## 6. Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Over-specification — source docs become so detailed that PARSE extracts redundant features | Medium | Medium | Validate with idempotency check (REQ-GS-203) |
| Feature ID drift — enriched seed uses F-001a but plan uses F-001; PARSE may renumber | Medium | High | Establish canonical feature IDs in golden seed and verify PARSE preserves them |
| Implementation contract duplication — enriched seed duplicates F-002a's contract into F-002b and F-002c | High | Low | Clean up during merge-back; each sub-feature should contain only its own contract |
| LLM sensitivity to document length — longer source docs may hit context limits | Low | Medium | Monitor PARSE/TRANSFORM token counts post-merge |

---

## 7. Implementation Plan

### Phase 1: Manual Merge-Back (Current)
1. Read enriched seed from most recent high-quality run (run-024)
2. Apply REQ-GS-301 through REQ-GS-306 to python-plan.md and python-requirements.md
3. Add provenance section (REQ-GS-202)
4. Run plan ingestion against updated documents
5. Validate success criteria (Section 5)

### Phase 2: Agent-Assisted Merge-Back (Future)
- Build a diff tool that compares enriched seed to source documents
- Generate merge-back patches for human review
- Integrate with kaizen investigation workflow

### Phase 3: Automated Feedback Loop (Future)
- Post-run hook that proposes merge-back when seed quality improves
- CI gate that validates golden seed idempotency
- Cross-workload golden seed library

---

## 8. Cross-References

| Document | Relationship |
|----------|-------------|
| [KAIZEN_INVESTIGATION_RUN023_ONLINE_BOUTIQUE.md](../kaizen/KAIZEN_INVESTIGATION_RUN023_ONLINE_BOUTIQUE.md) | Run-023 analysis revealing enrichment gaps |
| [KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md](../kaizen/KAIZEN_INVESTIGATION_RUN019_ONLINE_BOUTIQUE.md) | Run-019 analysis with seed quality and assembly findings |
| [KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md](../kaizen/KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) | Seed utilization requirements (downstream consumption) |
| [TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md](TASK_DENSITY_ENRICHMENT_REQUIREMENTS.md) | Deterministic enrichment (Option A) — the pipeline-side complement |
| `python-plan.md` | Source plan document (online-boutique calibration workload) |
| `python-requirements.md` | Source requirements document (online-boutique calibration workload) |
| `run-024-20260310T0939/plan-ingestion/prime-context-seed-enriched.json` | Most recent enriched seed |
