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

### 1. M-drive-$0 — safe endpoint routes ✅ (built, branch `feat/workbook-pipeline-drive-m0`)
Extended `stakeholder_run_server.py` with `$0` routes, each threading **through the CLI code paths**
(never reimplement); reuse the existing bearer-token auth + confinement. 19 route tests + 17 existing green.
- [x] **triage** (FR-R2) → `build_triage(transcript)` → `TriageReport.to_dict()`. `POST …/triage`
      (`{session_id?}`, default latest); degrades cleanly when no synthesis (`synthesis_present:false`,
      empty candidates); unknown/absent session → 404.
- [x] **disposition** (FR-R4) → `ProposalStore.update_disposition(domain, value_path, "accepted")`.
      `POST …/disposition`; pins the literals (only `"accepted"`/`"rejected"` accepted, else 400); the
      no-op-when-unstaged is surfaced as **404, not a false success**.
- [x] **serialize** (FR-R5) → `serialize_accepted_to_vipp(accepted_only=True)`. `POST …/serialize`;
      non-allow-listed paths **rejected, not dropped**; no-staged → 404, none-accepted → 409.
- [x] **negotiate** (FR-R6) → `run_vipp_negotiate` → dispositions. `POST …/negotiate`; `$0` by default;
      an opt-in `narrative:true` **requires** an explicit `max_cost_usd` (400 otherwise) and forwards it
      to `run_vipp_negotiate`'s own ceiling (NOT the run preflight); missing inbox → 409.
- [x] Tests: each route round-trips a store; disposition write verified `0600`; serialize inherits
      symlink-reject/confinement via the CLI path (`SafeWriteError` → 403).

### 2. M-drive-paid — extract→stage ✅ (built, branch `feat/workbook-pipeline-drive-paid`)
`POST /stakeholders/extract` — the one paid pipeline step. 8 route tests green.
- [x] **extract** (FR-R3) → `extract_field_mappings` (paid, via a route-local **tracked mapper** that
      records actual token spend to the `CostTracker` — FR-9 parity) → `stage_recommendations` ($0).
      Preflight/estimate keyed on **`(session_id + synthesis-checksum)`** via the reused `IdempotencyStore`
      — NOT `run_key`. Token estimate via `PricingService.estimate_cost`; fail-closed on the blocking
      budget; pre-call `max_cost_usd` gate refuses (412) before spending.
- [x] Dry-run estimate (`{dry_run:true}` → `{estimated_cost, synthesis_checksum, extract_key}`, $0) →
      confirm (`{confirm_checksum}`; stale checksum → 409); dedupe on resubmit (`status:"deduped"`, model
      runs once). Staged output is **SYNTHETIC & UNRATIFIED**; over-ceiling actuals are surfaced
      (`ceiling_exceeded`), not discarded (Mottainai — the call already charged).
- ⚠ **Found latent bug (not fixed here):** `extract_llm.py`'s *default* mapper imports
      `from startd8.agents import resolve_agent_spec` — that name is **not** exported there (canonical is
      `startd8.utils.agent_resolution`), so the CLI's real paid `panel propose --run` path would
      `ImportError`. Our route injects a working mapper and sidesteps it; the CLI default needs a one-line
      fix (separate PR).

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

- [x] **Plugin cancel button** ✅ — `kickoff-stakeholders-panel` now shows a destructive **Cancel run**
      control while a run is in flight; it POSTs `…/run/{run_key}/cancel` for the previewed `run_key`
      (via the datasource proxy, no token client-side). The awaiting run resolves `status:"cancelled"`
      with partial answers, shown honestly. 2 RTL tests (`StakeholdersPanel.test.tsx`).
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

## Access Control & Provisioning Security (own track)

**Spec:** `WORKBOOK_ACCESS_CONTROL_{REQUIREMENTS.md v0.3, PLAN.md v1.0}`. Fills the gap that the **read
Workbook has no authz** — it bakes real business targets/budgets/roster into panels and provisions them
to Grafana's **General folder** (visible to every org Viewer) on a **shared** instance. Planning found
`GrafanaClient` has **no folder or permission support** today — folder-ACL is the load-bearing to-build
control (not content redaction; `tracking_redaction` is secrets-only).

- [ ] ⚠ **IMMEDIATE: the household Workbook is currently in the General folder** (from the earlier
      `--provision`) — so its targets/budgets are visible to any Grafana Viewer on the shared `o11y-dev`.
      **Migrate it to the restricted folder once M1 lands** (or manually move/delete it sooner if the
      instance has other users).
- [ ] **CRP the access-control spec** (security/authz — an external review is warranted; offered).
- [ ] **M1 — folder + ACL (highest value):** add `create_folder` + `folderUid` on `upsert_dashboard` +
      `set_folder_permissions` to `grafana_client.py`; portal `--folder-uid` (default `cc-kickoff-{project}`)
      + `--viewers`; **fail-closed** — refuse to provision if ACLs can't be applied (`--allow-no-acl` to override).
- [ ] **M2 — content policy:** run panel free-text through `tracking_redaction` (secrets/paths out);
      keep business values (folder-protected, not scrubbed).
- [ ] **M3 — token + viewing boundary:** `--provision` preflight that **refuses/warns if anonymous
      access is enabled**; docs for a **folder-scoped least-privilege SA** + rotation; never embed the
      token in generated JSON/logs.
- [ ] **M4 — pilot:** migrate household → restricted folder; verify a **non-ACL Grafana user cannot see it**.

**Suggested order on this front:** CRP → migrate household out of General (or delete it) → build M1
(folder+ACL, fail-closed) → M2/M3 hardening → M4 verify. M1 is the one that actually closes the exposure;
everything else is defense-in-depth around it.

---

## Sequencing + risk

Do them in order: **M-drive-$0 → M-drive-paid → M-apply → M-pilot.** M-apply is last and isolated — it
writes the project source of record and is **token-gated**; keep real writes to throwaway projects until
the pilot. The concurrency/idempotency hardening (H1/M1/M3) from the Phase-2 code review already covers
the shared endpoint; the new routes inherit it.
