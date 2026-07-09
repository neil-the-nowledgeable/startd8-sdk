# Agentic Workbook — Implementation Plan

**Version:** 1.2 (OQ-2/OQ-3 user decisions + FR-6b Loki depth)
**Date:** 2026-07-09
**Status:** Ready for implementation (CRP R1 applied; OQ-2/OQ-3 resolved)
**Requirements:** `AGENTIC_WORKBOOK_REQUIREMENTS.md` (v0.5)

---

## 1. Approach

Reframe the shipped v2 audience Workbook (`build_workbook_v2`) into a **read-only agentic cockpit** by
(a) giving the agentic session a **durable snapshot** and (b) wrapping the existing rows in a
**TabsLayout** with two new read-only tabs that mirror that snapshot + the existing VIPP inbox. No live
backend, no new store, classic path untouched. Live chat (FR-11) is a separate, deferred track behind
the endpoint decision.

**Load-bearing reuse (all shipped):**
- `dashboard_creator/v2/` — `build_sectioned_v2`, `Section`, `TabsLayout`, `RowsLayoutRow`, `text_panel`, conditional rendering, `CustomVariable`, `provision_v2`, `workbook_v2_uid` (M0–M5).
- `kickoff_experience/portal_spec_v2.py:build_workbook_v2` — the Status content + audience variable + shield logic.
- `kickoff_experience/vipp_seam.py` — `inbox_path`, `serialize_buffer`/`maybe_serialize_buffer`, `ProposalEnvelope` (durable proposals; `kickoff chat` persists via `cli_kickoff.py:677`); already read at `portal_build.py:117`.
- `kickoff_experience/state.py` — `KickoffState`/`FieldState` oracle.
- `agents/agentic.py:AgenticSession` + `chat.py:cost_line()` — the session to snapshot.

---

## 2. Milestones

### M1 — Session snapshot capability (FR-1, FR-4) — *the agentic-capability update*
- Add a `session_snapshot` model (with a **`schema_version`** field; R1-S5) + writer: serialize `AgenticSession` turns (role, text, tool-call **name** only), cost (model, tokens, cost), `generated_at`, pending-proposal ids.
- **Redaction — named + tested (R1-S2):** invoke `fde.redaction.redact` (the redactor the VIPP inbox already uses, `vipp_seam.py:_warn_if_secret`) over every persisted string *before* serialization.
- Persist to `.startd8/kickoff/agentic-session.json` at session end via **temp-then-rename** (R1-S6: interrupted overwrite leaves the prior snapshot valid; concurrent sessions = last-writer-wins). Presence-gated; absent ⇒ absent.
- **Hook the existing session-end seam with atomicity (R1-S1):** `cli_kickoff.py:677` already calls `maybe_serialize_buffer(chat.buffer, …)` to persist proposals to the inbox (OQ-4 resolved — FR-2 is reuse). Add the snapshot write **beside** that call. **Ordering + failure isolation:** persist the inbox first, then the snapshot; a snapshot-write failure MUST leave the inbox intact and leave **no** partial `agentic-session.json` (temp-then-rename guarantees this). **FR-2 needs no new inbox wiring** — only the transcript is a genuine gap.
- **Full-transcript Loki emission (FR-6b, OQ-2):** alongside the snapshot write, emit each turn as a **redacted** structured-JSON log line via `get_logger("startd8.kickoff.transcript")` with `project`/`session_id`/`turn_index`/`role` fields (redact *before* logging — same `fde.redaction.redact`). Reaches Loki through the file→Promtail bridge; no new endpoint (does not cross the FR-11 gate). Best-effort: a logging failure never breaks session exit and never blocks the snapshot/inbox writes.
- Tests: snapshot round-trips; **planted-secret test** (a known API-key-shaped token in a turn's text + tool-call arg-kind is absent from the written bytes **and** from the emitted transcript log line; R1-S2); absent-session ⇒ no file; cost line matches `chat.py`; **fault-injection** (raise mid-snapshot-write → inbox complete, no partial snapshot; R1-S1); interrupted overwrite leaves prior snapshot readable (R1-S6); Loki-emit failure is swallowed (session still exits, snapshot still written).

### M2 — Snapshot read-model (FR-3)
- One builder `build_agentic_view(project_root) -> AgenticView` folding `KickoffState` + FR-1 snapshot + FR-2 inbox. Pure, deterministic, `$0`. Single derivation point (parity oracle).
- **Declare the `AgenticView` schema** (fields + types) and the **snapshot version contract (R1-S5):** an unknown `schema_version` degrades to a typed "unsupported snapshot" empty-marker, never a mis-parse or traceback.
- Empty-state semantics baked in (FR-10): no snapshot / no proposals / **malformed snapshot** ⇒ typed empty/unavailable markers, not exceptions.
- Tests: parity (same view drives dashboard + a future TUI); empty states; partial (snapshot present, inbox empty); **bumped `schema_version` ⇒ typed unsupported-marker** (R1-S5); **truncated/invalid snapshot ⇒ honest unavailable-state** (R1-F6).

### M3 — Cockpit tabs (FR-5, FR-6, FR-7, FR-9)
- **Sub-step (a) — capture the Status golden FIRST, on unrefactored code (R1-S4):** before any refactor, commit a Status-content golden fixture generated from the *current* `build_workbook_v2`. The refactor's test compares against that committed artifact (a golden regenerated from refactored code proves nothing).
- **Sub-step (b) — refactor:** wrap the existing rows as a **Status** `Section`/tab; add **Assistant** (capped-tail transcript markdown from M2 **+ a Loki `logs` panel** for full depth, FR-6/FR-6b) and **Proposals** (`table` from M2 with per-row confirm command) tabs via `build_sectioned_v2`/`TabsLayout`. Confirm commands are rendered id-bound + shell-escaped (FR-7).
- **Loki logs panel (FR-6b):** verify the v2 panel model can express a `loki`-datasource-backed `logs` panel (uid `loki`) with a static LogQL target scoped to project + newest session_id; if the v2 emit path lacks a datasource-backed panel builder, add a minimal one (the v1 path already has `PanelType.LOGS`). Panel is additive; empty when Loki absent (graceful degrade).
- Keep `-v2` UID; classic path untouched (FR-9). Idempotent re-provision via `provision_v2`.
- Tests: three tabs present; Status bytes unchanged vs the **pre-refactor committed golden** (R1-S4); **confirm-command round-trip** (render for P → parse back → target `id == P.id`, with a `value_path` containing spaces/quotes; R1-S7); classic `build_kickoff_portal_spec` byte-identity untouched (module-membership/`co_names` structural assertion — avoid brittle source-string checks).

### M4 — Audience-conditional cockpit (FR-8)
- Apply conditional rendering to Assistant/Proposals per the `audience` variable. **OQ-3 resolved:** Beginner sees a *simplified* Proposals tab (reduced columns, confirm command retained as the teaching moment) — **not hidden**; Beginner's Assistant tab shows the capped tail only (FR-6b logs panel hidden). Advanced/Intermediate get full detail.
- **Embed vs reference decided (R1-S3):** the cockpit **embeds (bakes)** snapshot bytes into panels (NR-1 posture) — it does not reference the file via a live datasource. Therefore byte-identity is asserted over a **frozen snapshot fixture** so audience is the only variable.
- Verify **byte-identity**: for one project + one fixed snapshot, one JSON identical except the variable `current` — the shipped dynamic-dashboards FR-9 AC.
- Tests: three audiences over a **frozen snapshot fixture** differ only in the variable default (byte-diff harness from the audience Workbook; R1-S3).

### M5 — CLI wiring + live verification
- `startd8 kickoff portal --dynamic` emits the cockpit; `kickoff chat` writes the snapshot (M1). Confirm the existing `--provision` path pushes the v2 cockpit.
- **Enumerated live assertions (R1-S8)** on Grafana 13.1.0 (do not delegate to an unspecified harness): (1) all **three tabs render**; (2) toggling the `audience` variable changes **only** the active default (no other panel diff); (3) a **seeded inbox row appears** in the Proposals tab; (4) conditional rendering hides/shows the Beginner-shielded sections; (5) the **Loki `logs` panel renders** and (given a seeded `startd8.kickoff.transcript` log line) returns the full transcript for the newest session. Reuse the dynamic-dashboards live-check harness for transport, add these named checks on top.
- Docs: update `GRAFANA_KICKOFF_PORTAL_*` + `DYNAMIC_DASHBOARDS_*` cross-refs to point at this cockpit as the M6/M7 consumer.

### M6 — Live chat (FR-11) — *DEFERRED, separate track, gated*
- Not scheduled in this plan. When the endpoint/exposure decision is made: fork the CC panel React shell, rewire to a loopback `AgenticSession` endpoint (survey/assess/propose + confirm), harden via the `consult --serve` pattern. Tracked as future work; no code in M1–M5.

---

## 3. Requirements → Milestone Traceability

| Req | Milestone |
|-----|-----------|
| FR-1 Session snapshot | M1 |
| FR-2 Reuse VIPP inbox | M1 (verify/wire) |
| FR-3 Read-model | M2 |
| FR-4 Cost/posture transparency | M1 (snapshot) + M3 (render) |
| FR-5 Tabbed cockpit | M3 |
| FR-6 Assistant tab (capped tail) | M3 |
| FR-6b Full-transcript Loki depth | M1 (emit) + M3 (logs panel) |
| FR-7 Proposals tab | M3 |
| FR-8 Audience-conditional | M4 |
| FR-9 Additive/idempotent | M3 |
| FR-10 Empty states | M2 (semantics) + M3 (render) |
| FR-11 Live chat | M6 (deferred) |

---

## 4. Risks

- **R1 — ~~`propose_action` may be buffer-only~~ (OQ-4, RESOLVED).** *Dissolved by source verification:* `kickoff chat` already persists the buffer to the inbox at session end (`cli_kickoff.py:677`), and `portal_build.py:117` reads it. The Proposals tab has real data with no new wiring. Residual: the transcript is not yet persisted — folded into M1.
- **R2 — Refactoring `build_workbook_v2` risks the Status byte-golden.** *Mitigation:* wrap, don't rewrite; add a Status-content regression golden before the tab refactor.
- **R3 — Transcript size in a Grafana text panel** (OQ-2, resolved). *Mitigation:* cap rendered turns in the baked panel; full transcript stays in the snapshot file **and** is served on demand via the FR-6b Loki `logs` panel. New residual **R7**.
- **R7 — Loki dependency for full-depth transcript (FR-6b).** The full-depth panel needs Loki reachable + the transcript log lines shipped (file→Promtail lag). *Mitigation:* additive/graceful-degrade — the baked capped-tail panel (FR-6) always renders offline; the logs panel is empty, not broken, when Loki is absent. Redaction runs before emit so Loki holds no secrets.
- **R4 — Byte-identity across audiences** is easy to break when adding conditional tabs. *Mitigation:* reuse the dynamic-dashboards byte-diff AC harness in M4.
- **R5 — Scope creep toward live chat.** *Mitigation:* FR-11/M6 is fenced out of the v1 set; the endpoint decision is an explicit prerequisite.
- **R6 — Single-file snapshot overwrite/concurrency (R1-S6).** An interrupted overwrite or a concurrent second `kickoff chat` could feed M2 a truncated/racy file. *Mitigation:* temp-then-rename + last-writer-wins (folded into M1); malformed-file honest state (M2, FR-10).

---

## 5. Validation

- Unit: snapshot round-trip + redaction (M1); read-model parity + empty states (M2); tab structure + confirm commands + classic-untouched (M3); audience byte-identity (M4).
- Integration/live: `kickoff chat` → snapshot → `kickoff portal --dynamic` → provision to Grafana 13.1.0 → visual round-trip of the three tabs + audience toggle (M5).
- Regression: classic Workbook golden unchanged; existing v2 audience Workbook tests stay green.

---

*v1.0 — initial plan from the post-planning requirements. Six milestones; M1–M5 are the read-only cockpit (v1), M6 (live chat) is deferred behind the endpoint/exposure gate.*

*v1.1 — Post-CRP R1 triage. All 8 S-suggestions ACCEPTED + applied: M1 gained named redaction + planted-secret test + write atomicity/ordering + temp-then-rename; M2 gained the `AgenticView` schema + version-degrade path; M3 gained the pre-refactor golden ordering gate + confirm-command round-trip test; M4 decided embed-not-reference + frozen-fixture byte-diff; M5 enumerated the live assertions; new risk R6 (overwrite/concurrency). See Appendix A.*

*v1.2 — OQ-2/OQ-3 user decisions folded in. OQ-2 (full transcript) → FR-6b: M1 emits redacted transcript turns to Loki via `get_logger`; M3 adds a `loki`-datasource `logs` panel to the Assistant tab for full depth (additive, graceful-degrade, no new endpoint → FR-11 gate uncrossed); new risk R7. OQ-3 (Beginner Proposals) → M4 shows a simplified (not hidden) Proposals tab. Source-verification pass confirmed all named symbols; 3 deltas recorded (redact() tuple return; build_workbook_v2 uses RowsLayout so M3 wraps into a Status Section; --dynamic in cli_concierge.py vs chat seam in cli_kickoff.py:677).*

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
| R1-S1 | Write atomicity for co-located snapshot + inbox | R1 (claude-opus-4-8[1m]) | Merged into **M1**: inbox-first ordering, temp-then-rename, snapshot-fail leaves inbox intact + no partial file; fault-injection test. | 2026-07-09 |
| R1-S2 | Name redaction fn + planted-secret test | R1 | Merged into **M1**: `fde.redaction.redact` + planted-secret assertion on written bytes. | 2026-07-09 |
| R1-S3 | Embed-vs-reference + frozen-fixture byte-diff | R1 | Merged into **M4**: embed (bake); byte-diff over a frozen snapshot fixture. | 2026-07-09 |
| R1-S4 | Pre-refactor golden ordering gate | R1 | Merged into **M3**: golden captured on unrefactored code (sub-step a) + compared as committed artifact. | 2026-07-09 |
| R1-S5 | `AgenticView` schema + snapshot `schema_version` degrade | R1 | Merged into **M1** (field) + **M2** (schema + unknown-version typed marker). | 2026-07-09 |
| R1-S6 | Single-file overwrite/concurrency semantics | R1 | Merged into **M1** (temp-then-rename, last-writer-wins) + new risk **R6**. | 2026-07-09 |
| R1-S7 | Confirm-command copy-exact round-trip test | R1 | Merged into **M3** test bullet (render→parse→assert id; spaces/quotes fixture). | 2026-07-09 |
| R1-S8 | Enumerate M5 live assertions | R1 | Merged into **M5**: 3-tabs / audience-only-diff / seeded-inbox-row / conditional-hide checks. | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | R1 | All 8 R1 S-suggestions accepted. | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-09

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-09 21:30:00 UTC
- **Scope**: Plan review (S-prefix) — dual-document, weighted toward FR-1 snapshot seam/schema, byte-identity under tabs×audience, Proposals-as-confirm-surface honesty, and the M3 Status-golden refactor risk.

**Executive summary (top risks / gaps):**
- M1 co-locates snapshot + inbox writes at `cli_kickoff.py:677` but does not specify **atomicity/failure isolation** — a snapshot-write failure must not orphan or corrupt the already-persisted inbox (or vice-versa).
- M1 asserts "apply the loop's existing redaction before write" but names **no concrete redaction function/module** and no test that a planted secret is scrubbed — the one genuinely new persistence path is the one most exposed to PII leakage.
- M4 verifies audience byte-identity, but the **snapshot content varies per session** (transcript/cost); the plan never states whether the emitted cockpit JSON embeds snapshot bytes or references them — this is the real threat to "identical bytes except the audience variable current."
- M3's Status regression golden is described as "add … before the tab refactor" but there is **no ordering gate** ensuring the golden is captured on unrefactored code; if captured after, it validates nothing.
- M2's `build_agentic_view` is the parity oracle, but the plan gives **no schema for `AgenticView`** and no versioning story for the FR-1 snapshot it folds — a snapshot schema drift silently degrades the read-model.
- OQ-1 retention (last-session-only) means each `kickoff chat` **overwrites** the prior snapshot; the plan does not call out concurrent-session or interrupted-write behavior for a single-file store.
- Proposals tab renders a CLI command as a string (FR-7/NR-2) but the plan does not require the command be **copy-exact and escaped**; a mis-rendered `id` yields a command that silently targets the wrong proposal.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Data | high | Specify write atomicity for the co-located snapshot + inbox handoff at `cli_kickoff.py:677`: define ordering (inbox first, snapshot second, or a shared temp-then-rename), and require a snapshot-write failure to leave the inbox intact and the snapshot absent (never a half-written `agentic-session.json`). | M1 makes "transcript + proposals persist together, atomically, from one place" a goal but never defines what atomicity means across two files; a crash between the two writes must be recoverable. | M1, after the "Hook the existing session-end seam" bullet | Fault-injection test: raise mid-snapshot-write, assert inbox is complete and no partial snapshot file remains |
| R1-S2 | Security | high | Name the exact redaction function/module M1 invokes before serialization and add a test that plants a known secret (API-key-shaped token) in a turn's text and a tool-call arg-kind and asserts it is absent from the persisted `agentic-session.json`. | "Apply the loop's existing redaction" is unanchored; the snapshot is a new on-disk artifact that persists transcript text — the highest-value leak surface in this feature. | M1 tests bullet | Unit test asserting planted secret does not appear in written bytes; grep-style assertion on the file |
| R1-S3 | Data | high | State explicitly whether the emitted cockpit JSON **embeds** snapshot bytes (transcript/cost) or **references** the snapshot file, and confirm which choice preserves the FR-8 byte-identity guarantee. If embedded, the byte-diff harness must run against a **fixed snapshot fixture** so audience is the only variable. | M4 reuses the audience byte-diff AC, but a per-session-varying snapshot embedded in the JSON would make three-audience byte-identity structurally impossible to assert without pinning the snapshot. | M4, before the "Tests" bullet | Byte-diff harness across 3 audiences over a **frozen** snapshot fixture; assert diff == audience `current` only |
| R1-S4 | Validation | medium | Add an explicit ordering gate to M3: capture the Status-content golden as a first sub-step on the **unrefactored** `build_workbook_v2` (e.g., a committed fixture generated pre-refactor), and make the refactor's test compare against that committed artifact — not a golden regenerated from the refactored code. | R2 mitigation says "add a Status-content regression golden before the tab refactor," but nothing prevents capturing it after; a same-commit golden tautologically passes. | M3, split the "Status bytes unchanged" test bullet into (a) capture golden pre-refactor, (b) assert post-refactor | CI check that the golden fixture's git blob predates the refactor commit, or golden lives in a separate prior commit |
| R1-S5 | Interfaces | medium | Define the `AgenticView` schema (fields + types) and give the FR-1 snapshot a `schema_version` field; M2's read-model should reject/degrade-gracefully on an unknown snapshot version rather than mis-parsing. | M2 is the single derivation oracle but has no declared contract; snapshot format drift (a near-certainty as the agentic loop evolves) would silently corrupt every rendered surface. | M2, first bullet (`build_agentic_view` signature) | Unit test: an snapshot with a bumped `schema_version` yields a typed "unsupported snapshot" empty-marker, not a traceback |
| R1-S6 | Risks | medium | Address single-file overwrite semantics for OQ-1's last-session-only store: specify that a new `kickoff chat` overwrites via temp-then-rename, and note behavior if two `kickoff chat` sessions run against the same project root concurrently (last-writer-wins is acceptable but must be stated). | The plan treats the snapshot as a durable artifact but never states its overwrite/concurrency contract; an interrupted overwrite could leave the cockpit reading a truncated file. | R3 (transcript size) or a new R6 risk row in §4 | Test: interrupted overwrite leaves prior valid snapshot readable (temp-then-rename semantics) |
| R1-S7 | Interfaces | medium | Require the Proposals-tab confirm command to be rendered from the proposal `id` with exact escaping (shell-safe quoting of any `value_path`/target), and add a test that the rendered command, if copy-pasted, resolves to the same proposal `id` it was rendered for. | FR-7's honesty depends on the command being copy-exact; a mis-escaped `value_path` or wrong `id` produces a command that looks actionable but targets the wrong (or no) proposal — worse than an empty state. | M3, "Proposals table shows correct confirm commands" test bullet | Round-trip test: render command for proposal P, parse it back, assert target `id` == P.id; include a `value_path` with spaces/quotes |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S8 | Ops | medium | M5 claims live-verify "reusing the dynamic-dashboards live-check harness" but the cockpit adds tabs the harness may not assert; specify the concrete live assertions (three tabs render, audience toggle switches default, Proposals table populated from a seeded inbox) rather than delegating to an unspecified harness. | "Reuse the harness" hides whether the harness actually checks tab structure and conditional rendering; without named assertions M5 can pass while the new tabs are broken in Grafana. | M5, split "Live-verify on Grafana 13.1.0" into enumerated assertions | Live checklist: 3 tabs visible; toggling `audience` var changes only the active default; seeded inbox row appears in Proposals |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; no prior untriaged suggestions exist.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement (from `AGENTIC_WORKBOOK_REQUIREMENTS.md` v0.3) to plan coverage.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 Durable session snapshot | M1 | Partial | Redaction function unnamed + untested (R1-S2); write atomicity vs inbox unspecified (R1-S1); no `schema_version` on the snapshot (R1-S5). |
| FR-2 Reuse VIPP inbox | M1 (verify/wire) | Full | Source-verified reuse; no new wiring needed. |
| FR-3 Single snapshot read-model | M2 | Partial | `AgenticView` schema/contract undeclared; unknown-version degrade path unstated (R1-S5). |
| FR-4 Cost & posture transparency | M1 + M3 | Full | Cost line mirrored from `chat.py`; "snapshot — not a live agent" disclosure carried in render. |
| FR-5 Tabbed cockpit | M3 | Full | Wrap-not-rewrite into TabsLayout; Status/Assistant/Proposals sections specified. |
| FR-6 Assistant tab | M3 (render), OQ-2 | Partial | Progressive-disclosure/cap for long transcripts deferred to OQ-2; rendering-depth rule not yet committed. |
| FR-7 Proposals tab (confirm affordance) | M3 | Partial | Confirm-command copy-exactness/escaping not required or tested (R1-S7). |
| FR-8 Audience-conditional cockpit | M4 | Partial | Byte-identity harness does not account for per-session-varying snapshot content; embed-vs-reference undecided (R1-S3). |
| FR-9 Additive & idempotent | M3 | Full | `-v2` UID kept; classic path byte-untouched; idempotent `provision_v2`. |
| FR-10 Honest empty states | M2 (semantics) + M3 (render) | Full | Typed empty markers baked into read-model; hint text specified. |
| FR-11 Live agentic chat (deferred) | M6 (deferred) | Full | Correctly fenced out of v1 behind the endpoint/exposure gate; requirements captured. |
