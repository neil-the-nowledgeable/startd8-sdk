# Facilitation Ops Hardening (#9 + #10) — Implementation Plan

**Version:** 1.0 (Post-draft planning pass)
**Date:** 2026-07-10
**Requirements:** `FACILITATION_OPS_HARDENING_REQUIREMENTS.md` v0.1

---

## Planning discoveries

Grounded against `facilitate_run.facilitate_status`, `kickoff_view/store.py` + `facade.py`, `metrics.py`,
`stakeholder_run.IdempotencyStore`.

| Draft assumption | Planning revealed | Impact |
|------------------|-------------------|--------|
| Need to add a mtime accessor | `KickoffPanelStore.mtime(session_id)` **already exists** (store.py:68, path-safe via the #8 guard) | #9 signal is free; just expose it on the facade (`KickoffViewService`) as a thin passthrough. |
| Facade exposes mtime | `KickoffViewService` (facade.py) has load/latest/load_latest but **no mtime** | Add `KickoffViewService.mtime()` → store.mtime (one canonical accessor). |
| Metrics are gauges only | `meter.create_counter` is available; the `_gauges()` dict just holds instruments | #10 counter drops into the same dict; `record_facilitation_cost` `.add()`s it beside the `.set()`. |
| A second emission point | `record_facilitation_cost` is the single call site (from `_worker` at terminal) | Reuse it — counter + gauge emitted together (Mottainai). |
| Stale check is cheap | `facilitate_status` already has the loaded transcript + status | The mtime stat is one syscall, gated on non-terminal only. |

## Approach

### #9 — stale-run staleness report
1. **`KickoffViewService.mtime(session_id)`** (facade.py) → passthrough to `KickoffPanelStore.mtime`.
2. **`facilitate_run`:** `STALE_AFTER_SECS` (const, env `STARTD8_FACILITATION_STALE_SECS`, default 600) +
   a resolver like `_max_concurrent_facilitations` (#4). In `facilitate_status`, after loading `t`:
   if **not terminal** (`not is_done`), best-effort `now - service.mtime(sid) > STALE_AFTER_SECS` → add
   `"stalled": True` to the payload. `is_terminal` stays `bool(is_done)` (FR-3). Stat failure → no flag (FR-5).
3. **Tests:** non-terminal + old mtime → `stalled True`; non-terminal + fresh → no/False; terminal (completed)
   → never stalled; env override changes the threshold; stat failure → no flag, no error.

### #10 — cumulative cost counter + documented alert
4. **`metrics.py`:** add `"facilitation_cost_total": meter.create_counter("kickoff.facilitation.cost_usd_total",
   description=…)` to `_gauges()`. In `record_facilitation_cost`, after the gauge `.set()`, `.add(cost_usd, attrs)`
   the counter (same labels). Best-effort/opt-in unchanged.
5. **Docs:** a metrics.py docstring note + a short design note with the PromQL alert
   (`increase(kickoff_facilitation_cost_usd_total{project="X"}[30d]) > CEILING`) and that provisioning is the
   operator's job (grafana skill) — distinct from the fail-closed `ensure_blocking_budget`.
6. **Test:** `record_facilitation_cost` with a fake meter → the counter `.add()` is called with cost + labels
   (mirror the existing gauge test).

### #10/#9 — plugin
7. **`types.ts::FacilitateStatusResult`** += `stalled?: boolean`. **`FacilitatePanel`** StatusView: when
   `status.stalled` (and not terminal), an info/warning "no progress in ~N min — the worker may have died;
   Check again or re-run". Keep the existing Check-again + banner. **Real verify** (npm typecheck/lint/test/build).

### Docs
8. README + roadmap (#9/#10 shipped).

## Requirement → step trace
FR-1/3/5→S2 · FR-2→S2 · FR-4→(observer; no reservation code) · FR-6→S4 · FR-7→S5 · FR-8→S5(doc) · FR-9→S2/S4 · FR-10→S7.

## Risks
- **R1 — false "stalled" on a slow-but-alive run.** Mitigated: generous 600s (a live worker writes every
  round ~1–2 min) + `is_terminal:false` + "may be stalled" framing + Check-again (never hard-stops).
- **R2 — observer can't free the leaked reservation.** Accepted (FR-4/NR-1): the reservation expires at its
  TTL; an active reap risks double-spend. Documented as the deferred option.
- **R3 — counter double-count on retries.** `record_facilitation_cost` fires once per `_worker` terminal;
  a deduped/replayed run doesn't re-emit (it returns before spending). No double-count.

*v1.0 — planning pass. Both are thin/additive; #9's signal reuses an existing `mtime` accessor, #10's
counter reuses the existing emission point. No security/write surface.*
