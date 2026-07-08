# Digital Project Workbook — Panel Capabilities: Next Steps

**Date:** 2026-07-08
**Owner docs:** `WORKBOOK_STAKEHOLDER_RUN_*` (Phase 2, run), `WORKBOOK_PANEL_PIPELINE_*` (Increment 3,
pipeline). This file is the running to-do; the FR/AC detail lives in those specs.

---

## Where we are (shipped)

| Capability | State |
|---|---|
| Digital Project Workbook (read) — kickoff state, per-domain, roster, latest run | ✅ shipped |
| Phase 2 — run the stakeholder panel from Grafana (endpoint + CLI serve + M1 plugin) | ✅ shipped; concurrency-hardened (H1/M1/M3); cost_tracker + cancel wired |
| Increment 3 M-display — **Panel Processing Pipeline** funnel (staged → inbox → dispositions → apply-status) | ✅ shipped (PR #144), $0 read-only |
| Increment 3 spec (drive + apply) — **v0.4**, CRP-hardened, apply gate rebuilt | ✅ merged (PR #145) |

---

## Remaining — Increment 3 drive/apply (build against reqs **v0.4**)

### 1. M-drive-$0 — safe endpoint routes (NEXT)
Extend `stakeholder_run_server.py` with `$0` routes, each threading **through the CLI code paths**
(never reimplement); reuse the existing bearer-token auth + confinement.
- [ ] **triage** (FR-R2) → `build_triage(transcript)` → `TriageReport.to_dict()`. Needs a *facilitated
      synthesis* transcript (ask-all runs don't have one) — degrade cleanly when absent.
- [ ] **disposition** (FR-R4) → `ProposalStore.update_disposition(domain, value_path, "accepted")` —
      ⚠ **3 positional args**, pin the literal **`"accepted"`/`"rejected"`** (serialize filters `== "accepted"`;
      the docstring's "approved" is a trap), and **ensure the rec is staged first** (else it no-ops).
- [ ] **serialize** (FR-R5) → `serialize_accepted_to_vipp(accepted_only=True)`. Non-allow-listed paths
      are **rejected, not dropped**.
- [ ] **negotiate** (FR-R6) → `run_vipp_negotiate` → dispositions. Narrative/panel spend uses its **own
      `max_cost_usd`** ceiling (NOT the run preflight) — set + enforce it explicitly.
- [ ] Tests: each route round-trips a store; disposition/serialize inherit `0600` + symlink-reject.

### 2. M-drive-paid — extract→stage
- [ ] **extract** (FR-R3) → `extract_field_mappings` (paid) → `stage_recommendations`. Fail-closed
      budget, but a **new preflight/estimate keyed on `(session_id + synthesis-checksum)`** — NOT
      `run_key` (which binds question/cap/roster).
- [ ] Dry-run estimate → confirm; dedupe on resubmit of the same synthesis.

### 3. M-apply — the gate (rebuilt, token-gated; most-guarded, LAST)
Per FR-R7 v0.4. **Apply is token-gated, not human-proof** (a real HTTP human gate is impossible — say so
in the UI).
- [ ] **preview** (`POST …/apply/preview`) — **PURE reconstruct** the would-apply set from inbox +
      dispositions; **NEVER call `apply_dispositions`** (it mutates the cursor / can shred the inbox).
      **AC: `vipp-cursor.json` + inbox byte-identical after preview.** Return a **stateless HMAC challenge**
      over `{envelope_seq, content-hash, expiry}` (per-server key; single-use).
- [ ] **ratify** (`POST …/apply/ratify`) — `{proposal_ids, challenge}`; verify HMAC; **refuse if live
      inbox seq ≠ the challenge's** (concurrent negotiate → stale → re-preview); then
      `apply_dispositions(confirm=…)` True only for the listed ids. **`force` never exposed**;
      **`strict=True` mandatory**; wrap with an explicit `resolve_confined_root` (apply doesn't confine itself).
- [ ] Plugin: **two-screen** flow (preview → paste challenge → ratify) + honest banner "token-gated —
      anyone with the endpoint token can apply."
- [ ] Tests: preview byte-identical; ratify writes only listed proposals; stale/forged challenge writes
      nothing; concurrent negotiate forces re-preview.

### 4. M-pilot — household end-to-end + verdict
- [ ] Real run → triage → stage → accept → serialize → negotiate → apply-**preview** on household;
      apply's **actual write only on a throwaway project**. Written verdict.

---

## Cross-cutting follow-ups (independent of the milestones above)

- [ ] **Plugin cancel button** — the Phase-2 server `POST …/run/{run_key}/cancel` is built + tested, but
      the `kickoff-stakeholders-panel` UI never calls it. Add a Cancel control.
- [ ] **Provision the plugin(s)** into the shared KinD Grafana — unsigned allow-list + a restart that
      touches the online-boutique dashboards (**NR-10 blast radius; operator decision**). Steps in
      `grafana-plugins/kickoff-stakeholders-panel/README.md`. Re-run the pilots *through* Grafana after.
- [ ] **Datasource `/stakeholders/*` proxy route + token** — set up the `contextcore-datasource` (or a
      dedicated one) that adds the bearer token server-side, so the plugin never holds it (S-3 / FR-2).
- [ ] **OQ-2** — decide: pipeline funnel as a **sibling dashboard** `cc-portal-kickoff-pipeline-{project}`
      vs a section in the main Workbook (the funnel is large).
- [ ] **Reverse consult-panel pass** (`panel_advisories`) is only on `run_vipp_negotiate(panel=…)`, not
      the `vipp negotiate` CLI — expose it if the Workbook should drive it (NR-5, currently display-only).
- [ ] **Live metrics (deferred Workbook FR-2/5d)** — the completeness gauge/burndown are still baked
      `vector(N)` literals; a real OTel `Meter`→Mimir producer would make them live (separate track).

---

## Sequencing + risk

Do them in order: **M-drive-$0 → M-drive-paid → M-apply → M-pilot.** M-apply is last and isolated — it
writes the project source of record and is **token-gated**; keep real writes to throwaway projects until
the pilot. The concurrency/idempotency hardening (H1/M1/M3) from the Phase-2 code review already covers
the shared endpoint; the new routes inherit it.
