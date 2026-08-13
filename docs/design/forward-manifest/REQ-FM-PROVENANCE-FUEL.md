# ForwardManifest Provenance Fuel — Requirements

**Project:** startd8-sdk (Forward-Looking Code Manifest)   **Criticality:** medium
**Version:** 0.3 (post lessons + principle hardening)   **Date:** 2026-08-13
**Format:** det-req/0.1
**Backend:** startd8-python-cascade
**Pairs with:** `docs/design/forward-manifest/PLAN-FM-PROVENANCE-FUEL.md`
**Inherits standards:** det-req-kit; cites FLCM schema (`forward_manifest.py`); cites intent-language evidence locator pattern (ContextCore Delivery Evidence Contract — **cite only**, do not fork)

## 0. Planning Insights (Self-Reflective Update)

> v0.1 assumed “persist writes nulls.” Planning against code showed the trio is **never set at construction** either: `_extract_forward_manifest` builds `ForwardManifest(contracts=…, file_specs=…)` only (`plan_ingestion_emitter.py` ~572–575), and `_write_forward_manifest` dumps the in-memory model unchanged (`prime_contractor.py` ~2275–2305). Seed already carries top-level `source_checksum`; Prime already reads it for corpus serving. Fuel at **persist time** (Option 2) is sufficient for disk consumers; optionally mirror into the in-memory model so post-write readers agree. Specimen: `benchmarking/Summer2026/portal-v2/.startd8/forward-manifest.json` — all three null, `metadata: {}`.

| v(n-1) Assumption | Planning Discovery | Impact |
|-------------------|--------------------|--------|
| Provenance nulls are a write-path bug only | Nulls originate at extract construction; write is a faithful dump of an unfueled model | FR-1 fuels at `_write_forward_manifest` (and may set fields on the in-memory model before dump); do **not** require a schema change |
| `source_checksum` must be recomputed at persist | Seed top-level already has `source_checksum` (ContextSeed emit ~1196–1198); Prime reads it via `_seed_path` (~4045–4054) | FR-2 copies seed → manifest; no new checksum algorithm |
| `pipeline_run_id` needs a new ID generator | `KAIZEN_RUN_ID` is already used in the same class (~3100, ~5882, ~5919); generation manifest already stamps `generated_at` (~2243) | FR-1/FR-3 reuse those sources; fail-honest leave null if truly absent |
| Evidence belongs as new schema fields | Schema already has `metadata: dict` (~348); intent pattern is `git:<40-hex>:<path>` + sha256 + provenance | FR-4 uses optional `metadata.persisted_file_evidence` only; cite Delivery Evidence Contract, do not restate |
| Every `file_specs` key is a file | Specimen keys directories (`app/templates/`, language unknown) | FR-4 records evidence only for real committed files; skip directories / missing paths |
| Fueling trio = delivery health | Harvest category error: `[BINDING]` / draft `validate_implementation` ≠ health; `stages_completed` is a monotone log | Non-goals NR-1…NR-4; null remains renderable as unknown |

**Resolved open questions (planning):**
- **OQ-1 → Fuel at persist (primary).** Disk artifact is the FR-CL-1 contract surface; extract-time fuel deferred (OQ-CRP-1).
- **OQ-2 → Copy seed `source_checksum`, do not rehash.** Matches Mottainai (forward the artifact).
- **OQ-3 → Metadata key name locked:** `persisted_file_evidence` (list of objects); omit or `[]` when nothing committed.

### 0.1 Lessons-Learned Hardening (v0.3)

> Pattern recall keyed on `{requirement\|code × context-arrival/data-wiring, single-source/no-drift, fail-loud/validation-gate}` → PC-5, PC-2, PC-4, PC-9. Domain lesson recall was thin/off-domain; harvest + PC twins carried the load.

- **[PC-5 / single-source]** — Intent evidence grammar already lives in ContextCore Delivery Evidence Contract + dossier `DeliveryEvidence` → **cite** locator/sha256/provenance shape; do not fork a startd8 evidence ledger (NR-2, FR-4 notes).
- **[PC-4 / Genchi]** — Specimen + file:line grounded before FR wording; Touches point at real persist/extract paths.
- **[PC-9 / fail-honest]** — Unknown provenance stays `null` (detectable), never a synthetic “ok” run id or empty-string success (FR-5).
- **[Harvest §4.1 — claims gate needs drift plates]** — PLAN requires a regression fixture of the null specimen + selftest-style unit coverage (FR-1 Verify / Iter 3).
- **[BACKEND_ROUTING]** — Re-checked: FRs are SDK model + persist wiring, **not** CLI/console-script → keep `startd8-python-cascade` (entity = ForwardManifest); reject `python-cli-surface`.

### 0.2 Design-Principle Hardening (v0.3)

| Principle | Check | Draft change |
|-----------|-------|--------------|
| **Context-Correctness-by-Construction** (`× context-arrival/data-wiring`) | Required provenance context must reach the persisted consumer, not silently stay `None` when known upstream | FR-1…FR-3: copy known run_id / timestamp / seed checksum into schema fields at persist |
| **Mottainai** | Do not rebuild Delivery Evidence Contract inside startd8 | Cite only; FR-4 is optional metadata fuel of the same locator shape |
| **Genchi Genbutsu** | Bind to real persist path + wild specimen | Grounded; regression against null specimen in PLAN |
| **Fail-loud / Hayai** | Null must be detectable as unknown, not silent success | FR-5 + NR-3; consumers treat null trio as unknown |
| **Accidental-Complexity** | No fourth conductor; no second ledger | NR-1, NR-2; Option 2 only |

## Overview

PrimeContractorWorkflow already persists `{project_root}/.startd8/forward-manifest.json` (FR-CL-1), but schema-defined provenance fields (`pipeline_run_id`, `generated_at`, `source_checksum`) ship as `null` in the wild while `metadata` stays empty. This requirement **fuels those existing Optional fields** at persist time from context the run already has (env run id, wall-clock ISO timestamp, seed checksum), and — once generated outputs are **committed** — optionally records per-file content-addressed evidence in `metadata` using the intent-language locator pattern (`git:<40-hex>:<path>` + sha256 + provenance). No new subsystem; dossier/intent ledger stays separate; `[BINDING]` prescription and `stages_completed` are out of scope for health.

## Objectives

- O-1: Persisted ForwardManifest carries non-null provenance trio whenever upstream values are known.
- O-2: When outputs are committed, `metadata.persisted_file_evidence` lists content-addressed locators for those files (cite intent pattern).
- O-3: Null / missing provenance remains an explicit **unknown** signal — never a false green.
- O-4: target: TBD (dormant) — extract-time fuel so seed-embedded `forward_manifest` also carries the trio (CRP may promote).

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Inventing a second evidence ledger inside FLCM | Optional metadata only; cite Delivery Evidence Contract; NR-2 | high |
| quality | Treating fuelled provenance or `[BINDING]` as delivery health | Explicit non-goals; FR-5 fail-honest null | high |
| quality | Fake run ids / checksums when upstream absent | Leave null; never invent | high |
| scope-creep | Redefining `stages_completed` or adding schema-required fields | Prefer Optional existing fields; NR-4 | medium |
| quality | Directory-keyed `file_specs` produce bogus evidence | Skip non-files / uncommitted paths (FR-4) | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Fuel provenance at persist.** When `_write_forward_manifest` writes a non-None `_forward_manifest`, it sets `generated_at` to an ISO-8601 UTC timestamp (same discipline as `_write_generation_manifest`) and sets `pipeline_run_id` from a known run identifier when available (`KAIZEN_RUN_ID` or an already-populated manifest/`seed` run id), mutating the in-memory model before dump so disk and memory agree. Touches: ForwardManifest.generated_at, ForwardManifest.pipeline_run_id, PrimeContractorWorkflow._write_forward_manifest. Verify: unit test — given a bare ForwardManifest with null trio and `KAIZEN_RUN_ID=test-run-42`, after `_write_forward_manifest` the JSON has non-null `pipeline_run_id` and `generated_at`. Serves: O-1

- **FR-2 — Propagate seed source_checksum.** At the same persist point, if `source_checksum` on the in-memory manifest is null/empty and the run’s seed (via `_seed_path` or already-loaded seed data) carries a string `source_checksum`, copy that value onto `ForwardManifest.source_checksum` before dump. Touches: ForwardManifest.source_checksum, PrimeContractorWorkflow._write_forward_manifest, seed top-level source_checksum. Verify: unit test — seed JSON with `source_checksum: "sha256:abc"` and null manifest field → persisted manifest `source_checksum == "sha256:abc"`. Serves: O-1

- **FR-3 — Fail-honest when upstream unknown.** If run id and/or seed checksum are genuinely unavailable, leave the corresponding field `null` (do not invent placeholders, empty strings, or `"unknown"` tokens that consumers could misread as success); `generated_at` is always settable at write time and MUST be non-null on a successful write. Touches: ForwardManifest.pipeline_run_id, ForwardManifest.source_checksum, ForwardManifest.generated_at. Verify: unit test — no env run id, no seed path → persisted JSON has `pipeline_run_id: null`, `source_checksum: null`, and non-null `generated_at`. Serves: O-3

- **FR-4 — Optional committed-file evidence in metadata.** After outputs exist and are committed in the project git repo, `_write_forward_manifest` MAY populate optional `metadata["persisted_file_evidence"]` as a list of objects `{path, locator, sha256, provenance}` where `locator` is `git:<40-hex-sha>:<repo-relative-path>`, `sha256` is the blob content digest, and `provenance` names the writer (e.g. `prime-contractor-persist`); only real file paths under consideration (not directory-keyed `file_specs`); omit the key or write `[]` when nothing is committed. Touches: ForwardManifest.metadata, metadata.persisted_file_evidence. Verify: unit test in a temp git repo — committed file `src/a.py` listed for evidence → entry with matching locator + sha256; uncommitted / directory path → no bogus entry. Serves: O-2

- **FR-5 — Null provenance detectable as unknown.** Consumers and tests MUST treat a null `pipeline_run_id` or `source_checksum` as **unknown provenance**, not as healthy/complete delivery; this REQ does not map provenance fields (or `stages_completed`, or `[BINDING]` text) into delivery-health enums. Touches: ForwardManifest (read contract), tests/unit/contractors/test_forward_manifest_persistence.py. Verify: regression fixture loaded from a copy of the portal-v2 null specimen asserts trio-null ⇒ “unknown” classification helper or explicit assertion comments; after fuel path, same helper reports partial/complete only from non-null fields. Serves: O-3

- **FR-6 — No schema break / round-trip.** Fuelled manifests continue to validate with `ForwardManifest.model_validate_json` and round-trip via existing persistence tests; new metadata keys are optional and ignored by readers that do not understand them. Touches: ForwardManifest, test_forward_manifest_persistence.py. Verify: existing `test_write_forward_manifest_round_trips` still passes; new cases cover fuelled + evidence metadata without requiring schema_version bump. Serves: O-1

## Non-goals

- NR-1: No fourth conductor / bidirectional sync of contracts ⟷ FRs ⟷ WorkItems ⟷ health (harvest Option 5 rejected).
- NR-2: Do not create a second evidence ledger in startd8; do not restate or fork the Delivery Evidence Contract / dossier `delivery:` block into FLCM.
- NR-3: Do not feed `[BINDING]` prescription, draft-time `validate_implementation`, or contract confidence into delivery health.
- NR-4: Do not redefine `stages_completed` as a health surface; it remains a monotone enrichment log.
- NR-5: Do not add required schema fields or bump `schema_version` solely for this fuel; prefer existing Optional trio + optional metadata keys.
- NR-6: Element-manifest evidence kind (harvest Option 3) and dossier-shaped postmortem ledger (Option 4) are out of scope.
- NR-7: Do not require extract-time fuel in v0.3 (seed-embedded forward_manifest may still show null trio until O-4 / CRP).

## Owned fields

Only humans enter: none for the trio (machine-fuelled from env/seed/clock). Humans may still author contracts / file_specs upstream. Evidence `provenance` string is a fixed writer token, not free-form human prose.

## Contract projection

- **Backend:** startd8-python-cascade
- **Vocabulary home (cite):** `det-req-kit/SCHEMA.md` §8 (`entity` · `page` · `view` · `completeness` · `ai-assist`); FLCM field SSOT: `src/startd8/forward_manifest.py` (`ForwardManifest` ~320–348); persist: `src/startd8/contractors/prime_contractor.py` (`_write_forward_manifest`, `_forward_manifest_path`); intent evidence pattern (cite only): `ContextCore/docs/design/DELIVERY_EVIDENCE_CONTRACT.md` + `initiative_dossier.DeliveryEvidence`

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| ForwardManifest | entity | structure | Top-level FLCM; provenance trio + metadata |
| pipeline_run_id | entity | structure | Optional[str]; fuel from KAIZEN_RUN_ID / known id |
| generated_at | entity | structure | Optional[str] ISO-8601; set at persist |
| source_checksum | entity | structure | Optional[str]; copy from seed |
| metadata.persisted_file_evidence | entity | structure | Optional list; git locator + sha256 + provenance |
| _write_forward_manifest | completeness | structure | Persist fuel seam (FR-CL-1 writer) |

---

## Appendix A — Accepted (with where merged)

_(empty — pre-CRP)_

## Appendix B — Rejected (with rationale)

_(empty — pre-CRP)_

## Appendix C — Incoming review rounds

_(empty — CRP not run; v0.4 optional)_

---

*v0.3 — Reflective loop through plan → §0 → lessons (PC-4/5/9 + harvest) → principles (Context-Correctness, Mottainai, fail-honest). Ready for optional CRP. Do not invent a CRP prompt here.*
