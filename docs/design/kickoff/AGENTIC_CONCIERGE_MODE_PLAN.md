# Agentic Concierge Mode — Implementation Plan

**Version:** 1.1 (Post-CRP R1)
**Date:** 2026-06-26
**Status:** Draft
**Requirements:** `AGENTIC_CONCIERGE_MODE_REQUIREMENTS.md` (v0.3)

> **Headline.** Feasible and correctly shaped, with one structural correction and one hard
> prerequisite the v0.1 missed:
> - **Buffer is host-owned, not session-side.** Attaching the proposal buffer to `AgenticSession`
>   (`agentic.py:368`) couples the generic loop to Concierge — wrong layering. It lives on
>   `KickoffChat`, injected into `build_kickoff_registry` and captured in the `propose_action` closure.
> - **The system prompt + banner forbid exactly what this feature needs.** `KICKOFF_SYSTEM_PROMPT`
>   (`chat.py:40-51`) says "you have exactly three tools" and "you must never claim to … log friction";
>   `POSTURE_BANNER` (`chat.py:34`) says "I cannot edit files." These MUST be rewritten or the model
>   contradicts the new `propose_action` tool. v0.1 never mentioned this.
> The whole feature is a thin propose-buffer over the existing typed write path — no new session
> plumbing, no new write engine.

## Milestones

### M1 — Proposal core (FR-AC-1/2/4) — *host-owned buffer + read-effect tool*
- **`ProposedAction`** (FR-AC-1): frozen dataclass (`kickoff_experience/proposals.py` or `chat.py`),
  `kind ∈ {instantiate, friction, capture}` + `params: dict`. Stores **params, not a prebuilt plan**
  (OQ-7) so the plan is rebuilt against live state at confirm.
- **Host-owned `ProposalBuffer`** — a bounded list (mirror `_IntentStore._MAX`, `web.py:236`) on
  `KickoffChat` (`chat.py:141`), NOT on `AgenticSession`.
- **`propose_action` tool** (FR-AC-2): added to `build_kickoff_registry` (`chat.py:97`),
  `effect_class="read"`. Handler **validates** (`validate_friction`/`validate_posture`
  `concierge_apply.py:95,110`; `value_path ∈ cfg.allowed_value_paths()` `manifest.py`), **appends** a
  `ProposedAction` to the closure-captured buffer, returns a short ack. Writes nothing. Dispatch only
  gates `effect_class` then calls the handler (`agentic.py:214,220`); the return is truncated for the
  model but the **side-effect append is unaffected** (`agentic.py:223-224`).
  - Signature: `build_kickoff_registry(project_root, *, proposal_sink=None)` — when `None`, the tool is
    omitted, keeping the **pure read-only** `kickoff chat` distinct (FR-NEW-5).
  - **Acceptance (R1-S4):** re-run validation at **confirm** time, not only at propose (also gates M4).
    The allow-list / posture set can change between propose and confirm (config edited, package state
    advanced), so propose-time validation is stale by confirm. `build_capture_plan` /
    `build_instantiate_plan` MUST **re-assert the allow-list** and **fail closed with a typed code**.
    Test: narrow `allowed_value_paths()` between propose and confirm → assert apply is refused with a
    typed code, not applied.
- **Floor guard** (FR-AC-4): extend `test_chat_and_ranking.py:40-62` — registry is exactly
  `{survey, assess, field_states, propose_action}`, all `read`; calling `propose_action`'s handler
  changes no files and records one buffer entry; no write path reachable.
  - **Acceptance (R1-S5):** extend the floor guard to the **agentic** build path
    (`build_kickoff_registry(root, proposal_sink=buf)`): assert the 4-tool set all `read`, the handler
    writes **zero files**, and a golden snapshot of the rewritten prompt contains "a human confirms"
    and **not** "exactly three tools". **Also bound propose calls per-turn** (with M5 / FR-NEW-4): a
    per-turn cap, or drain-before-evict, so `_MAX` evict-oldest never silently drops a live proposal
    mid-turn before the per-turn drain. Test: emit N > `_MAX` proposals in one turn → assert none
    evicted before drain (or a hard per-turn cap fires).

### M2 — System prompt / banner rewrite (FR-NEW-1) — *hard prerequisite*
- Rewrite `KICKOFF_SYSTEM_PROMPT` + `POSTURE_BANNER` (`chat.py:34-51`): the loop still never writes,
  but it now has a fourth tool `propose_action`; instruct the model to call it to recommend an action,
  and that **a human confirms before anything is applied**. Remove "exactly three tools" and "never
  claim to log friction." (Done as its own milestone because it gates M1's tool being usable.)
- **Acceptance (R1):** **split / parameterize by mode — do NOT rewrite the single constant.** A single
  propose-aware prompt would advertise `propose_action` to the pure `kickoff chat` session (M1's
  `proposal_sink=None`) that never registers it → unknown-tool calls (`agentic.py:215`). Add a
  **propose-aware variant** selected when `proposal_sink` is present; the pure path keeps the original
  read-only text. **Prompt-text assertion:** pure registry's system prompt **excludes** "propose_action";
  the agentic one **includes** it (and "a human confirms"); the pure session lists 3 tools.

### M3 — Confirm-then-apply gate + REPL surface (FR-AC-3/5/6/8/9)
- **Extend `run_kickoff_repl`** (`chat.py:184`, FR-NEW-3): add `pending: () -> list[ProposedAction]`,
  `confirm: ConfirmFn` (reuse `tui_concierge.ConfirmFn`, `None` → fail closed, NR-5), `apply_proposal:
  (ProposedAction) -> str` (returns the typed apply code).
- After each turn: drain `pending()`; per proposal `emit_line` a summary, `confirm(...)`; `None` → fail
  closed, `True` → `apply_proposal`, `False` → discard. **The host prints the apply code** — proposed-
  vs-applied is structural (FR-AC-9 / OQ-6), the model's prose is advisory.
- **`apply_proposal` builds the plan at confirm time against live state** (OQ-7): instantiate
  (`build_instantiate_plan` re-stat) / friction (`build_friction_entry`) → `apply_concierge_plan`
  (`concierge_apply.py:123`); capture → `build_capture_plan` → `apply_capture` (stale-file guard
  `capture.py:370`). The buffer entry **is** the one-time intent (pop-on-consume) — no `_IntentStore`
  in the TUI.
  - **Acceptance (R1-S2):** define the buffer-entry lifecycle on apply **failure** — "pop-on-consume"
    means pop on **terminal success or explicit discard**, NOT pop-before-apply. The web
    `_IntentStore.consume` pops eagerly (`web.py:246`); **don't copy that** — a `STALE_FILE` /
    `WRITE_REFUSED` apply would silently consume the proposal and block retry. On retriable failure the
    proposal is **retained / re-offered**. Test: simulate `STALE_FILE` on confirm → proposal remains
    pending/re-offered, no double-write on retry.
- **Stale-proposal outcome** (FR-NEW-2): when live state changed (package now complete; `STALE_FILE`),
  render the typed outcome, not a silent no-op.
  - **Acceptance (R1-S3):** extend the outcome handling to **`PARTIAL`** and **`WRITE_REFUSED`** for
    instantiate — `apply_concierge_plan` is non-atomic (`concierge_apply.py:148-156`: "some files may
    still have been written before/after the failing one" → `PARTIAL`). The host renders the
    **written/skipped split** + a **recovery affordance (resume)**, not just the "package now complete"
    case. Test: inject a per-file block mid-instantiate → assert host shows `PARTIAL` + counts and a
    recovery affordance.
- **Wire `chat_cmd`** (`cli_kickoff.py:219`): a new `new_agentic_kickoff_chat(...)` builds the registry
  **with** the proposal sink; pass `confirm=_questionary_confirm` + the new callables. Likely a new
  command `kickoff concierge-chat` (or `kickoff chat --agentic`) so plain `kickoff chat` stays pure.

### M4 — Capture proposals (FR-AC-7) — *low marginal cost*
- Apply path exists (`apply_capture`). Add propose-time `value_path` allow-list validation +
  confirm-time `build_capture_plan` (re-reads inputs, resolves staleness). OQ-4 → in v1.

### M5 — Observability + cost (FR-AC-10/11)
- Add `EV_PROPOSAL_MADE/CONFIRMED/DISCARDED` (`telemetry.py:37`), kind/code attrs only. **Caveat
  (FR-AC-11 narrowed):** `emit()` does not enforce `CONCIERGE_EVENT_ATTR_ALLOWLIST` (`telemetry.py:109`)
  — bounded attrs are discipline, not a guarantee. Cost line already exists (`chat.py:154`); FR-AC-10's
  extra "posture line" is dropped (overspecified).
- **Acceptance (R1-S5, FR-NEW-4):** the bounded-buffer `_MAX` evict-oldest policy must **not** drop a
  live proposal before the per-turn drain — bound propose calls **per turn** (a per-turn cap, or
  drain-before-evict). Eviction is for abandoned previews, not single chatty turns. (Guard test lives
  with the M1 floor guard.)

### M6 (deferred phase) — Web agentic panel (OQ-2)
Defer. Adds LLM-in-request-path + streaming + the apply gate; reuses web `_IntentStore`/CSRF/loopback
(`web.py:228,450`). Separate phase.

## Dependency order
```
M2 (prompt rewrite) ─> M1 (proposal core) ─> M3 (confirm+REPL) ─> M4 (capture) ; M5 (o11y)
```
M2 first (it unblocks the tool being coherent); M1; then M3 (the user-visible flow); M4/M5 layer on.

## Open questions still open
- **OQ-2 (web agentic panel)** — deferred to M6/a later phase; TUI-only for v1.

All other OQs resolved — see Requirements §0.

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
| R1-S1 | Split/parameterize prompt+banner by mode (not a single rewrite); propose-aware variant selected by proposal_sink; add prompt-text assertion | R1 / claude-opus-4-8 | Merged into M2 | 2026-06-26 |
| R1-S2 | Define buffer-entry lifecycle on apply failure: pop on terminal success/discard, not pop-before-apply; retain on STALE_FILE/WRITE_REFUSED | R1 / claude-opus-4-8 | Merged into M3 | 2026-06-26 |
| R1-S3 | Extend stale-outcome handling to PARTIAL + WRITE_REFUSED for non-atomic instantiate; render written/skipped + resume | R1 / claude-opus-4-8 | Merged into M3 | 2026-06-26 |
| R1-S4 | Re-run validation at confirm time (allow-list/posture can change); build_capture/instantiate_plan re-assert + fail closed | R1 / claude-opus-4-8 | Merged into M1 (gates M4) | 2026-06-26 |
| R1-S5 | Extend floor guard to agentic build path (4-tool, zero-write, prompt snapshot) + bound propose calls per-turn so evict never drops a live proposal | R1 / claude-opus-4-8 | Merged into M1 and M5 | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-06-26

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-26 17:55:00 UTC
- **Scope**: Plan sequencing/interfaces/validation for the propose buffer, confirm-then-apply gate, prompt rewrite, surface boundary. Grounded against `chat.py`, `agentic.py`, `concierge_apply.py`, `capture.py`, `web.py`.

**Executive summary (top risks / opportunities / blocking gaps):**
- **Blocking:** M2 "Rewrite `KICKOFF_SYSTEM_PROMPT` + `POSTURE_BANNER`" in place breaks FR-NEW-5 — the pure `kickoff chat` (M1's `proposal_sink=None`) would still present a propose-aware prompt/banner for a tool it never registers → unknown-tool calls (`agentic.py:215`).
- **High:** M3's "buffer entry IS the one-time intent (pop-on-consume)" doesn't define lifecycle on apply **failure** (STALE_FILE / PARTIAL / WRITE_REFUSED). Web pops in `consume` *before* apply (`web.py:246`); copying that loses the proposal on transient failure.
- **High:** M3/FR-NEW-2 stale handling omits the non-atomic **PARTIAL** instantiate outcome (`apply_concierge_plan`, `concierge_apply.py:148`).
- **High:** M1/M4 validate at *propose* time only; the allow-list / package-state can change before confirm — no re-validation at apply (allow-list TOCTOU named in the focus).
- **Gap:** M2 has no test/acceptance; the floor guard (M1) pins only the pure 3-tool registry, not the agentic 4-tool one.

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | Split (or parameterize) the prompt + banner by mode instead of rewriting the single constant. M2 says "Rewrite `KICKOFF_SYSTEM_PROMPT` + `POSTURE_BANNER` (`chat.py:34-51`)", but M1 keeps pure `kickoff chat` via `proposal_sink=None`. A single propose-aware prompt would advertise `propose_action` to the pure session that never registers it. Add a propose-aware variant selected when `proposal_sink` is present; pure path keeps the original read-only text. | Without this, FR-NEW-5's purity is silently violated and the pure session emits unknown-tool calls. M2 currently rewrites the shared constant unconditionally. | M2 ("Rewrite `KICKOFF_SYSTEM_PROMPT` + `POSTURE_BANNER`") | Test: pure registry's system prompt excludes "propose_action"; agentic one includes it; pure session lists 3 tools. |
| R1-S2 | Risks | high | Define the buffer entry lifecycle on apply **failure** in M3. "pop-on-consume" must mean pop on **terminal success or explicit discard**, not pop-before-apply. The web `_IntentStore.consume` pops eagerly (`web.py:246`); reusing that pattern means a STALE_FILE / WRITE_REFUSED apply silently consumes the proposal and the user cannot retry, while a half-applied PARTIAL leaves no re-confirmable intent. | M3 asserts the buffer entry is the one-time intent but never states when it is removed relative to a failed apply — the load-bearing detail for both double-write safety and retriability. | M3 ("The buffer entry **is** the one-time intent (pop-on-consume)") | Test: simulate STALE_FILE on confirm; assert proposal remains pending/re-offered and no double-write on retry. |
| R1-S3 | Risks | high | Extend the FR-NEW-2 stale-outcome handling in M3 to cover **PARTIAL** and **WRITE_REFUSED** for instantiate. `apply_concierge_plan` is non-atomic (`concierge_apply.py:148-156`: "some files may still have been written before/after the failing one" → `PARTIAL`). The host must render the written/skipped split and define resume vs re-propose, not just the "package now complete" case. | M3 only names "package now complete; STALE_FILE"; the real multi-file write path can half-apply on confirm, leaving an inconsistent package with no plan-level recovery. | M3 ("Stale-proposal outcome (FR-NEW-2): when live state changed ... render the typed outcome, not a silent no-op") | Test: inject a per-file block mid-instantiate; assert host shows `PARTIAL` + counts and a recovery affordance. |
| R1-S4 | Security | high | Re-run validation at **confirm** time, not only at propose time. M1's handler validates `value_path ∈ cfg.allowed_value_paths()` / `validate_posture` / `validate_friction`, but `apply_proposal` (M3/M4) must re-validate against live config: the allow-list or posture set can change between propose and confirm (config edited, package state advanced). Make `build_capture_plan`/`build_instantiate_plan` re-assert the allow-list and fail closed with a typed code. | The focus explicitly asks about the "allow-list changed" TOCTOU. Propose-time validation is stale by confirm time; only confirm-time re-validation closes it. | M1 ("Handler **validates** ... `value_path ∈ cfg.allowed_value_paths()`") + M4 ("propose-time `value_path` allow-list validation") | Test: narrow `allowed_value_paths()` between propose and confirm; assert apply is refused with a typed code, not applied. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S5 | Validation | medium | Extend the M1 floor guard to the **agentic** build path and add an M2 prompt-text assertion. The guard (`test_chat_and_ranking.py:40-62`) pins the pure 3-tool registry; add a case on `build_kickoff_registry(root, proposal_sink=buf)` asserting exactly `{survey,assess,field_states,propose_action}` all `read`, the handler writes zero files, and a golden snapshot of the rewritten prompt contains "a human confirms" and **not** "exactly three tools". Also bound propose calls **per turn** so FR-NEW-4 eviction (`_MAX`, evict-oldest) never silently drops a pending proposal mid-turn before the per-turn drain. | M2/M1 currently have no acceptance test for the security-critical surface; the eviction policy (good for abandoned web previews) can silently lose a live proposal in a single chatty turn. | M1 ("Floor guard (FR-AC-4): extend `test_chat_and_ranking.py:40-62`") + M5 (FR-NEW-4) | Test: agentic registry shape + zero-write handler; prompt snapshot; emit N>`_MAX` proposals in one turn and assert none evicted before drain (or a hard per-turn cap). |

**Endorsements / Disagreements:** none (R1 — no prior untriaged items).

---

## Requirements Coverage Matrix — R1

Analysis only (no triage). Maps each requirement to the plan milestone(s) that address it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-AC-1 (ProposedAction) | M1 | Full | — |
| FR-AC-2 (read-effect propose tool, host buffer) | M1 | Partial | No confirm-time re-validation (R1-S4); per-turn drain vs eviction unspecified (R1-S5) |
| FR-AC-3 (confirm-then-apply gate) | M3 | Partial | Double-confirm/idempotency + failure lifecycle undefined (R1-S2, R1-F5) |
| FR-AC-4 (read-only floor + guard) | M1 | Partial | Guard pins pure registry only, not the agentic 4-tool set / zero-write handler (R1-S5, R1-F6) |
| FR-AC-5 (agentic friction) | M3 | Partial | No verbatim display of drafted prose before confirm (R1-F4) |
| FR-AC-6 (agentic instantiate) | M3 | Partial | Non-atomic PARTIAL outcome unhandled (R1-S3, R1-F2) |
| FR-AC-7 (agentic capture) | M4 | Partial | STALE_FILE guard window collapses under confirm-time rebuild (R1-F1) |
| FR-AC-8 (TUI surface) | M3 | Full | — |
| FR-AC-9 (wording, structural) | M3 | Full | — |
| FR-AC-10 (cost disclosure) | M5 | Full | — |
| FR-AC-11 (observability, bounded attrs) | M5 | Full | Allow-list is discipline not enforced — documented, accepted |
| FR-NEW-1 (prompt/banner rewrite) | M2 | Partial | In-place rewrite breaks pure-chat purity; needs mode-pairing (R1-S1, R1-F3); no acceptance test (R1-S5) |
| FR-NEW-2 (stale-proposal outcome) | M3 | Partial | Outcome set omits PARTIAL/WRITE_REFUSED (R1-S3, R1-F2) |
| FR-NEW-3 (extend REPL signature) | M3 | Full | — |
| FR-NEW-4 (bounded buffer) | M1 | Partial | Evict-oldest can drop a live proposal mid-turn (R1-S5) |
| FR-NEW-5 (keep `kickoff chat` pure) | M1 | Partial | Prompt/banner purity not preserved by M2 (R1-S1, R1-F3) |
| NR-1..NR-5 (no autonomous/MCP/new-engine writes; no `--yes`) | M1/M3 | Full | Preserved by read-only floor + human-gated apply |
| OQ-2 (web agentic panel) | M6 | Deferred | Explicitly out of scope for v1 |
