# Phase 2 (Run the Stakeholder Panel from the Workbook) — M4 Pilot Verdict

**Date:** 2026-07-08
**Pilot:** bounded live spend (cap=1 persona, Haiku, $1 daily-ceiling backstop) against the real
endpoint, in a throwaway temp project. Harness: `pilot/run_m4_pilot.py`.

## Result: GO for the backend loop; plugin provisioning is an operator gate

The whole run loop was exercised **end-to-end with real LLM spend** and every guardrail held live:

| Guardrail | Evidence (live pilot) |
|---|---|
| Dry-run is $0 | `dry_run:true` → estimate `$0.02` + `run_key`, **no spend** |
| `run_key` integrity (FR-11) | confirm echoed the dry-run's `run_key`; server validated it |
| Real answer | budget-owner (grounded): *"…ensuring every bill gets paid before its due date…"* |
| Partial-failure (FR-6) | cap=1 of 2 → status **`partial`**, 2nd persona correctly `deferred` |
| Idempotency (FR-11) | replay with the same `run_key` → **`deduped`**, not re-charged |
| Transcript persists | 1 file under `.startd8/stakeholder-panel/` |
| UNRATIFIED, no auto-ratify (FR-6) | answer tagged SYNTHETIC & UNRATIFIED; **kickoff inputs untouched** |
| Renders in the Workbook (FR-8) | `portal --session <id>` → the exact session's answer in the Stakeholders section |
| Fail-closed budget (FR-4) | a $1 DAILY blocking budget was required + registered before any run |

## Gap the pilot surfaced (follow-up, not a blocker)

**Actual per-run cost is recorded as `$0.0000`.** The endpoint's `execute_run` accepts a `cost_tracker`
but the server passes `None`, so `PanelAnswer.cost_usd` is never populated (the same F-1 class the CRP
flagged for the *CLI* path). Consequences + bounding:
- **Spend safety is intact** — the fail-closed **preflight** gates on the honest dry-run *estimate*, and
  the DAILY ceiling caps cumulative spend regardless of per-run accounting.
- **Audit (FR-9) is degraded** — the displayed/recorded cost is 0, not the real spend.
- **Fix:** construct a `cost_tracker` (`CostStore`-backed) in `stakeholder_run_server` / `serve` and pass
  it into `execute_run` → `StakeholderPanel(cost_tracker=…)`. Small, isolated follow-up.

## Where Phase 2 stands

- **Backend + CLI:** shipped + validated live (M0 #130, CLI/M2/M3 #132).
- **Grafana panel:** built (#133), **not provisioned** — loading the unsigned plugin needs an allow-list
  change + a restart of the shared KinD Grafana that also serves the online-boutique dashboards
  (NR-10 blast radius). That is an **operator decision**, documented in the plugin README.
- **Cancel/abort:** deferred (needs async job management; `--cap` + the daily ceiling bound spend).

## Verdict

**The "run the stakeholder panel from the Digital Project Workbook" capability is real, safe, and
validated.** The loop is fail-closed, idempotent, partial-failure-aware, and keeps results UNRATIFIED
and out of the kickoff source of record. It is **fully driveable from the CLI today**; the browser
(plugin) surface is one operator-gated provisioning step away. Recommended next: the `cost_tracker`
follow-up (honest audit), then — when the operator is ready to accept the NR-10 restart — provision the
plugin and re-run the pilot *through Grafana* for the final visual confirmation.
