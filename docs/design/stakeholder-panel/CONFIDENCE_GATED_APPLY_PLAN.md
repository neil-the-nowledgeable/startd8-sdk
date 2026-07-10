# Confidence-Gated Apply (#8) — Implementation Plan

**Version:** 1.1 (Post-CRP — 2 rounds triaged)
**Date:** 2026-07-10
**Requirements:** `CONFIDENCE_GATED_APPLY_REQUIREMENTS.md` v0.4

---

## Planning discoveries (feeds the reflection)

Grounded against `synthesis_bridge/stage.py`, `kickoff_experience/vipp_seam.py`, `vipp/apply.py`,
`vipp/models.py`, `stakeholder_run_server.py` (`_serialize`/`_apply_preview`), `consensus.py`.

| Draft assumption | Planning revealed | Impact |
|------------------|-------------------|--------|
| Consensus can be computed at apply time | **No session provenance survives to apply** — proposals carry only `{value_path, value}`; `preview_dispositions` returns `{proposal_id, kind, params, value_path}`. The source facilitation `session_id` is **lost at serialize**. | FR-2 becomes the *enabling mechanism*: thread `source_session_id` serialize → envelope → preview. The naive "just surface #6" was infeasible (the >30% revision). |
| Adding provenance might break the ratify challenge | `ProposalEnvelope.content_checksum` covers **proposals only** (`checksum_payload()` = proposals; seq/ts excluded); the ratify `content_hash` is over `{proposal_id, kind, params}`. | A **top-level** `source_session_id` is hash-safe by construction → **FR-7 satisfied**, no gate change. |
| One envelope shape | **Two** constructors: `vipp_seam.serialize_buffer` (write dict) + `vipp/models.ProposalEnvelope` (read `from_json`/`to_dict`). Both need the field; `from_json` `.get(..., "")` default → old inboxes = graceful n/a. | Touch both; NR-3/FR-6 hold. |
| Compute in vipp | Keep `vipp/apply.py` **pure** of facilitation/consensus deps. | `PreviewResult` surfaces `source_session_id` (provenance passthrough); the **route** computes consensus (OQ-4 resolved). |
| `_serialize` knows the session | Confirmed — `_serialize` request already carries `session_id` (loads `ProposalStore(project, session_id)`). | Threading is a small pass-through, no new lookup. |

## Approach (FLAG only — sponsor resolved OQ-1)

### M1 — Server: thread provenance + compute consensus at preview  [FR-1/2/2a/2b/6/7/8/9]
1. **Write + one-session (R1-S1/R1-S6/R2-S4):** `serialize_buffer(buffer, root, *,
   source_session_id=None, …)` → top-level `"source_session_id"`. `serialize_accepted_to_vipp(…,
   source_session_id=None)` forwards it at the **real** call site (`stage.py`'s
   `serialize_buffer(buffer, project_root, …)`); `_serialize` route passes its `session_id`.
   **Distinct-session guard:** if `{r.session_id for staged recs}` has >1 non-empty value → pass `""`
   (→ n/a), never an arbitrary one (also re-checked on the `force=True` path).
2. **Read (R1-S2/R1-F4):** `ProposalEnvelope` += `source_session_id: str = ""` (`from_json` `.get(...,"")`
   → old inbox = `""`; `to_dict`). Round-trip test asserts survival **write → from_json → to_dict** (read side).
3. **Surface (FR-9):** `PreviewResult` += `source_session_id: str = ""`; `preview_dispositions` sets it
   from the envelope. vipp stays pure; **not echoed** in the HTTP body.
4. **Compute (FR-1/2a/6):** in `_apply_preview`, **after** `preview_dispositions` succeeds, a **separate
   inner try** (never the existing preview→502 try):
   - **path-safety (R2-F1/R2-S1):** validate `source_session_id` via `_safe_session_component`
     (reject `/ \ . ..`) **before** load; unsafe/empty → n/a. Also harden `KickoffPanelStore._path` with
     the guard (defense in depth — all callers benefit).
   - **lazy imports** of `compute_consensus`/`CHALLENGER_IDS`/`KickoffViewService` inside the route (R1-S4).
   - `compute_consensus(load(sid).rounds, exclude_role_ids=CHALLENGER_IDS)`; except → n/a + `logger.warning`
     (only on a real exception, not benign n/a — R1-S7).
   - `"consensus"` is **always present** (n/a-shaped when uncomputable — FR-1); `source_session_id` not echoed.
5. **M2 fingerprint (R2-S2):** add `"source_session_id"` to `exclude_keys` in `vipp/assistant.py`'s
   `checksum_json_excluding(...)` (it's metadata, like `generated_at`) — no cache-bust.
6. **Tests (real, pytest):** (a) envelope carries the id; 2-session recs → `""`; (b) read-side round-trip;
   old inbox → `""`; (c) real label on a completed inbox; `../..`/unknown sid → n/a **and the store is
   never loaded with the unsafe component**; `load` raising → 200+n/a; `preview_dispositions` raising →
   still 502; (d) **FR-7:** `content_checksum` + ratify `content_hash` byte-identical with/without the id;
   (e) **FR-8:** `checksum_json_excluding` identical for envelopes differing only in the id;
   (f) **import-graph:** `import startd8.vipp` pulls neither `consensus` nor `kickoff_view`.

### M2 — Plugin: render consensus on the apply preview  [FR-5]
- `types.ts::ApplyPreviewResult` += `consensus?: ConsensusSignal` (the type #6 added).
- `ApplyPanel.tsx` preview screen: a consensus chip (reuse the #6 pattern) with the synthetic/lexical
  caveat; when a session was present but n/a, show a muted **"consensus: n/a (reason)"** — don't silently
  hide (R2-F4). **Real verify:** `npm ci && typecheck && lint && test && build`.

### M3 — DROPPED (sponsor chose FLAG-only)
No soft-ack / gate. #8 is purely additive signal; the ratify path is untouched.

### M4 — Docs
- README (ApplyPanel consensus behavior) + roadmap (#8 shipped).

## Requirement → step trace
FR-1→M1.4 · FR-2→M1.1–3 · FR-2a→M1.4 · FR-2b→M1.1 · FR-3→(FLAG only; M3 dropped) · FR-4→M1.4/M2 ·
FR-5→M2 · FR-6→M1.4 · FR-7→M1.6(f-test d) · FR-8→M1.5 · FR-9→M1.3/M1.4.

## Risks
- **R1 — write-boundary security.** Mitigated: provenance is a top-level field outside both hashes
  (test d); the challenge/nonce/strict/confinement gate is untouched.
- **R2 — two envelope shapes drift.** Mitigated: field in both + a **read-side** round-trip test (b).
- **R3 — coupling vipp to facilitation.** Avoided: consensus in the route via lazy imports; import-graph test (f).
- **R4 — path traversal (CRP R2-F1, HIGH).** An inbox-controlled `source_session_id` → arbitrary file
  read via `KickoffPanelStore._path`. Mitigated: `_safe_session_component` guard before load **and** on
  the store itself (test c).
- **R5 — M2 cache-bust (CRP R2-F2).** New envelope field would bust the negotiate fingerprint. Mitigated:
  excluded from `checksum_json_excluding` (test e).
- **R6 — misleading provenance (CRP R2-F3).** `source_session_id` is unverified metadata (spoofable in the
  token boundary). Accepted non-goal: disclosed in FR-4/NR-5 + the panel caveat; not cryptographically bound.
- **R7 — force-overwrite mixes sessions (CRP R2-S4).** Mitigated: the distinct-session guard (M1.1) runs
  on the force path too → `""` → n/a rather than a wrong label.

*v1.1 — Post-CRP. CRP caught 2 security issues (path-traversal R4, M2 cache-bust R5) + the one-session
invariant + normative hash-placement. M1 grew accordingly; #6 reuse stays thin. Dispositions in Appendix A.*

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
| R2-S1 | Path-safety guard before load | sonnet | → M1.4 + store hardening; test c. HIGH. | 2026-07-10 |
| R2-S2 | Exclude id from M2 fingerprint | sonnet | → M1.5; test e. | 2026-07-10 |
| R1-S1 | Name the real `stage.py` call site | opus | → M1.1. | 2026-07-10 |
| R1-S6 (+R2-S4) | Distinct-session guard (+force path) | opus/sonnet | → M1.1; test a. | 2026-07-10 |
| R1-S2 | Read-side round-trip test | opus | → M1.2; test b. | 2026-07-10 |
| R1-S3 | Separate inner try (not preview→502) | opus | → M1.4; test c. | 2026-07-10 |
| R1-S5 | Two-hash invariance regression | opus | → M1.6 test d. | 2026-07-10 |
| R1-S4 | Lazy imports + import-graph test | opus | → M1.4; test f. | 2026-07-10 |
| R1-S7 | Warn-log on genuine-exception n/a | opus | → M1.4. | 2026-07-10 |
| R2-S3 | Decide echo → no-echo | sonnet | → M1.3/M1.4 (FR-9). | 2026-07-10 |
| R2-S5 | M2 fingerprint invariance test | sonnet | → M1.6 test e. | 2026-07-10 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All S-suggestions accepted — grounded; 2 security-critical. | 2026-07-10 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-07-10

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-07-10 00:00:00 UTC
- **Scope**: Write-boundary plan review — provenance threading (M1.1–3), consensus-at-preview (M1.4), hash-safety regression (M1.5), layering (R3), and the two-envelope drift guard (R2). Grounded against the real `serialize_buffer`, `serialize_accepted_to_vipp`, `ProposalEnvelope`, `preview_dispositions`, `_apply_preview`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Interfaces | high | M1.1 lists three call sites for the write thread (`serialize_buffer`, `serialize_accepted_to_vipp`, `_serialize`) but the **actual call site** `write = serialize_buffer(buffer, project_root)` in `stage.py:100` passes no kwargs — spell out that this line must forward `source_session_id`, or the field is added to the signature yet never populated on the real path. | The threading breaks silently at the one un-named call site; the signature default `None` masks it (no error, just empty provenance → always n/a). | M1.1 (add the `stage.py:100` call site explicitly) | Assert the serialized envelope from `serialize_accepted_to_vipp` (not just a direct `serialize_buffer` call) carries a non-empty `source_session_id`. |
| R1-S2 | Data | high | M1.2 adds `source_session_id` to `from_json`/`to_dict` but does not note that `from_json` **silently drops unknown keys within a protocol major** (`models.py:55`). The round-trip test (R2) must read the value back through `from_json`, not just confirm it was written — a write-only assertion passes even if the read model never wired it. | Guards against the exact drift R2 exists to prevent; a write-only test gives false confidence. | M1.2 + R2 (strengthen the round-trip assertion) | write via `serialize_buffer(source_session_id="s-42")` → `ProposalEnvelope.from_json(read_inbox())` → assert `.source_session_id == "s-42"`; and an old-inbox dict (no key) → `""`. |
| R1-S3 | Risks | high | M1.4's "best-effort" catch must be scoped so **only** the consensus block degrades — `_apply_preview` already wraps `preview_dispositions` in a try→502 (`stakeholder_run_server.py:841`). Adding consensus compute *inside* that same try would convert a consensus failure into a 502 (violates FR-6). Specify a **separate inner try** around the `KickoffViewService.load` + `compute_consensus`, after a successful preview, whose except-path yields consensus n/a and never re-raises. | A misplaced catch turns an advisory-signal failure into a hard preview failure — the precise "false-500 on the preview" the focus file warns against. | M1.4 (add "separate best-effort try, after preview succeeds; catch broadly → n/a") | Test: monkeypatch `KickoffViewService.load` to raise → preview returns 200 with consensus n/a; monkeypatch `preview_dispositions` to raise → still 502 (unchanged). |
| R1-S4 | Architecture | medium | R3 keeps `vipp/apply.py` pure by computing consensus in the route, but the plan doesn't state **where** `CHALLENGER_IDS` / `KickoffViewService` are imported. They must be imported lazily inside `_apply_preview` (matching `_serialize`/`_run`'s lazy-import pattern) so the vipp package still never transitively pulls facilitation at import time. | An eager module-level import in the route file could re-introduce the coupling R3 claims to avoid, depending on import graph. | R3 / M1.4 (note "lazy import inside `_apply_preview`") | Import-graph test: `import startd8.vipp` does not import `stakeholder_panel.consensus` or `kickoff_view`. |
| R1-S5 | Validation | medium | M1.5's regression is described as "content_hash + challenge unchanged vs before" but the strongest, cheapest assertion is **byte-identical `content_checksum` AND ratify `content_hash` with the field present vs absent** — assert both hashes are invariant to `source_session_id`, not just that the ratify path "works". This directly encodes FR-7. | Pins FR-7 as an executable invariant rather than a narrative claim; catches an accidental move of the field into a per-proposal dict. | M1.5 (reword the regression to the two-hash invariance assertion) | Compute `_content_checksum(proposals)` and `_content_hash(seq, would_apply)` for an envelope with and without a populated `source_session_id`; assert equality. |
| R1-S6 | Data | medium | The plan does not address the **multi-session degradation**: `serialize_accepted_to_vipp` iterates recs each with `rec.session_id`. Add a step: before serializing, if `{r.session_id for r in staged recs}` has >1 distinct non-empty value, pass `source_session_id=""` (→ n/a) rather than the route's request id. | The route's `session_id` and the recs' `session_id` can disagree; pinning the request id would mislabel consensus provenance (focus-file ask 5). | M1.1 (add the distinct-session check) | Unit test: stage recs across two sessions, serialize, assert envelope `source_session_id == ""` and preview consensus n/a. |
| R1-S7 | Ops | low | M1.4 should **log** (via `get_logger`) when consensus falls back to n/a *because compute raised* (vs the benign old-inbox/≤1-rateable n/a), so operators can distinguish "signal genuinely n/a" from "signal silently broke". | Best-effort swallowing hides real regressions in the consensus path; a single `logger.warning` on the exception branch preserves observability without changing behavior. | M1.4 (add a warn-on-exception line in the except branch) | Assert a warning is logged when `compute_consensus`/`load` raises; no log on the benign n/a paths. |

**Endorsements:** none (first round).

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-10

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-10 00:00:00 UTC
- **Scope**: Adversarial second-pass — plan-level stress-test. Focus: (a) M2 fingerprint mutation from adding `source_session_id` to the on-disk envelope JSON (omitted from the plan); (b) `KickoffPanelStore._path` path-traversal risk introduced by M1.4 (new load call with inbox-controlled input); (c) `force=True` / CLI serialize bypass of the one-session invariant; (d) `source_session_id` echo in preview response (plan adds it to `PreviewResult` but doesn't decide if the route surfaces it). Grounded against `vipp/assistant.py:85-87`, `kickoff_view/store.py:27-28`, `stakeholder_panel/transcript.py:36-44`, `cli_panel.py:491`.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Security | high | M1.4 must validate `source_session_id` against a path-safety guard (mirror `TranscriptStore._safe_session_component`: reject `/`, `\\`, `.`, `..`) before passing it to `KickoffViewService.load()`. Add an explicit step: *"before calling `load(sid)`, assert `sid` passes a path-safety check identical to `_safe_session_component` in `transcript.py:36-44`; an unsafe value → skip load, yield consensus n/a."* | `KickoffPanelStore._path` constructs `root / f"{session_id}.json"` with no guard (`store.py:27-28`), unlike `TranscriptStore`. A `source_session_id` of `../../etc/passwd` in the inbox causes `_path` to resolve outside the project root and `.read_text()` fires before Pydantic parse fails. The inbox is 0600 operator-written, but a token holder can craft a `session_id` at serialize time that becomes the stored value. | M1.4 (add "path-safety check on `sid` before load, unsafe → n/a" step) | Test: inbox with `source_session_id = "../../../nonexistent"` → preview 200 with consensus n/a AND `KickoffPanelStore.load` was not called with that value; also test a traversal that would resolve to an existing file. |
| R2-S2 | Data | medium | M1 (the whole milestone) does not address the **M2 fingerprint cache-bust** introduced by adding `source_session_id` to the on-disk envelope JSON. `vipp/assistant.py:85-87` computes `checksum_json_excluding(inbox_path, exclude_keys=("generated_at", "envelope_seq"))` — `source_session_id` is not in the exclusion list, so any post-#8 inbox has a different fingerprint than a pre-#8 inbox with identical proposals, breaking the "recognizably a no-op" short-circuit (models.py:143). Add a step: either (a) add `source_session_id` to the `exclude_keys` tuple in `vipp/assistant.py:86` (same rationale as `generated_at` — it is metadata, not proposal content), or (b) document a one-time cache-invalidation migration note for operators upgrading from pre-#8. | Violates the Mottainai principle: a content-identical re-serialize after upgrade forces full LLM re-negotiate unnecessarily. The fix is one tuple element. | M1 (add "exclude `source_session_id` from M2 fingerprint `exclude_keys`" step) or Risk section (document as migration cost if (b)) | Verify: serialize identical proposals pre- and post-#8 → `checksum_json_excluding` output is identical (if (a) chosen). |
| R2-S3 | Architecture | medium | The plan does not resolve whether `source_session_id` is **echoed in the HTTP preview response body** or consumed server-side only. M1.3 adds it to `PreviewResult`, and M1.4 reads it, but the route (`_apply_preview`, stakeholder_run_server.py:850-858) currently returns a fixed dict without it. If the route surfaces `source_session_id` to the plugin, it crosses the token boundary as a session identifier (low-sensitivity, but a decision). If not, `PreviewResult.source_session_id` is purely internal. The plan must specify: *"the preview response body DOES / DOES NOT include `source_session_id`."* | R1-F6 (untriaged) identified this gap in the requirements; the plan must also resolve it since the route is where the decision is implemented. Omitting it leaves the implementer to guess, and the two choices produce different plugin contracts and different security properties. | M1.3 or M1.4 (add explicit note on preview response shape re: `source_session_id`) | Verify: contract test asserts the preview JSON either includes or omits `source_session_id` deliberately; TypeScript `ApplyPreviewResult` type agrees. |
| R2-S4 | Risks | medium | Risk R2 ("two envelope shapes drift") is mitigated by a round-trip test, but the plan does not address the **`force=True` bypass path** in `serialize_buffer`. `cli_panel.py:491` calls `serialize_accepted_to_vipp` (which calls `serialize_buffer`) without `force`, so the route's M1d 409 guard holds for the HTTP path. However, `serialize_buffer` accepts `force=True` and nothing prevents a future caller (or an existing CLI path) from passing `force=True`, overwriting an undrained inbox with proposals from a DIFFERENT session. This would make `source_session_id` wrong without any error. Add to the Risks section: *"R4 — `force=True` overwrites the inbox, potentially mixing the committed `source_session_id` with proposals from a prior session's inbox; the one-session invariant is not re-checked after a force overwrite."* Mitigation: `serialize_accepted_to_vipp` should validate that all staged recs' `session_id`s match the `source_session_id` being committed (R1-S6 already calls for the distinct-session check, but the force path is an additional bypass). | A `force=True` overwrite can silently create an inbox whose `source_session_id` is wrong, producing a misleading (high) consensus display on a low-consensus set of proposals. | Risks section (add R4 with mitigation) | Test: force-overwrite an inbox with recs from session B while `source_session_id = session A`; verify the plan's distinct-session check (R1-S6) also fires on the force path. |
| R2-S5 | Validation | low | M1.5 regression ("content_hash + challenge unchanged vs before") does not cover the **M2 fingerprint invariant** introduced by R2-S2. If `source_session_id` is correctly added to `exclude_keys`, a test should assert that. If it is NOT excluded (migration-cost choice), a test should assert the fingerprint DOES change (so future refactors don't accidentally re-exclude it and restore the old behavior). Add to M1.5: *"a test asserts `checksum_json_excluding(inbox, exclude_keys=(...))` is identical for an envelope with vs without `source_session_id` populated (if excluded), OR documents and tests the expected fingerprint change (if not excluded)."* | Without this test, an inadvertent change to `exclude_keys` in a future refactor would silently re-introduce unnecessary re-negotiates (or silently fix a cache-busting bug without anyone noticing). | M1.5 (add M2 fingerprint invariance assertion to the regression suite) | Verify: two inbox files differing only in `source_session_id` → `checksum_json_excluding` output is equal (excluded) or unequal (not excluded, documented). |

**Endorsements:**

- **R1-S1**: Endorse strongly — `stage.py:100` is the real production call site; the plan must name it explicitly or the threading is silently broken.
- **R1-S3**: Endorse — the separate inner try/except is required; merging consensus failure into the preview's existing try→502 violates FR-6.
- **R1-S5**: Endorse — the two-hash-invariance assertion (not just "ratify path works") is the right regression form.
- **R1-S6**: Endorse — the distinct-session check is necessary; R2-S4 above extends it to the force path.

---

## Requirements Coverage Matrix — R1

*Analysis only (claude-opus-4-8, 2026-07-10). Maps each FR → plan step → coverage.*

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 — consensus in `_apply_preview` `{label,score,n,basis}` | M1.4 | Partial | n/a-path JSON shape not pinned (key omitted vs `score:null`) — see R1-F3/R1-F4. |
| FR-2 — thread `source_session_id` serialize→envelope→preview | M1.1–M1.3 | Partial | `stage.py:100` call site not named (R1-S1); multi-session degradation unhandled (R1-S6/R1-F5). |
| FR-3 — FLAG not block (gate untouched) | Approach header; M3 DROPPED | Full | — |
| FR-4 — honest framing (synthetic/lexical) | M1.4/M2 (reuses #6 framing) | Full | — |
| FR-5 — Grafana panel renders consensus, hidden when n/a | M2 | Partial | "hidden when n/a" depends on the unpinned n/a contract (R1-F3). |
| FR-6 — graceful n/a; best-effort never breaks preview | M1.4 | Partial | Best-effort catch scope not specified → 502 risk (R1-S3); transcript-load raise not named (R1-F2). |
| FR-7 — do not weaken apply security (top-level, outside hash) | M1 + M1.5 | Partial | Regression is narrative, not the two-hash-invariance assertion (R1-S5); placement not forbidden normatively (R1-F1). |
| NR-1 — no new consensus logic | M1.4 (reuses `compute_consensus`) | Full | — |
| NR-2/NR-3 — no server refusal / no hash change | Approach; R1 | Full | — |
| NR-4 — Grafana-only | M2 | Full | — |

## Requirements Coverage Matrix — R2

*Analysis only (claude-sonnet-4-6, 2026-07-10). Adversarial second-pass — maps each FR → plan step → R2 coverage assessment, focusing on gaps not caught by R1.*

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 — consensus in `_apply_preview` `{label,score,n,basis}` | M1.4 | Partial | Preview response body shape unresolved: plan adds `source_session_id` to `PreviewResult` but does not say if the route echoes it — R2-S3. |
| FR-2 — thread `source_session_id` serialize→envelope→preview | M1.1–M1.3 | Partial | Path-traversal risk at M1.4 load call (R2-S1); `force=True` bypass allows a different session's id to overwrite the field (R2-S4); M2 fingerprint busted by new field (R2-S2). |
| FR-3 — FLAG not block (gate untouched) | Approach header; M3 DROPPED | Full | — |
| FR-4 — honest framing (synthetic/lexical) | M1.4/M2 | Partial | `source_session_id` binding is unverified metadata (token-holder can substitute any session) — not disclosed in the plan; see R2-F3 in requirements doc. |
| FR-5 — Grafana panel renders consensus, hidden when n/a | M2 | Partial | UX for "session present but n/a" vs "no session" is unspecified — R2-F4 in requirements doc. |
| FR-6 — graceful n/a; best-effort never breaks preview | M1.4 | Partial | Path-traversal via unsafe `source_session_id` causes a read (not a crash, but a file-system access) before degrading to n/a — R2-S1. Best-effort catch scope still unresolved from R1-S3. |
| FR-7 — do not weaken apply security | M1 + M1.5 | Partial | M2 fingerprint cache-bust from new envelope field not addressed (R2-S2). Hash-safety of proposals themselves is confirmed clean (R1 ask 1 answered). |
| NR-1 — no new consensus logic | M1.4 | Full | — |
| NR-2/NR-3 — no server refusal / no hash change | Approach; M3 DROPPED | Full | — |
| NR-4 — Grafana-only | M2 | Full | — |
