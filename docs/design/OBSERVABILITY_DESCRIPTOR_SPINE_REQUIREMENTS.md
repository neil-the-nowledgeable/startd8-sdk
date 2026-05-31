# Observability Descriptor Spine — Shared Requirements

**Version:** 1.0
**Date:** 2026-05-31
**Status:** Normative (single source of truth for the cross-category descriptor spine)
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
- **`category` polysemy — opportunistic cleanup (REQ-OBS-SHARED-001a).** A *different* `category` field
  already exists on `EventTypeDescriptor` (manifest.py:137) with an 8-value **instrument-grouping**
  vocabulary (`agent, cost, pipeline, truncation, job, enhancement, storage, system`) — NOT this
  5-category taxonomy, though `agent`/`pipeline` overlap lexically. To avoid one module using
  `category` for two unrelated axes, the `EventTypeDescriptor` field SHOULD be renamed to
  `event_group` (the instrument-grouping axis), leaving `category` to mean the observability taxonomy
  uniformly across all three descriptor classes. Low blast radius; eliminates a pre-existing naming
  collision the taxonomy work was already fighting.

**Validation:** a schema unit test asserts both fields exist on Metric/Span descriptors with the named
enum domains and `""` defaults; existing descriptors construct unchanged; `generate_manifest()` output
includes the fields only when set.

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
- **First catch (already known):** the live `complexity.tier_distribution` histogram
  (`complexity/classifier.py:24`, recorded at :277) is **emitted but not declared** in any
  `_OTEL_DESCRIPTORS` — exactly what the metric-bijection check surfaces. (Corrects the cat-4 plan's
  stale "dead histogram" claim: it is *live but undeclared*; the fix is to **declare** it, not delete
  it. See `OBSERVABILITY_CAT45_CODE_VERIFICATION.md` §A-1.)

**Validation:** the parity test passes on the real manifest and **fails** on a deliberately
mis-declared metric (bijection) and a deliberately mis-declared span attr that isn't a subset; the
relation is documented identically wherever referenced.

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
  a member of the shared enums (a single source-of-enum check), and CI rejects a stray value in either
  layer.

**Validation:** a test asserts every `category`/`orientation` value appearing in the descriptor
manifest and in the taxonomy registry is a member of the shared enums; no overlapping `declared_type`↔
telemetry-signal row exists (the two registries are key-disjoint by construction).

---

## REQ-OBS-SHARED-004 — Emit-vs-cede boundary (one generator, two manifests)

Makes the cat-5/cat-4 ownership asymmetry implementable by a **single** artifact generator reading
both manifests (CRP R1-F8 both docs; R1-F1/S4 project; mirrors taxonomy REQ-OAT-011/052):

| Category | Ownership shape | Generator routing |
|----------|-----------------|-------------------|
| **Cat 5 (AI-agent)** | SDK **emits** in-process (every metric has a `meter.create_*` site) → its own declare-don't-guess producer | Routed as **produced** artifacts; **no** `skip_reason`. Dissolves taxonomy REQ-OAT-025 upstream-exporter dependency *for SDK-emitted metrics only*. |
| **Cat 4 (project)** | SDK **produces raw signals**; ContextCore **owns** the `contextcore_*` gauges + burndown | Routed as **honest-skip**: `skip_reason=owned_elsewhere`, `owner=contextcore`, **no** `source_checksum`, and **excluded from the `artifact_type_coverage` denominator** (taxonomy REQ-OAT-052). A cede is not a coverage failure. |

- The cede record's **field-level contract** (`skip_reason`/`owner` + denominator-exclusion) is
  REQ-OAT-052; this requirement binds cat-4 to it so the cede doesn't read as `coverage<1.0`.
- **Stale-metadata handling:** when onboarding metadata *still lists* `contextcore_task_*` as declared
  (as run-007 output does today), the generator MUST classify them as `owned_elsewhere` skips on read,
  not as startd8-emitted artifacts (CRP project R1-F5).

**Validation:** a generator fed both manifests routes cat-5 metrics as produced artifacts and cat-4
`contextcore_*` as `owned_elsewhere` skips with `owner=contextcore` and `artifact_type_coverage=1.0`;
feeding the current run-007 metadata yields the skip classification, not mis-attribution.

---

## REQ-OBS-SHARED-005 — Landing sequence (the keystone lands once)

Resolves the double-add hazard (CRP R1-S1 both plans; focus Ask 4):

1. **Cat-5 plan Phase 1 lands the keystone**: the REQ-OBS-SHARED-001 schema fields **and** the
   REQ-OBS-SHARED-002 parity helper. Cat 5 owns the descriptor manifest most directly and emits
   in-process.
2. **Cat-4 plan declares an explicit dependency edge** on that landing and performs only its
   *additive* work (declare project spans, ownership-boundary docs + cede). Cat-4 Phase 1.1 becomes
   "depends on cat-5 keystone," **not** a second add of the same fields.
3. Both target branch `feat/observability-followup-run007`; the dependency edge — not the shared
   branch alone — is what prevents the duplicate diff.

**Validation:** exactly one diff in the history adds the descriptor schema fields and the parity
helper; the cat-4 plan's traceability shows a dependency, not a duplicate step.

---

*v1.0 — Extracted from the combined cat-4/5 CRP R1 reconciliation. Owns the descriptor spine
(schema fields + enums + kind-aware parity + layer separation + emit-vs-cede + landing sequence) so
the AI-agent and project docs reference it by ID and cannot drift. Grounded by
`OBSERVABILITY_CAT45_CODE_VERIFICATION.md`.*
