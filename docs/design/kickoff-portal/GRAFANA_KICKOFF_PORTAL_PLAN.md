# Grafana Kickoff Portal — Iteration 1 Implementation Plan

**Version:** 1.1 (Post-CRP R1 — 5 plan findings accepted & applied)
**Date:** 2026-07-07
**Status:** Draft
**Requirements:** `GRAFANA_KICKOFF_PORTAL_REQUIREMENTS.md` (v0.3)
**Pilot:** `household-o11y`

---

## Planning summary

The spike is **~70% assembly of shipped capability + a two-plugin fork + a real metric producer**.
The stack risk is **void** (M0 verified live). Post-CRP, the dominant risk is **the emit→read path**:
`build_transport().emit()` produces no Mimir metrics and GUIDANCE is unqueryable, so M1 must stand up a
real OTel `Meter`→Mimir producer (proven by the M0 probe + M2 read-path proof) before any panel shows
live data. The option-3 spike already proved generation + provisioning + static render; the un-de-risked
part is live data flow.

Milestones are ordered so each lands independently and the "is Grafana a good kickoff UI" question is
answered as early as possible with the least sunk cost.

---

## M0 — Stack precondition — ✅ ALREADY SATISFIED (verified 2026-07-07)

**Goal:** a local TSDB + Grafana able to receive OTLP emits and host a provisioned dashboard.
**Status:** **DONE — no work required.** The environment already has:
- **Grafana 12.3.0** on `:3000`, healthy; SA tokens in `$GRAFANA_API_TOKEN` / `$GRAFANA_SA_TOKEN`.
- **OTLP** `:4317` (gRPC) + `:4318` (HTTP), **Loki** `:3100`, **Mimir** `:9009`, **Tempo** `:3200` — all listening.
- **Datasources with canonical UIDs**: `loki`, `mimir` (default, prometheus-type), `tempo` — matching
  the mixin `config.libsonnet` expectations. Plus `Infinity` (`yesoreyeram-infinity-datasource`) and Pyroscope.
- **Proof the target path works here:** live `cc-portal-online-boutique` persona dashboards in a
  "Portal" folder — `portal_spec_builder → dashboard_creator → provision` is a *demonstrated* path in
  this exact Grafana. Use them as the visual template for the kickoff sibling builder.

**Consequence:** the earlier "stand up a fixture stack" concern is void. M1 can emit to `:4318` and M2
can `provision=True` against `:3000` immediately.

**M0 sanity check — MANDATORY before trusting the read path (CRP S-2).** "Ports listen" ≠ "a kickoff
series is queryable." The M0 inventory does **not** include a span→gauge metric-ifier (that's
ContextCore-owned, out of scope). So before M1: **emit one probe metric** (`kickoff_completeness_ratio`
via an OTel `Meter` → OTLP `:4318`) and **confirm a queryable series actually appears in Mimir**
(`curl :9009/prometheus/api/v1/query?query=kickoff_completeness_ratio`) — and one probe log appears in
Loki. If the probe metric does *not* land, the FR-2 direct-`Meter` producer is confirmed mandatory
(it is — see M1). Note the option-3 spike proved provisioning + static render only, NOT live reads.

## M1 — Persistence-projection seam (TWO producers, CRP S-1/F-1/F-2/F-3)

**Goal:** kickoff state projected so the FR-5 panels can actually read it.
**Files:** `src/startd8/kickoff_experience/projection.py` (derive from the canonical view-model),
`src/startd8/integrations/contextcore.py` (emit hook).

The v0.3 "one `emit()` to Loki/Mimir" is **wrong** — `build_transport().emit()` writes only an
envelope span (Tempo) + local JSON, **no metrics**, and GUIDANCE is unqueryable. M1 therefore has
**two distinct producers**, each feeding a named store:

- **(a) Current-state + history metrics → Mimir (the FR-5 a–d producer).** An OTel **`Meter`** emits
  gauges `kickoff_completeness_ratio` and `kickoff_field_confirmed{domain,field}` via **OTLP `:4318`**.
  Mimir's scrape-time samples ARE the append-only **history** (burndown) — no comms record involved.
  Current value = latest sample. This is a *different mechanism* than the comms transport.
- **(b) Audit event → Loki (optional, the capture/confirm log).** One structured log line per write
  (LogQL-queryable). If a durable comms record is also wanted, use a **queryable** kind
  (`TASK_STATE`/`INSIGHT`) — **never `GUIDANCE`** (query dead-end).

- Derive from **`state.py`'s `KickoffState`/`FieldState`** (FR-3), NOT a YAML re-parse. **State +
  provenance only**, through the `tracking_redaction` chokepoint.
- **Current-state identity** (if a comms record is kept): explicit `record_id` from
  `(project, domain, field_path)` — NOT the default `now()` id (CRP F-3). History lives in the metric
  samples, never in an idempotent-overwritten record.
- **Non-blocking:** try/except, fail-open; projection failure never fails the CLI write.
- Hook into `capture.py:apply_capture` + the `confirm` verb.
- **Exit (per store):** `kickoff_completeness_ratio` + `kickoff_field_confirmed` are **queryable in
  Mimir** and move on confirm; the audit log is **queryable in Loki**. (No claim about GUIDANCE.)

## M2 — Deterministic dashboard generation (read surface)

**Goal:** a generated kickoff dashboard, jsonnet path, no hand-authored JSON.
**Decision (Discovery 2):** do **NOT** retrofit `portal_spec_builder.py`'s persona-gating into a 2D
persona×domain matrix (16 scattered `if section in sections` sites — moderate surgery). Instead write
a dedicated **`src/startd8/kickoff_experience/portal_spec.py`** (SHIPPED) that emits a `DashboardSpec`
**dict** directly (the spec is a plain dict — cheap to build fresh). Borrows panel idioms from
`portal_spec_builder` but gates by the 4 kickoff **domains**. Lives with the other kickoff surfaces
(`web.py`/`serve.py`), NOT in `observability/` — it depends on `state.py` + `concierge.explain`.
Wired as **`startd8 kickoff portal`** (read-only by default; `--provision URL` pushes to Grafana).

- Panels (FR-5): overall **completeness gauge**; **per-domain status** (stat/table over the 4 domains);
  **per-field confirmation state**; **confirmation-history/burndown timeseries** (the unique TS value);
  **markdown `text`** panels for each domain's What/Why/Who (reuse `concierge/core.py` `explain`
  content — cite it, don't restate it).
- Generate via `DashboardCreatorWorkflow` **generate-only mode** (`dry_run`/`check`) → writes
  `.startd8/dashboards/cc-portal-{project}.json` with **no live Grafana** (Discovery 3). UID
  `cc-portal-{project}`. **Provision immediately** to the verified `:3000` Grafana (`provision=True`,
  `$GRAFANA_API_TOKEN`) — M0 is live. Use the existing `cc-portal-online-boutique` dashboards as the
  visual/layout template.
- **Read-path proof FIRST (CRP S-3), gates M4:** before layout polish, prove **one emitted metric
  renders in a provisioned panel end-to-end** (M1 `Meter` → Mimir → a live PromQL stat panel showing a
  real, non-`vector()` value). The "closes the loop" claim rests on this demonstrated read-back, not on
  the static-render spike.
- **Read-path decision (OQ-8, CRP S-4) — DECIDED: option-1 "bake + re-provision" (no endpoint).**
  Two ways to do "Infinity-over-static-file", and only one carries a reachability/exposure cost:
  - **Option 1 — bake current state into panels + re-provision on write (CHOSEN for the read slice).**
    State is rendered into the panels at generation time; the CLI re-provisions on each write. **No
    endpoint, no new network exposure, never stale** (kickoff state only changes on a CLI write). This
    is what the option-3 spike already proved.
  - **Option 2 — Infinity over a live host endpoint (deferred to M4).** Panel self-refreshes by
    fetching `http://host.docker.internal:<port>/kickoff-state.json`. **Reachability CONFIRMED
    (2026-07-07):** the Grafana pod resolves `host.docker.internal` and reaches a host server
    empirically (also the LAN IP `192.168.7.64`; `172.18.0.1`/`gateway.docker.internal` do NOT).
    **Caveat:** it only works if the endpoint binds `0.0.0.0` (not `serve.py`'s loopback-only) → LAN
    exposure of the snapshot; acceptable only because it's state+provenance (no raw values) + a token.
  Option 2's *only* advantage is decoupling refresh from re-provision — which matters for M4's live
  write-back loop, not for a read slice. So: **read slice = option 1; option 2 lands with M4.**
  Topology on record: KinD `o11y-dev` (3 nodes, `172.18.0.0/16`); Grafana = NodePort 30000 → host `:3000`.
- **Exit:** `startd8` generates the dashboard JSON deterministically ($0); provisioned dashboard
  renders the 4 domains + completeness + burndown reading **live** M1 metrics (read-path proof passed).

## M3 — Self-monitoring completeness verifier

**Goal:** the portal watches its own kickoff completeness.
**Pattern:** copy ContextCore `install/verifier.py` shape.
**File:** `src/startd8/kickoff_experience/completeness_verifier.py`.

- Declarative `KICKOFF_REQUIREMENTS` list (each a `check()` over `KickoffState`): "≥1 value prop
  captured", "each domain has ≥1 confirmed field", etc. Emit `kickoff.completeness_percent` gauge +
  per-requirement status gauges + a span tree.
- Surface as a self-monitoring section/row in the M2 dashboard.
- **Exit:** completeness gauge moves as fields are confirmed; per-requirement panel shows gaps.

## M4 — Write action via forked panel (interactive surface)

**Goal:** confirm/capture a field **from Grafana**, routed through the CLI (FR-6, CLI-sole-writer).
**Decision (Discovery 1 / user steer):** fork the **already-built `contextcore-chat-panel`** (input
capture + configurable webhook), NOT the trigger-only workflow-panel.

- **Fork delta is likely TWO plugins (CRP S-5), both unsigned — pin both commits:**
  1. `kickoff-capture-panel` (fork of `contextcore-chat-panel`): field selector + value + `mode`;
     payload `{project, field_path, value, mode}`; thread the `serve.py` auth headers (token/CSRF/origin).
  2. `contextcore-datasource` (configure/fork): the CORS-free proxy so the browser panel reaches the
     CLI-backed endpoint without a cross-origin fetch.
  Enumerate the real UI + payload-contract + auth-header-threading delta before estimating M4.
- Scope: **confirm an existing scalar** field (writes the ledger — the wired path; capture-new is out,
  per CRP F-4). POST `{project, field_path, value, mode: "confirm"}` to a **CLI-backed thin endpoint**.
- **Write endpoint (OQ-2 resolution):** reuse `kickoff_experience/serve.py`'s posture (loopback bind,
  token, CSRF/origin) — add one `POST /capture/apply`-style route that calls the **existing**
  `capture.py` path, inheriting `allowed_value_paths` allow-list + confinement + round-trip gate. The
  panel may route through **`contextcore-datasource`** (CORS-free proxy) to avoid browser-CORS.
- **Write-back refresh needs option-2 (Infinity over a host endpoint).** For the panel to reflect a
  Grafana-driven write *without* a CLI re-provision, stand up the read-only JSON endpoint bound
  `0.0.0.0` and point an Infinity panel at `http://host.docker.internal:<port>/kickoff-state.json`
  (**reachability confirmed 2026-07-07** from the Grafana pod). Add a token + keep it state+provenance
  only (no raw values) to bound the LAN exposure the `0.0.0.0` bind introduces.
- **Plugin-load reconfig is real work on a SHARED Grafana (CRP F-6 / NR-10):** loading the unsigned
  panel needs `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS` + a plugin mount + a **Grafana restart** on
  the `:3000` that also serves `cc-portal-online-boutique`. This is NOT covered by "M0 satisfied."
  **Confirm the allow-list (or isolate a plugin-enabled Grafana) before M4** — restarting the shared
  instance has blast radius.
- After a write, M1 metrics re-emit → M2 panels + M3 gauge update (closes the loop — gated on the M2
  read-path proof).
- **Exit:** clicking confirm in Grafana writes the ledger via the CLI path and the live gauge reflects it.

## M5 — Pilot + verdict

**Goal:** the deliverable — an honest go/no-go on Grafana-as-kickoff-UX.

- Run M0–M4 end-to-end on `household-o11y`.
- Score the FR-9 rubric (form ergonomics, write→reflect latency, discoverability, linear-flow support,
  accessibility, plugin maintenance cost) with evidence (screenshots, timings).
- Write `GRAFANA_KICKOFF_PORTAL_VERDICT.md`: **PRIMARY / COMPLEMENTARY / NO-GO** + rationale +
  recommended iteration-2 scope. Working hypothesis to test, not assume: **COMPLEMENTARY** (Grafana
  owns read/history/self-monitoring; HTMX stays primary for linear form-filling).

---

## Requirement → milestone traceability

| Req | Milestone(s) |
|-----|-------------|
| FR-1 projection seam | M1 |
| FR-2 non-task emit hook | M1 |
| FR-3 single source of truth | M1 (derive from `state.py`) |
| FR-4 generated dashboard | M2 (sibling builder, not portal_spec_builder retrofit) |
| FR-5 read panels | M2 |
| FR-6 write action | M4 |
| FR-7 completeness verifier | M3 |
| FR-8 pilot on household | M0 (stack) + M5 |
| FR-9 rubric + verdict | M5 |

## Key risks

1. ~~Stack bring-up (M0) is the critical path.~~ **VOID — M0 verified live** (Grafana 12.3.0 :3000 +
   OTLP/Loki/Mimir/Tempo + canonical UIDs + a proven portal-provisioning path). The former top risk is
   gone; the critical path is now M1 (emit seam) → M4 (panel fork).
2. **The emit→read path (M1) — NEW critical risk (CRP S-1/S-2).** `emit()` produces no Mimir metrics
   and GUIDANCE is unqueryable; M1 must stand up a real OTel `Meter`→Mimir producer, verified by the M0
   probe + M2 read-path proof. This — not the panel fork — is the true unknown.
3. **Plugin fork is two unsigned plugins on a shared Grafana (CRP S-5/F-6)** — pin both commits,
   document the delta, and confirm the unsigned allow-list before restarting the shared instance.
4. **Burndown emptiness (OQ-6)** — synthetic history can demo the panel but **cannot** validate the
   burndown hypothesis; FR-9 now requires a **real** multi-timepoint capture sequence in the evidence.

---

## Appendix A — Accepted (Applied)

> CRP R1 — all 5 plan findings accepted and applied.

- **[S-1]** ACCEPTED → M1 split into (a) `Meter`→Mimir metrics + (b) Loki audit; per-store exit criteria.
- **[S-2]** ACCEPTED → M0 gains a mandatory probe-metric end-to-end sanity check.
- **[S-3]** ACCEPTED → M2 read-path proof inserted; M4 "closes the loop" gated on it.
- **[S-4]** ACCEPTED → M2 Infinity path must name a concrete source (static file / standing endpoint) or drop.
- **[S-5]** ACCEPTED → M4 enumerated as two unsigned plugins; Risk 3 rewritten; commits to be pinned.

## Appendix B — Rejected (with rationale)

_None — all 5 plan findings were code-grounded and accepted._

## Appendix C — Incoming Review

_(empty — R1 triaged into Appendix A; original suggestions retained below for provenance)_

### R1 (triaged — retained for provenance)

- **[S-1]** (plan) **[BLOCKER]** — *M1's exit criterion is unachievable via `build_transport().emit()` alone; name the metric producer.* M1 exits on "a record visible in **Loki/Mimir**," but `build_transport(mode=DUAL).emit()` writes only an envelope span to **Tempo** (payload-less; `otlp_transport.py:98-115`) + a local JSON file — **nothing to Mimir**, and Loki only if a log is separately emitted. Per the REQ-PRO-001 ownership boundary (`integrations/contextcore.py:11-18`), the span→gauge metric-ification is ContextCore-owned and out of scope. **Proposed change:** split M1 into (a) comms-record emit (current-state/audit) and (b) an explicit OTel `Meter` gauge emit to `:4318` for the Mimir-backed completeness/burndown series — or re-point FR-5 panels off Mimir onto Tempo/Loki. Rewrite the M1 exit to state **which store each FR-5 panel reads**.

- **[S-2]** (plan) **[BLOCKER]** — *The M0 "verified live" inventory omits the span→gauge metric-ifier, so FR-5/FR-7 can render empty on a green M0.* M0 lists Grafana/OTLP/Loki/Mimir/Tempo/collector + canonical UIDs, but **not** the ContextCore-owned component that turns emitted spans into `contextcore_*`/kickoff gauges (`contextcore.py:11-18`). "Ports listen" ≠ "a kickoff series is queryable." **Proposed change:** add a concrete M0 sanity check that **emits one kickoff record and confirms a queryable series actually appears in Mimir (or Loki)** end-to-end — not just that `:9009`/`:3100` are up. If no metric-ifier is present, S-1(b) (direct gauge emit) becomes mandatory, not optional.

- **[S-3]** (plan) **[SHOULD]** — *Prove the read path before M4, not inside it.* M4's exit ("projection re-emits → M2 panels + M3 gauge update — closes the loop") is unverifiable if M1 emitted via `GUIDANCE`, which `OTLPTransport.query()` refuses (see requirements F-1; `otlp_transport.py:121-129`). **Proposed change:** insert a read-path spike **in M2** that proves a single emitted record renders in a provisioned panel end-to-end (choosing the queryable kind + datasource). Gate M4 on that spike passing, so the "closes the loop" claim rests on demonstrated read-back.

- **[S-4]** (plan) **[SHOULD]** — *M2's Infinity path (OQ-8) has no standing read-only endpoint to point at.* M2 proposes an Infinity panel over "the CLI `state.json`," but `serve.py` exposes state only via `inspect_payload` or a served app that **binds a loopback port and (write mode) can mutate** (`kickoff_experience/serve.py:182-210, 285-333`) — there is no always-on read-only JSON endpoint for Grafana's **server-side** Infinity fetch (a different origin/trust context than the browser). **Proposed change:** specify concretely how Infinity reaches state — a static generated file path vs a standing read-only endpoint — and its auth, or drop OQ-8 for iteration 1 and keep current-state on the same producer as burndown.

- **[S-5]** (plan) **[SHOULD]** — *The plugin-fork delta (Risk 3) is under-scoped; it is likely two forks, not one.* The chat-panel is a single-`TextArea`→configurable-webhook panel (`plugin.json`: type `panel`, `grafanaDependency >=10.0.0`, unsigned). M4 needs: a field-selector + value input + `mode` field, a payload schema (`{project, field_path, value, mode}`), a CLI-backed thin endpoint with the `serve.py` auth posture threaded (token/CSRF/origin), **and** a CORS story — which the plan says routes through `contextcore-datasource`, i.e. a **second** plugin to fork/configure. **Proposed change:** enumerate the real fork delta (new form UI, payload contract, auth-header threading) and state explicitly whether the `contextcore-datasource` proxy is also forked/configured; re-estimate M4 accordingly and pin both plugin commits.
