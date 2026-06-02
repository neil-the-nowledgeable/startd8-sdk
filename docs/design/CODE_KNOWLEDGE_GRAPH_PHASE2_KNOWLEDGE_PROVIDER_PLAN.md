# CKG Phase 2 — Knowledge Provider: Implementation Plan

**Version:** 1.0 (post-planning, paired with requirements v0.2)
**Date:** 2026-06-01
**Requirements:** [CODE_KNOWLEDGE_GRAPH_PHASE2_KNOWLEDGE_PROVIDER_REQUIREMENTS.md](./CODE_KNOWLEDGE_GRAPH_PHASE2_KNOWLEDGE_PROVIDER_REQUIREMENTS.md) (v0.2)
**Worktree:** `code-knowledge-graph` (off main HEAD, Phase-1 landed)
**Status:** Plan — pre-CRP, pre-implementation

> Produced by the `/reflective-requirements` planning pass. Every requirement maps to concrete
> files/functions verified to exist in the Phase-1 tree; every discovery that changed a
> requirement is recorded in requirements §0.

---

## 0. Verified substrate (what Phase 1 already gives us)

The planning pass confirmed these surfaces exist and are reusable (file:line, real signatures):

| Surface | Signature | Provider role |
|---|---|---|
| `validators/cross_file_verifier.py:94` | `run_checks(sources: Dict[str,str], project_root: str, *, scip: Optional[ScipReader]=None) -> CrossFileResult` | **Convergence template** — provider mirrors this signature (the inverse: assert truth pre-gen) |
| `validators/cross_file_verifier.py:48` | `Finding(check_id, kind, source_file, locus, severity, scope, message, remediation)` — frozen | shared fact vocabulary; **no `availability_state`** (it's on `CrossFileResult.availability`) |
| `languages/prisma_parser.py:276` | `parse_prisma_schema(text: str) -> PrismaSchema{models: Dict[str,PrismaModel]}` | Prisma field-set authority; `PrismaField(name,type,is_optional,is_list,attributes)` |
| `validators/tsconfig_paths.py:88` | `scan(project_root, *, tsconfig_name) -> List[TsconfigAliasViolation]`; `_merged_compiler_options` follows `extends` | tsconfig `paths`/`baseUrl` alias source |
| `contractors/upstream_interface.py` | `build_upstream_interfaces(*, producer_files, project_root, import_specifiers=None, require_present=True, read_fn=None) -> List[UpstreamInterface]`; `render_upstream_interfaces`; `render_prisma_field_sets(prisma_text, entities=None) -> str`; `extract_ts_exports`; `extract_exports(source, path)`; `extract_import_specifiers(source) -> List[str]`; `resolve_specifier_to_paths(specifier, candidate_paths, *, alias_prefixes=None, importer_path="") -> List[str]` | **the renderer + resolver layer to wrap** — most rendering already exists |
| `validators/cross_file_imports.py:130` | `_package_name(specifier) -> str` (PRIVATE); `scan_unresolvable_imports`, `scan_missing_dependencies` | npm package-name mapping (promote `_package_name` or reuse scans) |
| `code_observability/scip_reader.py:92` | `ScipReader.from_path/from_bytes`; `.external_symbols_by_package()`, `.cross_file_edges()`, `.documents()` | authoritative tier when a SCIP index exists; gated by `[code-observability]` |
| `contractors/prime_contractor.py:4223` | `_collect_upstream_interfaces(self, feature) -> str` (Mode-A/B + Prisma branch) | **injection seam to refactor** |
| `contractors/prime_contractor.py:4320` | `_feature_mirrors_data_model(feature) -> bool` (gates ONLY the Prisma branch) | the keyword gate to **replace structurally** |

No `ProjectKnowledge`/`forward_project_knowledge` exists yet — the artifact + producer are greenfield, but built **entirely** over the surfaces above.

---

## 1. Module layout (new)

```
src/startd8/contractors/project_knowledge/
├── __init__.py            # public exports
├── models.py              # ProjectKnowledge, FieldSetAuthority, ModulePathAuthority,
│                          #   Negatives, Omissions  (the output model; carries `omissions`)
├── producer.py            # ProjectKnowledgeProducer protocol + DraftModeProducer
│                          #   build(sources, project_root, *, scip=None) -> ProjectKnowledge
├── scoping.py             # relevance scoping: import-graph closure + entity-reference resolution
├── negatives.py           # seeded negative list (REQ-522) + render
└── render.py              # ProjectKnowledge -> spec-context markdown (wraps upstream_interface renderers)

tests/unit/contractors/project_knowledge/
├── test_producer_injection.py     # REQ-520/521/522/523 (deterministic prompt content)
├── test_scoping.py                # REQ-524/527 (structural scope, no keyword gate)
├── test_negatives.py              # REQ-522 negatives rendered first-class
├── test_omissions.py              # REQ-523 omission, never "(none)"
└── test_collect_upstream_snapshot.py  # REQ-540 characterization parity
```

---

## 2. Requirement → implementation map

### REQ-CKG-520 — Producer protocol (convergence)
- **`producer.py`**: define `ProjectKnowledgeProducer` `Protocol` with
  `build(sources: Dict[str,str], project_root: str, *, scip: Optional[ScipReader]=None) -> ProjectKnowledge`
  — **mirrors `cross_file_verifier.run_checks`** signature (same `sources`/`project_root`/`scip`).
- `DraftModeProducer` is the v1 backend; a future `ScipProducer` drops in by consuming `scip`.
- **Acceptance test**: assert `DraftModeProducer().build(...)` calls `parse_prisma_schema` / `tsconfig_paths.scan` / `upstream_interface.*` — no new regex scanner (assert by patching those and checking they're hit).

### REQ-CKG-521 — Prisma field-set authority (Gap A)
- **`models.py`**: `FieldSetAuthority{entity, fields: List[FieldSpec(name,type,optional,is_list)], source_file}`.
- **`producer.py`**: for each scoped entity, `parse_prisma_schema(schema_text).models[entity]` → FieldSetAuthority.
- **`render.py`**: reuse/extend `render_prisma_field_sets(prisma_text, entities=...)`; append the "use only these; do not invent" P0 instruction.
- **Acceptance**: RUN-011 PI-001/004/007 repro → context lists the model's exact fields (incl. optional/list), no invented `aiRefId`/`label`/`title`.

### REQ-CKG-522 — Module-path authority + negatives (Gap B, D2)
- **Positive**: `upstream_interface.resolve_specifier_to_paths` + `tsconfig_paths` alias_prefixes → canonical path table.
- **Negatives**: **`negatives.py`** seeds the observed recurrences (`@/lib/prisma`→`@/lib/db`, `@/lib/db/<model>`, `@/lib/ai/client`→`@/lib/ai/service`) and renders them as a first-class section.
- npm mapping: promote `cross_file_imports._package_name` → public `package_name` (or import the scan helpers).
- **Acceptance**: PI-002/007 repro → `@/lib/prisma` invention absent; negatives section present.

### REQ-CKG-523 — Omissions (D3)
- **`models.py`**: `ProjectKnowledge.omissions: List[str]` (top-level, mirrors `CrossFileResult.availability` split).
- **`producer.py`**: missing `schema.prisma`/`tsconfig` → append an omission string, **set no authority**.
- **`render.py`**: render omissions as "X unavailable — do not assume …"; **never** emit "use only these fields: (none)".
- **Acceptance**: project without `schema.prisma` → omission statement, no empty field authority.

### REQ-CKG-524 + REQ-CKG-527 — Structural scoping, drop the keyword gate (D4)
- **`scoping.py`**:
  - **Import-graph closure**: from `feature.target_files`, `extract_import_specifiers` → `resolve_specifier_to_paths` (transitively, bounded depth) → the set of modules in scope.
  - **REQ-527 entity-reference resolution** (the gap): determine which Prisma entities a feature references — scan the feature's `target_files` content + description for model-name tokens from `PrismaSchema.models.keys()` (structural, not a fixed keyword list).
- **`prime_contractor._collect_upstream_interfaces`**: replace the `_feature_mirrors_data_model(feature)` gate (4301) with `scoping.referenced_entities(feature, schema)`; delete `_feature_mirrors_data_model` (4320) after REQ-540 parity holds.
- **Acceptance**: PI-001 (enrich-capabilities) gets `Capability`+`Outcome` field sets with **no** name-heuristic match.

### REQ-CKG-525 — Bounded token cost
- **`render.py`**: per-feature section size-bounded; `log()` artifact size + injected-token delta.
- **Acceptance**: per-feature section ≤ declared budget (~800 tok); budget+actual logged.

### REQ-CKG-540 — Characterization snapshot (refactor safety, D4)
- **`test_collect_upstream_snapshot.py`**: BEFORE refactor, capture golden output of `_collect_upstream_interfaces` on the at-risk branches:
  1. absent-anchor warning, 2. Mode-A producer not yet on disk, 3. no-TS/JS upstream early return (`""`), 4. Prisma branch fires / does-not-fire.
- Assert byte-parity after the REQ-524 refactor (same discipline as 690a).
- **Sequencing**: this test lands and goes green **before** any edit to `_collect_upstream_interfaces`.

### REQ-CKG-530 — Two-level success: injection vs adherence (D1)
- **Injection** (unit, the above tests): prompt content provable.
- **Adherence** (empirical harness, `scripts/`): re-run RUN-011 failed features with injection, **N≥5 seeds/feature**, measure per-Gap adherence rate vs ~0.9 threshold; preserve a no-injection baseline as regression guard. Below threshold → escalate (Approach C, scoped separately).
- **Acceptance**: provider is **not** declared done on injection alone; harness reports a rate per failure class.

---

## 3. Build order (dependency-ordered)

1. **REQ-540 characterization snapshot** of `_collect_upstream_interfaces` (lock current behavior) — *no production edits yet*.
2. **models.py** (`ProjectKnowledge` + `omissions`) — the output contract first (Keiyaku discipline).
3. **producer.py** `DraftModeProducer.build` over `parse_prisma_schema`/`tsconfig_paths`/`upstream_interface` (REQ-520/521/523).
4. **negatives.py** seeded list + **render.py** (REQ-522/523/525) — injection unit-testable end to end.
5. **scoping.py** import-graph closure + entity-reference resolution (REQ-524/527).
6. **Refactor `_collect_upstream_interfaces`** to consume the provider + structural scope; **assert REQ-540 parity**; delete `_feature_mirrors_data_model`.
7. **Adherence harness** (REQ-530) — the real gate; run RUN-011 repro, N≥5 seeds.

Steps 1–5 are additive (no behavior change). Step 6 is the only seam edit and is guarded by step 1.

---

## 4. Risks / watch-items

- **R1 — double resolver if scoping re-implements import resolution.** Mitigation: scoping MUST call `upstream_interface.resolve_specifier_to_paths`, not a new regex (§11).
- **R2 — REQ-540 snapshot misses a branch.** Mitigation: enumerate the four at-risk inputs explicitly (above); fixtures from the RUN-008/009 anchors.
- **R3 — entity-reference resolution (REQ-527) over/under-scopes.** Mitigation: start from token-match against real `models.keys()`; measure scope precision on PI-001/004/007 in the adherence harness.
- **R4 — adherence stays below threshold even with injection (D1 realized).** Then injection alone is insufficient → escalate to contract-first (Approach C); this plan delivers the *measurement* that triggers that decision, not the escalation itself.

---

## 5. Traceability (plan step → requirement)

| Plan step | REQ |
|---|---|
| §2 producer protocol + scip mirror | REQ-520, NFR-5 |
| §2 field-set authority | REQ-521 |
| §2 negatives | REQ-522 (D2) |
| §2 omissions model | REQ-523 (D3) |
| §2 scoping + entity-ref | REQ-524, **REQ-527 (new)** (D4) |
| §2 token budget | REQ-525 |
| §3 step 1 snapshot | REQ-540 (D4) |
| §2 adherence harness | REQ-530 (D1) |
