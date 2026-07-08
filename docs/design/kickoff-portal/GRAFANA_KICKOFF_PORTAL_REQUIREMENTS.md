# Grafana Kickoff Portal — Iteration 1 (Capability-Validation Spike) Requirements

**Version:** 0.4 (Post-CRP R1 — 12 findings triaged, all accepted & applied)
**Date:** 2026-07-07
**Status:** Draft
**Doc home:** `docs/design/kickoff-portal/`
**Plan:** `GRAFANA_KICKOFF_PORTAL_PLAN.md` (v1.0)
**Pilot fixture:** `household` (`/Users/neilyashinsky/Documents/dev/household/household-o11y`)

---

## 0. Planning Insights (Self-Reflective Update)

> Changes from v0.1 (pre-planning) → v0.2 after a grounded planning pass (2 exploration agents over
> the owl plugins, `portal_spec_builder`, ContextCore `comms/`, and the household stack). Seven
> corrections:

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|--------------------|--------|
| The already-built plugin (owl `contextcore-workflow-panel`) is the reusable write surface | The **workflow-panel is trigger-only** (`{project_id, dry_run}` → Rabbit `/workflow/run`, **no input capture**). The reusable input-capture plugin is **`contextcore-chat-panel`** (controlled input → configurable `webhookUrl` POST), plus a `contextcore-datasource` CORS proxy. | FR-6 now says **fork chat-panel** (small delta), not "reuse workflow-panel as-is." OQ-1 resolved. |
| Adapt `portal_spec_builder.py` persona-gating → domain-gating | Persona→sections is a hardcoded dict + 16 scattered `if section in sections` checks; adding a 2nd gate dimension is **moderate surgery**. `DashboardSpec` is a plain dict (cheap to build fresh). | FR-4 now specifies a **sibling `kickoff_portal_spec.py`** that emits the dict directly, not a retrofit. OQ-3 resolved. |
| Dashboard generation may need a live Grafana | `DashboardCreatorWorkflow` has **generate-only mode** (`dry_run`/`check`) → writes `.startd8/dashboards/{uid}.json` with no Grafana contact. | The smallest slice needs **no running Grafana**; de-risks the read surface. |
| Emit a kickoff record via the ContextCore bridge | `CommsKind` enum has **no kickoff/config variant** (only insight/handoff/guidance/task_state/lesson); there is **no non-task raw-record emit path** in `integrations/contextcore.py`. | FR-2: iteration 1 **reuses `CommsKind.GUIDANCE` + a `record_type` discriminator** (zero cross-repo change); a real enum add is a deferred follow-up. |
| "Supersede/tombstone" is available | Transport layer is **emit + idempotent `record_id` only — no delete/tombstone**. Supersede exists only at the higher *insight* layer. | FR-1: supersede is a **payload convention** (`retracted`/`superseded_by` + new record), not a store primitive. OQ modeling clarified. |
| household is a ready pilot with Grafana+TSDB | household has **no compose, no exporter, no Grafana provisioning** — the stack is *aspirational* in `conventions.yaml`. | New **M0 precondition** (stand up a fixture stack; reuse SDK `docker-compose.loki-stack.yml`). FR-8 split into stack + verdict. OQ-5 resolved. |
| Emit field values into the TSDB | Kickoff inputs (business-targets) can carry sensitive text; the store is queryable via Grafana. | FR-1 defaults to **emit state + provenance, NOT raw values**; raw text stays in YAML. OQ-7 resolved. |

**Resolved open questions:**
- **OQ-1 → Fork `contextcore-chat-panel`.** The already-built input-capture panel; workflow-panel is trigger-only.
- **OQ-2 → Reuse `kickoff_experience/serve.py` posture** (loopback + token + CSRF/origin); add one CLI-backed capture route; optionally proxy via `contextcore-datasource`.
- **OQ-3 → Sibling spec builder**, not a `portal_spec_builder` retrofit.
- **OQ-5 → Stack must be stood up (M0).** household's TSDB stack is unbuilt; reuse the SDK loki-stack compose as the fixture.
- **OQ-7 → Emit state + provenance only** by default; raw values stay in YAML (redacted-value emission is a later opt-in).

**Still open:** OQ-4 (signal-type mix — see revised list), OQ-6 (burndown richness — mitigated by seeding synthetic history for the demo).

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted `Lessons_Learned/sdk/Design_Docs_LESSONS_LEARNED.md` + the recurring-lesson classes. Each
> applied lesson changed the draft:

- **Phantom-reference audit** — every symbol this spec names was grounded to a real path during the
  planning pass (`portal_spec_builder.py`, `dashboard_creator/workflow.py`, `comms/transport.py`,
  `tracking_redaction.py`, `contextcore-chat-panel`, `kickoff_experience/{state,capture,serve}.py`).
  The one **non-existent** thing (`CommsKind.CONFIGURATION`) is explicitly marked **to-be-created /
  deferred** in FR-2, not assumed. Added the §Reference-Audit table below.
- **Prune phantom scope** — the persona-gating retrofit was architecturally the wrong mechanism (2D
  gate surgery); moved to a Non-Requirement (NR-8) and replaced with a sibling builder (FR-4).
- **Single-source vocabulary ownership** — the per-domain What/Why/Who prose is **owned by
  `concierge/core.py`'s `explain` content**; FR-5 **cites** it rather than restating it (no drift).
  The kickoff data model (4 domains, ledger) is owned by existing kickoff docs and cited, not redefined.
- **Overloaded-term co-location** — "portal" already denotes `observability/portal_spec_builder.py`'s
  onboarding portal. The kickoff portal gets its **own module namespace** (`kickoff_portal_spec.py`)
  to avoid stacking a 2nd meaning onto the onboarding-portal builder.
- **CRP steering** — this doc-set is brand-new (least-reviewed); the CRP focus file names it as the
  target and lists settled items (dual-store split, CLI-sole-writer, no-hand-authored-JSON) as
  do-not-relitigate.

### Reference Audit

| Symbol / artifact cited | Exists? | Path |
|-------------------------|---------|------|
| `portal_spec_builder.build_portal_spec` | ✅ | `src/startd8/observability/portal_spec_builder.py` |
| `DashboardCreatorWorkflow` (dry_run/check) | ✅ | `src/startd8/dashboard_creator/workflow.py` |
| `CommsRecord` / `Transport.emit` / `build_transport` | ✅ | `ContextCore/src/contextcore/comms/transport.py` |
| `CommsKind.GUIDANCE` (reused) | ✅ | same |
| `CommsKind.CONFIGURATION` (kickoff-specific) | ❌ to-be-created (deferred) | — |
| `redact_text` / `redact_evidence` chokepoint | ✅ | `src/startd8/integrations/tracking_redaction.py` |
| `contextcore-chat-panel` (fork base) | ✅ | `ContextCore/contextcore-owl/plugins/contextcore-chat-panel/` |
| `contextcore-datasource` (CORS proxy) | ✅ | `ContextCore/contextcore-owl/plugins/contextcore-datasource/` |
| Canonical kickoff view-model (`KickoffState`) | ✅ | `src/startd8/kickoff_experience/state.py` |
| Capture/safe-write path | ✅ | `src/startd8/kickoff_experience/capture.py` |
| Serve auth posture | ✅ | `src/startd8/kickoff_experience/serve.py` |
| household's *own* TSDB stack (compose/exporter) | ❌ unbuilt (aspirational) — **but irrelevant** | we use the shared stack instead |
| Shared local stack (Grafana 12.3.0 :3000, OTLP :4317/:4318, Loki/Mimir/Tempo, UIDs `loki`/`mimir`/`tempo`, SA tokens in env) | ✅ **verified live 2026-07-07** | M0 already satisfied |
| Proven `portal→dashboard_creator→provision` path | ✅ live `cc-portal-online-boutique` dashboards in this Grafana | template for FR-4 |
| `Infinity` datasource (REST/JSON→Grafana) | ✅ installed (`yesoreyeram-infinity-datasource`) | alt read path (OQ-8) |

### 0.2 CRP Round-1 Triage (v0.3 → v0.4)

> Independent CRP (Appendix A) raised F-1…F-7 (requirements) + S-1…S-5 (plan), all verified against
> real code. **All 12 ACCEPTED** (0 rejected — every finding was grounded and 2 were independently
> confirmed by the option-3 spike). The live-data path (emit→metric→panel) was **broken as specced**;
> this triage fixes it.

| # | Sev | Finding | Change applied |
|---|-----|---------|----------------|
| F-1 | BLOCKER | `CommsKind.GUIDANCE` is a query dead-end — `OTLPTransport.query()` *raises* for GUIDANCE | **Abandon the GUIDANCE reuse.** FR-2/NR-9 rewritten: current-state via a **real OTel metric gauge** (queryable), audit trail via a **Loki log** or a *queryable* comms kind — never GUIDANCE. |
| F-2 | BLOCKER | Emit seam emits **zero Mimir metrics**; span→gauge metric-ifier is ContextCore-owned + out of scope | FR-2 now **names a concrete producer per FR-5 panel** (OTel `Meter`→OTLP `:4318`→Mimir for gauges; Loki for the event log). No panel left without a producer. |
| F-3 | BLOCKER | `record_id` keys on `now()` → not idempotent; identity-overwrite would erase burndown history | FR-1 **splits two stores**: current-state = idempotent-by-**identity** (`(project,domain,field_path)`); history = **append-only metric samples over scrape time** (never the comms store). |
| F-4 | SHOULD | `capture.py` rejects not-yet-present keys; confirm≠capture are different write paths | FR-6 scoped to an **existing scalar** field + states it demos **confirm (ledger)**, the wired path. |
| F-5 | SHOULD | "Proven path" proves *provisioning*, not live reads (OB panels are text + `vector(N)` literals) | Reference-Audit row + FR-8 **qualified**: "provisioning proven; live-metric read UNPROVEN." Spike confirmed this. |
| F-6 | SHOULD | Unsigned forked panel needs allow-list + restart on the **shared** Grafana (blast radius) | New **NR-10**: acknowledge the plugin-load reconfig + shared-stack risk; confirm/isolate allow-list before M4. |
| F-7 | SHOULD | FR-9 rubric has no thresholds → verdict not reproducible | FR-9 given **falsifiable pass-bars** + a decision rule + a required **real multi-timepoint capture sequence** (not synthetic). |
| S-1 | BLOCKER | M1 exit ("visible in Loki/Mimir") unachievable via `emit()` alone | M1 **split** (a) comms/audit emit + (b) explicit `Meter` gauge→Mimir; exit states which store each panel reads. |
| S-2 | BLOCKER | M0 "verified live" omits the metric-ifier → panels can render empty on green M0 | M0 gains an **end-to-end sanity check**: emit one record, confirm a **queryable series appears** in Mimir/Loki. |
| S-3 | SHOULD | "Closes the loop" unverifiable if emitted via GUIDANCE | **Read-path proof moved into M2** (one emitted record renders in a provisioned panel); M4 **gated** on it. |
| S-4 | SHOULD | Infinity (OQ-8) has no standing read-only endpoint for server-side fetch | OQ-8/M2 must **specify** how Infinity reaches state (static file vs standing read-only endpoint + auth) or drop it for iter 1. |
| S-5 | SHOULD | Plugin fork is likely **two** forks (panel + `contextcore-datasource`), under-scoped | M4/Risk-3 **enumerate** the real delta + pin **both** plugin commits. |

### 0.3 Implementation Status (semantic-validation reconciliation, 2026-07-08)

> A per-FR traceability audit against the shipped code. This increment deliberately shipped the
> **read-side spike ("Option 1: bake current state into panels + re-provide")**; the **live-data path
> is the deferred follow-on**. Marked explicitly so the FR list is not over-read.

| FR | Shipped? | Note |
|----|----------|------|
| FR-1 (single-source, no-mutation Stakeholders section) | ✅ **DONE** | pure `build_kickoff_portal_spec`; CLI reads roster/transcript read-only |
| FR-3 (YAML authoritative) · FR-4 (generated dashboard, sibling builder) | ✅ **DONE** | `portal_spec.py` → `DashboardCreatorWorkflow` |
| FR-5 (a) gauge (b) per-domain (c) per-field (e) markdown | ✅ **DONE (static)** | baked `vector(N)` + markdown from `explain_input_domain` |
| FR-2 (real OTel `Meter`→Mimir producers) | ⛔ **DEFERRED** | the live metric-emit seam; panels use baked literals today |
| FR-5 (d) burndown timeseries | ⛔ **DEFERRED** | needs FR-2's history metrics |
| FR-6 (confirm-scalar write panel) | ⛔ **DEFERRED** | no `kickoff-capture-panel` (Phase-2 built a *different* panel — the stakeholders runner) |
| FR-7 (kickoff-completeness verifier + gauge) | ⛔ **DEFERRED** | completeness is computed inline (a ratio), not emitted as a verifier gauge |
| FR-8/FR-9 (pilot + verdict) | ✅ deliverables | `SPIKE_FINDINGS.md` |

**Verdict:** the shipped scope (FR-1/3/4 + static FR-5 a/b/c/e) is **complete and semantically correct**;
FR-2/5d/6/7 are the **explicitly-deferred "make the reads live" follow-on**, not delivered capability.

---

## 1. Problem Statement

The startd8 kickoff process today has two shipped surfaces — a CLI kernel (`startd8 kickoff` /
concierge) and a FastAPI+HTMX web UI with TUI parity (`kickoff_experience/web.py`, M4). Both write
kickoff inputs to per-domain YAML (`docs/kickoff/inputs/{domain}.yaml`) plus a `confirmed.yaml`
ledger, under a **CLI-sole-writer / human-privileged-mutation** principle.

We want to explore a **third presentation surface**: **Grafana dashboards as the kickoff UI**, with
the **CLI as the spine** and an **OpenTelemetry / time-series store (via ContextCore) as lightweight
persistence** for the projected kickoff state. The motivating hypotheses:

1. **Grafana-as-UI is worth testing for real.** The user has been wary of Grafana as an application
   UI. Iteration 1 exists to *validate that bet with a working artifact and an honest verdict*, not
   to commit to a full portal.
2. **Kickoff state is genuinely time-series-shaped** in the dimension that matters: *"field X captured
   at T1 as `estimate`, confirmed at T2 as `authored`, corrected at T3."* A confirmation/completeness
   **burndown over time** and a **self-monitoring completeness** view are things Grafana does natively
   and the HTMX UI does not.
3. **This is additive, not a rebuild.** ContextCore already provides an OTLP-native persistence stack
   (mutable state files + append/idempotent comms tier + OTLP export to Tempo/Mimir/Loki) and startd8
   already has a deterministic dashboard generator (`dashboard_creator/` + `startd8-mixin/`) and a
   persona-gated portal spec builder (`observability/portal_spec_builder.py`). The spike should be
   **mostly assembly of existing capability**, plus one identified gap (a non-task raw-record emit
   path in `integrations/contextcore.py`).

### The tension this spike must confront honestly

A shipped HTMX kickoff web UI **already exists**. So the question is **not** "kickoff has no UI" — it
is **"can a Grafana surface *beat or usefully complement* the HTMX one, and where?"** Grafana's honest
weakness is **input forms** (stock panels are read-oriented; rich edit needs a custom React panel
plugin + a write endpoint). Grafana's honest strength is **read/history/self-monitoring** (live
PromQL/LogQL panels, markdown text panels, time-series burndown, completeness gauges). The spike's
central output is a **go/no-go verdict**: Grafana as **PRIMARY** kickoff surface, or **COMPLEMENTARY**
(own the read/history/self-monitoring pane while HTMX stays primary for form-filling)?

### Gap table

| Component | Current State | Gap for this spike |
|-----------|---------------|--------------------|
| Kickoff persistence | YAML inputs + `confirmed.yaml` ledger; CLI-sole-writer | No OTLP/TSDB projection of kickoff state |
| ContextCore emit bridge (`integrations/contextcore.py`) | Task-span + insight emit hooks; PII redaction chokepoint | **No non-task raw-record emit path** (kickoff records aren't tasks) |
| Dashboard generation | `dashboard_creator/` + `portal_spec_builder.py` (persona-gated) | No **domain-gated** kickoff dashboard spec |
| Grafana write path | Beaver owl `contextcore-workflow-panel` prototype (action → Rabbit API) | No CLI-routed, safe-write-preserving write action for kickoff |
| Self-monitoring | ContextCore `install/verifier.py` (completeness gauges + span tree) | No kickoff-completeness verifier |
| Canonical kickoff state | `kickoff_experience/state.py` view-model (HTMX+TUI parity) | Grafana projection must derive from THIS, not a 3rd source of truth |

---

## 2. Requirements

### Persistence-projection seam (the "soften the TSDB stance" bucket)

- **FR-1 — Emit-on-write projection (TWO distinct stores).** (CRP F-3) When a kickoff input is
  captured or confirmed, the system projects the field state as **state + provenance only — NOT raw
  values** (kickoff inputs can carry sensitive text; raw values stay in YAML; redacted-value emission
  is a later opt-in via the redaction chokepoint). Because a TSDB has no random-access CRUD, the
  projection splits into two stores that must not be conflated:
  - **Current-state store — idempotent by identity.** One record per field, keyed by an **explicit
    `record_id` derived from stable identity `(project, domain, field_path)`** (NOT the default
    `now()`-based id, which is not idempotent). Re-emit overwrites in place = "update"; retract = a
    supersession payload (`retracted: true` / `superseded_by`), since the transport has no tombstone.
    This store answers "what is the current confirmation state of each field?"
  - **History store — append-only samples.** The confirmation/completeness **time-series** is
    **append-only metric samples over scrape time** (see FR-2), **never** the identity-keyed record
    store (idempotent overwrite there would destroy the very history the burndown needs). This store
    answers "how did confirmation progress over time?"

- **FR-2 — Emit producers, named per panel (NOT the GUIDANCE comms path).** (CRP F-1, F-2) The v0.3
  plan to emit `CommsKind.GUIDANCE` records is **abandoned**: `OTLPTransport.query()` *explicitly
  raises* for GUIDANCE (it is a query dead-end), and `build_transport().emit()` writes only a
  payload-less envelope span + a local JSON file — **zero Mimir metrics** — while ContextCore, not
  startd8, owns any span→gauge metric-ifier (REQ-PRO-001, out of scope). Therefore **every FR-5 panel
  must name a concrete producer that is actually queryable**:
  - **Completeness gauge + per-field/per-domain state + burndown (Mimir/PromQL panels)** ← a real
    **OTel `Meter`** emitting gauges (`kickoff_completeness_ratio`, `kickoff_field_confirmed`) via
    **OTLP `:4318` → Mimir**. This is a *different mechanism* than the comms transport.
  - **Capture/confirm event log (audit)** ← a **Loki log line** per write (LogQL-queryable), and/or a
    *queryable* comms kind (`TASK_STATE`/`INSIGHT` have TraceQL mappings; GUIDANCE does not).
  All emission routes through the **PII redaction chokepoint** (`tracking_redaction`), emits **state +
  provenance only**, and is **best-effort/non-blocking** — a projection failure never fails the CLI
  write (ContextCore REQ-STU-001/003). The emit hook still lands in `integrations/contextcore.py`
  (the gap remains), but its output is metrics + logs, not GUIDANCE records.

- **FR-3 — Single source of truth preserved.** The projected records are **derived from the canonical
  kickoff state** (`kickoff_experience/state.py` view-model) that HTMX and TUI already consume. The
  TSDB is **not** a parallel authoring path. The YAML inputs + `confirmed.yaml` ledger remain the
  authoring source of record for iteration 1.

### Presentation (deterministically generated, NOT hand-authored)

- **FR-4 — Generated kickoff dashboard.** Generate the kickoff portal dashboard via the existing
  `DashboardSpec` → `dashboard_creator/` **jsonnet path** (grafonnet, `startd8-mixin/`, UID
  `cc-portal-{project}` per house convention), using **generate-only mode** (`dry_run`/`check`) so the
  dashboard JSON is produced **with no live Grafana** ($0, deterministic → `.startd8/dashboards/`).
  **No hand-authored dashboard JSON** (the Beaver 1,140-line drifted-into-two-copies dashboard is the
  cautionary tale; also a standing house rule). Emit the spec from a dedicated module
  **`kickoff_experience/portal_spec.py`** (SHIPPED — `build_kickoff_portal_spec(state, project)`; a
  kickoff surface alongside `web.py`/`serve.py`, NOT folded into `observability/portal_spec_builder`)
  that builds the `DashboardSpec` dict **domain-gated** (the 4
  kickoff domains) — **not** a persona×domain retrofit of `portal_spec_builder.py` (see NR-8).

- **FR-5 — Read panels (each with a named producer, per FR-2).** The dashboard presents kickoff state:
  (a) overall **completeness gauge** ← Mimir gauge `kickoff_completeness_ratio`; (b) **per-domain
  status** (business-targets, observability, conventions, build-preferences) ← Mimir
  `kickoff_field_confirmed` aggregated by domain; (c) **per-field confirmation state** ← same series by
  field; (d) **confirmation-history / burndown timeseries** (the unique value HTMX lacks) ← the Mimir
  gauge over scrape time (append-only history store, FR-1); (e) **markdown `text` panels** for each
  domain's What/Why/Who ← static content baked at generation (owned by `concierge/core.py` `explain`,
  cited not restated). No panel reads a GUIDANCE record. **(Spike note:** static `vector(N)` literals
  render but are NOT live data — panels (a–d) require the FR-2 `Meter` producer to be real.)

- **FR-6 — Minimal write action via a panel (confirm an EXISTING scalar field).** (CRP F-4) Provide
  one working **write action from the dashboard**: **confirm an already-present scalar field** (writes
  the `confirmed.yaml` ledger — the currently-wired path). Scope excludes capturing *new* fields
  (`capture.py:splice_yaml_value` raises `KEY_NOT_FOUND` for absent keys) and does not conflate confirm
  (ledger) with capture (`inputs/*.yaml` edit) — they are different paths; the demo does **confirm**.
  Implement by **forking the already-built `contextcore-chat-panel`** into `kickoff-capture-panel`
  (field-selector + value + `mode`), POSTing `{project, field_path, value, mode}`. The action **MUST
  route through the CLI / a thin CLI-backed endpoint** (never writes YAML/ledger directly), inheriting
  the safe-write guarantees + CLI-sole-writer principle, reusing `kickoff_experience/serve.py`'s auth
  posture (loopback, token, CSRF/origin). **(CRP S-5:** the fork is likely **two** plugins — the panel
  **and** `contextcore-datasource` for CORS — both unsigned; see NR-10 + Plan M4.)

### Self-monitoring

- **FR-7 — Kickoff-completeness verifier.** Copy the shape of ContextCore `install/verifier.py`: a
  declarative list of kickoff "requirements" (e.g., "≥1 value prop captured", "each domain has ≥1
  confirmed field") whose checks emit a `kickoff.completeness_percent` gauge + per-requirement status
  gauges + a span tree, surfaced as a self-monitoring section of the dashboard.

### Pilot + verdict

- **FR-8 — Pilot on household (against the verified shared local stack).** Exercise the whole slice
  end-to-end against `household-o11y` (its kickoff inputs) as the acceptance fixture. **M0 is already
  satisfied** (verified 2026-07-07): a live local stack — Grafana 12.3.0 on `:3000` (SA tokens in
  `$GRAFANA_API_TOKEN`/`$GRAFANA_SA_TOKEN`), OTLP `:4317`/`:4318`, Loki `:3100`, Mimir `:9009`, Tempo
  `:3200`, canonical datasource UIDs `loki`/`mimir`/`tempo` — is running, and the
  `portal_spec_builder → dashboard_creator → provision` path is **proven here for generation +
  provisioning** (live `cc-portal-online-boutique` dashboards + the option-3 spike
  `cc-portal-kickoff-household-o11y`). **(CRP F-5: what is proven is provisioning + static-content
  render, NOT the live-metric read** — the OB/spike panels are markdown text + baked `vector(N)`
  literals; live PromQL over emitted kickoff metrics is the un-de-risked part, gated on FR-2.) We emit
  to this shared stack; household's own unbuilt `src/household_o11y` exporter is irrelevant. **No stack
  bring-up required; but a live-metric read-back must be proven in M2 before FR-6 (CRP S-2/S-3).**

- **FR-9 — Evaluation rubric + written verdict (falsifiable).** (CRP F-7) Produce a written **go/no-go**
  scored against **concrete pass-bars**, not narrative:
  | Dimension | PRIMARY bar | evidence |
  |-----------|-------------|----------|
  | write→reflect latency | < 3 s end-to-end (panel click → dashboard reflects) | measured |
  | Grafana-driven write | ≥1 successful CLI-routed write from a panel | demoed |
  | form ergonomics | ≥ HTMX baseline **on the same confirm task** | side-by-side |
  | linear 4-domain flow | completable without leaving Grafana | walkthrough |
  | accessibility | keyboard + contrast parity with HTMX | audited |
  | maintenance cost | ≤ 1 forked plugin, pinned, documented delta | commit refs |
  **Decision rule:** all bars pass → **PRIMARY**; read/history bars pass but form/flow bars fail →
  **COMPLEMENTARY** (Grafana owns read/history/self-monitoring; HTMX stays primary for forms); read
  bars fail → **NO-GO**. Evidence MUST include **≥1 real multi-timepoint capture sequence**
  (capture→confirm→correct over wall-clock) — synthetic history (OQ-6) can demo the panel but cannot
  validate whether burndown is *genuinely useful*, which is the core hypothesis.

---

## 3. Non-Requirements

- **NR-1 — Not the full portal.** Only the validation slice is in scope. No multi-page portal, no full
  per-field editing UX.
- **NR-2 — Not replacing HTMX/TUI.** The shipped kickoff web UI and TUI remain. This is exploratory.
- **NR-3 — Not migrating the source of record.** YAML inputs + `confirmed.yaml` stay authoritative;
  TSDB is a projection. (Migration is a possible *outcome* the verdict may recommend, not a scope item.)
- **NR-4 — No random-access CRUD against the TSDB.** Update = idempotent re-emit; delete = supersession.
- **NR-5 — Not a general Grafana app plugin.** At most **one focused panel plugin** if the write action
  genuinely requires it; prefer lighter mechanisms first.
- **NR-6 — Local pilot only.** No Grafana Cloud, no multi-tenant, no external exposure.
- **NR-7 — No iteration-2 build.** Iteration 2 scope is an *output* of FR-9, not built here.
- **NR-8 — No persona×domain retrofit of `portal_spec_builder.py`.** Adding a 2nd gate dimension to the
  onboarding-portal builder is moderate surgery (16 scattered gate sites) and overloads a module that
  already owns "portal." The kickoff portal uses a **separate** `kickoff_portal_spec.py` (see FR-4).
- **NR-9 — No GUIDANCE comms records for kickoff state.** (CRP F-1, revised) The v0.3 "reuse
  `CommsKind.GUIDANCE`" plan is dropped — GUIDANCE is unqueryable via OTLP. Iteration 1 uses real OTel
  **metrics** (Mimir) + optional **Loki logs**; a dedicated `CommsKind.CONFIGURATION` remains a
  deferred cross-repo follow-up only if a *queryable* comms record is later wanted (see FR-2).
- **NR-10 — Acknowledge the unsigned-plugin reconfig + shared-stack blast radius.** (CRP F-6) FR-6's
  forked panel(s) are **unsigned**, requiring `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS` + a plugin
  mount + a **Grafana restart** on the *shared* `:3000` that also hosts the `cc-portal-online-boutique`
  dashboards. This is **not** covered by "no stack bring-up required." Before M4: confirm the allow-list
  (or isolate a plugin-enabled Grafana). "M0 satisfied" refers to read/provision only, not plugin-load.

---

## 4. Open Questions

- **OQ-1 — Minimal write surface. → RESOLVED (fork `contextcore-chat-panel`).** The already-built
  input-capture React panel; the workflow-panel is trigger-only. See FR-6.
- **OQ-2 — Write endpoint home + auth. → RESOLVED.** Reuse `kickoff_experience/serve.py`'s posture
  (loopback + token + CSRF/origin), add one CLI-backed capture route; optionally proxy via the
  already-built `contextcore-datasource` to avoid browser CORS. See FR-6.
- **OQ-3 — portal_spec_builder generalization. → RESOLVED (sibling builder).** Persona×domain retrofit
  is moderate surgery; use `kickoff_portal_spec.py`. See FR-4 / NR-8.
- **OQ-4 — Signal type(s). → RESOLVED (CRP F-2).** **Mimir metric gauges** (`kickoff_completeness_ratio`,
  `kickoff_field_confirmed`) drive completeness/status/burndown (FR-5 a–d); a **Loki log** per write
  drives the audit view; **Tempo spans** only for the FR-7 verifier's span tree. **No GUIDANCE comms
  records.** See FR-2.
- **OQ-5 — Stack availability. → RESOLVED (M0 precondition).** household's stack is unbuilt; stand up a
  fixture stack (reuse SDK `docker-compose.loki-stack.yml`). See FR-8 / Plan M0.
- **OQ-6 — Burndown signal richness. → OPEN (mitigated).** A single fresh kickoff is a flat line; seed
  **synthetic confirmation history** for the demo and label it synthetic. Revisit after M5.
- **OQ-7 — PII in emitted values. → RESOLVED.** Default to emitting **state + provenance only**; raw
  values stay in YAML. Redacted-value emission (via `tracking_redaction`) is a later opt-in. See FR-1.
- **OQ-8 — Infinity read path (NEW, post-stack-verification).** The stack has an `Infinity` datasource
  (`yesoreyeram-infinity-datasource`), which can render a Grafana panel directly from a REST/JSON
  endpoint. This offers a **simpler read path for *current* state**: point an Infinity panel at the CLI's
  existing `state.json` (`kickoff_experience/serve.py`) — **no TSDB emit needed for the live-state view**.
  The TSDB projection (FR-1) is still required for **history/burndown** (Infinity has no time-series
  memory) and self-monitoring (FR-7). **Decision for M2:** evaluate Infinity-for-current-state vs
  Mimir-PromQL-for-current-state; Infinity may make the FR-5(a–c) panels cheaper while FR-5(d) burndown
  stays on Mimir. **Constraint (CRP S-4):** Infinity fetches **server-side**, and there is no standing
  read-only `state.json` endpoint today (`serve.py` binds a loopback port and can mutate). M2 must name
  a concrete source (static generated file vs standing read-only endpoint + auth) **or drop OQ-8 for
  iteration 1** and keep current-state on the Mimir producer. Resolve during M2.

---

*v0.4 — Post-CRP R1. All 7 requirements findings (F-1…F-7) ACCEPTED & applied (§0.2). The GUIDANCE
emit path was abandoned (F-1), the emit→metric producer named per panel (F-2), the persistence split
into current-state + append-only-history stores (F-3), FR-6 scoped to confirm-existing-scalar (F-4),
the "proven path" qualified to provisioning-only (F-5), unsigned-plugin blast radius acknowledged as
NR-10 (F-6), and FR-9 made falsifiable (F-7). Independently corroborated by the option-3 spike.*

---

## Appendix A — Accepted (Applied)

> CRP R1 — all 7 requirements findings accepted and applied in v0.4. Change locations in §0.2 table.

- **[F-1]** ACCEPTED → FR-2 + NR-9 rewritten (GUIDANCE abandoned; queryable metrics/logs instead).
- **[F-2]** ACCEPTED → FR-2 names a concrete producer per FR-5 panel; OQ-4 resolved.
- **[F-3]** ACCEPTED → FR-1 split into current-state (idempotent-by-identity) + append-only history.
- **[F-4]** ACCEPTED → FR-6 scoped to confirm-an-existing-scalar; confirm≠capture stated.
- **[F-5]** ACCEPTED → Reference-Audit row + FR-8 qualified to "provisioning proven, live read UNPROVEN."
- **[F-6]** ACCEPTED → NR-10 added (unsigned-plugin reconfig + shared-stack blast radius).
- **[F-7]** ACCEPTED → FR-9 given falsifiable pass-bars + decision rule + real multi-timepoint evidence.

## Appendix B — Rejected (with rationale)

_None. All 12 CRP findings (F-1…F-7, S-1…S-5) were code-grounded and accepted; 2 (F-2, F-5) were
independently confirmed by the option-3 spike._

## Appendix C — Incoming Review

_(empty — R1 triaged into Appendix A; original suggestions preserved below for provenance)_

### R1 (triaged — retained for provenance)

#### Review Round R1 (independent CRP, 2026-07-07)

- **[F-1]** (requirements) **[BLOCKER]** — *The `CommsKind.GUIDANCE` reuse (FR-2 / NR-9) breaks the OTLP read path, not just the semantics.* `OTLPTransport.query()` **explicitly raises `TransportCapabilityError` for `CommsKind.GUIDANCE`** — "OTLPTransport cannot query guidance (K8s CRD only in Phase 1)" (`ContextCore/src/contextcore/comms/otlp_transport.py:121-129`). So records emitted as GUIDANCE **can never be queried back through the OTLP/Tempo transport** — the read throws by design. The `_build_traceql` name-prefix table maps `INSIGHT`/`HANDOFF`/`TASK_STATE`/`comms.emit` but has **no queryable route for GUIDANCE** (`otlp_transport.py:200-224`). This is a functional dead-end for FR-5's read surface, on top of being a semantic overload (a GUIDANCE query anywhere else in the stack would now also surface kickoff-field records). **Proposed change:** amend FR-2/NR-9 to pick a *queryable* discriminator — either reuse `TASK_STATE`/`INSIGHT` (both have TraceQL mappings), or go metric-only (see F-2), or explicitly accept the LOCAL-file transport for reads and state that Grafana cannot natively read it. Do not ship the spike on GUIDANCE.

- **[F-2]** (requirements) **[BLOCKER]** — *The FR-2 emit seam and the FR-5 read seam do not connect; no metric producer exists.* `build_transport(mode=DUAL).emit(CommsRecord)` writes **only a thin envelope span** to Tempo carrying `record_id/kind/project_id/agent_id/schema_version` — **not** the field payload/`confirmed_state`/`provenance` (`otlp_transport.py:98-115`) — plus a local JSON file. It emits **zero Mimir metrics**. But FR-5(a) completeness gauge and FR-5(d) burndown are PromQL panels: the sibling builder's template (`portal_spec_builder.py:164`) declares a `prometheusDatasource` variable. And the documented ownership boundary says exactly this: *"startd8 writes state files and emits spans; **ContextCore reads them and OWNS the metric-ified gauges, live progress, and burndown dashboards**"* (`integrations/contextcore.py:11-18`, REQ-PRO-001). The span→gauge metric-ifier is a **separate, ContextCore-owned component not in this spike's scope**. **Proposed change:** FR-2 must either (a) *additionally* emit real OTel metric gauges via a `Meter`→OTLP `:4318`→Mimir (a different mechanism than the comms transport), or (b) FR-5 must read from Tempo (TraceQL) / Loki (LogQL) instead of Mimir PromQL. Name the concrete producer for **every** FR-5 panel.

- **[F-3]** (requirements) **[BLOCKER]** — *FR-1's "Update = re-emit the same deterministic `record_id` (idempotent overwrite)" is false as written, and it contradicts FR-5(d)/OQ-6.* `CommsRecord._derive_record_id` keys on `(kind, project_id, agent_id, timestamp_ns, payload_checksum)` with `timestamp` **defaulting to `now()`** (`transport.py:127-141`). So (i) two emits of the same field get **different** ids (different ts) → not idempotent; (ii) a state change (capture→confirm) changes the payload checksum → different id anyway. Idempotent overwrite only holds if the caller passes an **explicit** `record_id` derived from stable identity `(project, domain, field_path)`. But an identity-keyed idempotent overwrite **collapses the durable store to one record per field**, destroying the very time-series history FR-5(d) burndown and OQ-6 depend on. **Proposed change:** FR-1 must separate the two stores explicitly — *current-state* = idempotent-by-identity (one record/field), *history* = append-only metric samples over scrape time (never the comms record store) — and state the exact `record_id` input tuple.

- **[F-4]** (requirements) **[SHOULD]** — *FR-6's "capture-a-value" demo collides with `capture.py`'s existing-scalar-only constraint, and conflates two write paths.* `build_capture_plan`→`splice_yaml_value` raises `KEY_NOT_FOUND` for any dotted key **not already present** and refuses mapping/block parents (`kickoff_experience/capture.py:155-194`) — so a Grafana action capturing a *new* field will fail. Separately, **"confirm" (writes the `confirmed.yaml` ledger) and "capture" (edits `inputs/*.yaml` via `apply_capture`) are different write paths**; M4 wires only `apply_capture`. **Proposed change:** FR-6 must (a) scope the write demo to an *existing scalar* field, and (b) state whether the demo performs confirm (ledger) or capture (inputs edit) — they are not interchangeable, and only one is currently wired.

- **[F-5]** (requirements) **[SHOULD]** — *The cited "proven read path" proves provisioning, not live-metric reads.* The online-boutique portal panels are almost entirely `_text_panel` (markdown) plus `_stat_panel` with **baked-literal `vector(N)` exprs** (`portal_spec_builder.py:141, 317-318`) — not live PromQL over emitted metrics. So the Reference-Audit row "Proven `portal→dashboard_creator→provision` path" and FR-8's "already proven here" evidence **generation + provisioning**, but **not** the live time-series read that FR-5(a/d) and FR-7 hinge on — which is exactly the un-de-risked part of the bet. **Proposed change:** qualify that Reference-Audit row and FR-8 to "provisioning proven; live-metric read UNPROVEN," and add an explicit early read-path proof (one emitted record rendering in a provisioned panel) before FR-6.

- **[F-6]** (requirements) **[SHOULD]** — *Loading the unsigned forked panel contradicts "M0 needs no work" and has shared-stack blast radius.* FR-6 needs an unsigned `kickoff-capture-panel` loaded, which requires `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS` + a plugin mount + a **Grafana restart** on the *shared* Grafana 12.3.0 that also hosts the `cc-portal-online-boutique` dashboards (the OB portal uses only stock/signed panels + Infinity, so unsigned-loading is likely **not** currently enabled). FR-8's "no stack bring-up required" does not cover this reconfig. **Proposed change:** add an FR/NR acknowledging the plugin-load reconfig + shared-stack blast radius, and require confirming (or isolating) the unsigned-plugin allow-list before M4 — do not assume the live Grafana already permits it.

- **[F-7]** (requirements) **[SHOULD]** — *FR-9's rubric is not yet falsifiable/decisive.* The six dimensions are named but carry **no thresholds** separating PRIMARY vs COMPLEMENTARY vs NO-GO, so the verdict is narrative, not reproducible. **Proposed change:** for each dimension define a concrete pass bar (e.g., write→reflect latency < N s measured end-to-end; ≥1 successful Grafana-driven CLI-routed write; form-ergonomics scored against the HTMX baseline **on the same task**) plus a decision rule mapping scores→verdict. Additionally, require **at least one real multi-timepoint capture sequence** (capture→confirm→correct over wall-clock) in the evidence — synthetic history (OQ-6) can demo the panel but cannot validate whether burndown is genuinely useful, which is the core hypothesis.
