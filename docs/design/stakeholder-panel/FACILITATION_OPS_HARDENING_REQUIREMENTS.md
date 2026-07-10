# Facilitation Ops Hardening (#9 + #10) — Requirements

**Version:** 0.3.1 (Post lessons + design-principle hardening — ready for CRP)
**Date:** 2026-07-10
**Status:** Draft

---

## 0. Planning Insights (Self-Reflective Update)

> Planning mostly **confirmed** the draft (two thin, additive, observer-only changes). Key findings:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| Need a new mtime accessor for #9 | `KickoffPanelStore.mtime()` **already exists** (path-safe via the #8 guard) | Just expose it on the facade (`KickoffViewService.mtime`) — the signal is free. |
| Metrics are gauge-only | `meter.create_counter` is available; `_gauges()` holds instruments | #10 counter drops in beside the gauge. |
| #10 needs a new emission point | `record_facilitation_cost` is the single call site (`_worker` terminal) | Reuse it — counter `.add()` beside the gauge `.set()` (Mottainai). |

**Resolved open questions:** OQ-1 → **file mtime**; OQ-2 → **600s, env-overridable**; OQ-3 →
**observer-only** (active reaper = deferred, would risk double-spend); OQ-4 → **monotonic Counter**;
OQ-5 → **emit + document** (no provisioning). *(OQ-3 observer-vs-reaper is the one sponsor confirm — §4.)*

### 0.1 Lessons-Learned Hardening (v0.3)

- **[Phantom-reference audit]** — verified: `KickoffPanelStore.mtime`, `KickoffViewService`,
  `record_facilitation_cost`, `_gauges`, `meter.create_counter`, `is_done`, `facilitate_status` all exist.
  New: `KickoffViewService.mtime` (passthrough), `STALE_AFTER_SECS`, `facilitation_cost_total` counter, a
  `stalled` field.
- **[Single-source]** — staleness reuses the one `mtime` accessor; the counter reuses the one emission
  point — no restated logic.

### 0.2 Design-Principle Hardening (v0.3.1)

- **[Mottainai]** — reuse the existing `mtime` accessor + the existing `record_facilitation_cost` emission
  point (no second stat path, no second emit site).
- **[Hitsuzen]** — staleness is derived deterministically from the file mtime (no LLM, no heuristic model).
- **[Genchi Genbutsu]** — binds to the **real** transcript file mtime + a real OTel Counter, not a proxy.
- **[Accidental-Complexity]** — one `stalled` flag + one counter; no reaper machinery, no new budget layer
  (the fail-closed gate already exists — FR-8 keeps them distinct).
- **[Context-Correctness]** — `stalled` is best-effort: absent on any stat failure (not a false `false`);
  the poll never errors because of it.

---

## 1. Problem Statement

Two operational-reliability gaps in the facilitation path, done together (shared surface):

- **#9 — stale runs read as eternal "in_progress".** A hard server restart kills the worker thread but
  leaves the reservation `started` (until TTL) and the transcript non-terminal. A poller sees "in_progress"
  forever for a run that actually died.
- **#10 — no cumulative facilitation-cost signal for alerting.** #1 shipped a `kickoff.facilitation.cost_usd`
  **gauge** (latest cost). There's no **cumulative** counter an operator can alert on when a project
  crosses a monthly ceiling.

| Component | Current State | Gap |
|-----------|--------------|-----|
| `facilitate_status` | Non-terminal run → `status:"in_progress"` forever | No "stalled / no progress" signal (#9) |
| `metrics.py` | `kickoff.facilitation.cost_usd` **gauge** (latest) | No cumulative **counter** for spend alerts (#10) |
| Cost alerting | Fail-closed pre-spend budget only (`ensure_blocking_budget`) | No *after-the-fact* monthly-spend alert (#10) |

## 2. Requirements

### #9 — stale-run staleness report (observer)
- **FR-1 — Stalled flag on the poll.** `facilitate_status` adds `stalled: true` when a **non-terminal**
  run's transcript hasn't advanced (file mtime) in more than `STALE_AFTER_SECS`. Terminal runs
  (completed/cancelled/error/halted) never stall.
- **FR-2 — Configurable, generous threshold.** `STALE_AFTER_SECS` default 600s (10 min — a live worker
  persists the transcript every round, ~1–2 min; 10 min of no writes is very likely dead), env-overridable
  (`STARTD8_FACILITATION_STALE_SECS`, like #4/#5).
- **FR-3 — Honest, non-terminal.** `stalled` is a heuristic ("no progress in N min — the worker may have
  died; retry"), NOT a certainty. `is_terminal` stays `false` (the run *might* be slow); the client shows a
  warning + the existing **Check again**, it does not hard-stop.
- **FR-4 — Observer only.** #9 does **not** touch the IdempotencyStore reservation (no active reap) —
  releasing a slow-but-alive run risks a double-spend on retry. (Active reaper = a rejected/deferred option.)
- **FR-5 — Best-effort.** A mtime/stat failure → no `stalled` flag; the poll never errors because of #9.

### #10 — cumulative facilitation-cost counter + documented alert
- **FR-6 — Cumulative counter.** Add a monotonic Counter `kickoff.facilitation.cost_usd_total` (labels
  project/posture/tier, same as the gauge), incremented by the run cost at completion **at the existing
  emission point** (`record_facilitation_cost`, called from `_worker`) — no second emission site.
- **FR-7 — Documented alert, not provisioned.** Ship the PromQL alert expression (e.g.
  `increase(kickoff_facilitation_cost_usd_total{project="X"}[30d]) > CEILING`) + how to set a per-project
  ceiling. Provisioning the actual Grafana alert is the operator's / the grafana-skill's job (per CLAUDE.md).
- **FR-8 — Distinct from the fail-closed budget.** #10 is *observability* (after-the-fact alert), NOT the
  pre-spend gate (`ensure_blocking_budget` already fail-closes) — keep them separate.

### Cross-cutting
- **FR-9 — Additive + best-effort.** New `stalled` field + new counter; existing poll fields, the gauge,
  and all existing tests unchanged. Metrics stay opt-in silent-no-op (no collector → nothing).
- **FR-10 — Plugin surfaces stalled.** `FacilitatePanel` shows a "may be stalled" warning when
  `status.stalled`, alongside the existing Check-again.

## 3. Non-Requirements

- **NR-1 — No active reaper** (no reservation release) — observer-only (FR-4).
- **NR-2 — No Grafana alert provisioning** — documented expression only (FR-7).
- **NR-3 — No new fail-closed budget** — #10 is observability, not a gate (FR-8).
- **NR-4 — No change to existing poll fields / the gauge / TTL.**

## 4. Open Questions

- **OQ-3 — Observer vs active reaper (the one sponsor lever).** Draft = **observer-only** (report
  `stalled`, don't touch the reservation) — an active reap (releasing the leaked reservation so a retry
  re-spawns) risks a double-spend if the run was slow-but-alive, and would warrant CRP. Confirm observer.

*(OQ-1/2/4/5 resolved in §0: file mtime; 600s env-overridable; monotonic Counter; emit+document.)*

---

*v0.1 — draft.*
*v0.2 — post-planning: both thin/additive; the mtime accessor + emission point already exist; 4 OQs resolved.*
*v0.3 — lessons hardening: phantom audit clean; single-source accessor + emit point.*
*v0.3.1 — design-principle hardening: Mottainai/Hitsuzen/Genchi-Genbutsu/Accidental-Complexity/
Context-Correctness. One OQ (observer vs reaper) for the sponsor. Ready for CRP.*
