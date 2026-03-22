# Seed Unification — Requirements

**Version:** 1.0.0
**Created:** 2026-03-22
**Status:** Active — Architectural Direction
**Author:** Human + Agent collaboration
**Pattern:** Kaizen (cross-run signal propagation), Mottainai (don't discard capabilities), Warm Up (don't discard context across toolchain transitions)
**Domain:** Plan Ingestion → Seed → Prime Contractor (+ Artisan capability preservation)

---

## 1. Problem Statement

The StartD8 SDK maintains two conceptual seed types distinguished by a `route` field on a unified `ContextSeed` model: `"prime"` and `"artisan"`. While the data model is already unified, the **enrichment path**, **validation logic**, **quality metadata**, and **transform format** diverge by route. This creates:

1. **Artificial capability gaps** — Prime seeds omit quality metadata (`_ingestion_quality`) that is universally valuable
2. **Divergent validation** — `validate_for_route()` checks different fields per route
3. **Vestigial routing logic** — `ContractorRoute` enum and complexity threshold exist but `force_route="prime"` is the default; the routing decision never fires in production
4. **Scattered convergence requirements** — REQ-PI-003/004 (route parity), REQ-PC-009 (artisan validators in Prime), REQ-RFL-120 (artisan ReviewPhaseHandler in Prime), and REQ-RFL-340 (shared review fields) all describe convergence but no single document owns the trajectory

### Architectural Trajectory

The planning exercise revealed that **Prime is systematically absorbing Artisan's capabilities**:

| Capability | Artisan Source | Prime Absorption | Status |
|-----------|---------------|-----------------|--------|
| Domain validation (AR-143–149) | `artisan_phases/domain_checklist.py` | `prime_contractor.py` imports `validate_generated_code` | **Done** |
| Integration engine | `integration_engine.py` | Same class, shared | **Done** |
| Disk quality scoring | `prime_postmortem.py` | Same function, shared | **Done** |
| Review phase | `context_seed/core.py` ReviewPhaseHandler | `PrimeReviewAdapter` (REQ-RFL-120) | **Planned** |
| Quality hints in seed | — | `SeedTask.quality_hints` (REQ-RFL-300) | **Implemented** |
| Arch context + design calibration | Artisan-only enrichment | REQ-PI-003/004 require parity | **Planned** |
| Ingestion quality metadata | Artisan-only guard | Guard removed (this doc) | **Done** |
| Unified validation | Route-specific branches | Branches merged (this doc) | **Done** |

This document owns the convergence trajectory and serves as the traceability anchor.

---

## 2. Goals

1. **Eliminate route-conditional logic** in seed enrichment, validation, and quality metadata
2. **Preserve all Artisan capabilities** as reusable infrastructure (not deleted, not gated behind route checks)
3. **Establish the seed as a route-agnostic contract** — consumption differs by pipeline, but the seed itself is universal
4. **Separate seed authoring from seed consumption** — how a seed is created (pipeline-derived, hand-designed, hybrid) is orthogonal to how it's consumed

### Non-Goals

- Deleting Artisan code (it stays as preserved infrastructure)
- Implementing the full Artisan pipeline in Prime (Prime remains lean)
- Automating Artisan-to-Prime migration (capabilities are absorbed incrementally via requirements)

---

## 3. Definitions

| Term | Definition |
|------|-----------|
| **Route** | The `ContextSeed.route` field (`"prime"` or `"artisan"`). Being deprecated as a behavioral selector — retained only as a provenance label. |
| **Seed authoring** | How a seed is created: pipeline-derived (plan ingestion), hand-designed (golden seed), or hybrid (pipeline + post-ingestion enrichment). |
| **Seed consumption** | How a pipeline reads and uses seed fields. Prime uses FeatureQueue; Artisan uses phase handlers. Both should read the same fields. |
| **Capability preservation** | Artisan capabilities that are not actively used but must survive for future reactivation. Each has a canonical source, reactivation condition, and compilation test. |

---

## 4. Requirements

### Layer 1: Route Elimination (REQ-SU-1xx)

#### REQ-SU-100: Universal Ingestion Quality Metadata
**Status:** ✅ Implemented (2026-03-22)
**File:** `plan_ingestion_emitter.py`

The `_ingestion_quality` metadata block MUST be computed for ALL seeds regardless of route. This enables KSU-1xx seed fitness scoring for Prime runs.

**Change:** Removed `if route == ContractorRoute.ARTISAN:` guard.

---

#### REQ-SU-101: Unified Seed Validation
**Status:** ✅ Implemented (2026-03-22)
**File:** `seeds/validation.py`

`validate_for_route()` MUST validate ALL context fields (design_calibration, architectural_context, onboarding) for ALL seeds. Route-specific warning prefixes removed.

**Change:** Merged artisan and prime validation branches into a single path.

---

#### REQ-SU-102: Deprecate Routing Threshold
**Status:** Planned
**Files:** `plan_ingestion_models.py`, `plan_ingestion_workflow.py`

The `complexity_threshold` field and the composite-score-based routing decision MUST be deprecated. The composite score is retained for seed quality analysis but no longer determines route.

**Acceptance criteria:**
- `ContractorRoute` enum retained for backward compatibility (existing seeds on disk reference it)
- `force_route` config field retained but defaults to `"prime"` and documented as deprecated
- Route margin telemetry (`_assess_q["route_margin"]`) reframed as "quality classification score" in log messages and `_ingestion_quality` metadata
- Heuristic fallback override (line 4137) removed — no automatic routing to artisan
- No behavioral change for existing production flows (already forced to prime)

---

#### REQ-SU-103: Universal Enrichment Path
**Status:** Planned
**Files:** `plan_ingestion_workflow.py`, `seeds/builder.py`

Both `derive_architectural_context()` and `derive_design_calibration()` MUST be called for ALL seeds, not just artisan route seeds. This implements REQ-PI-003/004.

**Acceptance criteria:**
- The prime transform path in `_phase_emit` calls `builder.derive_architectural_context()` and `builder.derive_design_calibration()` (currently only artisan path calls these)
- No new code needed — the functions exist; they just need to be called

---

### Layer 2: Cross-Requirement Consolidation (REQ-SU-2xx)

#### REQ-SU-200: Post-Generation Validation Consolidation
**Status:** Planned
**Cross-references:** REQ-PC-009, REQ-RFL-100, REQ-RFL-105, REQ-RFL-115

These four requirements describe the same implementation work from different angles:
- REQ-PC-009: "Run artisan validators AR-143–AR-149 after code generation"
- REQ-RFL-100: "Persist DiskComplianceResult in integration metadata"
- REQ-RFL-105: "Persist RepairOutcome summary in integration metadata"
- REQ-RFL-115: "Compute disk quality score at integration time"

**Consolidation:** Implementing RFL I1 (Plumbing + Review) delivers all four requirements. The implementation vehicle is the Review Feedback Loop Iteration 1.

---

#### REQ-SU-201: Static Seed Consumption Map
**Status:** Planned
**Simplifies:** REQ-KSU-100 (dynamic field access logging)

The consumption map in KAIZEN_SEED_UTILIZATION_REQUIREMENTS Section 1.3 is empirically complete and static — it doesn't change per run. Instead of building dynamic field-access tracing:

1. Emit the static consumption map as a constant in `implementation_engine/spec_builder.py`
2. Compute "unused" and "missing" fields by diff against the seed's actual fields at load time
3. Zero runtime overhead, zero new LLM calls

**Acceptance criteria:**
- `SEED_FIELD_CONSUMPTION_MAP: dict[str, dict]` constant with field name → consumer, impact, notes
- At seed load time, compute diff and log "unused fields: [...]" and "missing high-impact fields: [...]"
- Per-run report artifact: `seed-consumption-report.json`

---

### Layer 3: Seed Authoring vs Consumption Separation (REQ-SU-3xx)

#### REQ-SU-300: Authoring Mode Classification
**Status:** Planned
**Refactors:** REQ-GS-201/202

Seeds MUST carry an `authoring_mode` field indicating how they were created:
- `"pipeline"` — derived by plan ingestion (PARSE → TRANSFORM → REFINE → EMIT)
- `"designed"` — hand-authored (golden seed)
- `"hybrid"` — pipeline-derived then enriched with post-ingestion quality hints

**Acceptance criteria:**
- `ContextSeed.authoring_mode: Optional[str]` field added (default: `None` = legacy/unknown)
- Plan ingestion sets `authoring_mode="pipeline"` on emit
- Golden seed sets `authoring_mode="designed"` in JSON
- Post-ingestion enrichment script sets `authoring_mode="hybrid"`
- The `authoring_mode` is provenance metadata only — it MUST NOT affect consumption behavior

---

#### REQ-SU-301: Consumption Contract (Route-Agnostic)
**Status:** Planned

The seed consumption contract defines what fields a consumer MAY expect, regardless of authoring mode or legacy route:

| Field | Impact | Required | Consumer |
|-------|--------|----------|----------|
| `tasks` | Critical | Yes | FeatureQueue, phase handlers |
| `tasks[].config.task_description` | Critical | Yes | spec_builder (primary LLM instruction) |
| `tasks[].config.context.target_files` | Critical | Yes | spec_builder, drafter, output routing |
| `tasks[].depends_on` | Critical | Yes | queue ordering (deadlock prevention) |
| `architectural_context` | High | Recommended | gen_context injection |
| `design_calibration` | High | Recommended | token budget calibration |
| `onboarding` | High | Recommended | mode detection, semantic conventions |
| `service_metadata` | Medium | Recommended | protocol-aware generation |
| `tasks[].quality_hints` | Medium | Optional | spec_builder quality guidance |
| `_ingestion_quality` | Low | Optional | Kaizen fitness scoring |

**Acceptance criteria:**
- This table is the canonical reference for seed consumers
- Consumers MUST use `.get()` with defaults for all optional fields (graceful degradation)
- No consumer MAY branch on `route` to decide which fields to read

---

### Layer 4: Capability Preservation (REQ-SU-4xx)

Artisan capabilities that are not actively consumed by Prime but MUST be preserved for future reactivation.

#### REQ-SU-400: Preserved Capability Registry

Each preserved capability MUST have:
1. **Canonical source location** — the authoritative implementation file(s)
2. **Reactivation condition** — when this capability becomes active again
3. **Compilation test** — a test that verifies the code still compiles and passes (prevents drift)

| ID | Capability | Canonical Source | Reactivation Condition | Test |
|----|-----------|-----------------|----------------------|------|
| PC-1 | Design phase dual-review orchestration | `context_seed/phases/design.py` | Prime adds LLM design pre-pass | Existing unit tests in `tests/unit/contractors/` |
| PC-2 | 8-phase checkpoint/resume | `checkpoint.py`, `artisan_contractor.py` | Prime adds multi-phase checkpointing | Existing checkpoint tests |
| PC-3 | Self-consistency validators (AR-143–149) | `artisan_phases/self_consistency.py` | REQ-PC-009 implementation (already consuming `domain_checklist.py`) | Existing self-consistency tests |
| PC-4 | Test generation (LLMTestGenerator) | `artisan_phases/test_construction.py` | Prime adds post-generation test creation | Existing test construction tests |
| PC-5 | LLM code review (ReviewPhaseHandler) | `context_seed/core.py` ReviewPhaseHandler | REQ-RFL-120 PrimeReviewAdapter (planned) | Existing review handler tests |
| PC-6 | Design-implementation handoff | `handoff.py` (680 lines) | Prime adds design pre-pass | Existing handoff tests |
| PC-7 | Lessons extraction (retrospective) | `artisan_phases/retrospective.py` | Prime adds post-run learning capture | Existing retrospective tests |
| PC-8 | Lane collision detection (CCD-301) | `context_seed/design_support.py` | Prime adds parallel task scheduling | Existing design support tests |

**Acceptance criteria:**
- No capability in the registry MAY be deleted without updating this table
- CI MUST continue to run existing tests for preserved capabilities
- When a capability is reactivated (absorbed into Prime), its row moves from this table to the "Absorbed" section above

---

### Layer 5: Transform Format Convergence (REQ-SU-5xx)

#### REQ-SU-500: Architecture/Risk/Verification Context Extraction
**Status:** Planned

The Artisan transform produces 7-section markdown (Overview, Data Models, Architecture, Phase Breakdown, Cost Model, Risk Register, Verification). Prime's YAML transform omits this context. The Architecture, Risk Register, and Verification sections contain high-value context for code generation.

**Requirements:**
1. After Prime's YAML transform, extract architecture/risk/verification context from the source plan document
2. Store as structured fields in the seed: `plan_architecture_context`, `plan_risk_register`, `plan_verification_criteria`
3. These fields are consumed by the spec builder as P3 context (same priority as existing `architectural_context`)
4. Extraction can be deterministic (regex/heuristic) for plans with standard section headers, or LLM-assisted for unstructured plans

**Acceptance criteria:**
- A Prime seed produced from a plan with Architecture/Risk/Verification sections contains these as structured fields
- The spec builder renders them when present (`.get()` with None default)
- No change to the YAML transform format itself — this is an enrichment step, not a format change

---

## 5. Implementation Phases

| Phase | Requirements | Effort | Dependencies |
|-------|-------------|--------|-------------|
| **Done** | REQ-SU-100, REQ-SU-101 | ~15 LOC | None |
| **Phase 1: Enrichment parity** | REQ-SU-103 | ~20 LOC | None |
| **Phase 2: Consumption map** | REQ-SU-201 | ~50 LOC | None |
| **Phase 3: Deprecate routing** | REQ-SU-102 | ~30 LOC | Phase 1 |
| **Phase 4: Authoring classification** | REQ-SU-300, REQ-SU-301 | ~30 LOC | Phase 3 |
| **Phase 5: Transform enrichment** | REQ-SU-500 | ~100 LOC | Phase 1 |
| **Phase 6: Cross-req consolidation** | REQ-SU-200 | 0 LOC (doc only) | RFL I1 |

---

## 6. Success Criteria

| Criterion | Metric | Target |
|-----------|--------|--------|
| No route-conditional enrichment | `grep -rn 'ContractorRoute.ARTISAN' src/` matches | 0 in enrichment/validation paths |
| All seeds have quality metadata | `_ingestion_quality` present in prime seeds | 100% of pipeline runs |
| Preserved capabilities compile | CI test pass rate for PC-1 through PC-8 | 100% |
| Consumption contract documented | Static map emitted per run | Present in every seed-consumption-report.json |

---

## 7. Cross-References

| Document | Relationship |
|----------|-------------|
| [PRIME_CONTRACTOR_REQUIREMENTS.md](prime/PRIME_CONTRACTOR_REQUIREMENTS.md) | REQ-PC-009 (post-gen validation) → consolidated by REQ-SU-200 |
| [REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md](prime/REVIEW_FEEDBACK_LOOP_REQUIREMENTS.md) | REQ-RFL-120 (review adapter), REQ-RFL-340 (shared fields) → aligned with REQ-SU-301 |
| [KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md](kaizen/KAIZEN_SEED_UTILIZATION_REQUIREMENTS.md) | REQ-KSU-100 (consumption observability) → simplified by REQ-SU-201 |
| [GOLDEN_SEED_REQUIREMENTS.md](plan-ingestion/GOLDEN_SEED_REQUIREMENTS.md) | REQ-GS-201/202 (designed not derived) → refactored by REQ-SU-300 |
| [PLAN_INGESTION_REQUIREMENTS.md](../../PLAN_INGESTION_REQUIREMENTS.md) | REQ-PI-003/004 (route parity) → implemented by REQ-SU-103 |
| [ARTISAN_REQUIREMENTS.md](artisan/ARTISAN_REQUIREMENTS.md) | AR-143–149, AR-120, AR-5xx → preserved by REQ-SU-400 |

---

## 8. Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0.0 | 2026-03-22 | human:neil + agent:claude-code | Initial requirements from seed unification planning exercise |
