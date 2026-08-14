# Prime Postmortem → Delivery Ledger — Requirements

**Project:** startd8-sdk (Prime Contractor)   **Criticality:** medium
**Version:** 0.3   **Date:** 2026-08-13
**Format:** det-req/0.1
**Backend:** spike-component (projection emitter module + derived artifact; not cascade entities)
**Pairs with:** `PLAN-PRIME-DELIVERY-LEDGER.md`
**Inherits standards:** det-req-kit
**Cite:** FLCM ⟷ intent-language harvest Option 4 —
`dev-os/det-req-kit/_HARVEST_2026-08-13_forward-manifest-reuse.md` §6

## 0. Planning Insights (Self-Reflective Update)

> v0.1 → v0.3 in one reflective pass. Planning against live postmortem / traceability /
> reconciler surfaces falsified several first-draft assumptions before any emitter code.

| v(n-1) Assumption | Planning Discovery | Impact |
|-------------------|--------------------|--------|
| Postmortem alone holds enough to emit `satisfies` | `requirement_mappings` live in upstream `ingestion-traceability.json` (`_build_traceability_artifact` ~2207–2320); postmortem holds `generated_files` / `target_files` / disk quality only | Emitter **requires both inputs**; discover via run-dir (same patterns as `scripts/run_prime_postmortem.py`) or explicit paths |
| Merge SHA is already on the postmortem report | `PrimePostMortemReport` has `report_id` (UUID) and writes `prime-postmortem-report.json`; **no merge/commit field** | Merge SHA is an **operator/gate input** (`--merge-sha` or resolved at a defined post-merge gate); never invent from `report_id` |
| `generated_files` can be pasted into `git:` locators | Paths are often **absolute**; postmortem already suffix-matches them against relative `target_files` for coverage | Emitter **must normalize to repo-relative** under `project_root` before forming locators |
| Emitter should embed ContextCore WorkItem runtime | Dossier `delivery:` is a **vocabulary** the reconciler already loads (`load_dossier`); overview open question answered: twins stay independently authored + cheaply reconciled | Emit a **delivery-shaped fragment** (minimal YAML with `delivery:`); do **not** invent WorkItemManager inside startd8 |
| Book A is always a Lives-bearing REQ in the same repo | Generated project vs REQ tree are often **cross-repo**; reconciler already takes `--repo` + `--req` + `--dossier` | Dogfood joins books explicitly: ledger beside `.startd8/` (or postmortem out), `--repo` = generated git root, `--req` = REQ path (may be foreign) |
| "Agree" dogfood needs Lives on day one | Lives may be absent on the driving REQ; temporary book-A = stub REQ whose FR ids = `requirement_mappings[].requirement_id` with **no** Lives → reconciler yields `fr-missing-lives` (proves book-B loadable). Real `agree` is a later fuel step | Plan iteration 2 splits "ledger loads + reconciler runs" from "Lives agree" |
| Disk-quality / FLCM `validate_implementation` could seed evidence | Harvest **category error**: draft-time validation ≠ merged-at-main delivery proof | Evidence rows **only** from post-merge content-addressed locators; never from PASS verdicts or prescription |

**Resolved open questions:**
- **OQ-1 → Backend = `spike-component`.** FRs touch emitter module + derived YAML paths, not cascade entity/page vocabulary and not a new console_scripts surface as the primary deliverable. Optional thin CLI/script is a spike file, not `python-cli-surface` overclaim.
- **OQ-2 → Artifact shape = delivery fragment.** Minimal YAML with `delivery.evidence` + `delivery.work_items` (compatible with `reconcile_lives_evidence.load_dossier`); optional `schema:` / initiative stub for human readability. Not a full four-artifact dossier.
- **OQ-3 → Hook site = sibling of `_write_outputs`, gated.** Prefer post-hoc / explicit emit at post-merge gate for v1; optional call from `_write_outputs` only when merge-sha is supplied (otherwise skip loud, write nothing pretending to be evidence).

### 0.1 Lessons-Learned Hardening (v0.3)

> Grounded against the 2026-08-13 forward-manifest harvest + twin-sync pilot (pattern_catalog
> CLI unavailable in this session; decisions keyed on `#5 single-source/no-drift`,
> `#2 fail-loud/validation-gate`, `#4 context-arrival/data-wiring`, `#10 idempotency/reuse`).

- **[Harvest §3 lacuna / claims-then-reconcile]** — startd8 reconciles plan↔tasks↔files, not FR↔commit; this REQ fills **only** the projection that makes book-B dossier-shaped so the **existing** Check half can run → FR-1, FR-6; NR-1 / NR-5.
- **[Harvest §6 category error]** — `[BINDING]` / draft `validate_implementation` / disk-quality PASS must never feed delivery health → NR-3; FR-3 Verify binds to merge commit presence.
- **[Hansei: mirror Lives parser drift]** — do not shadow-parse det-req or invent a third ledger schema; cite dossier vocabulary + reuse reconciler → FR-5, NR-4.
- **[Authored ≠ propagated]** — wait-for-driving-run / golden fixture before coding emitter+reconcile dogfood → Plan gate G0; FR-7.

### 0.2 Design-Principle Hardening (v0.3)

| Principle | Check on this draft | Disposition |
|-----------|---------------------|-------------|
| **Mottainai** | Cite dossier `delivery:` vocab + `reconcile_lives_evidence.py`; do not rebuild WorkItemManager or a second reconciler | Held — NR-2, FR-6 |
| **Accidental-Complexity** | Projection emitter only; Option 5 (live sync conductor) rejected | Held — NR-1 |
| **Genchi Genbutsu** | Locators must resolve via `git cat-file` in `--repo`; no invented SHAs | Held — FR-3, FR-4 |
| **Context-Correctness-by-Construction** | Merge-sha is required context for evidence rows; absence → skip/unknown, not silent omit-as-green | Held — FR-4 |
| **Fail-loud** (advisory half) | Enforcer = reconciler `--strict` on unresolvable/digest-mismatch; emitter fails loud on malformed inputs, prefers skip over fake locators | Named — FR-4, FR-6 |

## Overview

After a Prime Contractor run's outputs are **merged** (or at a defined post-merge gate), emit
one small **derived** artifact in initiative-dossier **delivery vocabulary**: each WorkItem ≈
a plan-ingestion `task_id`; `satisfies` comes from `ingestion-traceability.json`
`requirement_mappings`; each evidence row is `git:<merge-sha>:<repo-relative-file>` plus
content `sha256`. Then `dev-os/scripts/reconcile_lives_evidence.py` (or a thin wrapper that
only sets paths) Checks the books. This is a **projection emitter**, not a sync conductor.
Implementation of the emitter and dogfood reconcile is **gated** behind an explicit first
driving prime run / golden fixture (wait-for-driving-run acknowledged; the work is still
fully specified here).

## Objectives

- O-1: A post-merge prime run can produce a dossier-shaped delivery ledger from artifacts the chain already holds. — target: one derived YAML/JSON beside `.startd8/` or postmortem out
- O-2: The shipped twin-sync reconciler can Check that ledger against a REQ Lives surface (or an honest temporary book-A stub) without a fourth conductor. — target: `reconcile_lives_evidence.py` exit 0 dry-run (advisory statuses OK)
- O-3: Unknown merge identity or uncommitted files never become invented delivery proof. — target: skip/unknown rows, no synthetic `git:` locators

## Risks

| Type | Description | Mitigation | Priority |
|------|-------------|------------|----------|
| quality | Draft-time disk PASS treated as delivery evidence | NR-3; FR-3 only post-merge locators | high |
| quality | Cross-repo `--repo` ambiguity corrupts strict exit semantics | FR-6: require explicit `--repo` = generated project; document foreign REQ path | high |
| scope-creep | Emitter grows into live sync / Lives auto-writer | NR-1, NR-2, NR-5 | high |
| availability | No driving run ⇒ emitter untested against real shapes | Plan G0 dogfood gate before coding FR-1..FR-4 | medium |
| quality | Absolute `generated_files` → broken locators | FR-3 normalization + fail skip if not under project_root | medium |

## Profile

Declared profile: **internal**

## Functional requirements

- **FR-1 — Projection emitter.** Given a prime postmortem report, an `ingestion-traceability.json`, a merge SHA (or explicit unknown), and the generated project's git root, the system emits one dossier-shaped delivery ledger derived only from those inputs. Touches: `prime_delivery_ledger.py`, `prime-postmortem-report.json`, `ingestion-traceability.json`. Verify: given golden fixture inputs, emitter writes a YAML/JSON file whose `delivery.work_items` and `delivery.evidence` parse via the same shape `reconcile_lives_evidence.load_dossier` expects. Serves: O-1

- **FR-2 — WorkItem ≈ task, satisfies from mappings.** Each emitted work item id equals a `task_id` from mapped (non-`auto-satisfied`) `requirement_mappings` rows (or the task list reachable through those mappings); each work item's `satisfies` lists the corresponding `requirement_id`s; pipeline-innate `auto-satisfied` rows are excluded from the delivery denominator. Touches: `prime_delivery_ledger.py`, `ingestion-traceability.json`. Verify: for a fixture mapping `REQ-X → task T1`, the ledger contains work item `T1` with `satisfies` containing `REQ-X` and no work item invented for `__pipeline_artifact:` features. Serves: O-1

- **FR-3 — Content-addressed evidence only.** For each generated file that normalizes to a repo-relative path and exists as a blob at `merge-sha:path`, the emitter adds an evidence row `locator: git:<40-hex-merge-sha>:<path>` with `sha256` of that blob and binds it to the work item(s) whose features produced the file; disk-quality scores, FLCM validation, and draft-time PASS verdicts MUST NOT create evidence rows. Touches: `prime_delivery_ledger.py`, `prime-postmortem-report.json` (`generated_files` / `target_files`). Verify: fixture with known merge commit yields locators that `git cat-file` resolves in `--repo` and whose sha256 matches `hashlib.sha256(blob)`; a feature with only disk PASS and no merge blob produces **no** evidence row. Serves: O-1, O-3

- **FR-4 — Fail-loud / honest skip.** If merge SHA is missing/`unknown`, or a candidate file is not present in that commit (or cannot be normalized under project_root), the emitter MUST NOT invent a locator: it omits that evidence row and records a loud skip/unresolved note in the emit report (stderr or sidecar); malformed required inputs fail the emit invocation non-zero. Touches: `prime_delivery_ledger.py`, emit exit-class. Verify: emit with `--merge-sha unknown` (or omitted) writes a ledger with empty `delivery.evidence` (or only rows from an explicitly supplied valid sha) and non-silent skip diagnostics; inventing a fake 40-hex is a test failure. Serves: O-3

- **FR-5 — Placement without a third ledger.** The emitter writes the derived ledger next to the generated project's `.startd8/` (normative: `.startd8/delivery-ledger.yaml`) or into the postmortem `output_dir` under a fixed basename; it MUST NOT overwrite an independently authored ContextCore initiative `dossier.yaml`, and MUST NOT become a second requirement Lives store. Touches: `.startd8/delivery-ledger.yaml`, `prime_postmortem.py` (optional hook). Verify: emit against a tree that already has a ContextCore dossier leaves that dossier byte-identical; new file appears at the normative path. Serves: O-1

- **FR-6 — Reconciler Check (no conductor).** An operator can run `python3 dev-os/scripts/reconcile_lives_evidence.py --req <REQ> --dossier <emitted-ledger> --repo <generated-project-root>` (optional thin wrapper that only forwards those paths) and obtain a `dev-os.lives-evidence-reconcile/v0.1` report; startd8 MUST NOT add a live sync loop that writes FRs or health from the ledger. Touches: `reconcile_lives_evidence.py` (cite), emitted ledger. Verify: dry-run on dogfood fixture exits 0 without `--strict` when only advisory statuses appear; with matching Lives+evidence, status `agree` appears for at least one FR. Serves: O-2

- **FR-7 — Dogfood gate before emitter code.** Coding of FR-1…FR-4 (and the FR-6 dogfood run) is blocked until Plan iteration 0 records a concrete driving prime run directory **or** a checked-in golden fixture built from a real postmortem report + sibling `ingestion-traceability.json`. Touches: `PLAN-PRIME-DELIVERY-LEDGER.md` gate G0. Verify: PLAN shows G0 cleared with path + sha256 of fixture inputs before any emitter module lands on main. Serves: O-1, O-2

## Non-goals

- NR-1: Bidirectional live sync of contracts ⟷ FRs ⟷ WorkItems ⟷ health (harvest Option 5 — rejected).
- NR-2: Inventing ContextCore WorkItemManager / SpanState runtime inside startd8.
- NR-3: Treating FLCM `[BINDING]` prescription, `validate_implementation`, or postmortem disk-quality PASS as delivery evidence.
- NR-4: A third competing ledger (FLCM stays claims/prescription; Lives stays requirement attestation; emitted `delivery:` is the sole evidence book for this join).
- NR-5: Auto-writing FR `Lives:` lines or feeding delivery health from prescription.
- NR-6: Replacing or subsuming Semantic Compliance Review / SOURCE_RECONCILE (different cell: plan↔files/AST).

## Owned fields

Only humans enter: merge SHA at the post-merge gate (unless an operator-approved resolver is documented later); choice of `--req` path for Check; any initiative metadata beyond the derived `delivery:` block.

## Contract projection

- **Backend:** spike-component
- **Vocabulary home (cite):** det-req-kit `SCHEMA.md` §8 `spike-component` · delivery vocabulary cite
  `ContextCore-navigr8/docs/initiatives/internal-artifact-self-hosting/dossier.yaml` (`delivery:`) ·
  reconciler cite `dev-os/scripts/reconcile_lives_evidence.py`

| Entry (name) | Kind | Words/Structure | Notes |
|--------------|------|-----------------|-------|
| prime_delivery_ledger.py | file | structure | new emitter module under `src/startd8/contractors/` (name may shift; path is the seam) |
| prime_postmortem.py | file | structure | optional post-merge hook beside `_write_outputs`; must not invent merge-sha |
| run_prime_postmortem.py / emit script | file | structure | post-hoc discovery sibling to existing standalone runner |
| .startd8/delivery-ledger.yaml | file | structure | normative derived output basename |
| ingestion-traceability.json | file | structure | input — `requirement_mappings` |
| prime-postmortem-report.json | file | structure | input — `generated_files` / `target_files` |
| reconcile_lives_evidence.py | file | structure | Check half — cite only, do not fork |

## Open questions (remaining)

- **OQ-4:** Prefer YAML vs JSON for the emitted ledger? Reconciler loads YAML today; JSON would need a one-line loader extension or a YAML dump of the same dict — default **YAML** unless dogfood proves otherwise.
- **OQ-5:** When one file is produced by multiple tasks, bind evidence to all satisfying work items or to a single primary task? Default: bind to **all** work items whose mapped features list that file (dedupe evidence id).

## Appendix A — Accepted (with where merged)

- **A1 — Wait-for-driving-run.** Spec now; implement after G0. Merged: FR-7 + Plan G0.
- **A2 — Two books only.** Generated delivery ledger vs REQ Lives (or temporary stub). Merged: FR-5, FR-6, NR-4.
- **A3 — Overview answer.** Twin surfaces independently authored + cheaply reconciled; no fourth conductor. Merged: Overview, NR-1.

## Appendix B — Rejected (with rationale)

- **B1 — Option 5 live sync conductor.** Rejected: Accidental-Complexity + harvest verdict.
- **B2 — Evidence from disk_quality / FLCM validate_implementation.** Rejected: category error (draft ≠ merged).
- **B3 — Backend startd8-python-cascade.** Rejected: no entity/page FRs; would hide the spike/file seam (BACKEND_ROUTING anti-pattern).

## Appendix C — Incoming review rounds

*(empty — pre-CRP)*

---

*v0.3 — Reflective loop through planning + lessons + principle hardening. Ready for CRP when a driving run exists; coding gated by Plan G0.*

*G0 CLEARED 2026-08-14 — golden fixture + emitter landed (`prime_delivery_ledger.py`).*
