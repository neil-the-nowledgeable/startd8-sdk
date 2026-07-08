# Workbook — Run the Stakeholder Panel from the UI (Phase 2) — Requirements

**Version:** 0.3 (Post-CRP R1 — PREMISE CORRECTED; 8 findings triaged, all accepted)
**Date:** 2026-07-07
**Status:** Draft
**Parent:** the Digital Project Workbook (`GRAFANA_KICKOFF_PORTAL_*`; `startd8 kickoff portal`)
**Depends on:** Phase 1 (Workbook Stakeholders section — shipped, `b84b1f25`)
**Pilot:** `household-o11y`

---

## 0. Planning Insights (Self-Reflective Update)

> A grounded planning pass over the run path (`cli_panel.py:panel_ask_all`, `stakeholder_panel/{panel,
> budget,facilitation,transcript}.py`, `serve.py`, the owl plugins) corrected the naive v0.1:

> ⚠️ **The v0.2 premise below (row 1) was FALSE — corrected by CRP R1 (see §0.2).** The guardrails are
> NOT inherited via the CLI. Read §0.2 first.

| v0.1 assumption | Planning discovery | Impact |
|-----------------|--------------------|--------|
| ~~Phase 2 just exposes guardrails that already exist~~ **(FALSE — CRP F-1/F-2/F-3)** | `cli_panel.py:panel_ask_all` builds `StakeholderPanel` with **no `budget_preflight` and no `cost_tracker`** → preflight is a **no-op** and cost is always `0.0` on that path; `BudgetManager` is **fail-OPEN** with no budget configured; `serve.py` is loopback-only with **no CSRF/Origin**; `projected_calls` is the wrong (facilitator) cost basis. | Phase 2 must **BUILD** a fail-closed budget gate + cost tracker + real auth + an honest cost estimator — **net-new, security-critical**, not wiring. See §0.2. |
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

### 0.2 CRP Round-1 Triage (v0.2 → v0.3) — the premise was wrong

> Independent CRP (Appendix A) raised F-1…F-7 + F-2b (requirements) and S-1…S-7 (plan), each verified
> against real code. **All 15 ACCEPTED (0 rejected).** The self-reflective loop's central claim —
> "guardrails already exist and are inherited via the CLI" — **did not survive contact with the source.**
> Phase 2 is a **fail-closed budget gate + real auth + honest cost estimator + idempotency/crash
> consistency + a real plugin render path** — net-new and security-critical.

| # | Sev | Finding | Change applied |
|---|-----|---------|----------------|
| F-1 | BLOCKER | `panel_ask_all` wires **no preflight, no cost_tracker** → preflight is a no-op, cost always 0 | FR-4 rewritten: the endpoint **constructs** `BudgetManager`+`budget_preflight`+`cost_tracker` and passes them in. §0 row 1 corrected. |
| F-2 | BLOCKER | `serve.py` = loopback-only, **no CSRF/Origin**; `0.0.0.0` deletes the only control; answers cross the LAN | FR-2 rewritten: mandate constant-time `APIKeyMiddleware` + Origin allow-list + CSRF + replay nonce (or docker-bridge-IP bind + TLS), not "reuse serve.py". |
| F-2b | SHOULD | `BudgetManager.check_budget` returns `[]` (never raises) with no budget → **fail-OPEN** | FR-4: endpoint must **register a blocking budget** (`block_on_exceed`, scoped `stakeholder-panel`) and **refuse to run if none configured**. |
| F-3 | BLOCKER | `projected_calls` = facilitator basis (×3–4), not `ask_all` fan-out; it's a call count, not dollars | FR-3: dry-run basis = `min(cap, len(roster)) × per_question_estimate`; name the honest (estimate-only) dollar source. |
| F-4 | SHOULD→FR | No `run_key`; confirm re-POSTs fresh, ignoring the dry-run | New **FR-11**: dry-run mints an opaque `run_key` binding `{question,cap,roster_version}`; confirm echoes it; server dedupes (persisted TTL) + validates the hash before spend. |
| F-5 | SHOULD | "latest by mtime" races under concurrent runs | FR-8: render the **specific `session_id`** returned by the run, not latest-mtime. |
| F-6 | SHOULD | `ask_all` spend is **per-persona, not atomic**; mid-fan-out failure drops paid answers | FR-4: define partial-failure semantics — return persisted partials + per-persona status; distinguish no-key (0 spend) from mid-run (partial spend). |
| F-7 | CONSIDER | No cancel/kill, no cumulative USD ceiling | New **FR-12**: cancel/abort path + per-session/daily USD ceiling (reuse `FacilitationConfig.budget_usd` cumulative-abort). |
| S-1 | BLOCKER | (plan M0) build the budget gate, don't inherit | M0 rewritten (see plan). |
| S-2 | BLOCKER | (plan M0) add real auth deliverables on the `0.0.0.0` listener | M0 rewritten. |
| S-3 | BLOCKER | (plan M1) token delivery is unsolved + gates the endpoint; panel-option token is world-readable | M1: token via `contextcore-datasource` **server-side** proxy = a hard **exit gate**. |
| S-4 | SHOULD | (plan) run_key minted by dry-run, echoed+validated by confirm | M0/M1 fork deltas. |
| S-5 | SHOULD | (plan) crash-after-spend → double charge; commit spend marker **before** the provider call | M0/M3. |
| S-6 | SHOULD | (plan M1) the fork is a **new render path + new status schema**, not a payload tweak | M1 re-scoped; `GET /stakeholders/run/{id}` schema added to M0. |
| S-7 | CONSIDER | (plan) endpoint lifecycle (on-demand vs standing daemon) decided **before** M0; add cancel + daily ceiling | M0 lifecycle decision + M3 additions. |

**Net:** Phase 2 grows from "wiring" to a security-critical build. This materially affects the go/no-go —
the honest alternative (**keep the panel CLI-only; Workbook stays read-only via Phase 1.5**) is now a
first-class option, not a fallback.

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
- **FR-2 — Route THROUGH the CLI + auth SCOPED to the deployment posture (CRP F-2, local-posture
  split).** The action POSTs to a thin CLI-backed endpoint that invokes the `StakeholderPanel` code path
  (preserves CLI-sole-writer). Reachability from the KinD Grafana pod (`host.docker.internal`) requires
  a **non-loopback bind**, so the endpoint is not loopback-protected. The threat model splits by posture:
  - **Load-bearing regardless of posture (always on):** a **constant-time bearer token** (a spend
    endpoint on any non-loopback bind must not be anonymous) **+ the fail-closed budget ceiling (FR-4)**
    — the budget bounds the *harm* of any triggering; the token bounds *who* can trigger. The endpoint
    **refuses to start without a token**. `run_key` idempotency (FR-11) neutralizes replay's double-charge.
  - **Local-trusted DEFAULT (household posture):** token + budget ceiling + idempotency is sufficient.
    CSRF is **not applicable** (auth is a header token, not a cookie, and the write originates
    **server-side** from the `contextcore-datasource` proxy — no ambient credential to forge); replay's
    harm is already covered by idempotency. So CSRF/Origin/replay-nonce are **deferred** here.
  - **`--strict-auth` OPT-IN (untrusted/shared network):** additionally enforce an **Origin allow-list**
    + a **replay nonce**, and prefer binding the **docker-bridge IP** (not broad `0.0.0.0`) + TLS/tunnel.
  Contract: `POST /stakeholders/run`, `GET /stakeholders/run/{session_id}` — not the owl mock's
  `/workflow/*`. (Rationale recorded so the CRP's controls are **scoped**, not silently dropped.)
- **FR-3 — Dry-run BEFORE spend, with an HONEST cost basis (CRP F-3).** The preview shows personas ×
  question with `--cap` applied and an **estimated** cost = `min(cap, len(roster)) × per_question_
  estimate`. **Do NOT use `projected_calls`** (it's the multi-round *facilitator* basis, ×3–4 too high,
  and a call count not dollars). Name the per-question dollar estimate's source; label it an estimate
  (real cost is only known post-call). No spend until explicit **confirm**.
- **FR-4 — Fail-CLOSED cost guardrails the endpoint BUILDS (CRP F-1, F-2b, F-6).** The endpoint
  **constructs** `BudgetManager` + `budget_preflight(model, cost_per_question)` + a `cost_tracker` and
  passes all three into `StakeholderPanel` — the CLI path wires **none** of these, so nothing is
  inherited. It MUST **register a blocking budget** (`block_on_exceed=True`, scoped
  `project="stakeholder-panel"`) and **refuse to run if none is configured** (`check_budget` returns
  `[]` = fail-OPEN otherwise). **Partial-failure semantics:** `ask_all` spend is **per-persona, not
  atomic** — on a mid-fan-out failure, return the **persisted partial answers + per-persona status**;
  distinguish "no/invalid key → 0 spend" from "mid-run failure → partial spend". Plus `--cap` +
  rate-limit.
- **FR-5 — Results via the existing transcript store.** Runs persist to
  `.startd8/stakeholder-panel/<session>.json` (unchanged); the Workbook renders the **specific
  triggered session** (see FR-8), not "latest".
- **FR-6 — Results are UNRATIFIED candidate input.** They are tagged **SYNTHETIC & UNRATIFIED** and
  **never** mutate the kickoff inputs/ledger (no auto-ratify). Consistent with existing panel semantics.
- **FR-7 — Reuse the owl workflow-panel.** Fork/configure `contextcore-workflow-panel` (trigger +
  dry-run + status poll + confirm modal), not chat-panel. Unsigned → **NR-10** blast radius applies.
- **FR-8 — Reflect the SPECIFIC run in the Workbook (CRP F-5).** After completion, the Workbook shows
  the answers of the **exact `session_id` returned by `POST /stakeholders/run`** — NOT "latest by mtime"
  (which races when two runs overlap; a slow run finishing later would clobber the display). State how
  concurrent runs are disambiguated.
- **FR-9 — Audit every run.** Log who/when/question/cap/estimated+actual cost/session_id (via transcript
  + the `cost_tracker` FR-4 builds); surface a per-run audit line.
- **FR-10 — Pilot on household.** Requires a roster (`kickoff instantiate`) first; then run from the UI.
- **FR-11 — Dry-run→confirm integrity + idempotency (CRP F-4, promoted from OQ-2).** The dry-run
  response mints an opaque **`run_key`** binding `{question, cap, roster_version}`. The confirm MUST
  echo it; the server **dedupes on it** (persisted, TTL) and **validates the params hash matches** the
  preview before spending — so the confirmed run is provably the previewed one, and a double-click
  charges once. The base owl confirm re-POSTs fresh (ignores the dry-run) — this is a fork requirement.
- **FR-12 — Cancel + cumulative ceiling (CRP F-7).** A **cancel/abort** path (the poll exists; add
  abort), and a **per-session/daily USD ceiling** that aborts before the next run's calls (reuse
  `FacilitationConfig.budget_usd`'s cumulative-abort pattern). `--cap` bounds *personas in one run*, not
  dollars or runs-per-period.
- **FR-13 — Crash-after-spend consistency (CRP F-5/S-5).** Persist the `run_key` + a **spend marker
  BEFORE the provider call** (not an in-memory TTL); a re-submit after a crash between spend and the
  HTTP response is recognized and **not re-charged**. Define transcript-write ordering vs the HTTP
  return. (Note: `ask()`'s transcript append currently swallows `OSError` best-effort.)

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
| `panel_ask_all` (`--cap`) | ✅ (but wires no preflight/tracker) | `cli_panel.py:207` |
| `StakeholderPanel.ask/ask_all` | ✅ | `stakeholder_panel/panel.py` |
| `budget_preflight` — **NOT wired on the CLI path; fail-OPEN w/o a budget** | ⚠️ exists, not inherited | `stakeholder_panel/budget.py:28` |
| `projected_calls` — **wrong basis (facilitator, ×3–4, call-count)** | ❌ do not use for ask-all | `facilitation.py:507` |
| honest per-question **dollar** cost estimator | ❌ does not exist | — (FR-3 to source) |
| transcript store `.startd8/stakeholder-panel/<id>.json` | ✅ | `stakeholder_panel/transcript.py` |
| SYNTHETIC/UNRATIFIED banner | ✅ | `cli_panel.py:_render_answer` |
| serve auth — **loopback-only, NO CSRF/Origin/replay** | ⚠️ not what FR-2 needs | `serve.py`; `server/auth.py:APIKeyMiddleware` (cloud-only, non-const-time) |
| owl workflow-panel (trigger+monitor+dry-run) | ✅ (but confirm ignores dry-run; sends no creds) | `contextcore-owl/plugins/contextcore-workflow-panel/` |
| `host.docker.internal` reachability from Grafana pod | ✅ verified 2026-07-07 (needs non-loopback bind) | KinD `o11y-dev` |
| `BudgetManager` fail-closed / `run_key` idempotency / cancel / crash-marker | ❌ to-build | Phase 2 |
| CLI-backed `/stakeholders/run` endpoint | ❌ to-build | Phase 2 |

---

*v0.3 — Post-CRP R1. **The v0.2 premise was wrong:** the paid-run guardrails are NOT inherited from the
CLI (`panel_ask_all` wires no preflight/tracker), `BudgetManager` is fail-OPEN by default, `serve.py`
has no CSRF/Origin (and `0.0.0.0` deletes its loopback control), and `projected_calls` is the wrong
cost basis. All 15 CRP findings accepted; Phase 2 is now specced as a **fail-closed budget gate + real
auth + honest cost estimator + run_key idempotency + crash-marker + a real plugin render path** (FR-2/3/
4/8/11/12/13). Net effect: **keeping the panel CLI-only is now a first-class go/no-go option.***

---

## Appendix A — Accepted (Applied)

> CRP R1 — all 8 requirements findings accepted; changes in §0.2 + FR-2/3/4/8/11/12/13 + Reference Audit.

- **[F-1]** ACCEPTED → FR-4 (endpoint builds preflight+tracker, not inherited); §0 row 1 corrected.
- **[F-2]** ACCEPTED → FR-2 (build real auth: const-time key + Origin + CSRF + replay, or bridge-IP+TLS).
- **[F-2b]** ACCEPTED → FR-4 (register a blocking budget; refuse to run if none — else fail-open).
- **[F-3]** ACCEPTED → FR-3 (honest `min(cap,roster)×per_question_estimate`; drop `projected_calls`).
- **[F-4]** ACCEPTED → new FR-11 (run_key integrity + dedupe).
- **[F-5]** ACCEPTED → FR-8 (render the specific triggered session_id, not latest-mtime).
- **[F-6]** ACCEPTED → FR-4 (per-persona partial-failure semantics).
- **[F-7]** ACCEPTED → new FR-12 (cancel + daily/session USD ceiling).

## Appendix B — Rejected (with rationale)

_None — all 15 CRP findings (F-1…F-7/F-2b, S-1…S-7) were code-grounded and accepted._

## Appendix C — Incoming Review

#### Review Round R1 (independent CRP, 2026-07-07)

- **[F-1]** [BLOCKER] (FR-2, FR-4, §0 planning table row 1) The premise that "routing through the CLI *inherits* `budget_preflight`" is **false in the real code**. `cli_panel.py:panel_ask_all` (line 206) constructs `StakeholderPanel(roster, project_root=…, model_spec=…)` with **no `budget_preflight=` and no `cost_tracker=`**. Therefore `StakeholderPanel.preflight_budget()` is a **no-op** on the CLI path (panel.py:161-169 only fires when a preflight was injected), and `_record_cost` returns `0.0` for every answer (cost_tracker is `None`, panel.py:257) — the "total cost" line never even prints. The fail-closed gate and cost tracking **do not exist on the path FR-2 says to reuse** — the endpoint must construct `BudgetManager` + `budget_preflight(model=…, cost_per_question=…)` + a `cost_tracker` itself and pass them into `StakeholderPanel`. *Change:* rewrite the §0 row and FR-4 to state the endpoint **wires** (not inherits) the preflight/tracker, and add a requirement that a **blocking budget must be configured** — see F-2b.
- **[F-2]** [BLOCKER] (FR-2) `serve.py`'s security posture is **loopback-only**: `serve_kickoff` binds `127.0.0.1` (R1-S8, serve.py:285-333) and the *only* auth is `server/auth.py:APIKeyMiddleware`, active **only in `cloud` mode**, which checks `X-API-Key` on POST with a **non-constant-time `!=` compare and has no CSRF, no Origin allow-list, and no replay/nonce** (auth.py:24-33). FR-2's claim that serve.py provides "token, CSRF/origin" is unsupported. Binding `0.0.0.0` (required so the KinD Grafana pod reaches the host via `host.docker.internal` — a 127.0.0.1 service is *not* reachable that way) **removes the sole control (loopback) and exposes an unauthenticated spend endpoint to the LAN**. Also note per-persona **answer text (full Q&A) is returned to the browser in transit over this LAN-exposed endpoint** even though the transcript is `0600` at rest. *Change:* FR-2 must mandate mounting `APIKeyMiddleware` (constant-time compare) **plus** an Origin allow-list + CSRF token + replay nonce on the `0.0.0.0` bind, or bind the docker-bridge IP (not `0.0.0.0`) + TLS/tunnel — because serve.py supplies none of these for a non-cloud bind.
- **[F-2b]** [SHOULD] (FR-4) `BudgetManager.check_budget` only raises when a budget row is **active, matches scope, `block_on_exceed`, and is exceeded** (budget.py:220-252); with **no budget configured it returns `[]` and never raises** — i.e. the preflight is **fail-OPEN by default**, not fail-closed. FR-4 must require the endpoint to register a blocking budget (scoped to `project="stakeholder-panel"`) at startup and **refuse to run if none is configured**, else "fail-closed" is aspirational.
- **[F-3]** [BLOCKER] (FR-3, Reference Audit row `projected_calls`) `facilitation.projected_calls` (facilitation.py:507-511) computes the **multi-round `KickoffFacilitator`** basis: `prep_calls + n_personas × (3 or 4 rounds) + 1 synthesis`. The `ask-all` path is a **single fan-out of `n_personas × 1` call** (`StakeholderPanel.ask_all`, panel.py:216-237). Citing `projected_calls` as the ask-all dry-run cost basis **over-counts by 3-4× and mis-attributes a different engine**. It also returns a **call count, not a dollar estimate** — no "estimated cost" function exists; the only dollar figure is the caller-supplied `cost_per_question` in `budget_preflight`. *Change:* FR-3 must define the ask-all dry-run basis as `min(cap, len(roster)) × per_question_estimate` and name the honest source of the per-question dollar estimate (it is an estimate; real cost is only known post-call, as budget.py's docstring admits).
- **[F-4]** [SHOULD] (FR-4, OQ-2, OQ-5) Idempotency and dry-run→confirm integrity are asserted as guardrails but **nothing implements them**: there is no `run_key` anywhere in `panel.py`, and the base owl plugin's confirm path (`WorkflowPanel.tsx:135` → `executeWorkflow` :101) issues a **fresh POST that ignores the dry-run's `run_id`** — the confirmed run is unrelated to the previewed one, so question/cap/roster could differ between preview and spend. *Change:* promote OQ-2 to an FR: the dry-run response returns an opaque `run_key` binding the previewed `{question, cap, roster_version}`; the confirm MUST echo it; the server dedupes on it (persisted, TTL) and validates the params hash matches before spending.
- **[F-5]** [SHOULD] (FR-5, FR-8) "Renders the **latest** session's answers" races under concurrent runs. Each `StakeholderPanel` gets a unique `session_id` so per-file writes are safe, but "latest by mtime" is **nondeterministic when two runs overlap**, and a slow run finishing later overwrites the displayed one. *Change:* FR-8 must render the **specific `session_id` the panel triggered** (returned from `POST /stakeholders/run`), not "latest mtime", and state how concurrent runs are disambiguated in the Workbook.
- **[F-6]** [SHOULD] (FR-4, FR-9) "Missing key = clean fail, not a partial charge" is only half true. `ask_all` uses `asyncio.gather` (panel.py:233); a provider **timeout/failure on persona k after personas 1..k-1 already spent** raises, and the CLI catches it and returns **only the exception** (cli_panel.py:224-230) — the already-paid, already-persisted answers from the completed personas are dropped from the result. Spend is **per-persona, not atomic**. *Change:* FR-4 must specify partial-failure semantics (return the persisted partial answers + per-persona status; distinguish "no key → zero spend" from "mid-fan-out failure → partial spend").
- **[F-7]** [CONSIDER] (NR-3, scope) There is **no kill/cancel and no cumulative spend ceiling per period**. `--cap` bounds persona **count within one run**, not dollars and not runs-per-hour/day; a misconfigured or rapid-fire panel can fire many capped runs. The facilitator already has a cumulative-abort ceiling (`FacilitationConfig.budget_usd`, facilitation.py:541-543) — reuse that concept. *Change:* add an FR for a cancel/abort path and a per-session/daily USD ceiling that aborts before the next run's calls.

_Total: 8 findings (3 BLOCKER, 4 SHOULD, 1 CONSIDER). Not triaged — orchestrator dispositions to Appendix A/B._
