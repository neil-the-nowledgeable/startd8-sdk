# Benchmark Analyst Onboarding Persona — Requirements

**Version:** 0.3 (Post architecture-discovery — declarative-loader pivot)
**Date:** 2026-06-14
**Status:** Draft
**Owner:** neil-the-nowledgeable
**Relates to:** `REQUIREMENTS.md` (det-obs, FR-7/9/12), `PLAN.md` (P3), `benchmark.contextcore.yaml`,
the benchmark scoring data (`aggregate.json`/`cells.json`), parent benchmark reqs (FR-11/37/47/52)

---

## 0. Planning Insights (Self-Reflective Update)

> The planning pass read `portal_spec_builder`'s real section-builder + persona plumbing. The biggest
> correction: the "declarative persona" mechanism is **overspecified** for one persona, and the static
> analytical sections are **trivial** (a proven markdown-table-in-text-panel idiom).

| v0.1 Assumption | Planning Discovery | Impact |
|-----------------|-------------------|--------|
| FR-9: pull the declarative (manifest-sourced) persona mechanism forward to add `analyst` | The **section builders are code regardless** (the analytical sections don't exist), and the persona *definition* is just **2 dict entries** (`_PERSONA_SECTIONS` + `_PERSONA_VALUE`) + section gates in `build_portal_spec`. A declarative loader is far more plumbing for marginal benefit on ONE persona. | **FR-9 narrowed to Option A (hard-code `analyst`).** Declarative persona authoring stays the deferred FR-9 enhancement — a separate, clearly-scoped next step, not required to ship the analyst persona. |
| FR-11: static-from-aggregate panels — feasible but uncertain how | **Proven idiom:** section builders render **markdown tables inside `_text_panel(title, content, row)`** from data (`_build_objectives_panels`, `_build_alert_inventory_panels`). Helpers `_text_panel`/`_badge` are reusable. | FR-11 confirmed **trivial + $0/offline**: leaderboard/distribution/exclusions/discrimination = build a markdown table from `aggregate.json` → `_text_panel`. No live data, no Prometheus, no FR-18. |
| (implicit) the analyst's data threads via a new builder signature | Section builders take `(metadata)` / `(report)` etc.; `build_portal_spec` calls them with those. **Thread `aggregate`/`cells`/`scoring` via `metadata`** — no signature change to `build_portal_spec`. | New builders are `_build_*_panels(metadata)`; `generate_onboarding_portal` reads the run's `aggregate.json` into `metadata["aggregate"]`. |
| (P3 carryover) the objectives metadata keys are `objective/metric/target/unit` | `_build_objectives_panels` reads **`description`/`metricKey`/`target`/`unit`** — P3's keys were wrong, so the manager/executive "Objectives" panel renders "—". | New FR-16: fix the P3 objectives metadata keys (small bug the analyst work surfaced). |

**Resolved open questions:**
- **OQ-1 → Static markdown tables in `_text_panel`** (proven). No live data needed for the analyst portal.
- **OQ-2 → Thread aggregate data via `metadata`** (`metadata["aggregate"]`); new builders take `metadata`.
- **OQ-3 → Option A (hard-code `analyst`)** — 2 dict entries + 6 section builders + 6 gates. Declarative FR-9 deferred.
- **OQ-4 → `analyst` is genuinely new** — none of operator/engineer/manager/executive fit (it's analytical).
- **OQ-5 → Static median+IQR table suffices** for onboarding; a real histogram is FR-12 (live) territory.
- **OQ-6 → The generate call takes manifest + run dir** (like P1+P3); confirmed.

*Still open: OQ-7 (added) — whether to also fix the P3 objectives keys now (FR-16) or separately.*

---

## 0.1 Architecture Discovery (v0.3 — flips FR-9/FR-10 back to declarative)

> A hardcoding-elimination pass (inventory of `portal_spec_builder` + the polish pattern + the kickoff/
> declarative inputs) found the non-hardcoded **home already largely exists** — so the declarative
> persona loader v0.2 deferred is actually the *cheaper, correct* path AND the user's explicit goal.

| v0.2 Conclusion | Architecture Discovery | v0.3 Impact |
|-----------------|------------------------|-------------|
| FR-9 narrowed to **hard-code `analyst`**; declarative deferred (FR-10) | (a) The persona hardcoding = just **two dicts** (`_PERSONA_SECTIONS` :29-51, `_PERSONA_VALUE` :169-226). (b) The section→builder binding is **already a convention-registry** (`if "X" in sections` → `_build_X_panels`) — moving personas to data **auto-unlocks all sections**. (c) The home **exists**: `.contextcore.yaml personas[]` (we added it) + the `benefits.yaml` schema (pain_point/value_received already declarative) + the retail-demo `onboarding-index` section_sets pattern. (d) The **polish** pattern to copy = registry + DEFAULT + drift-check, but polish's *gap* is exactly ours (themes are code) — the fix is the **YAML loading polish lacks**. | **FR-9/FR-10 FLIP:** build a thin **persona-config loader** (manifest `personas[]` → hardcoded-dict fallback, the polish `DEFAULT_THEME` precedence). Then `analyst` (and the existing 4 personas) become **DATA**, not code. Net-new code = the loader + the unavoidable analytical section builders. |

**Correction to a framing assumption:** the polish capability is **selection-driven, not objective-driven**
(it applies a chosen `--theme`; it does not read objectives/requirements). So there is no "polish reads
objectives" pattern to copy — objectives live in the ContextManifest (`strategy.objectives`) / portal
`metadata["objectives"]`. What we copy from polish is the **registry + default-fallback + drift idiom**.

---

## 1. Capability Test Findings (what the existing onboarding-dashboard capability does, outside OB)

> Verified hands-on by generating the benchmark's persona portals (P3) — not the Online Boutique demo.

- **The capability** = `observability/portal_spec_builder.py`: `build_all_portal_specs(business,
  services, report, metadata)` → one `DashboardSpec` per persona → `DashboardCreatorWorkflow` →
  Grafana JSON. Dogfood-proven: 4 benchmark persona portals compiled ($0).
- **Personas are hard-coded:** `_PERSONA_SECTIONS` = {operator, engineer, manager, executive} +
  `_PERSONA_VALUE` (hard-coded value props). **No "analyst"**, no manifest-sourced persona mechanism
  (the deferred FR-9).
- **Fixed 10-section vocabulary**, each a `_build_*_panels` builder: overview, services, objectives,
  alerts, dashboards, communication, security, quality, health, provenance.
- **Panels are mostly static `text`/`stat`** — summaries of *declared context*, not live analytical
  charts. (The "Quality Metrics" panel is a text panel, not a quality-distribution chart.)

**Conclusion:** the existing capability is an *onboarding-orientation* portal. A Benchmark Analyst —
who supervises **scoring** and does **deeper analysis** — needs (a) a **new persona definition** and
(b) **new analytical sections** the 10-section vocabulary lacks, over the benchmark's rich scoring data.

### Gap table

| Component | Current State | Gap for the analyst persona |
|-----------|--------------|------------------------------|
| Persona definition | 4 hard-coded personas | No "analyst"; adding one = code (Option A) or declarative (FR-9, Option B) |
| Section vocabulary | 10 builders, static text/stat | Missing analytical sections: scoring-methodology, leaderboard, quality-distribution/IQR, exclusions, service-discrimination, deeper-analysis levers |
| Value props | hard-coded `_PERSONA_VALUE` | No analyst value prop; sourcing from manifest = FR-9 |
| Data | static summaries of declared context | The analyst's data is `aggregate.json`/`cells.json` (scoring rollups) — must be read at generation time |

---

## 2. Requirements

### Section A — The Benchmark Analyst persona (what they supervise + deeper analysis)

- **FR-1.** Define a **`analyst`** onboarding persona whose portal orients a benchmark analyst to:
  **(i)** the scoring methodology, **(ii)** the current results posture + its caveats, **(iii)** the
  reliability signals, **(iv)** the exclusions, **(v)** the per-model/per-service breakdowns, and
  **(vi)** the deeper-analysis levers. The persona's value prop = "supervise the scoring; know where
  it saturates, what's excluded, and where to dig deeper."
- **FR-2.** The analyst persona's **section set** (composing existing + new sections):
  `overview` (reuse) + `scoring-methodology` (new) + `leaderboard` (new) + `quality-distribution`
  (new) + `exclusions` (new) + `service-discrimination` (new) + `deeper-analysis` (new) +
  `provenance` (reuse).

### Section B — New analytical sections (the vocabulary additions)

- **FR-3. `scoring-methodology`** — orient the analyst to: the composite formula (compile gate +
  contract 0.4 / imports 0.2 / stubs 0.2 / semantic 0.2), **composite vs structural** quality, the
  `pass_threshold` (0.5), and the compile-gate floor. Static text from the run's `run-spec.json`
  (`scoring_formula`) + methodology constants.
- **FR-4. `leaderboard`** — per-model **quality (median + IQR)**, **cost**, and **cost-per-quality**,
  ranked. From `aggregate.json.by_model`. Surfaces the saturation finding (composite ~1.0 → **cost is
  the differentiator**).
- **FR-5. `quality-distribution`** — quality **median + IQR** (variance = reliability) per model and
  per service; flags low-N / high-IQR cells as low-confidence. From `aggregate.json` +
  `overall.quality_iqr`/`catastrophic_count`.
- **FR-6. `exclusions`** — the **infra_fail / integrity** breakdown and **why they're excluded** from
  model pass/fail (not model failures). From `aggregate.json.overall.infra_fail_count` + the per-cell
  `exclusion_reason`. Critical so the analyst does not mis-score a key/quota outage as model failure.
- **FR-7. `service-discrimination`** — which services **separate** the models (per-service quality
  spread); surfaces `checkoutservice` as the discriminating service. From `aggregate.json.by_service`/
  `by_service_model`.
- **FR-8. `deeper-analysis`** — pointers/links to the analyst's deeper-analysis levers: **replayable
  re-scoring from artifacts** (parent FR-37), **weight-sensitivity ±0.1** (FR-11), **blind
  human-validation sample** (FR-52), **contamination probe** (FR-47), and the raw data locations
  (`cells.json`, the tracking spans, the join contract).

### Section C — Persona mechanism (the FR-9 decision)

- **FR-9.** *(v0.3 — declarative loader, A1.)* Build a thin **persona-config loader**
  (`observability/persona_config.py`): `load_personas(manifest_dict | None) -> {persona_id:
  PersonaProfile}` where `PersonaProfile = {sections: list[str], value: {title, pain, headline,
  content}}`. **Precedence (the polish `DEFAULT_THEME` idiom):** a persona declared in the manifest's
  `personas[]` overrides; otherwise fall back to the hardcoded `_PERSONA_SECTIONS`/`_PERSONA_VALUE`
  (which become the built-in default). Wire `build_portal_spec` / `build_all_portal_specs` to read
  through the loader instead of the dicts directly. **No regression** when the manifest declares no
  personas (pure fallback). This de-hardcodes the existing 4 personas too.
- **FR-10.** *(v0.3 — declare `analyst` as DATA, A2.)* Add `analyst` to the benchmark
  `.contextcore.yaml` `personas[]` with its `value` (title/pain/headline/content) + `sections` (FR-2).
  No persona code — the loader (FR-9) renders it. The hardcoded value-prop dollar figures
  (`$247K/yr`…, wayfinder-demo content) are NOT inherited; the benchmark declares its own.

### Section D — Data path (the recurring FR-18 question, scoped for onboarding)

- **FR-11.** *(v0.2 confirmed trivial.)* The analytical sections render as **markdown tables inside
  `_text_panel(...)`**, built from the run's `aggregate.json`/`cells.json` at generation time — the
  proven idiom (`_build_objectives_panels`/`_build_alert_inventory_panels`); reuse `_text_panel`/
  `_badge`. **$0, offline, no Prometheus, no FR-18.** Aggregate data threads via `metadata["aggregate"]`.
- **FR-12.** A **live, interactive analytical dashboard** (queryable quality histograms over exported
  metrics) is a **separate, heavier concern** — out of scope; note it as future (it would need the
  FR-18 data path).

### Section E — Reuse & integration constraints

- **FR-13.** Reuse `portal_spec_builder` + `DashboardCreatorWorkflow` + the P3 `generate_onboarding_portal`
  pipeline. Net-new = the analyst persona definition + the new section builders + the static-from-aggregate
  data reads.
- **FR-14.** Generation MUST be **$0 and offline** (the static-from-aggregate path needs no live stack);
  compiling to Grafana JSON still needs jsonnet+mixin `vendor/` (the P1 guard applies).
- **FR-15.** The analyst portal MUST take a **run dir** input (where `aggregate.json`/`cells.json` live);
  with no run dir, the analytical sections degrade to a "run a benchmark first" placeholder.
- **FR-16.** *(v0.2 NEW — bug surfaced by planning.)* Fix the P3 `_benchmark_objectives()` metadata
  keys to match what `_build_objectives_panels` reads (`description`/`metricKey`/`target`/`unit`), so
  the existing manager/executive portals stop rendering "—" in the Objectives table.

---

## 3. Non-Requirements

- **NR-1.** Not building a live/interactive quality-exploration dashboard (FR-12 defers it).
- **NR-2.** Not changing the scoring methodology or the aggregate/cells schema (consume them as-is).
- **NR-3.** Not generating the analyst's *conclusions* (bucket 4 content) — only the structural
  orientation portal + the data summaries.
- **NR-4.** Not building a generic persona-authoring UI; declarative personas are YAML in the manifest.
- **NR-5.** Not re-running or re-scoring the benchmark (the analyst portal reads existing artifacts).

## 4. Open Questions

- **OQ-1.** ✅ **RESOLVED:** static markdown tables in `_text_panel` (proven idiom). No live data.
- **OQ-2.** ✅ **RESOLVED:** thread aggregate data via `metadata["aggregate"]`; builders take `metadata`.
- **OQ-3.** ✅ **RESOLVED:** Option A (hard-code `analyst`); declarative FR-9 deferred (FR-10).
- **OQ-4.** ✅ **RESOLVED:** `analyst` is genuinely new (analytical; no built-in fits).
- **OQ-5.** ✅ **RESOLVED:** static median+IQR table suffices for onboarding; histogram = FR-12 (live).
- **OQ-6.** ✅ **RESOLVED:** the generate call takes manifest + run dir (P1+P3 pattern).
- **OQ-7.** *(new)* Fix the P3 objectives-key bug **now** (FR-16, while in this code) or as a separate
  commit? Lean: now — it's one line and the analyst work is in the same module.

---

*v0.2 — Post-planning self-reflective update. Core correction: the declarative persona mechanism is
overspecified for one persona (FR-9 narrowed to hard-code `analyst`; declarative deferred as FR-10);
the static analytical sections are a trivial proven idiom (FR-11). 6 open questions resolved, 1 added;
1 new requirement (FR-16, a P3 bug planning surfaced). The analyst persona = Option-A code: 2 dict
entries + 6 markdown-table section builders fed by `aggregate.json` via metadata.*
