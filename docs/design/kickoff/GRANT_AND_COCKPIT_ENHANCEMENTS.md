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
- **FR-E3 (S, P1) — Auto-provision the cockpit on session end (opt-in).** After a `kickoff chat` /
  concierge session, call `build_workbook_v2_and_maybe_provision` beside the existing snapshot persist
  (gated by a `--provision <url>` / config), so the cockpit refreshes without a manual step.
- **FR-E4 (S–M, P1) — Grant events → OTel metrics.** Behind the `_audit` hook, emit
  `cloud_grant_issued_total`, `_consumed_total`, `_denied_total{reason}`, `_expired_total`,
  `_uses_remaining` — reusing `costs/otel_metrics.py`. Fail-open (never breaks the grant).
- **FR-E5 (S, P2) — Grant-usage Grafana panel** (depends on FR-E4): issued/consumed/denied-by-reason
  over time, live-grant count. Via the dashboard pipeline (no raw JSON).
- **FR-E6 (S, P1) — `cloud-grant status` / `audit`** — read the audit JSONL → "who consumed what, when,
  uses left, denials." The operator's missing visibility (offline, no metrics stack required).
- **FR-E7 (S, P2) — `cloud-grant gc`** (or prune-on-write) — drop expired/exhausted grants so the file
  store doesn't grow unbounded.
- **FR-E8 (S, P2) — Human `--ttl` (`15m`/`1h`) + env-var defaults** (`STARTD8_GRANT_STORE`,
  `_API_KEY`, `_DEPLOYMENT_ID`) so the operator doesn't retype five flags.
- **FR-E9 (S, P2) — `cloud-grant list --live-only` + near-expiry warnings.**
- **FR-E10 (S, P1) — `startd8 doctor`** — flags the **venv-vs-global `startd8` version drift** (a
  recurring pain), plus store/audit reachability. Pure friction removal.
- **FR-E11 (S, P2) — Cockpit Assistant deep-link** → "continue in `kickoff start`", so the read-only
  transcript becomes a jumping-off point.
- **FR-E20 (S, P2) — Health/readiness endpoint** on the cloud serve for a load balancer.
- **FR-E21 (S, P2) — `kickoff serve-cloud` wrapper** — grant-capable serve with sane defaults that prints
  the operator's next step (`cloud-grant issue --for-serve .`). Ties the operator flow together.
- **FR-E22 (S, P2) — Grant alerts** (depends on FR-E4): near-expiry, denial-rate spike (misconfig/abuse).

### Tier 2 — M-effort higher-value outputs

- **FR-E12 (M, P1) — Close OQ-12 (human cloud door).** A documented **auth-injecting reverse-proxy
  recipe** and/or a `login → session-mint POST` so a browser can open a grant session. Un-strands the
  cloud grant's value.
- **FR-E13 (M, P1) — Real readiness + cost burndown in the cockpit.** Emit `kickoff_completeness_ratio`
  + per-session cost to Mimir (the designed kickoff-portal M1 seam) so the cockpit's time-series panels
  show **real progress**, not baked `vector()` values.
- **FR-E14 (M, P2) — Exportable kickoff report** — "what was captured, what's blocked, proposed next
  actions" as shareable markdown/PDF. A tangible artifact for the project owner.
- **FR-E15 (M, P1) — Packaged "remote onboarding" workflow (mostly docs/assembly).** Operator issues a
  bounded/audited grant → remote stakeholder runs a session → mirrored + audited → operator reviews
  proposals in the cockpit → applies via VIPP. The pieces exist; package + document the headline flow.
- **FR-E16 (M, P2) — Richer portfolio view** — `kickoff portal --index` → a real multi-project readiness
  board (who's stuck, who's build-ready).
- **FR-E18 (S–M, P2) — Generalize the grant to more capabilities** — the `capability` string is already
  parameterized; wire `capture`/`instantiate` under a grant to extend the parity story.

### Tier 3 — architectural

- **FR-E17 (M, P1) — SQLite `GrantStore` backend.** **Structurally enforces NR-6** (the served app holds
  a *decrement-only* capability; issuance needs another grant), ACID cross-process for free (simpler +
  more correct than the fcntl lock), GC via SQL. Drop-in behind the existing `GrantStore` interface —
  converts the "convention-level privilege split" into an enforced one.
- **FR-E19 (M, P3) — Lift `_cloud_capability` + the trust chain into a reusable served-surface
  middleware** — reuse for `stakeholder_run_server` and `consult --serve` instead of each re-implementing
  cloud posture.

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
the silent-mismatch footgun (FR-E1/E2) surfaced as the top P0. S-tier being implemented incrementally.*
