# Digital Project Workbook — Project-Start Generation Plan

**Version:** 1.1 (post-CRP R1 — tracks requirements v0.4)
**Date:** 2026-07-08
**Requirements:** `WORKBOOK_PROJECT_START_REQUIREMENTS.md`

The net-new is small: the generator, CLI, and content already exist. This plan wires generation into the
project-start flow, factors the shared logic to prevent drift, and isolates the toolchain coupling.

---

## Milestones

### M1 — Factor the shared generate(+provision) helper (FR-1, FR-10)
- Extract the state→spec→workflow steps currently inline in `kickoff_portal` (`cli_concierge.py:983-1025`)
  into one helper, e.g. `kickoff_experience/portal_build.py: build_and_maybe_provision(project_root,
  project, *, out_dir, provision_url=None, session=None) -> PortalResult`.
- `PortalResult`: `{json_path, provisioned_url|None, uid, summary, skipped_reason|None}`.
- Re-point `kickoff portal` at the helper (behavior byte-identical — a pure refactor; guard with a golden
  on the produced JSON path + UID).
- **Verify:** existing `kickoff portal` output unchanged (same UID, same JSON); toolchain-present path. The
  golden MUST also pin the **provision decision** — `provisioned_url` set iff `provision_url` given, else
  `None` — with a **no-network assertion** (mock the provision path; assert not called when `provision_url
  is None`). *(CRP R1-S1.)*

### M2 — Toolchain degradation, absent AND broken (FR-6)
- In the helper, detect the jsonnet toolchain up front (reuse `dashboard_creator` discovery — binary
  `jsonnet` via `shutil.which`, else `gojsonnet` import). If **absent**, return
  `PortalResult(skipped_reason="no jsonnet toolchain")` instead of raising.
- **Present-but-broken** (compile non-zero/import error/timeout/OOM): catch and return
  `PortalResult(skipped_reason="generation failed: <reason>")` — never a stack trace *(CRP R1-F2)*.
- **Exit-code contract (resolves the v0.3 "TBD" — CRP R1-S2):** **FR-7 wins uniformly** — a generation OR
  provision failure is **non-fatal**; `kickoff portal`'s exit reflects only whether the *requested*
  artifact could be produced… but for the `instantiate` path (M3) the exit code is always the write
  result's. A future opt-in `--strict-portal` MAY make portal failure non-zero; **not** default.
- **Verify:** monkeypatch toolchain absent → skipped, no exception; monkeypatch `.run()` to raise
  mid-compile → skipped with a labelled reason, no traceback; present → generates.

### M3 — Wire into `instantiate` (FR-2, FR-3, FR-7)
- Add `--portal/--no-portal` (default **ON**, OQ-4) and `--provision <url>` to `concierge_instantiate`
  (`cli_concierge.py:321`).
- **Isolation invariant (CRP R1-S3/R1-F1):** call the M1 helper **strictly after** `apply_write_plan`
  returns `res.ok` (`:377`), never concurrently; the helper writes ONLY to `.startd8/dashboards/`, never
  into the kickoff-package tree. Wrap in try/except: any error → warning, exit code unchanged (FR-7).
  Preview and `--check` paths never call it (FR-2).
- Human output (CRP R1-S9): success → `Workbook: <json_path>` (+ URL if provisioned); `--no-portal` →
  `Workbook: skipped (--no-portal)`; **preview prints nothing** about the Workbook.
- **Verify:** preview writes nothing + no dashboard + no Workbook line; `--apply` generates to
  `.startd8/dashboards/`; **fault-injection** (kill mid-generation) → kickoff YAMLs byte-identical + exit
  code = the write result's.

### M3.5 — Slug→UID 1:1 + rename (FR-5; CRP R1-S4/R1-F6/R1-F4)
- Pin/name the slug function (add to the Reference Audit). Detect two distinct projects slugging to one
  UID → **error, not silent clobber**. Define rename behavior (re-point vs orphan-warning). Reserve the
  literal `index` slug so no project collides with the portfolio-index UID.
- **Verify:** two names slugifying identically → collision error (or distinct UIDs); rename → defined
  behavior (no silently-orphaned duplicate the index lists); a project named "Index" → not `…-index`.

### M4 — Portfolio index (link-index) (FR-11)
- **Gate (OQ-6, resolved NO):** `dashlist` is **absent** from `PanelType` (`models.py:16-39`) and the
  mixin. Add a `dashlist` `PanelType` + a `panels.dashlist(...)` mixin constructor (small, deterministic)
  — the one explicit NR-5 exception.
- Build `build_workbook_index_spec() -> DashboardSpec` (UID `cc-portal-kickoff-index`, title `Digital
  Project Workbooks — Index`, one `dashlist` panel filtered to tag `workbook`, with the folder-scope per
  FR-11). Deterministic, `$0`.
- Expose it (OQ-7 — propose `startd8 kickoff portal --index`, idempotent upsert). **Stricter provision
  guard (NR-6 / CRP R1-S8):** `--index --provision` to a non-loopback URL requires a confirmation/allowlist
  flag; the auto-upsert option (if chosen) never auto-provisions.
- **Verify:** empty-portfolio (zero Workbooks) → index compiles + renders clean empty `dashlist`, not an
  error (CRP R1-S5); folder-scope assertion; re-run upserts the same UID; ≥2 Workbooks → both listed.

### M5 — Tests + docs
- Unit: helper (absent/broken/present toolchain, provision on/off + no-network, idempotent UID);
  instantiate wiring (preview-skips, apply-generates, error-non-fatal, `--no-portal` skips, fault-injection
  isolation); slug collision/rename/reserved-`index`; index spec (UID, dashlist tag, empty-portfolio).
- Update the kickoff docs + `WORKBOOK_PANEL_NEXT_STEPS.md` cross-refs.
- **Verify:** full kickoff_experience + dashboard_creator suites green.

---

## Design notes / risks

- **Toolchain coupling (the central tension, OQ-4).** `instantiate` is today pure/`$0`/toolchain-free.
  M2+M3 keep the coupling *non-fatal and isolated* — generation runs only after the writes, in a
  try/except, and degrades to a printed nudge. The file-scaffold contract is unchanged.
- **Idempotency (FR-5)** is already provided by the workflow's `overwrite=True` upsert + the stable UID;
  M1 must not regress it.
- **No new provisioning path** — reuse `DashboardCreatorWorkflow` provision config; NR-4 forbids auto-push,
  so provision is reachable only via an explicit `--provision <url>`.
- **Refactor safety (M1)** — the highest-risk step is the pure refactor of the portal command body; a JSON
  golden on the produced dashboard (sorted keys) pins byte-equivalence.
- **Observability of the degrade path (CRP R1-S6).** FR-6/FR-7 skip/failure messages MUST go to the user
  (stdout) **AND** be logged via `get_logger` (Loki visibility) — never print-only — so a degraded
  instantiate is observable after the fact (SDK convention: no bare `print`/`logging.getLogger`).
- **One message formatter (CRP R1-S7).** Route all skip/degrade/failure rendering through a single
  formatter fed by `PortalResult.skipped_reason`, so `kickoff portal`, `instantiate --portal`, and
  `--index` emit byte-identical messages — extends the FR-10 anti-drift guarantee from generation to
  *messaging*.

---

## Traceability

| FR | Milestone |
|---|---|
| FR-1, FR-10 | M1 |
| FR-6 | M2 (absent + broken) |
| FR-2, FR-3, FR-7 | M3 (isolation invariants + fault-injection) |
| FR-5 | M3.5 (slug 1:1 / rename / reserved-`index`) |
| FR-11, NR-6 | M4 (dashlist gate + index provision guard) |
| FR-4 | M4/M5 (empty-state AC golden) |
| FR-8 | this doc + requirements (cite owner doc) |
| FR-9 | deferred (not in this plan) |

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | Golden pins the provision decision + no-network assertion | CRP R1 | M1 Verify | 2026-07-08 |
| R1-S2 | Resolve the exit-code contract (FR-7 wins; optional `--strict-portal`) | CRP R1 | M2 exit-code bullet | 2026-07-08 |
| R1-S3 | M3 isolation invariant (after `res.ok`; writes only `.startd8/dashboards/`) | CRP R1 | M3 isolation bullet + fault-injection Verify | 2026-07-08 |
| R1-S4 | Slug collision + rename milestone task | CRP R1 | New **M3.5** | 2026-07-08 |
| R1-S5 | M4 empty-portfolio + folder-scope Verify | CRP R1 | M4 Verify | 2026-07-08 |
| R1-S6 | Degrade messages via `get_logger` (Loki), not print-only | CRP R1 | Design notes (observability) | 2026-07-08 |
| R1-S7 | One message formatter fed by `PortalResult.skipped_reason` | CRP R1 | Design notes (anti-drift messaging) | 2026-07-08 |
| R1-S8 | Stricter guard for index provisioning; OQ-7 auto never provisions | CRP R1 | M4 provision-guard bullet (NR-6) | 2026-07-08 |
| R1-S9 | Define `--no-portal` + preview output | CRP R1 | M3 human-output bullet | 2026-07-08 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none — all 9 S-suggestions accepted) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-08

- **Reviewer**: claude-opus-4-8 (1M context)
- **Date**: 2026-07-08 20:30:00 UTC
- **Scope**: Plan review (milestones M1–M5, design notes/risks, traceability), weighted to the sponsor focus asks (toolchain coupling isolation, FR-11 dashlist gate, empty-skeleton default-ON, idempotency/UID, provisioning blast-radius). Settled owner-doc items treated as fixed context.

##### Executive summary (top risks / opportunities / gaps)

- M1's "pure refactor" pins byte-equivalence with a JSON golden on the produced dashboard, but does NOT pin the *provision* side-effect of `PortalResult` — a refactor could silently change provisioning behavior and pass the golden.
- M2 explicitly leaves the exit-code contract "TBD in CRP" for the case where the user *asked* to provision and it couldn't — this is an open, load-bearing decision, not a detail.
- M3 wires generation into the `--apply` success path but the plan does not state generation runs strictly after the write *returns* (durably), leaving the FR-7 isolation invariant unpinned in the plan (mirrors requirements R1-F1).
- M4 gates FR-11 on adding a `dashlist` PanelType + mixin constructor but has no test that the *empty portfolio* (zero provisioned Workbooks) renders cleanly, and no folder-scoping assertion.
- Slug→UID collision and project-rename orphaning (requirements R1-F6) are absent from every milestone and from the M5 test list — an untested clobber path.
- The plan has no explicit rollback/verify step for a *partial* provision (JSON written, provision to shared instance half-applied), and no Ops note on where the skip/failure nudge is logged vs printed.
- Opportunity (low-hanging): M1's `PortalResult.skipped_reason` field already carries structured skip/degrade state — the plan should route it through a single formatter so `portal`, `instantiate`, and `--index` render identical skip/failure messages (anti-drift, ~free given FR-10).

##### Numbered suggestions

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Validation | high | M1's golden pins the JSON path + UID but MUST also pin the *provision decision* of `PortalResult` (provisioned_url set iff provision_url given; None otherwise). Add an assertion that with `provision_url=None` the refactor performs no network call. | The refactor extracts state→spec→workflow *and* the provision branch; a JSON-only golden cannot catch a regression that provisions when it shouldn't (or vice-versa) — the highest-blast-radius refactor bug. | M1 (Verify bullet) | Golden + a no-network assertion (mock the provision path, assert not called when `provision_url is None`). |
| R1-S2 | Risks | high | M2/M3 MUST resolve the exit-code contract the plan flags as "TBD in CRP": define what happens when the user explicitly passed `--provision` and provisioning failed. Recommend: FR-7 wins uniformly (provision failure is non-fatal to instantiate, exit code = write result), and the failure is surfaced as a clearly-flagged warning + non-zero *only* if a future `--strict-portal` opt-in is set. | The plan leaves a load-bearing exit-code decision open; leaving it to implementation risks the exit-code leak the focus file asks about (Ask 1). | M2 (skip-note bullet) / M3 (try/except bullet) | Test matrix: `--provision <bad-url>` with and without a strict flag → assert exit code equals the write result unless strict is set. |
| R1-S3 | Risks | high | M3 MUST state that the M1 helper is invoked strictly AFTER `apply_write_plan` returns `res.ok` (not concurrently) and that the helper writes ONLY to `.startd8/dashboards/`, never into the kickoff-package directory. Add this as an explicit isolation invariant, not just "in the success path." | Mirrors requirements R1-F1: "after the writes" in prose is weaker than an invariant a fault-injection test can pin; a helper that touches the source-of-record tree could corrupt it on a mid-generation crash. | M3 (Verify bullet) / Design notes | Fault-injection: kill mid-generation; assert kickoff YAMLs byte-identical + exit code unchanged. |
| R1-S4 | Data | high | Add a milestone task (M3 or M4) covering slug→UID collision + project rename: detect two distinct projects slugging to one UID (error, not silent clobber) and define rename behavior (re-point vs orphan). Add both to the M5 test list. | Mirrors requirements R1-F6; FR-5 "idempotent upsert" is only safe once slug→UID is 1:1 and rename-aware, but no milestone touches it — a silent-clobber path ships untested. | M3/M4 (new task); M5 (unit list) | Unit: two names slugifying identically → collision error or distinct UIDs; rename → defined UID behavior. |
| R1-S5 | Validation | medium | M4's Verify list MUST add an *empty-portfolio* case: with ZERO provisioned Workbooks the index still compiles and renders cleanly (empty dashlist, not an error), and a folder-scoping assertion (index sees Workbooks in the expected folder). | M4 verifies the ≥2-Workbook case but not the day-0 empty case (the index is generated before any project exists) nor the folder scope the "self-updating" claim depends on (requirements R1-F3). | M4 (Verify bullet) | Compile the index spec with no provisioned boards → assert clean empty render; provision into a folder → assert visibility per documented scope. |
| R1-S6 | Ops | medium | Add a design-notes/M5 item: define WHERE the FR-6/FR-7 skip and failure messages go — printed to the user (stdout) AND logged via `get_logger` (Loki visibility), not print-only, so a degraded instantiate is observable after the fact. | The plan's degrade path is "printed nudge" only; a print-only failure is invisible to observability and to CI logs, and the SDK convention requires `get_logger` (not bare print/logging). | Design notes / M5 | Assert the degrade path emits a structured log record (captured via caplog) in addition to the printed nudge. |
| R1-S7 | Architecture | low | Route all skip/degrade/failure rendering through ONE formatter fed by `PortalResult.skipped_reason` so `kickoff portal`, `instantiate --portal`, and `--index` produce byte-identical messages — extending the FR-10 anti-drift guarantee from generation to *messaging*. | FR-10 factors the generation helper but not its human-output; three call sites can still drift in what they print on skip/failure. Low effort given `PortalResult` already carries the reason. | M1 (`PortalResult`) / M3 | Snapshot the rendered message for present/absent/failed across all three entry points; assert identical. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Security | medium | Add a plan task to give index provisioning (`--index --provision`) a stricter guard than per-project provisioning (confirmation or allowlist), and pin OQ-7 so the "auto-upsert index on any provision" option, if chosen, NEVER auto-provisions to a shared instance. | Mirrors requirements R1-F8; the index is a global singleton with portfolio-wide blast radius, and OQ-7's auto option could silently couple it to every provision. | M4 / Design notes (resolve with OQ-7) | Assert index `--provision` to a non-loopback URL requires the guard; assert OQ-7 auto path never provisions. |
| R1-S9 | Interfaces | low | M3's human-output ("Workbook: <json_path>" / URL / skip) SHOULD define the `--no-portal` output line and confirm preview (`instantiate` sans `--apply`) prints nothing about the Workbook (matching FR-2's side-effect-free contract). | The plan lists the success/skip output but not the `--no-portal` and preview cases (requirements R1-F5); silent-vs-noted behavior is currently ambiguous. | M3 (output bullet) | Assert `--no-portal` prints the defined skip line; assert preview prints no Workbook line and creates no file. |

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement FR/NR to the plan milestone(s) that address it and rates coverage. Anchors: FRs from `WORKBOOK_PROJECT_START_REQUIREMENTS.md` §2; NRs §3; OQs §4.

| Requirement | Plan Milestone(s) | Coverage | Gaps |
|---|---|---|---|
| FR-1 (reuse, don't rebuild) | M1 | Full | Helper reuses `build_kickoff_portal_spec()` → `DashboardCreatorWorkflow().run()` verbatim. |
| FR-2 (generate at project start, `--portal/--no-portal`, preview side-effect-free) | M3 | Partial | `--no-portal` output contract undefined (R1-S9/R1-F5); preview no-op asserted but not the `--no-portal` message. |
| FR-3 (provision opt-in + explicit `--provision`) | M3 (via M1 helper) | Partial | Provision *decision* not pinned by M1's golden (R1-S1); explicit-provision-failure exit-code TBD (R1-S2). |
| FR-4 (skeleton-at-start renders cleanly empty) | M3 / M4 | Partial | FR-4 asserts "already true" by citation; no owned smoke check that the empty board compiles cleanly (R1-F9). |
| FR-5 (idempotent upsert, stable UID) | M1 / M3 | Partial | Upsert covered; slug→UID collision + rename orphaning untested and unspecified (R1-S4 / R1-F6). |
| FR-6 (graceful toolchain degradation — absent) | M2 | Partial | Absent case covered; present-but-broken toolchain not distinguished (R1-F2); degrade log destination undefined (R1-S6). |
| FR-7 (non-fatal isolation, exit code = write result) | M2 / M3 | Partial | Isolation-ordering + no-shared-write invariant not pinned (R1-S3 / R1-F1); explicit-provision-failure exit code TBD (R1-S2). |
| FR-8 (single-source vocabulary — cite owner doc) | Traceability (cites owner doc) | Full | Plan defers content/panels/live-data to owner doc as required. |
| FR-9 (refresh on confirm — DEFERRED) | Traceability (deferred) | Full | Correctly out of scope; no plan action needed. |
| FR-10 (shared generation helper, anti-drift) | M1 | Partial | Generation factored; human-output/messaging not factored — can still drift across entry points (R1-S7). |
| FR-11 (portfolio link-index, `dashlist`, self-updating) | M4 (gated on OQ-6) | Partial | dashlist PanelType + mixin gated correctly; empty-portfolio render, folder scoping, tag-invariant, and `index`-slug collision unaddressed (R1-S5 / R1-F3 / R1-F4 / R1-F7). |
| NR-1 (no live metrics/burndown) | M4 / Design notes | Full | Plan keeps FR-11 as link-index only; no metric aggregation. |
| NR-2 (index is link-index, not data-aggregating) | M4 | Full | dashlist links only; no per-project data centralized. |
| NR-3 (no writes from dashboard) | (implicit — read-only surface) | Full | No milestone adds write paths; consistent with SPIKE verdict. |
| NR-4 (no auto-provision to shared Grafana) | M3 / Design notes | Partial | Default path airtight; no guard against a user pasting a shared URL, and index provision has same-blast-radius as per-project (R1-S8 / R1-F8). |
| NR-5 (no new generator except the FR-11 dashlist addition) | M4 | Full | The single bounded exception (dashlist PanelType + mixin) is gated in M4; everything else reuses the existing path. |
| OQ-5 (provision UX at start — bare board acceptable?) | (leaning documented; unresolved) | Partial | Plan does not schedule a resolution task; carried as open. |
| OQ-7 (index generation trigger) | M4 (proposes `--index` upsert) | Partial | M4 proposes `--index`; the auto-upsert-on-provision option's blast-radius/toolchain-degrade constraints unaddressed (R1-S8 / R1-F10). |
