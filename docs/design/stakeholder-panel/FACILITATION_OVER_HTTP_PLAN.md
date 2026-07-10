# Facilitation over HTTP (F1) — Implementation Plan

**Version:** 1.0 (paired with REQUIREMENTS v0.3)
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
