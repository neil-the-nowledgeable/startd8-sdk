# Grant & Cockpit Enhancements — Backlog Requirements

**Version:** 0.2 (Post-planning — feasibility-verified against the shipped code)
**Date:** 2026-07-12
**Status:** Draft backlog — prioritized; the S-tier is being implemented incrementally.
**Owner doc for:** value/usability/observability enhancements to the shipped Cloud Authorization Grant
(M0–M5) + the Agentic Workbook cockpit + the kickoff web/CLI surface.
**Relates to (does not restate):** `CLOUD_MIRROR_GRANT_REQUIREMENTS.md` (the grant), `AGENTIC_WORKBOOK_REQUIREMENTS.md`
(the cockpit), `WELCOME_MAT_2.0_REQUIREMENTS.md` (the web app), `GRAFANA_KICKOFF_PORTAL_*` (the metrics path).

---

## 0. Planning Insights (verified against the code)

> A feasibility pass over the shipped code confirmed the seams each enhancement plugs into and sharpened
> the effort estimates. Key findings:

| Assumption | Verified against code | Impact |
|-----------|----------------------|--------|
| The operator can silently mis-configure the grant target. | **Confirmed footgun:** `serve_kickoff`/`start_cmd` never set `project_id`, so `build_kickoff_app` defaults it to `Path(root).name`. An operator who issues `cloud-grant issue --project X` where `X ≠ the served dir name` gets a grant that **never resolves** — chat "unavailable," no error. `deployment_id` has the same latent trap. | **FR-E1 (print the required triple) + FR-E2 (`--for-serve` derive) are the top S-tier — they prevent silent failure.** |
| Grant events can emit metrics cheaply. | The `GrantStore._audit` hook (`cloud_grant.py:151`) fires on issue/consume/revoke — the perfect single emit point; OTel infra already exists (`costs/otel_metrics.py`, `otel.py`). | FR-E4 is a small, on-ethos win: one emitter behind the existing audit hook. |
| Auto-provisioning the cockpit is a call, not a build. | `build_workbook_v2_and_maybe_provision` (`portal_build.py:53`) exists; the CLI already calls `persist_snapshot_for_chat` at session end (`cli_kickoff.py:61`). | FR-E3 = add one provision call beside the existing snapshot persist. S, not M. |
| A `doctor` command exists. | **None** — no `doctor` command in any `cli_*.py`. | FR-E10 is net-new (small). |

**Resolved from the ideation pass:** the grant is invisible to itself (→ FR-E4/E5), the loop needs a manual
re-provision (→ FR-E3), and the cloud grant's value is stranded behind OQ-12 (→ FR-E12).

---

## 1. Problem Statement — the three value gaps

| Gap | Today | Should be |
|-----|-------|-----------|
| **The loop isn't closed for the human.** | The mirror persists the snapshot; the cockpit is read-only and only updates on a **manual re-provision**. | A kickoff session automatically refreshes the cockpit; the read-only surface points back to the action. |
| **The human door on cloud is shut (OQ-12).** | The grant authorizes cloud chat-write, but session creation is a GET and a browser can't present `X-API-Key` — only a programmatic client can reach it. | A documented, safe human path (auth-injecting proxy, or login→session-mint) so the grant's value is reachable. |
| **The grant is invisible to itself.** | An append-only JSONL audit file; no metrics/traces in an observability-first SDK. | Grant issue/consume/deny/expire as OTel metrics → a Grafana panel + alerts, where the operator lives. |

---

## 2. Requirements (prioritized; effort S/M/L)

### Tier 1 — S-effort quick wins (operator ergonomics + closing the loop)

- **FR-E1 (S, P0) — `kickoff start --grant-store` prints the exact required grant target.** On a
  grant-capable serve, print `(deployment_id, project_id, capability, allowed-origins)` the app will
  require, so the operator issues a matching grant. *(Fixes the confirmed silent-mismatch footgun.)*
- **FR-E2 (S, P0) — `cloud-grant issue --for-serve <project-root>`** derives `deployment_id`/`project_id`
  from the served project (dir name / config) so issue and serve **cannot drift**. Complements FR-E1.
- **FR-E3 (S, P1) — Auto-provision the cockpit on session end (opt-in). ✅ SHIPPED.** After a `kickoff chat` /
  concierge session, call `build_workbook_v2_and_maybe_provision` beside the existing snapshot persist
  (gated by a `--provision <url>` / config), so the cockpit refreshes without a manual step.
- **FR-E4 (S–M, P1) — Grant events → OTel metrics. ✅ SHIPPED.** A `GrantMetrics` sink
  (`cloud_grant.py`) wired as the `GrantStore(metrics=…)` callback emits four counters:
  `startd8.cloud_grant.{issued,consumed,denied,revoked}` — `denied` **labelled by `reason`** (the
  `GrantDeny` value: `absent`/`expired`/`exhausted`/`revoked`/`target_mismatch`/`store_unavailable`/
  `clock_untrusted`/`api_key_invalid`/`origin_rejected`), captured at every deny path (incl. the
  trust-chain auth-layer denials) via a single `_denied()` choke point. **Fail-OPEN** (distinct from
  the fail-CLOSED audit hook): a telemetry error never affects a grant. Wired in the issuance CLI
  (`cli_cloud_grant._open_store` → issue/revoke) and the served app (`cli_kickoff.start_cmd` →
  consume/deny). A no-op if OTel has no MeterProvider configured.
- **FR-E5 (S, P2) — Grant-usage Grafana panel. ✅ SHIPPED (spec).** `cloud-grant-usage.dashboardspec.yaml`
  (validated against the real `DashboardSpec` model): issued/consumed/revoked/denied stats +
  issue-vs-consume rate + **denials-by-reason** timeseries & bar. It is the sanctioned `/dbrd-cr8r`
  pipeline input — provision it with the pipeline (no raw JSON). Mimir mangles the counter names to
  `startd8_cloud_grant_*_total` (dots→underscores + `_total`); the spec's exprs already use that form.
- **FR-E6 (S, P1) — `cloud-grant status` / `audit`** — read the audit JSONL → "who consumed what, when,
  uses left, denials." The operator's missing visibility (offline, no metrics stack required).
- **FR-E7 (S, P2) — `cloud-grant gc`** (or prune-on-write) — drop expired/exhausted grants so the file
  store doesn't grow unbounded.
- **FR-E8 (S, P2) — Human `--ttl` (`15m`/`1h`) + env-var defaults** (`STARTD8_GRANT_STORE`,
  `_API_KEY`, `_DEPLOYMENT_ID`) so the operator doesn't retype five flags.
- **FR-E9 (S, P2) — `cloud-grant list --live-only` + near-expiry warnings.**
- **FR-E10 (S, P1) — `startd8 doctor`. ✅ SHIPPED.** — flags the **venv-vs-global `startd8` version drift** (a
  recurring pain), plus store/audit reachability. Pure friction removal.
- **FR-E11 (S, P2) — Cockpit Assistant deep-link** → "continue in `kickoff start`", so the read-only
  transcript becomes a jumping-off point.
- **FR-E20 (S, P2) — Health/readiness endpoint** on the cloud serve for a load balancer.
- **FR-E21 (S, P2) — `kickoff serve-cloud` wrapper** — grant-capable serve with sane defaults that prints
  the operator's next step (`cloud-grant issue --for-serve .`). Ties the operator flow together.
- **FR-E22 (S, P2) — Grant alerts. ✅ SHIPPED.** `cloud_grant_alerts.py` (source of truth) +
  `cloud-grant-alerts.rules.yaml` (committed Prometheus rule group, drift-guarded by test). 6 rules on
  the FR-E4 `denied{reason}` counter: origin/api-key **probing** (critical), **store-unavailable** infra
  (critical), aggregate **denial spike** (warning), and **expired/exhausted-in-use** reissue signals
  (the near-expiry proxy — fires when expiry actually bites, no new gauge needed). Self-contained.

### Tier 2 — M-effort higher-value outputs

- **FR-E12 (M, P1) — Close OQ-12 (human cloud door). ✅ SHIPPED (magic-link).** Resolved toward the
  **magic-link one-time session** (not the reverse-proxy recipe — see the decision in
  `CLOUD_HUMAN_DOOR_REQUIREMENTS.md`): `cloud-grant issue --with-link` mints a one-time bearer bound
  to the grant; `GET /kickoff/enter?t=…` redeems it (consume + burn, atomic), mints the same session
  `chat_page` does, and drops the human straight into the granted chat — no CLI, no X-API-Key header.
  Host-confined, no-oracle failures, revoke kills the door, per-turn revalidation unchanged. Minimal
  local-cloud scope (single-user); multi-user/IdP deferred. Un-strands the cloud grant's value.
- **FR-E13 (M, P1) — Real readiness + cost burndown in the cockpit. ✅ SHIPPED (was already built;
  verified + hardened).** Investigation found the live-data path is **complete**, contrary to the old
  spike note: `metrics.py` emits `kickoff.readiness.percent` (the completeness ratio — shipped under
  this name, not the doc's placeholder `kickoff_completeness_ratio`) + `kickoff.session.cost_usd`
  (+ proposals/blocked/facilitation) as real OTel gauges; `_gauges()` calls `auto_configure_otel()`
  (MeterProvider→OTLP→Mimir); `record_from_view` fires on **every** `build_workbook_v2_and_maybe_provision`
  (so E3's auto-provision now drives it); and the v2 cockpit's **"Readiness over time" + "Cost over
  time"** Mimir timeseries panels query `kickoff_readiness_percent` / `kickoff_session_cost_usd`. **No
  baked `vector()` anywhere.** The real gap was *coverage*: the emit→export path was "live-verified
  separately" (unautomated). This PR adds the missing tests — view→gauge (unmocked), an OTel in-memory
  export smoke, and a **name-drift guard** tying the panel PromQL to the emitted gauge names (the single
  failure that silently blanks the burndown).
- **FR-E14 (M, P2) — Exportable kickoff report. ✅ SHIPPED (was mostly built; completed).** The
  `startd8 kickoff readout` command + `readout.py` already exported a self-contained shareable document
  (Markdown / printable HTML → PDF-via-print / JSON, `--out`, `--full` for "how it got here" + "what's
  left"), covering **what's blocked** (activation) and **proposed next actions** (Proposals + Next step).
  The gap was **"what was captured"** — the report showed readiness *counts*, not the actual input
  *values*. Added a **"What was captured"** section (md + HTML, XSS-escaped, additive/byte-preserving
  when empty) listing the captured field values — the substance a project owner actually shares.
- **FR-E15 (M, P1) — Packaged "remote onboarding" workflow. ✅ SHIPPED.** `startd8 cloud-grant invite`
  assembles the operator's side in one command: issues a bounded/audited grant + one-time link,
  generates the consumer key, and prints the **operator playbook** — the exact `kickoff start --cloud …`
  serve command, the link to send, and how to review (cockpit/proposals/readout) + apply (VIPP). Pure
  assembly of shipped pieces (grant issuance, FR-E12 human door, `--mirror-cockpit`, audit). The
  headline flow is documented in **`REMOTE_ONBOARDING_GUIDE.md`**.
- **FR-E16 (M, P2) — Richer portfolio view. ✅ SHIPPED.** The existing `kickoff portal --index` built a
  Grafana *dashlist* (link-list of Workbooks) with no readiness. Added `kickoff portal --index --scan
  <workspace>`: a **$0, offline** scan (`portfolio.py`) that discovers every project (a dir with a
  `docs/kickoff` package), computes each one's readiness from the same `AgenticView` oracle the
  cockpit/readout use, and renders a **ranked readiness board** — build-ready first, stuck flagged —
  with a summary line + `--json`. The real "who's stuck / who's build-ready" view the dashlist couldn't
  give; complements (doesn't replace) the Grafana index. Best-effort per project (a broken one → an
  honest `unreadable` row, never a failed scan).
- **FR-E18 (S–M, P2) — Generalize the grant to more capabilities. ✅ SHIPPED.** `capture` and
  `instantiate` are now grantable on cloud via the SAME FR-14 trust chain as chat-write: the request's
  `X-API-Key` + `Origin` are threaded into `capture_apply` and (via a `capability`-parameterized
  `_concierge_write_gate`) `instantiate`, so a grant for that capability resolves + **consumes one use**
  per write. On cloud the trust chain replaces the local loopback-Host/CSRF chain (parity with
  chat-write); **local is byte-identical** and un-opted-in writes (friction/audience) still defer. A
  grant for one capability never authorizes another. Operators grant them with the existing
  `cloud-grant issue --capability capture|instantiate` (no CLI change needed).

### Tier 3 — architectural

- **FR-E17 (M, P1) — SQLite `GrantStore` backend. ✅ SHIPPED.** `SqliteGrantStore(GrantStore)` +
  `open_grant_store()` suffix-dispatch factory (`.db`/`.sqlite`/`.sqlite3` → SQLite, else the JSON
  `FileGrantStore`, unchanged). Structural wins over the file backend: (1) **`BEGIN IMMEDIATE` is the
  cross-process lock** (the DB serializes writers — no companion `.lock` flock); (2) **`CHECK(uses_remaining
  >= 0)`** makes the floor a DB constraint; (3) **`consumer_only=True`** (what the served app opens, NR-6)
  makes the store object structurally unable to `issue()` — the privilege split stops being convention.
  Row-per-grant (no full-file rewrite). Passes the same resolve/consume/revalidate/redeem/revoke/prune
  contract. **OQ-E3 resolved: SQLite is worth it** (stdlib, no new dependency).
- **FR-E19 (M, P3) — Lift the trust chain into a reusable middleware. ✅ INVESTIGATED → REJECTED
  (consolidate the contract, not the code); see `ADR_E19_SURFACE_AUTH.md`.** The three surfaces' auth
  only *looks* shared — kickoff (api-key ∧ Origin ∧ **grant/consume**), stakeholder (**bearer** ∧ nonce
  ∧ budget), consult (**per-run token** ∧ loopback-socket ∧ CSP) have **deliberately divergent** security
  semantics (empty-Origin → reject vs allow; `localhost` accepted vs rejected — two `_host_ok`s with
  *opposite* behavior; three different replay models). A shared middleware would be a false unification
  (over-abstraction + security-regression risk). Instead: **`test_surface_auth_conformance.py`** guards
  the ONE universal invariant (constant-time credential rejection) across all three. **That guard
  immediately caught a real drift** — kickoff's api-key used `!=`; fixed to `secrets.compare_digest`
  (behavior-preserving, closes a timing side-channel, now on parity with the other two surfaces).

---

## 3. Non-Requirements

- **NR-E1 — Not the full live in-dashboard chat (FR-11)** — deferred; these enhancements make the
  *read-only* cockpit + the *web-app* chat more valuable, not a live Grafana chat.
- **NR-E2 — Not the full tenancy/auth model (OQ-GE-7)** — FR-E12 is a deployment *recipe* + a coarse
  session-mint, not per-principal identity.
- **NR-E3 — No change to the grant's security semantics** — metrics/CLI/GC are additive + fail-open;
  they never weaken the fail-closed trust chain, redaction, or audit.

---

## 4. Open Questions

- **OQ-E1 — Auto-provision default.** Opt-in flag vs on-by-default when a `--provision` URL is configured?
- **OQ-E2 — Grant metrics cardinality.** `denied{reason}` is bounded (6 reasons); confirm no unbounded
  labels (never the grant id / project as a label at scale).
- **OQ-E3 — SQLite vs keep-file** for FR-E17 — is the added dependency worth the structural NR-6
  enforcement for the near-term single-instance target, or defer until multi-instance?

---

*v0.2 — Post-planning. 22 enhancements across 3 tiers, feasibility-verified against the shipped seams;
the silent-mismatch footgun (FR-E1/E2) surfaced as the top P0. S-tier being implemented incrementally — shipped so far: FR-E1/E2/E6/E7/E8/E9 (operator ergonomics) + FR-E3/E10 (close-the-loop + doctor).*
