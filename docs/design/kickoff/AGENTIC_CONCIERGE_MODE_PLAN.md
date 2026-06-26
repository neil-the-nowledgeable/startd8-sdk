# Agentic Concierge Mode — Implementation Plan

**Version:** 1.0 (Post-planning, paired with Requirements v0.2)
**Date:** 2026-06-26
**Status:** Draft
**Requirements:** `AGENTIC_CONCIERGE_MODE_REQUIREMENTS.md` (v0.2)

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
- **Floor guard** (FR-AC-4): extend `test_chat_and_ranking.py:40-62` — registry is exactly
  `{survey, assess, field_states, propose_action}`, all `read`; calling `propose_action`'s handler
  changes no files and records one buffer entry; no write path reachable.

### M2 — System prompt / banner rewrite (FR-NEW-1) — *hard prerequisite*
- Rewrite `KICKOFF_SYSTEM_PROMPT` + `POSTURE_BANNER` (`chat.py:34-51`): the loop still never writes,
  but it now has a fourth tool `propose_action`; instruct the model to call it to recommend an action,
  and that **a human confirms before anything is applied**. Remove "exactly three tools" and "never
  claim to log friction." (Done as its own milestone because it gates M1's tool being usable.)

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
- **Stale-proposal outcome** (FR-NEW-2): when live state changed (package now complete; `STALE_FILE`),
  render the typed outcome, not a silent no-op.
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
