# Grafana Triage Panel Mode — Requirements

**Version:** 0.4 (Post-CRP — 2 rounds triaged)
**Date:** 2026-07-10
**Status:** Draft (scope: read-only viewer **+ full VIPP write path**, per OQ-1 decision)

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass (grounded against `stakeholder_run_server.py` + `synthesis_bridge/`) corrected the
> v0.1 draft, and the OQ-1 scope decision expanded it from a read-only viewer to the full write path.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The triage route returns a backlog preview | `_triage` returns `TriageReport.to_dict()` + `synthesis_present` **only** — no backlog markdown | **FR-4** now requires a small server change: extend `_triage` to also return `render_backlog_section(report)` (reuse the *tested* renderer — no TS re-impl). NR-3 (v0.1) was wrong. |
| Per-candidate disposition is a small add | `_disposition` acts on **staged** recs; staging is `_extract` — **the ONE paid step** (budget-gated, checksum-deduped) | The write path is `triage → extract(PAID) → disposition → serialize → apply`. Added **FR-8/9/10/11**. |
| Backlog-append is in reach | **No backlog-append HTTP route exists**; the file write is CLI-only | Backlog stays a **display-only preview** (NR-2). The actioned write path is the **VIPP field pipeline**, not the backlog file. |
| session_id needs a picker | `_triage`/`_extract` default to `latest_session_id()` when empty | Latest-or-explicit needs **no new route** (resolves OQ-3). |
| The panel must build its own apply gate | `ApplyPanel.tsx` already owns `apply/preview → challenge → ratify` against the VIPP inbox that `serialize` fills | **FR-11**: the Triage panel ends at `serialize` (fills the inbox); the existing **Apply mode** ratifies. Do **not** duplicate the challenge/nonce gate. |
| `extract` maps all candidates | `extract_field_mappings(synthesis, allowed_value_paths)` maps only **FIELD_LEVEL** (`entity.field`) items | Two distinct outputs: FIELD_LEVEL → VIPP write pipeline; NON_DECIDABLE + UNSTRUCTURED → backlog preview (copy-out). Made explicit in FR-3/FR-4. |

**Resolved open questions:**
- **OQ-1 → Read-only viewer + full VIPP write path** (user decision). Backlog-file append is *not* in
  scope (that was option C); the write path is the VIPP field pipeline.
- **OQ-2 → Extend the triage route** to return `backlog_markdown` (reuse the tested Python renderer).
- **OQ-3 → Latest-by-default + optional explicit `session_id`** (the routes already behave this way).
- **OQ-4 → UNSTRUCTURED renders as a visually distinct "preserved — received but not accounted for"
  group**, separate from FIELD_LEVEL and NON_DECIDABLE.

### 0.1 Lessons-Learned Hardening (v0.3)

> Applied the SDK design-docs lessons before CRP. Each was checked:

- **[Leg 6 #6 / recent "phantom config field"] Phantom-reference audit** — grepped every symbol + route
  the spec/plan names. **All 8 symbols** (`render_backlog_section`, `latest_session_id`, `build_triage`,
  `extract_field_mappings`, `stage_recommendations`, `serialize_accepted_to_vipp`, `update_disposition`,
  `preview_dispositions`) **and all 5 routes** exist in the shipped code → **no phantoms** (see §Reference
  Audit). Only *new* symbol is the additive `backlog_markdown` field (M1, to-be-created).
- **[recent Leg "overloaded-term co-location"]** — the new concept lives in its own component
  (`TriagePanel.tsx`) and an additive response field; it does **not** stack a second meaning onto a
  module that owns another. No overload.
- **[recent Leg "provenance over-claim"]** — kept honest naming: the extract idempotency basis is a
  "checksum", not an "attestation"; output is labeled **SYNTHETIC & UNRATIFIED**. No over-claim.
- **[Leg "internal passes miss what fresh eyes catch"]** — this NEW req+plan has had zero external
  review → CRP is warranted (carried to the focus file as the least-reviewed target).

### 0.2 Design-Principle Hardening (v0.3.1)

> Checked the draft against the design principles. Each was applied:

- **[Mottainai]** — FR-4 reuses the *tested* `render_backlog_section` **server-side** (M1) rather than
  re-implementing the backlog renderer in TS; the panel renders `backlog_markdown`, it does not
  re-derive it. (Also NR-6.)
- **[Genchi Genbutsu]** — every request/response shape in the plan is bound to the **real** route code
  (grounded verbatim), not an assumed contract; the final write reuses the **real** Apply gate (FR-11),
  not a lookalike. One canonical name (`triage` mode) — no duplicate surface.
- **[Accidental-Complexity anti-principle]** — no allowlist/special-case/bypass added; the panel is a
  thin driver and the only server change is one additive field. Nothing to dissolve.
- **[Context-Correctness-by-Construction]** — the extract confirm **echoes the `synthesis_checksum`**;
  a concurrent synthesis edit → 409, so the paid step can't silently bind to the wrong synthesis.
- **[Hitsuzen]** — the backlog preview is deterministic ($0 renderer); only `extract` uses an LLM, and
  it genuinely must (mapping free-text synthesis → allowed `entity.field` values).

### Reference Audit (phantom-free)

| Symbol / route | Exists in |
|----------------|-----------|
| `render_backlog_section` | `synthesis_bridge/backlog.py` |
| `build_triage` | `synthesis_bridge/route.py` |
| `extract_field_mappings` / `stage_recommendations` / `serialize_accepted_to_vipp` | `synthesis_bridge/{extract_llm,stage}.py` |
| `update_disposition` | `stakeholder_panel/proposals.py` |
| `latest_session_id` | `kickoff_view/facade.py` |
| `preview_dispositions` | `vipp/apply.py` |
| `/stakeholders/{triage,extract,disposition,serialize,apply/*}` | `stakeholder_run_server.py` |
| `backlog_markdown` (response field) | **to-be-created (M1)** |

---

## 1. Problem Statement

The whole synthesis→action pipeline exists over HTTP (`/stakeholders/{triage,extract,disposition,
serialize,apply}`), but the Grafana plugin surfaces only `run`/`apply`/`facilitate`. An operator can
*generate* a synthesis and *ratify* an already-staged inbox, but the **middle — triage → stage → accept
→ serialize — is CLI-only**. This feature adds a `triage` mode that drives that middle from the
dashboard and hands off to the existing Apply mode for the final write.

| Stage | Route | Cost | Today |
|-------|-------|------|-------|
| Triage (view routed candidates) | `POST /stakeholders/triage` | $0 | CLI-only |
| Extract (stage field-level recs) | `POST /stakeholders/extract` | **PAID** | CLI-only |
| Disposition (accept/reject staged) | `POST /stakeholders/disposition` | $0 | CLI-only |
| Serialize (accepted → VIPP inbox) | `POST /stakeholders/serialize` | $0 | CLI-only |
| Apply (ratify → source of record) | `POST /stakeholders/apply/{preview,ratify}` | $0 | **Apply mode (exists)** |

## 2. Requirements

### Read surface
- **FR-1 — `triage` panel mode.** Add `triage` to the mode radio; `StakeholdersPanel` dispatches to a
  new `TriagePanel`. Mirror `ApplyPanel`/`FacilitatePanel`.
- **FR-2 — Session selection.** Triage the *latest* facilitation session by default, or an explicit
  `session_id` (matches the route default).
- **FR-3 — Render typed, lane-routed candidates.** Per-lane counts (FIELD_LEVEL / NON_DECIDABLE /
  UNSTRUCTURED), per-`input_kind` breakdown, health warnings, and candidates grouped by lane — each
  with `input_kind`, `reason`, `value_path` (field-level), `role` (provenance). UNSTRUCTURED is a
  visually distinct "preserved" group (OQ-4).
- **FR-4 — Backlog preview.** Show `render_backlog_section` output (via the extended triage route) as a
  read-only preview of what would land in `ENHANCEMENTS_BACKLOG.md` (the NON_DECIDABLE + UNSTRUCTURED
  copy-out). Requires the **server change** (extend `_triage` to return `backlog_markdown`).
- **FR-5 — Honest framing.** Persistent **SYNTHETIC & UNRATIFIED** banner; a clean empty state when
  `synthesis_present` is false (e.g. an ask-all session); label read-only vs paid steps clearly.

### Write path (VIPP field pipeline)
- **FR-8 — Extract (the paid step), cost-gated.** A **dry-run → confirm** flow mirroring run/facilitate:
  dry-run returns the estimate + `synthesis_checksum` (+`extract_key`); confirm **echoes the checksum**;
  the server fail-closes on the blocking budget (412) and honors `max_cost_usd`. The confirm button
  shows the estimate.
  - **FR-8a — Double-spend-safe (CRP R1-F1/R2-S1).** Two concurrent confirms sharing an `extract_key`
    MUST NOT both charge. Server: replace the non-atomic `lookup`+`record_start` in `_extract` with the
    existing atomic `IdempotencyStore.reserve()`; a still-`started` reservation → 409 "extraction in
    progress", not a second spend. **UX (CRP R2-F2):** the confirm handler transitions phase
    synchronously *before* the async POST (mirror `FacilitatePanel.handleConfirm`) so the modal closes
    on the first click and a double-click can't issue a second request.
  - **FR-8b — Honest `deduped` state (CRP R1-F2).** Render `status:"deduped"` as an explicit
    "already extracted — no charge" state, visually distinct from a fresh `"staged"` charge; do **not**
    bind `actual_cost`/`ceiling_exceeded` on the deduped branch (they're absent → would show `$undefined`).
- **FR-9 — Disposition.** For each staged rec, accept/reject via `POST /stakeholders/disposition`
  (`{session_id, domain, value_path, disposition∈{accepted,rejected}}`). Surface the 404
  "stage it first" as a clear state, not a silent failure.
  - **FR-9a — Extract MUST surface `domain` (CRP R1-F3/R1-S1 — blocking).** `update_disposition` keys on
    `(domain, value_path)`, but `_extract`'s `staged[]` returns only `{value_path, value}` — so the panel
    has no source for `domain` and every disposition would send `domain:""`. Server: include `domain`
    (and a stable identity) in each staged row for **both** the `"staged"` and `"deduped"` branches.
    Without this, FR-9 is unbuildable.
- **FR-10 — Serialize.** `POST /stakeholders/serialize` pushes *accepted* staged recs to the VIPP
  inbox; surface `{staged, rejected, inbox}`.
  - **FR-10a — Surface `rejected[]` (CRP R1-F5).** Non-allow-listed accepted recs are *rejected, not
    dropped*. Render them in a distinct "not serialized — not allow-listed" group so an accepted decision
    can't silently vanish before the Apply hand-off.
  - **FR-10b — Undrained-inbox is an error, not a silent success (CRP R2-F1/R2-S2).** `serialize_buffer`
    is no-clobber: an existing undrained inbox → `write.skipped`, nothing written. But `_serialize`
    currently ignores `result["write"]` and returns 200 with `staged`/`inbox` populated. Server: when the
    write was skipped, return **409 "undrained inbox — ratify/consume it in Apply mode first"**. Panel
    shows a distinct "inbox occupied" state; display the `inbox` path only when a write actually occurred.
- **FR-11 — Compose with Apply; do not duplicate it.** The Triage panel ends at serialize (fills the
  inbox). The final write (challenge → ratify → source of record) stays in the existing Apply mode. No
  re-implementation of the HMAC challenge/nonce gate here.
  - **FR-11a — Hand-off targets the same session (CRP R1-F6/R1-S4).** After serialize, the operator
    switching to Apply mode must land on the *same session's* inbox (display/carry the `session_id`); a
    second serialize on an undrained inbox is the 409 of FR-10b (re-serialize semantics defined).

### Cross-cutting
- **FR-6 — Token stays server-side.** All requests via the datasource proxy (`proxyPost`); the token is
  never a panel option. Mirror the existing components.
- **FR-7 — Operator docs.** README documents the `triage` mode, the paid extract step, the
  serialize→Apply hand-off, and the manual typecheck/build/restart (Actions is disabled repo-wide).
- **FR-12 — Staleness guard (CRP R1-F4/R1-S3).** The extract checksum guards *extract* only. The panel
  MUST pin triage-view + disposition to the `synthesis_checksum` triage was built against; if the synthesis
  changes mid-flow (a re-facilitation), surface "synthesis changed — re-triage" rather than allowing
  disposition against superseded staged recs.
- **FR-13 — Session continuity (CRP R2-F4/R2-S4).** The `session_id` established at extract time is the
  anchor for disposition + serialize; it MUST be held in component state and threaded to every call. A
  lost anchor (re-render/navigation) surfaces as a recoverable "re-triage to re-establish session", not
  an opaque 400.

## 3. Non-Requirements

- **NR-1 — No new apply gate.** Reuse the existing Apply mode for ratify (FR-11).
- **NR-2 — No backlog-append-to-file from the dashboard.** The backlog is a display-only preview; no
  new write route.
- **NR-4 — No session-list UI** beyond latest-or-explicit.
- **NR-5 — No Tier-2 bespoke styling** — reuse the existing emotion/css patterns.
- **NR-6 — No new synthesis_bridge logic** — the panel is a thin driver over existing routes. Server
  changes are limited to **surfacing/hardening** existing behavior (CRP-driven): `backlog_markdown` on
  triage (FR-4), `domain` in extract staged rows (FR-9a), `reserve()` atomicity in extract (FR-8a),
  undrained-inbox 409 in serialize (FR-10b). No new pipeline logic, no new routes.

## 4. Open Questions (post-planning)

- **OQ-5 — Single panel vs stepped wizard.** Is the write path one scrolling panel (Triage → Extract →
  Disposition → Serialize sections revealed as you go), or discrete steps? (Leaning: one panel with
  progressive sections, mirroring the run/facilitate preview→confirm idiom.)
- **OQ-6 — Does the paid Extract belong in the Triage panel at all**, or should Extract be its own mode
  so the "paid" action is unmistakably separate from the free triage view? (Leaning: same panel, but
  the paid step is behind its own dry-run→confirm modal so it can't be triggered accidentally.)

---

*v0.2 — Post-planning self-reflective update. 4 requirements added (FR-8/9/10/11), 1 changed (FR-4
needs a server change), 4 open questions resolved, 2 new (OQ-5/6). Scope: read-only viewer + full VIPP
write path, composing with the existing Apply mode.*
*v0.3 — Lessons hardening: phantom-reference audit (clean — 8 symbols + 5 routes exist), no overloaded
term, no provenance over-claim.*
*v0.3.1 — Design-principle hardening: applied Mottainai (reuse the renderer), Genchi Genbutsu (bind to
real routes + reuse the real Apply gate), Accidental-Complexity (nothing to dissolve),
Context-Correctness (checksum echo), Hitsuzen (deterministic backlog preview). Ready for CRP.*
*v0.4 — Post-CRP (2 rounds, opus+sonnet). All 10 F-suggestions accepted. Added FR-8a (double-spend +
double-click), FR-8b (deduped UX), FR-9a (**blocking**: extract must surface `domain`), FR-10a
(rejected[]), FR-10b (undrained-inbox 409), FR-11a (hand-off session), FR-12 (staleness guard), FR-13
(session continuity). Net: 3 new hardening server changes beyond M1. Dispositions in Appendix A.*

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
| R1-F3 (+R1-S1) | Extract must surface `domain` in staged rows | opus | **Blocking.** → FR-9a. Server sub-task (M1b) + test. | 2026-07-10 |
| R1-F1 (+R2-S1, R1-S2) | Extract double-spend-safe via `reserve()` | opus/sonnet | → FR-8a. Server sub-task (M1c) replaces `lookup`+`record_start`; concurrent-confirm test. | 2026-07-10 |
| R2-F1 (+R2-S2) | Undrained-inbox → 409, not silent 200 | sonnet | → FR-10b. Server sub-task (M6b); re-serialize test. | 2026-07-10 |
| R1-F4 (+R1-S3) | Staleness guard on triage/disposition | opus | → FR-12. State machine carries `currentChecksum`. | 2026-07-10 |
| R1-F2 (+R1-S7) | `deduped` UX distinct; don't bind absent cost fields | opus | → FR-8b. | 2026-07-10 |
| R2-F2 (+R2-S3) | ConfirmModal transitions phase synchronously (no double-click) | sonnet | → FR-8a (UX clause). | 2026-07-10 |
| R1-F5 (+R1-S5) | Surface serialize `rejected[]` | opus | → FR-10a. | 2026-07-10 |
| R2-F4 (+R2-S4) | `session_id` continuity M4→M5→M6 | sonnet | → FR-13. | 2026-07-10 |
| R1-F6 (+R1-S4) | Hand-off targets same session's inbox | opus | → FR-11a. | 2026-07-10 |
| R2-F3 | Display `inbox` path only on real write | sonnet | Folded into FR-10b. | 2026-07-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All 10 F-suggestions accepted — each was grounded in the real route code and improves correctness. | 2026-07-10 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-10

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-10 07:05:00 UTC
- **Scope**: Requirements review (F-prefix) grounded in `stakeholder_run_server.py` + `synthesis_bridge/{stage,extract_llm}.py` + `proposals.py`. Focus weight: FR-8 (paid extract cost-gate), FR-9/10 (disposition/serialize write surface), FR-11 (compose-with-Apply), session UX (OQ-5/6), multi-step state machine.

**Focus-file asks (addressed first):**

- **Ask 1 — Is the FR-8 cost gate sufficient to make a paid Grafana action safe? Any way to spend without the confirm? Idempotent-replay correctness?**
  - **Summary answer:** Mostly yes, with one concrete gap (dedupe has a concurrency window) and one under-specified UX contract (`deduped` must be visually unmistakable from a fresh charge).
  - **Rationale:** Grounded read of `_extract` (server) confirms you cannot spend without a confirm: `dry_run` returns before any provider call; confirm requires `confirm_checksum==checksum` (409 else), `ensure_blocking_budget` fail-closes (412), and the pre-call `max_cost_usd` ceiling refuses *before* the call (line 688-690). Idempotency: `record_start` writes the spend marker *before* the provider call (crash-safe), and a completed prior returns `status:"deduped"` without re-charge (line 670-679). However `record_start`→`mark_complete` is **not locked**: two concurrent confirms with the same `extract_key` both pass `lookup` (neither is "completed") and both spend. FR-8 does not require the server to serialize concurrent confirms on the same key.
  - **Assumptions / conditions:** Single-operator dashboards make the concurrency window low-probability but not zero (double-click, two Grafana tabs).
  - **Suggested improvements:** see R1-F1 (dedupe concurrency), R1-F2 (`deduped` UX contract).
- **Ask 2 — FR-9/10 write-surface boundary (intermediate stores, not source of record) clear + safe? Failure modes?**
  - **Summary answer:** Boundary is clear in prose but FR-9 is **not implementable as written** — the disposition request needs `domain`, which the extract response never returns.
  - **Rationale:** `update_disposition` keys on `(domain, value_path)` (`proposals.py:113`), and the `/disposition` route requires `domain` in the body. But `_extract`'s `staged[]` (both `"staged"` and `"deduped"` branches) returns only `{value_path, value}` — `domain` is dropped (server lines 676, 707). The React state machine has no source for `domain`, so every disposition call would send `domain:""`, silently matching only recs whose stored domain is also `""`.
  - **Assumptions / conditions:** none — this is a hard data-flow gap.
  - **Suggested improvements:** see R1-F3 (surface `domain` in staged rows) — this is the highest-value finding.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Data | high | FR-8: add an acceptance criterion that two concurrent confirms sharing an `extract_key` MUST NOT both charge (server serializes on the key, or `record_start` is a compare-and-set that a second caller loses). | `record_start`→provider→`mark_complete` is unlocked; two confirms both pass `lookup` (neither "completed") and both spend. A paid action must be double-spend-safe, not just replay-safe. | FR-8, after "the `deduped` idempotent-replay state" | Fire two `confirm` requests with identical `extract_key` concurrently; assert exactly one `status:"staged"`, the other `"deduped"` (or 409), and cost recorded once. |
| R1-F2 | Interfaces | medium | FR-8: require the panel to render `status:"deduped"` as an explicit "already extracted — no charge" state, visually distinct from a fresh `"staged"` charge, and to suppress `actual_cost` display on the deduped branch. | The `deduped` response omits `actual_cost`/`ceiling_exceeded` (server line 674-679); if the panel binds those fields blindly it shows `$undefined` or a stale prior cost, misleading the operator about whether money was spent. | FR-8, "Surface `actual_cost`, `ceiling_exceeded`, and the `deduped`…" | Golden-render both response shapes; assert deduped shows "$0 / no re-charge" and staged shows the real `actual_cost`. |
| R1-F3 | Data | critical | FR-9: the disposition request is `{session_id, domain, value_path, disposition}` but no requirement guarantees the panel can obtain `domain` — the extract `staged[]` rows return only `{value_path, value}`. Add FR-9a: extract MUST surface `domain` (and ideally a stable rec identity) per staged row. | `update_disposition` matches on `(domain, value_path)` (`proposals.py:113`); with `domain` absent the panel sends `""`, matching the wrong recs or 404-ing. FR-9 is unbuildable without this. | New FR-9a in "Write path"; also flag in §Route contracts staged shape | Assert `/extract` staged rows include `domain`; then a disposition call built solely from an extract response returns `updated:true` for a rec with a non-empty domain. |
| R1-F4 | Risks | high | FR-8/FR-3: add a requirement that triage-view and disposition are pinned to the **same `synthesis_checksum`** the extract confirmed against, and stale triage/disposition state is detected. Extract echoes the checksum (409 on drift), but FR-3 triage and FR-9 disposition have no staleness guard. | Focus item R3: checksum guards *extract* only. If synthesis changes after triage, the displayed candidates and any in-flight disposition silently reference a superseded synthesis; the operator accepts recs mapped from prose that no longer exists. | FR-3 and FR-9; cross-ref R1-S3 in plan | Re-facilitate mid-flow; assert the panel flags "synthesis changed — re-triage" rather than allowing disposition against stale staged recs. |
| R1-F5 | Interfaces | medium | FR-10: specify how the panel surfaces `serialize`'s `rejected[]` (non-allow-listed `value_path`s are *rejected, not dropped* — server line 455). An accepted rec silently missing from the inbox is a lost decision. | Operator accepts N recs, serialize pushes N-k, and without surfacing `rejected` the k dropped are invisible; the Apply hand-off then ratifies fewer items than the operator believes. | FR-10, after "surface `{staged, rejected, inbox}`" | Serialize a set containing one non-allow-listed path; assert the panel lists it under a visible "rejected — not allow-listed" group. |
| R1-F6 | Validation | medium | FR-11: add an acceptance criterion for the cross-mode hand-off — after serialize, the operator switching to Apply mode must land on the *same session's* inbox, and the requirement should state what happens if the inbox is re-serialized (append vs replace) before ratify. | The flow spans two panel modes with no shared session state; a state-desync (Apply mode previewing a different/older inbox) is the focus-file's named hazard (FR-11). | FR-11, after "No re-implementation of the HMAC…gate" | Serialize session A, open Apply mode; assert preview reflects session A's just-serialized inbox; document idempotency of a second serialize. |

**Endorsements / Disagreements:** none (first review round; Appendix C was empty).

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-10

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-10 00:00:00 UTC
- **Scope**: Adversarial requirements pass — grounded against `_serialize` / `serialize_buffer` / `vipp_seam.py` (no-clobber semantics), `_extract` / `IdempotencyStore.reserve()` (atomic claim), and `FacilitatePanel.tsx` (ConfirmModal pattern). Focus: FR-8 paid-action hazards not covered by R1, FR-10 serialize silent-skip, FR-11 hand-off session contract.

**Focus-file asks (addressed first):**

- **Ask 5 — Multi-step React state machine (idle→triaged→staged→dispositioned→serialized): race/stale-state hazards; synthesis change mid-flow.**
  - **Summary answer:** Two new hazards R1 missed: (a) ConfirmModal double-click fires two concurrent confirms before phase transition closes it; (b) serialize returns 200 but writes nothing when the inbox is undrained (stale Apply mode context).
  - **Rationale:** (a) `FacilitatePanel` avoids double-click by transitioning `phase` to `'polling'` **before** the confirm await, closing the modal immediately. If M4's ConfirmModal mirrors this, double-click is a no-op — but the plan does not specify this. (b) `serialize_buffer` is no-clobber: an existing undrained inbox causes `WriteResult(skipped=[...])`, but `_serialize` does not check `result["write"]["skipped"]` and returns `{staged:[...], inbox:"path"}` — looks like success but nothing was written. R1-F4 covers synthesis staleness at the triage/disposition layer; this is the orthogonal serialize layer.
  - **Assumptions / conditions:** Addressed by R2-F1 (serialize silent-skip), R2-F2 (ConfirmModal phase transition), R2-F4 (state-machine `session_id` carry).
  - **Suggested improvements:** see numbered suggestions below.

- **Ask 6 — M1 additive `backlog_markdown` field: could it break an exact-key-matching consumer?**
  - **Summary answer:** Partial — no existing code exact-key-matches the triage dict, but R1-F6 / R1-S6 are the right mitigations; nothing new to add here beyond endorsing those.
  - **Rationale:** Grounded grep of the triage response consumers finds only `TriageReport.to_dict()` used in `_triage`. No test or downstream consumer does `set(keys) == {...}`. The risk is forward-looking (a new consumer added later). R1-S6's superset regression test is the right mitigation.
  - **Assumptions / conditions:** Risk is future-consumer, not current-code.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Risks | high | FR-10: add an acceptance criterion that if `serialize_buffer` returns an undrained-inbox skip (non-empty `write.skipped`), the route MUST return a non-200 error (409 "undrained inbox — drain via Apply mode first") rather than 200 with `staged:[...]` and `inbox:"path"`. Surface this in the panel as a distinct "inbox occupied" state. | `serialize_buffer` is no-clobber per `vipp_seam.py:196` — an existing inbox is not overwritten, and `WriteResult.skipped` is set. `_serialize` ignores `result["write"]` entirely and returns 200. The panel then guides the operator to Apply mode, which previews a stale inbox, not the just-serialized one. This is a silent data-loss path at the write surface. | FR-10 ("surface `{staged, rejected, inbox}`") — add error case | Serialize once (inbox now exists); serialize again without draining; assert the panel shows an "inbox occupied — drain first" state and the inbox file is byte-identical to after the first serialize. |
| R2-F2 | Interfaces | medium | FR-8: add an acceptance criterion that the ConfirmModal's confirm handler MUST transition the panel phase (e.g. to `"extracting"`) **synchronously before** the async confirm POST, so the modal closes immediately on the first click and a second click cannot fire a second confirm. Reference: `FacilitatePanel.handleConfirm` calls `setPhase('polling')` before `await proxyPost`. | Without this, double-clicking the confirm button issues two concurrent POSTs to `/stakeholders/extract`. The non-atomic `lookup+record_start` in `_extract` (pre-fix) means both pass. Even with the server fix (R2-S1 in plan), the requirements should independently mandate UX-level prevention. | FR-8 ("confirm button shows the estimate") — add: "the confirm action MUST close the modal synchronously (phase transition before await) so double-click cannot issue two requests" | Mock extract endpoint with a 200ms delay; click confirm twice rapidly; assert exactly one POST issued. |
| R2-F3 | Data | medium | FR-10: require that when `serialize` returns with `inbox` non-null, the panel display the `inbox` path so the operator can verify which file Apply mode will drain. Currently FR-10 says "guides the operator to Apply mode" but a second serialize (different session) could produce a different inbox path — the operator needs to know which inbox is staged. | The VIPP inbox path is project-scoped (one inbox per project), so there is only one inbox. However, making the path visible confirms to the operator that the file was actually written, and disambiguates from the undrained-inbox 409 case (R2-F1) where `inbox` is null. | FR-10 ("surface `{staged, rejected, inbox}`") — add: "display `inbox` path when non-null; null means nothing was written" | Assert panel renders the `inbox` path string in the serialize result; assert when 409 (undrained), no path is shown. |
| R2-F4 | Architecture | medium | FR-8/9/10: add a cross-cutting requirement that `session_id` obtained from the extract response must be preserved in React component state and threaded to all subsequent disposition and serialize calls; losing it (panel re-render, navigation) MUST surface as a recoverable error ("re-triage to re-establish session"), not a silent 400. | `_serialize` returns 400 if `session_id` is absent or empty. The requirements describe FR-8/9/10 as sequential steps but do not specify the session continuity contract across those steps. A full-page Grafana refresh between M4 and M5 would lose the extracted `session_id` and cause an opaque 400. | FR-8 → FR-10, add a cross-cutting note: "the `session_id` from extract response is the anchor for disposition and serialize; a lost anchor MUST prompt re-triage rather than silently failing" | Clear React state between M4 and M5; assert the panel shows a clear "re-triage needed" state, not an error boundary. |

**Endorsements:**

- **R1-F1** (high — extract double-spend concurrency): Endorsed. Grounded: `IdempotencyStore.reserve()` already exists and is the atomic check-and-set fix. R2-F2 is the complementary UX-layer requirement.
- **R1-F3** (critical — `domain` missing from staged rows): Endorsed. This is the single blocking data-flow gap. `Recommendation.domain` is stored in the dataclass; omitting it from the extract response is the sole cause.
- **R1-F4** (high — triage/disposition staleness, no checksum guard): Endorsed. Orthogonal to R2-F1 (which covers serialize-layer staleness).
- **R1-F5** (medium — `rejected[]` not surfaced in serialize): Endorsed. Grounded: `_serialize` does return `result["rejected"]` (list of `(value_path, reason)` tuples), so the data is available; the requirement just needs to mandate its display.
