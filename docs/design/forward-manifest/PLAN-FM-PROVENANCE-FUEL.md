# ForwardManifest Provenance Fuel — Implementation Plan

**Project:** startd8-sdk (Forward-Looking Code Manifest)   **Criticality:** medium
**Version:** 0.3 (aligned with REQ reflective update)   **Date:** 2026-08-13
**Pairs with:** `docs/design/forward-manifest/REQ-FM-PROVENANCE-FUEL.md`
**Format companion:** det-req/0.1 (iterations / acyclic deps)

## 0. Planning Insights (mirror of REQ §0)

Planning falsified “write-only bug”: extract constructs an unfueled `ForwardManifest`; persist dumps it. Seed already owns `source_checksum`. `KAIZEN_RUN_ID` + generation-manifest `generated_at` are the twin precedents in the same contractor. Evidence is optional metadata citing the intent locator pattern — not a new ledger.

| Discovery | Plan consequence |
|-----------|------------------|
| Nulls at extract + persist dump | Iter 1: fuel helper called from `_write_forward_manifest` only (v0.3 scope) |
| Seed checksum already loaded for corpus path | Iter 1: reuse `_seed_path` JSON read pattern (~4045–4054), small shared helper |
| Specimen has directory `file_specs` keys | Iter 2: file-existence + `git cat-file` gate before evidence rows |
| Existing persistence tests use bare `__new__` contractor | Extend `test_forward_manifest_persistence.py`; keep heavy `__init__` out |
| Claims gates need drift plates (harvest Hansei) | Iter 3: null-specimen fixture regression + committed-file evidence plate |

## Goal

Implement REQ-FM-PROVENANCE-FUEL FRs so FR-CL-1’s on-disk `forward-manifest.json` carries a fuelled provenance trio when known, fail-honest nulls when not, and optional `metadata.persisted_file_evidence` for committed generated files — without schema bumps or a second ledger.

## Non-goals (plan-enforced)

- No extract-time fuel in this plan (REQ O-4 / NR-7).
- No dossier emitter, no health mapping, no `stages_completed` semantics change.
- No copy-paste of Delivery Evidence Contract prose into startd8.

## Dependencies (acyclic)

```
Iter 0 (fixture + helper sketch)
  → Iter 1 (trio fuel at persist)     [FR-1, FR-2, FR-3, FR-6]
  → Iter 2 (optional file evidence)   [FR-4]
  → Iter 3 (unknown helper + specimen regression) [FR-5]
  → Iter 4 (docs cross-cite only)
```

No cycle: 2 depends on 1’s write hook; 3 depends on 1–2 behavior being testable; 4 is documentation only.

## Iterations

### Iter 0 — Ground fixtures (no product behavior change)

**Touches:**
- `tests/unit/contractors/fixtures/portal_v2_forward_manifest_null_provenance.json` (new) — minimal scrubbed copy of the wild specimen’s provenance header (`pipeline_run_id`/`generated_at`/`source_checksum` null, `metadata: {}`, one directory-like `file_specs` key optional for skip coverage).
- Confirm read of `tests/unit/contractors/test_forward_manifest_persistence.py`.

**Verify:**
```bash
python -c "from startd8.forward_manifest import ForwardManifest; \
  ForwardManifest.model_validate_json(open('tests/unit/contractors/fixtures/portal_v2_forward_manifest_null_provenance.json').read()); print('ok')"
```

**Deps:** none.

---

### Iter 1 — Fuel provenance trio at `_write_forward_manifest`

**Touches:**
- `src/startd8/contractors/prime_contractor.py`
  - Add a small private helper, e.g. `_fuel_forward_manifest_provenance(self) -> None`, called at the start of `_write_forward_manifest` after the None-guard (~2290–2293).
  - Behavior:
    1. If `generated_at` is null/empty → set `datetime.now(timezone.utc).isoformat()` (match `_write_generation_manifest` ~2243).
    2. If `pipeline_run_id` is null/empty → set from `os.environ.get("KAIZEN_RUN_ID")` when non-empty; else leave null (FR-3). Do **not** invent `run-{time}` here (that pattern at ~5882 is for other metrics — using it would manufacture a false identity).
    3. If `source_checksum` is null/empty → read seed JSON via `getattr(self, "_seed_path", None)` the same way as ~4045–4054; copy string `source_checksum` if present; else leave null.
  - Mutate `self._forward_manifest` fields in place (model is not frozen), then `model_dump_json` as today.
- Prefer **not** changing `forward_manifest.py` schema.

**Verify:**
```bash
cd /Users/neilyashinsky/Documents/dev/startd8-sdk
python -m pytest tests/unit/contractors/test_forward_manifest_persistence.py -q
# New tests (add in this iter):
# - test_write_fuels_generated_at_and_run_id_from_env
# - test_write_copies_source_checksum_from_seed
# - test_write_leaves_run_id_and_checksum_null_when_unknown
```

**Deps:** Iter 0 (fixture available for later; not required to compile Iter 1).

---

### Iter 2 — Optional `metadata.persisted_file_evidence`

**Touches:**
- `src/startd8/contractors/prime_contractor.py` (same helper or `_collect_persisted_file_evidence`)
  - Inputs: project git root (`self.project_root`), candidate paths = keys of `file_specs` that are existing **files** (skip dirs / trailing-slash keys / missing paths).
  - For each candidate: resolve `HEAD` (or current commit) via `git rev-parse HEAD`; `git cat-file blob <sha>:<path>`; sha256 hex of bytes; append `{path, locator: f"git:{sha}:{path}", sha256, provenance: "prime-contractor-persist"}`.
  - On any git failure / uncommitted path (blob missing): skip that path (no partial fake digest).
  - Set `metadata["persisted_file_evidence"]` only when the list is non-empty **or** explicitly set `[]` when the feature flag/path list was considered and empty — prefer omit-if-empty to avoid noisy metadata (document choice in code comment; REQ allows either).
- Cite pattern only in a one-line comment pointing at Delivery Evidence Contract / dossier `DeliveryEvidence` — do not import ContextCore.

**Verify:**
```bash
python -m pytest tests/unit/contractors/test_forward_manifest_persistence.py -q \
  -k "evidence or provenance"
# Plates:
# - temp git repo + committed file → one evidence row, digest matches hashlib.sha256
# - uncommitted file → no row
# - directory key in file_specs → no row
```

**Deps:** Iter 1 (write hook exists).

---

### Iter 3 — Fail-honest unknown surface + specimen regression

**Touches:**
- `tests/unit/contractors/test_forward_manifest_persistence.py`
  - Load Iter 0 fixture; assert trio null ⇒ helper `provenance_status(manifest) -> "unknown"|"partial"|"complete"` (test-local or tiny function next to writer — **not** a health enum; names are provenance completeness only).
  - After fuel with env+seed: `"complete"`; with only `generated_at`: `"partial"`.
- Keep FR-5 semantics out of SCR/postmortem health.

**Verify:**
```bash
python -m pytest tests/unit/contractors/test_forward_manifest_persistence.py -q
# Explicit: test_null_specimen_is_unknown_provenance
# Explicit: test_fuelled_manifest_not_unknown
```

**Deps:** Iter 1; Iter 2 optional for evidence plates but trio tests independent.

---

### Iter 4 — Cross-cites only (docs)

**Touches:**
- `docs/design/forward-manifest/04_FORWARD_MANIFEST.md` — short pointer under schema/provenance that persist fuels Optional trio (cite REQ-FM-PROVENANCE-FUEL); do **not** restate intent ledger.
- Optional one-line in harvest note already in dev-os (out of startd8) — skip unless asked.

**Verify:** doc link resolves; no schema_version bump.

**Deps:** Iter 1 complete (behavior exists before documenting).

## File touch summary

| File | Iters | Role |
|------|-------|------|
| `src/startd8/contractors/prime_contractor.py` | 1–2 | Fuel + optional evidence at persist |
| `tests/unit/contractors/test_forward_manifest_persistence.py` | 1–3 | Unit + regression |
| `tests/unit/contractors/fixtures/portal_v2_forward_manifest_null_provenance.json` | 0, 3 | Null specimen plate |
| `docs/design/forward-manifest/04_FORWARD_MANIFEST.md` | 4 | Cite REQ (Mottainai) |
| `src/startd8/forward_manifest.py` | — | **No change expected** (fields already Optional) |

## Verification commands (full gate)

```bash
cd /Users/neilyashinsky/Documents/dev/startd8-sdk
python -m pytest tests/unit/contractors/test_forward_manifest_persistence.py \
  tests/unit/semantic_compliance/test_forward_manifest_loading.py -q
```

Optional manual: compare a re-run persist against the portal-v2 specimen shape — trio fuelled when env/seed present; metadata evidence only after commit.

## Open questions left for CRP (do not invent prompt)

1. **OQ-CRP-1 — Extract-time fuel?** Should plan-ingestion also stamp the trio into seed-embedded `forward_manifest` so in-memory / seed consumers see fuel before Prime persist (REQ O-4)?
2. **OQ-CRP-2 — Run-id precedence?** Strict `KAIZEN_RUN_ID` only vs allow seed/`pipeline_run_id` already set by upstream to win (current plan: do not overwrite non-empty).
3. **OQ-CRP-3 — Evidence candidate set?** All file-like `file_specs` keys vs only files written this run (integration_history / target_files intersection)?
4. **OQ-CRP-4 — Cross-repo locators?** Harvest watch-item: `git:` is repo-relative; if Prime `project_root` ≠ evidence repo, skip vs `unresolvable` — confirm degrade rule.
5. **OQ-CRP-5 — Omit vs empty list** for `persisted_file_evidence` when no committed files? (**Resolved in impl:** omit-if-empty.)

## Risks → plan mitigations

| Risk | Mitigation |
|------|------------|
| Inventing run ids | Forbids `run-{time}` for `pipeline_run_id` |
| Second ledger | Metadata-only; no WorkItem/satisfies |
| Directory / escape `file_specs` | Skip non-files; `relative_to(root)` gate (HTH) |
| Silent success on null | `provenance_completeness` + persist info log |

## HTH harvest (2026-08-13, post-harden)

**Extracted standard:** *Optional schema fields that ship null in the wild are fueled at the persist seam from context the run already has; unknown stays null (detectable); optional content-addressed metadata cites an external evidence grammar without becoming a second ledger; completeness is logged as provenance, never mapped to delivery health.*

**Dormant inventory (grep-grounded):**

| Path | State |
|---|---|
| `persisted_file_evidence` metadata | written when committed files exist; **no** SCR/postmortem consumer yet |
| `provenance_completeness` | wired to persist **info** log + unit tests; no operator CLI/`--as-json` surface |
| Seed-embedded `forward_manifest` trio | still often null until extract-time fuel (O-4 / OQ-CRP-1) |

**Enhancement backlog (CEP light — surface is shipped; rows only):**

| # | Size | Row |
|---|---|---|
| B1 | S | Postmortem/SCR read `persisted_file_evidence` as advisory corroboration (not health) |
| B2 | M | Extract-time fuel (O-4) so seed consumers see trio before Prime |
| B3 | S | Restrict evidence candidates to this-run generated files (OQ-CRP-3) |
| B4 | XS | Operator one-liner / docs recipe: `jq` completeness of `.startd8/forward-manifest.json` |

**Bus:** `no bus peer` — `bus.sh` absent in cursor-loops queue template; Yokoten is the harvest §6 / Option 3–4 REQs already citing this pattern.

---

*v0.3 — Plan stress-tested REQ; iterations acyclic; implemented + HTH-hardened 2026-08-13.*
