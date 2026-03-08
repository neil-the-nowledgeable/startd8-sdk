# Element Registry — Design Documents

Persistent, indexed element store for the capability delivery pipeline. Tracks element identity, state, quality, and lineage across all phases, tasks, and runs.

## Documents

| Document | Scope | Status |
|----------|-------|--------|
| [ELEMENT_REGISTRY_REQUIREMENTS.md](./ELEMENT_REGISTRY_REQUIREMENTS.md) | Pipeline-wide requirements (ER-001 through ER-018) | DRAFT |
| [REQ-MP-11xx (Micro-Prime)](../micro-prime/REQ-MP-11xx_ELEMENT_REGISTRY.md) | Core data model, engine integration, CLI (REQ-MP-1100 through REQ-MP-1109) | DRAFT |
| [Forward Manifest Element Registry Gap Review](../../reviews/forward-manifest-element-registry-gap-2026-03-07.md) | Investigation that motivated these requirements | Complete |
| [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) | Step-by-step implementation plan (3 phases, 22 steps) | DRAFT |

## Relationship Between Documents

```
ELEMENT_REGISTRY_REQUIREMENTS.md (this directory)
  │
  ├── Defines pipeline-wide scope: all 8 artisan phases,
  │   prime contractor, plan ingestion, Kaizen, Warm Up
  │
  ├── References REQ-MP-11xx for core data model
  │   (ElementEntry, ElementRegistry class, storage layout)
  │
  └── Extends REQ-MP-11xx with:
      ├── ER-001: Element identity standard (make_element_id)
      ├── ER-002: Registry as top-level pipeline service
      ├── ER-003..ER-011: Per-phase integration (8 phases)
      ├── ER-012: Prime contractor element loop
      ├── ER-013: Handoff element state
      ├── ER-014..ER-015: Kaizen + Warm Up integration
      ├── ER-016..ER-017: Quality gates + contract propagation
      └── ER-018: Element lineage and provenance

REQ-MP-11xx (micro-prime directory)
  │
  ├── Defines core implementation:
  │   REQ-MP-1100: ElementRegistry class + ElementEntry dataclass
  │   REQ-MP-1101: ForwardManifest element index (lazy O(1) lookup)
  │   REQ-MP-1102: MicroPrimeEngine registry integration
  │   REQ-MP-1103: MicroPrimeCodeGenerator (prime_adapter) integration
  │   REQ-MP-1104: Skeleton-derived element specs
  │   REQ-MP-1105: Cross-task element lookup
  │   REQ-MP-1106: DeterministicFileAssembler pre-fill
  │   REQ-MP-1107: Observability (OTel metrics)
  │   REQ-MP-1108: Staleness and invalidation
  │   REQ-MP-1109: CLI report
  │
  └── Parent: MICRO_PRIME_REQUIREMENTS.md (Layer 11)
```

## Design Principles Served

| Principle | Element Registry Role |
|-----------|----------------------|
| [Mottainai](../../design-princples/MOTTAINAI_DESIGN_PRINCIPLE.md) | Rules 1, 2, 4, 5 — inventory, forward, register, deterministic-over-stochastic |
| [Kaizen](../../design-princples/KAIZEN_DESIGN_PRINCIPLE.md) | Per-element metrics enable cross-run PDCA improvement |
| [Warm Up](../../design-princples/WARM_UP_DESIGN_PRINCIPLE.md) | Registry provides ground truth for toolchain transition reconciliation |

## Implementation Phases

| Phase | Focus | Requirements | Lines |
|-------|-------|-------------|-------|
| 1 | Foundation | ER-001, ER-002, ER-003, ER-007, ER-012 + REQ-MP-1100..1103 | ~710 + 390 |
| 2 | Pipeline Integration | ER-004..ER-006, ER-008..ER-009, ER-011, ER-013, ER-016..ER-017 | ~700 |
| 3 | Intelligence | ER-010, ER-014..ER-015, ER-018 + REQ-MP-1104..1109 | ~380 + 570 |
