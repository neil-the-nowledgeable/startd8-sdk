# Generate Dynamic Dashboards — Requirements

**Version:** 0.4 (Post-CRP R1/R2 triage — ready for M0 spike)
**Date:** 2026-07-09
**Status:** Draft (CRP R1/R2 triaged; M0 spike is the next action)
**Prerequisite (ops, not in scope):** Grafana upgraded to **≥ 13.1** — **DONE (13.1.x)**. (Dynamic
dashboards GA in 13; section-level variables GA in 13.1.) The upgrade itself is NR-3.

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
  regressing the classic path**. A `DashboardSpec` opts into v2 by an **explicit, single trigger:
  `schema="v2"`** (R1-F2) — **not** the mere presence of a dynamic construct. A classic spec that carries a
  v2-only field MUST raise a validation error, never silently flip schema. Classic remains the default
  (NR-1). *(Note: `DashboardSpec.panels = Field(min_length=1)` (`models.py:266`) must be relaxed for v2 —
  a pure-tabs/rows board has zero flat panels; see plan M1/R1-S9.)*
- **FR-2 — Conditional rendering.** A spec MUST be able to attach show/hide rules to **panels, rows, and
  tabs**, with condition types **variable-value** (`equals|notEquals|matches|notMatches`), **data-presence**,
  and **time-range-size**, combinable with **AND/OR**. Compiles to Grafana's conditional-rendering group.
- **FR-3 — Section-level variables.** A spec MUST be able to declare variables **scoped to a row or tab**;
  panels in that section resolve section-first then dashboard-fallback, other sections unaffected
  (shared time range). Requires Grafana's `dashboardSectionVariables` (GA 13.1, OQ-3). **The same-tab
  cross-reference limitation (Grafana #122553) MUST be a build-time validation error (R1-F6):** a section
  variable referencing another section variable in the same tab is rejected at build, never a
  silently-broken render (this realizes FR-11's "never ship broken" intent at the spec level).
- **FR-4 — Tabs/rows layout.** A spec MUST express a **tabs and/or rows** layout (nesting allowed),
  mapping to the v2 layout kinds; auto-grid vs custom layout selectable.
- **FR-5 — Deterministic + `$0`.** All v2 output MUST be deterministic (no LLM, sorted-key stable bytes),
  matching the classic path's guarantees.
- **FR-6 — Provisioning parity.** The provision path MUST publish a v2 board to Grafana ≥13.1 with the
  same UID / idempotent-upsert semantics as classic — via `/api/dashboards/db` **if it accepts v2**, else
  the new dashboard resource API (OQ-1). A provision that the target can't accept MUST fail loud, not
  produce a broken board. **The chosen endpoint MUST be observable (R1-F3):** the `ProvisioningResult`
  records which API accepted the payload (`details["provision_api"]`) so OQ-1's answer is captured in
  artifacts. A v2 UID that collides with an in-use **classic** board MUST be refused/namespaced, never a
  silent `overwrite:True` clobber (R1-S8).
- **FR-7 — Schema-aware validation.** Validation MUST **discriminate schema first** (`apiVersion` present →
  v2; absent → classic) **before** any classic-specific check (R2-F3/R2-S4) — today the `schemaVersion`
  range-check at `json_validator.py:69` fires on a v2 board (key absent → `None not in range(36,42)` =
  `True`). The v2 path **positively asserts** `apiVersion`/`kind`/`spec` present + `spec.elements` is a
  list, does **not** run the classic UID/panel-count branch (`json_validator.py:76-93`), and **rejects any
  v2 `kind` outside the NR-6 allowlist** (R1-F7). Classic validation is unchanged for classic specs.
- **FR-8 — Audience personalization on the Workbook (first consumer).** The Workbook gains an `audience`
  dashboard variable (**`type: custom`, a fixed enumerated allowlist `beginner|intermediate|advanced` —
  never a query/datasource variable**, R1-F8, since it gates shielded-field disclosure; default =
  `resolve_audience_preference(project_root).value.value`, the token — the function returns an
  **`AudienceResolution`** with a `.value` `KickoffAudience` enum (**not** `.audience`) and defaults to
  **Intermediate**, R1-F4). Conditional-rendering rules realize the persona lens: **disclosure** (intro/
  prose variant per tier) and **surface** (collapse the `AUDIENCE_PROFILES`-shielded fields for beginner).
  **Era 1 coexistence (R2-F1):** Era 1 (shipped, `3f86b72c`) renders each domain as ONE `text` panel with
  a per-row 🛡️ badge; the v2 surface knob acts on panels/rows, not table rows. The contract: shielded
  fields move to a **separate collapsible subsection** hidden for beginner (only shielded fields collapse,
  not the whole domain), and the static badge is **retained** on the non-beginner render (orthogonal
  mechanisms: bake-time label vs runtime show/hide). Era 1's `build_kickoff_portal_spec` signature
  (`audience`/`tier`/`provenance`) MUST survive the v2 migration (R2-F5). The `audience` model + tiers +
  profiles are **owned by** the persona feature — cited, not re-specified.
- **FR-9 — One deterministic board per project, viewer-personalized.** The Workbook board carries **all**
  persona variants + the rules; `audience` is a **runtime variable**, so the generated JSON is **identical
  regardless of the viewer's audience** (no per-audience UIDs; strengthens the persona byte-identity
  guarantee). **Byte-identity AC (R1-F5):** regenerating under beginner/intermediate/advanced project
  defaults yields the same bytes **except the `audience` variable's `current` default** — a golden diff
  pins exactly that invariant. Switching `audience` re-renders **in-browser**, no regeneration, **no write**
  (read-only, NR-2). *(Grafana persists variable state to the URL/last-used; a shared link can pin an
  audience — this is still not a write to `inputs/`/`confirmed.yaml`, so read-only holds, R1-F9.)*
- **FR-10 — Additive spec model.** The dynamic constructs extend `DashboardSpec`/`PanelSpec` with **new
  optional fields** (e.g. per-element `conditional`, section `variables` on a row/tab element, a `layout`
  descriptor); existing specs + consumers (portal_spec, observability, dbrd) are untouched until they opt
  in.
- **FR-11 — Graceful version handling.** If the target Grafana is `< 13.1` (or the section-variables
  capability is off), generation/provision MUST **detect and message clearly** (refuse, or emit a classic
  fallback — OQ-4), never silently ship a board the target renders broken. **AC (R1-F1/R1-S3):** detection
  MUST gate on the **13.1 minor / capability**, not the major version — the shipped `check_version()`
  parses only the major (`grafana_client.py:91`) and cannot tell 13.0 from 13.1 (the exact section-var GA
  boundary). Use a minor/capability probe (`/api/frontend/settings` toggles or a resource-API HEAD) read
  against the M0-captured `verified_on` baseline; given a 13.0 target, generation of a section-variable
  board MUST be refused/downgraded (test: mock `/api/health` → `13.0.x` → refuse fires).

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
  and the named other boards need), not every v2 feature. **Enforced (R1-F7):** the v2 validator raises on
  any v2 `kind` outside the M0 construct allowlist (`v2-construct-names.json`) — scope creep is caught, not
  silently emitted as unvalidated JSON.

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

*v0.4 — Post-CRP triage (R1 opus + R2 sonnet, 14 F-suggestions, all accepted; 2 qualified). FR-1 single
opt-in trigger + `panels min_length=1` note; FR-3 same-tab #122553 build-time rule; FR-6 observable
provision endpoint + cross-schema UID guard; FR-7 schema-discriminator-first (the `json_validator` v2
blocker) + NR-6 allowlist enforcement; FR-8 corrected `AudienceResolution.value`/Intermediate default +
custom-allowlist safety + the Era 1 🛡️-badge coexistence contract + caller-interface stability; FR-9
byte-identity AC + URL-state note; FR-11 minor/capability gating. Dispositions in Appendix A. Grafana
≥13.1 now met — M0 spike is the next action.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) add suggestions to Appendix C; once validated, the orchestrator records the final disposition in Appendix A (applied) or Appendix B (rejected with rationale). **Do not delete A/B** — they are the cross-model memory that stops later reviewers from re-proposing settled or rejected ideas.

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append a `#### Review Round R{n}` block under Appendix C (n = highest existing round + 1, or 1), with unique suggestion IDs `R{n}-S{k}` (plan) / `R{n}-F{k}` (requirements).
- **When endorsing prior suggestions**: If you agree with an untriaged item from a prior round, list it in an **Endorsements** section instead of restating it. Multi-reviewer endorsements raise triage priority.
- **When validating (orchestrator)**: For each suggestion, append a row to Appendix A (applied) or Appendix B (rejected) referencing the suggestion ID.
- **If rejecting**: Record **why** (specific rationale) so future reviewers don't re-propose the same idea.

### Appendix A: Applied Suggestions

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| (none yet) |  |  |  |  |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-09

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-09 04:10:00 UTC
- **Scope**: Requirements quality for the v2-schema fork (FR-1), provision path (OQ-1/FR-6), version handling (FR-11), and the Workbook audience consumer (FR-8/9). Findings grounded against the live `dashboard_creator/` code and `startd8-mixin`.

**Executive summary (top risks / gaps in the requirements text):**
- FR-11's "detect and message clearly" is untestable as written: the existing `grafana_client.check_version()` parses **only the major** version (`int(version_str.split(".")[0])`, `grafana_client.py:91`) — it cannot distinguish 13.0 from 13.1, yet section-vars GA is 13.1. FR-11 needs a minor/capability acceptance criterion.
- FR-1's opt-in trigger is left "decided in the plan" (`explicit schema="v2" and/or the presence of any dynamic construct`). Two triggers = ambiguity: a classic spec that happens to set one new optional field could silently flip schema. Requirement should pin the disambiguation rule.
- FR-6 conflates two provision outcomes ("`/api/dashboards/db` if it accepts v2, else resource API") without an acceptance criterion for *how the code chooses* — the branch is unspecified and untestable until OQ-1 resolves.
- FR-8 cites `resolve_audience_preference()` as the default source but the function returns an `AudienceResolution` object (not a bare audience) and is currently wired only into `web.py`/`concierge_view.py`, **not** `portal_spec.py` (`_manifest_section`). The requirement understates the integration surface.
- FR-9's "identical regardless of viewer audience" byte-identity claim has no stated verification method; determinism (FR-5) has a golden but the persona byte-identity guarantee (FR-9) has none specified.
- No requirement covers **datasource/variable interpolation determinism** for v2 `variables` scoped to a section (FR-3) — section-first-then-fallback resolution is a behavior with no acceptance test.

**Feature Requirements Suggestions (F-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F1 | Validation | high | Rewrite FR-11 to require **minor-version or capability** detection (e.g. GET `/api/health` major-only is insufficient; use `/api/frontend/settings` or a resource-API probe for `dashboardSectionVariables`), and add an AC: "given a 13.0 target, generation of a section-variable board is refused/downgraded." | `grafana_client.check_version()` (`grafana_client.py:91`) only reads the major version; 13.0 vs 13.1 is exactly the boundary FR-11 must guard, so FR-11 is untestable against the shipped client. | FR-11 | Unit test: mock `/api/health` returning `13.0.x`; assert refuse-or-fallback fires. |
| R1-F2 | Interfaces | high | Make FR-1's v2 opt-in trigger **single and explicit** (`schema="v2"` only) rather than "and/or presence of any dynamic construct", OR state a precedence rule + a validation error when a classic spec carries a v2-only field. | Dual triggers create a silent-mode-flip hazard: a consumer adding one optional `conditional` field to an intended-classic spec could change the emit schema and break `json_validator` (`_REQUIRED_KEYS`, `json_validator.py:9`). | FR-1, sentence "A `DashboardSpec` opts into v2…" | Test: classic spec + one dynamic field → assert explicit error or documented schema, never a silent v2 emit. |
| R1-F3 | Interfaces | medium | FR-6: add an AC that the **provision-API selection is observable** — e.g. the ProvisioningResult records which endpoint (`/api/dashboards/db` vs resource API) accepted the payload, so OQ-1's answer is captured in artifacts, not just M0 notes. | `provision_dashboard` (`provisioning.py:64`) currently only knows one endpoint; FR-6 must specify the branch's contract and make it auditable. | FR-6 | Assert `ProvisioningResult.details["provision_api"]` is set on a v2 upsert. |
| R1-F4 | Data | medium | Correct FR-8's citation: `resolve_audience_preference(project_root, flag)` returns an `AudienceResolution` (has `.audience` + `.source`), and its default is **Intermediate** (`DEFAULT_AUDIENCE`), not "beginner". State that the dashboard variable default = `resolve_audience_preference(project_root).audience`. | Grounding: `concierge/audience.py:115`. As written, FR-8 implies a bare-string return and doesn't name the Intermediate default, so the variable's default value is ambiguous. | FR-8, "default = `resolve_audience_preference()`" | Read `audience.py`; assert the default variable value equals the resolved `.audience`, source-tagged. |
| R1-F5 | Validation | medium | FR-9: add an explicit **byte-identity acceptance criterion** — a golden that regenerating the Workbook board under three different `resolve_audience_preference` results (beginner/intermediate/advanced project defaults) yields **the same file bytes except the variable's `current` default**. | FR-9 claims JSON "identical regardless of viewer audience" but the *default* still varies by project; the requirement must state which bytes are invariant vs which (the current-value) legitimately differ, else the persona byte-identity guarantee is unverifiable. | FR-9 | Golden diff across three project defaults; only the `audience` variable `current` differs. |
| R1-F6 | Data | medium | FR-3: specify the **section-first-then-dashboard-fallback resolution** as a testable behavior and record the known Grafana limitation (issue #122553: a section variable can't reference another section variable in the same tab) as a **hard constraint the emitter must reject at build time**, not just an OQ-3 note. | The limitation currently lives only in OQ-3/plan M4; if it's not a build-time validation rule it will surface as a silently-broken board at render, violating FR-11's "never silently ship broken" intent. | FR-3 (add AC) and/or FR-7 | Test: a spec with same-tab section-var cross-reference → build-time validation error. |
| R1-F7 | Risks | low | NR-6 ("support only FR-2/3/4 constructs") lacks an enforcement hook: state that an unsupported v2 construct in a spec MUST raise, so scope creep is caught, not silently emitted as unvalidated JSON. | Without this, FR-7's schema-aware validator could pass through arbitrary v2 keys, defeating NR-6 and hiding drift against the 2026-06 external snapshot. | NR-6 / FR-7 | Test: spec with an out-of-scope v2 kind → validation error naming the construct. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-F8 | Security | medium | Add a requirement that the `audience` variable is a **fixed custom allowlist** (`beginner\|intermediate\|advanced`) and NOT a query/datasource variable, so a viewer cannot inject an arbitrary value that dodges the shielding rules (FR-8 "surface" knob). | FR-8/FR-9 treat audience as a pure view toggle, but if the shielded-field visibility is driven by `audience == …` conditional rules, an unconstrained variable value is effectively a client-side authorization control. The read-only stance (NR-2) doesn't cover *disclosure* of shielded fields. | FR-8 / NR-2 | Assert the emitted variable is `type: custom` with an enumerated options list; no free-text/query source. |
| R1-F9 | Risks | low | Clarify FR-9's "no write" boundary: Grafana **persists variable state to the URL / user's last-used**, so a shared link can pin an audience. State whether that is acceptable (it's still not a write to `inputs/`/`confirmed.yaml`) to preempt a false "read-only violated" reading in later review. | Pre-empts relitigation of the settled read-only stance while acknowledging Grafana's real URL-state behavior. | FR-9 / NR-2 | Doc note; manual check that URL var-state does not write project source of record. |

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-09

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-09 00:00:00 UTC
- **Scope**: Focus areas assigned for R2: (a) external-schema version fragility and M0 spike construct-name capture; (b) M0 as a decisive experiment; (c) OQ-5 / FR-8/FR-9 composition with the shipped Era 1 structure; (d) testing/validation strategy for a v2 emitter without a live 13.1 instance in CI. Grounded against `dashboard_creator/{json_validator,grafana_client,output,models}.py`, `startd8-mixin/lib/dashboards.libsonnet`, and `kickoff_experience/portal_spec.py` (main branch + `feat/workbook-audience-personalization` Era 1 commit `3f86b72c`).

**Executive summary:**
- The Era 1 `_manifest_section` in `feat/workbook-audience-personalization` (`3f86b72c`) is still **one `text` panel per domain** — every field in that domain is a row in a single Markdown table. FR-8/FR-9's `audience == 'beginner'` conditional-rendering rule would toggle the whole panel, not individual rows. The coarse-row-collapse path in OQ-5 correctly identifies the mismatch, but the requirement (FR-8 "surface" knob) does not state what the "coarse" path actually guarantees vs. what Era 1 already ships — a reader cannot tell whether Era 2 is a meaningful addition to Surface or is replacing the badge with a different mechanism.
- FR-8's reference to the 🛡️ badge (Era 1, `_AUDIENCE_DEFAULT_DISPLAY`) is zero. The badge is a static bake-time label; the Era 2 conditional-rendering rule is a runtime show/hide of a row. These operate on orthogonal mechanisms and the requirement does not specify their coexistence contract.
- The M0 spike hands off a "de-risking note + canonical v2 JSON envelope" (Plan §M0 "Output:") but specifies no structured schema for that artifact — no one can programmatically diff it against a later construct-name change in a 13.1.x minor.
- FR-7's `validate_dashboard_json` (`json_validator.py:9`) in the v2 path must not call into the panel-count branch at all (`_SUPPORTED_SCHEMA_VERSIONS` range-check would also need a bypass). The current code at line 69 range-checks `schemaVersion` against `range(36,42)` — a v2 board has no `schemaVersion` key, so that check currently passes silently (key absent → `None` → not-in-range evaluates False). FR-7 needs a positive acceptance criterion for the v2 `apiVersion`/`kind` keys, not just "don't require classic keys."
- No requirement specifies **how to test a v2 emit without a live Grafana 13.1**: the golden in FR-5/M1 pins byte-stability of the emitter's output, but there is no requirement for a structural conformance fixture (a snapshot of the real v2 schema) that CI can validate against without network access.

**Feature Requirements Suggestions (F-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | high | FR-8's "surface" knob must explicitly state the **coexistence contract between the Era 1 🛡️ badge and the Era 2 conditional-rendering row-collapse**: does the v2 version replace the static badge with a dynamic row, or do both coexist (badge within the row, row hidden for beginner)? Without this, M6 has two plausible and incompatible implementations. | Era 1 (`3f86b72c`, `_manifest_section`) bakes a 🛡️ glyph into the Markdown table row for audience-default-shielded fields. Era 2 would hide an entire row (or panel) for `audience == 'beginner'`. The requirement says "hide/collapse the `AUDIENCE_PROFILES`-shielded fields" — but in the one-panel-per-domain structure, hiding the panel hides ALL fields in that domain, not just the shielded ones. The requirement must specify granularity. | FR-8, "surface (hide/collapse the `AUDIENCE_PROFILES`-shielded fields for beginner)" | Test: a board with a domain containing both shielded and unshielded fields; assert only the shielded row/section is hidden, not the full domain panel. |
| R2-F2 | Validation | high | Add a **CI-testable structural conformance strategy for v2 emit** without a live Grafana instance: require M0 to produce a committed JSON Schema (or a minimal fixture) for the v2 envelope, and require the v2 emitter's output to validate against it in unit tests. | FR-5 (determinism golden) pins byte-stability but not structural correctness. Without a schema fixture from M0, CI cannot distinguish a well-formed v2 board from one that has a typo in `ConditionalRenderingGroupKind` — the test would pass but Grafana 13.1 would reject it. The Grafana v2 schema is already treated as a non-normative snapshot (§0.1 Reference Audit); a committed JSON Schema fixture operationalizes that posture. | FR-5 / FR-7, and the Reference Audit "non-normative snapshot" note in §0.1 | Unit test: `validate_dashboard_json` (v2 branch) asserts `apiVersion`/`kind`/`spec` are present and `spec.elements` is a list; structural fixture checked in from M0. |
| R2-F3 | Interfaces | medium | FR-7 needs a positive acceptance criterion for v2 required keys, not just "don't require classic keys": the shipped `json_validator.py:69` range-checks `schemaVersion` against `range(36,42)`; a v2 board has no `schemaVersion`, so the check passes silently (key absent → `None`). The validator must **positively assert** `apiVersion` and `kind` are present for a v2 board, and assert `schemaVersion` is absent (or ignored) — a passive absence-of-classic-keys check is not equivalent. | Grounding: `json_validator.py:9-10` — `_REQUIRED_KEYS` and `_SUPPORTED_SCHEMA_VERSIONS = range(36,42)`. The absence of `schemaVersion` in a v2 board currently causes line 69's check to evaluate `None not in range(36,42)` which is `True` — an **error** fires even before the missing-keys check. The validator needs a schema-discriminator first. | FR-7, "validate v2 required keys + construct well-formedness" | Test: pass a v2-shaped dict to `validate_dashboard_json`; assert no `schemaVersion`-range error fires; assert `apiVersion` and `kind` are checked. |
| R2-F4 | Risks | medium | The Reference Audit marks Grafana v2 construct names as "⚠ non-normative snapshot — verify on live 13.1 (OQ-1/3)" but provides no mechanism to detect a rename in a future 13.1.x minor. Require M0 to **commit a construct-name map** (e.g. `docs/design/dynamic-dashboards/v2-construct-names.json`) that names the verified values of `apiVersion`, layout kinds, and `dashboardSectionVariables` so a 13.1.x patch rename is a one-liner diff, not silent breakage. | The plan names this risk ("M0 pins them") but the plan's M0 output is a prose "de-risking note" plus the emitter's JSON skeleton. Neither is a diffable artifact with a clear update protocol. R1-S10 (adversarial pass, plan file) proposes the construct-name map for the plan; this F-prefix extends it as a requirements-level artifact commitment. | §Reference Audit, "⚠ non-normative snapshot" row; cross-reference R1-S10 (plan) | Artifact checked in after M0; emitter imports/references it rather than hardcoding names inline. CI diff: `git diff` on the file flags any post-M0 rename. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F5 | Architecture | medium | Pressure-test FR-10 ("additive spec model, existing specs untouched until they opt in") against the Era 1 `build_kickoff_portal_spec` signature (branch `feat/workbook-audience-personalization`): the Era 1 function already adds `audience`, `tier`, `provenance` keyword params to `build_kickoff_portal_spec`. When M6 migrates this to v2, those params must survive the refactor. FR-10's "untouched" guarantee must explicitly cover the **caller interface** of `build_kickoff_portal_spec`, not just `DashboardSpec` fields. | If M6 changes `portal_spec.py` to use v2 constructs and the caller interface changes (e.g. `DashboardSpec.schema="v2"` replaces the current dict-based spec), the `portal_build.py` caller (which resolves audience+ledger and passes `provenance`) must be updated in lockstep. FR-10's "untouched" guarantee is a `DashboardSpec` model guarantee, not a `portal_spec.py` API guarantee. | FR-10, "existing specs + consumers (portal_spec, observability, dbrd) are untouched until they opt in" | Test: `portal_build.py` compiles without modification when `portal_spec.py` migrates to v2 output; the public signature of `build_kickoff_portal_spec` is stable. |

**Endorsements** (prior untriaged R1 suggestions this reviewer agrees with):
- R1-F1: Endorse strongly — `grafana_client.check_version()` at line 91 confirmed to parse major only; 13.0 vs 13.1 boundary is a real and testable gap.
- R1-F2: Endorse — the dual opt-in trigger ("schema='v2' and/or presence of any dynamic construct") is genuinely ambiguous; confirmed `DashboardSpec.panels = Field(min_length=1)` at `models.py:266` makes the ambiguity worse (R1-S9 in the plan).
- R1-F6: Endorse — the same-tab cross-ref limitation (#122553) is currently only a plan note (M4); it must be a build-time validation rule to satisfy FR-11's "never silently ship broken."
- R1-F8: Endorse — grounded: the Era 1 branch already gates on `type: custom` with enumerated options (via `AUDIENCE_PROFILES` keys); the v2 emitter must carry the same constraint forward. The `VariableType.CUSTOM` enum value in `models.py:55` is the right type to mandate.

**Disagreements** (prior untriaged R1 suggestions this reviewer would reject or qualify):
- R1-F9 (Grafana URL state): qualify rather than reject — Grafana's URL-bar persistence is read-only from the SDK's perspective; the requirement note is accurate but not load-bearing. The concern is real but low-severity; a single sentence in FR-9 suffices rather than a full AC.
