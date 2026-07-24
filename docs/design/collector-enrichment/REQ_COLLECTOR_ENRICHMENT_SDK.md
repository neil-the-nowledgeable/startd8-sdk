# Collector Enrichment — SDK-side Requirements (FR-1b + the generator)

**Version:** 0.3.1 (Post planning + lessons + design-principle hardening — ready for CRP)
**Date:** 2026-07-23
**Status:** Ready for implementation
**Owner doc (cross-repo, canonical spec):** ContextCore-pilots `docs/design/requirements/REQ_COLLECTOR_ENRICHMENT.md`
· `docs/plans/COLLECTOR_ENRICHMENT_NEXT_STEPS.md`
**Incoming handoff (this repo):** `docs/design/COLLECTOR_ENRICHMENT_SDK_HANDOFF.md` (issue #320)
**Tracks:** issue #320 (doc mirror, done) + the SDK-side FR-1b/FR-2–11 build.

---

## 0. Planning Insights (Self-Reflective Update)

> This section records what the planning pass (reading the real producer + the real reference
> OTTL block, not the handoff prose) corrected between the draft understanding and v0.2. Six of
> the fine-grained requirements changed — the loop earned its keep.

| Draft assumption (from handoff prose) | Planning discovery (from real code/artifact) | Impact |
|---|---|---|
| Hint carries top-level `hint["criticality"]`/`hint["owner"]` (one Explore agent suggested this). | The **real producer** (`ContextCore utils/instrumentation.py:523`, PR branch) writes a **nested** `hint["business"] = {criticality?, owner?}`, keys omitted when absent. | FR-1b reads `hint["business"]`, not top-level keys. |
| SDK must re-apply a **project→service fallback** onto `ServiceHints` (handoff FR-1b: "else fall back to the project value"). | The producer **already resolved** per-target-over-project **field-by-field** (`_svc.get(x) or _project.get(x)`, `:516-517`). Re-applying it SDK-side is redundant **and** breaks the "absent → omitted → byte-identical" acceptance (every service would default to `medium`). | **Dropped** the SDK-side project fallback (NR-2). `ServiceHints.criticality/owner` carry the raw, already-resolved per-service value; absent ⇒ `""`/`None`. |
| OTTL statement form is `set(business.<attr>) where resource.attributes["service.name"] == "<svc>"` (handoff). | The **real reference block** (`Insight-Finder/demo/collector/otelcol-config-extras.yml:37-48`) uses `set(attributes["business.<attr>"], "<value>") where resource.attributes["service.name"] == "<svc>"` — two-arg, bracketed attribute path, inside `trace_statements → context: span`, `error_mode: ignore`. | FR-3 emits the **real** form (the handoff prose was garbled OTTL). |
| Parity gate compares **bytes** vs the hand-written block (handoff FR-10a/11). | The hand-written block **groups services by shared value** (all `critical` services OR'd into one statement); the spec emits **one statement per service**. Byte parity is impossible between the two forms. | FR-10a/11 reframed to **semantic** parity — parse both into `{service:{attr:value}}` and compare (order/grouping-insensitive). |
| Statement count acceptance = `|attributes| × N(services)` (handoff acceptance #2). | The contract allows **partial** targets (a service may carry only `criticality`). After producer resolution a service may legitimately have one attr. | Count = **Σ present `(service, attr)` pairs**, not `|attr|×N`. `|attr|×N` is only the special case where every service carries every attr. |
| Artifact is **declaration-gated** (emit only if `collector_enrichment` in `metadata.declared`), mirroring `capability_index`. | Requiring a separate declaration is redundant machinery — the presence of exported `business` context **is** the signal. Declaration-gating would also leave the file un-emitted for the exact demo the parity gate targets. | Artifact is **presence-gated**: emit iff ≥1 service carries business context; else `status="skipped"`, empty content (SOTTO byte-identical absence). |

**Resolved open questions:**
- **OQ-1 → one statement per service** (not grouped-by-value). Simpler, fully deterministic, no OR-chain ordering ambiguity; the semantic parity gate absorbs the grouping difference.
- **OQ-2 → statement count = Σ present `(service, attr)` pairs.** Partial business context is valid.
- **OQ-3 → no SDK-side project fallback.** The producer already applied it.
- **OQ-4 → semantic parity, not byte parity.**
- **OQ-5 → presence-gated emission, not declaration-gated.**
- **OQ-6 → provenance lives in the `# GENERATED` header comment only** (canonical hash), *not* as a `business.context_version` OTTL statement — keeps the emitted statement set equal to the reference so semantic parity is clean (NR-4).

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK / design-doc lessons before CRP. Each changed the draft:

- **Phantom-reference audit** — grepped every symbol the spec names against its owning module. Findings folded into §7 Reference Audit: `ServiceHints`, `ArtifactTypeSpec`, `ArtifactResult`, `_ARTIFACT_TYPE_REGISTRY`, `extract_service_hints`, `generate_capability_index`, `generate_observability_artifacts` all **verified present** at cited lines; `generate_collector_enrichment` + `validate_collector_enrichment` + `check_collector_enrichment_parity` are marked **to-be-created**.
- **Genchi Genbutsu / bind-to-real-artifact** — the reference OTTL was **not** on the handoff's stated path; found the real file under `~/Documents/Jobs/.../Insight-Finder/demo/`. Its verbatim block is now the parity fixture (FR-11), not the handoff's paraphrase.
- **Single-source vocabulary ownership** — the `criticality` enum (`critical|high|medium|low`) is **owned by ContextCore** (`models/core.py Criticality`). This doc cites it as a *non-normative snapshot*; the validator (FR-8) treats it as the closed set but does not re-declare ownership.
- **CRP steering** — the least-reviewed artifact here is this fresh requirements doc + its plan; the settled/do-not-relitigate set is the ContextCore-side contract (FR-1a, merged) and the reference block bytes.

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked the draft against `docs/design-princples/`. Each changed the draft:

- **Genchi Genbutsu** — bind the selector value to the **real** `service.name` (`ServiceHints.service_name`, REQ-CCL-105), never the sanitized `service_id`; fall back to `service_id` only when `service_name` is empty (FR-3, FR-6a).
- **SOTTO (don't disturb what exists)** — a manifest with no business context must yield **no `business` key** and **no new artifact file** — byte-identical to a pre-feature run. Encoded as the presence gate (FR-3) + a byte-identical-absence test (FR-9 accept #3a).
- **Mottainai (don't regenerate what exists)** — do **not** re-apply the project→service fallback the producer already computed (NR-2); consume the forwarded `hint["business"]` as-is.
- **Accidental-Complexity anti-principle** — the two highest-yield deletions: (a) **no declaration allowlist** — presence-gate instead (one rule, not an enumerated `declared` entry + `owned_elsewhere` bookkeeping); (b) **no value-grouping engine** — one-statement-per-service + a semantic parity gate, rather than a grouping algorithm whose ordering is a fresh source of non-determinism.
- **Hitsuzen (derive the determinable)** — every byte of the OTTL is a pure function of `(services, business vocabulary)`; **zero LLM** involvement. This is a bucket-1 deterministic artifact.

---

## 1. Problem Statement

The InsightFinder / Online-Boutique demo hand-maintains a 3-way mirror of `service → {criticality, owner}`
(`otelcol-config-extras.yml` transform block, `bpi-astronomy/_bpi_map.py`, `decks.yaml`). ContextCore's
FR-1a now captures that data once in the manifest (`spec.business` + `spec.targets[].criticality/owner`)
and **exports it** per-service as `onboarding-metadata → instrumentation_hints[svc].business`. The SDK must
turn that single source into the OTel Collector `transform/business` processor, retiring the hand-written
mirror.

| Component | Current State | Gap |
|---|---|---|
| `ServiceHints` | 15 fields; reads metrics/datasource/span hints per service | Does **not** read `hint["business"]` → per-service criticality/owner unavailable to generators |
| Artifact registry | 9 rows (triplet + extended + 2 PROJECT) | No `collector_enrichment` row |
| Generators | alert/dashboard/slo/…/capability_index | No OTTL `transform/business` emitter |
| OTTL emission | none in repo | Greenfield — need deterministic + escaped emit + validate + parity gate |
| Demo enrichment | hand-written `transform/business`, hand-mirrored | Must be generated from the manifest, parity-checked before removal |

## 2. Requirements

### FR-1b — Read per-service business onto `ServiceHints`
- Add two fields to `ServiceHints` (`artifact_generator_models.py`): `criticality: str = ""`,
  `owner: Optional[str] = None`.
- In `extract_service_hints` (`artifact_generator_context.py:398`), read `_biz = hint.get("business") or {}`
  and set `criticality=str(_biz.get("criticality") or "")`, `owner=(_biz.get("owner") or None)`.
- **No SDK-side project fallback** (the producer already resolved target-over-project). Absent `business`
  key ⇒ `""` / `None` ⇒ the service contributes no enrichment statement.
- Byte-identical to today for any hint without a `business` key.

### FR-2 — Register the `collector_enrichment` artifact type
- Add one `ArtifactTypeSpec` row to `_ARTIFACT_TYPE_REGISTRY`
  (`artifact_generator_context.py:30`): `ArtifactTypeSpec("collector_enrichment",
  "collector_enrichment", Category.PROJECT.value, Orientation.SYSTEM.value, False, 85)` — a PROJECT/SYSTEM
  artifact ordered after per-service rows, before `capability_index` (80 < 85 < 90 sits it among project
  consumers; final order is fixed in the plan). `requires_declaration=False` — gating is presence-based
  (FR-3), not declaration-based.

### FR-3 — Emit the OTTL `transform/business` processor
- New `generate_collector_enrichment(services, business, report) -> ArtifactResult` in
  `artifact_generator_generators.py`.
- **Selector value:** `service.service_name` when non-empty, else `service.service_id` (REQ-CCL-105).
- **Statement form (verbatim to the reference):**
  `set(attributes["business.<attr>"], "<value>") where resource.attributes["service.name"] == "<svc>"`.
- **One statement per present `(service, attr)`**, `attr ∈ {criticality, owner}` (criticality statements
  before owner statements; §5 fixes ordering).
- **Wrapper (verbatim structure):**
  ```yaml
  processors:
    transform/business:
      error_mode: ignore
      trace_statements:
        - context: span
          statements:
            - set(attributes["business.criticality"], "critical") where resource.attributes["service.name"] == "frontend"
            - ...
  ```
- **Output path:** `collector-enrichment/otelcol-business-enrichment.yaml` (one mergeable file, project-scope).
- **Presence gate:** if no service carries criticality or owner ⇒ `status="skipped"`, `content=""`
  (SOTTO: no file written, byte-identical absence).

### FR-4 — Provenance header
- Prepend a `# GENERATED — do not edit; regenerate via startd8 observability` header carrying
  `# provenance: sha256:<hash>`, where `<hash>` = canonical hash of the sorted service→business map
  (the `business`-carrying subtree). No `business.context_version` OTTL statement (NR-4).

### FR-5 — Determinism
- Pre-sort statements by `(attr rank: criticality=0, owner=1, then service_name asc)`.
- Deterministic YAML dump (`sort_keys=False`, block style) with insertion-ordered dicts.
- Output **byte-identical across repeated runs and across shuffled input service order** (accept-test enforced).

### FR-6 — Escaping (injection safety)
- Escape **every** emitted string literal — the selector service name **and** the value (owner is free
  text). OTTL uses Go-style double-quoted literals: `\` → `\\`, then `"` → `\"`. Apply via one
  `_ottl_str(s)` helper used for both positions.
- **FR-6a:** the escaped service name in the selector is the same real `service.name` (FR-3), escaped.

### FR-8 — Validation (fail-fast, no partial output)
- `validate_collector_enrichment(model) -> None` raises `CollectorEnrichmentError` on any of:
  1. a service present in the resolved business map contributes **zero** statements;
  2. a `criticality` value outside `{critical, high, medium, low}` (ContextCore `Criticality` snapshot);
  3. a duplicate or empty resolved `service.name`;
  4. structurally malformed model (missing processor/statements keys).
- On raise, the generator returns `status="error"`, `error_message=<reason>`, `content=""` — **never a
  half-written file.** Validation runs on the built model **before** serialization.

### FR-10a / FR-11 — Cutover parity gate (one-shot, semantic)
- `check_collector_enrichment_parity(generated_yaml: str, reference_yaml: str) -> ParityResult` parses
  both configs, extracts `{service.name: {criticality?, owner?}}` from each transform/business block
  (order- and grouping-insensitive: splits `where … == "x" or … == "y"` back into per-service entries),
  and reports `matches: bool` + a symmetric diff (`only_in_generated`, `only_in_reference`, `value_mismatch`).
- Ships as a function + a unit test that runs it against the **verbatim reference block** (FR-11 fixture)
  built from the Online-Boutique manifest, asserting `matches == True`.
- **FR-11:** regeneration is idempotent (byte-identical re-run); the deterministic output + the framework's
  existing drift/`--check` path cover rollback/diff (no new retention machinery).

## 3. Non-Requirements

- **NR-1 — Rewiring existing generators (alert/slo/runbook/dashboard) to prefer per-service
  criticality/owner.** They keep reading project-level `business.criticality/owner`. Making them
  per-service is a separate, byte-output-affecting change; **deferred**. The sole consumer of the new
  `ServiceHints` fields in v1 is `generate_collector_enrichment`.
- **NR-2 — SDK-side project→service fallback.** The producer already applied it (§0).
- **NR-3 — FR-7 `business.criticality` as a spanmetrics dimension** (`calls_total{business_criticality=…}`).
  Deferred.
- **NR-4 — `business.context_version` OTTL statement.** Provenance lives in the header comment; keeps the
  emitted statement set equal to the reference for clean semantic parity.
- **NR-5 — value-grouping (OR-chaining services that share a value).** The generator emits one statement
  per service; the semantic parity gate tolerates the reference's grouping.
- **NR-6 — `cost_weight`/`owner`-dimension extensions, FR-10b post-cutover drift detection, the episodic
  `business.event` layer.** Deferred (sibling contracts).
- **NR-7 — LLM involvement.** Fully deterministic ($0), bucket-1.

## 4. Open Questions

All resolved in §0. None outstanding.

## 5. Acceptance Criteria (SDK side)

1. Registry row present → exactly one project-scoped file per run **when ≥1 service has business context**.
2. Statement count == **Σ present `(service, attr)` pairs** — no hardcoded count; `|attr|×N` only when all
   services carry all attrs.
3. Byte-identical output across repeated runs **and** shuffled input order.
   **3a.** A manifest with no business context writes **no** enrichment file and is byte-identical to a
   pre-feature run.
4. Validator raises (⇒ `status="error"`, no file) on: out-of-enum criticality, duplicate/empty
   `service.name`, a business-carrying service with zero statements, malformed model.
5. Every emitted string literal is Go-escaped (verified with an owner value containing `"` and `\`).
6. `check_collector_enrichment_parity(generated, reference)` returns `matches == True` against the
   verbatim Online-Boutique reference block.
7. Selector uses the real `service.name` (slash-preserved), not `service_id`.

## 6. Traceability

| FR | Plan step | Primary file(s) |
|---|---|---|
| FR-1b | P1 | `artifact_generator_models.py`, `artifact_generator_context.py` |
| FR-2 | P2 | `artifact_generator_context.py` (`_ARTIFACT_TYPE_REGISTRY`) |
| FR-3/4/5/6 | P3 | `artifact_generator_generators.py` (new emitter + `_ottl_str`) |
| FR-8 | P4 | new `collector_enrichment_validation.py` (or `validators/observability_artifact_checks.py`) |
| FR-10a/11 | P5 | new parity module + fixture |
| Wiring | P6 | `artifact_generator.py` (`generate_observability_artifacts`) |
| Tests | P7 | `tests/unit/observability/` |

## 7. Reference Audit (phantom-reference check)

| Symbol | Owning module:line | Status |
|---|---|---|
| `ServiceHints` | `artifact_generator_models.py:117` | ✅ exists (extend) |
| `BusinessContext` | `artifact_generator_models.py:191` | ✅ exists |
| `ArtifactTypeSpec` | `artifact_generator_models.py:~311` | ✅ exists |
| `ArtifactResult` | `artifact_generator_models.py:262` | ✅ exists |
| `_ARTIFACT_TYPE_REGISTRY` | `artifact_generator_context.py:30` | ✅ exists (add row) |
| `extract_service_hints` | `artifact_generator_context.py:398` | ✅ exists (extend) |
| `generate_observability_artifacts` | `artifact_generator.py:477` | ✅ exists (wire in) |
| `generate_capability_index` | `artifact_generator_generators.py` | ✅ exists (model) |
| `Category` / `Orientation` | `taxonomy_enums.py` | ✅ exists |
| Reference OTTL block | `~/Documents/Jobs/.../Insight-Finder/demo/collector/otelcol-config-extras.yml:31-48` | ✅ exists (fixture) |
| `generate_collector_enrichment` | `artifact_generator_generators.py` | ⛔ **to be created** |
| `validate_collector_enrichment` | new module | ⛔ **to be created** |
| `check_collector_enrichment_parity` | new module | ⛔ **to be created** |
| ContextCore `hint["business"]` producer | `ContextCore utils/instrumentation.py:523` (PR branch) | ✅ verified (contract) |

---

*v0.3.1 — Post planning (6 corrections), lessons (4 applied), and design-principle (5 applied) hardening.
Ready for CRP review. Bucket-1 deterministic, $0.*
