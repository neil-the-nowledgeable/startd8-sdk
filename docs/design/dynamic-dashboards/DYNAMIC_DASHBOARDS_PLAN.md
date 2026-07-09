# Generate Dynamic Dashboards — Plan

**Version:** 1.1 (post-CRP R1/R2 triage; tracks requirements v0.4)
**Date:** 2026-07-09
**Requirements:** `DYNAMIC_DASHBOARDS_REQUIREMENTS.md`

The work is a **second (v2) emit target** alongside the untouched classic path, proven end-to-end on the
Workbook. Two strategy forks are resolved by an up-front spike (M0) before building.

---

## M0 — Spike on the upgraded Grafana (resolves OQ-1, OQ-3) — ✅ **DONE (2026-07-09, verdict GO)**
> Executed on live Grafana **13.1.0**. **OQ-1 GO** (both `/api/dashboards/db` and the resource API accept
> v2 with round-trip fidelity; resource API recommended). **OQ-2** Python-side emitter confirmed (plain
> JSON). **OQ-3** `dashboardSectionVariables` + `dashboardNewLayouts` ON; tab-scoped section variable
> round-tripped. Composite board (tabs + conditionalRendering + section var + embedded Panel) validated.
> Artifacts + full write-up: **`m0-spike/`** (`M0_SPIKE_FINDINGS.md`, `v2-envelope.golden.json`,
> `v2-envelope-schema.json`, `v2-construct-names.json`). M1 is unblocked.

- **Composite board (R2-S6/R1-S7):** hand-author ONE v2 dashboard that nests **all three FR-2/3/4
  constructs simultaneously** — a `TabsLayout` tab → `RowsLayout` row → a **section variable** on the row,
  a **conditional-rendering rule** on the tab (`variable == 'x'`), AND **one existing classic panel dict
  embedded inside a v2 element** (proves the PanelSpec→`elements` mapping, folding R1-S7). Individual
  constructs would miss interaction effects (e.g. a section var inside a conditionally-hidden tab).
- **Verify the provision API (OQ-1)** and record the outcome in the **go/no-go decision matrix** below
  (R1-S1/R2-S3) — not prose. Capture the exact accepted payload envelope.

  | OQ-1 outcome | Downstream delta | Decision |
  |---|---|---|
  | `POST /api/dashboards/db` accepts v2 | M5 extends the classic client path | **GO** |
  | resource API (`/apis/dashboard.grafana.app/...`) required | M5 gains `grafana_client.provision_v2()` (+est.) | **GO (rescoped)** |
  | neither accepts v2 on this 13.1.x build | file an upstream issue; **defer M1–M6** | **NO-GO / STOP** |

- **Decide OQ-2 (emit strategy):** confirm a **Python-side v2 emitter** is viable (lean recommendation —
  the mixin is deeply classic; teaching it the whole v2 schema is NR-5).
- **Committed artifacts (R1-S2/R2-S1/R2-S2/R1-S10/R2-F4)** — M0 produces *diffable files*, not a dev note:
  1. **`v2-envelope.golden.json`** — the exact accepted v2 payload the emitter (M1) byte-targets.
  2. **`v2-envelope-schema.json`** — a minimal **JSON Schema** for the v2 envelope, so CI validates the
     emitter's structural correctness **without a live Grafana** (asserts `apiVersion`/`kind`/`spec`,
     `spec.elements` is a list, etc.).
  3. **`v2-construct-names.json`** — the verified values of `apiVersion`, layout kinds
     (`TabsLayout`/`RowsLayout`/`AutoGridLayout`), the conditional-rendering group kind, and the
     `dashboardSectionVariables` toggle, **plus a `verified_on` field carrying the exact
     `/api/health` version string** (e.g. `13.1.2`). A later 13.1.x rename becomes a one-line diff; M5's
     validator/emitter *reads* this map rather than hardcoding names inline.
  All three land in `docs/design/dynamic-dashboards/`. **Output:** the artifacts + a filled decision
  matrix reviewed before M1 starts. No SDK code yet.

## M1 — v2 emit foundation (FR-1, FR-5, FR-10) — ✅ **DONE (2026-07-09)**
> Shipped `src/startd8/dashboard_creator/v2/` (`models.py` + `emitter.py`), 12 tests, 493 dashboard_creator
> tests green (classic untouched). **Live-verified:** the emitter's foundation board round-trips through
> Grafana 13.1.0 (201 Created, full fidelity, `text` viz accepted natively). Byte-golden
> `tests/unit/dashboard_creator/fixtures/v2_foundation.golden.json` + offline schema validation against the
> M0 `v2-envelope-schema.json`.
>
> **Design decision (fed back):** built as a **separate v2 model tree** (own `V2Panel`/`GridLayout`/
> `RowsLayout`/`CustomVariable`), **not** new fields on `DashboardSpec`. Consequences: (a) classic
> `DashboardSpec`/generator/compiler/validator are byte-untouched (strongest FR-10/NR-1); (b) **R1-S9 is
> dissolved** — the `panels min_length=1` invariant is classic-only and never applied to v2, so a
> layout-only v2 board is legal without editing `models.py`; (c) the R1-F2 opt-in trigger is the
> `emit_v2_dashboard(schema="v2")` param (raises on any other value), not a `DashboardSpec` field.
> **Deferred to M6 (not needed by the foundation):** the richer classic-PanelSpec→viz mapping — M1 ships
> `text_panel` + a `viz_config` passthrough, which covers the Workbook's dominant text panels.

- ~~New `dashboard_creator/v2/` (emitter + models)~~ ✅ done — additive, classic untouched (FR-10).
- **Single, explicit opt-in trigger (R1-F2):** ✅ `emit_v2_dashboard` requires `schema="v2"`; any other
  value raises `V2ValidationError` — no silent schema flip.
- **`panels min_length=1` (R1-S9):** ✅ dissolved by the separate-model design (v2 has no such invariant;
  classic keeps ≥1 — proven by `test_classic_dashboardspec_still_requires_panels`).
- **Deterministic (R1-S4/R2-S7):** ✅ `v2_json` is the identical `json.dumps(sort_keys=True, indent=2)+"\n"`
  call as `output.py:44`; `persist_v2_dashboard` routes through `persist_dashboard` for the atomic
  tmp-then-`os.replace` write. Byte-golden pins stability.
- **Verify:** ✅ deterministic + byte-golden + validates against `v2-envelope-schema.json` + live
  round-trip; classic specs byte-identical to today (493 tests). Element-reference integrity fails loud
  (undeclared `ElementReference` → error).

## M2 — Tabs/rows layout (FR-4) — ✅ **DONE (2026-07-09)**
> Extended `v2/models.py` with `TabsLayout`/`TabsLayoutTab` + `AutoGridLayout`/`AutoGridItem`, and real
> **nesting** — a tab or row carries any sub-layout (`_sub_layout_v2` fails loud on a non-layout). All four
> v2 layout kinds (`GridLayout`/`RowsLayout`/`AutoGridLayout`/`TabsLayout`) are now emittable + selectable.
> Element-reference integrity **walks the full nesting** (an undeclared ref deep in a tab→autogrid fails
> loud). Backward-compatible: `RowsLayoutRow`/`TabsLayoutTab` keep the M1 `items` shorthand (→GridLayout)
> and gain an optional explicit `layout`. M2 byte-golden `fixtures/v2_tabs.golden.json`. 19 v2 tests, 500
> dashboard_creator green.
- A `layout` descriptor (tabs → rows → panels, nesting) → v2 layout kinds ✅ all four; auto-grid vs custom
  selectable (`AutoGridLayout` vs `GridLayout`).
- **Verify:** ✅ a 2-tab board (tab0 = RowsLayout→GridLayout, tab1 = AutoGridLayout) emits + validates
  against the M0 schema **and round-trips through live Grafana 13.1.0** (201, fidelity confirmed).

## M3 — Conditional rendering (FR-2) — ✅ **DONE (2026-07-09)**
> Added `ConditionalRendering` (`ConditionalRenderingGroup`, visibility show/hide, condition and/or) with
> all three condition kinds — `VariableCondition` (operators `equals|notEquals|matches|notMatches`),
> `DataCondition` (data-presence), `TimeRangeSizeCondition` — plus a `show_when_variable()` helper for the
> audience knob. A `conditional` field on `RowsLayoutRow`/`TabsLayoutTab`. **Build-time guard:** every
> `ConditionalRenderingVariable` must reference a declared dashboard variable (else raise — no
> silently-broken always-hidden section). 26 v2 tests / 507 dashboard_creator green; M3 golden
> `fixtures/v2_conditional.golden.json`.
>
> **⚠ Verified attach-point (design finding):** conditional rendering is **section-level** — it attaches
> to a **row or tab only**; Grafana 13.1.0 **strips** it from a Panel element and from a GridLayoutItem
> (both round-tripped away to `None`). So FR-2's "per-panel" show/hide is realized by **wrapping the panel
> in its own conditionally-rendered row** (the idiom M6's disclosure knob uses). Fed back to FR-2.
- Condition types + AND/OR groups → the conditional-rendering group construct ✅ (all three kinds).
- **Verify:** ✅ a row/tab shown only when `audience == 'x'`; AND/OR + hide/show compose; the 2-row board
  validates against the M0 schema **and round-trips through live Grafana 13.1.0** (201, conditional
  survived). Bad operator/visibility/condition + undeclared-variable all fail loud.

## M4 — Section-level variables (FR-3) — ✅ **DONE (2026-07-09)**
> Added a `variables` field (list of `CustomVariable`) to `RowsLayoutRow`/`TabsLayoutTab` — section-scoped
> variables, verified on both a row and a tab (round-trip). Two guards: (a) the **#122553 build-time rule
> (R1-F6)** — a section variable referencing another section variable **in the same tab** raises (per-tab
> scope; nested tabs are separate scopes; cross-tab is allowed); (b) the M3 conditional-variable guard now
> also recognizes **section** variables, so a conditional inside a section may reference its own section
> var without a false "undeclared" error. 34 v2 tests / 515 dashboard_creator green; M4 golden
> `fixtures/v2_sections.golden.json`. `dashboardSectionVariables` toggle was confirmed ON in M0.
- Per-row/tab `variables`; section-first resolution ✅. Same-tab cross-reference limitation (#122553)
  validated at build time ✅.
- **Verify:** ✅ two rows each with an independent section variable emit + validate against the M0 schema
  **and round-trip through live Grafana 13.1.0** (201, both sections carry their variable). Same-tab
  cross-ref + bad section-variable type fail loud; cross-tab reuse is allowed.

## M5 — Validation + provisioning + version handling (FR-7, FR-6, FR-11) — ✅ **DONE (2026-07-09)**
> Shipped `v2/{validate,version,provision,constructs}.py` + a one-line discriminator into the existing
> `json_validator.py` (classic path byte-untouched). **Validation:** `validate_dashboard_json` routes an
> `apiVersion`-bearing board to `validate_v2_dashboard`, which positively asserts the envelope
> (`apiVersion`/`kind`/`spec`+`title`/`layout`/`elements`-is-object), enforces UID via `metadata.name`
> (R1-S5), and rejects out-of-scope `*Layout`/`*Variable` kinds (NR-6/R1-F7) against the M0 allowlist (a
> test pins it to `v2-construct-names.json`, no drift). **Version:** minor-aware `parse_version` +
> `supports_v2_dynamic` (≥13.1) + `version_gate_reason` — fixes the major-only `check_version` gap
> (R1-F1). **Provision:** `provision_v2(client, board)` = version-gate → UID-collision guard → idempotent
> legacy upsert (M0 outcome-1 path), recording `provision_api`. 21 M5 tests / 536 dashboard_creator green,
> and **live-verified** against Grafana 13.1.0 (provision + idempotent re-provision + fetch + cleanup).
>
> **Design note (fed back):** the collision guard uses **title comparison** (the FR-5 pattern), **not** an
> `apiVersion`/schema sniff — the legacy `GET /api/dashboards/uid` returns a *classic-shaped*
> representation even for a v2-stored board, so "no apiVersion" is not a reliable "classic" signal (a
> schema sniff caused a false self-collision on re-provision; caught live). Different title ⇒ collision;
> same title ⇒ idempotent. `force=True` overrides. The **resource API** stays the M0-noted native path but
> the legacy endpoint is used for its clean `overwrite` upsert (resource-API updates need resourceVersion).

- **Schema discriminator FIRST (R2-S4, blocker):** `json_validator.py:69` range-checks `schemaVersion`
  against `range(36,42)`; a v2 board has **no** `schemaVersion`, so `None not in range(36,42)` is `True`
  and the range error **already fires on every v2 board today**. Add `if "apiVersion" in data: <v2 path>
  else: <classic path>` **before** any classic-specific check.
- **Branch the classic-only checks (R1-S5):** the UID + panel-count + `panels`-is-list logic
  (`json_validator.py:76-93`) has no v2 analog (v2 has no top-level `panels[]`). The v2 path positively
  asserts `apiVersion`/`kind`/`spec` present + `spec.elements` is a list (per `v2-envelope-schema.json`)
  and enforces UID via `spec`/metadata — it does NOT run the panel-count branch.
- **Reject out-of-scope v2 constructs (NR-6 / R1-F7):** the v2 validator raises on any v2 `kind` not in
  the M0 `v2-construct-names.json` allowlist — scope creep is caught, not silently emitted.
- **Build-time guard for the same-tab section-var limitation (R1-F6, #122553):** a spec whose section
  variable references another section variable in the same tab is a **build-time validation error**, not a
  silently-broken render.
- **Provision path per M0/OQ-1** (`/api/dashboards/db` or `provision_v2()`); the `ProvisioningResult`
  **records which endpoint accepted the payload** (`details["provision_api"]`, R1-F3) so OQ-1's answer is
  auditable. Preserve UID/idempotent upsert + the FR-5 collision guard already in `portal_build`.
- **Cross-schema UID collision (R1-S8):** `upsert_dashboard` uses `overwrite: True` (`grafana_client.py:118`)
  — provisioning a v2 board whose UID is already an in-use **classic** board is refused (or namespaced),
  never a silent destructive overwrite.
- **Version detect gated on the 13.1 MINOR / capability (R1-F1/R1-S3/R2-S2):** the shipped
  `check_version()` parses **only the major** (`grafana_client.py:91`) — it cannot tell 13.0 from 13.1,
  the exact section-var GA boundary. Add a minor/capability probe (`/api/frontend/settings` feature
  toggles or a resource-API HEAD) that reads against the M0 `verified_on` baseline; `<13.1` (or toggle
  off) → refuse-with-message (or classic fallback per OQ-4) — never a silently-broken board.
- **Verify:** a v2 dict with no `schemaVersion` produces **zero** range/missing-key errors; a v2 board
  upserts idempotently and records its `provision_api`; a mocked `13.0.x` target is refused, a `13.1.x`
  (toggle on) proceeds.

## M6 — Workbook audience consumer (FR-8, FR-9) — the proof — ✅ **DONE (2026-07-09)**
> Shipped `kickoff_experience/portal_spec_v2.py` — `build_workbook_v2(state, project, *, audience,
> provenance)` emits the audience-personalized **v2 dynamic Workbook**. The `audience` **`CustomVariable`**
> (fixed allowlist, R1-F8) defaults to the resolved token; **disclosure** = a Beginner plain-language intro
> (`show when audience==beginner`) + a standard intro (`hide when beginner`); **surface** = each domain's
> `audience-default`-shielded fields in a **separate "safe defaults" subsection hidden for Beginner**
> (coarse OQ-5), carrying the 🛡️ badge on the non-Beginner render. **FR-9 byte-identity proven:** across
> beginner/intermediate/advanced the board is byte-identical **except the audience variable's `current`**
> (golden diff test). 8 M6 tests / full v2 suite green, and **live round-trip through Grafana 13.1.0**
> (201) — flipping the variable switches persona in-browser, **no regen, no write**.
>
> **Build decision (fed back — see reqs §0.2 / the branch note):** built **self-contained** on the
> dynamic-dashboards branch — Era 1 (the classic audience Workbook) lives on a separate unmerged branch,
> so M6 consumes only the primitives that ship here (`resolve_audience_preference`/`coerce_audience`,
> `load_ledger`/`_is_audience_default`, `KickoffState`) and renders the tiered intro **inline**. It is a
> **separate additive v2 board** (distinct `-v2` UID; coexists with the classic one) and does **not** touch
> `build_kickoff_portal_spec`/`portal_build` — R2-F5 satisfied trivially (a test asserts the classic
> builder is unmodified). Wiring v2 into the `kickoff portal` CLI as an opt-in surface is a follow-up.
- **Named integration sub-task, not just "cite" (R1-S6/R1-F4):** Era 1 wired `resolve_audience_preference`
  into `portal_build.py` (the I/O caller), NOT `portal_spec.py`. It returns an **`AudienceResolution`**
  object with fields **`.value`** (a `KickoffAudience` enum) and `.source` — **not** `.audience`; the
  default is **Intermediate** (`DEFAULT_AUDIENCE`), not beginner. Add the `audience` variable default =
  `resolve_audience_preference(project_root).value.value` (the token).
- **`audience` is a fixed custom allowlist (R1-F8, security):** emit `type: custom` with the enumerated
  options `beginner|intermediate|advanced` — **never** a query/datasource variable. Because shielded-field
  visibility is driven by `audience == …` conditional rules, an unconstrained value is effectively a
  client-side disclosure control; the allowlist closes that.
- **Disclosure:** intro/prose panels per tier with `audience == …` show-rules (OQ-6: intro-first for v1).
- **Surface + the Era 1 badge coexistence contract (R2-F1/R2-S5, OQ-5 coarse):** Era 1 renders each
  domain as **ONE `text` panel** with the 🛡️ badge baked per-row inside it; a coarse `audience=='beginner'`
  conditional hides the **whole domain panel**, not individual rows. State the migration contract: for v1,
  the shielded fields move to a **separate collapsible domain-subsection panel** hidden for beginner (so
  only shielded fields collapse, not the whole domain), and the Era 1 static badge is **retained** on the
  still-visible non-beginner render (it degrades cleanly — the badge and the row-collapse are orthogonal:
  bake-time label vs runtime show/hide). `build_kickoff_portal_spec`'s Era 1 signature (`audience`, `tier`,
  `provenance` keyword params) MUST survive the v2 migration unchanged (R2-F5/FR-10 caller-interface
  stability).
- One deterministic JSON per project; switching `audience` re-renders in-browser, no write (FR-9, NR-2).
  **Byte-identity AC (R1-F5):** regenerating under beginner/intermediate/advanced project defaults yields
  the **same bytes except the `audience` variable's `current` default** — a golden diff pins exactly that.
- **Verify:** the board defaults to the project audience; flipping the variable changes prose density +
  shielded-field visibility with zero regeneration and zero writes; `portal_build.py` compiles unchanged.

## M7 — Broaden (optional, OQ-7)
- Fleet (per-service section filters), gov-budget (per-department sections/tabs), o11y-artifact boards opt
  into the v2 constructs. Sequence after the Workbook proof.

---

## Design notes / risks
- **Emit strategy (OQ-2).** Lean **Python-side v2 emitter** — the classic jsonnet mixin stays for classic;
  v2 is a separate, simpler JSON builder. Avoids a parallel v2 jsonnet library (NR-5).
- **Classic path is sacrosanct (NR-1).** M1's golden pins classic byte-equivalence; no existing consumer
  changes until it opts in (FR-10).
- **Provision uncertainty (OQ-1) is the top risk** — M0 resolves it before any build; if the resource API
  is required, `grafana_client` gains a v2 method.
- **Workbook structural change (OQ-5)** — the one-markdown-panel-per-domain layout limits field-level
  conditional rendering; take the coarse (row-collapse) path for v1 to keep `portal_spec` change small.
- **External-schema drift** — the Grafana v2 construct names are a 2026-06 snapshot; M0 pins them against
  the live instance before the emitter hardcodes anything.

## Traceability
| FR | Milestone |
|---|---|
| FR-1, FR-5, FR-10 | M1 |
| FR-4 | M2 |
| FR-2 | M3 |
| FR-3 | M4 |
| FR-6, FR-7, FR-11 | M5 |
| FR-8, FR-9 | M6 |
| (broaden) | M7 |
| (verify OQ-1/2/3) | **M0 (gates all)** |

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

> **Areas substantially addressed (R1/R2):** M0 decisiveness (go/no-go matrix + committed golden/schema/
> construct-name artifacts + composite board), the `json_validator` v2-discriminator blocker, minor-version/
> capability gating, serializer + atomic-write reuse, FR-1 single opt-in trigger, `panels min_length=1`
> relaxation, cross-schema UID collision, NR-6 construct allowlist, the Era 1 badge↔row-collapse
> coexistence contract, and caller-interface stability. Later reviewers: do not re-propose these.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|-----------------------------------|------|
| R1-S1 | M0 branch/decision matrix (incl. "neither" outcome) | R1 opus | Applied → M0 decision matrix | 2026-07-09 |
| R1-S2 | M0 committed golden envelope | R1 opus | Applied → M0 `v2-envelope.golden.json` | 2026-07-09 |
| R1-S3 | M5 minor/capability version probe | R1 opus | Applied → M5 version-detect bullet | 2026-07-09 |
| R1-S4 | v2 emitter reuses output.py serializer | R1 opus | Applied → M1 Deterministic bullet | 2026-07-09 |
| R1-S5 | Branch classic-only UID/panel-count checks | R1 opus | Applied → M5 branch bullet | 2026-07-09 |
| R1-S6 | M6 named integration sub-task (AudienceResolution) | R1 opus | Applied → M6 (corrected `.value`, Intermediate default) | 2026-07-09 |
| R1-S7 | Verify PanelSpec→v2 element in M0 | R1 opus (R2 qualified) | Applied (folded) → M0 composite board embeds a classic panel | 2026-07-09 |
| R1-S8 | Cross-schema UID collision guard | R1 opus | Applied → M5 collision bullet | 2026-07-09 |
| R1-S9 | Relax `panels min_length=1` for v2 | R1 opus | Applied → M1 invariant bullet | 2026-07-09 |
| R1-S10 | M0 construct-name map | R1 opus | Applied → M0 `v2-construct-names.json` | 2026-07-09 |
| R2-S1 | M0 committed JSON Schema fixture | R2 sonnet | Applied → M0 `v2-envelope-schema.json` | 2026-07-09 |
| R2-S2 | M0 record exact Grafana build string | R2 sonnet | Applied → M0 `verified_on` in construct-name map | 2026-07-09 |
| R2-S3 | M0 structured go/no-go decision tree | R2 sonnet | Applied → M0 decision matrix (merged w/ R1-S1) | 2026-07-09 |
| R2-S4 | Schema discriminator FIRST in validator | R2 sonnet | Applied → M5 discriminator bullet (blocker) | 2026-07-09 |
| R2-S5 | Era 1 badge coexistence contract | R2 sonnet | Applied → M6 coexistence bullet (merged w/ R2-F1) | 2026-07-09 |
| R2-S6 | M0 composite board (all 3 constructs) | R2 sonnet | Applied → M0 composite board bullet | 2026-07-09 |
| R2-S7 | Atomic write via persist_dashboard | R2 sonnet | Applied → M1 Deterministic bullet | 2026-07-09 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none) | — | — | All R1/R2 plan suggestions accepted; R1-S7 accepted in the qualified form R2 proposed (folded into M0's composite board rather than a separate step). | 2026-07-09 |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R1 — claude-opus-4-8[1m] — 2026-07-09

- **Reviewer**: claude-opus-4-8[1m]
- **Date**: 2026-07-09 04:12:00 UTC
- **Scope**: Plan quality — M0 spike design, v2 emit strategy (OQ-2), provision-path degradation (OQ-1), and the Workbook consumer wiring (M6). Findings grounded against `dashboard_creator/{grafana_client,provisioning,json_validator,output}.py`, `models.py`, and `startd8-mixin/lib/dashboards.libsonnet:26`.

**Executive summary (top risks / gaps in the plan):**
- **M0 does not define its own failure/degrade branch.** M0 is "gates everything" but if OQ-1 resolves to "resource API only" the plan just says `grafana_client` gains a v2 method — there is no rescoping of M5/M6 effort or a decision record. The riskiest single item is unbudgeted.
- **M0 spike's exit criteria are prose, not artifacts.** "Capture the exact accepted payload envelope" needs to be a committed golden fixture the emitter (M1) targets, else M0's answer is not reusable and M1 re-derives it.
- **M5 version-detect underspecified vs the shipped client.** `check_version()` reads only the *major* version (`grafana_client.py:91`); M5 says "query Grafana version/capabilities" but never states the client change needed to gate on 13.1 minor / `dashboardSectionVariables`.
- **The Python-side v2 emitter (OQ-2) has no determinism plan of its own.** Classic goes through `output.py` `json.dumps(sort_keys=True)`; the plan must confirm the v2 emitter shares that exact serializer, or byte-stability (FR-5) forks.
- **M6 cites `resolve_audience_preference(project_root)` returning a default**, but it returns an `AudienceResolution` object and is not currently wired into `portal_spec.py` — the "cite, don't re-implement" instruction understates a real integration task.
- **M1's "reuse the existing PanelSpec→panel mapping" assumes classic panel dicts drop cleanly into v2 `elements`** — unverified; v2 elements wrap panels differently and may need a shim.
- **No milestone owns the `json_validator` panel-count/UID checks under v2** — v2 has no top-level `panels[]`, so the count logic (`json_validator.py:80`) is classic-only and M5 must branch it, not just relax `_REQUIRED_KEYS`.

**Plan Suggestions (S-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S1 | Risks | critical | Add an explicit **M0 branch/decision matrix**: for each OQ-1 outcome (`/api/dashboards/db` accepts v2 \| resource API required \| neither on this 13.1 minor) state the concrete downstream delta to M5/M6 and a go/no-go. | M0 "gates everything" but the plan only degrades for one branch ("if resource API required, `grafana_client` gains a v2 method"); the "neither" case is unhandled, and there's no rescoping trigger. | M0 section + Design notes/risks | Review: M0 note contains a filled decision matrix before M1 starts. |
| R1-S2 | Validation | high | Make M0's deliverable a **committed golden fixture** (the canonical accepted v2 envelope JSON) that M1's `Verify` diffs against, not just "record the v2 JSON skeleton". | M1 already plans a golden for byte-stability; anchoring it to M0's captured real envelope closes the external-schema-drift risk deterministically. | M0 "Output:" bullet; M1 "Verify:" bullet | Golden file exists; M1 compile output byte-matches it. |
| R1-S3 | Ops | high | In M5, specify the **client change to gate on Grafana 13.1 minor / capability**, not just "query version/capabilities": `check_version()` today parses only the major version (`grafana_client.py:91`). Name the probe (e.g. `/api/frontend/settings` feature toggles, or a resource-API HEAD). | Without a minor/capability probe, FR-11/OQ-4 cannot distinguish 13.0 from 13.1 and will ship section-var boards to a target that renders them broken. | M5, "Version detect (FR-11/OQ-4)" bullet | Unit test: mocked `13.0.x` health → refuse/fallback; `13.1.x` + toggle on → proceed. |
| R1-S4 | Data | high | M1: state that the **v2 emitter reuses `output.py`'s `json.dumps(sort_keys=True, indent=2)+"\n"` serializer verbatim** (not a new dumps call), so FR-5 determinism is shared and cannot fork between paths. | Classic determinism lives in `output.py:44`; a separate Python v2 emitter that re-implements serialization risks divergent byte output. | M1 "Deterministic:" bullet | Golden across both paths produced by the same serializer function; grep confirms single call site. |
| R1-S5 | Interfaces | high | M5: split the `json_validator` change into two — (a) accept v2 required keys (`apiVersion`/`kind`/`spec`) AND (b) **branch the UID + panel-count + panels-is-list checks**, which are classic-only (`json_validator.py:76-93`) and have no v2 analog (v2 has no top-level `panels[]`). | The plan says "make json_validator schema-aware" but only names key acceptance; the count/UID logic would still run and mis-validate a v2 board (no `panels` → count 0). | M5 first bullet | Test: v2 board with N `elements` passes validation; UID still enforced via `spec`/metadata. |
| R1-S6 | Architecture | medium | M6: elevate "wire in `portal_spec.py` via the audience feature's public API" to a named sub-task and note `resolve_audience_preference` returns an `AudienceResolution` (`.audience`/`.source`) currently used only in `web.py`/`concierge_view.py`, **not** `portal_spec.py`. | Grounding shows the integration point does not yet exist in `portal_spec.py`; "cite, don't re-implement" hides a real new wire-up + the object-unwrap. | M6 first bullet | Test: `build_kickoff_portal_spec` emits an `audience` variable whose default = resolved `.audience`. |
| R1-S7 | Risks | medium | M1: verify the "reuse the existing PanelSpec→panel mapping … wrap them in v2 `elements`" assumption in the M0 spike (hand-author one real v2 element from an existing classic panel dict) before M1 depends on it. | v2 `elements` wrap panels with a different envelope than classic `panels[]`; if the mapping needs a shim, that's M1 scope, not a footnote. | M0 hand-author bullet / M1 "Reuse…" bullet | M0 note shows a classic panel dict embedded in a rendering v2 element. |
| R1-S8 | Ops | medium | Add a rollback/coexistence note: since v2 boards share the classic UID space and `upsert_dashboard` overwrites by UID (`overwrite: True`, `grafana_client.py:118`), state whether a v2 board reuses or namespaces the classic UID, to avoid a v2 emit silently overwriting a live classic board. | FR-5 collision guard is mentioned for `portal_build` but cross-schema UID collision (classic↔v2 same uid) isn't addressed; `overwrite=True` makes it destructive. | M5 provision bullet / Design notes | Test: provisioning a v2 board with an in-use classic UID is refused or namespaced. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R1-S9 | Architecture | medium | Pressure-test the "additive second emit target" framing: confirm the plan does **not** require any change to `DashboardSpec`'s `panels: List[PanelSpec] = Field(min_length=1)` constraint (`models.py`), which forces ≥1 flat panel — a pure-tabs/rows v2 board may legitimately have zero top-level panels. | The `min_length=1` validator is a classic-era invariant; a v2 layout-only spec would fail model validation before emit, contradicting FR-10 "additive/untouched". | M1 additive-model bullet | Instantiate a v2 `DashboardSpec` with layout only, no flat panels; assert it validates. |
| R1-S10 | Validation | low | Add a negative M0 outcome to the de-risking note: explicitly record **which 2026-06 construct names were confirmed vs renamed** on the live 13.1 (`ConditionalRenderingGroupKind`, `TabsLayout`, `dashboardSectionVariables`), so a later 13.1.x minor rename is a diffable one-liner, not a silent break. | The external-schema-drift risk is named but the mitigation ("M0 pins them") produces no durable artifact; a checked-in name map makes drift auditable. | Design notes "External-schema drift" | M0 emits a construct-name map file; M5 validator reads it. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with): none — R1 is the first round; Appendix C was empty.

#### Review Round R2 — claude-sonnet-4-6 — 2026-07-09

- **Reviewer**: claude-sonnet-4-6
- **Date**: 2026-07-09 00:00:00 UTC
- **Scope**: Focus areas: (a) external-schema construct-name versioning and M0 spike artifact design; (b) M0 as a decisive experiment with clear go/no-go criteria; (c) OQ-5 / FR-8/FR-9 composition with the shipped Era 1 `portal_spec.py` structure; (d) CI testing strategy for v2 emit without live 13.1. Grounded against `dashboard_creator/{json_validator,grafana_client,output,models}.py`, `startd8-mixin/lib/dashboards.libsonnet:26`, and `kickoff_experience/portal_spec.py` (main + Era 1 commit `3f86b72c` on `feat/workbook-audience-personalization`).

**Executive summary:**
- M0 as written has a **decisiveness gap**: it produces a prose "de-risking note + canonical v2 JSON skeleton" but no structured go/no-go decision matrix and no committed artifact that downstream milestones can programmatically verify against. R1-S1 and R1-S2 raised parts of this; the M0 artifact gap is a separate concern (the JSON skeleton is not a JSON Schema).
- The Era 1 `_manifest_section` (confirmed in `3f86b72c`) is still **one `text` panel per domain** — all fields are rows in a single Markdown table. The coarse OQ-5 row-collapse path means M6 would toggle visibility on a whole-domain panel, not individual shielded field rows, **while Era 1 already renders the 🛡️ badge per-row inside that same Markdown**. These two mechanisms need a stated coexistence contract (addressed as R2-F1 in the requirements file).
- The M0 spike does not specify **which 13.1.x build** was verified — a Grafana 13.1.0 construct name could shift in 13.1.1. The plan needs a versioned probe step.
- `json_validator.py:69` silently mishandles a v2 board: `schemaVersion` absent → `None not in range(36,42)` evaluates to `True` → the **schemaVersion-range error fires on every v2 board** before M5's changes. M5's "make json_validator schema-aware" must discriminate schema first, not just relax key requirements.

**Plan Suggestions (S-prefix):**

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S1 | Validation | high | M0 must produce a **committed JSON Schema fixture** (e.g. `docs/design/dynamic-dashboards/v2-envelope-schema.json`) that captures the verified v2 envelope shape, not just a prose note. M1's golden pins byte-stability; the JSON Schema fixture lets CI validate structural correctness without a live Grafana instance. | "Capture the exact accepted payload envelope" (M0 Output bullet) currently means a developer note. A JSON Schema derived from the hand-authored board is a machine-checkable artifact that survives personnel turnover and validates the emitter in unit tests. Complements R1-S2's golden-fixture proposal (R1-S2 is the emitter golden; this is the structural schema). | M0 "Output:" bullet — add: "Commit a minimal JSON Schema for the v2 envelope to `docs/design/dynamic-dashboards/`" | Unit test: v2 emitter output validates against the committed JSON Schema; the schema is checked in after M0 and referenced by M5 validator. |
| R2-S2 | Risks | high | M0 must record **which exact Grafana build** (version string from `/api/health`) was used to verify the v2 construct names — not just "Grafana ≥13.1". A 13.1.x patch could rename a construct. | "The Grafana v2 construct names are a 2026-06 snapshot" (Design notes) — but the plan's M0 output does not include the build string. Without it, there is no baseline to diff against if a later CI run fails because a construct was renamed between 13.1.0 and 13.1.1. | M0 "Output:" bullet — add: "Record the exact version string from `/api/health` alongside the construct names in the de-risking note." | The de-risking note contains a `verified_on` field; an M5 re-probe on a different 13.1.x minor triggers a diff-review step. |
| R2-S3 | Architecture | high | M0 must specify a **structured go/no-go decision tree** (not just prose notes) for the three OQ-1 outcomes: (1) `/api/dashboards/db` accepts v2 → proceed, M5 classic client path extended; (2) resource API required → M5 gains `grafana_client.provision_v2()`, estimate +X days; (3) neither endpoint accepts v2 on this 13.1.x minor → STOP, file an upstream issue, defer M1–M6. R1-S1 raised the "neither" degrade path; this extends it to a formal decision gate. | M0 says it "gates everything" but the only stated degrade is "(if the resource API is required, `grafana_client` gains a v2 method)". The unstated outcomes (neither endpoint works; partial v2 support with unexpected constraints) are where the risk actually lives. The decision tree converts M0's gate from implicit to explicit. | M0 section — replace the provision bullet with a decision matrix format | M0 note reviewed by orchestrator before M1 starts; matrix has a populated decision column. |
| R2-S4 | Interfaces | medium | M5's validator change must explicitly add a **schema discriminator first** before relaxing key checks. Grounding: `json_validator.py:69` — `_SUPPORTED_SCHEMA_VERSIONS = range(36,42)`; a v2 board has no `schemaVersion` key, so `None not in range(36,42)` evaluates `True` and the range-check error fires on every v2 board **before M5 is complete**. The fix is a discriminator (`if "apiVersion" in data: validate as v2; else: validate as classic`) not just an additive key check. | R1-S5 correctly raised the panel-count/UID branching gap; this is a different (and earlier) issue: the `schemaVersion` range check fires even when `schemaVersion` is absent, which means an in-progress v2 board would silently fail the validator with a misleading error. | M5 first bullet — add: "Add a schema discriminator (`apiVersion` present → v2 path; absent → classic path) before any classic-specific checks." | Test: `validate_dashboard_json` on a v2 dict with no `schemaVersion` produces zero range-check errors and no missing-key errors for `panels`/`templating`. |
| R2-S5 | Architecture | medium | M6 must specify whether the **Era 1 🛡️ badge** (a baked static glyph in the Markdown table row, `_AUDIENCE_DEFAULT_DISPLAY = ("🛡️", "safe default set for you")`) is **retained, replaced, or coexists** with the v2 conditional-rendering row-collapse. Confirmed in Era 1 `3f86b72c`: the badge is a per-row glyph inside the single-domain `text` panel; the v2 coarse row-collapse would hide the entire domain's panel for beginner. Two different mechanisms; the plan must state the migration contract. | The plan says "recommend coarse for v1 to keep `portal_spec` change small" (OQ-5), but does not state what happens to the Era 1 badge rendering in the v2 path. If the whole-domain panel is hidden for beginner, the badge is invisible anyway (the panel is hidden). If both coexist (badge stays, row-collapse added), the beginner sees neither the shielded row nor the badge — a state not described anywhere. | M6 "Surface (OQ-5 decision needed):" bullet — add the Era 1 coexistence note | Test: a board for a Beginner project — assert that the domain panel containing shielded fields is hidden AND that the Era 1 badge logic in `_manifest_section` degrades cleanly (or is bypassed) under v2 generation. |

### Stress-test / adversarial pass

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-S6 | Validation | medium | The M0 spike "hand-authors one v2 dashboard" but does not specify that the hand-authored board must include **all three FR-2/3/4 constructs simultaneously** (a tab with a section variable AND a conditional-rendering rule). Testing them individually would miss interaction effects (e.g. a section variable inside a conditionally-hidden tab). If M0 uses a board with only one construct, M1–M4 may be built on an incomplete picture of the envelope. | M0's board spec is "a tab, a row, a section variable, and a conditional-rendering rule" — but these could be independent elements. A composite test (section variable inside a row inside a tab with a conditional show rule on the tab) is a different shape than three individual elements. The focus file's point (b) asks whether M0 is a decisive experiment; a minimal composite is more decisive than three minimal individual ones. | M0 "hand-author one v2 dashboard" bullet | M0 note records that the hand-authored board uses all three constructs simultaneously in one nesting; the JSON envelope captures the composite shape. |
| R2-S7 | Ops | low | Add a note to the Design notes section: the `output.py` persistence layer uses an **atomic tmp-then-replace write** (`_tmp.write_text → os.replace`). If the v2 emitter uses `persist_dashboard` directly, this is free. If M6 introduces a separate write path, it must replicate the atomicity contract (`output.py:46-48`). R1-S4 addressed serializer reuse; this addresses write-path atomicity. | `output.py:46`: `_tmp = json_path.with_name(json_path.name + ".tmp"); _tmp.write_text(...); os.replace(_tmp, json_path)`. If M6 goes through `persist_dashboard`, this is inherited. If a new path is created, atomicity is at risk. | Design notes / M1 "Deterministic:" bullet — one sentence: "route v2 output through `persist_dashboard` to inherit atomic write." | Grep: v2 emit path calls `persist_dashboard`; no raw `Path.write_text` in the v2 module. |

**Endorsements** (prior untriaged R1 suggestions this reviewer agrees with):
- R1-S1: Endorse strongly — "neither endpoint accepts v2" is a real outcome and the plan has no degrade for it; extends into R2-S3 above.
- R1-S2: Endorse — committed golden fixture for M0 is the right call; R2-S1 adds the JSON Schema layer on top.
- R1-S3: Endorse — `check_version()` parses major only (`grafana_client.py:91`); confirmed against live code.
- R1-S4: Endorse — `output.py:44` has `json.dumps(sort_keys=True, indent=2) + "\n"`; the v2 emitter must reuse this exact call.
- R1-S5: Endorse — `json_validator.py:76-93` panel-count logic has no v2 analog; R2-S4 addresses the earlier discriminator gap that R1-S5 didn't catch.
- R1-S9: Endorse — `DashboardSpec.panels = Field(min_length=1)` at `models.py:266` confirmed; a pure-tabs v2 board fails this invariant.

**Disagreements** (prior untriaged R1 suggestions this reviewer would reject or qualify):
- R1-S7 ("verify PanelSpec→panel mapping in M0 spike"): qualify — the mapping concern is valid but M0's hand-authored board should answer it implicitly by including one panel inside a v2 element; no separate verification step needed if M0 is comprehensive (per R2-S6).

---

## Requirements Coverage Matrix — R1

Analysis only (not triage). Maps each requirement to the plan milestone(s) that address it, grounded against the current code.

| Requirement | Plan Step(s) | Coverage | Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (additive v2 emit target) | M1 | Partial | Opt-in trigger left "decided in plan" (M1) — the `schema="v2"` vs "presence of a dynamic construct" ambiguity (see R1-F2/R1-S9) is not resolved; `DashboardSpec.panels min_length=1` collision unaddressed. |
| FR-2 (conditional rendering) | M3 | Full | Condition types + AND/OR groups mapped to the group construct; verify step present. |
| FR-3 (section-level variables) | M4 | Partial | Section-first-then-fallback resolution and the same-tab cross-ref limitation (#122553) are noted but not turned into a build-time validation rule (R1-F6). |
| FR-4 (tabs/rows layout) | M2 | Full | Layout kinds + auto-grid vs custom + verify step covered. |
| FR-5 (deterministic + $0) | M1 | Partial | Golden pins byte-stability, but the plan doesn't state the v2 emitter reuses `output.py`'s serializer verbatim (R1-S4); determinism could fork across paths. |
| FR-6 (provisioning parity) | M5 (gated by M0) | Partial | Endpoint-selection branch is real but the choice contract/observability is unspecified (R1-F3); "neither endpoint" outcome unhandled (R1-S1). |
| FR-7 (schema-aware validation) | M5 | Partial | M5 names key-acceptance but not the classic-only UID/panel-count/panels-is-list branch (`json_validator.py:76-93`) that has no v2 analog (R1-S5). |
| FR-8 (audience personalization) | M6 | Partial | `resolve_audience_preference` returns an `AudienceResolution` object and is not wired into `portal_spec.py` yet; default value (Intermediate) unstated (R1-F4/R1-S6); variable-allowlist safety (R1-F8) uncovered. |
| FR-9 (one deterministic board, viewer-personalized) | M6 | Partial | Byte-identity verification method unspecified — which bytes are invariant vs the varying `current` default (R1-F5); URL/var-state "no write" boundary unclarified (R1-F9). |
| FR-10 (additive spec model) | M1 | Partial | Additive fields listed, but the `panels min_length=1` invariant would reject a layout-only v2 spec (R1-S9), contradicting "untouched until opt-in". |
| FR-11 (graceful version handling) | M5 (OQ-4) | Partial | Shipped `check_version()` is major-only (`grafana_client.py:91`) — cannot gate on 13.1 minor / `dashboardSectionVariables`; M5 doesn't name the client change (R1-F1/R1-S3). |
| NR-6 (not a full v2 library) | (none) | Missing | No milestone enforces rejecting out-of-scope v2 constructs; FR-7 validator could pass arbitrary v2 keys (R1-F7). |
| OQ-1 (provision API for v2) | M0 | Partial | M0 verifies it, but "neither endpoint accepts v2" degrade path is absent (R1-S1). |
| OQ-2 (emit strategy) | M0 + Design notes | Full | Python-side v2 emitter recommended; NR-5 alignment stated. |
| OQ-3 (section-vars enablement) | M0, M4 | Partial | Toggle-default verification planned, but the #122553 limitation is not a build-time guard (R1-F6). |
| OQ-4 (degradation policy) | M5 | Partial | Decision (refuse vs classic fallback) still open; blocked on the minor-version probe (R1-S3). |
| OQ-5 (Workbook field granularity) | M6 | Full | Coarse row-collapse recommended for v1 with a clear rationale; verify step present. |
| OQ-6 (disclosure depth) | M6 | Full | Intro-first for v1 recommended. |
| OQ-7 (scope of first cut) | M6 → M7 | Full | Broad capability first, Workbook-audience as proof, then M7 broadens. |

## Requirements Coverage Matrix — R2

Analysis only (not triage). Incremental delta from R1 — re-scores rows where R2 findings change the assessment; rows not mentioned are unchanged from R1. Grounded against Era 1 commit `3f86b72c` on `feat/workbook-audience-personalization`.

| Requirement | Plan Step(s) | Coverage | R2 Delta / Gaps |
| ---- | ---- | ---- | ---- |
| FR-1 (additive v2 emit target) | M1 | Partial | Unchanged from R1. `DashboardSpec.panels min_length=1` conflict (R1-S9) still open. |
| FR-5 (deterministic + $0) | M1 | Partial | R1 gap (serializer fork) unchanged. R2-S7 adds: write-path atomicity must route through `persist_dashboard` to inherit `output.py`'s atomic tmp-replace. |
| FR-7 (schema-aware validation) | M5 | Partial | R2 worsens coverage assessment: `json_validator.py:69` range-check fires on v2 boards (`schemaVersion` absent → `None not in range(36,42)` = True → error). M5 must add a schema discriminator FIRST (R2-S4); this is a blocker not just a gap. |
| FR-8 (audience personalization) | M6 | Partial | R2 adds: the Era 1 🛡️ badge (`_AUDIENCE_DEFAULT_DISPLAY`, confirmed in `3f86b72c`) and the v2 row-collapse are different mechanisms with no stated coexistence contract (R2-S5). OQ-5 "coarse" recommendation is sound but incomplete without this. |
| FR-9 (one deterministic board, viewer-personalized) | M6 | Partial | Unchanged from R1 (byte-identity AC missing). R2-F1 in requirements adds the Era 1 badge coexistence gap as a second open item. |
| FR-11 (graceful version handling) | M5 (OQ-4) | Partial | R2 adds: M0 must record the exact Grafana build string (R2-S2) so FR-11's "detect" step has a version-pinned baseline; without it, a 13.1.x minor rename is undetectable. |
| NR-6 (not a full v2 library) | (none) | Missing | Unchanged from R1 — no milestone enforces out-of-scope construct rejection. |
| OQ-1 (provision API for v2) | M0 | Partial | R2-S3 adds: M0 must record a formal go/no-go decision matrix with all three OQ-1 outcomes (accept via `/api/dashboards/db` \| resource API required \| neither), not just prose. Current M0 "Output" bullet covers only outcome 1 and outcome 2. |
| OQ-5 (Workbook field granularity) | M6 | Partial | Downgraded from R1's Full: Era 1 `_manifest_section` (one `text` panel per domain) confirmed; the coarse row-collapse hides the whole-domain panel, not individual rows. The recommendation is sound but the Era 1 🛡️ badge coexistence is unstated. |
