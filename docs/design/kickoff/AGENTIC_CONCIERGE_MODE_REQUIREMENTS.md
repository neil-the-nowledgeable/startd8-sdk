# Agentic Concierge Mode Requirements

**Version:** 0.4 (added §E provider/model config, via the reflective loop)
**Date:** 2026-06-26
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Plan:** `AGENTIC_CONCIERGE_MODE_PLAN.md` (v1.0)
**Related:** `WELCOME_MAT_CONCIERGE_MODE_REQUIREMENTS.md` (v0.4),
`INTERACTIVE_KICKOFF_EXPERIENCE_REQUIREMENTS.md` (v0.5)

---

## 0. Planning Insights (Self-Reflective Update)

> What changed between v0.1 and v0.2. The planning pass read the real `agents/agentic.py` +
> `kickoff_experience/` code and confirmed the core mechanism is feasible, but found **one hard
> prerequisite and one layering correction** the v0.1 missed, narrowed a privacy claim, and resolved
> all 7 open questions.

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| The loop is free to propose actions once we add the tool | `KICKOFF_SYSTEM_PROMPT` says "you have **exactly three tools**" + "you **must never claim to … log friction**"; `POSTURE_BANNER` says "I cannot edit files" (`chat.py:34-51`). Adding `propose_action` **contradicts the prompt**. | **Added FR-NEW-1** (rewrite the prompt/banner) — a hard prerequisite, its own milestone (M2). |
| **FR-AC-2:** the proposal buffer is **session-side** (on `AgenticSession`) | `AgenticSession` is the *generic* loop (`agentic.py:368`); coupling it to Concierge proposals is wrong layering. The registry is built by `build_kickoff_registry` with closures (`chat.py:97`). | **Reframed FR-AC-2 → host-owned buffer** on `KickoffChat`, injected into the registry builder. |
| **OQ-1:** a read tool with a recording side-effect may be "awkward" | `ToolSpec.handler` is an arbitrary callable; dispatch only gates `effect_class` then calls it (`agentic.py:214,220`); the return is truncated for the model but the **side-effect append is unaffected** (`:223`). | **OQ-1 resolved → propose-tool path is clean.** |
| **FR-AC-8:** `run_kickoff_repl` can surface + confirm proposals | Its signature is only `ask_sync/read_input/emit_line/cost_line` (`chat.py:184`) — no confirm, no proposals accessor. | **Added FR-NEW-3** (extend the REPL signature) — understated as an implementation detail. |
| Confirmed proposal binds to a one-time intent like the web | `_IntentStore` is web/CSRF-only (`web.py:228`); the TUI `run_concierge` confirms-then-applies inline (`tui_concierge.py:81`). | **OQ-3 resolved → the buffer entry IS the one-time intent** in the TUI (pop-on-consume); no `_IntentStore`. |
| Proposal carries a prebuilt plan | Instantiate is stat-based & cheap to rebuild (`writes.py:81`); capture re-reads with a `STALE_FILE` guard at apply (`capture.py:370`). | **OQ-7 resolved → store params, build plan at confirm against live state.** Added FR-NEW-2 (surface a stale-proposal outcome). |
| **FR-AC-9 / OQ-6:** the wording rule needs policing the model | The host already owns the result render (`tui_concierge.py:88`, `web.py:522`); apply returns a typed `code`. | **OQ-6 resolved → enforce structurally** (host prints the code; model prose is advisory). |
| **FR-AC-11:** the telemetry attribute allow-list is enforced | `emit()` filters only `None`; it does **not** apply `CONCIERGE_EVENT_ATTR_ALLOWLIST` (`telemetry.py:64,109`). | **Narrowed FR-AC-11** — bounded attrs are discipline, not a guarantee. |
| Capture proposals (FR-AC-7) are materially harder | The apply path (`apply_capture`) already exists; only a `value_path` allow-list check is new. | **OQ-4 resolved → capture is in v1.** |

**Resolved open questions:**
- **OQ-1 → propose via a read-effect tool** (handler records to a host buffer, writes nothing).
- **OQ-2 → TUI-only for v1**; web agentic panel deferred (M6).
- **OQ-3 → host-owned buffer**; in the TUI the buffer entry is the one-time intent (no `_IntentStore`).
- **OQ-4 → capture proposals in v1** (apply path exists; +1 allow-list check).
- **OQ-5 → allow multiple proposals, confirm serially** (buffer is a bounded list — FR-NEW-4).
- **OQ-6 → proposed-vs-applied is structural** (host prints the apply code).
- **OQ-7 → store params, rebuild the plan at confirm** against live state.

---

## 1. Problem Statement

The Welcome Mat now has three onboarding surfaces, but the **conversational** one can only *talk*,
not *act*:

| Surface | What it does today | Gap |
|---------|--------------------|-----|
| **`kickoff chat`** (just hosted) | Read-only agentic loop — survey / assess / field_states; explains state, advises next step | Can recommend "create a kickoff package" or "log this friction" in **prose**, but cannot turn that into a confirmable action — the user must leave the chat and run the deterministic forms |
| **Concierge mode** (web + `kickoff concierge` TUI) | Deterministic forms / questionary — survey panel, instantiate, log-friction | Not conversational; the human drives every field. No LLM assistance drafting friction or recommending the next write |
| **Agentic write boundary** (FR-CM-8 / NR-5) | The loop is **propose-only**: it drafts prose; a human applies via `apply_concierge_plan` / the safe-writer | "Propose" is unstructured — there is no *object* the loop emits that a confirm-gate can consume, so the recommendation can't flow into an apply without retyping |

So the conversational assistant can diagnose ("you're blocked on the `Language` field; the
conventions block is malformed") but cannot offer **"shall I draft the fix / scaffold the package /
log that friction?"** as a one-confirm action. The deterministic Concierge and the agentic chat are
two disconnected halves.

**What should exist:** an **agentic Concierge mode** — the conversational assistant *conducts* the
onboarding. It surveys/assesses/reports (already possible), then **structurally proposes** write
actions (instantiate-kickoff, log-friction, and field capture) that a human confirms before
`apply_concierge_plan` runs. The loop **never applies a write itself, never over MCP** — it emits a
typed *proposal* the human gate consumes, preserving the read-only floor exactly.

The enabling mechanism already fits the architecture: a tool's `effect_class` drives the
default-deny policy, and a **read-effect "propose" tool** (its handler records a structured proposal
and writes nothing) is permitted under the read-only allow-list. The loop calls it to *signal* an
action; the host shows pending proposals; the human confirms; the existing typed write path applies.

---

## 2. Guiding Principles (inherited)

- **P1 — The loop never writes.** No write tool is ever registered in the agentic loop. Proposals are
  emitted via a **read-effect** tool that records intent only. Application is a separate, human-gated
  step (FR-CM-8 / NR-5 are preserved, not relaxed).
- **P2 — Reuse the typed write path.** Confirmed proposals apply through `apply_concierge_plan`
  (instantiate/friction) and the M6 capture path (field values) — no new write engine, no new safety
  surface. The same one-time-intent / typed-reason-code machinery applies.
- **P3 — Never MCP, never autonomous.** Proposals are not applied over MCP; a proposal never
  auto-applies (no "auto-confirm", no `--yes` in v1).
- **P4 — Honest wording.** The assistant may say "I propose / recommend / drafted"; it must never say
  "saved / created / logged" before an apply succeeds (inherits the confirmed-write wording rule).

---

## 3. Requirements

### A. The proposal mechanism

- **FR-AC-1 — Structured proposed action.** Define a typed `ProposedAction` the loop can emit:
  `kind` ∈ `instantiate | friction | capture`, plus the parameters for that kind (e.g. posture;
  the three friction fields; a `value_path` + value). It carries no applied state — it is a
  *recommendation*, not a write.
- **FR-AC-2 — Read-effect propose tool** *(v0.2: host-owned buffer, not session-side)*. The agentic
  Concierge registry adds a single `propose_action` tool with `effect_class="read"` whose handler
  **validates and records** a `ProposedAction` into a **host-owned buffer** (on `KickoffChat`,
  injected into `build_kickoff_registry` — NOT on the generic `AgenticSession`) and returns an
  acknowledgment. It writes nothing to disk. The read tools (`survey`/`assess`/`field_states`) are
  unchanged. The proposal stores **params, not a prebuilt plan** (the plan is rebuilt at confirm
  against live state — OQ-7).
- **FR-AC-3 — Human-confirm-then-apply gate.** After a turn, the host surfaces pending proposals to
  the human. On **explicit confirmation** of a specific proposal, the host builds the corresponding
  plan (`build_instantiate_plan` / `build_friction_entry` / `build_capture_plan`) and applies it via
  the existing typed path (`apply_concierge_plan` / `apply_capture`), bound to a one-time intent. The
  loop is not in this path.
  - **Acceptance (R1):** define double-confirm / idempotency semantics. A proposal is popped from the
    buffer only on **terminal success or explicit discard** — never pop-before-apply. A retriable
    failure (e.g. `STALE_FILE`) **retains / re-offers** the proposal (the friction append path has no
    `(action,digest)` dedup, unlike web `_IntentStore.consume`). Test: confirm a friction proposal
    twice → assert exactly **one** log entry; a failed apply does not silently consume the buffer entry.
- **FR-AC-4 — Read-only floor intact + guarded.** The loop's tool set is exactly
  `{survey, assess, field_states, propose_action}`, all `effect_class="read"`; **no** apply/write tool
  is reachable. Extend the M-CM6 negative regression guard to assert this (and that `propose_action`
  cannot itself write).
  - **Acceptance (R1):** strengthen the guard to the **agentic** registry (`proposal_sink` set), not
    just the pure 3-tool one: the registry is exactly `{survey, assess, field_states, propose_action}`,
    every spec `effect_class="read"`, **and** `propose_action`'s handler performs **zero filesystem
    writes**. Test: snapshot the project tree before/after invoking the handler → assert byte-identical
    except the in-memory buffer.

### B. The experiences

- **FR-AC-5 — Agentic friction (the §G prefill, made real).** The canonical proposal case: from the
  conversation context (a blocked field, an ignored source, a typed failure) the assistant **drafts**
  a friction entry (candidate `friction`/`what_happened`/`implication`) and proposes it. The human
  edits/confirms; apply via the friction path. This realizes the deferred "deterministic friction
  prefill" item as an LLM-assisted, human-confirmed flow.
  - **Acceptance (R1):** before confirm, the host MUST display **all three candidate friction fields
    verbatim** (within `FRICTION_FIELD_MAX`) so a human can catch prompt-injected / PII-laden /
    low-quality LLM prose before it lands in the **tracked append-only** friction log. Length is capped
    (`validate_friction`); content review is not — so the exact bytes that will be written must be
    shown in full, not summarized. Test: a multiline/PII candidate is echoed in full at the confirm
    prompt.
- **FR-AC-6 — Agentic instantiate.** When the package is `missing`/`partial`, the assistant may
  propose instantiate (with a posture); on confirm, the existing instantiate path runs (honest
  no-clobber, package-state reconciliation).
- **FR-AC-7 — Agentic capture.** The assistant may propose a field value for a capturable
  `value_path` (e.g. "set conventions.language = python"); on confirm, the M6 capture path applies
  (allow-list, round-trip gate, stale-file precondition all intact).
  - **Acceptance (R1):** `base_sha` is captured at **PROPOSE** time (not re-read at confirm). If the
    plan re-read the inputs at confirm and applied immediately, `apply_capture`'s
    `current_sha != base_sha` guard (`capture.py:370`) could never fire — vacuous, leaving the
    propose→confirm human-edit window unprotected. Capturing `base_sha` at propose keeps the guard
    meaningful across that window. Test: edit the inputs file in the propose→confirm window → apply
    returns `STALE_FILE`, not a silent overwrite. *(Reconciles the FR-AC-7 "precondition intact" claim
    with OQ-7's "rebuild plan at confirm against live state" — params, including `base_sha`, are
    snapshotted at propose; only the build/apply happens at confirm.)*

### C. Surfaces, wording, ops

- **FR-AC-8 — TUI surface** *(v0.2: requires the REPL signature extension, FR-NEW-3)*. The agentic
  Concierge is reachable from the TUI (v1 is TUI-only — OQ-2). `run_kickoff_repl` is **extended**
  (FR-NEW-3) so that after each turn pending proposals are listed and confirmed via `questionary`,
  then applied. A new entry point (e.g. `kickoff concierge-chat`, or `kickoff chat --agentic`) keeps
  plain `kickoff chat` strictly read-only/advisory.
- **FR-AC-9 — Confirmed-write wording (enforced structurally — OQ-6).** Proposed-vs-applied is the
  **host's** to render: the host prints the typed apply `code`, so the model's prose is advisory and
  never the source of truth. The model is still instructed not to claim "saved/created/logged"
  (inherits R2-F8), but correctness does not depend on the model obeying.
- **FR-AC-10 — Cost disclosure.** The agentic Concierge spends LLM tokens; the per-turn cost line
  (already shown by the chat host, `chat.py:154`) is preserved. *(v0.2: the extra "posture line it can
  propose but not write" is dropped — overspecified; the rewritten banner already states the posture.)*
- **FR-AC-11 — Observability** *(v0.2: allow-list is discipline, not enforced)*. Emit `proposal_made`
  (kind), `proposal_confirmed` (kind, applied code), `proposal_discarded` — bounded attributes only
  (kind/code; **no free-text/paths**). Note: `emit()` does not mechanically enforce the attribute
  allow-list (`telemetry.py:109` — it is documentary), so the privacy guarantee rests on call sites
  passing only bounded keys, not a runtime filter.

### D. Requirements surfaced by planning (new in v0.2)

- **FR-NEW-1 — Rewrite the system prompt + banner.** `KICKOFF_SYSTEM_PROMPT`/`POSTURE_BANNER`
  (`chat.py:34-51`) currently say "exactly three tools" + "never claim to log friction" + "I cannot
  edit files" — which **contradict** the new `propose_action` tool. They must be rewritten: the loop
  still never writes, but it has a fourth tool to *recommend* an action, and a human confirms before
  anything is applied. **Hard prerequisite** (gates FR-AC-2/5/6/7).
  - **Acceptance (R1):** the prompt + banner are **mode-paired**, NOT a single rewritten constant.
    Rewriting the one shared `KICKOFF_SYSTEM_PROMPT`/`POSTURE_BANNER` to mention `propose_action` would
    advertise a fourth tool to the pure `kickoff chat` session that (per FR-NEW-5) never registers it —
    inviting an unknown-tool call. Pure path keeps the **read-only** prompt/banner (3 tools); the
    agentic path uses a **propose-aware** variant (mentions `propose_action` + "a human confirms");
    selection is driven by `proposal_sink` presence. Test: the pure session's effective system prompt
    **excludes** "propose_action"; the agentic session's **includes** it.
- **FR-NEW-2 — Surface a stale-proposal outcome.** Because the plan is rebuilt at confirm against live
  state (OQ-7), the state may have changed since the proposal (package now complete; a `STALE_FILE`
  on capture). The host must render the typed outcome, not silently no-op.
  - **Acceptance (R1):** expand the outcome set beyond "complete / `STALE_FILE`" to include **`PARTIAL`**
    and **`WRITE_REFUSED`** — `apply_concierge_plan` is explicitly **non-atomic** (`concierge_apply.py:148-156`:
    "some files may still have been written before/after the failing one" → `PARTIAL`), so a confirmed
    instantiate can half-apply. The host MUST render the **written/skipped counts** and define recovery:
    **resume = re-confirm completes the remaining `ACTION_NEW` files** (idempotent), not silently leave a
    half-built package. Test: inject a per-file write block mid-plan → assert the host renders `PARTIAL`
    with written/skipped counts (not `OK`).
- **FR-NEW-3 — Extend the REPL host signature.** `run_kickoff_repl` must accept a pending-proposals
  accessor, a `ConfirmFn` (fail closed on `None`/non-TTY, NR-5), and an `apply_proposal` callback —
  this is a requirement, not an implementation detail (FR-AC-8 understated it).
- **FR-NEW-4 — Bound the pending-proposal buffer.** The host buffer is a **bounded** list (mirror
  `_IntentStore._MAX`) so proposals can't accumulate without limit; multiple proposals confirm
  serially (OQ-5).
- **FR-NEW-5 — Keep `kickoff chat` pure.** `build_kickoff_registry` gates `propose_action` behind a
  `proposal_sink` parameter (omitted → no propose tool), so plain `kickoff chat` stays strictly
  read-only/advisory and agentic Concierge is the opt-in superset.
  - **Acceptance (R1):** purity covers the **prompt + banner too**, not just the tool — `proposal_sink`
    presence selects the mode-paired prompt/banner variant (see FR-NEW-1), so the pure session never
    advertises `propose_action`. Test: pure session's system prompt has no "propose_action" and lists
    no 4th tool.

### E. Provider/Model configuration (FR-PC-*) — *added v0.4*

> Detail + planning insights: `AGENTIC_CONCIERGE_PROVIDER_CONFIG_REQUIREMENTS.md` (v0.2) +
> `AGENTIC_CONCIERGE_PROVIDER_CONFIG_PLAN.md` (v1.0). Summary:

- **FR-PC-1 — Config-file provider/model selection.** The agent is resolvable from a config-file value
  that is a full agent **spec** (`provider:model` / provider / model-id / alias — anything
  `resolve_agent_spec` accepts; **no tiers**), not only `--agent`.
- **FR-PC-2 — Per-project key.** A new top-level `concierge_agent:` in
  `docs/kickoff/inputs/build-preferences.yaml` (added to the parser's closed key allowlist + manifest).
- **FR-PC-3 — Global default.** A `concierge_agent` preference in `~/.startd8/config.json` applies when
  no per-project value is set.
- **FR-PC-4 — Precedence.** `--agent` flag > project config > global config >
  catalog default (`Models.CLAUDE_SONNET_LATEST`); first present, non-placeholder value wins.
- **FR-PC-5 — Graceful degradation (unchanged).** Resolution returns a spec string only; validation
  stays at the existing sites — a bad configured spec degrades exactly like a bad `--agent` (CLI
  actionable error; web "chat not enabled" notice). Never a hard crash.
- **FR-PC-6 — No hardcoded model.** The default stays a `model_catalog` reference; no literal version.
- **FR-PC-7 — Discoverability.** The surface prints the resolved spec + its source (flag / project /
  global / default).
- **FR-PC-8 — Pinned path.** Project config = `<project_root>/docs/kickoff/inputs/build-preferences.yaml`
  only. **FR-PC-9 — Malformed config is non-fatal** (skip-and-warn). **FR-PC-10 — Angle-bracket
  placeholders are unset.** **FR-PC-11 — Both chat surfaces share the `concierge_agent` key.**
- **Mechanism:** one helper `resolve_concierge_agent_spec(project_root, flag) -> (spec, source)` in
  `kickoff_experience/concierge_agent.py`, called by the three chat surfaces.

---

## 4. Non-Requirements

- **NR-1 — No autonomous writes.** A proposal never auto-applies; the loop never calls a write path.
- **NR-2 — No MCP writes.** Proposals are not applied over MCP (the MCP surface stays read-only).
- **NR-3 — No new write engine.** Confirmed proposals reuse `apply_concierge_plan` / `apply_capture` —
  no new safety surface, no new file writer.
- **NR-4 — Not a replacement for the deterministic Concierge.** The forms / `kickoff concierge`
  questionary flow remain; the agentic mode is an additional, optional surface.
- **NR-5 — No unattended `--yes`.** v1 requires foreground human confirmation (fails closed on
  non-TTY, inherits the TUI confirm-unavailable rule).

---

## 5. Open Questions

*6 of 7 resolved by the planning pass — see §0 for rationale + citations. Retained for the record.*

- **OQ-1 — RESOLVED → propose-tool path.** A `effect_class="read"` `propose_action` whose handler
  records to a host buffer (writes nothing) passes dispatch (`agentic.py:214,220`); output-parsing the
  final message is rejected as brittle/untestable.
- **OQ-2 — RESOLVED (scope) → TUI-only for v1.** Web agentic panel deferred (M6) — it adds an
  LLM-in-request-path surface + streaming + the CSRF/intent apply gate.
- **OQ-3 — RESOLVED → host-owned buffer; the buffer entry is the one-time intent** in the TUI
  (pop-on-consume). No `_IntentStore` clone; plan+digest binding stays a web concern.
- **OQ-4 — RESOLVED → capture in v1.** The apply path (`apply_capture`) exists; only a `value_path`
  allow-list check is new.
- **OQ-5 — RESOLVED → allow multiple, confirm serially** (bounded buffer, FR-NEW-4).
- **OQ-6 — RESOLVED (structural + params grounding).** Proposed-vs-applied is enforced by the host
  printing the apply code; params are validated; free-text friction *prose* grounding is **not**
  enforceable, which is acceptable because a human confirms.
- **OQ-7 — RESOLVED → re-validate at confirm** by rebuilding the plan against live state (instantiate
  re-stats; capture re-reads with the `STALE_FILE` guard). Proposals store params, not plans.
  - **Acceptance (R1):** the snapshotted params **include `base_sha` captured at propose time** — so
    capture's `STALE_FILE` guard stays meaningful across the propose→confirm window (see FR-AC-7).
    "Rebuild at confirm" rebuilds the *plan/apply*, not the staleness baseline.

---

*v0.2 — Post-planning self-reflective update. 1 requirement reframed (FR-AC-2 → host buffer), 1
clarified-structural (FR-AC-9), 1 narrowed (FR-AC-11), 1 trimmed (FR-AC-10), 5 added (FR-NEW-1..5),
6 of 7 OQs resolved. Headline: the mechanism is feasible (a read-effect propose tool), but the
existing system prompt/banner **forbid** the new tool (FR-NEW-1 — a hard prerequisite), and the buffer
is host-owned, not on the generic session. Ready for optional CRP review before implementation.*

*v0.3 — Post-CRP R1. All 6 R1 F-suggestions (claude-opus-4-8) accepted and merged: base_sha-at-propose
(FR-AC-7/OQ-7), PARTIAL/WRITE_REFUSED outcomes (FR-NEW-2), mode-paired prompt/banner (FR-NEW-1/5),
verbatim friction display (FR-AC-5), double-confirm idempotency (FR-AC-3), agentic-registry floor guard
(FR-AC-4). See Appendix A for dispositions; Appendix C retains the R1 round verbatim.*

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
| R1-F1 | Capture `base_sha` at propose time so the STALE_FILE guard isn't vacuous across the propose→confirm window | R1 / claude-opus-4-8 | Merged into FR-AC-7 (+ OQ-7 note) | 2026-06-26 |
| R1-F2 | Expand stale-outcome set to PARTIAL + WRITE_REFUSED for non-atomic instantiate; render written/skipped + resume recovery | R1 / claude-opus-4-8 | Merged into FR-NEW-2 | 2026-06-26 |
| R1-F3 | Mode-pair the prompt/banner (not a single rewrite); pure path read-only, agentic propose-aware, selected by proposal_sink | R1 / claude-opus-4-8 | Merged into FR-NEW-1 and FR-NEW-5 | 2026-06-26 |
| R1-F4 | Host displays all three candidate friction fields verbatim before confirm (content review, not just length cap) | R1 / claude-opus-4-8 | Merged into FR-AC-5 | 2026-06-26 |
| R1-F5 | Define double-confirm/idempotency: pop on terminal success or discard, never pop-before-apply; retain on retriable failure | R1 / claude-opus-4-8 | Merged into FR-AC-3 | 2026-06-26 |
| R1-F6 | Strengthen floor guard to the agentic registry (4-tool set, read-only, zero-write handler via tree snapshot) | R1 / claude-opus-4-8 | Merged into FR-AC-4 | 2026-06-26 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8 — 2026-06-26

- **Reviewer**: claude-opus-4-8
- **Date**: 2026-06-26 17:55:00 UTC
- **Scope**: Requirements quality for the read-effect propose tool, confirm-then-apply TOCTOU, prompt-rewrite/surface-boundary, friction grounding. Grounded against `chat.py`, `agentic.py`, `concierge_apply.py`, `capture.py`, `web.py`.

**Executive summary (top risks / gaps):**
- The §0 STALE_FILE claim ("precondition all intact", FR-AC-7) is in tension with OQ-7: if the plan is *rebuilt at confirm* the read→apply window collapses and `apply_capture`'s `base_sha` guard (`capture.py:370`) becomes vacuous for the propose→confirm gap — the window the human actually edits in is unprotected.
- FR-NEW-2's outcome set is incomplete: `apply_concierge_plan` is explicitly **non-atomic** (`concierge_apply.py:150` — `PARTIAL`, "some files may still have been written before/after the failing one"). A confirmed instantiate can half-apply; no requirement covers this.
- FR-NEW-1 (rewrite the one shared prompt/banner) and FR-NEW-5 (omit the tool for pure `kickoff chat`) collide: a single rewritten `KICKOFF_SYSTEM_PROMPT` would advertise `propose_action` to the pure session that doesn't register it → model emits an unknown-tool call (`agentic.py:215`).
- FR-AC-5's only gate is human-confirm, but no requirement forces the candidate friction prose to be *shown verbatim* before it lands in the tracked append-only log — injection / PII can pass unreviewed.
- FR-AC-3 "one-time intent" is underspecified for double-confirm and failure: the friction append path has no digest-dedup (unlike web `_IntentStore`, `web.py:246`).

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | Specify at which instant `base_sha` is captured for capture proposals. FR-AC-7 says "stale-file precondition all intact" but OQ-7 says "rebuild the plan at confirm against live state". If `build_capture_plan` re-reads at confirm and applies immediately, `apply_capture`'s `current_sha != plan.base_sha` check (`capture.py:370`) can never fire — the guard is vacuous and the propose→confirm human-edit window is unprotected. State: base_sha is read at **propose** time (preserving the guard), or that STALE_FILE is intentionally inert in the agentic path (and what protects the gap instead). | A vacuous concurrency guard is worse than none — it reads as protection in the requirement but provides none in the agentic flow. The focus file names exactly this TOCTOU. | FR-AC-7 ("the M6 capture path applies (allow-list, round-trip gate, stale-file precondition all intact)") + OQ-7 | Test: edit the inputs file in the propose→confirm window; assert apply returns `STALE_FILE` (not a silent overwrite). |
| R1-F2 | Risks | high | Expand FR-NEW-2 from "package now complete; STALE_FILE on capture" to the full typed-outcome set including **PARTIAL** and **WRITE_REFUSED** for a non-atomic instantiate. `apply_concierge_plan` returns `PARTIAL` when some files wrote and one failed (`concierge_apply.py:148-156`). Require the host to render the partial state and define recovery (resume vs re-propose). | FR-NEW-2 as written treats confirm-apply as all-or-nothing; the real write path is not atomic, so a confirmed instantiate can leave a half-built package with no stated recovery. | FR-NEW-2 ("the state may have changed since the proposal ... render the typed outcome, not silently no-op") | Test: inject a per-file write block mid-plan; assert host renders `PARTIAL` with the written/skipped counts, not OK. |
| R1-F3 | Architecture | high | Make FR-NEW-1 and FR-NEW-5 jointly consistent: the system prompt **and** banner must be **mode-paired**. Rewriting the single `KICKOFF_SYSTEM_PROMPT`/`POSTURE_BANNER` (`chat.py:34-51`) to mention `propose_action` would advertise a fourth tool to the pure `kickoff chat` session that (per FR-NEW-5) does not register it, inviting an unknown-tool call. Require: pure path keeps the read-only prompt/banner; agentic path uses the propose-aware variant; selection is driven by `proposal_sink` presence. | FR-NEW-5's purity guarantee is silently broken by FR-NEW-1 if the prompt is a single shared constant. This is a cross-requirement contradiction, not an implementation detail. | FR-NEW-1 + FR-NEW-5 | Test: pure session's effective system prompt does **not** contain "propose_action"; agentic session's does; pure session never lists a 4th tool. |
| R1-F4 | Security | medium | Add an acceptance criterion to FR-AC-5: before confirm, the host MUST display **all three candidate friction fields verbatim** (within `FRICTION_FIELD_MAX`) so the human can catch prompt-injected, PII-laden, or low-quality LLM prose before it lands in the **tracked append-only** friction log. Length is already capped (`validate_friction`, `concierge_apply.py:95`); content review is not. | The focus flags injection/privacy. Human-confirm is only a real gate if the human sees the exact bytes that will be written and committed. | FR-AC-5 ("The human edits/confirms; apply via the friction path") | Manual + test: confirm prompt echoes the candidate text; a multiline/PII candidate is shown in full, not summarized. |
| R1-F5 | Interfaces | medium | Define double-confirm / idempotency semantics for FR-AC-3. The friction append path has no `(action,digest)` dedup (the web `_IntentStore.consume`, `web.py:246`, does). Two identical proposals in one session, or a re-confirm after a non-terminal apply failure, can duplicate the friction entry. Specify: a proposal is consumed (popped) only on **terminal success or explicit discard**; on retriable failure it is retained or re-offered, never both popped and partially applied. | "Bound to a one-time intent" (FR-AC-3) is asserted but the pop timing and the no-dedup append path make double-write reachable. | FR-AC-3 ("bound to a one-time intent. The loop is not in this path") | Test: confirm a friction proposal twice; assert exactly one log entry; failed apply does not silently consume the buffer entry. |

##### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F6 | Validation | medium | Strengthen FR-AC-4 to assert the **agentic** registry (proposal_sink set), not just the pure one: registry is exactly `{survey, assess, field_states, propose_action}`, every spec `effect_class="read"`, **and** `propose_action`'s handler performs zero filesystem writes (assert no new/modified files under a temp project root after invoking it). Today the guard text only pins the pure 3-tool set; the new tool is the one that needs the negative proof. | A "read-effect tool that records intent" is exactly where a future edit could leak a write; the regression guard must cover the handler's side-effect surface, not just its `effect_class` label. | FR-AC-4 ("Extend the M-CM6 negative regression guard to assert this (and that propose_action cannot itself write)") | Test: snapshot project tree before/after `propose_action` handler call; assert byte-identical except the in-memory buffer. |

**Endorsements / Disagreements:** none (R1 — no prior untriaged items).
