# Workbook — Run the Stakeholder Panel from the UI (Phase 2) — Plan

**Version:** 1.1 (Post-CRP R1 — premise corrected; 7 plan findings accepted)
**Date:** 2026-07-07
**Requirements:** `WORKBOOK_STAKEHOLDER_RUN_REQUIREMENTS.md` (v0.3)

## Planning summary

> ⚠️ **CRP R1 overturned the "mostly wiring" premise (S-1…S-3).** The CLI path wires **no**
> `budget_preflight` and **no** `cost_tracker`; `BudgetManager` is **fail-open** without a configured
> budget; `serve.py` is loopback-only with **no CSRF/Origin** (and the required non-loopback bind
> deletes its one control); `projected_calls` is the wrong cost basis. Phase 2 is a **security-critical
> build**, not wiring. All 7 plan findings accepted (Appendix A). Lifecycle (S-7) is decided below.

The net-new is: (a) a CLI-backed endpoint that **builds** a fail-closed budget gate + cost tracker +
real auth; (b) a **forked** owl workflow-panel (new render path + status schema + run_key confirm); (c)
result-surfacing keyed to the **triggered** session. Reachability (`host.docker.internal`) confirmed.

**Lifecycle decision (S-7):** iteration-1 = **on-demand** endpoint (started by the user; short-lived),
with **re-provision-on-complete** refresh — a smaller LAN attack surface than a standing daemon. A
standing `0.0.0.0` daemon (for Infinity self-refresh) is deferred; it needs stronger auth.

## M0 — CLI-backed run endpoint: BUILD the guardrails (S-1, S-2, S-5)

**Goal:** `POST /stakeholders/run` (+ `GET /stakeholders/run/{id}`) that runs the panel behind a
fail-closed budget gate + real auth; never runs the LLM in Grafana.
- **Build the budget gate (S-1):** construct `BudgetManager` → `budget_preflight(model,
  cost_per_question)` → a `cost_tracker`, and pass **all three** into `StakeholderPanel(...)` (the CLI
  wires none). **Register a blocking budget** (`block_on_exceed=True`, scoped `stakeholder-panel`) and
  **refuse to run if none is configured** — else `check_budget` returns `[]` (fail-open).
- **Build real auth (S-2):** the non-loopback bind (required for `host.docker.internal`) deletes
  `serve.py`'s loopback control. Add: constant-time `APIKeyMiddleware` + Origin allow-list + CSRF token
  + replay nonce; prefer binding the **docker-bridge IP** over `0.0.0.0`. TLS/tunnel if feasible.
- **Contract:** body `{question, cap, dry_run, run_key}`; define the `GET /stakeholders/run/{id}`
  response schema (per-persona answers + status + cost) — a new schema, not the owl `StatusResponse`.
- **Honest dry-run (F-3):** `dry_run=true` returns `min(cap,len(roster)) × per_question_estimate`, **not**
  `projected_calls`. No spend.
- **Crash consistency (S-5):** persist `run_key` + a **spend marker BEFORE the provider call**; a
  re-submit after a crash is recognized, not re-charged. Define transcript-write ordering vs HTTP return.
- **Exit:** dry-run returns the honest estimate + a `run_key`; a confirmed run (echoing the run_key)
  persists a transcript + returns its `session_id`; no budget configured → refuses.

## M1 — Plugin: fork owl workflow-panel — SOURCE BUILT (provisioning = operator/NR-10)

**Status:** `grafana-plugins/kickoff-stakeholders-panel/` — forked, rewritten `src/`, typecheck clean,
`npm run build` succeeds (`dist/module.js`). Implements: question+cap input, dry-run→confirm with the
**run_key echoed** (the base ignored it), per-persona **UNRATIFIED** render (base rendered run-steps),
and **datasource-proxy token routing** (base sent no creds — token via `secureJsonData`, never in the
panel/dashboard JSON). **NOT provisioned** to the shared KinD Grafana — that needs the unsigned
allow-list + a restart affecting the online-boutique dashboards (NR-10), an operator step (see the
plugin README).


**Goal:** trigger + honest dry-run preview + confirm modal + status poll + render answers.
- **Token delivery is a hard EXIT GATE (S-3):** the base plugin's `fetch()` sends **no credentials**, and
  a panel-option token is **world-readable in dashboard JSON**. Route through the `contextcore-datasource`
  **server-side proxy** (adds `X-API-Key` out of the browser's reach). No token in the panel/dashboard.
- **New render path + status schema (S-6):** not a payload tweak — render per-persona `PanelAnswer`
  (`grounding`, `flags`, cost, **SYNTHETIC & UNRATIFIED** banner) + poll the new `GET /stakeholders/run/{id}`.
- **run_key integrity (S-4):** the dry-run mints `run_key`; the confirm **echoes** it (the base confirm
  re-POSTs fresh — must be changed); the server validates the `{question,cap,roster_version}` hash.
- **NR-10:** unsigned → confirm/enable the allow-list + plan the shared-Grafana restart BEFORE
  provisioning. Pin the fork commit.
- **Exit:** dry-run preview renders the honest estimate; confirm (with run_key, via the proxy) triggers
  M0; per-persona answers render UNRATIFIED.

## M2 — Surface results in the Workbook

**Goal:** the Stakeholders section shows the latest run's answers.
- Extend `portal_spec._stakeholders_section` to render the latest transcript
  (`.startd8/stakeholder-panel/<id>.json`) — role → answer, UNRATIFIED-tagged. Keep display-only ($0).
- **Refresh (OQ-3):** start with **re-provision-on-complete** (simplest, no standing exposure); add
  Infinity-over-endpoint self-refresh only if the live loop is wanted.
- **Session-keyed render (S-F5):** the section renders the **specific `session_id` M0 returned**, not
  "latest by mtime" (which races under concurrent runs). Phase 1.5's latest-mtime render is fine for
  single-user CLI display, but the triggered loop must key on the returned id.
- **Exit:** after a run, the section shows that run's answers.

## M3 — Guardrail hardening + audit + cancel/ceiling (S-5, S-7)

- Idempotency + rate-limit finalized; **crash-marker recovery** (re-submit after crash not re-charged);
  partial-failure reporting (per-persona status). Per-run audit line (who/when/question/cap/estimated+
  actual cost/session_id) via transcript + the M0-built `cost_tracker`.
- **Daily USD ceiling — SHIPPED:** `ensure_daily_ceiling()` registers a DAILY `block_on_exceed` budget
  (also satisfies the fail-closed gate); `kickoff stakeholders serve --daily-ceiling` sets it. Aborts
  before the next run's calls exceed the day's cap.
- **Cancel/abort — SHIPPED:** `POST /stakeholders/run/{run_key}/cancel` + `cancel_run()`. A run executes
  in a worker thread's own event loop; a `_RunRegistry` holds `(loop, task)` so a cancel request (a
  different thread) aborts it cross-thread via `loop.call_soon_threadsafe(task.cancel)`. Personas that
  already answered persist to the transcript (incremental); in-flight LLM calls are aborted; the run
  returns `status="cancelled"` with the partial. (No full async-job refactor needed — the sync response
  contract is preserved.)

## M4 — Pilot + verdict on household

- Scaffold a household roster (`kickoff instantiate`), run `ask-all` from the Workbook, confirm results
  render + are UNRATIFIED + do not touch kickoff inputs. Short verdict: is running-from-UI worth the
  spend-in-dashboard posture, or does it stay CLI-only with the Workbook read-only?

## Traceability

| Req | Milestone |
|---|---|
| FR-1 trigger | M1 |
| FR-2 CLI-routed endpoint | M0 |
| FR-3 dry-run before spend | M0 + M1 |
| FR-4 fail-closed guardrails | M0 + M3 |
| FR-5 transcript results | M0 + M2 |
| FR-6 UNRATIFIED, no auto-ratify | M1 + M2 |
| FR-7 workflow-panel fork | M1 |
| FR-8 reflect in Workbook | M2 |
| FR-9 audit | M3 |
| FR-10 pilot | M4 |

## Risks

1. **The guardrails don't exist yet (CRP S-1)** — the budget gate + cost tracker + real auth are
   net-new; the "inherited from CLI" assumption was false. This is the dominant scope + security risk.
2. **Unauthenticated spend endpoint on the LAN (S-2)** — the non-loopback bind + no CSRF/Origin/replay
   must be fixed before the endpoint is reachable; prefer docker-bridge IP over `0.0.0.0`.
3. **Token delivery (S-3)** — world-readable panel token unless routed via the datasource proxy; gates M1.
4. **Double-charge (S-4/S-5)** — run_key integrity + a pre-call spend marker must hold.
5. **Unsigned plugin on shared KinD Grafana (NR-10)** — allow-list + restart affects other dashboards.

---

## Appendix A — Accepted (Applied)

> CRP R1 — all 7 plan findings accepted; applied to Planning summary + M0/M1/M2/M3 + Risks.

- **[S-1]** ACCEPTED → M0 builds `BudgetManager`+preflight+tracker + a blocking budget (not inherited).
- **[S-2]** ACCEPTED → M0 adds constant-time key + Origin + CSRF + replay on the non-loopback bind.
- **[S-3]** ACCEPTED → M1 token via `contextcore-datasource` server-side proxy = exit gate.
- **[S-4]** ACCEPTED → M0/M1 run_key minted by dry-run, echoed + hash-validated by confirm.
- **[S-5]** ACCEPTED → M0/M3 pre-call spend marker; crash-safe recovery.
- **[S-6]** ACCEPTED → M1 re-scoped to a new render path + status schema.
- **[S-7]** ACCEPTED → lifecycle decided (on-demand + re-provision); M3 adds cancel + daily ceiling.

## Appendix B — Rejected (with rationale)

_None — all findings code-grounded and accepted._

## Appendix C — Incoming Review

#### Review Round R1 (independent CRP, 2026-07-07)

- **[S-1]** [BLOCKER] (M0) "Invokes `StakeholderPanel.ask_all` behind `budget_preflight()` + `--cap`" implies the guardrail is inherited from the CLI. It is **not**: `cli_panel.py:panel_ask_all` constructs the panel with **no `budget_preflight` and no `cost_tracker`** (see requirements F-1), so `preflight_budget()` is a no-op and cost is always `0.0` there. M0 must **explicitly build** `BudgetManager` → `budget_preflight(manager, model=…, cost_per_question=…)` (budget.py:28) → and a `cost_tracker`, and pass **all three** into `StakeholderPanel(...)`. Add a sub-task: register a **blocking** budget (`block_on_exceed=True`, scoped `project="stakeholder-panel"`) — without it `check_budget` returns `[]` and never blocks (budget.py:220-252 = fail-open). Update the traceability row for FR-4 to reflect this is **net-new wiring**, not reuse.
- **[S-2]** [BLOCKER] (M0) "Reuse `serve.py` auth posture (loopback/host bind, token, CSRF/origin)… bind `0.0.0.0` … token-gated" is not achievable by reuse: `serve.py` binds `127.0.0.1` and its **only** token is `server/auth.py:APIKeyMiddleware` — cloud-mode-only, POST `X-API-Key`, **non-constant-time compare, no CSRF, no Origin check, no replay** (auth.py:24-33). M0 must add, as explicit deliverables: mount `APIKeyMiddleware` (constant-time compare) on the `0.0.0.0` listener + an **Origin allow-list** + **CSRF token** + **replay nonce**. Binding `0.0.0.0` is required for `host.docker.internal` (loopback is unreachable from the pod) and therefore **deletes the loopback control** the rest of serve.py assumes.
- **[S-3]** [BLOCKER] (M1, OQ-1) The token-delivery problem is **unsolved and gates the whole spend endpoint**. The base owl plugin's `fetch()` calls (`WorkflowPanel.tsx:67`, `:108`, `:36`) send **no credentials at all** — there is no code path to attach a token from the panel. A panel-option token is **world-readable in the dashboard JSON** (anyone with Grafana view access reads it). M1 must specify server-side injection via the `contextcore-datasource` proxy (which can add `X-API-Key` out of the browser's reach) as a hard requirement, and treat "how the token reaches Grafana" as an M1 exit gate — not a later OQ.
- **[S-4]** [SHOULD] (M0, M1) Dry-run→confirm **integrity** is missing from the fork's base behavior: dry-run and execute are **independent POSTs to the same `/workflow/run`**, and the confirm modal (`handleConfirmExecute` :135) calls `executeWorkflow` which **discards the dry-run's `run_id`** and re-POSTs fresh. Nothing guarantees the confirmed run == the previewed one. M0's `run_key` must be **minted by the dry-run**, returned to the panel, **echoed by the confirm**, and the server must **validate the `{question, cap, roster_version}` hash matches** the preview before spending. Add this to the M1 fork deltas explicitly.
- **[S-5]** [SHOULD] (M0, M3) **Crash-after-spend consistency** is unaddressed. `ask()` appends to the transcript **best-effort, swallowing `OSError`** (panel.py:205-213); a crash between the LLM call (spend) and the HTTP response loses the answer with no idempotent recovery, and the user re-runs → **double spend**. M3's "missing key = clean fail" check is not the same as this. Specify: **commit the idempotency key + a spend marker BEFORE the provider call** (persisted, not in-memory TTL) so a re-submit after a crash is recognized and not re-charged; define transcript-write ordering relative to the HTTP return.
- **[S-6]** [SHOULD] (M1) The response-shape change is larger than "a delta." The base plugin renders `DryRunStep[]` / `StatusResponse` (types.ts); per-persona `PanelAnswer` carries `grounding`, `flags`, cost, and needs the **SYNTHETIC & UNRATIFIED** banner — a **different data model**, and the poll endpoint (`GET /workflow/status/{id}` vs your `GET /stakeholders/run/{id}`) returns a different shape too. Budget the fork for a **new render path + new status schema**, not a payload tweak, and add the `GET /stakeholders/run/{id}` response schema to M0.
- **[S-7]** [CONSIDER] (M0, M2, OQ-3) Endpoint **lifecycle** is unresolved but the milestones quietly assume conflicting answers: M2's default (re-provision-on-complete) implies a **short-lived on-demand** endpoint, while Infinity self-refresh needs a **standing `0.0.0.0` daemon** — a materially larger LAN attack surface. Decide before M0; a standing spend daemon on the LAN needs stronger auth than an on-demand one. Also add (M3) a **cancel/abort** path (poll already exists; add abort) and a **cumulative daily/session USD ceiling** reusing `FacilitationConfig.budget_usd`'s cumulative-abort pattern.

_Total: 7 findings (3 BLOCKER, 3 SHOULD, 1 CONSIDER). Not triaged — orchestrator dispositions to Appendix A/B._
