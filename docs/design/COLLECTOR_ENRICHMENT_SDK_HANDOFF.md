> **Mirror.** Canonical lives in ContextCore `docs/integrations/COLLECTOR_ENRICHMENT_SDK_HANDOFF.md`
> (PR #61). Copied here so the startd8-sdk team finds it in-repo. If the two drift, ContextCore wins.

# Handoff: `collector_enrichment` — SDK side (FR-1b + the generator)

**To:** startd8-sdk / observability generator team
**From:** ContextCore (cross-repo maintainer)
**Date:** 2026-07-23
**Feature:** generate the OTel Collector `transform/business` processor from the manifest, so the
per-service `{owner, criticality}` map has **one source** instead of the demo's 3-way hand-maintained mirror.
**Spec / plan (pilots repo):** `docs/design/requirements/REQ_COLLECTOR_ENRICHMENT.md` ·
`docs/plans/COLLECTOR_ENRICHMENT_NEXT_STEPS.md`

---

## BLUF

ContextCore's half of the **gate is now done and non-dormant**: `spec.targets[].criticality/owner`
(FR-1a) are captured, validated, and **exported into onboarding-metadata**. The SDK now receives a
per-service business block. What remains is **SDK-side**: read it onto `ServiceHints` (FR-1b) and build
the generator (FR-2–11). The generator is the same *generate-Collector-config-from-manifest* class as the
spanmetrics work (#307) — a new registered artifact type that emits one OTTL file.

## What ContextCore now produces (the contract — verify against this, not prose)

Per service, `onboarding-metadata.json → instrumentation_hints[<svc>].business`:

```json
"instrumentation_hints": {
  "cartservice":  { "business": { "criticality": "critical", "owner": "commerce-team" } },
  "emailservice": { "business": { "criticality": "high",     "owner": "platform-team" } }
}
```

Contract semantics (ContextCore side, shipped):
- **Shape:** `business: { criticality?: str, owner?: str }`. `criticality` ∈ `critical|high|medium|low`
  (the `Criticality` enum, serialized to its `.value`). `owner` is a team/persona alias (non-empty;
  never a personal email — a soft R2-F1 rule, not enforced yet).
- **Resolution (already applied):** per-target **overrides project, field-by-field**. A target matches a
  service by `TargetSpec.name == <svc>`. Partial is allowed (a target may set only `criticality`; `owner`
  falls back to `spec.business.owner`).
- **Absent → key omitted.** A manifest with no `spec.business` and no per-target values yields **no
  `business` key** (byte-identical to before) — so absence must degrade to a safe default, never read as a
  signal.
- **Produced by:** `derive_instrumentation_hints(... business_binding=...)` in
  `src/contextcore/utils/instrumentation.py`; the binding is built from the manifest in
  `src/contextcore/cli/manifest.py` (mirrors the `metric_binding` / `datasource_binding` pattern).

## SDK work remaining

### FR-1b — read `business` onto `ServiceHints` (small)
Today `extract_service_hints` (`artifact_generator_context.py:~528`) sets business **project-level only**:
```python
business = spec.get("business", {})
ctx.criticality = business.get("criticality", "medium")   # :535  — same for every service
ctx.owner       = business.get("owner")                   # :539
```
Change: for each service, **prefer `instrumentation_hints[svc].business.{criticality,owner}`** when
present, else fall back to the project value. This is the same per-service-hint consumption you already do
for `metrics.convention_profile` / `declared_span_signals`. Result: `ServiceHints.criticality/owner` become
genuinely per-service.

### FR-2–4 — register the artifact + emit the OTTL processor
- Add one row to `_ARTIFACT_TYPE_REGISTRY` (`artifact_generator_context.py:~30`), modeled on the
  `capability_index` / `onboarding_portal` **PROJECT** rows (`:44/:45`) but `Orientation.SYSTEM`:
  `ArtifactTypeSpec("collector_enrichment", "collector_enrichment", Category.PROJECT.value, Orientation.SYSTEM.value, <mergeable?>, <order>)`.
- Emit the OTTL `transform` processor, one statement per `(service, business attribute)`:
  `set(business.<attr>) where resource.attributes["service.name"] == "<svc>"` — iterate
  `services × {criticality, owner}` (no allowlist beyond the declared `business.*` vocabulary).
- One mergeable file at a named path (e.g. `collector-enrichment/otelcol-business-enrichment.yaml`) with a
  `# GENERATED` header + provenance = canonical hash of the `business`-carrying subtree.
- Use the **real `service.name`** (`ServiceHints.service_name`, REQ-CCL-105) for the selector value, not the
  sanitized `service_id`.

### FR-5/6/8 — determinism · escaping · validation
- Pre-sort the `(service, attribute)` list; deterministic dump (byte-identical across runs **and** shuffled
  input order).
- **Escape every string literal** (service name, owner, any `business.*` value) — greenfield OTTL, injection risk.
- `validate_collector_enrichment()`: every service with business context has a statement; no out-of-enum
  criticality; no duplicate/empty `service.name`; OTTL well-formed. **Fail-fast — no partial output.**

### FR-10a/11 — cutover safety
- One-shot parity gate: generated OTTL ≡ the demo's hand-written `transform/business` block before removal
  (generalize `bpi-astronomy/tools/check_context.py`).
- Idempotent regen; retain the prior artifact for rollback/diff.

**Deferred (NOT v1):** FR-7 spanmetrics dimension, `cost_weight`/`owner`-dimension extensions, FR-10b
post-cutover drift detection, the episodic `business.event` layer.

## Acceptance (SDK side)

1. Registry row → one project-scoped file per run.
2. Statement count == `|attributes| × N(services with business context)` — no hardcoded count.
3. Byte-identical across runs and shuffled input order.
4. Validator fails on: out-of-enum criticality, duplicate `service.name`, missing business on a declared service.
5. After operator wiring, spans carry `business.criticality`/`owner` in the backend.
6. Parity gate passes vs the deployed hand-written block before removal.

## References
- **Contract producer:** ContextCore `utils/instrumentation.py` (`business_binding`), `cli/manifest.py` (builder).
- **FR-1b precedent:** your existing per-service hint consumption (`convention_profile`,
  `_parse_declared_span_signals`).
- **Reference implementation to match (read-only):** InsightFinder demo
  `collector/otelcol-config-extras.yml` (the hand-written block this generates),
  `bpi-astronomy/tools/check_context.py` (parity), `bpi-astronomy/_bpi_map.py` + `decks.yaml` (the mirror this collapses).
- **Full spec + build sequence:** pilots `REQ_COLLECTOR_ENRICHMENT.md` + `COLLECTOR_ENRICHMENT_NEXT_STEPS.md`.

## Status ledger
| FR | Where | Status |
|----|-------|--------|
| FR-1a field (`TargetSpec.criticality/owner`) | ContextCore | ✅ merged (#59) |
| FR-1a export (`instrumentation_hints[svc].business`) | ContextCore | ✅ **this handoff's companion PR** |
| FR-1b (`ServiceHints` per-service) | startd8-sdk | ⏳ **you** |
| FR-2–11 (generator) | startd8-sdk | ⏳ **you** |
