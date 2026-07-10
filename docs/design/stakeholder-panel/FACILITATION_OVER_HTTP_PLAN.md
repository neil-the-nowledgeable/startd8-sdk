# Facilitation over HTTP (F1) — Implementation Plan

**Version:** 1.1 (CRP-hardened; paired with REQUIREMENTS v0.5 §2.1 H-1…H-18)
**Target:** `kickoff_experience/stakeholder_run_server.py` + `stakeholder_run.py` +
`stakeholder_panel/facilitation.py` + a shared cost-tracker helper + `grafana-plugins/kickoff-stakeholders-panel/`.

> Reuse the facilitator + registry + cost + persistence; add transport + async orchestration + a cheap tier.

## Sequencing
```
M1 cheap tier      (FR-10: CHEAP_FAMILIES + FacilitationConfig.tier + assign_models tier-aware + transcript records tier)
M2 facilitate core (FR-1/2: a facilitate dry_run estimator + an async kickoff runner in stakeholder_run.py)
M3 routes          (FR-1/3/4/6: POST /facilitate, GET /facilitate/{sid}, POST /facilitate/{run_key}/cancel)
M4 budget          (FR-5: shared _build_cost_tracker + budget_usd + daily ceiling wired into the runner)
M5 e2e             (FR-8: facilitate→status=completed→triage round-trips)
M6 plugin          (FR-9: facilitate mode + posture/tier selectors + poll loop in the TS panel)
M7 guards          (tests: dry_run estimate, single-flight/idempotency, status transitions, cancel, tier, fail-closed budget)
```

## Per-milestone

### M1 — cheap tier (`facilitation.py`)
- `CHEAP_FAMILIES = {"claude": "anthropic:claude-haiku-4-5-20251001", "gpt": "openai:gpt-5-mini",
  "gemini": "gemini:gemini-2.5-flash"}` (resolve real ids via `model_catalog`); keep de-correlation.
- `FacilitationConfig.tier: str = "premium"` (validate {premium,cheap} in `__post_init__`).
- `assign_models(briefs, *, tier)` picks the family set by tier; `projected_calls` unchanged (count only);
  add a per-tier per-call token estimate for the dry-run. Record `tier` in the session dict + transcript.

### M2 — facilitate core (`stakeholder_run.py`)
- `facilitate_dry_run(project, roster, posture, tier, budget) -> FacilitateDryRun` — `projected_calls` ×
  per-call estimate → `{run_key, posture, tier, n_participants, projected_calls, estimated_cost_usd, models}`.
  `run_key = derive_run_key(f"facilitate:{posture}:{tier}", cap, roster_version)`.
- `start_facilitation(project, cfg, run_key, cost_tracker) -> session_id` — build `KickoffFacilitator`,
  spawn its `run()` in a **background worker thread with its own event loop**, register `(loop, task)` in
  `_RUN_REGISTRY` under `run_key`, return the session_id synchronously (transcript created `in_progress` at
  round 0). Single-flight: if `run_key` is registered/terminal, return the existing session_id (FR-4).
- Persistence + status come free from `KickoffFacilitator._persist`.

### M3 — routes (`stakeholder_run_server.py`)
- `POST /stakeholders/facilitate` — auth + strict/nonce (reuse `_authorize`, `_apply_guard` posture);
  `dry_run` → `facilitate_dry_run`; confirm (needs `run_key`) → `start_facilitation`, return `{session_id,
  status, run_key}` (202-style, but 200 for proxy simplicity).
- `GET /stakeholders/facilitate/{session_id}` — `KickoffViewService.load` → `{status, rounds_completed,
  cost_so_far_usd, synthesis?, halt?, posture, tier}`; 404 if unknown.
- `POST /stakeholders/facilitate/{run_key}/cancel` — `cancel_run`.
- Register the 3 routes; extend the module docstring's endpoint list.

### M4 — budget (`stakeholder_run.py` / server)
- Lift `_build_cost_tracker` from the CLI script into a shared module (e.g. `costs` helper or
  `stakeholder_run.build_panel_cost_tracker`); wire into `start_facilitation`. `budget_usd` → the config's
  cumulative-abort; the endpoint daily ceiling via `ensure_daily_ceiling`. Missing budget config →
  fail-closed (no untracked $0 run).

### M5 — e2e (test)
- A `$0` offline facilitate (scripted agents) → status `completed` → `build_triage(load(sid))` yields
  candidates. Proves the session id round-trips into the bridge (FR-8).

### M6 — plugin (`grafana-plugins/kickoff-stakeholders-panel/src/`)
- `module.ts`: add `facilitate` to the `mode` radio; add `posture` (radio scrutiny|prototype) + `tier`
  (radio premium|cheap) options.
- `components/FacilitatePanel.tsx`: posture/tier inputs → **Preview cost** (POST dry_run via the datasource
  proxy) → confirm modal (echo run_key) → POST confirm → **poll** `GET /facilitate/{sid}` every ~5s until
  terminal → render synthesis / halt with the SYNTHETIC & UNRATIFIED banner; a Cancel button hits the cancel
  route. Token stays server-side (proxy). `npm run typecheck && npm run build`.
- README: document the facilitate mode + the unsigned-plugin build+restart operator step.

### M7 — guards (`tests/unit/kickoff_experience/` + `stakeholder_panel/`)
- tier: assign_models(tier=cheap) uses CHEAP_FAMILIES, de-correlated; config validates tier; dry-run cost
  scales with tier.
- facilitate_dry_run: estimate + run_key stable; run_key binds posture/tier.
- start_facilitation: single-flight (same run_key → same session_id, no second spawn); status transitions
  in_progress→completed / →halted (scripted agents, offline $0); cancel signals + transcript ends
  non-running.
- routes: auth required; dry_run $0; confirm needs run_key; status 404 on unknown; fail-closed budget.
- e2e (M5).

## Backward-compat / risk register
- **Long-running thread lifecycle** — the background worker + its event loop must be cleaned up
  (unregister on completion/error); mirror `execute_run`'s task handling. Server shutdown should not hang.
- **Cost tracker sharing** — one tracker instance vs per-run; `panel-costs.db` writes are serialized
  (existing `_STORE_LOCK`).
- **run_key namespace** — facilitate run_keys must not collide with ask-all run_keys (prefix `facilitate:`).
- **Plugin can't be unit-tested here** — rely on typecheck + a documented manual verify; keep the panel a
  thin driver over the (tested) routes.
- **Model ids** — verify the cheap-tier ids resolve in `model_catalog`/providers before shipping (a bad id
  → infra-fail, not a model 0).

## Definition of done
All FRs mapped; M7 guards green + ruff clean; a `$0` offline facilitate round-trips facilitate→status→triage;
the plugin typechecks+builds; cheap-tier dry-run is ~10× the… (order-of-magnitude) cheaper than premium.

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
- **Scope**: Plan review weighted to the focus file — the M2 async runner (background thread + own loop, single-flight, terminal-on-crash), M1 tier + dry-run cost accuracy, M4 fail-closed budget across concurrent runs, M3 route collision + status store, M6 plugin poll/error/cancel. Grounded in `stakeholder_run.py`, `stakeholder_run_server.py`, `facilitation.py`.

**Executive summary (top risks / gaps):**
- M2 `start_facilitation` is described as reusing `execute_run`'s task handling, but `execute_run` runs `asyncio.run` **synchronously in-thread** and returns only on completion — the background-thread-own-loop runner is net-new; the plan under-scopes it.
- Single-flight (M2/FR-4) has a spawn-race: the existing registry registers **inside** the run coroutine, so the guard must move earlier under a lock.
- `session_id` is minted inside `KickoffFacilitator.run()`; M2 cannot "return the session_id synchronously" without an injection seam — unspecified.
- M3 GET status route reuses the wrong store: `_status` reads `TranscriptStore` (ask-all per-answer), not the kickoff-panel transcript; the plan says `KickoffViewService.load` but must also avoid the `/stakeholders/run/{session_id}` path collision.
- M1 dry-run cost is round-flat; the R5 synthesis call embeds the whole transcript → estimate under-reads. `run_key` must fold in `posture`+`tier` (M2 shows the prefix but the plan doesn't bind tier into the hash consistently).
- M4 wires the daily ceiling at request time only; no mechanism aborts a long-running background run when a concurrent run breaches the shared ceiling.
- No terminal-`error` writer: a worker crash leaves the transcript `in_progress` and the run_key `started` forever.

**Numbered suggestions:**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Architecture | high | M2: scope `start_facilitation`'s background worker as a **new** primitive, not a reuse of `execute_run`. Spell out: spawn a `threading.Thread`, create `asyncio.new_event_loop()` in it, `loop.run_until_complete(facilitator.run())`, and in a `finally` unregister + persist a terminal state. The risk register's "mirror `execute_run`'s task handling" is misleading — `execute_run` (`stakeholder_run.py:435`) is synchronous. | Prevents the implementer from copying a blocking pattern into a fire-and-poll route. | M2 / risk register | Code review + a test asserting the POST returns before `run()` completes (worker still in_progress). |
| R1-S2 | Risks | high | M2: register the run_key in the registry (and take the single-flight decision) **before** starting the thread, under one lock — not inside `run()`. Today `_RunRegistry.register` runs inside `_go()` (`stakeholder_run.py:428`). | Two near-simultaneous confirms could both see "not registered" and both spawn (double-spend). | M2 (single-flight bullet) | Test: concurrent identical confirms → exactly one thread/transcript; second returns the first session_id. |
| R1-S3 | Interfaces | high | M2: add the `session_id` seam — either pre-mint the id in `start_facilitation` and inject it into `KickoffFacilitator` (add a `session_id` param / factory), or have the runner block on the first `_persist` and read it back. State which. | The plan asserts "return the session_id synchronously (transcript created in_progress at round 0)" but the id is created inside `run()` (`facilitation.py:954`); the transcript isn't written until R0 either. | M2 | Test: confirm's returned session_id resolves via GET status with 0 rounds landed. |
| R1-S4 | Interfaces | high | M3: the GET status route must load the **kickoff-panel** transcript via `KickoffViewService.load` (returns `KickoffTranscript` with `.status/.synthesis/.rounds/.cost_total_usd`), NOT the existing `_status` which reads `TranscriptStore` (ask-all answers). Also give it a distinct path — `/stakeholders/run/{session_id}` already exists (`stakeholder_run_server.py:800`); use `/stakeholders/facilitate/{session_id}`. | Reusing `_status` would 404 (no ask-all answers) on a real facilitation; a shared path collides with the ask-all status route. | M3 | Test: GET the facilitate status of a facilitated session returns rounds_completed/synthesis; assert it does not resolve as an ask-all run. |
| R1-S5 | Data | high | M1/M2: make the dry-run estimate **round-weighted**. `projected_calls` is a count only (`facilitation.py:737`); add a per-tier per-round token model where R3 (digest) and R5 (full transcript, `facilitation.py:1086`) carry a synthesis/context multiplier. Keep it conservative (over-estimate). | A flat per-call estimate under-reads exactly the priciest calls — the "$0/too-low dry-run is a bug" lesson the doc cites (§0.1). | M1 (dry-run cost) / M2 (`facilitate_dry_run`) | Test: synthesis-term > single-round-term; cheap-tier estimate ≈ 1/10 premium at equal shape. |
| R1-S6 | Security | critical | M2: bind BOTH `posture` and `tier` into the run_key hash, and validate on confirm. The plan's `derive_run_key(f"facilitate:{posture}:{tier}", cap, roster_version)` puts them in the "question" slot — good — but make it explicit that confirm re-derives with the *request's* posture/tier and 409s on mismatch, so a cheap dry-run can't authorize a premium run. | `derive_run_key` (`stakeholder_run.py:91`) hashes its first arg; the confirm-side re-derivation + 409 must be stated or the binding is inert. | M2 / M3 (confirm) | Test: cheap dry_run key + premium confirm → 409; same posture+tier round-trips. |
| R1-S7 | Ops | high | M4: add a concurrent daily-ceiling abort. Wire the background runner's round-boundary guard to consult the shared `CostTracker`/`BudgetManager` daily ceiling (not just `cfg.budget_usd`), so a run halts when a *concurrent* run has pushed `panel-costs.db` over the ceiling. Note `_STORE_LOCK` serializes writes but does not gate spend. | `_budget_guard` (`facilitation.py:1128`) only checks the per-run cap; the daily ceiling is request-time only → two background runs jointly breach it silently. | M4 / risk register | Test: two scripted concurrent runs with a ceiling below their sum → second halts budget_cap once the ledger crosses. |
| R1-S8 | Risks | high | M2: add a terminal-`error` writer in the worker's `finally`/`except`: on an unhandled exception, persist the transcript as `status:"error"` (a first-class state like halt) and `mark_complete`/mark-error the run_key, then unregister. | Nothing writes `error` today — a crash leaves `in_progress` + a `started` run_key forever, defeating FR-3's terminal contract and stranding the idempotency slot. | M2 / M7 guards | Test: inject a raising worker → GET status `error`; a resubmit is not a stuck replay. |
| R1-S9 | Validation | medium | M7: add a leak/shutdown guard — assert the worker thread is joined/daemonized and the registry entry is removed on every terminal path (completed/halted/error/cancelled), and that server shutdown does not hang on an in-flight run (risk register names this but M7 lists no test). | The risk register calls out "server shutdown should not hang" and "unregister on completion/error" with no corresponding guard. | M7 | Test: after a completed and a cancelled run, `_RUN_REGISTRY._runs` is empty and no non-daemon thread survives. |
| R1-S10 | Ops | medium | M6: bound the plugin poll (max attempts / wall-clock) and specify the error/timeout/cancel UI states; document that a never-terminating run yields a "still running" state, not an infinite loop, and that `status:"error"`/proxy-5xx render a distinct banner. | M6 lists a 5s poll "until terminal" with no bound and no error branch; a stuck `in_progress` (see R1-S8) would poll forever. | M6 | Manual verify: force error/timeout/cancel, confirm three distinct terminal UIs. |

#### Review Round R2 — claude-opus-4-8-1m — 2026-07-09

- **Reviewer**: claude-opus-4-8-1m
- **Date**: 2026-07-09 00:00:00 UTC
- **Scope**: ADVERSARIAL / stress-test pass on the PLAN. Tried to break M1–M7 against the real code (`stakeholder_run.py` `execute_run`/`IdempotencyStore`/`_RunRegistry`; `stakeholder_run_server.py` routes+`_authorize`+`_NonceStore`; `facilitation.py` `run()`/`_finish_halt`/`_budget_guard`/session_id mint; `kickoff_view/{store,models}.py`). Endorses/disputes R1 by id; adds NEW gaps R1 missed. Do-not-relitigate honored (facilitator+postures, fire-and-poll, `/run` auth+run_key, transcript-as-store).

### Stress-test / adversarial pass

**Executive summary (NEW gaps R1 missed):**
- M2 wires single-flight through `_RUN_REGISTRY` only, but that store is memory-only and `unregister`ed at terminal (`stakeholder_run.py:328`) — a *completed* run is no longer "in-flight", so FR-4 dedupe needs the on-disk `IdempotencyStore` M2 doesn't mention.
- M2/M6 never persist a `cancelled` transcript; `KickoffFacilitator.run()` has no `except CancelledError`, and `cancelled` isn't in `is_terminal` (`kickoff_view/models.py:147`) — the plugin poll loop (M6) would spin forever on a cancelled run.
- M4 lifts `_build_cost_tracker` into a shared helper but doesn't state whether concurrent facilitations share ONE `CostTracker`/`CostStore` instance or one each; `.startd8/costs.db` (`stakeholder_run_server.py:154`) writes must be serialized, and the daily ceiling must be read from the shared store not a per-run tracker.
- M3 cancel route is keyed by `run_key`; M6's poll loop holds only `session_id` — the plugin's Cancel button has no `run_key` unless the confirm response carries it (M3 returns `{session_id, status, run_key}` — good — but M6 must thread run_key, not just session_id, into the cancel call).
- M6/M3 in strict mode: `_authorize` burns the replay nonce (`stakeholder_run_server.py:139`) before the handler runs, so a confirm whose spawn fails cannot be retried with the same nonce — a denial-of-retry on a paid kick.

**Numbered suggestions (adversarial):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Data | high | M2: wire an on-disk idempotency marker (reuse `IdempotencyStore`, `stakeholder_run.py:142`) for facilitate single-flight, NOT the `_RUN_REGISTRY` alone. The registry is `unregister`ed at terminal (`stakeholder_run.py:328`), so "already terminal → return session_id" (FR-4) is unanswerable from it; `execute_run` already uses `IdempotencyStore` for this. | Without the persisted marker, a resubmit after completion re-spawns (double-spend) once the registry entry is gone; the registry only covers *in-flight*. | M2 (single-flight bullet) | Test: after a run completes and the registry is empty, resubmitting the same run_key dedupes to the original session_id. |
| R2-S2 | Risks | high | M2: add an `except asyncio.CancelledError` in the worker that persists a first-class `cancelled` transcript (mirror `_finish_halt`, `facilitation.py:1147`), keeping partial rounds, before unregistering. Today `run()` unwinds a cancel through `finally: panel.close()` (`facilitation.py:1112`) with no terminal write. | The M3 cancel route signals the task but nothing writes a terminal state → M6's poll never terminates; this is the *cancel* dual of R1-S8's *crash* case. | M2 (worker finally/except) | Test: cancel a scripted run → GET status `cancelled` with rounds>0, poll loop exits. |
| R2-S3 | Data | high | M2/M3: add `cancelled` and `error` to the transcript status enum and to `KickoffTranscript.is_terminal` (`kickoff_view/models.py:147`), which today recognizes only `completed`/`done`/`halted`. State the literal terminal set the GET route and the plugin both key on. | A `cancelled`/`error` write that `is_terminal` doesn't recognize makes the status route report non-terminal forever (poll spins). | M2 / M3 | Test: `is_terminal` True for `cancelled` and `error`; GET status returns them terminal. |
| R2-S4 | Ops | high | M4: state the cost-tracker sharing model explicitly — one process-wide `CostTracker` over one `CostStore(.startd8/costs.db)` shared by all concurrent facilitations, with serialized writes, and the daily-ceiling read from that shared store (not a per-run tracker). The risk register mentions `_STORE_LOCK` but M4 doesn't say the daily ceiling consults the shared ledger. | Two concurrent runs each with a private tracker can't see each other's spend → the concurrent-ceiling abort (R1-S7) is impossible without a shared store; also `costs.db` write races. | M4 / risk register | Test: two concurrent scripted runs record into one `costs.db`; the daily-ceiling query sums both. |
| R2-S5 | Interfaces | medium | M6: thread the confirm response's `run_key` (not just `session_id`) into the plugin state so the Cancel button can call `POST /facilitate/{run_key}/cancel` (M3 keys cancel by run_key). A panel that only kept `session_id` from the poll cannot cancel. | M3's cancel route path param is `run_key`; the poll uses `session_id` — the two are distinct and non-interchangeable. | M6 (FacilitatePanel state) | Manual verify: Cancel from the panel actually aborts the run (run_key present in panel state). |
| R2-S6 | Security | medium | M3/M6: in strict mode, document that the confirm's replay-nonce is consumed at `_authorize` (`stakeholder_run_server.py:139`) BEFORE spawn, so a spawn failure requires a *fresh* nonce on retry — or move nonce-consumption to after a successful spawn. A browser auto-retry of a failed paid confirm otherwise gets "replayed nonce". | Couples replay protection to spawn success; a transient spawn error becomes a denial-of-retry on a multi-$ kick. | M3 / M6 | Test: strict-mode confirm where spawn raises → retry with same nonce behavior is documented and tested. |
| R2-S7 | Risks | medium | M2/M4: cap concurrent in-flight facilitations (a max or a queue). Nothing bounds distinct run_keys; N confirms spawn N threads + N event loops + N premium fleets — a fd/loop/spend fan-out even with per-run `budget_usd` intact (compounds R1-S7). | The registry is unbounded; an operator or retrying client can exhaust threads/loops/spend on a shared Grafana-fronted server. | M2 / M4 | Test: the (cap+1)th concurrent confirm is 429'd or queued, not spawned. |

**Endorsements** (prior untriaged R1 plan items I strongly agree with):
- R1-S6: STRONGLY endorse — `derive_run_key` (`stakeholder_run.py:91`) hashes its first arg only; the confirm-side re-derive + 409 MUST be stated or the posture/tier binding is inert. Top binding fix.
- R1-S1: endorse — `execute_run` (`stakeholder_run.py:435`) is `asyncio.run(...)` synchronous in-thread; "mirror execute_run's task handling" is misleading, the background-loop runner is net-new.
- R1-S2: endorse — registration inside `_go()` (`stakeholder_run.py:428`) is the real spawn-race; move it before thread start under one lock. R2-S1 adds the on-disk half.
- R1-S4: endorse — `_status` (`stakeholder_run_server.py:227`) reads `TranscriptStore` (ask-all answers), which would 404 on a facilitation; must use `KickoffViewService.load`.
- R1-S8: endorse — no `error` writer today; R2-S2/S3 add the `cancelled` terminal path alongside it.

**Disagreements** (untriaged prior items I would weight down):
- R1-S3: I dispute the "block on the first `_persist`" alternative — that reintroduces a blocking wait into a fire-and-poll route. Pre-minting the session_id in `start_facilitation` and injecting it into `KickoffFacilitator` is the only option that preserves immediacy; drop the block-on-persist branch.

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan milestone(s) that carry it.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (async kickoff route) | M2 (`start_facilitation`) + M3 (POST route) | Partial | Background-thread-own-loop runner is net-new, not a reuse of `execute_run` (R1-S1); registry-before-spawn (R1-S2) and synchronous `session_id` seam (R1-S3) unspecified. |
| FR-2 (dry-run cost pre-flight) | M1 (per-tier estimate) + M2 (`facilitate_dry_run`) | Partial | Estimate is round-flat, under-reads R3/R5 (R1-S5); run_key must bind posture+tier and confirm re-derive+409 (R1-S6). |
| FR-3 (status poll) | M3 (GET route) | Partial | Route reuses wrong store/path (R1-S4); no terminal-`error` writer on worker crash (R1-S8). |
| FR-4 (single-flight + idempotency) | M2 (single-flight bullet) | Partial | Spawn-race — registration happens inside the run coroutine today (R1-S2). |
| FR-5 (fail-closed budget) | M4 (cost tracker + ceiling) | Partial | Daily ceiling is request-time only; no concurrent-run mid-flight abort (R1-S7). |
| FR-6 (cancel) | M2 (`_RUN_REGISTRY`) + M3 (cancel route) | Full | Reuses `cancel_run` cross-thread abort; keyed by run_key. Depends on R1-S2 registration timing. |
| FR-7 (posture selection + framing) | M1/M2 (posture threaded) + M3 (echo) | Full | `FacilitationConfig.posture` + prototype/scrutiny framing already exist; plan threads them through. |
| FR-8 (feed the bridge) | M5 (e2e) | Partial | e2e should gate on terminal-`completed` + non-empty synthesis, not merely synthesis-present (R1-S8/F8). |
| FR-9 (Grafana plugin facilitate mode) | M6 (plugin) | Partial | Poll unbounded; error/timeout/cancel UI states unspecified (R1-S10). |
| FR-10 (cheap tier) | M1 (CHEAP_FAMILIES + tier) | Full | Adds tier to config/assign_models/transcript; dry-run reflects tier (pairs with R1-S5 estimate accuracy). |
| NR-1..NR-5 (no new logic/store/blocking/streaming/auto-deploy) | Reuse across M1–M6 | Full | Plan respects reuse-only constraints; plugin left operator-gated. |

## Requirements Coverage Matrix — R2 (deltas vs R1)

Adversarial pass. Only rows whose coverage/gap assessment CHANGES vs R1 are listed; unlisted rows stand as R1 rated them.

| Requirement | Plan Step(s) | Coverage (R2) | Delta vs R1 |
| ---- | ---- | ---- | ---- |
| FR-4 (single-flight + idempotency) | M2 | Partial | **Downgraded scope of gap:** R1 caught the spawn-race; R2 adds that the registry is memory-only and `unregister`ed at terminal, so "already terminal → return session_id" needs an on-disk marker (`IdempotencyStore`) M2 omits (R2-S1). |
| FR-6 (cancel) | M2 + M3 | **Partial (was Full in R1)** | R1 rated Full; adversarially it is NOT: no `except CancelledError` writes a terminal `cancelled` transcript (R2-S2), `cancelled` isn't in `is_terminal` (R2-S3), and cancel is keyed by run_key while the poller holds only session_id (R2-S5). |
| FR-5 (fail-closed budget) | M4 | Partial | R2 adds the cost-tracker **sharing model** gap — concurrent runs need one shared `CostStore` with serialized writes and a shared-ledger ceiling read (R2-S4), a precondition R1-S7's concurrent abort silently assumes. |
| FR-3 (status poll) | M3 | Partial | R2 adds that the terminal enum itself is incomplete (`cancelled`/`error` not modeled, R2-S3) — the route can report a non-terminal state forever, beyond R1-S4's wrong-store finding. |
