# Workbook — Run the Stakeholder Panel from the UI (Phase 2) — Requirements

**Version:** 0.2 (Post-planning — self-reflective update)
**Date:** 2026-07-07
**Status:** Draft
**Parent:** the Digital Project Workbook (`GRAFANA_KICKOFF_PORTAL_*`; `startd8 kickoff portal`)
**Depends on:** Phase 1 (Workbook Stakeholders section — shipped, `b84b1f25`)
**Pilot:** `household-o11y`

---

## 0. Planning Insights (Self-Reflective Update)

> A grounded planning pass over the run path (`cli_panel.py:panel_ask_all`, `stakeholder_panel/{panel,
> budget,facilitation,transcript}.py`, `serve.py`, the owl plugins) corrected the naive v0.1:

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| Phase 2 must build cost/cap/confirm guardrails | They **already exist at the CLI/panel layer**: `--cap` (FR-17), fail-closed `budget_preflight()` (adapts `costs.BudgetManager`, aborts before spend), `facilitation.projected_calls()` (the dry-run/cost basis), and the `_render_answer` SYNTHETIC/UNRATIFIED banner | Phase 2 **exposes/threads** these through the endpoint — it does **not** re-implement them. Routing through the CLI *inherits* them. |
| chat-panel is the write plugin (from Phase-2/M4 earlier) | "Run the panel" is **trigger + dry-run + monitor**, which is exactly the owl **workflow-panel** (it has a dry-run preview, status polling, and a confirm modal) | FR-7: base is **workflow-panel**, not chat-panel. |
| Need a reachable endpoint but unsure it works from KinD Grafana | **Confirmed (2026-07-07):** the Grafana pod reaches a host endpoint via `host.docker.internal` (empirically). | FR-2 reachability is de-risked; the residual cost is the `0.0.0.0`-bind exposure. |
| Results need a new store | Runs **already persist** to `.startd8/stakeholder-panel/<session>.json` (auditable transcripts) | FR-5 reuses the transcript store; the Phase-1 section renders the latest. |
| Results could inform kickoff inputs | Answers are **synthetic + UNRATIFIED** by design | FR-6: results **never** mutate the kickoff source of record; candidate-only. |

**Resolved:** OQ-plugin → workflow-panel; OQ-reachability → host.docker.internal. **Still open:** endpoint
lifecycle/auth (OQ-1), idempotency key (OQ-2), live-refresh mechanism (OQ-3), results-render location (OQ-4).

### 0.1 Lessons-Learned Hardening
- **Single-source ownership:** reuse `budget_preflight`/`projected_calls`/transcript/`_render_answer` —
  cite, do not restate the cost/labeling logic.
- **Phantom-reference audit:** every symbol named here is grounded (see Reference Audit). The owl
  workflow-panel's `/workflow/run` vs mock `/workflow/dry-run` **contract drift** is noted (we define our
  own endpoint contract, FR-2).
- **NR-10 carry-over:** the unsigned plugin on the shared KinD Grafana (allow-list + restart, blast
  radius over the online-boutique dashboards) applies here verbatim.

---

## 1. Problem Statement

The Phase-1 Workbook **displays** the stakeholder roster read-only. Phase 2 makes the Workbook
**dynamic** in the way that matters most (the "Digital" in Digital Project Workbook): let a user **run
the stakeholder panel** (`ask` / `ask-all`) from within the Grafana Workbook and see the results — the
M4-class action loop, specialized to the *paid* stakeholder panel. This is a deliberate posture shift
(a spend-triggering, content-producing action inside a dashboard), so the guardrails are the point.

## 2. Requirements

- **FR-1 — Trigger from the Workbook.** An action-panel in the Workbook triggers a stakeholder-panel
  run (`ask-all` with a question + optional `--cap`) and shows progress + results.
- **FR-2 — Route THROUGH the CLI (never run the LLM in Grafana).** The action POSTs to a thin
  CLI-backed endpoint that invokes the *same* `StakeholderPanel` code path. Preserves CLI-sole-writer.
  Auth reuses `serve.py`'s posture (loopback/host bind, token, CSRF/origin). Reachable from the KinD
  Grafana pod via `host.docker.internal` (confirmed). We define the endpoint contract
  (`POST /stakeholders/run`, `GET /stakeholders/run/{id}`) — not the owl mock's `/workflow/*`.
- **FR-3 — Dry-run BEFORE spend.** The panel first shows a **preview**: personas × question, projected
  calls (`projected_calls`), and estimated cost, with the `--cap` applied. No spend until an explicit
  **confirm** (workflow-panel confirm modal). 
- **FR-4 — Fail-closed cost guardrails.** The endpoint enforces `budget_preflight()` (aborts before
  spend if over budget) + `--cap`; **idempotency** (a run key dedupes double-clicks — no double charge)
  + rate-limit. A missing/invalid API key fails cleanly (not a partial charge).
- **FR-5 — Results via the existing transcript store.** Runs persist to
  `.startd8/stakeholder-panel/<session>.json` (unchanged); the Phase-1 Stakeholders section renders the
  **latest session's** answers.
- **FR-6 — Results are UNRATIFIED candidate input.** They are tagged **SYNTHETIC & UNRATIFIED** and
  **never** mutate the kickoff inputs/ledger (no auto-ratify). Consistent with existing panel semantics.
- **FR-7 — Reuse the owl workflow-panel.** Fork/configure `contextcore-workflow-panel` (trigger +
  dry-run + status poll + confirm modal), not chat-panel. Unsigned → **NR-10** blast radius applies.
- **FR-8 — Reflect the run in the Workbook.** After completion, the Stakeholders section shows the new
  results (live via Infinity-over-endpoint, or re-provision-on-complete — OQ-3).
- **FR-9 — Audit every run.** Log who/when/question/cap/estimated+actual cost/session_id (reuse
  transcript + cost tracking); surface a per-run audit line.
- **FR-10 — Pilot on household.** Requires a roster (`kickoff instantiate`) first; then run from the UI.

## 3. Non-Requirements

- **NR-1 — No LLM in Grafana.** The model only ever runs via the CLI endpoint.
- **NR-2 — No auto-ratify.** Results never write the kickoff source of record.
- **NR-3 — No unbounded spend.** Dry-run + cap + fail-closed preflight are mandatory, not optional.
- **NR-4 — Not a general workflow runner.** Scoped to the stakeholder panel (ask/ask-all).
- **NR-5 — Not Phase 1.** The read-only display already shipped.
- **NR-6 — Local pilot only.** No cloud Grafana / multi-tenant exposure.

## 4. Open Questions

- **OQ-1 — Endpoint lifecycle + auth.** Standing daemon (`kickoff portal serve`?) vs on-demand; how the
  token reaches the panel (panel option vs `contextcore-datasource` proxy).
- **OQ-2 — Idempotency key.** What dedupes a double-click into one charged run (client nonce? question+
  cap+roster hash within a TTL?).
- **OQ-3 — Live refresh.** Infinity-over-endpoint (self-refresh; needs the `0.0.0.0` bind) vs
  re-provision-on-complete (simpler; no standing exposure).
- **OQ-4 — Results render location.** Extend the Phase-1 Stakeholders section vs a dedicated results
  panel with per-persona rows.
- **OQ-5 — Plugin fork delta.** How much of workflow-panel changes (payload `{question, cap}` vs
  `{project_id, dry_run}`; response shape = per-persona answers, not run-steps).

## Reference Audit

| Symbol / artifact | Exists? | Path |
|---|---|---|
| `panel_ask_all` (`--cap`) | ✅ | `cli_panel.py:207` |
| `StakeholderPanel.ask/ask_all` | ✅ | `stakeholder_panel/panel.py` |
| `budget_preflight` (fail-closed) | ✅ | `stakeholder_panel/budget.py:28` |
| `projected_calls` (dry-run basis) | ✅ | `stakeholder_panel/facilitation.py:507` |
| transcript store `.startd8/stakeholder-panel/<id>.json` | ✅ | `stakeholder_panel/transcript.py` |
| SYNTHETIC/UNRATIFIED banner | ✅ | `cli_panel.py:_render_answer` |
| serve auth posture | ✅ | `kickoff_experience/serve.py` |
| owl workflow-panel (trigger+monitor+dry-run) | ✅ | `contextcore-owl/plugins/contextcore-workflow-panel/` |
| `host.docker.internal` reachability from Grafana pod | ✅ verified 2026-07-07 | KinD `o11y-dev` |
| CLI-backed `/stakeholders/run` endpoint | ❌ to-build | Phase 2 |

---

*v0.2 — Post-planning. Key correction: the cost/cap/dry-run/label guardrails already exist at the CLI
layer; Phase 2 exposes them via a CLI-routed endpoint + the owl workflow-panel. Ready for lessons pass
+ CRP.*
