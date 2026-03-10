# Kaizen Investigation: Plan Ingestion Quality Patterns (Run-025)

> **Date:** 2026-03-10
> **Run:** run-025-20260310T1231 (online-boutique)
> **Scope:** Systemic quality patterns in PARSE → TRANSFORM → ENRICH → EMIT data flow
> **Companion:** [KAIZEN_PLAN_INGESTION_REQUIREMENTS.md](../plan-ingestion/KAIZEN_PLAN_INGESTION_REQUIREMENTS.md)

---

## Summary

Run-025 produced a high seed quality score (0.975) but field-level analysis reveals 5 systemic patterns that silently degrade downstream code generation quality. The score is inflated because it measures description presence and target files but not structured context field completeness.

| ID | Pattern | Severity | Priority | Impact |
|----|---------|----------|----------|--------|
| QP-1 | Two-channel data loss (PARSE → seed) | HIGH | P0 | New PARSE fields silently dropped without explicit wiring |
| QP-2 | TRANSFORM prompt context duplication | MEDIUM | P1 | ~15% token waste, cross-contamination of sub-feature contracts |
| QP-3 | Seed quality score doesn't reflect structured field completeness | HIGH | P0 | 0.975 score masks 10/17 tasks missing api_signatures |
| QP-4 | PARSE feature granularity mismatch | MEDIUM | P2 | Sub-features inherit full parent contract (5000+ chars irrelevant) |
| QP-5 | Enrichment-diagnostic timing ambiguity | LOW | P2 | Quality score may not reflect enrichment improvements |

---

## QP-1: Two-Channel Data Loss (PARSE Fields → Seed)

**Severity:** HIGH
**Priority:** P0

### Problem

PARSE extracts rich structured data per feature (`api_signatures`, `negative_scope`, `protocol`, etc.), but each field must be manually threaded through the seed assembly function (`_build_prime_tasks`, lines 3153–3200 in `plan_ingestion_workflow.py`). Any field PARSE extracts but the assembly doesn't explicitly wire gets silently dropped.

### Current Wiring (7 explicit fields)

```python
ctx = {
    "feature_id": feat.feature_id,
    "target_files": ordered_files,
    "estimated_loc": feat.estimated_loc,
}
if feat.negative_scope: ctx["negative_scope"] = list(feat.negative_scope)
if feat.api_signatures: ctx["api_signatures"] = list(feat.api_signatures)
if feat.protocol: ctx["protocol"] = feat.protocol
if feat.runtime_dependencies: ctx["runtime_dependencies"] = list(feat.runtime_dependencies)
if feat.design_doc_sections: ctx["design_doc_sections"] = list(feat.design_doc_sections)
if feat.artifact_types_addressed: ctx["artifact_types_addressed"] = list(feat.artifact_types_addressed)
```

### Missing Fields

- `requirements_refs` — only populated by enrichment, not from PARSE
- `refinement_suggestions` — only populated by enrichment (was broken, now fixed)
- Any future PARSE fields — silent loss unless someone adds an `if feat.X:` line

### Fix

Replace the manual field-by-field wiring with a declarative approach: define the set of "context-threadable" fields on `ParsedFeature` and auto-forward any non-empty field to the task context dict.

```python
_CONTEXT_THREADABLE_FIELDS = {
    "negative_scope", "api_signatures", "protocol",
    "runtime_dependencies", "design_doc_sections",
    "artifact_types_addressed",
}

for field_name in _CONTEXT_THREADABLE_FIELDS:
    val = getattr(feat, field_name, None)
    if val:
        ctx[field_name] = list(val) if isinstance(val, (list, tuple)) else val
```

Adding a new PARSE field to `_CONTEXT_THREADABLE_FIELDS` becomes a one-line change instead of adding another `if` block.

---

## QP-2: TRANSFORM Prompt Context Duplication

**Severity:** MEDIUM
**Priority:** P1

### Problem

The TRANSFORM prompt (39KB) includes the full implementation contract from PARSE for EVERY feature — even sub-features of the same service. F-002a (email server), F-002b (email client), and F-002c (email template) each include the complete 200-line `email_server.py` contract verbatim.

### Evidence

- F-002a, F-002b, F-002c share identical 200-line contract block in the TRANSFORM prompt
- Total duplication: ~6KB across 3 sub-features
- TRANSFORM cost: $0.277 — deduplication could reduce by ~15%
- Sub-feature task descriptions inherit the parent contract, creating 5000+ char descriptions where the relevant content is a fraction

### Impact

1. **Token waste**: Same contract appears 3x in the prompt
2. **Cross-contamination**: LLM may produce task descriptions that reference the wrong sub-feature's internals (PI-005/template gets server class details)
3. **Downstream cost**: Contractor processes 5000+ chars per task when 500–1000 would suffice

### Fix

In `_phase_transform` prompt construction, deduplicate shared contracts:
- When multiple features share the same parent (e.g., F-002a/b/c), include the full contract once under the parent, then reference it from sub-features
- Or: scope each sub-feature's contract to only the relevant section (email_client.py for F-002b, not the full email_server.py)

This is a PARSE-level fix — the feature splitting logic should scope the contract to the sub-feature's target file, not copy the entire parent.

---

## QP-3: Seed Quality Score Doesn't Reflect Structured Field Completeness

**Severity:** HIGH
**Priority:** P0

### Problem

The 6-component quality formula (REQ-KPI-302) measures:

| Component | Weight | What It Checks |
|-----------|--------|----------------|
| Description presence | 0.20 | Non-empty `task_description` |
| Target file presence | 0.20 | Non-empty `target_files` |
| Schema validity | 0.15 | JSON schema passes |
| Field coverage | 0.15 | Optional enrichment fields populated |
| Description depth | 0.15 | `min(chars/500, 1.0)` average |
| Description richness | 0.15 | Code examples OR requirements refs |

### Gap

No component measures structured context field completeness. Run-025:
- 10/17 tasks missing `api_signatures` in context → score unaffected
- 17/17 tasks missing `requirements_refs` in context → score unaffected
- 17/17 tasks missing `refinement_suggestions` in context → score unaffected
- **Score: 0.975** — gives false confidence

### Fix

Add a 7th component or replace "Field coverage" with a structured completeness check:

```python
# Count tasks with minimum viable structured context
_STRUCTURED_CONTEXT_FIELDS = {"api_signatures", "negative_scope", "target_files"}
ctx_complete = sum(
    1 for t in tasks
    if all(t.get("config", {}).get("context", {}).get(f) for f in _STRUCTURED_CONTEXT_FIELDS)
) / max(len(tasks), 1)
```

This would drop run-025's score from 0.975 to ~0.85, reflecting the actual field gaps.

---

## QP-4: PARSE Feature Granularity Mismatch

**Severity:** MEDIUM
**Priority:** P2

### Problem

PARSE splits multi-file features (F-002 → F-002a, F-002b, F-002c) to enforce single-file-per-task. But the implementation contracts from the original feature aren't scoped to the sub-feature — each sub-feature inherits the FULL parent contract.

### Evidence

- PI-005 (HTML template, 54 lines) carries the complete 200-line email_server.py contract
- PI-007 (test client, 40 lines) also carries the full server contract
- PI-010–013 (Dockerfiles, ~30 lines each) each carry the full gRPC service contract

### Impact

Downstream code generation wastes tokens processing irrelevant context. The contractor sees 5000+ chars of server internals when it only needs the 54-line template specification.

### Fix

In PARSE, when splitting features into sub-features:
1. Extract only the contract section relevant to the sub-feature's target file
2. Preserve the parent feature reference for cross-context lookups
3. Include a "parent_contract_summary" (1-2 lines) instead of the full contract

This requires changes to the PARSE prompt template (ask the LLM to scope contracts per sub-feature) and/or post-PARSE processing to trim contracts.

---

## QP-5: Enrichment-Diagnostic Timing Ambiguity

**Severity:** LOW
**Priority:** P2

### Problem

The `seed_quality_score` in the diagnostic report uses `compute_seed_quality()` which accepts task density data. The density data should reflect post-enrichment state, but if the diagnostic is computed before enrichment runs, the score doesn't reflect improvements.

### Evidence

The code path in `_phase_emit` shows enrichment runs before diagnostic computation (correct ordering), but the `compute_seed_quality` call in the artisan route may use pre-enrichment data depending on when `task_density` is computed.

### Fix

Ensure `compute_task_density()` is always called AFTER enrichment completes. Add an assertion or ordering comment at the call site. This is a defensive measure — current code likely has correct ordering, but the implicit dependency should be explicit.

---

## Implementation Priority

### P0 (this session)
1. **QP-1**: Declarative context field forwarding — replace manual `if feat.X:` wiring
2. **QP-3**: Add structured context completeness to seed quality score

### P1 (next session)
3. **QP-2**: TRANSFORM prompt deduplication — scope sub-feature contracts

### P2 (backlog)
4. **QP-4**: PARSE contract scoping for sub-features
5. **QP-5**: Defensive ordering assertion for enrichment → diagnostic
