# Grafana Triage Panel Mode — Implementation Plan

**Version:** 1.2 (Post-CRP — 2 rounds triaged)
**Date:** 2026-07-10
**Requirements:** `TRIAGE_PANEL_REQUIREMENTS.md` v0.4

---

## Composition (the key design)

The Triage panel drives the **middle** of the pipeline and hands off to the existing Apply mode:

```
[Triage panel]  triage(view,$0) → extract(PAID) → disposition($0) → serialize($0, fills VIPP inbox)
[Apply mode]                                                        → preview → ratify → source of record
```

The panel never re-implements the apply HMAC/nonce gate (FR-11). Field-level items flow through the
VIPP pipeline; NON_DECIDABLE + UNSTRUCTURED items are shown as the read-only backlog preview (copy-out).

## Route contracts (grounded — verbatim shapes)

| Route | Request | Response (key fields) |
|-------|---------|-----------------------|
| `POST /triage` | `{session_id?}` | `{kind, session_id, counts, kind_counts, health, candidates[], synthesis_present}` **+ `backlog_markdown` (M1)** |
| `POST /extract` (dry) | `{session_id?, dry_run:true}` | `{session_id, synthesis_checksum, extract_key, estimated_cost, model, n_allowed, note}` |
| `POST /extract` (confirm) | `{session_id?, confirm_checksum, max_cost_usd?}` | `{status:"staged"\|"deduped", staged[{value_path, value, **domain** (M1b)}], actual_cost, ceiling_exceeded, ...}` · 409 checksum mismatch **or in-progress (M1c)** · 412 budget/ceiling · 422 no synthesis |
| `POST /disposition` | `{session_id, domain, value_path, disposition}` | `{..., updated:true}` · 400 · 404 not staged. **`domain` comes from the extract row (M1b).** |
| `POST /serialize` | `{session_id}` | `{staged, rejected, inbox}` · 409 none accepted · 404 none staged · **409 undrained-inbox (M1d) — was a silent 200** |

Candidate shape: `{title, source_section, raw_text, lane, reason, suggested_owner, value_path,
input_kind, role}`. Lanes: `FIELD_LEVEL`/`NON_DECIDABLE`/`UNSTRUCTURED`. 10 input_kinds.

## Milestones

### M1 — Server hardening (the Python surface; do FIRST, all in one PR-slice, real tests)  [FR-4, FR-8a, FR-9a, FR-10b]
Four small, grounded changes to `stakeholder_run_server.py` (CRP surfaced M1b/c/d — the panel is
**unbuildable/unsafe without them**). All additive/hardening; no new routes, no new pipeline logic.
- **M1a — `backlog_markdown` on `_triage`** [FR-4]. After `build_triage`, add
  `render_backlog_section(report, project=<root name>)` to the response (`""` when no candidates).
- **M1b — `domain` in extract `staged[]`** [FR-9a, **blocking**]. `_extract` currently emits
  `{value_path, value}` in **both** the `"staged"` and `"deduped"` branches; add `domain` (from
  `Recommendation.domain`) so the panel can build a valid `/disposition` `(domain, value_path)` call.
- **M1c — atomic extract via `reserve()`** [FR-8a]. Replace `store.lookup(...)`+`store.record_start(...)`
  in `_extract` with the existing atomic `IdempotencyStore.reserve(extract_key, checksum)`; a still-
  `started` reservation → **409 "extraction in progress"** instead of a second spend.
- **M1d — undrained-inbox 409 in `_serialize`** [FR-10b]. Inspect `result["write"]["skipped"]`; if
  non-empty (no-clobber skip), return **409 "undrained inbox — consume via Apply mode first"** rather
  than 200 with populated `staged`/`inbox`.
- **Tests** (`tests/unit/…/test_stakeholder_run_server_*`, real, in-pytest):
  (a) triage carries `backlog_markdown` (non-empty w/ candidates; `""` when synthesis absent) **and the
  response is a superset — every pre-existing key still present with unchanged type** (R1-S6);
  (b) extract `staged[]` rows include `domain`; a disposition built from an extract row → `updated:true`;
  (c) two concurrent confirms on one `extract_key` → exactly one `"staged"`, the other `"deduped"`/409,
  cost recorded once; (d) second serialize on an undrained inbox → 409, inbox byte-unchanged.

### M2 — Plugin scaffolding  [FR-1, FR-6]
- `types.ts`: `mode` union `+ 'triage'`; `TriageCandidate`, `TriageReportResult` (+ `backlog_markdown`),
  `ExtractDryRun`, `ExtractResult`, `DispositionResult`, `SerializeResult`.
- `module.ts`: `triage` in the mode radio + decision-aid description.
- `StakeholdersPanel.tsx`: dispatch `mode==='triage'` → `<TriagePanel/>`.

### M3 — `TriagePanel.tsx` Phase 1: triage view (read-only)  [FR-2, FR-3, FR-5, FR-12, FR-13]
- Optional `session_id` input (empty = latest) → **Triage** → `proxyPost('stakeholders/triage',…)`.
- Render counts/kind_counts/health; candidates grouped by lane; UNSTRUCTURED as a distinct "preserved"
  group; collapsible `backlog_markdown` preview; persistent SYNTHETIC & UNRATIFIED banner; empty state
  when `synthesis_present===false`.
- **State machine** (FR-12/FR-13): phase `idle→triaged→staged→dispositioned→serialized`; hold the
  `session_id` **and** `synthesis_checksum` from the responses as the anchor threaded to every later
  call. A changed checksum or lost `session_id` → "synthesis changed / re-triage" transition, never a
  silent 400/stale disposition.

### M4 — Phase 2: Extract (the paid step), cost-gated  [FR-8, FR-8a, FR-8b]
- **Preview cost** (`dry_run:true`) → estimate + `synthesis_checksum` → **ConfirmModal** (echo estimate)
  → confirm (`confirm_checksum`) → render `staged[]` (now incl. `domain`) + `actual_cost` +
  `ceiling_exceeded`/`deduped`.
- **Double-click safety (FR-8a):** the confirm handler transitions phase **synchronously before** the
  `await` (mirror `FacilitatePanel.handleConfirm`'s `setPhase` pre-await) so the modal closes on the
  first click. Backstopped by M1c server atomicity.
- **`deduped` UX (FR-8b):** render as "already extracted — $0, no re-charge"; do NOT bind
  `actual_cost`/`ceiling_exceeded` on that branch (absent → `$undefined`).
- Surface 412 (budget)/409 (checksum **or in-progress**)/422 (no synthesis) honestly.

### M5 — Phase 3: Disposition  [FR-9, FR-9a, FR-13]
- Per staged rec: Accept / Reject → `proxyPost('stakeholders/disposition',{session_id, domain,
  value_path, disposition})` — **`domain` + `session_id` come from M4's held state** (M1b/FR-13). Track
  per-rec state; surface the 404 "stage it first" clearly.

### M6 — Phase 4: Serialize + hand-off  [FR-10, FR-10a, FR-10b, FR-11, FR-11a]
- **Serialize accepted** → `proxyPost('stakeholders/serialize',{session_id})` → show `{staged,
  rejected, inbox}`.
- **FR-10a:** render `rejected[]` (non-allow-listed) in a distinct "not serialized" group.
- **FR-10b/FR-11a:** on **409 undrained-inbox**, show an "inbox occupied — ratify in Apply mode first"
  state (display the `inbox` path only on a real write); the hand-off note carries the `session_id` so
  Apply targets the same session.

### M7 — README + manual verify  [FR-7]
- Document the mode, the paid extract, the serialize→Apply hand-off, and the operator
  `npm ci && npm run typecheck && npm run build` + restart (Actions disabled → no CI gate).

## Test / validation
- **Python:** M1 carries **four** real route tests (M1a backlog / M1b domain / M1c concurrent-confirm /
  M1d undrained-inbox). These are genuine correctness fixes to shipped routes, verified in pytest.
- **TS:** typecheck-pending (no `node_modules`; Actions disabled). Thin driver over tested routes;
  documented manual verify + the dormant `grafana-plugin.yml` CI gate covers it once Actions is on.

## Requirement → milestone trace
FR-1→M2/M3 · FR-2→M3 · FR-3→M3 · FR-4→**M1a**/M3 · FR-5→M3 · FR-6→M2/M3 · FR-7→M7 ·
FR-8→M4 · FR-8a→**M1c**/M4 · FR-8b→M4 · FR-9→M5 · FR-9a→**M1b** · FR-10→M6 · FR-10a→M6 ·
FR-10b→**M1d**/M6 · FR-11→M6 · FR-11a→M6 · FR-12→M3 · FR-13→M3/M5.

## Risks
- **R1 — paid action in a dashboard.** Extract spends. Mitigated: dry-run→confirm modal + server
  fail-closed budget (412) + `max_cost_usd` ceiling + checksum echo + **atomic `reserve()` (M1c)** +
  **synchronous ConfirmModal close (FR-8a)** — double-spend closed at both the server and UX layers.
- **R2 — TS unverified here.** No `node_modules`/CI. Mitigated: thin driver, mirror existing panels,
  documented manual verify; keep logic server-side.
- **R3 — multi-step state in one component.** Mitigated: explicit phase state machine holding
  `session_id`+`synthesis_checksum` (FR-12/13); a mid-flow synthesis change or lost anchor forces
  re-triage rather than a stale disposition or opaque 400.
- **R4 — silent data-loss at serialize (CRP R2).** An undrained inbox previously returned 200 while
  writing nothing. Mitigated by M1d (409) + the panel's "inbox occupied" state.

*v1.2 — Post-CRP. M1 grew from one to FOUR server changes (M1a backlog + M1b domain + M1c reserve +
M1d undrained-inbox) — all grounded correctness fixes to shipped routes; M3–M6 gain the state-machine
+ per-step hardening; Apply mode still reused for the final write. Dispositions in Appendix A.*

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
| R1-S1 | `domain` in extract staged rows | opus | → M1b + test (b). Blocking. | 2026-07-10 |
| R2-S1 (+R1-S2) | `reserve()` atomic extract; 409 in-progress | sonnet/opus | → M1c + concurrent-confirm test (c). | 2026-07-10 |
| R2-S2 | Undrained-inbox → 409 in `_serialize` | sonnet | → M1d + re-serialize test (d). | 2026-07-10 |
| R1-S3 | Staleness: state machine carries `synthesis_checksum` | opus | → M3 state-machine (FR-12). | 2026-07-10 |
| R2-S3 | ConfirmModal transitions phase before await | sonnet | → M4 double-click safety. | 2026-07-10 |
| R2-S4 (+R1-S4) | Thread `session_id` M4→M5→M6 | sonnet/opus | → M3/M5/M6 (FR-13). | 2026-07-10 |
| R1-S5 | Render serialize `rejected[]` | opus | → M6 (FR-10a). | 2026-07-10 |
| R1-S7 | `deduped` = $0 state; guard absent cost fields | opus | → M4 (FR-8b). | 2026-07-10 |
| R1-S6 | M1 superset regression test | opus | → M1a test asserts triage response is a superset (old keys unchanged). | 2026-07-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All S-suggestions accepted — each grounded in shipped route code; several are real correctness fixes. | 2026-07-10 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-10

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-10 07:05:00 UTC
- **Scope**: Plan review (S-prefix) grounded in `stakeholder_run_server.py` (`_extract`, `_disposition`, `_serialize`) + `synthesis_bridge/stage.py` + `proposals.py`. Focus weight: M1 server change, M4 paid-extract cost gate, M5/M6 write surface, R3 state machine.

**Executive summary (top risks / gaps):**
- **Blocking data-flow gap (M4→M5):** M4's extract renders `staged[]` as `{value_path, value}` per the route contract, but M5 disposition needs `domain` (`update_disposition` keys on `(domain, value_path)`). M5 is not buildable from M4's output as specced.
- **M4 idempotency has a concurrency window:** `record_start`→provider→`mark_complete` is unlocked; two concurrent confirms on one `extract_key` can both spend. The plan's R1 mitigation only covers replay, not double-submit.
- **R3 state machine guards extract-checksum but not triage/disposition staleness** — a mid-flow synthesis change leaves the earlier phases silently stale.
- **M6 hand-off is a two-mode split with no shared session assertion** — state-desync risk (Apply mode previewing a different inbox) is unmitigated in the plan.
- **M1 additivity is under-verified:** the plan asserts additive but no test checks that an existing exact-key triage-response consumer doesn't break on the new key.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | critical | M4/M5: extend the extract staged-row shape (and M4's `ExtractResult` TS type) to include `domain` so M5 can build the disposition request; add a server sub-task to include `domain` (and `recommended_value`) in `_extract`'s `staged[]` for both `"staged"` and `"deduped"` branches. | Route contract staged shape is `{value_path, value}`; `/disposition` requires `domain`. As written the panel cannot produce a valid disposition call. | M4 bullet + M5 bullet; §Route contracts staged-row note | Assert `/extract` staged rows carry `domain`; M5 disposition built from an extract response returns `updated:true`. |
| R1-S2 | Data | high | M4: add a sub-task making the extract confirm double-submit-safe (serialize on `extract_key`, or `record_start` as an atomic claim a second caller loses), and add a Python test for two concurrent confirms. | `_extract` writes `record_start` before the provider call but takes no lock; two confirms both pass `lookup` and both charge. R1's mitigation ("checksum echo") does not cover same-checksum double-submit. | M4, after "Surface 412/409/422 honestly"; Risks R1 | Concurrent-confirm test: exactly one `staged`, one `deduped`/409, cost recorded once. |
| R1-S3 | Risks | high | R3: expand the state machine so triage/staged/dispositioned state is invalidated when `synthesis_checksum` changes, not only the extract confirm. Add a `currentChecksum` to phase state and a "synthesis changed — re-triage" transition. | Focus R3: checksum guards extract only; triage candidates and staged dispositions can go stale after a re-facilitation, so the operator dispositions against a superseded synthesis. | R3 risk bullet; M3/M5 state notes | Simulate a synthesis change between triage and disposition; assert the panel forces re-triage. |
| R1-S4 | Interfaces | medium | M6: add a hand-off assertion — after serialize, deep-link/carry the `session_id` into Apply mode (or display it prominently) so preview→ratify targets the just-serialized inbox; document whether a second serialize appends or replaces. | Flow splits across two modes with no shared session state (focus FR-11 state-desync hazard). | M6 bullet, after the "switch to Apply" note | Serialize session A → Apply mode; assert preview reflects A's inbox; specify re-serialize semantics. |
| R1-S5 | Interfaces | medium | M6: render `serialize`'s `rejected[]` explicitly (non-allow-listed accepted recs are rejected-not-dropped). Show a distinct "not serialized — not allow-listed" group. | Without surfacing `rejected`, an accepted decision silently vanishes before Apply, so ratify covers fewer items than the operator believes. | M6 bullet | Serialize a set with one non-allow-listed path; assert it appears in a visible rejected group. |
| R1-S6 | Validation | medium | M1: add a regression test asserting the triage response is a **superset** — every pre-existing key still present with unchanged types — so the additive `backlog_markdown` cannot mask a shape change, and confirm no consumer exact-key-matches (`set(keys)==…`) the triage dict. | Plan claims M1 is additive/safe but only tests the new field's presence; the focus file explicitly asks whether any consumer exact-key-matches the triage response. | M1 test bullet | Snapshot pre-change keys; assert new response keys ⊇ old; grep consumers for exact-key comparisons. |
| R1-S7 | Ops | low | M4: surface `deduped` in the UI as an explicit "$0 — already extracted" state and guard against binding `actual_cost`/`ceiling_exceeded` (absent on the deduped branch) to avoid `$undefined`. | Deduped response omits cost fields; blind binding misleads the operator about spend. | M4 bullet | Golden-render both branches; deduped shows no charge. |

**Endorsements / Disagreements:** none (first review round; Appendix C was empty).

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-10

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-10 00:00:00 UTC
- **Scope**: Adversarial pass — grounded against `stakeholder_run_server.py` (`_extract`, `_serialize`, `IdempotencyStore`), `vipp_seam.py` (`serialize_buffer`), `synthesis_bridge/stage.py` (`serialize_accepted_to_vipp`), and `FacilitatePanel.tsx` (pattern reference). Focus: paid-action hazards, silent-skip on serialize, double-click confirm, ConfirmModal phase-transition pattern, `reserve()` vs `record_start()` gap.

**Executive summary (top risks / gaps):**
- **New critical: `_extract` uses `lookup+record_start` (non-atomic) but `reserve()` exists and closes the window.** Facilitation correctly uses `reserve()`; extract does not. The fix is one-line: replace `lookup`+`record_start` with `reserve()` in `_extract`.
- **New high: `_serialize` silently succeeds (200 + `staged:[...]`, `inbox:"path"`) when the inbox is undrained.** `serialize_buffer` returns a `WriteResult(skipped=[...])` — `_serialize` only reads `result["staged"]`/`rejected`/`inbox` from `stage.py`, which are populated even when the write was skipped. Operator is told serialize succeeded; Apply mode then previews an older inbox.
- **New medium: M4's ConfirmModal must close (transition phase) on the first click, not after the async response.** FacilitatePanel's `handleConfirm` calls `setPhase('polling')` before the await, so the modal closes immediately. If M4 doesn't mirror this, a user who double-clicks "Confirm" fires two concurrent confirms, both pass the non-atomic `lookup`, and both spend.
- **New medium: M6 plan omits `session_id` carry obligation.** `_serialize` requires `session_id` in the body (400 otherwise) but M6 describes "switch to Apply mode" with no mention of carrying the `session_id` forward through the React state chain (M4 extract → M5 disposition → M6 serialize all need the same `session_id`).
- **R1-S2 root cause is more specific than stated:** the correct fix is `reserve()` not a new lock; this is a one-line server change (already has the method).

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Security | critical | M4 server sub-task: replace `store.lookup(extract_key, checksum)` + `store.record_start(extract_key, checksum)` with `store.reserve(extract_key, checksum)` (already exists on `IdempotencyStore`). If `reserve()` returns a non-None record that is `"started"` (not "completed"), return 409 "extraction in progress — retry" rather than proceeding to spend. | `_extract` uses the non-atomic two-call pattern; `reserve()` is an existing atomic check-and-set (used correctly by facilitation). Two concurrent confirms both pass `lookup` (neither completed), both fall through to `record_start`, both spend. `reserve()` closes this in one operation. | M4 bullet; Risks R1 ("paid action in a dashboard") | Two concurrent `/extract` confirms with the same `extract_key`; assert exactly one returns `status:"staged"`, the other 409; cost recorded once; server logs one provider call. |
| R2-S2 | Risks | high | M6 server sub-task: add an explicit undrained-inbox check in `_serialize` — after `serialize_accepted_to_vipp` returns, inspect `result["write"]` for a non-empty `skipped` list; if present, return 409 "undrained inbox — consume it in Apply mode before re-serializing" rather than returning 200 with `staged:[...], inbox:"path"`. | `serialize_buffer` is no-clobber: when an existing inbox is undrained, it sets `write.skipped` and returns without writing. `_serialize` currently ignores `result["write"]` entirely, so the operator sees a 200 with `staged` and `inbox` populated but nothing was written. Apply mode then previews a stale inbox. This is a silent data-loss path on the write surface. | M6 bullet; §Route contracts `POST /serialize` response row | Serialize once (inbox now exists); serialize again without draining; assert the second call returns 409 with an "undrained inbox" message; inbox file is unchanged. |
| R2-S3 | Interfaces | medium | M4: specify that the ConfirmModal's `onConfirm` handler MUST transition phase away from `"confirm"` (e.g. to `"extracting"`) **synchronously before the await**, so the modal closes immediately on first click and a second click is a no-op. Mirror `FacilitatePanel.handleConfirm` which calls `setPhase('polling')` before the first `await`. | Without this, double-clicking the confirm button in the Grafana modal fires two concurrent `POST /extract` confirms. The non-atomic `lookup+record_start` in `_extract` (pre-R2-S1) means both pass and both spend. Even with R2-S1 applied, the UX should prevent duplicate confirm requests. | M4 bullet ("ConfirmModal (echo estimate)"); §Test/validation TS notes | Mock the extract endpoint with a 500ms delay; click confirm twice rapidly; assert exactly one POST fires. |
| R2-S4 | Data | medium | M4→M6: add a plan note that `session_id` (obtained from `_extract`'s response) must be threaded through React state from M4 (extract) → M5 (disposition) → M6 (serialize) and that each `proxyPost` call must carry it. `_serialize` returns 400 if `session_id` is absent; the plan currently says `proxyPost('stakeholders/serialize',{session_id})` without noting where `session_id` comes from in the component. | The three write steps share a `session_id` established at extract time. If the component loses state (e.g. panel re-renders, user navigates away and back), M5 and M6 will send empty `session_id` → 400. The plan has no data-flow note. | M5 bullet + M6 bullet (add "using the `session_id` from M4 extract response, held in component state") | Integration test: assert disposition and serialize both use the `session_id` from the extract response. |

**Endorsements:**

- **R1-S1** (critical — `domain` missing from extract staged rows): Grounded confirmation — `Recommendation.domain` exists in the dataclass and is persisted, but `_extract` emits only `{value_path, recommended_value}`. Agree this is the top-priority blocking gap.
- **R1-S2** (high — double-submit concurrency): Endorsed with the correction in R2-S1: the right fix is `reserve()`, not a new lock. The `reserve()` method already exists and is the canonical pattern.
- **R1-S4** (medium — hand-off session assertion): Endorsed; related to R2-S4 which adds the React data-flow note.
- **R1-S5** (medium — `rejected[]` not surfaced): Endorsed. Grounded: `_serialize` returns `result["rejected"]` which is `[(value_path, reason)]` tuples, but also returns 200 on undrained-inbox (fixed by R2-S2). These are orthogonal.
- **R1-S6** (medium — M1 superset regression test): Endorsed; the `build_triage` return shape from `TriageReport.to_dict()` is worth locking down as a superset.

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement → plan milestone(s) → coverage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (`triage` panel mode) | M2, M3 | Full | — |
| FR-2 (session selection latest-or-explicit) | M3 | Full | — |
| FR-3 (typed lane-routed candidates) | M3 | Partial | No staleness guard if synthesis changes after triage (R1-S3/R1-F4). |
| FR-4 (backlog preview via extended route) | M1, M3 | Partial | M1 additivity under-tested — no superset/consumer-exact-match check (R1-S6). |
| FR-5 (honest framing / banner / empty state) | M3 | Full | — |
| FR-6 (token server-side / proxyPost) | M2, M3 | Full | Settled (token-via-proxy) — not reviewed. |
| FR-7 (operator docs) | M7 | Full | — |
| FR-8 (paid extract, cost-gated) | M4 | Partial | Double-submit concurrency window (R1-S2/R1-F1); `deduped` UX contract (R1-S7/R1-F2). |
| FR-9 (disposition) | M5 | Partial | **`domain` not surfaced by extract → M5 unbuildable as specced (R1-S1/R1-F3).** |
| FR-10 (serialize) | M6 | Partial | `rejected[]` not surfaced (R1-S5/R1-F5). |
| FR-11 (compose with Apply, no duplicate gate) | M6 | Partial | Two-mode hand-off lacks shared-session assertion / re-serialize semantics (R1-S4/R1-F6). |

## Requirements Coverage Matrix — R2

Analysis only (not triage). Incremental — focuses on gaps newly identified in R2 or coverage changes from grounded code reading.

| Requirement | Plan Step(s) | Coverage | Gaps / R2 Findings |
| ---- | ---- | ---- | ---- |
| FR-8 (paid extract, cost-gated) | M4 | Partial | R1 gaps still open; NEW: M4 does not specify synchronous phase-transition on confirm (double-click hazard, R2-S3/R2-F2); `reserve()` not specified as the atomic replacement for `lookup+record_start` (R2-S1). |
| FR-9 (disposition) | M5 | Partial | R1-S1/R1-F3 still open (blocking). NEW: `session_id` carry obligation from M4→M5 not stated (R2-S4/R2-F4). |
| FR-10 (serialize) | M6 | Partial | R1 gaps still open. NEW: undrained-inbox silent-skip hazard — `_serialize` returns 200 but nothing written when inbox exists (R2-S2/R2-F1). `inbox` path display on success not required (R2-F3). |
| FR-11 (compose with Apply, no duplicate gate) | M6 | Partial | R1 gaps still open. `serialize_buffer` no-clobber semantics are the mechanism for re-serialize; plan should note that a second serialize on an undrained inbox returns 409 (per R2-S2), which is the correct behavior for the hand-off. |
| FR-1 (`triage` panel mode) | M2, M3 | Full | — |
| FR-2 (session selection) | M3 | Full | — |
| FR-3 (typed lane-routed candidates) | M3 | Partial | R1-S3/R1-F4 staleness guard still open. |
| FR-4 (backlog preview) | M1, M3 | Partial | R1-S6 superset regression test still open. |
| FR-5 (honest framing) | M3 | Full | — |
| FR-6 (token server-side) | M2, M3 | Full | Settled. |
| FR-7 (operator docs) | M7 | Full | — |
