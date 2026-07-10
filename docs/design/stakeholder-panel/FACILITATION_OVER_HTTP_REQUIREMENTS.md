# Facilitation over HTTP (F1) — Grafana-drivable multi-round panel + posture

**Version:** 0.5 (CRP-hardened — 2 rounds, 32 accepted)
**Date:** 2026-07-09
**Status:** Draft (reflective loop; CRP pending)

> ### 0.2 Decisions
> - **OQ-1 → fire-and-poll** (kickoff→session_id→GET status). FR-1/FR-3.
> - **OQ-2 → build the plugin UI too** — FR-9 is IN SCOPE this increment (server routes + CLI driver AND
>   the Grafana `facilitate` mode).
> - **OQ-3 → add `tier=cheap` now** — folds roadmap Q4 (FR-10): a cheap model-family set (~10× cheaper).
> - **OQ-4 → reuse the endpoint's `--daily-ceiling` + per-run `budget_usd`.**
**Cluster:** F1 (from `ROLE_BASED_INPUT_ENHANCEMENTS.md`) — expose the multi-round facilitation + posture
selection over HTTP so the Digital Project Workbook can drive it (today it's CLI-only).

---

## 0. Planning Insights (grounded audit)

| v0.1 assumption | Audit discovery | Impact |
|-----------------|-----------------|--------|
| "Add a `/stakeholders/facilitate` route like `/run`" | `/run` (ask-all) **blocks** via `run_in_threadpool` (~seconds, 6 personas). Facilitation is **minutes** (R0–R5 × premium de-correlated models, ~$0.43). Blocking an HTTP request that long → Grafana datasource-proxy + client timeouts. | **Must be fire-and-poll** (FR-1/FR-3): kick off async, return `session_id` immediately, poll status. Not a blocking route. |
| "Read status from the run" | `KickoffFacilitator.run()` **persists per-round** to the kickoff-panel store with a `status` field (`in_progress`/`completed`/`halted`) via `_persist` (`facilitation.py:893`), + `transcript_path`. | **Status route reads the transcript** (`KickoffViewService.load`), no new state store (FR-3). |
| "Cancellation is new" | `_RunRegistry` + `cancel_run` already abort an in-flight run cross-thread via `loop.call_soon_threadsafe` (`stakeholder_run.py:310`). | **Reuse the registry** keyed by the facilitation `run_key`/session (FR-6). |
| "Cost pre-flight is new" | `projected_calls(cfg, n)` gives the call count; `_build_cost_tracker` (CLI) wires a `CostTracker` → `panel-costs.db`; `budget_usd` is a hard cumulative-abort; `ensure_daily_ceiling` fail-closes. | **Dry-run reuses `projected_calls` + a per-call estimate** (FR-2); confirm wires the cost tracker + ceilings (FR-5). |
| "One plugin change" | The Grafana plugin (`kickoff-stakeholders-panel`) is **unsigned**, on a **shared** Grafana, and needs build + allow-list + **restart** (operator, blast radius). Its `mode` option is `run|apply` (`module.ts:23`). | The **server routes are the substance**; the plugin `facilitate` mode is operator-gated UI — scope per OQ-2. |
| "Facilitation is premium-only" | FAMILIES are hard-coded premium; no cheap tier today (roadmap Q4). | Optionally thread a **tier** into the request (OQ-3). |

**Resolved:** the facilitation config already carries `posture` (#172–174) and `budget_usd` — F1 threads them
through the request; no new facilitation logic.

---

### 0.1 Lessons-Learned Hardening (v0.4)
> Applied SDK lessons before CRP:
- **Phantom-reference audit (Leg 13/16)** — every symbol named (`_RunRegistry`, `cancel_run`,
  `projected_calls`, `KickoffViewService.load`, `_build_cost_tracker`, `ensure_daily_ceiling`) verified
  present (§Reference Audit). New surfaces marked ❌→FR.
- **`$0.00`-cost-as-red-flag / fail-closed budget (Leg 10 / Leg 5 #24)** — FR-5 fail-closes on missing
  budget config; an untracked `$0` run must never defeat the ceiling. A dry-run that returns `$0` for a
  premium multi-round run is a bug, not a free lunch.
- **Cross-thread task cancel (Leg 11 #119)** — reuse `loop.call_soon_threadsafe(task.cancel)` via the
  existing registry; never a direct cross-thread `task.cancel()`. Unregister on terminal to avoid leaks.
- **Thin-driver-over-tested-core (Leg 11 #100 / #101)** — the un-unit-testable plugin stays a thin driver
  over the tested Python routes; a green Python suite doesn't cover the TS — documented manual verify.
- **CRP steering** — least-reviewed = this doc + the new async routes; do-not-relitigate: the facilitator
  itself (#172–174), fire-and-poll (OQ-1), the existing `/run` auth/idempotency pattern.

## 1. Problem
The **prototype posture** and the whole multi-round facilitation — the SDK's richest role-based-input
capability — are **CLI-only**. The Grafana Workbook can drive only the single-question ask-all (`/run`)
and the apply gate. Make facilitation + posture a **dashboard-native, one-click** action.

## 2. Requirements
- **FR-1 (kickoff route, async).** `POST /stakeholders/facilitate` — body
  `{posture, dry_run, run_key, budget_usd?, tier?, cap?, project_context?}`. A **confirmed** call kicks the
  facilitation off in a background worker (its own event loop, registered for cancel), **persists per-round
  to the kickoff-panel store**, and returns **immediately** with `{session_id, status:"in_progress",
  run_key}`. Same bearer auth + strict/nonce posture as the other routes.
- **FR-2 (dry-run cost pre-flight, `$0`).** `dry_run:true` → `{run_key, posture, n_participants,
  projected_calls, estimated_cost_usd, models}` from `projected_calls` + a per-call token estimate. No spend.
  `run_key` binds `{posture, cap, roster_version, budget}` (mismatch on confirm → 409, mirroring `/run`).
- **FR-3 (status poll).** `GET /stakeholders/facilitate/{session_id}` → `{status, rounds_completed,
  cost_so_far_usd, synthesis?, halt?}` read from the persisted transcript (`KickoffViewService`). Terminal
  states: `completed` (synthesis present), `halted` (halt payload), `error`.
- **FR-4 (single-flight + idempotency).** A `run_key` already in-flight or already terminal → return its
  current status (no double-spend), mirroring `/run`'s `deduped` semantics.
- **FR-5 (fail-closed budget).** Wire a `CostTracker` (→ `panel-costs.db`) + the per-run `budget_usd`
  cumulative-abort + the endpoint's daily ceiling; a missing budget config fail-closes (never an untracked
  `$0` run that defeats the cap).
- **FR-6 (cancel).** `POST /stakeholders/facilitate/{run_key}/cancel` → `cancel_run` (reuse `_RunRegistry`);
  already-completed rounds persist; the transcript ends `halted`/`cancelled`, pollable.
- **FR-7 (posture selection + honest framing).** `posture ∈ {scrutiny, prototype}` (validated; default
  scrutiny). The response/status echoes the posture; a prototype run carries the SYNTHETIC & UNRATIFIED +
  "backlog-bound" framing.
- **FR-8 (feed the bridge).** A completed facilitation transcript is already consumable by
  `triage`/`backlog`/`extract` (existing routes) — verify the session id round-trips end-to-end
  (facilitate → status=completed → triage).
- **FR-9 (Grafana plugin `facilitate` mode) — IN SCOPE (OQ-2).** Add a `facilitate` panel mode: posture +
  tier selectors → **Preview cost** (dry-run, echoing `run_key`) → confirm → **poll** the status route →
  render the synthesis (or the halt) with the SYNTHETIC & UNRATIFIED banner. Reuses the datasource proxy +
  server-side token (never in the panel). Unsigned/operator-gated deploy (build + restart) is documented,
  not automated (NR-5).
- **FR-10 (cheap tier) — folds Q4.** `tier ∈ {premium (default), cheap}` on the facilitate request →
  `FacilitationConfig` selects the model-family set: premium = today's de-correlated
  opus-4.8/gpt-5.5/gemini-3.1-pro; cheap = a haiku/mini/flash de-correlated trio (~10× cheaper). The
  dry-run cost estimate reflects the chosen tier. De-correlation (one family per participant) is preserved
  in both tiers; the transcript records the tier.

## 2.1 CRP Hardening (v0.5) — accepted refinements

> Two CRP rounds (R1 focus, R2 adversarial), 15 F + 17 S suggestions, all code-anchored; orchestrator
> ACCEPTED all (Appendix A), 0 rejected. Normative. The design shifts from "thin transport" to a careful
> async-orchestration primitive.

**Single-flight, session_id, lifecycle (the async core):**
- **H-1 [R1-F1/S2] register-before-spawn under one lock** — the single-flight decision + registry insert
  happen BEFORE the worker starts, under one lock (not inside `run()`). Closes the double-spawn race.
- **H-2 [R1-F2/S3] `session_id` injection seam** — `start_facilitation` pre-mints the session_id and injects
  it into `KickoffFacilitator` so the route returns it synchronously; NOT block-on-first-`_persist` (R2's
  dispute of the blocking alternative sustained).
- **H-3 [R1-S1] the worker is a NEW primitive** (`threading.Thread` + `asyncio.new_event_loop()` +
  `run_until_complete` + `finally: loop.close()` + `unregister`), not a reuse of `execute_run`.
- **H-4 [R2-F3/S1] two-keyspace single-flight** — an on-disk `IdempotencyStore` marker (survives unregister +
  restart) for "already terminal → return session"; the in-memory `_RUN_REGISTRY` for "in-flight → cancel".
- **H-5 [R2-F7/S7] concurrency cap** — bound in-flight facilitations (excess → 429/queued).

**Terminal states + cancel:**
- **H-6 [R2-F1/S3] add `cancelled` + `error` to the status enum AND `KickoffTranscript.is_terminal`**
  (`kickoff_view/models.py:147`, today only completed/done/halted).
- **H-7 [R1-F5/S8] terminal-`error` writer** — the worker's except/finally persists `status:"error"`
  (first-class) on an unhandled exception; no stuck `in_progress`.
- **H-8 [R2-F2/S2] `except asyncio.CancelledError`** persists a first-class `cancelled` transcript (mirror
  `_finish_halt`), keeping partial rounds, before unregister.
- **H-9 [R2-F4/S5] cancel accepts `session_id`** — the poller holds session_id; cancel resolves
  session_id→run_key (or accepts either).

**run_key / cost / budget:**
- **H-10 [R1-F4/S6 — CRITICAL] run_key binds `{posture, tier, cap, roster_version, budget}`** — a cheap
  dry-run must not mint a run_key a premium confirm echoes; confirm re-derives + 409s on mismatch.
- **H-11 [R1-F3/S5] round-weighted cost estimate** — R3 (digest) and R5 (full-transcript synth) carry far
  more input tokens; per-tier per-round token model, not flat per-call.
- **H-12 [R1-F6/S7 + R2-S4] concurrent daily-ceiling abort + explicit cost-tracker model** — one
  process-wide `CostTracker`/`CostStore` (serialized writes); the round-boundary guard consults the shared
  daily ceiling, not just `cfg.budget_usd`.
- **H-13 [R2-F6] dry_run runs the fail-closed budget check** too (no green-preview→412-confirm).

**Security / routing:**
- **H-14 [R2-F5/S6] nonce consumed on successful spawn** (strict mode) — not in `_authorize` before spawn;
  a spawn failure must not deny the retry.
- **H-15 [R1-S4] status route reads the kickoff-panel transcript** via `KickoffViewService.load` (not the
  ask-all `TranscriptStore`); `/facilitate/` path must not collide with `GET /run/{session_id}`.

**Plugin + tests:**
- **H-16 [R1-F7/S10] bounded plugin poll** (max attempts/wall-clock) + explicit
  completed/halted/cancelled/error/"still running" states; a retried confirm must not double-run.
- **H-17 [R2-S5] plugin threads the `run_key`** (not just session_id) for Cancel.
- **H-18 [R1-F8/S9] tests** — e2e asserts `status=="completed"` before triage; a leak/shutdown guard asserts
  thread-joined + registry-entry-removed on EVERY terminal path.

## 3. Non-Requirements
- **NR-1** no new facilitation *logic* — reuse `KickoffFacilitator`; F1 is transport + orchestration.
- **NR-2** no synchronous/blocking facilitation route (minutes-long → fire-and-poll only).
- **NR-3** no streaming of live round deltas over HTTP in v1 (poll granularity = per-round via the
  persisted transcript); SSE/websocket streaming is a later increment.
- **NR-4** no new persistence store — reuse the kickoff-panel transcript (status + per-round) + `panel-costs.db`.
- **NR-5** the plugin is unsigned/operator-gated; F1 does not auto-deploy it (build+restart is an operator action).

## 4. Open Questions — RESOLVED (v0.3)
- **OQ-1 → fire-and-poll** (FR-1/FR-3). **OQ-2 → plugin IN SCOPE** (FR-9). **OQ-3 → `tier=cheap`** (FR-10).
  **OQ-4 → reuse `--daily-ceiling` + `budget_usd`** (FR-5).

*Residual forks for CRP: the async single-flight/idempotency + cancel semantics (FR-1/FR-4/FR-6), the
dry-run cost-estimate accuracy per tier (FR-2/FR-10), and the plugin's poll/timeout/error handling (FR-9).*

## Reference Audit
| Symbol | Where | Exists? |
|--------|-------|---------|
| `/stakeholders/run` (+dry_run/run_key/status/cancel), auth, `ensure_daily_ceiling` | `stakeholder_run_server.py` | ✅ (pattern to mirror) |
| `_RunRegistry` / `cancel_run` (cross-thread abort) | `stakeholder_run.py:310` | ✅ (reuse) |
| `KickoffFacilitator.run()` (async, per-round persist, status, budget, cost_tracker) | `facilitation.py:927` | ✅ (reuse) |
| `projected_calls` / `FacilitationConfig(posture, budget_usd)` | `facilitation.py` | ✅ |
| `_build_cost_tracker` → `panel-costs.db` | `scripts/run_kickoff_panel.py:59` | ✅ (lift into a shared helper) |
| `KickoffViewService.load` (read transcript status/synthesis) | `kickoff_view/facade.py` | ✅ |
| `POST /stakeholders/facilitate` (+ status/cancel) | `stakeholder_run_server.py` | ❌ → FR-1/3/6 |
| plugin `facilitate` mode | `grafana-plugins/.../module.ts` | ❌ → FR-9 (OQ-2) |

*v0.3 — post-audit + decisions folded (fire-and-poll; plugin IN scope; cheap tier folds Q4; reuse budget
ceilings). F1 = transport + async orchestration over the existing facilitator. Ready for CRP.*

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
| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| ALL R1+R2 (15 F + 17 S) | see Appendix C | opus-4.8-1m ×2 | **ACCEPTED all** → REQUIREMENTS §2.1 H-1…H-18 (F/S ids that coincide share one H). 0 rejected — both rounds code-anchored, non-redundant. Resolutions: session_id **injection** (not block-on-persist, R2 dispute sustained); nonce **consume-on-spawn**; two-keyspace single-flight. | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | Both rounds code-anchored and non-redundant; nothing rejected. | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-09 00:00:00 UTC
- **Scope**: Requirements review weighted to the focus file — async fire-and-poll lifecycle, dry-run cost accuracy per tier, fail-closed budget across concurrent background runs, plugin poll/error/cancel. Grounded in `stakeholder_run.py`, `stakeholder_run_server.py`, `facilitation.py`, `kickoff_view/facade.py`.

**Focus-file asks answered first (least-reviewed / highest-risk):**

**Ask 1 — Async fire-and-poll lifecycle (FR-1/3/4/6).**
- **Summary answer:** Partial — the requirements name the right primitives but rest on a reuse claim that the real code does not support; three concrete lifecycle holes are unspecified.
- **Rationale:** (a) The audit table (§0 row 1) says "reuse `execute_run`'s task handling", but `execute_run` (`stakeholder_run.py:435`) calls `asyncio.run(_go())` **synchronously in the calling thread** and only returns after the whole run completes — there is NO background-thread-with-own-loop today; FR-1 is net-new, not reuse. (b) `_RunRegistry.register` is called **inside** `_go()` after the task already exists (`stakeholder_run.py:428`), so a facilitate run_key is not registered until the worker loop is already running — the single-flight check in FR-4 has a spawn-race window. (c) The `session_id` is minted **inside** `KickoffFacilitator.run()` (`facilitation.py:954`), so FR-1's "return `{session_id …}` immediately" cannot read it synchronously without pre-generating the id and injecting it.
- **Assumptions / conditions:** the worker thread owns its own event loop and the request thread returns before `run()` finishes.
- **Suggested improvements:** see R1-F1 (registry-before-spawn), R1-F2 (session_id injection), R1-F5 (terminal-error on crash). Add an explicit FR: "the run_key is registered for cancel/single-flight BEFORE the worker thread is started, not inside the run coroutine."

**Ask 2 — Dry-run cost accuracy per tier (FR-2/FR-10).**
- **Summary answer:** No — `projected_calls × flat-per-call` under-reads a facilitated run because later rounds carry materially more input tokens; and the run_key binding in FR-2 omits `tier`.
- **Rationale:** `projected_calls` (`facilitation.py:737`) is a pure **count** (prep + n×rounds + 1). A flat per-call estimate ignores that R3 injects a cross-persona `_digest` and R5 injects the **entire transcript** (`facilitation.py:1086`, `_synth_prompt`) — the synthesis call alone is many× a round-1 call. FR-2 says `run_key` binds `{posture, cap, roster_version, budget}` but **omits `tier`** — so a `cheap` dry-run's run_key equals a `premium` confirm's run_key, letting a cheap preview authorize a premium (10×) run. The focus file explicitly requires `tier` in the binding.
- **Assumptions / conditions:** cheap/premium differ ~10× per call (FR-10).
- **Suggested improvements:** R1-F3 (round-weighted estimate), R1-F4 (bind tier into run_key). 

**Ask 3 — Fail-closed budget across concurrent background runs (FR-5).**
- **Summary answer:** Partial — FR-5 covers missing-config and per-run `budget_usd`, but not a mid-flight daily-ceiling breach caused by a *concurrent* run, nor terminal accounting on crash.
- **Rationale:** `KickoffFacilitator._budget_guard` (`facilitation.py:1128`) only checks `cfg.budget_usd` (the per-run cap) at round boundaries; it never consults the shared daily ceiling / `CostTracker`. Two concurrent background facilitations sharing `panel-costs.db` can each individually pass their per-run cap yet jointly blow the daily ceiling, and neither aborts. `ensure_daily_ceiling` (`stakeholder_run.py:267`) is checked only at request time.
- **Assumptions / conditions:** more than one facilitate run can be in-flight at once (the registry is keyed per run_key, so yes).
- **Suggested improvements:** R1-F6 (concurrent daily-ceiling abort), R1-F5 (crash → terminal error + final cost).

**Ask 4 — Plugin poll/error/timeout + token server-side (FR-9).**
- **Summary answer:** Partial — token-stays-server-side is asserted but FR-9 lacks explicit poll-timeout, error-terminal, and cancel-confirmation acceptance criteria.
- **Rationale:** FR-9 says "poll the status route … render synthesis or halt" but never bounds the poll (a run that never terminates → infinite poll) nor states what the panel renders on `status:"error"` or a 404/5xx from the proxy.
- **Suggested improvements:** R1-F7 (poll bound + error rendering).

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Risks | high | FR-1: state that the run_key is registered in `_RUN_REGISTRY` (or a facilitate registry) **before** the worker thread starts, and that single-flight (FR-4) is checked under the same lock, so two near-simultaneous POSTs cannot both spawn. | The existing `_RunRegistry.register` is called inside the run coroutine (`stakeholder_run.py:428`), after the task exists — reusing that pattern leaves a spawn-race the fire-and-poll design must close. | FR-1 / FR-4 | Test: fire two concurrent confirms with the same run_key; assert exactly one worker thread/transcript is created and the second returns the first's session_id. |
| R1-F2 | Interfaces | high | FR-1: specify how `session_id` is returned synchronously — either the caller mints it and injects it into `KickoffFacilitator`, or `start_facilitation` blocks on the first per-round persist. Today `session_id` is created inside `run()` (`facilitation.py:954`). | FR-1 promises `{session_id …}` "immediately" but the id does not exist until `run()` executes; the contract is unbuildable as written without an injection seam. | FR-1 | Test: confirm returns a session_id that a subsequent GET status resolves (round-trip) with zero rounds landed yet. |
| R1-F3 | Data | high | FR-2: replace "a per-call token estimate" with a **round-weighted** estimate — the R3 digest and R5 full-transcript calls cost materially more input tokens than R1. Give a formula (e.g. base per-persona-round + a synthesis multiplier) and label it conservative. | `_synth_prompt` embeds the whole transcript (`facilitation.py:1086`); a flat per-call × `projected_calls` under-promises exactly where spend concentrates — the "$0/wildly-low dry-run is a bug" lesson (§0.1). | FR-2 | Test: dry-run estimate for a 6-persona run is not less than a flat estimate; assert the synthesis term is > a single round's term. |
| R1-F4 | Security | critical | FR-2: add **`tier`** to the run_key binding (`{posture, tier, cap, roster_version, budget}`). As written a `cheap` dry-run mints the same run_key a `premium` confirm echoes → a cheap preview authorizes a premium run. | Focus file names this exactly; `derive_run_key` (`stakeholder_run.py:91`) only hashes `{question,cap,rv}` today — the facilitate key must fold posture+tier in or the 409 guard is defeated. | FR-2 / FR-10 | Test: dry_run(tier=cheap).run_key ≠ dry_run(tier=premium).run_key; confirm with a cheap key against a premium request → 409. |
| R1-F5 | Risks | high | FR-3: define the crash/error → terminal path. If the worker thread dies before writing synthesis/halt, nothing calls `mark_complete` and the transcript stays `in_progress` forever; specify that a status poll after worker death returns terminal `error` (and that `IdempotencyStore` is marked so a resubmit isn't a stuck replay). | FR-3 lists `error` as terminal but no requirement makes anything WRITE it; `KickoffFacilitator.run` only persists `completed`/`halted` (`facilitation.py:1107`,`1150`). | FR-3 | Test: inject a worker that raises mid-run; assert GET status → `error`, not a permanently-`in_progress` transcript. |
| R1-F6 | Ops | high | FR-5: add an acceptance criterion for **concurrent** runs sharing `panel-costs.db` — a run that would push the shared daily ceiling over must fail-closed at a round boundary even though its own `budget_usd` is unspent. | `_budget_guard` only checks the per-run cap; the daily ceiling is request-time only, so two concurrent background runs can jointly breach it with no abort (focus Ask 3). | FR-5 | Test: two concurrent scripted runs, daily ceiling set below their sum; assert the second halts with a budget-cap halt once the shared ledger crosses the ceiling. |
| R1-F7 | Interfaces | medium | FR-9: add acceptance criteria for the plugin poll — a **bounded** poll (max attempts / max wall-clock → surfaces a "still running, check later" state, never infinite), explicit rendering for `status:"error"` and for a 4xx/5xx from the proxy, and a confirmation that Cancel echoes the run_key and reflects `cancelled` in the next poll. | FR-9 describes the happy path (preview→confirm→poll→render) but not the non-terminating/error/cancel branches the focus file flags. | FR-9 | Manual verify checklist in the plugin README: force error, force timeout, force cancel; assert each renders a distinct terminal UI. |
| R1-F8 | Validation | medium | FR-8: make the round-trip testable offline — state that the e2e uses scripted `$0` agents and asserts `status=="completed"` (not merely "synthesis present") before `triage` consumes it, since `build_triage` degrades cleanly on an absent synthesis and would silently pass on an in-progress transcript. | `_triage` (`stakeholder_run_server.py:289`) tolerates a missing synthesis with empty candidates — an e2e that doesn't gate on terminal-completed could green on a half-written transcript. | FR-8 | Test: assert the loaded transcript `status=="completed"` AND `synthesis.text` non-empty before asserting triage candidates. |

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-09 00:00:00 UTC
- **Scope**: ADVERSARIAL / stress-test pass. Tried to break the design against the real code (`stakeholder_run.py` `execute_run`/`IdempotencyStore`/`_RunRegistry`, `stakeholder_run_server.py` routes+`_authorize`+`_NonceStore`, `facilitation.py` `run()`/`_finish_halt`/`_budget_guard`, `kickoff_view/{store,models}.py`). Endorses/disputes R1 by id; adds NEW holes R1 missed. Do-not-relitigate honored (facilitator+postures, fire-and-poll, `/run` auth+run_key, transcript-as-store).

**Executive summary (top NEW risks R1 missed):**
- `cancelled` is NOT a modeled transcript status — `KickoffTranscript` (`kickoff_view/models.py:126`, `is_terminal` line 147) only recognizes `completed|done|halted`; a `cancelled` write would poll as *non-terminal forever*, and FR-6 asserts the transcript "ends `halted`/`cancelled`" without either being writable.
- `KickoffFacilitator.run()` has NO `except CancelledError` — the R1 cancel path (registry→`task.cancel`) unwinds through `run()`'s bare `finally: panel.close()` (`facilitation.py:1112`) and NOTHING persists a terminal state; the transcript is left `in_progress` (distinct from R1-F5's *crash* path — this is the *cancel* path).
- Single-flight has TWO keyspaces the requirements conflate: the in-memory `_RunRegistry` (cleared on `unregister`, so a *completed* run is no longer "in-flight") and the on-disk `IdempotencyStore` (which `execute_run` uses but no facilitate FR wires). FR-4's "already terminal → return current status" is unimplementable via the registry alone.
- Cancel is keyed by `run_key` (`_cancel`, `stakeholder_run_server.py:251`) but a poller only holds `session_id` — FR-6 gives no `session_id→run_key` resolution, so a plugin that got `session_id` from confirm cannot cancel.
- `_authorize` records the replay nonce (`_NonceStore.use`) BEFORE the handler runs, and in strict mode a confirm POST that kicks a multi-$ run burns its nonce even if `start_facilitation` then 500s — a legitimate retry is refused as "replayed".
- FR-2 dry-run for facilitate never runs `ensure_blocking_budget`; the ask-all `dry_run` returns an estimate with no fail-closed check (`stakeholder_run_server.py:193`), so a preview succeeds then the confirm 412s — the estimate is not gated to the budget it will be spent under.

**Numbered suggestions (adversarial pass):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Data | high | FR-6/FR-3: add `cancelled` (and confirm `error`) to the transcript **status enum** and to `KickoffTranscript.is_terminal`. Today `is_terminal` (`kickoff_view/models.py:147`) returns True only for `completed`/`done`/`is_halted`; a `cancelled` transcript polls as non-terminal forever. State the exact literal set: `{in_progress, completed, halted, cancelled, error}`. | FR-6 says the transcript "ends `halted`/`cancelled`" but `cancelled` is not a known terminal state in the model the status route reads — the poll never resolves. | FR-3 (terminal states) / FR-6 | Test: a cancelled transcript's `is_terminal` is True and GET status returns a terminal `cancelled`. |
| R2-F2 | Risks | high | FR-6: require `KickoffFacilitator.run()` (or the worker wrapper) to catch `asyncio.CancelledError` and persist a first-class `cancelled` transcript (like `_finish_halt` does for halts, `facilitation.py:1147`) with the partial rounds kept, BEFORE re-raising/returning. Today `run()` has only `finally: panel.close()` (`facilitation.py:1112`) — a cross-thread cancel leaves `in_progress`. | This is the *cancel* terminal-write gap, distinct from R1-F5's *crash* gap; without it FR-6's "pollable, ends cancelled" is false. | FR-6 | Test: cancel a scripted run mid-round → GET status `cancelled` with `rounds_completed>0`, not `in_progress`. |
| R2-F3 | Interfaces | high | FR-4/FR-6: name the **two-keyspace** single-flight model explicitly — an on-disk `IdempotencyStore`-style marker (survives `unregister` and process restart) for "already terminal → return session_id", PLUS the in-memory `_RunRegistry` for "in-flight → dedupe/cancel". The registry alone cannot answer "already terminal" because `unregister` (`stakeholder_run.py:328`) removes the entry on completion. | FR-4 says "already in-flight OR already terminal → return current status" but the registry is memory-only and cleared at terminal; `execute_run` uses `IdempotencyStore` for exactly this and facilitate must too. | FR-4 | Test: after a run completes and its registry entry is gone, a resubmit of the same run_key still dedupes to the original session_id (from the persisted marker), not a fresh spawn. |
| R2-F4 | Interfaces | medium | FR-6: give the cancel route a `session_id → run_key` path (or accept either), since the confirm response returns `session_id` but `_cancel` is keyed by `run_key` (`stakeholder_run_server.py:251`) and a poller/plugin holds only `session_id`. State whether the transcript persists its `run_key` so cancel can resolve it. | A plugin that polls by `session_id` (FR-3) has no `run_key` to cancel with (FR-6); the two ids are not interchangeable in the current route. | FR-6 | Test: cancel using only the session_id returned by confirm succeeds (or the response also returns run_key and the doc says so). |
| R2-F5 | Security | high | FR-1: in **strict** mode, specify that the confirm's replay-nonce is only consumed on a *successfully spawned* run — today `_authorize` calls `nonces.use` (`stakeholder_run_server.py:139`) before the handler body, so a confirm whose `start_facilitation` then fails burns the nonce and the legitimate retry is rejected "replayed nonce". For a multi-$ paid kick this is a denial-of-retry. | The nonce is single-use TTL-bounded; consuming it before the spawn couples auth replay-protection to spawn success, breaking idempotent retry on transient spawn failure. | FR-1 (auth) | Test: strict-mode confirm where spawn raises → same nonce retried succeeds (or an explicit doc note that a fresh nonce is required and why that is acceptable). |
| R2-F6 | Security | medium | FR-2: state that the facilitate `dry_run` also runs the fail-closed budget check (`ensure_blocking_budget`) so a preview cannot succeed for a run the confirm will 412-refuse. The ask-all `dry_run` returns an estimate with no budget gate (`stakeholder_run_server.py:193`); a facilitate preview that says "$0.43" then a confirm that fail-closes is a UX/trust cliff. | Binds the estimate to the budget it will actually be spent under, per the §0.1 fail-closed lesson; avoids a green preview → 412 confirm. | FR-2 / FR-5 | Test: dry_run with no blocking budget configured returns a warning/412-preview, not a bare estimate. |
| R2-F7 | Risks | medium | FR-1/FR-5: bound the number of concurrently in-flight facilitations (a max, or a queue). The registry is keyed per run_key with no cap; N distinct run_keys spawn N worker threads + N event loops + N premium fleets simultaneously, each individually under its `budget_usd` but jointly a fd/loop/spend storm (compounds R1-F6). | Nothing limits concurrent background runs; an operator or a retrying client can fan out unbounded threads/loops on a shared server. | FR-1 / FR-5 | Test: the (N+1)th concurrent confirm past the cap is rejected 429 or queued, not spawned. |

**Endorsements** (prior untriaged R1 items this reviewer strongly agrees with):
- R1-F4: STRONGLY endorse — confirmed `derive_run_key` (`stakeholder_run.py:91`) hashes only `{q,cap,rv}`; a cheap dry-run authorizing a premium confirm is a real, code-grounded defect. Highest-priority binding fix.
- R1-F5: endorse — verified `run()` only persists `completed`/`halted` (`facilitation.py:1107`,`1150`); nothing writes `error`. R2-F2 adds the *cancel* counterpart to this *crash* case.
- R1-F1: endorse — `_RunRegistry.register` is called inside `_go()` (`stakeholder_run.py:428`), after the task exists; the spawn-race is real. R2-F3 shows the fix must also cover the on-disk keyspace.
- R1-F3: endorse — `_synth_prompt` embeds the whole transcript (`facilitation.py:1086`); a flat per-call estimate under-reads the synthesis call materially.
- R1-F6: endorse — `_budget_guard` (`facilitation.py:1128`) checks only `cfg.budget_usd`; the daily ceiling is request-time only. R2-F7 extends this to a concurrency cap.

**Disagreements** (untriaged prior items I would weight down):
- R1-F2 (partial): I dispute the framing that a synchronous `session_id` return is hard. The transcript session_id is minted deterministically from a UTC timestamp + `uuid4` (`facilitation.py:954`); the simplest fix is to pre-mint it in the caller and inject — not to "block on the first per-round persist" (that would defeat fire-and-poll's immediacy). Keep only the injection option.
