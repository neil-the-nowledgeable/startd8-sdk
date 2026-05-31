# Observability Descriptor Spine — Shared Requirements

**Version:** 1.1
**Date:** 2026-05-31
**Status:** Normative (single source of truth for the cross-category descriptor spine; R2+R3 triaged)
**Referenced by:** `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` (cat 5), `OBSERVABILITY_PROJECT_REQUIREMENTS.md`
(cat 4), and (for vocabulary alignment) `OBSERVABILITY_ARTIFACT_TAXONOMY_REQUIREMENTS.md`
(REQ-OAT-070a).

> **Why this doc exists.** The combined cat-4/5 CRP (R1) found that the descriptor schema change
> (`category`/`orientation`) and the descriptor↔emission parity test were described *narratively in
> both* the AI-agent and project docs but **owned normatively in neither** — and had *already drifted*
> (AAO-012 read as bijection, PRO plan 2.3 as subset). This document is the single owner. Both
> category docs reference these requirements **by ID** rather than restating them, so the contract
> cannot diverge. This is net-negative complexity: one definition replaces two-to-three partial
> restatements. Resolves CRP R1-F7/F8/F9 (both reqs docs) and R1-S1/S2/S3/S6 (both plans).

---

## REQ-OBS-SHARED-001 — Descriptor schema fields, enums, defaults

The `_OTEL_DESCRIPTORS` telemetry-declaration manifest (`observability/manifest.py`) is the shared
spine across observability categories. Its `MetricDescriptor` and `SpanDescriptor` dataclasses MUST
carry two axis fields, defined **once, here**:

| Field | Type | Enum domain | Default | Notes |
|-------|------|-------------|---------|-------|
| `category` | str | `service_observability` \| `business_observability` \| `pipeline_innate` \| `project_observability` \| `ai_agent_observability` | `""` (unset) | The 5-category observability taxonomy. Values match the taxonomy doc exactly. |
| `orientation` | str | `system` \| `human` \| `bridge` | `""` (unset) | Who consumes: `system` (metrics/SLOs/SLIs), `human` (dashboards), `bridge` (alerts/notification policies). |

- **Additive & backward-compatible.** Both fields default to `""` so every existing descriptor still
  constructs; `to_dict()`/`from_dict()` MUST emit/accept them only when non-empty (mirrors the existing
  optional-field pattern). Verified: `MetricDescriptor` (manifest.py:47) and `SpanDescriptor` (94)
  currently have **neither** field, so the addition is purely additive.
- **Collector pass-through is part of the change, not a follow-up (R3-F1, critical).** Adding the
  dataclass fields is insufficient: `collect_metric_descriptors()`/`collect_span_descriptors()`
  (`collector.py`) instantiate descriptors copying only a **fixed set of legacy fields**, so a
  `_OTEL_DESCRIPTORS` entry annotated with `category`/`orientation` is **silently dropped** from the
  generated manifest. The schema change MUST include collector pass-through of the new axes (and MUST
  preserve existing optional fields like `prometheus_name`/`dashboard_hints`, which the collector must
  not drop). This co-lands in the keystone (REQ-OBS-SHARED-005).
- **Empty defaults are a compatibility bridge, not an accepted end state (R3-F5).** `category=""`/
  `orientation=""` exist only so legacy descriptors construct during bootstrap. After the keystone, a
  completeness gate MUST report any Metric/Span descriptor with unset axes **by source file**; empty
  axes are allowed only for an explicit, shrinking grandfather list — never as a silent "unknown"
  path that leaves generated dashboards/coverage incomplete.
- **Enum domains have ONE code-level source of truth (R3-F7, R2-F8).** The enum tables above are
  *documentation of* a single code-level constant set (one module exporting the `category`/
  `orientation` enums) imported by **both** descriptor-manifest validation and taxonomy-registry
  validation. Docs (this one + the taxonomy) cite that source; **referencing docs MUST NOT restate the
  enum domains** (ID-reference only) — restating them recreates the drift vector the spine was extracted
  to remove. Audit: only this doc + the taxonomy doc may contain the literal value lists (fixes the
  residual cat-5 blockquote restatement, R2-F8).
- **`category` polysemy — cleanup is REQUIRED (REQ-OBS-SHARED-001a, R2-F4).** A *different* `category`
  field already exists on `EventTypeDescriptor` (manifest.py:137) with an 8-value **instrument-grouping**
  vocabulary (`agent, cost, pipeline, truncation, job, enhancement, storage, system`) — NOT this
  5-category taxonomy, though `agent`/`pipeline` overlap lexically. To stop one module using `category`
  for two unrelated axes, the `EventTypeDescriptor` field **MUST** (not should — the collision is live,
  CAT45 §C) be renamed to `event_group`. **Backward-compat:** `from_dict` MUST accept the legacy YAML
  key `category` as an alias for `event_group` for one release; `to_dict` emits only `event_group`.
  Named consumers to migrate: `collect_event_types()` (collector.py:157),
  `tests/unit/test_observability_manifest.py:82`.

**Validation:** a schema unit test asserts both fields exist on Metric/Span descriptors with the named
enum domains and `""` defaults; **a `_OTEL_DESCRIPTORS` entry carrying `category`/`orientation` survives
`generate_manifest().to_dict()` round-trip** (collector pass-through, R3-F1) and `prometheus_name`
survives for metrics; old YAML with `event_types[].category` deserializes via the `event_group` alias
(R2-F4); the post-keystone completeness gate fails with a source-file list for any unset axis outside
the grandfather list (R3-F5).

---

## REQ-OBS-SHARED-002 — Descriptor↔emission parity, kind-aware

A single parity-test mechanism enforces that the descriptor manifest does not silently lie. The
relation is **parameterized by signal kind** (resolving the bijection-vs-subset drift, CRP R1-F6/F3/
S2):

| Signal kind | Relation | Rationale |
|-------------|----------|-----------|
| **Metrics** (`MetricDescriptor`) | **Bijection** — every declared metric ⇔ an actual `meter.create_*` site, and every created instrument is declared | Metric instruments are a closed, hand-declared set; a declared-but-unemitted (or emitted-but-undeclared) metric is a real defect. |
| **Spans** (`SpanDescriptor` attributes) | **Subset** — declared attributes ⊆ emitted attributes | Span attribute sets are **open** (ad-hoc attrs are legitimate); requiring bijection would force declaring every incidental attribute. |

- The shared parity helper MUST document this one kind-aware relation; both category plans reference
  **this requirement** rather than restating a relation.
- **"Parity" is a parent of named sub-checks, not one vague gate (R3 focus-6).** Each fails precisely:
  (a) *collection coverage*, (b) *metric identity*, (c) *emitter-universe coverage*, (d) *span
  name-pattern match*, (e) *attribute relation*. They are specified below.

**Sub-check (b) — metric identity is dual-name (R3-F2).** Bijection compares **both** the canonical
OTel name **and** the exported/query name (`prometheus_name`, or the documented dot→underscore
normalization). The helper MUST reject **exported-name collisions even when canonical names differ**
(`startd8.cost.total` vs `startd8_cost_total` are distinct in code but dangerously close on the surface
operators/dashboards query).

**Sub-check (c) — the parity universe is the repo, not `_INSTRUMENTED_MODULES` (R3-F3).** A helper that
walks only `collector.py`'s hardcoded module list can pass while whole emitting packages stay
undeclared. The check MUST be a repo-wide `meter.create_*` call-site scan (or an explicit **owned
exclusion registry** with owner/rationale/expiry); adding a new emitter without a descriptor or an
exclusion entry fails. Known undeclared emitters to seed it: `complexity/classifier.py`,
`element_registry.py` (~384–401), and the packages flagged in R3-F3 (`micro_prime`, `security_prime`,
`utils/artifact_inventory.py`, `workflows/builtin/plan_ingestion_mottainai.py`).

**Sub-check (d) — span name-pattern parity (R3-F4).** Beyond attribute subset, every
`SpanDescriptor.name_pattern` MUST match ≥1 runtime `start_as_current_span` site (or be declared
`attributes_dynamic=True`), and every stable runtime span family MUST have a descriptor. This catches
the real CAT45 §B-4 mismatch (`artisan.workflow.{id}.phase.{phase}` declared vs `phase.{phase.value}`
emitted). `attributes_dynamic=True` requires a name-pattern match but waives the attribute check.

**Metric-bijection exceptions (R2-F2) — strict bijection would false-positive on legitimate patterns:**
- **indirect emitters** — a recording module delegating to a declaring module is matched at the
  declaration site (e.g. `costs/tracker.py` → `costs/otel_metrics.py` `_OTEL_DESCRIPTORS`, CAT45 §D);
- **observable gauges** (`create_observable_gauge`, session_tracking.py:384, element_registry.py:401)
  — matched by the **owning module's declaration site**, not callback frequency;
- **deprecated opt-in Prometheus path** (`session_tracking.py:336–337, 438–503`) — excluded until its
  retirement (AAO Phase 0.3), or counted as an alternate producer behind the mutual-exclusion guard.

**Required-span-attribute allowlist (R2-F7).** General span attrs stay subset, but **contract/gate
attrs** (e.g. `phase.name`, `phase.status` where forward-manifest/gate contracts require presence) MAY
be allowlisted as **bijection-on-that-subset** — declared-and-absent on the emitted span is a failure.

- **First catch (already known):** the live `complexity.tier_distribution` histogram
  (`complexity/classifier.py:24`, recorded at :277) is **emitted but not declared** — exactly what
  sub-check (c)/bijection surfaces; the fix is to **declare** it, not delete it (corrects the cat-4
  plan's stale "dead histogram" claim; CAT45 §A-1).

**Validation:** the parity test names each failing sub-check (a)–(e); passes on the real manifest with
the indirection/observable-gauge exceptions; **fails** on the tier histogram until declared, on an
exported-name collision, on a `name_pattern` with no runtime site, and on an allowlisted contract attr
that is declared but absent; the relation is documented identically wherever referenced.

---

## REQ-OBS-SHARED-003 — Registry layering: telemetry-declaration vs artifact-dispatch

Resolves the projection question (CRP R1-F9/F3/S3/S6): are descriptor `category`/`orientation`
*authoritative* or *projections* of the taxonomy `declared_type`-keyed registry (REQ-OAT-070a)?

**Resolution — they are two distinct layers that share a vocabulary, not one registry:**

- The **descriptor manifest** (`_OTEL_DESCRIPTORS`) is the **telemetry-declaration** layer: *what
  metrics/spans the SDK emits.* Its `category`/`orientation` are **authoritative for telemetry
  signals**.
- The **taxonomy registry** (REQ-OAT-070a) is the **artifact-dispatch** layer: *what artifacts get
  generated* (`declared_type` → generator/validator/output_path), with `category`/`orientation` as
  **derived projections of a registry row**.
- They do **not** share rows — a telemetry signal (`startd8.cost.total`) is not an artifact
  `declared_type` (`alert_rule`, `dashboard`, `slo`). So there is **no parallel-table drift**: nothing
  is independently maintained in two places. REQ-OAT-070a's "never independently maintained" rule is
  about the *artifact-dispatch* row's projections and is not violated by the telemetry layer.
- **What they DO share is the enum vocabulary** (REQ-OBS-SHARED-001): the `category` (5-value) and
  `orientation` (3-value) domains are defined once and consumed by both layers. A reconciliation
  assertion is therefore **vocabulary-level, not row-level**: any value used by either layer MUST be
  a member of the shared enums (the single source-of-enum check, REQ-OBS-SHARED-001), and CI rejects a
  stray value in either layer.
- **Scope is exactly two layers — `MetricDescriptor`/`SpanDescriptor` vs artifact-dispatch rows
  (R2-F1).** `ObservabilityManifest` *also* carries `event_types` (`EventTypeDescriptor`, manifest.py:279)
  and `dashboards` (`DashboardRef`), collected by `collector.py`. These are **out of scope** of this
  layering model: `event_types` carries `event_group` (the instrument-grouping axis, SHARED-001a), not
  the taxonomy axes; `DashboardRef` is a generated-artifact pointer, not a descriptor. They participate
  in neither the row-disjointness nor the vocabulary-reconciliation assertion.
- **Conceptual name overlap is permitted, not drift (R2-F5).** The *same metric name* MAY legitimately
  appear in `MetricDescriptor.name`, `DashboardRef.metrics_used`, and onboarding `manifest_declared[]` —
  this is intentional (a dashboard references declared metrics by design). The disjointness assertion is
  on **registry row keys** (`declared_type` vs instrument name), **not** on name uniqueness across the
  ecosystem; implementers MUST NOT chase "duplicate row" bugs on shared names.

**Validation:** a test asserts every `category`/`orientation` value in the descriptor manifest and the
taxonomy registry is a member of the shared enums; no overlapping `declared_type`↔telemetry-signal row
exists (key-disjoint by construction); a worked example shows `startd8.cost.total` appearing in a
descriptor **and** a `DashboardRef.metrics_used` **and** artifact metadata **passes** both checks
(R2-F5); the `event_types`/`dashboards` surfaces are explicitly excluded from the scope assertion (R2-F1).

---

## REQ-OBS-SHARED-004 — Emit-vs-cede boundary (one generator, two manifests)

Makes ownership implementable by a **single** artifact generator reading both manifests (CRP R1-F8
both docs; R1-F1/S4 project; mirrors taxonomy REQ-OAT-011/052). **Routing is driven by an explicit
`route_state` provenance field, NOT inferred from `category` (R3-F6)** — `category` answers "what domain
is this for," not "who emits it / why is it skipped." Every signal/artifact row carries one
`route_state` and a user-visible status string. The emit/cede asymmetry is two of **four** states
(R2-F3): the cat-4/cat-5 binary was incomplete.

| `route_state` | Meaning | Generator behavior | Coverage |
|---------------|---------|--------------------|----------|
| `sdk_emitted` | SDK emits in-process (cat 5 — every metric has a `meter.create_*` site) → its own declare-don't-guess producer | **Produced** artifact; no `skip_reason`. Dissolves taxonomy REQ-OAT-025 exporter dependency *for SDK-emitted metrics only*. | counted |
| `contextcore_owned` | SDK produces raw signals; ContextCore owns the `contextcore_*` gauges + burndown (cat 4) | **Honest-skip**: `skip_reason=owned_elsewhere`, `owner=contextcore`, **no** `source_checksum` | **excluded** from `artifact_type_coverage` denominator (REQ-OAT-052) |
| `declared_unimplemented` | A declared artifact `declared_type` with no generator yet (already emitted by `_record_unimplemented_artifact_types`, artifact_generator.py ~1986) | **Honest-skip**: `skip_reason=unimplemented` (REQ-OAT-052) | excluded per REQ-OAT-052 rules |
| `external_convention` | Onboarding `convention_metrics` (HTTP RED, mesh, etc.) — produced artifacts referencing metrics with **no** SDK `meter.create_*` site (not SDK-emitted, not a ContextCore cede) | **Produced** artifact referencing an externally-observed metric | counted per REQ-OAT-052 |

- The cede record's **field-level contract** (`skip_reason`/`owner` + denominator-exclusion) is
  REQ-OAT-052; this requirement binds cat-4 to it so a cede doesn't read as `coverage<1.0`.
- **Stale-metadata handling:** when onboarding metadata *still lists* `contextcore_task_*` as declared
  (as run-007 output does today), the generator MUST classify them as `contextcore_owned` on read, not
  as startd8-emitted (CRP project R1-F5).

**Validation:** every row in a generated report carries a `route_state` + user-visible status text
(R3-F6); a generator fed both manifests routes cat-5 metrics `sdk_emitted`, `contextcore_*`
`contextcore_owned` (coverage=1.0), a declared-but-generatorless type `declared_unimplemented`, and a
`convention_metrics` entry `external_convention`; changing a row's `category` without its `route_state`
does **not** change ownership behavior; feeding the current run-007 metadata yields `contextcore_owned`,
not mis-attribution.

---

## REQ-OBS-SHARED-005 — Keystone merge invariants (behavior, not choreography)

This requirement states **testable merge invariants** only; the per-phase step choreography lives in
the cat-4/5 **plans** (R2-F10 — SHARED-005 was the weakest req because it was process prose; the plans
are the operational source). The invariants resolve the double-add hazard (CRP R1-S1) plus the
gaps R2/R3 surfaced:

- **I1 — one diff (anti-double-add).** Exactly one diff in history adds the SHARED-001 schema fields
  **and** the SHARED-002 parity helper; the cat-4 plan's traceability shows a *dependency* on that
  landing, not a duplicate add. (Cat 5 owns the descriptor manifest most directly.)
- **I2 — collector pass-through co-lands before any annotation (R3-F8, R3-F1).** The keystone diff MUST
  include: dataclass fields **+** collector pass-through **+** a `generate_manifest().to_dict()`
  round-trip fixture proving an annotated descriptor's axes survive. Cat-4 may depend on "schema landed"
  only once this holds — otherwise it depends on a state that silently emits empty axes.
- **I3 — reverse dependency: attribute names stable before parity enrollment (R2-F6).** The cat-4
  PRO-008 span-attribute rename (`task.*` → `codegen.task.*`, CAT45 §B-3) MUST land **before** cat-4
  project spans enter the SHARED-002 subset check — otherwise parity encodes the `task.status` polysemy
  as a *passing* subset. Sequenced as a cat-4 Phase-0 prerequisite, not a forward-only "cat-5 first".
- **I4 — parity bootstrap gate (R2-F9).** The keystone MAY merge with the parity helper in **bootstrap
  mode**: an explicit allowlisted known-gap list (seed: `complexity.tier_distribution`,
  `element_registry` instruments) that the helper reports but does not hard-fail on. Removing an item
  from the allowlist MUST co-occur with declaring that descriptor in the same PR; the list shrinks to
  empty, at which point parity is hard-fail. This avoids a chicken-and-egg where Phase 1 can't land
  until all 11+ emitting modules are clean in one commit.

**Validation:** I1 — exactly one schema+helper diff; I2 — keystone PR contains fields + collector
pass-through + round-trip fixture; I3 — cat-4 plan shows PRO-008 rename before span declaration and
parity fixtures use renamed attrs; I4 — a CI job documents the bootstrap allowlist and fails if an item
is removed without a corresponding descriptor declaration.

---

*v1.1 — Extracted from the combined cat-4/5 CRP R1 reconciliation (v1.0), then hardened by R2
(composer-2.5-fast) + R3 (GPT-5.5): all 18 suggestions applied. Key additions — collector pass-through
co-lands with the schema (R3-F1); parity is a parent of named sub-checks incl. dual-name identity,
repo-wide emitter universe, span name-pattern, and documented bijection exceptions (R2-F2, R3-F2/F3/F4);
SHARED-004 routing is a 4-state `route_state` provenance enum, not a cat-4/5 binary (R2-F3, R3-F6);
SHARED-005 trimmed to testable merge invariants (one-diff, collector-co-land, reverse-dep, bootstrap
allowlist) with choreography delegated to the plans (R2-F6/F9/F10, R3-F8); `event_group` rename is now
MUST + alias (R2-F4); one code-level enum source + no-restatement rule (R3-F7, R2-F8). Owns the
descriptor spine so the AI-agent and project docs reference it by ID and cannot drift. Grounded by
`OBSERVABILITY_CAT45_CODE_VERIFICATION.md`.*

---

## Appendix: Iterative Review Log (Applied / Rejected Suggestions)

This appendix is intentionally **append-only**. New reviewers (human or model) should add suggestions to Appendix C, and then once validated, record the final disposition in Appendix A (applied) or Appendix B (rejected with rationale).

### Reviewer Instructions (for humans + models)

- **Before suggesting changes**: Scan Appendix A and Appendix B first. Do **not** re-suggest items already applied or explicitly rejected.
- **When proposing changes**: Append them to Appendix C using a unique suggestion ID (`R{round}-F{n}`).
- **When endorsing prior suggestions**: If you agree with an untriaged suggestion from a prior round, list it in an **Endorsements** section after your suggestion table. This builds consensus signal — suggestions endorsed by multiple reviewers should be prioritized during triage.
- **When validating**: For each suggestion, append a row to Appendix A (if applied) or Appendix B (if rejected) referencing the suggestion ID. Endorsement counts inform priority but do not auto-apply suggestions.
- **If rejecting**: Record **why** (specific rationale) so future models don't re-propose the same idea.

### Appendix A: Applied Suggestions

All 18 R2+R3 suggestions accepted (each code-grounded; several converged). Bumped doc to v1.1.

| ID | Suggestion | Source | Implementation / Validation Notes | Date |
|----|------------|--------|----------------------------------|------|
| R2-F1 | Scope SHARED-003 to Metric/Span vs artifact-dispatch; event_types/dashboards out | composer-2.5-fast | SHARED-003 new scope bullet + validation exclusion | 2026-05-31 |
| R2-F2 | Metric-bijection exceptions (indirect emitters, observable gauges, Prom opt-in) | composer-2.5-fast | SHARED-002 exceptions block | 2026-05-31 |
| R2-F3 | SHARED-004 routing beyond binary (unimplemented + external/convention) | composer-2.5-fast | Merged into 4-state `route_state` table w/ R3-F6 | 2026-05-31 |
| R2-F4 | `event_group` rename SHOULD→MUST + `from_dict` alias | composer-2.5-fast | SHARED-001a upgraded; alias one release | 2026-05-31 |
| R2-F5 | SHARED-003: conceptual name overlap permitted (row-key disjointness only) | composer-2.5-fast | SHARED-003 bullet + worked-example validation | 2026-05-31 |
| R2-F6 | SHARED-005 reverse dep: PRO-008 rename before span parity | composer-2.5-fast | Invariant I3 | 2026-05-31 |
| R2-F7 | Required-span-attribute allowlist (bijection on contract attrs) | composer-2.5-fast | SHARED-002 allowlist block | 2026-05-31 |
| R2-F8 | No-restatement rule; fix cat-5 enum restatement | composer-2.5-fast | SHARED-001 enum-source bullet; cat-5 blockquote de-restated | 2026-05-31 |
| R2-F9 | SHARED-005 parity bootstrap allowlist gate | composer-2.5-fast | Invariant I4 | 2026-05-31 |
| R2-F10 | Trim SHARED-005 to merge invariant; choreography to plans | composer-2.5-fast | SHARED-005 reframed to I1–I4 (behavior, not process) | 2026-05-31 |
| R3-F1 | Collector pass-through (fields dropped otherwise) | GPT-5.5 | SHARED-001 critical bullet + round-trip validation; co-lands (I2) | 2026-05-31 |
| R3-F2 | Metric identity = canonical + exported name; collision check | GPT-5.5 | SHARED-002 sub-check (b) | 2026-05-31 |
| R3-F3 | Parity universe = repo-wide scan, not `_INSTRUMENTED_MODULES` | GPT-5.5 | SHARED-002 sub-check (c) + exclusion registry | 2026-05-31 |
| R3-F4 | Span name-pattern parity + `attributes_dynamic` semantics | GPT-5.5 | SHARED-002 sub-check (d) | 2026-05-31 |
| R3-F5 | Empty axes are compat-only; post-keystone completeness gate | GPT-5.5 | SHARED-001 bullet + validation | 2026-05-31 |
| R3-F6 | `route_state`/provenance enum; don't infer routing from category | GPT-5.5 | SHARED-004 `route_state` 4-state table | 2026-05-31 |
| R3-F7 | One code-level enum source imported by both validators | GPT-5.5 | SHARED-001 enum-source bullet | 2026-05-31 |
| R3-F8 | Keystone checklist: collector pass-through before annotation | GPT-5.5 | Invariant I2 | 2026-05-31 |

### Appendix B: Rejected Suggestions (with Rationale)

| ID | Suggestion | Source | Rejection Rationale | Date |
|----|------------|--------|---------------------|------|
| (none yet) |  |  |  |

### Appendix C: Incoming Suggestions (Untriaged, append-only)

#### Review Round R2 — composer-2.5-fast — 2026-05-31 20:00:00 UTC

- **Reviewer**: composer-2.5-fast
- **Date**: 2026-05-31 20:00:00 UTC
- **Scope**: R2 stress-test of cat-4/5 reconciliation spine (SHARED-001..005); code-grounded via `OBSERVABILITY_CAT45_CODE_VERIFICATION.md` and `startd8-sdk` `observability/manifest.py`, `collector.py`, `artifact_generator.py`, `complexity/classifier.py`, `element_registry.py`, `session_tracking.py`.

**Executive summary**

- Row-level key-disjointness (SHARED-003) **holds** for `declared_type` vs telemetry instrument names, but the manifest has **third surfaces** (`event_types`, `dashboards`) not covered by the two-layer model.
- `EventTypeDescriptor` is **outside** SHARED-001 taxonomy fields today; 001a's `event_group` rename is correct but **under-specified** for YAML consumers and tests.
- Metric **bijection** is directionally right but will **false-positive** without explicit rules for indirect emitters, observable gauges, and the deprecated Prometheus opt-in path.
- SHARED-004's cat-4/cat-5 binary is **incomplete** for a single generator: taxonomy `skip_reason=unimplemented` and convention-based onboarding metrics are real third routes.
- Landing sequence (SHARED-005) has a **reverse dependency**: PRO-008 `task.*` → `codegen.task.*` should precede span parity enrollment.
- Cat-5 requirements still **inline restate** enum domains despite SHARED-001 ownership — residual drift surface.
- Separate spine doc is **justified**; SHARED-005 is the weakest normative req (process-only) and should carry concrete merge gates.

---

**Focus ask 1 — Is SHARED-003 layer-separation actually true?**

- **Summary answer:** Partial — row keys are disjoint, but the manifest is not a two-layer-only model.
- **Rationale:** REQ-OAT-070a `declared_type` keys (`dashboard`, `alert_rule`, …) do not collide with telemetry instrument names (`startd8.cost.total`, `complexity.tier_distribution`). Verified in taxonomy vs `MetricDescriptor.name`. However `ObservabilityManifest` also carries `event_types` (`EventTypeDescriptor`, manifest.py:279) and `dashboards` (`DashboardRef`) collected by `collector.py` — neither is an artifact `declared_type` nor a `_OTEL_DESCRIPTORS` row. SHARED-003's validation ("no overlapping `declared_type`↔ telemetry-signal row") passes, but the **conceptual** overlap (same metric names referenced in `DashboardRef.metrics_used` and declared metrics) is intentional, not drift.
- **Assumptions / conditions:** Taxonomy registry and `_OTEL_DESCRIPTORS` remain separate key namespaces; onboarding `manifest_declared[]` metric names may appear in both telemetry and artifact metadata without sharing a row key.
- **Suggested improvements:** Explicitly scope SHARED-003 to telemetry-declaration vs artifact-dispatch **only**; add an out-of-scope note for `event_types`/`dashboards` or extend layering (see R2-F1, R2-F5).

**Focus ask 2 — Is kind-aware parity the right cut?**

- **Summary answer:** Mostly yes for the closed-set vs open-set split; metric bijection needs documented exceptions.
- **Rationale:** `complexity.tier_distribution` is exactly the intended first catch (emitted at classifier.py:277, undeclared) — bijection should **fail until declared**, not spuriously pass. But `costs/tracker.py` records into `costs/otel_metrics.py` (CAT45 §D), `element_registry.py` creates five instruments with no `_OTEL_DESCRIPTORS`, and `session_tracking.py` has a **reachable** deprecated Prometheus path (336–337, 438–503) mutually exclusive with OTel — strict bijection without exclusion rules will block the keystone merge or force premature deletion.
- **Assumptions / conditions:** Observable gauges (`create_observable_gauge`, session_tracking.py:384, element_registry.py:401) are matched by **declaration site** (module owning the callback), not callback invocation count.
- **Suggested improvements:** Add bijection exception table and optional required-span-attr allowlist (R2-F2, R2-F7).

**Focus ask 3 — Does SHARED-005 landing sequence survive?**

- **Summary answer:** Partial — forward dependency is correct; reverse deps and parity bootstrap need explicit gates.
- **Rationale:** Cat-4 span declaration needs SHARED-001 fields on `SpanDescriptor` → cat-5 keystone first (correct). Reverse: PRO-008 `task.status` polysemy (CAT45 §B-3) means cat-4 span attrs should use `codegen.task.*` **before** parity enrollment, or the subset check encodes the collision. Same branch + dependency edge is workable if cat-5 merges keystone before cat-4 span work; separate PRs are safer for review but not strictly required.
- **Assumptions / conditions:** Both plans stay on `feat/observability-followup-run007`; parity CI can ship in **bootstrap** mode listing known gaps before hard-fail.
- **Suggested improvements:** Document reverse dep and bootstrap mode (R2-F6, R2-F9).

**Focus ask 4 — References / duplication / EventTypeDescriptor consumers?**

- **Summary answer:** Partial — IDs resolve; residual enum restatement and 001a consumer impact remain.
- **Rationale:** All cited SHARED-001..005 IDs exist. Cat-5 requirements still blockquote the 5-value `category` enum (line ~178) despite deferring to SHARED-001 — drift surface. `EventTypeDescriptor.category` is serialized to YAML (`manifest.py:143`), read by `collect_event_types()` (`collector.py:157`), and tested in `tests/unit/test_observability_manifest.py:82`; rename to `event_group` without alias breaks round-trip unless `from_dict` accepts both keys.
- **Assumptions / conditions:** No external Wayfinder consumer hard-codes `event_types[].category` outside this repo (unverified).
- **Suggested improvements:** 001a compat shim + cat-5 enum dedup pointer (R2-F4, R2-F8).

**Focus ask 5 — Is SHARED-004 complete for one generator?**

- **Summary answer:** No — binary emit/cede misses taxonomy `unimplemented` skips and external/convention metrics.
- **Rationale:** `artifact_generator.py` already emits `skip_reason`-less skips for unimplemented declared types (`_record_unimplemented_artifact_types`, ~1986–2000); taxonomy REQ-OAT-052 defines `owned_elsewhere` \| `unimplemented`. Onboarding `convention_metrics` (HTTP RED, etc.) are **produced artifacts** referencing metrics with **no** startd8 `meter.create_*` site — neither cat-5 emit nor cat-4 cede. SHARED-004 table covers only SDK in-process vs ContextCore gauges.
- **Assumptions / conditions:** Generator reads onboarding metadata + SDK manifest together; convention-based metrics are out-of-SDK-declaration scope.
- **Suggested improvements:** Extend routing table with third states referencing REQ-OAT-052 (R2-F3).

**Focus ask 6 — Adversarial: weakest SHARED req / spine doc justified?**

- **Summary answer:** SHARED-005 is weakest (process-only); separate spine doc is **not** accidental complexity — it fixes proven R1 drift.
- **Rationale:** SHARED-001–004 are implementable contracts with validation hooks. SHARED-005 is git-history/process prose with no runtime behavior — valuable but belongs primarily in plan traceability. The spine doc eliminated bijection-vs-subset drift between cat-4/5; inlining back into cat-5 would recreate the failure mode R1 documented.
- **Assumptions / conditions:** Orchestrator triages R1 Appendix C stale items in category docs separately.
- **Suggested improvements:** Trim SHARED-005 to normative merge gate + reference plan ordering; demote step prose to plans (R2-F10).

---

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R2-F1 | Architecture | high | REQ-OBS-SHARED-003 MUST explicitly scope its two-layer model to **MetricDescriptor + SpanDescriptor** vs artifact-dispatch registry rows, and state whether **`EventTypeDescriptor` + `DashboardRef`** (manifest.py:279, collected in collector.py) are **in-scope** (third layer) or **explicitly out-of-scope** with a one-line consumer note. Today 001a discusses events but 003 ignores them — implementers cannot tell if event/dashboard surfaces participate in vocabulary reconciliation. | Without scoping, a reader assumes "manifest = telemetry-declaration layer" but `generate_manifest()` also emits event types and dashboard refs that share metric *names* conceptually but not `declared_type` keys. | REQ-OBS-SHARED-003 (after "Resolution — they are two distinct layers") | Doc review: section names the four manifest sections and marks each in/out of the two-layer model; CI vocabulary test scope matches the stated list. |
| R2-F2 | Validation | high | REQ-OBS-SHARED-002 MUST add a **metric bijection exceptions** subsection: (a) **indirect emitters** — recording modules that delegate to a declaring module (e.g. `costs/tracker.py` → `costs/otel_metrics.py` `_OTEL_DESCRIPTORS`); (b) **observable gauges** — matched by owning module's declaration site, not callback frequency; (c) **deprecated opt-in Prometheus path** (`session_tracking.py:336–337`, `438–503`) — excluded until REQ-AAO Phase 0.3 retirement or counted as alternate producer with mutual-exclusion guard. Also list **known second catch**: `element_registry.py` instruments (~384–401) with no `_OTEL_DESCRIPTORS`. | Strict bijection on first run will fail on at least three legitimate patterns beyond `complexity.tier_distribution`, blocking SHARED-005 keystone merge or forcing silent test disabling. | REQ-OBS-SHARED-002 (after parity table) | Test: parity helper documents exceptions; passes with tracker→otel_metrics indirection; fails on tier histogram until declared; lists element_registry as expected second failure. |
| R2-F3 | Interfaces | high | REQ-OBS-SHARED-004 MUST extend the generator routing table beyond cat-4/cat-5 binary with rows for **(c) `skip_reason=unimplemented`** (declared artifact type with no generator — taxonomy REQ-OAT-052, already emitted by `_record_unimplemented_artifact_types`) and **(d) convention-based / external metrics** in onboarding `convention_metrics` — produced artifacts referencing metrics **not** in `_OTEL_DESCRIPTORS` (no SDK `meter.create_*` site, not ContextCore cede). State these are **not** coverage failures when denominator rules from REQ-OAT-052 apply. | A generator fed both manifests today cannot classify HTTP RED / mesh metrics or Gap-2 unimplemented skips using only "produced vs owned_elsewhere". | REQ-OBS-SHARED-004 (generator routing table) | Test: metadata with `convention_metrics` routes to produced-without-sdk-declaration; declared-but-unimplemented type yields `skip_reason=unimplemented`; coverage gate matches REQ-OAT-052. |
| R2-F4 | Data | medium | REQ-OBS-SHARED-001a MUST upgrade `event_group` rename from SHOULD to **MUST** (collision is live per CAT45 §C) and require **`from_dict` backward compatibility**: accept YAML key `category` as alias for `event_group` for one release; `to_dict` emits `event_group` only. Cite consumers: `collect_event_types()` (collector.py:157), `tests/unit/test_observability_manifest.py:82`. | SHOULD allows shipping taxonomy `category` on Metric/Span while events keep the colliding field — exactly the polysemy 001a was meant to eliminate; tests and saved manifests break on hard rename without alias. | REQ-OBS-SHARED-001a bullet list + Validation | Test: round-trip old YAML with `event_types[].category` deserializes; new output uses `event_group`; Metric/Span `category` means taxonomy only. |
| R2-F5 | Validation | medium | REQ-OBS-SHARED-003 validation MUST clarify that **conceptual overlap is permitted**: the same metric name MAY appear in `MetricDescriptor.name`, `DashboardRef.metrics_used`, and onboarding `manifest_declared[]` without violating row-disjointness — the assertion is on **registry row keys** (`declared_type` vs instrument name), not on name uniqueness across the observability ecosystem. | Without this, implementers may chase false "duplicate row" bugs when dashboards reference declared metrics by design. | REQ-OBS-SHARED-003 Validation paragraph | Test/doc: worked example showing `startd8.cost.total` in descriptor + dashboard ref + artifact metadata passes vocabulary + disjointness checks. |
| R2-F6 | Risks | high | REQ-OBS-SHARED-005 MUST document **reverse dependency**: cat-4 PRO-008 span-attribute rename (`task.*` → `codegen.task.*`, CAT45 §B-3) SHOULD land **before** cat-4 project spans enter the SHARED-002 subset check, or parity will encode the `task.status` polysemy as a passing subset. Add as step 1.5 or explicit cat-4 Phase 0 prerequisite. | Forward-only "cat-5 keystone first" misses that span **attribute naming** must be stable before declaration+parity — otherwise cat-4 work creates debt the parity test cannot detect as collision. | REQ-OBS-SHARED-005 numbered list | Traceability: cat-4 plan shows PRO-008 before Phase 2 span declaration; parity test uses renamed attrs in fixtures. |
| R2-F7 | Validation | medium | REQ-OBS-SHARED-002 SHOULD define an optional **required span attribute allowlist** (contract/gate attrs that MUST be present on emission — bijection on that subset only) while keeping general attrs as subset. Example candidates: `phase.name`, `phase.status` on artisan phase spans where forward-manifest/gate contracts require presence. | Open span attribute sets justify subset, but some attrs are **normative contracts**; treating all attrs as optionally emitted weakens gate validation. | REQ-OBS-SHARED-002 (Spans row footnote) | Test: parity helper accepts superset for general attrs but fails if allowlisted contract attr is declared and absent on emitted span fixture. |
| R2-F8 | Architecture | low | Cross-doc hygiene (not body edit here): cat-5 `OBSERVABILITY_AI_AGENT_REQUIREMENTS.md` blockquote ~line 178 still **restates** the 5-value `category` enum despite SHARED-001 ownership — spine doc SHOULD add a note under REQ-OBS-SHARED-001 that **referencing docs MUST NOT restate enum domains** (ID-only reference pattern), matching what cat-4 PRO-002 already does. | Residual inline restatement recreates the drift vector the spine was extracted to remove. | REQ-OBS-SHARED-001 (new bullet under normative intro) | Doc audit: grep cat-4/5 reqs for enum literal lists; only spine + taxonomy contain domains. |
| R2-F9 | Ops | medium | REQ-OBS-SHARED-005 MUST add **parity bootstrap gate**: keystone PR may merge schema + helper with an explicit **allowlisted known-gap list** (initially: `complexity.tier_distribution`, element_registry instruments) transitioning to hard CI fail once declared — prevents keystone merge from blocking on every pre-existing undeclared emitter discovered sequentially. | "Exactly one diff" + immediate hard parity fail creates a chicken-and-egg where cat-5 Phase 1 cannot land until all 11+ modules are clean in the same commit. | REQ-OBS-SHARED-005 Validation + step 1 | Test/ops: CI job documents bootstrap list; removing an item from the list requires corresponding descriptor declaration in same PR. |
| R2-F10 | Architecture | low | **Adversarial — trim SHARED-005:** keep only normative merge invariant ("exactly one diff adds schema + parity helper; cat-4 depends") in this doc; move numbered plan choreography (Phase 1/1.1 wording) to cat-4/5 **plans** as the operational source. SHARED-005 is the weakest SHARED req because it specifies process, not behavior — splitting reduces spine doc ceremony while preserving the anti-double-add invariant R1 needed. | Process steps duplicated in both plans and spine; end implementers read SHARED-001–004 for contracts, plans for sequencing. Separate spine doc stays justified (proven anti-drift); SHARED-005 prose is the accidental-complexity candidate **within** the spine. | REQ-OBS-SHARED-005 (replace numbered list with invariant + plan cross-refs) | Doc review: plans retain landing order; spine retains testable merge gate only; no triple restatement of Phase 1.1 dependency. |

#### Review Round R3 — GPT-5.5 — 2026-05-31 19:11:00 UTC

- **Reviewer**: GPT-5.5
- **Date**: 2026-05-31 19:11:00 UTC
- **Scope**: Fresh R3 stress-test of the descriptor spine, avoiding near-duplicates of R2 and focusing on collector pass-through, parity scope, exported-name collisions, and end-user failure modes.

### Executive summary — R3

- SHARED-001 can be implemented on the dataclasses but still fail silently because `collector.py` currently drops any per-descriptor fields it does not copy through.
- Metric bijection should validate both OTel names and exported Prometheus names; otherwise two "distinct" metrics can collide on the dashboard/query surface users actually see.
- The current collector's hardcoded `_INSTRUMENTED_MODULES` list is itself a drift source; a parity test built only on that list can miss whole emitting packages.
- Span parity needs to cover `name_pattern` matching and `attributes_dynamic`, not only attribute subset semantics.
- Empty `category`/`orientation` defaults are useful for compatibility but dangerous as a final accepted manifest state.
- Routing will be more robust if each row carries provenance/ownership, not if a generator infers ownership from category names.

---

**Focus ask 1 — Is SHARED-003 layer-separation actually true?**

- **Summary answer:** Yes at the key-space level, but the implementation needs provenance so row-disjointness does not become guesswork.
- **Rationale:** The artifact registry keys (`declared_type`) and telemetry descriptor keys (`MetricDescriptor.name` / `SpanDescriptor.name_pattern`) are distinct. The weaker point is not key collision but origin ambiguity: `manifest_declared[]`, `convention_based[]`, generated dashboard metric refs, and SDK descriptors can all mention the same metric name while meaning different ownership responsibilities.
- **Assumptions / conditions:** The taxonomy registry remains artifact-dispatch-only; telemetry descriptors remain the SDK telemetry declaration surface.
- **Suggested improvements:** Add row provenance (`sdk_descriptor`, `onboarding_convention`, `contextcore_owned`, `declared_unimplemented`) to the generator-facing contract so SHARED-003 stays simple without forcing name uniqueness across layers.

**Focus ask 2 — Is kind-aware parity the right cut?**

- **Summary answer:** Yes, but parity must compare the names operators query, not only the Python creation strings.
- **Rationale:** `MetricDescriptor` already has `prometheus_name`, and the code mixes dotted and underscored names (`startd8.cost.total` vs `startd8_cost_total`). A bijection over only OTel instrument names can pass while the Prometheus-exported names collide or while dashboards query the wrong spelling.
- **Assumptions / conditions:** Prometheus/Mimir remains a primary consumer for generated dashboards and alerts.
- **Suggested improvements:** Define canonical-name and exported-name checks for metrics, and require a collision test on exported names.

**Focus ask 3 — Does SHARED-005's landing sequence survive?**

- **Summary answer:** Partial — schema-before-category-work is right, but collector pass-through must land before descriptor annotation or the keystone appears to work while emitting empty axes.
- **Rationale:** `MetricDescriptor`/`SpanDescriptor` can gain `category` and `orientation`, but `collect_metric_descriptors()` and `collect_span_descriptors()` currently instantiate descriptors with a fixed set of copied fields. Any `_OTEL_DESCRIPTORS` entry that adds `category`/`orientation` is dropped unless collector pass-through co-lands.
- **Assumptions / conditions:** The generator continues to build `ObservabilityManifest` through `collector.py`.
- **Suggested improvements:** Make "collector pass-through + manifest round-trip" part of the cat-5 keystone, before any cat-4/5 descriptor annotation tasks.

**Focus ask 4 — Did references introduce new duplication or dangling pointers?**

- **Summary answer:** The ID references resolve; the remaining duplication risk is prose-defined enum domains that must be kept in sync with code.
- **Rationale:** SHARED-001 defines enum domains in Markdown, while the implementation will need code-level validators/constants to reject invalid values. If taxonomy and manifest validation each encode literal lists separately, the spine has reduced document drift but left code drift intact.
- **Assumptions / conditions:** CI will validate descriptors and taxonomy registry values rather than relying on manual review.
- **Suggested improvements:** Require one code-level enum source consumed by both manifest validation and artifact-registry validation; docs should cite that source rather than duplicate implementation literals.

**Focus ask 5 — Is SHARED-004 complete enough for one generator?**

- **Summary answer:** Not quite; routing should be driven by explicit provenance/ownership fields, not derived from category alone.
- **Rationale:** A single generator cannot reliably infer whether a metric is produced, skipped, externally observed, or unimplemented from `category=project_observability` / `ai_agent_observability`. End users care whether a dashboard panel is backed by data, skipped honestly, or awaiting a generator, so the manifest needs an explicit route reason.
- **Assumptions / conditions:** The generator consumes both SDK manifest data and onboarding metadata in one pass.
- **Suggested improvements:** Extend SHARED-004 with a small route-state enum and require every route to have user-visible status text in the generated report.

**Focus ask 6 — Adversarial: weakest SHARED req / spine doc justified?**

- **Summary answer:** The spine doc remains justified; the weakest point is SHARED-002 because "parity" sounds singular but actually contains several different checks.
- **Rationale:** The separate spine removes proven cross-doc drift, so inlining into cat-5 would reduce robustness. SHARED-002 should be split into named sub-checks (descriptor collection coverage, metric identity/export identity, span name matching, attribute subset/required attrs) so implementers can fail one precise gate instead of debating a vague "parity" failure.
- **Assumptions / conditions:** The parity helper is intended as an enduring CI gate, not a one-off migration script.
- **Suggested improvements:** Keep SHARED-002 as the parent requirement but require separately named subtests and fixtures.

---

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R3-F1 | Interfaces | critical | REQ-OBS-SHARED-001 MUST require `collector.py` pass-through for the new fields: `collect_metric_descriptors()` and `collect_span_descriptors()` must copy `category` and `orientation` from `_OTEL_DESCRIPTORS` into `MetricDescriptor`/`SpanDescriptor`, and the metric collector should preserve existing optional fields such as `prometheus_name` / `dashboard_hints` rather than silently dropping them. | Adding dataclass fields alone does not make the generated manifest carry them; current collector constructors copy only fixed legacy fields, so descriptor authors could annotate categories and still produce a manifest with empty axes. | REQ-OBS-SHARED-001 Validation | Unit test: a fake `_OTEL_DESCRIPTORS` metric/span with `category` and `orientation` survives `generate_manifest().to_dict()` round-trip; `prometheus_name` survives for metrics. |
| R3-F2 | Validation | high | REQ-OBS-SHARED-002 MUST define metric identity at two levels: canonical OTel name and exported/query name (`prometheus_name` or documented dot-to-underscore normalization). The parity helper must reject exported-name collisions even when canonical OTel names differ. | Operators and generated dashboards query the exported Prometheus/Mimir name; `startd8.cost.total` and `startd8_cost_total` are semantically distinct in code but dangerously close on the exported surface. | REQ-OBS-SHARED-002 metric row / new identity subsection | Fixture with two canonical names that normalize to one Prometheus name fails unless one descriptor has an explicit non-colliding `prometheus_name` and documented semantics. |
| R3-F3 | Validation | high | REQ-OBS-SHARED-002 MUST not let `collector.py`'s hardcoded `_INSTRUMENTED_MODULES` list define the full parity universe. Add a repo-wide instrument-creation scan (or an explicit owned exclusion registry) that catches emitters outside the collector list, including `micro_prime`, `security_prime`, `utils/artifact_inventory.py`, and `workflows/builtin/plan_ingestion_mottainai.py`. | A parity test that only walks the current descriptor-module list can pass while entire emitting packages remain undeclared, giving users an incomplete catalog with a false green check. | REQ-OBS-SHARED-002 Validation | CI compares all `meter.create_*` call sites against descriptors or an allowlisted exclusion with owner/rationale/expiry; adding a new emitter without either fails. |
| R3-F4 | Validation | high | REQ-OBS-SHARED-002 MUST include span **name-pattern parity**, not just attribute subset parity: every `SpanDescriptor.name_pattern` should match at least one runtime `start_as_current_span` site or be explicitly dynamic, and every stable runtime span family should have a descriptor. Define how `attributes_dynamic=True` affects this check. | CAT45 §B-4 shows a real phase-span name mismatch; attribute subset checks alone would miss a descriptor that names the wrong span family. `attributes_dynamic=True` already exists and needs test semantics. | REQ-OBS-SHARED-002 spans row | Fixture: `artisan.workflow.{workflow_id}.phase.{phase}` descriptor fails against runtime `phase.{phase.value}` until reconciled; `attributes_dynamic=True` spans require a name-pattern match but allow open attributes. |
| R3-F5 | Data | medium | REQ-OBS-SHARED-001 SHOULD state that `category=""` / `orientation=""` are **compatibility defaults only**, not acceptable values for newly declared or migrated descriptors after the keystone phase. Require a completeness gate that reports any unset axes by source file. | Empty defaults preserve old construction but can become a silent "unknown category" path that leaves generated dashboards and category coverage incomplete for end users. | REQ-OBS-SHARED-001 Additive/backward-compatible bullet + Validation | CI allows empty axes only for explicitly grandfathered descriptors during bootstrap; final gate fails with source-file list for any unset Metric/Span category or orientation. |
| R3-F6 | Interfaces | medium | REQ-OBS-SHARED-004 SHOULD add a generator-facing `route_state` / `provenance` enum for each signal or artifact route (`sdk_emitted`, `contextcore_owned`, `external_convention`, `declared_unimplemented`, `generated_artifact`). Do not infer routing solely from `category`. | Category answers "what domain is this for"; it does not answer "who emits it" or "why is it skipped." Explicit route state improves user-facing reports and removes brittle conditionals in the generator. | REQ-OBS-SHARED-004 table and Validation | Report fixture shows every row has a route state and user-facing explanation; changing `category` without route state does not change ownership behavior. |
| R3-F7 | Architecture | medium | REQ-OBS-SHARED-003 SHOULD require the shared enum domains to exist as one code-level source of truth imported by both descriptor validation and taxonomy-registry validation, with the Markdown table treated as documentation of that source. | The spine removes cross-doc drift, but if manifest validation and artifact validation each copy literal enum arrays, the accidental complexity simply moves from docs into code. | REQ-OBS-SHARED-003 vocabulary-level assertion | Test imports the same constants/enums in both validation paths; a synthetic bad value fails in both registries with the same error vocabulary. |
| R3-F8 | Ops | medium | REQ-OBS-SHARED-005 MUST add a keystone acceptance checklist item for "collector pass-through before annotation": schema fields, collector copying, YAML round-trip, and generated-manifest fixture must land in the same keystone diff before category-specific descriptors are annotated. | Otherwise cat-4 can depend on a "schema landed" state that still cannot preserve category/orientation through generation, causing rework and false confidence. | REQ-OBS-SHARED-005 Validation | History/PR check: the keystone PR includes dataclass fields, collector pass-through, round-trip tests, and one fixture descriptor whose axes survive generation. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R2-F1: The manifest has more surfaces than Metric/Span descriptors; scoping those surfaces prevents layer confusion.
- R2-F2: Metric bijection needs documented exceptions, especially for indirect emitters and legacy Prometheus paths.
- R2-F3: The binary emit/cede routing table is too narrow for the generator's real states.
- R2-F4: `EventTypeDescriptor.category` needs a compatibility-aware rename to avoid same-module field polysemy.
- R2-F6: The `task.*` / `codegen.task.*` reverse dependency should be ordered before span descriptor enrollment.
- R2-F9: A bootstrap gate avoids making the keystone hostage to every pre-existing telemetry gap.

**Disagreements** (prior untriaged suggestions this reviewer would modify before accepting):

- R2-F10: I would not demote SHARED-005 entirely to plan prose; keep a short normative landing/acceptance gate in the spine so the anti-double-add invariant remains visible to both category docs.

#### Review Round R4 — claude-opus-4.8 — 2026-05-31 19:14:00 UTC

- **Reviewer**: claude-opus-4.8
- **Date**: 2026-05-31 19:14:00 UTC
- **Scope**: Fresh R4 pass. Deliberately avoids R2/R3 themes (collector pass-through, exported-name identity, module-universe, routing third-states, event_group rename). New angles: orientation cardinality (falsification), collector name-dedup masking, manifest schema versioning, intra-manifest reference integrity, label cardinality/PII (Security), and onboarding-name injection (Security). Grounded in `observability/manifest.py`, `collector.py`, `artifact_generator.py`.

### Executive summary — R4

- **Falsification of SHARED-001:** `orientation` is **1:many** for a metric — one metric feeds a dashboard (human), an SLO (system), and an alert (bridge) at once — so a scalar `orientation` on `MetricDescriptor` is lossy and will mislead the generator. Orientation is a property of the *derived artifact*, not the *signal*.
- **Robustness bug the spine should name:** `collect_metric_descriptors()` dedups by `name` only (`seen_names`), **silently dropping** a same-name descriptor from another module/meter — this hides exactly the collisions SHARED-002 bijection is meant to catch.
- **Consumer contract gap:** `ObservabilityManifest.version` is hardcoded `"1.0.0"`; adding `category`/`orientation` is a consumer-visible change with **no version bump or capability signal**, so Wayfinder/ContextCore cannot detect field presence.
- **Looks-like-success failure:** hand-authored `SLOTemplate.metric` / `AlertTemplate.metric` are **excluded** from `generate_manifest()` parity; a renamed/removed metric leaves a dangling alert that **never fires** — invisible to operators.
- **Security (untouched by R2/R3):** descriptor `labels` include high-cardinality / sensitive keys (`session_id`, `correlation_id`); no cardinality or sensitivity annotation → metrics-backend blowup and PII leakage into a shared store.
- **Security:** onboarding-sourced metric names are interpolated into PromQL via `str.format` (`_INSTRUMENT_TO_QUERY[...].format(metric=prom, ...)`); the spine owns the contract but requires no validation of externally-sourced names.
- **Accidental complexity:** `meter` (namespace), `category` (5-value), and `event_group` (8-value) are now three grouping-ish axes on telemetry descriptors; relate `meter`↔`category` explicitly or they drift into a fourth lookup.

---

**Focus ask 1 — Is SHARED-003 layer-separation actually true?**

- **Summary answer:** Holds at the row-key level (consistent with R2/R3); the unaddressed leak is *sensitive label vocabulary*, not row keys.
- **Rationale:** `declared_type` vs telemetry instrument names stay disjoint. But SHARED-003 reconciles only `category`/`orientation` vocabulary; it ignores the `labels` vocabulary that flows from descriptors into generated PromQL/recording rules, where high-cardinality or PII labels become a cross-layer hazard.
- **Assumptions / conditions:** Generated artifacts consume descriptor `labels` to build queries/group-bys.
- **Suggested improvements:** Note that label vocabulary is out-of-scope for SHARED-003 reconciliation but governed by a new label-metadata requirement (R4-F5).

**Focus ask 2 — Is kind-aware parity the right cut?**

- **Summary answer:** The metric/span split is right, but the metric side has a *self-inflicted blind spot* in the collector and an *orientation* mismodeling.
- **Rationale:** Beyond R3's exported-name and module-universe points, `collect_metric_descriptors()` dedups by name (`seen_names`) and `generate_manifest()` keys identity on name alone — so a true duplicate/collision is dropped before any parity test sees it. Separately, bijection presumes a metric maps to one consumption orientation, but a single metric is multi-oriented.
- **Assumptions / conditions:** Parity runs over the collected manifest, not the raw `_OTEL_DESCRIPTORS` dicts.
- **Suggested improvements:** Key identity on `(meter, name)` and forbid silent name-dedup (R4-F2); move orientation off the scalar metric field (R4-F1).

**Focus ask 3 — Does SHARED-005's landing sequence survive?**

- **Summary answer:** Yes, with one added keystone artifact: the **committed manifest YAML** must be regenerated in the same diff or the repo-wide drift check breaks for everyone.
- **Rationale:** The manifest is generated, committed, and drift-checked. Adding fields without regenerating the checked-in YAML makes every subsequent CI run fail the drift check — an avoidable repo-wide block distinct from R3-F8's collector round-trip test.
- **Assumptions / conditions:** A committed manifest YAML + drift check exists (per `generate_manifest()` docstring).
- **Suggested improvements:** Add "regenerate + commit manifest YAML" to the keystone acceptance set (R4-F7).

**Focus ask 4 — Did references introduce new duplication or dangling pointers?**

- **Summary answer:** Cross-doc IDs resolve (per R2/R3); the unguarded dangling pointers are **inside the manifest** (template→metric), plus a missing **schema version** signal for consumers.
- **Rationale:** `SLOTemplate.metric` / `AlertTemplate.metric` reference metric names but are hand-authored and excluded from parity, so they can dangle silently. And consumers can't detect the new fields without a manifest schema-version bump.
- **Assumptions / conditions:** SLO/alert templates remain hand-authored and shipped in the committed YAML.
- **Suggested improvements:** Add intra-manifest reference integrity (R4-F4) and a manifest schema-version contract (R4-F3).

**Focus ask 5 — Is SHARED-004 complete enough for one generator?**

- **Summary answer:** Beyond R2/R3 route-states, the missing dimension is **trust of the inputs** the generator interpolates.
- **Rationale:** The generator substitutes onboarding-sourced metric names directly into PromQL templates; SHARED-004 routes ownership but never requires validating/escaping externally-sourced names before they reach a query string.
- **Assumptions / conditions:** Onboarding metadata can originate outside the SDK's trust boundary.
- **Suggested improvements:** Require name validation at the manifest/generator boundary (R4-F6).

**Focus ask 6 — Adversarial: weakest SHARED req / spine doc justified?**

- **Summary answer:** Spine doc justified (agree with R2/R3). The weakest *content* is SHARED-001's `orientation` field, which is mismodeled for metrics.
- **Rationale:** Unlike R2-F10 (which targeted SHARED-005 process prose), the substantive modeling error is that `orientation` is not a function of a telemetry signal — it is a function of each generated artifact. Putting a scalar `orientation` on `MetricDescriptor` forces a false 1:1 and will produce wrong dashboard/alert routing.
- **Assumptions / conditions:** A metric legitimately feeds multiple artifact kinds.
- **Suggested improvements:** Keep `category` on the signal; derive `orientation` per artifact, or make it a set with documented semantics (R4-F1).

---

| ID | Area | Severity | Suggestion | Rationale | Proposed Placement | Validation Approach |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| R4-F1 | Architecture | high | REQ-OBS-SHARED-001 MUST resolve `orientation` cardinality: a single metric feeds a dashboard (human), an SLO (system), and an alert (bridge) simultaneously, so a scalar `orientation` on `MetricDescriptor` is lossy. Either (a) keep `category` on the signal and make `orientation` a **derived per-artifact** property (not a descriptor field), or (b) type `orientation` as a **set** with documented semantics. Spans/artifacts may keep a scalar. | The current single-value field (`orientation` ∈ system\|human\|bridge per the schema table) encodes a false 1:1; a generator reading it will route a multi-oriented metric to one surface only. | REQ-OBS-SHARED-001 schema table + a new "orientation cardinality" note | Test: a metric used by dashboard+SLO+alert carries all three orientations (set) or none on the descriptor with orientation derived per generated artifact; generator emits all three surfaces. |
| R4-F2 | Data | high | REQ-OBS-SHARED-002 MUST forbid the collector's silent name-dedup from masking collisions: `collect_metric_descriptors()` skips any metric whose `name` was already seen (`seen_names`), so a genuine duplicate/cross-module collision is dropped before parity runs. Key metric identity on `(meter, name)` and have the parity helper consume pre-dedup descriptors, failing on duplicate `(meter, name)` or duplicate bare `name` across meters. | A bijection test that runs on a list the collector already de-duplicated by name cannot catch the emitted-but-undeclared/duplicate case it exists to catch — the masking happens upstream of the test. | REQ-OBS-SHARED-002 Validation (identity + collection) | Test: two modules declaring the same metric `name` (same or different meter) produce a parity failure, not a silently single manifest entry. |
| R4-F3 | Interfaces | high | REQ-OBS-SHARED-001 MUST bump the manifest **schema version** (`ObservabilityManifest.version`, hardcoded `"1.0.0"`) when `category`/`orientation` are added, and define the consumer contract: how Wayfinder/ContextCore detect field presence and how absent fields are interpreted on older manifests. | Adding consumer-visible fields without a version/capability signal means downstream generators cannot tell a pre-spine manifest (no axes) from a post-spine one with intentionally-empty axes — a silent compatibility trap. | REQ-OBS-SHARED-001 (new "manifest version / consumer contract" bullet) | Test: post-keystone `generate_manifest().version` differs from the pre-spine value; a documented rule maps "field absent" → defined consumer behavior. |
| R4-F4 | Validation | high | Add intra-manifest **reference integrity** to REQ-OBS-SHARED-002 (or a sibling clause): every `SLOTemplate.metric` and `AlertTemplate.metric` (and dashboard `metrics_used`) MUST reference a declared metric `name`. These sections are hand-authored and **excluded** from `generate_manifest()`, so they are not covered by the metric-bijection check today. | A renamed/removed metric leaves an alert or SLO referencing a nonexistent metric — a generated alert that **never fires** is a looks-like-success failure invisible to operators (the exact end-user harm the spine should prevent). | REQ-OBS-SHARED-002 Validation, new reference-integrity sub-check | Test: an `AlertTemplate.metric` not present in the declared metric set fails CI; renaming a metric without updating templates fails. |
| R4-F5 | Security | medium | REQ-OBS-SHARED-001 SHOULD add optional per-label metadata for **cardinality** and **sensitivity** (e.g. `high_cardinality: bool`, `sensitive: bool`) on descriptor `labels`, since labels like `session_id` / `correlation_id` become Prometheus label dimensions in generated dashboards/recording rules. Generators MUST avoid grouping/recording on high-cardinality or sensitive labels by default. | Today `labels` are bare strings; the SDK already declares `session_id` and `correlation_id`. Propagating these into a shared metrics backend risks cardinality blowups and PII leakage — a governance gap no prior round covered. | REQ-OBS-SHARED-001 labels note + generator guidance | Test: a descriptor label marked `high_cardinality`/`sensitive` is excluded from default group-by/recording-rule generation; lint flags unannotated known-risky labels. |
| R4-F6 | Security | medium | REQ-OBS-SHARED-004 SHOULD require validation/escaping of **externally-sourced metric names** before they are interpolated into query strings. The generator does `_INSTRUMENT_TO_QUERY[...].format(metric=prom, service=...)` with `prom` derived from onboarding `convention_metrics`/`manifest_declared`; an attacker- or typo-influenced name flows unvalidated into PromQL and dashboard JSON. | The spine owns the emit/cede contract that decides which names reach the generator; it should also require those names match a safe identifier pattern, preventing query injection / malformed-rule generation. | REQ-OBS-SHARED-004 (input-trust note) | Test: an onboarding metric name with PromQL metacharacters is rejected or sanitized before reaching `.format`; only `[a-zA-Z_:][a-zA-Z0-9_:]*` names are interpolated. |
| R4-F7 | Ops | medium | REQ-OBS-SHARED-005 keystone acceptance MUST include **regenerating and committing the manifest YAML** in the same diff as the schema fields. The manifest is generated, committed, and drift-checked; landing fields without regenerating the checked-in YAML breaks the drift check repo-wide on every later run. | This is distinct from R3-F8 (collector pass-through + round-trip *test*): here the concrete artifact is the committed YAML whose staleness fails CI for unrelated PRs. | REQ-OBS-SHARED-005 Validation checklist | CI: post-keystone, `generate_manifest()` output equals the committed YAML; a documented regen command is referenced. |
| R4-F8 | Architecture | low | REQ-OBS-SHARED-001/003 SHOULD state the relationship between the existing `meter` namespace (`startd8`, `startd8.costs`) and the new `category` axis, so `meter`, `category` (5-value), and `event_group` (8-value, per 001a) don't become three overlapping grouping concepts. Clarify that `meter` is an emission namespace and `category` is the taxonomy, with no derivation expected between them (or define one). | Opportunistic accidental-complexity reduction: three grouping-ish axes on sibling descriptor classes invite a future "which grouping do I use?" ambiguity — the same polysemy 001a is already fighting. | REQ-OBS-SHARED-003 (layer/vocabulary note) | Doc review: the doc names all three axes and their distinct roles; no validator treats `meter` as a category source unless a derivation is specified. |

**Endorsements** (prior untriaged suggestions this reviewer agrees with):

- R3-F1: Collector pass-through is the true critical path — schema fields are inert without it.
- R3-F3: The hardcoded `_INSTRUMENTED_MODULES` list is itself a drift/coverage hole.
- R2-F3 / R3-F6: The binary emit/cede routing needs explicit route/provenance states.
- R2-F9: A bootstrap allowlist keeps the keystone from being hostage to pre-existing gaps.
- R3-F7: A single code-level enum source prevents the drift from merely relocating docs→code.

**Disagreements** (prior untriaged suggestions this reviewer would weigh against):

- R3-F2 (partial): exported-name identity is valuable, but pair it with R4-F2 — the more dangerous masking is the collector's name-dedup, which hides collisions before any name-normalization check runs.
