# Agentic Concierge Mode Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
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
- **FR-AC-4 — Read-only floor intact + guarded.** The loop's tool set is exactly
  `{survey, assess, field_states, propose_action}`, all `effect_class="read"`; **no** apply/write tool
  is reachable. Extend the M-CM6 negative regression guard to assert this (and that `propose_action`
  cannot itself write).

### B. The experiences

- **FR-AC-5 — Agentic friction (the §G prefill, made real).** The canonical proposal case: from the
  conversation context (a blocked field, an ignored source, a typed failure) the assistant **drafts**
  a friction entry (candidate `friction`/`what_happened`/`implication`) and proposes it. The human
  edits/confirms; apply via the friction path. This realizes the deferred "deterministic friction
  prefill" item as an LLM-assisted, human-confirmed flow.
- **FR-AC-6 — Agentic instantiate.** When the package is `missing`/`partial`, the assistant may
  propose instantiate (with a posture); on confirm, the existing instantiate path runs (honest
  no-clobber, package-state reconciliation).
- **FR-AC-7 — Agentic capture.** The assistant may propose a field value for a capturable
  `value_path` (e.g. "set conventions.language = python"); on confirm, the M6 capture path applies
  (allow-list, round-trip gate, stale-file precondition all intact).

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
- **FR-NEW-2 — Surface a stale-proposal outcome.** Because the plan is rebuilt at confirm against live
  state (OQ-7), the state may have changed since the proposal (package now complete; a `STALE_FILE`
  on capture). The host must render the typed outcome, not silently no-op.
- **FR-NEW-3 — Extend the REPL host signature.** `run_kickoff_repl` must accept a pending-proposals
  accessor, a `ConfirmFn` (fail closed on `None`/non-TTY, NR-5), and an `apply_proposal` callback —
  this is a requirement, not an implementation detail (FR-AC-8 understated it).
- **FR-NEW-4 — Bound the pending-proposal buffer.** The host buffer is a **bounded** list (mirror
  `_IntentStore._MAX`) so proposals can't accumulate without limit; multiple proposals confirm
  serially (OQ-5).
- **FR-NEW-5 — Keep `kickoff chat` pure.** `build_kickoff_registry` gates `propose_action` behind a
  `proposal_sink` parameter (omitted → no propose tool), so plain `kickoff chat` stays strictly
  read-only/advisory and agentic Concierge is the opt-in superset.

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

---

*v0.2 — Post-planning self-reflective update. 1 requirement reframed (FR-AC-2 → host buffer), 1
clarified-structural (FR-AC-9), 1 narrowed (FR-AC-11), 1 trimmed (FR-AC-10), 5 added (FR-NEW-1..5),
6 of 7 OQs resolved. Headline: the mechanism is feasible (a read-effect propose tool), but the
existing system prompt/banner **forbid** the new tool (FR-NEW-1 — a hard prerequisite), and the buffer
is host-owned, not on the generic session. Ready for optional CRP review before implementation.*
