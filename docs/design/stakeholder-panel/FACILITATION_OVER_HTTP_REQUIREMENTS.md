# Facilitation over HTTP (F1) — Grafana-drivable multi-round panel + posture

**Version:** 0.4 (Decisions + lessons-hardening — pre-CRP)
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
