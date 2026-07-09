# Generate Dynamic Dashboards — Requirements

**Version:** 0.3 (Post-planning + lessons-hardened — ready for CRP)
**Date:** 2026-07-08
**Status:** Draft
**Prerequisite (ops, not in scope):** Grafana upgraded to **≥ 13.1** (dynamic dashboards GA in 13;
section-level variables GA in 13.1). Assumed available; the upgrade itself is NR-3.

---

## 0. Planning Insights (Self-Reflective Update)

> The v0.1 framing was "**extend** the generator to emit new dynamic constructs (conditional rendering,
> section variables, tabs)." Reading the code falsified the word *extend*: these are **new-schema
> constructs**, and the entire generator/mixin/validator/provision stack is built around the **classic**
> schema. This is a **second output target**, not an incremental addition.

| v0.1 Assumption | Planning Discovery | Impact |
|---|---|---|
| Add a few new panel constructors for conditional rendering / section vars / tabs | They are **Grafana new-schema (v2) `*Kind` constructs** — `ConditionalRenderingGroupKind`, layout kinds (`TabsLayout`/`RowsLayout`/`AutoGridLayout`), section variables on row/tab — a **different JSON shape** (`apiVersion`/`kind`/`spec`/`elements`/`layout`) than classic `panels[]` + `gridPos` + `templating` + `schemaVersion` | **FR-1**: an **additive v2 emit path**, classic path untouched (NR-1). This is the core of the work, not a footnote |
| The startd8-mixin just needs new `panels.*` constructors | `startd8-mixin/lib/dashboards.libsonnet:26` **hardcodes `schemaVersion: 39`**; layout is `withPanels` + `apply_layout` (gridPos). The mixin is structurally classic-only | **OQ-2**: emit v2 via a **Python-side emitter** (bypass jsonnet for v2) vs a parallel v2 jsonnet library — a real strategy fork the plan must decide |
| The validator will accept it | `json_validator.py:9` **requires** `{title, uid, panels, templating, schemaVersion}` and range-checks `schemaVersion` — it would **reject** a v2 dashboard | **FR-7**: the validator must become schema-aware (classic vs v2) |
| Provision is unchanged (`/api/dashboards/db`) | `grafana_client.upsert_dashboard` posts classic JSON to `/api/dashboards/db`. Whether that endpoint accepts a **v2** payload on 13.1 (vs the new `apis/dashboard.grafana.app` resource API) is **unverified** | **OQ-1**, load-bearing — gates the whole provision path; verify on the upgraded instance |
| The audience port = hide/show fields | The Workbook renders each domain as **ONE markdown text panel** with a table of fields inside. Conditional rendering acts on **panels/rows/tabs, not table rows** | **OQ-5**: to conditionally shield individual *fields* (beginner surface knob), the Workbook must render fields as **separate panels/rows** — a real structural change to `portal_spec.py` |
| Baking a dashboard per audience | With an `audience` **runtime variable** + conditional rendering, the generated JSON is **identical regardless of viewer audience** — one deterministic board, viewer-personalized | **FR-9**: strengthens determinism + the persona byte-identity guarantee; **dissolves** the read-only tension (it's a view toggle, not a write — NR-2) |

**Resolved open questions (from planning):**
- **OQ (does audience personalization break the Workbook's read-only NR-3?) → NO.** An `audience` template
  variable + conditional rendering is a pure **view toggle** (like any dashboard filter); the source of
  record (`inputs/`, `confirmed.yaml`) is untouched. Read-only holds (FR-8/FR-9, NR-2).
- **OQ (per-audience dashboards?) → NO.** One board carries all variants + rules (FR-9).

### 0.1 Lessons-Learned Hardening (v0.3)

> Consulted the SDK design-docs lessons index. Applied:

- **Phantom-reference audit** — every startd8 symbol cited is byte-verified (see §Reference Audit). The
  **Grafana v2 schema constructs** (`ConditionalRenderingGroupKind`, layout kinds, `dashboardSectionVariables`
  toggle) are **external** and named from current Grafana release notes (2026-06); treated as a
  **non-normative snapshot** to verify against the live 13.1 instance (OQ-1/OQ-3), not as settled SDK API.
- **Single-source vocabulary** — the Grafana schema is **owned by Grafana docs**; this spec cites the
  construct names and does not re-specify Grafana's schema. The `audience` model is **owned by**
  `PERSONA_EXPERIENCES_REQUIREMENTS.md` / `concierge/audience.py` — cite, don't restate (FR-8).
- **Prune phantom scope** — do **not** migrate existing classic dashboards to v2 (NR-1); the classic path
  stays the default. v2 is opt-in for boards that need dynamic behavior.
- **Overloaded-term co-location** — the v2 emit path is a **new module/target**, not new meaning bolted
  onto the classic generator functions (the plan keeps them separable).
- **CRP steering** — least-reviewed = this new capability spec + its plan. **Settled, do-not-relitigate:**
  the audience model (owned by the persona spec), the Workbook read-only stance (NR-3 there), and the
  deterministic-`$0` generation principle.

---

## 1. Problem Statement

The SDK's deterministic dashboard generator (`dashboard_creator` + `startd8-mixin`) emits **static**
Grafana dashboards (classic `schemaVersion: 39`). It cannot express the Grafana 13 **dynamic-dashboard**
constructs — **conditional rendering** (show/hide by variable/data/time), **section-level variables**
(per row/tab), and **tabs/rows layout** — that enable a *personalized* board. The immediate driver is
**audience/persona personalization** on the Digital Project Workbook: today a beginner and a veteran get
the identical dense board; with conditional rendering + an `audience` variable, one board could re-render
its prose density and field surface **live, in-browser, per viewer, with no regeneration and no write**.
The same primitives benefit other generated boards (fleet per-service filters, gov per-department
sections, o11y-artifact boards). This spec makes **dynamic-dashboard generation a first-class,
deterministic (`$0`) capability**, with the Workbook + audience feature as the first consumer.

### Gap table

| Component | Current state | Gap |
|---|---|---|
| `dashboard_creator` output | classic `schemaVersion: 39` JSON only | **add a v2 emit target (FR-1)** |
| Conditional rendering | none | **FR-2** |
| Section-level (row/tab) variables | none | **FR-3** |
| Tabs/rows layout | flat panels + gridPos (`apply_layout`) | **FR-4** |
| Validation | classic-only (`json_validator` requires classic keys) | **schema-aware (FR-7)** |
| Provisioning | `POST /api/dashboards/db` (classic) | **verify/support v2 (FR-6, OQ-1)** |
| Workbook personalization | one dense board for everyone | **audience variable + rules (FR-8/FR-9)** |

---

## 2. Requirements

- **FR-1 — Additive v2 (new-schema) emit target.** The generator MUST gain a Grafana **v2 dynamic-schema**
  output target (`apiVersion` + `kind` + `spec{elements, layout, variables}`) **without removing or
  regressing the classic path**. A `DashboardSpec` opts into v2 (explicit `schema="v2"` and/or the
  presence of any dynamic construct — decided in the plan). Classic remains the default (NR-1).
- **FR-2 — Conditional rendering.** A spec MUST be able to attach show/hide rules to **panels, rows, and
  tabs**, with condition types **variable-value** (`equals|notEquals|matches|notMatches`), **data-presence**,
  and **time-range-size**, combinable with **AND/OR**. Compiles to Grafana's conditional-rendering group.
- **FR-3 — Section-level variables.** A spec MUST be able to declare variables **scoped to a row or tab**;
  panels in that section resolve section-first then dashboard-fallback, other sections unaffected
  (shared time range). Requires Grafana's `dashboardSectionVariables` (GA 13.1, OQ-3).
- **FR-4 — Tabs/rows layout.** A spec MUST express a **tabs and/or rows** layout (nesting allowed),
  mapping to the v2 layout kinds; auto-grid vs custom layout selectable.
- **FR-5 — Deterministic + `$0`.** All v2 output MUST be deterministic (no LLM, sorted-key stable bytes),
  matching the classic path's guarantees.
- **FR-6 — Provisioning parity.** The provision path MUST publish a v2 board to Grafana ≥13.1 with the
  same UID / idempotent-upsert semantics as classic — via `/api/dashboards/db` **if it accepts v2**, else
  the new dashboard resource API (OQ-1). A provision that the target can't accept MUST fail loud, not
  produce a broken board.
- **FR-7 — Schema-aware validation.** Validation MUST accept the v2 shape (not require classic
  `panels`/`templating`/`schemaVersion`) and validate the v2 required keys + construct well-formedness;
  classic validation is unchanged for classic specs.
- **FR-8 — Audience personalization on the Workbook (first consumer).** The Workbook gains an `audience`
  dashboard variable (custom: `beginner|intermediate|advanced`; **default = `resolve_audience_preference()`**
  for the project) and conditional-rendering rules realizing the persona lens: **disclosure** (intro/prose
  variant per tier) and **surface** (hide/collapse the `AUDIENCE_PROFILES`-shielded fields for beginner).
  The `audience` model + tiers + profiles are **owned by** the persona feature — cited, not re-specified.
- **FR-9 — One deterministic board per project, viewer-personalized.** The Workbook board carries **all**
  persona variants + the rules; `audience` is a **runtime variable**, so the generated JSON is **identical
  regardless of the viewer's audience** (no per-audience UIDs; strengthens the persona byte-identity
  guarantee). Switching `audience` re-renders **in-browser**, no regeneration, **no write** (read-only,
  NR-2).
- **FR-10 — Additive spec model.** The dynamic constructs extend `DashboardSpec`/`PanelSpec` with **new
  optional fields** (e.g. per-element `conditional`, section `variables` on a row/tab element, a `layout`
  descriptor); existing specs + consumers (portal_spec, observability, dbrd) are untouched until they opt
  in.
- **FR-11 — Graceful version handling.** If the target Grafana is `< 13.1` (or the section-variables
  capability is off), generation/provision MUST **detect and message clearly** (refuse, or emit a classic
  fallback — OQ-4), never silently ship a board the target renders broken.

---

## 3. Non-Requirements

- **NR-1 — No migration of existing classic dashboards to v2.** Static boards stay classic (the default);
  v2 is opt-in for boards that need dynamic behavior.
- **NR-2 — No writes from the dashboard.** The `audience` variable (and any dynamic control) is a **view
  toggle**; the Workbook stays **read-only** (Workbook spec NR-3). No dashboard-native confirm.
- **NR-3 — Not the Grafana upgrade.** Upgrading the instance to ≥13.1 is an ops prerequisite, out of scope.
- **NR-4 — No per-user server-side personalization.** No Grafana per-user default-variable-values / user
  preference plumbing; personalization is the `audience` variable + its project default (FR-8).
- **NR-5 — No gold-plating the jsonnet mixin.** If a Python-side v2 emitter is cleaner (OQ-2), do not port
  the entire Grafana v2 schema into `startd8-mixin`.
- **NR-6 — Not a full Grafana-schema library.** Support only the constructs FR-2/3/4 (+ what the Workbook
  and the named other boards need), not every v2 feature.

---

## 4. Open Questions

- **OQ-1 — Provision API for v2.** Does `POST /api/dashboards/db` accept a v2 (`apiVersion`/`kind`) payload
  on Grafana 13.1, or is the new resource API (`/apis/dashboard.grafana.app/...`) required? *(Verify on the
  upgraded instance — load-bearing for FR-6.)*
- **OQ-2 — Emit strategy.** Extend the jsonnet mixin with a v2 library, or emit v2 JSON **directly from
  Python** (bypass jsonnet for v2, reuse the PanelSpec→element mapping)? The mixin is deeply classic;
  Python emit may be far simpler. *(Plan decides.)*
- **OQ-3 — Section-variables enablement.** Is `dashboardSectionVariables` on by default on self-managed
  13.1, or must the feature toggle be set? *(Verify; note the known limitation: a section variable can't
  reference another section variable in the same tab — Grafana issue #122553.)*
- **OQ-4 — Degradation policy (FR-11).** On Grafana `<13.1`: refuse with a clear error, or emit a classic
  fallback board (losing the dynamic behavior)?
- **OQ-5 — Workbook field granularity.** To conditionally shield individual *fields* (FR-8 surface knob),
  the Workbook must render fields as **separate panels/rows** rather than one markdown table per domain —
  a structural change to `portal_spec.py`. Is per-field granularity required for v1, or is a coarser
  "collapse the shielded-fields section for beginner" (a row-level rule) enough?
- **OQ-6 — Disclosure depth.** Does FR-8's disclosure need `explain_input_domain` to gain **tiers** (for
  per-domain prose variants), or is **intro-panel disclosure only** enough for v1? *(`explain_input_domain`
  has no tier param today.)*
- **OQ-7 — Scope of the first cut.** Ship the generator v2 capability **broadly** (conditional rendering +
  section vars + tabs, usable by fleet/gov/o11y), or **Workbook-audience-first** (only the constructs the
  audience port needs) and generalize after? *(Affects milestone ordering.)*

---

## Reference Audit (startd8 symbols — byte-verified; Grafana constructs = external snapshot)

| Symbol / fact | Location | Verified |
|---|---|---|
| classic `schemaVersion: 39` hardcoded | `startd8-mixin/lib/dashboards.libsonnet:26` | ✅ |
| validator requires classic keys | `dashboard_creator/json_validator.py:9` (`{title,uid,panels,templating,schemaVersion}`) | ✅ would reject v2 |
| `DashboardSpec` fields (panels/variables/links/…) | `dashboard_creator/models.py:254` | ✅ additive extension point (FR-10) |
| `PanelType` enum (+ `ROW`,`TEXT`,`DASHLIST`) | `dashboard_creator/models.py:14` | ✅ |
| gridPos layout | `dashboard_creator/layout.py`, `generator.py:425` | ✅ classic-only |
| provision `POST /api/dashboards/db` | `dashboard_creator/grafana_client.py:114` | ✅ classic path (OQ-1 for v2) |
| Workbook = one markdown panel per domain | `kickoff_experience/portal_spec.py` `_manifest_section` | ✅ (OQ-5) |
| `audience` model / tiers / profiles | `concierge/audience.py` (`KickoffAudience`, `disclosure_tier`), `manifest.py` `AUDIENCE_PROFILES` | ✅ owned by persona spec |
| Grafana v2 constructs / `dashboardSectionVariables` | Grafana release notes 2026-06 (external) | ⚠ non-normative snapshot — verify on live 13.1 (OQ-1/3) |

---

*v0.3 — Post-planning + lessons hardening. The "extend the generator" framing collapsed to a **second
(v2) emit target** (FR-1, the core); conditional rendering / section vars / tabs specced against the
external Grafana schema (verify-on-upgrade OQs); audience personalization reframed as a runtime variable
that **dissolves** the read-only tension and strengthens determinism (FR-8/FR-9). Surfaced the Workbook
one-panel-per-domain structural snag (OQ-5). Ready for CRP.*
