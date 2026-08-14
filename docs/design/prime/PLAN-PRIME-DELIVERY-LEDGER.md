# Prime Postmortem → Delivery Ledger — Implementation Plan

**Project:** startd8-sdk (Prime Contractor)  
**Version:** 0.3   **Date:** 2026-08-13  
**Requirements:** `REQ-PRIME-DELIVERY-LEDGER.md` v0.3  
**Format companion:** det-req/0.1 reflective plan (iterations acyclic; coding gated)

---

## Strategy

Emit **one derived artifact** (dossier-shaped `delivery:`) from data postmortem +
plan-ingestion already produce. Reuse `dev-os/scripts/reconcile_lives_evidence.py` as the
Check half. No sync service, no Lives auto-writer, no WorkItemManager port.

```
[G0 dogfood / golden fixture]
        ↓
[Iter 1] emitter: postmortem + traceability + merge-sha → delivery-ledger.yaml
        ↓
[Iter 2] reconciler dry-run (book A = Lives REQ or stub from requirement_ids)
        ↓
[Iter 3] docs + operator HOWTO cite
```

Dependencies are **forward-only**. Iterations 1–2 MUST NOT start until G0 is cleared.

---

## Gate G0 — First dogfood prime run / golden fixture (blocks coding of FR-1…FR-4, FR-6 dogfood)

**Exact dogfood gate (copy into Closure Ledger / PR checklist):**

> **G0 CLEAR only when all of the following are recorded in this PLAN (or a dated annex):**
>
> 1. **Driving source** — either  
>    (a) a real post-merge prime run directory with readable  
>    `prime-postmortem-report.json` **and** sibling/upstream `ingestion-traceability.json`,  
>    **or**  
>    (b) a checked-in golden fixture under e.g.  
>    `startd8-sdk/tests/fixtures/prime_delivery_ledger/` built by copying those two
>    artifacts from a real run (scrub secrets; keep `generated_files` / `requirement_mappings` shapes).
> 2. **Paths + content identity** — absolute or repo-relative paths logged here, plus
>    `sha256` of both input files (and of the merge commit tip if known).
> 3. **Merge identity stance** — either a real `40-hex` merge SHA for the generated
>    project repo, or an explicit `unknown` used only to prove FR-4 skip behavior
>    (skip-path dogfood does **not** unlock FR-3 agree plates).
> 4. **Book-A stance** — path to a Lives-bearing REQ **or** intent to use a temporary
>    stub REQ whose FR ids = mapped `requirement_id`s (no Lives → expect
>    `fr-missing-lives`).
>
> Until G0 is cleared, **do not** land `prime_delivery_ledger.py` on main. Spec-only PRs
> (this REQ/PLAN) are allowed.

**G0 status:** ✅ **CLEAR** (2026-08-14) — golden fixture checked in.  
**Annex:** `tests/fixtures/prime_delivery_ledger/README.md`

| Field | Value |
|-------|-------|
| Driving source | (b) golden fixture from `strtd8-v2-cascade` `latest/plan-ingestion` (run-010 lineage) |
| Paths | `tests/fixtures/prime_delivery_ledger/{prime-postmortem-report,ingestion-traceability}.json` + `generated/` |
| sha256 (PM) | `dfbd64d8b889d25da92d3128e912be4d63e7442610c3df20698f186c2f47b40d` |
| sha256 (TR) | `c1cc84dbfaee059eea0dec21c59d0260a01525b81545d0df382d9251b5d9cd64` |
| Merge stance | Test-minted 40-hex from fixture `generated/` (FR-3); `unknown` plate for FR-4 |
| Book-A stance | Ephemeral stub REQ in unit test → `fr-missing-lives` |


---

## Iteration 0 — Select dogfood run / build golden fixture

**Goal:** Clear G0.  
**Reqs:** FR-7  
**Deps:** none  
**Work:**

1. Inventory candidate run dirs (cap-dev-pipe pipeline-output / local prime outs) that have
   both postmortem report and `ingestion-traceability.json`.
2. Prefer a run whose `generated_files` are committed on a known merge SHA in a local git
   clone (enables FR-3); if none, accept `unknown` merge for FR-4-only fixture **and**
   schedule a second fixture when a merge exists.
3. Check in golden copies (or document external paths + shas if proprietary).
4. Mark G0 CLEAR in this file.

**Exit:** G0 checklist above complete.

---

## Iteration 1 — Emitter (projection only)

**Goal:** FR-1…FR-5  
**Deps:** G0 CLEAR  
**Work:**

1. Add `src/startd8/contractors/prime_delivery_ledger.py` (name flexible):
   - Inputs: postmortem report dict/path, traceability dict/path, `project_root`, `merge_sha | None`.
   - Build `work_items` from mapped `requirement_mappings` (exclude `auto-satisfied`).
   - Normalize `generated_files` → repo-relative; resolve blob at `merge_sha:path`; compute sha256.
   - Emit YAML with `delivery: { evidence: [...], work_items: [...] }` compatible with
     `load_dossier` (cite ContextCore dossier `delivery:` vocabulary — do not fork schema docs).
2. Fail-loud: missing required files → non-zero; unknown merge / missing blob → skip + diagnostics (FR-4).
3. Write normative output `.startd8/delivery-ledger.yaml` (or postmortem `output_dir` basename);
   never overwrite a ContextCore `dossier.yaml`.
4. Optional: call from `PrimePostMortemEvaluator._write_outputs` **only** when merge-sha
   provided in result/env; default path remains standalone/post-hoc script beside
   `scripts/run_prime_postmortem.py`.
5. Unit tests against G0 golden fixture (no network; local git fixture ok).

**Exit:** Fixture emit parses; FR-4 skip plate green; no invented locators.

---

## Iteration 2 — Reconciler dry-run

**Goal:** FR-6  
**Deps:** Iteration 1  
**Work:**

1. Run:
   ```bash
   python3 /Users/neilyashinsky/Documents/dev/dev-os/scripts/reconcile_lives_evidence.py \
     --req <book-A> \
     --dossier <generated-project>/.startd8/delivery-ledger.yaml \
     --repo <generated-project-root> \
     --out /tmp/prime-delivery-reconcile.json
   ```
2. If Lives absent: generate temporary stub REQ (FR ids from mappings, no Lives) → expect
   `fr-missing-lives` in denominator; proves book-B loadable. Do **not** treat that as agree.
3. Optional thin wrapper in startd8 or dev-os that only forwards `--req/--dossier/--repo`
   (no new reconcile logic — Mottainai).
4. If a Lives-bearing dogfood REQ exists (or is fueled in this iteration), assert at least
   one `agree` under matching locator.

**Exit:** Report schema `dev-os.lives-evidence-reconcile/v0.1` written; statuses understood;
`--strict` behavior documented for unresolvable/digest-mismatch.

---

## Iteration 3 — Docs + operator HOWTO cite

**Goal:** Discoverability without restating reconciler  
**Deps:** Iteration 2  
**Work:**

1. Short HOWTO section (prime docs or harvest annex): post-merge gate → emit → reconcile
   command with cross-repo path example.
2. Cite REQ/PLAN from harvest Option 4 (already footnoted at spec time).
3. Explicit non-goals reminder: no health-from-prescription; no Lives auto-write.

**Exit:** Operator can find the three paths (emit, ledger, reconcile) from one cite.

---

## Dependency graph (acyclic)

```
G0 (Iter 0) ──► Iter 1 (emitter) ──► Iter 2 (reconcile dry-run) ──► Iter 3 (docs)
```

No back-edges. Iter 3 must not invent emitter behavior.

---

## Mapping — FR → iteration

| FR | Iteration | Notes |
|----|-----------|-------|
| FR-7 | 0 / G0 | Gate only |
| FR-1, FR-2, FR-3, FR-4, FR-5 | 1 | Emitter |
| FR-6 | 2 | Check half reuse |
| (operator surface) | 3 | Cite-only HOWTO |

---

## Planning discoveries (fed §0 of REQ)

1. Traceability is upstream of postmortem — two inputs required.  
2. Merge SHA not on report — operator/gate input.  
3. Absolute `generated_files` need normalization.  
4. Delivery fragment sufficient for `load_dossier`.  
5. Cross-repo join via existing `--repo` + foreign `--req`.  
6. Temporary book-A stub proves load without false agree.  
7. Category error: never feed draft validation into evidence.

---

## Non-goals (plan-side)

- Do not implement Option 5 sync.  
- Do not extend reconciler schema unless YAML-only load blocks JSON (prefer emit YAML).  
- Do not block on ContextCore WorkItem SpanState — authored `satisfies` on the emitted
  fragment is enough for the Check half.

---

*v0.3 — Aligned with REQ-PRIME-DELIVERY-LEDGER.md v0.3. Coding blocked on G0.*

*G0 CLEAR 2026-08-14. Iter 1–3 implemented: emitter + reconciler dogfood test + HOWTO.*
