# Workbook — Run the Stakeholder Panel from the UI (Phase 2) — Plan

**Version:** 1.0 (Post-planning)
**Date:** 2026-07-07
**Requirements:** `WORKBOOK_STAKEHOLDER_RUN_REQUIREMENTS.md` (v0.2)

## Planning summary

Phase 2 is **mostly wiring**: the paid-run guardrails (cap, fail-closed `budget_preflight`, `projected_
calls` dry-run, transcript persistence, UNRATIFIED labeling) already exist at the CLI/panel layer. The
net-new is (a) a thin **CLI-backed endpoint** that invokes `StakeholderPanel` behind those guardrails,
(b) a **forked owl workflow-panel** as the trigger/monitor UI, and (c) **surfacing results** in the
Phase-1 Stakeholders section. Reachability (Grafana pod → `host.docker.internal`) is confirmed. The
dominant risks are the spend-from-a-dashboard posture and the unsigned-plugin blast radius (NR-10).

## M0 — CLI-backed run endpoint (the spine)

**Goal:** `POST /stakeholders/run` (+ `GET /stakeholders/run/{id}`) that runs the panel through the
existing guardrails; never runs the LLM in Grafana.
- Reuse `serve.py` auth posture (loopback/host bind, token, CSRF/origin). Bind must be reachable from
  the KinD Grafana pod → `0.0.0.0` (accept the LAN exposure; token-gated; state only).
- Body `{question, cap, dry_run, run_key}`. Invokes `StakeholderPanel.ask_all` behind
  `budget_preflight()` + `--cap`. `dry_run=true` returns `projected_calls` + estimated cost, **no spend**.
- **Idempotency:** `run_key` dedupes double-submits within a TTL (no double charge).
- **Exit:** a dry-run returns the projection; a confirmed run persists a transcript + returns session_id.

## M1 — Plugin: fork owl workflow-panel → kickoff-stakeholders-panel

**Goal:** trigger + dry-run preview + confirm modal + status poll + render answers.
- Fork `contextcore-workflow-panel` (it already has dry-run/confirm/poll). Deltas: payload
  `{question, cap}` (not `{project_id, dry_run}` — note the mock contract drift); response = per-persona
  answers (not run-steps); render each with the **SYNTHETIC & UNRATIFIED** banner.
- Route to the M0 endpoint (optionally via `contextcore-datasource` to avoid browser CORS).
- **NR-10:** unsigned → confirm/enable the allow-list + plan the shared-Grafana restart (blast radius
  over online-boutique dashboards) BEFORE provisioning. Pin the fork commit.
- **Exit:** dry-run preview renders projected calls+cost; confirm triggers M0; answers render.

## M2 — Surface results in the Workbook

**Goal:** the Stakeholders section shows the latest run's answers.
- Extend `portal_spec._stakeholders_section` to render the latest transcript
  (`.startd8/stakeholder-panel/<id>.json`) — role → answer, UNRATIFIED-tagged. Keep display-only ($0).
- **Refresh (OQ-3):** start with **re-provision-on-complete** (simplest, no standing exposure); add
  Infinity-over-endpoint self-refresh only if the live loop is wanted.
- **Exit:** after a run, the section shows the new answers.

## M3 — Guardrail hardening + audit

- Idempotency + rate-limit finalized; per-run audit line (who/when/question/cap/estimated+actual
  cost/session_id) via transcript + cost tracking. Confirm the "missing key = clean fail, no partial
  charge" path.

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

1. **Spend-from-a-dashboard posture** — the biggest concern; dry-run + cap + fail-closed preflight +
   confirm modal + idempotency must all hold before the button is live.
2. **Unsigned plugin on shared KinD Grafana (NR-10)** — allow-list + restart affects other dashboards.
3. **`0.0.0.0` endpoint bind** — LAN exposure; bound by token + state-only + no raw secrets.
4. **Plugin fork drift** — pin the commit; document the payload/response delta from workflow-panel.
